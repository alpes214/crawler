# Proxy-Domain Relationship & Intelligent Rotation Strategy

## Problem Statement

**Requirements**:
1. Each domain should use a **specific set of proxies** (not all proxies)
2. For recrawling every 1 hour, use **different proxies** from the pool
3. **Intelligent rotation** to minimize proxy usage while avoiding detection
4. Track which proxy was used for which domain/URL

---

## Architecture Design

### Option 1: Many-to-Many Relationship (Recommended)

Create a junction table to map domains to their allowed proxy pool.

#### New Table: `domain_proxies`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Auto-increment ID |
| domain_id | INTEGER | FK → domains.id, NOT NULL | Domain reference |
| proxy_id | INTEGER | FK → proxies.id, NOT NULL | Proxy reference |
| is_active | BOOLEAN | DEFAULT TRUE | Enable/disable this mapping |
| priority | INTEGER | DEFAULT 5 | Proxy priority for this domain (1=highest) |
| last_used_at | TIMESTAMP | NULL | Last time this proxy was used for this domain |
| success_count | INTEGER | DEFAULT 0 | Successful requests for this domain |
| failure_count | INTEGER | DEFAULT 0 | Failed requests for this domain |
| avg_response_time_ms | INTEGER | NULL | Avg response time for this domain |
| created_at | TIMESTAMP | DEFAULT NOW() | Record creation time |
| updated_at | TIMESTAMP | DEFAULT NOW() | Last update time |

**Unique Constraint**:
```sql
ALTER TABLE domain_proxies ADD CONSTRAINT unique_domain_proxy
UNIQUE (domain_id, proxy_id);
```

**Indexes**:
```sql
CREATE INDEX idx_domain_proxies_domain_id ON domain_proxies(domain_id);
CREATE INDEX idx_domain_proxies_proxy_id ON domain_proxies(proxy_id);
CREATE INDEX idx_domain_proxies_is_active ON domain_proxies(is_active);
CREATE INDEX idx_domain_proxies_last_used_at ON domain_proxies(domain_id, last_used_at);
```

---

## Proxy Selection Strategies

### Strategy 1: Least Recently Used (LRU) - Simple

**Best for**: Even distribution, simple implementation

**Query**:
```sql
-- Select least recently used proxy for domain
SELECT
  dp.proxy_id,
  p.proxy_url,
  p.proxy_port,
  p.proxy_protocol,
  dp.last_used_at
FROM domain_proxies dp
JOIN proxies p ON dp.proxy_id = p.id
WHERE dp.domain_id = :domain_id
  AND dp.is_active = TRUE
  AND p.is_active = TRUE
  AND dp.failure_count < 5  -- Avoid failing proxies
ORDER BY
  dp.last_used_at ASC NULLS FIRST  -- Never used first, then oldest
LIMIT 1;
```

**Update after use**:
```sql
UPDATE domain_proxies
SET
  last_used_at = NOW(),
  success_count = success_count + 1,
  failure_count = 0,  -- Reset on success
  updated_at = NOW()
WHERE domain_id = :domain_id
  AND proxy_id = :proxy_id;
```

**Example Behavior**:
```
Domain: amazon.com
Proxy Pool: [proxy1, proxy2, proxy3]

Hour 1: Use proxy1 (last_used_at = NULL → oldest)
Hour 2: Use proxy2 (last_used_at = NULL → oldest)
Hour 3: Use proxy3 (last_used_at = NULL → oldest)
Hour 4: Use proxy1 (last_used_at = Hour 1 → oldest)
Hour 5: Use proxy2 (last_used_at = Hour 2 → oldest)
...
```

**Pros**:
- Simple implementation
- Even distribution across proxies
- Predictable behavior

**Cons**:
- Doesn't consider proxy health/performance
- Fixed rotation pattern (detectable)

---

### Strategy 2: Weighted Round-Robin with Health Score

**Best for**: Prioritize healthy, fast proxies while still rotating

**Health Score Calculation**:
```sql
-- Health score: 0-100 (higher is better)
-- Formula: success_rate * 50 + response_time_score * 30 + recency_score * 20

WITH proxy_scores AS (
  SELECT
    dp.proxy_id,
    dp.domain_id,
    -- Success rate: 0-50 points
    CASE
      WHEN (dp.success_count + dp.failure_count) = 0 THEN 25  -- New proxy, neutral score
      ELSE (dp.success_count::FLOAT / (dp.success_count + dp.failure_count)) * 50
    END as success_score,

    -- Response time: 0-30 points (faster = better)
    CASE
      WHEN dp.avg_response_time_ms IS NULL THEN 15  -- New proxy, neutral score
      WHEN dp.avg_response_time_ms <= 500 THEN 30
      WHEN dp.avg_response_time_ms <= 1000 THEN 25
      WHEN dp.avg_response_time_ms <= 2000 THEN 20
      WHEN dp.avg_response_time_ms <= 5000 THEN 10
      ELSE 5
    END as response_time_score,

    -- Recency: 0-20 points (least recently used = better)
    CASE
      WHEN dp.last_used_at IS NULL THEN 20  -- Never used, highest score
      WHEN dp.last_used_at < NOW() - INTERVAL '6 hours' THEN 20
      WHEN dp.last_used_at < NOW() - INTERVAL '3 hours' THEN 15
      WHEN dp.last_used_at < NOW() - INTERVAL '1 hour' THEN 10
      ELSE 5
    END as recency_score
  FROM domain_proxies dp
  WHERE dp.domain_id = :domain_id
    AND dp.is_active = TRUE
)
SELECT
  ps.proxy_id,
  p.proxy_url,
  p.proxy_port,
  (ps.success_score + ps.response_time_score + ps.recency_score) as health_score
FROM proxy_scores ps
JOIN proxies p ON ps.proxy_id = p.id
WHERE p.is_active = TRUE
ORDER BY health_score DESC
LIMIT 1;
```

**Pros**:
- Considers proxy performance
- Avoids slow/failing proxies
- Still rotates through pool

**Cons**:
- More complex query
- Slightly higher database load

---

### Strategy 3: Time-Based Rotation with Randomization

**Best for**: Avoid detection, unpredictable pattern

**Query**:
```sql
-- Select random proxy from top N least recently used
WITH eligible_proxies AS (
  SELECT
    dp.proxy_id,
    p.proxy_url,
    p.proxy_port,
    p.proxy_protocol,
    dp.last_used_at,
    ROW_NUMBER() OVER (ORDER BY dp.last_used_at ASC NULLS FIRST) as rank
  FROM domain_proxies dp
  JOIN proxies p ON dp.proxy_id = p.id
  WHERE dp.domain_id = :domain_id
    AND dp.is_active = TRUE
    AND p.is_active = TRUE
    AND dp.failure_count < 5
)
SELECT proxy_id, proxy_url, proxy_port, proxy_protocol
FROM eligible_proxies
WHERE rank <= 3  -- Top 3 least recently used
ORDER BY RANDOM()  -- Pick one randomly
LIMIT 1;
```

**Example Behavior**:
```
Domain: amazon.com
Proxy Pool: [proxy1, proxy2, proxy3, proxy4, proxy5]

Hour 1: Candidates [proxy1, proxy2, proxy3] → Random → proxy2
Hour 2: Candidates [proxy1, proxy3, proxy4] → Random → proxy4
Hour 3: Candidates [proxy1, proxy3, proxy5] → Random → proxy1
Hour 4: Candidates [proxy3, proxy5, proxy2] → Random → proxy5
...
```

**Pros**:
- Unpredictable pattern
- Still ensures rotation
- Harder to detect

**Cons**:
- Slightly uneven distribution
- More complex logic

---

### Strategy 4: Geographic/Provider Distribution

**Best for**: Large proxy pools, geo-specific requirements

**Add columns to proxies table**:
```sql
ALTER TABLE proxies ADD COLUMN country_code VARCHAR(2);
ALTER TABLE proxies ADD COLUMN provider VARCHAR(100);
```

**Query**:
```sql
-- Rotate through different providers/countries
WITH last_used_proxy AS (
  SELECT
    p.provider,
    p.country_code
  FROM crawl_tasks ct
  JOIN domain_proxies dp ON ct.proxy_id = dp.proxy_id
  JOIN proxies p ON dp.proxy_id = p.id
  WHERE ct.domain_id = :domain_id
    AND ct.completed_at IS NOT NULL
  ORDER BY ct.completed_at DESC
  LIMIT 1
)
SELECT
  dp.proxy_id,
  p.proxy_url,
  p.proxy_port
FROM domain_proxies dp
JOIN proxies p ON dp.proxy_id = p.id
LEFT JOIN last_used_proxy lup ON
  p.provider = lup.provider
  AND p.country_code = lup.country_code
WHERE dp.domain_id = :domain_id
  AND dp.is_active = TRUE
  AND p.is_active = TRUE
  AND lup.provider IS NULL  -- Different provider than last time
ORDER BY dp.last_used_at ASC NULLS FIRST
LIMIT 1;
```

**Pros**:
- Rotate through different providers
- Good for bypassing provider-level blocks
- Geographic diversity

**Cons**:
- Requires provider/country metadata
- More complex setup

---

## Recommended Implementation

### Phase 1: Start with LRU (Simple)

**Why**:
- Easy to implement
- Predictable behavior
- Good enough for MVP
- Can upgrade later

**Implementation**:
```python
# src/services/proxy_service.py

from sqlalchemy import select
from src.core.models.domain_proxy import DomainProxy
from src.core.models.proxy import Proxy

class ProxyService:
    def __init__(self, db_session):
        self.db = db_session

    def get_proxy_for_domain(self, domain_id: int):
        """
        Select least recently used proxy for domain
        """
        query = (
            select(
                DomainProxy.proxy_id,
                Proxy.proxy_url,
                Proxy.proxy_port,
                Proxy.proxy_protocol,
                Proxy.proxy_username,
                Proxy.proxy_password
            )
            .join(Proxy, DomainProxy.proxy_id == Proxy.id)
            .where(
                DomainProxy.domain_id == domain_id,
                DomainProxy.is_active == True,
                Proxy.is_active == True,
                DomainProxy.failure_count < 5
            )
            .order_by(
                DomainProxy.last_used_at.asc().nulls_first()
            )
            .limit(1)
        )

        result = self.db.execute(query).first()

        if not result:
            raise NoProxyAvailableError(f"No active proxy for domain {domain_id}")

        return {
            'proxy_id': result.proxy_id,
            'proxy_url': result.proxy_url,
            'proxy_port': result.proxy_port,
            'proxy_protocol': result.proxy_protocol,
            'proxy_username': result.proxy_username,
            'proxy_password': result.proxy_password
        }

    def mark_proxy_used(self, domain_id: int, proxy_id: int,
                        success: bool, response_time_ms: int = None):
        """
        Update proxy usage stats after request
        """
        domain_proxy = self.db.query(DomainProxy).filter(
            DomainProxy.domain_id == domain_id,
            DomainProxy.proxy_id == proxy_id
        ).first()

        if not domain_proxy:
            return

        domain_proxy.last_used_at = datetime.now()
        domain_proxy.updated_at = datetime.now()

        if success:
            domain_proxy.success_count += 1
            domain_proxy.failure_count = 0  # Reset consecutive failures

            # Update average response time
            if response_time_ms:
                if domain_proxy.avg_response_time_ms:
                    domain_proxy.avg_response_time_ms = (
                        domain_proxy.avg_response_time_ms + response_time_ms
                    ) // 2
                else:
                    domain_proxy.avg_response_time_ms = response_time_ms
        else:
            domain_proxy.failure_count += 1

            # Auto-disable after 5 consecutive failures
            if domain_proxy.failure_count >= 5:
                domain_proxy.is_active = False

        self.db.commit()
```

**Usage in crawler worker**:
```python
# src/workers/crawler.py

@celery_app.task
def crawl_url_task(task_id: int):
    db = SessionLocal()
    try:
        task = db.query(CrawlTask).get(task_id)
        domain = db.query(Domain).get(task.domain_id)

        # Get proxy for this domain
        proxy_service = ProxyService(db)
        proxy = proxy_service.get_proxy_for_domain(domain.id)

        # Update task with proxy info
        task.proxy_id = proxy['proxy_id']
        task.status = 'crawling'
        task.started_at = datetime.now()
        db.commit()

        # Make HTTP request with proxy
        start_time = time.time()
        response = await fetch_url(
            url=task.url,
            proxy_url=f"{proxy['proxy_protocol']}://{proxy['proxy_url']}:{proxy['proxy_port']}",
            proxy_auth=(proxy['proxy_username'], proxy['proxy_password'])
        )
        response_time_ms = int((time.time() - start_time) * 1000)

        # Save HTML
        html_path = save_html(task.id, response.text)

        # Update task
        task.html_path = html_path
        task.http_status_code = response.status_code
        task.response_time_ms = response_time_ms
        task.status = 'downloaded'
        db.commit()

        # Mark proxy as successful
        proxy_service.mark_proxy_used(
            domain_id=domain.id,
            proxy_id=proxy['proxy_id'],
            success=True,
            response_time_ms=response_time_ms
        )

        # Queue for parsing
        parse_product_task.apply_async(args=[task.id], queue='parse_queue')

    except Exception as e:
        # Mark proxy as failed
        if proxy:
            proxy_service.mark_proxy_used(
                domain_id=domain.id,
                proxy_id=proxy['proxy_id'],
                success=False
            )

        # Update task with error
        task.status = 'failed'
        task.error_message = str(e)
        task.retry_count += 1
        db.commit()
    finally:
        db.close()
```

---

### Phase 2: Upgrade to Weighted Health Score

When you have enough data, upgrade to health-based selection for better performance.

---

## Domain-Proxy Mapping Management

### API Endpoints

#### 1. Assign Proxies to Domain

**POST** `/api/admin/domains/{domain_id}/proxies`

```json
{
  "proxy_ids": [1, 2, 3, 4, 5],
  "priority": 5
}
```

**SQL**:
```sql
-- Insert multiple proxies for domain
INSERT INTO domain_proxies (domain_id, proxy_id, priority)
VALUES
  (:domain_id, 1, 5),
  (:domain_id, 2, 5),
  (:domain_id, 3, 5),
  (:domain_id, 4, 5),
  (:domain_id, 5, 5)
ON CONFLICT (domain_id, proxy_id) DO NOTHING;
```

#### 2. Remove Proxy from Domain

**DELETE** `/api/admin/domains/{domain_id}/proxies/{proxy_id}`

```sql
DELETE FROM domain_proxies
WHERE domain_id = :domain_id
  AND proxy_id = :proxy_id;
```

#### 3. List Proxies for Domain

**GET** `/api/admin/domains/{domain_id}/proxies`

```sql
SELECT
  dp.proxy_id,
  p.proxy_url,
  p.proxy_port,
  dp.is_active,
  dp.success_count,
  dp.failure_count,
  dp.last_used_at,
  dp.avg_response_time_ms
FROM domain_proxies dp
JOIN proxies p ON dp.proxy_id = p.id
WHERE dp.domain_id = :domain_id
ORDER BY dp.priority ASC, dp.last_used_at ASC;
```

#### 4. Get Proxy Usage Stats for Domain

**GET** `/api/admin/domains/{domain_id}/proxies/stats`

```sql
SELECT
  p.proxy_url,
  p.country_code,
  dp.success_count,
  dp.failure_count,
  ROUND(
    dp.success_count::FLOAT / NULLIF(dp.success_count + dp.failure_count, 0) * 100,
    2
  ) as success_rate,
  dp.avg_response_time_ms,
  dp.last_used_at
FROM domain_proxies dp
JOIN proxies p ON dp.proxy_id = p.id
WHERE dp.domain_id = :domain_id
ORDER BY success_rate DESC;
```

**Response**:
```json
{
  "domain_id": 1,
  "domain_name": "amazon.com",
  "proxies": [
    {
      "proxy_url": "proxy1.example.com",
      "country_code": "US",
      "success_count": 1543,
      "failure_count": 12,
      "success_rate": 99.23,
      "avg_response_time_ms": 487,
      "last_used_at": "2025-11-29T14:30:00Z"
    },
    {
      "proxy_url": "proxy2.example.com",
      "country_code": "DE",
      "success_count": 1502,
      "failure_count": 45,
      "success_rate": 97.09,
      "avg_response_time_ms": 623,
      "last_used_at": "2025-11-29T13:30:00Z"
    }
  ]
}
```

---

## Intelligent Proxy Pool Sizing

### How Many Proxies per Domain?

**Calculation**:
```
Required Proxies = (Requests per Hour / Max Requests per Proxy per Hour) + Buffer

Example:
- Amazon.com: 100 URLs per hour
- Each proxy: Max 20 requests per hour to amazon.com (to avoid rate limiting)
- Required: 100 / 20 = 5 proxies
- With 20% buffer: 5 * 1.2 = 6 proxies
```

**Factors to consider**:
1. **Crawl frequency**: 1 URL per hour = 1 request/hour
2. **Domain rate limits**: Amazon allows ~5-10 req/min per IP
3. **Proxy provider limits**: Some providers limit requests per proxy
4. **Failure buffer**: 20-30% extra for failed proxies

### Recommended Pool Sizes

| Crawl Rate | Proxies Needed | Reasoning |
|------------|----------------|-----------|
| 10 URLs/hour | 2-3 proxies | Small pool, each proxy handles 3-5 URLs |
| 100 URLs/hour | 5-7 proxies | Medium pool, each handles 15-20 URLs |
| 1000 URLs/hour | 50-70 proxies | Large pool, each handles 15-20 URLs |
| 10000 URLs/hour | 500-700 proxies | Very large, need provider rotation |

---

## Monitoring & Alerts

### 1. Proxy Health Dashboard

**Query**:
```sql
-- Proxy health summary per domain
SELECT
  d.domain_name,
  COUNT(DISTINCT dp.proxy_id) as total_proxies,
  COUNT(DISTINCT CASE WHEN dp.is_active THEN dp.proxy_id END) as active_proxies,
  COUNT(DISTINCT CASE WHEN dp.failure_count >= 5 THEN dp.proxy_id END) as failing_proxies,
  AVG(dp.avg_response_time_ms) as avg_response_time,
  SUM(dp.success_count) as total_success,
  SUM(dp.failure_count) as total_failures
FROM domains d
LEFT JOIN domain_proxies dp ON d.id = dp.domain_id
GROUP BY d.id, d.domain_name
ORDER BY d.domain_name;
```

### 2. Alert Triggers

**Alert 1: Low Active Proxy Count**
```sql
SELECT domain_id, COUNT(*) as active_count
FROM domain_proxies
WHERE is_active = TRUE
GROUP BY domain_id
HAVING COUNT(*) < 3;  -- Less than 3 active proxies
```

**Alert 2: High Failure Rate**
```sql
SELECT
  domain_id,
  (SUM(failure_count)::FLOAT / NULLIF(SUM(success_count + failure_count), 0)) * 100 as failure_rate
FROM domain_proxies
GROUP BY domain_id
HAVING failure_rate > 10;  -- More than 10% failures
```

**Alert 3: Slow Proxies**
```sql
SELECT domain_id, proxy_id, avg_response_time_ms
FROM domain_proxies
WHERE avg_response_time_ms > 5000  -- Slower than 5 seconds
  AND is_active = TRUE;
```

---

## Migration from Global Proxy Pool

If you currently have a global proxy pool (no domain mapping):

### Step 1: Create domain_proxies table

```sql
CREATE TABLE domain_proxies (
  id SERIAL PRIMARY KEY,
  domain_id INTEGER NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
  proxy_id INTEGER NOT NULL REFERENCES proxies(id) ON DELETE CASCADE,
  is_active BOOLEAN DEFAULT TRUE,
  priority INTEGER DEFAULT 5,
  last_used_at TIMESTAMP,
  success_count INTEGER DEFAULT 0,
  failure_count INTEGER DEFAULT 0,
  avg_response_time_ms INTEGER,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(domain_id, proxy_id)
);
```

### Step 2: Populate with existing proxies

```sql
-- Assign all proxies to all domains (initial state)
INSERT INTO domain_proxies (domain_id, proxy_id)
SELECT d.id, p.id
FROM domains d
CROSS JOIN proxies p
WHERE d.is_active = TRUE
  AND p.is_active = TRUE;
```

### Step 3: Gradually refine mappings

Use API to remove unnecessary mappings:
- Monitor which proxies work best for which domains
- Remove failing proxy-domain combinations
- Add geo-specific proxies for specific domains

---

## Summary

### Key Design Decisions

1. **Many-to-Many Relationship**: `domain_proxies` junction table
2. **Per-Domain Stats**: Track success/failure per domain-proxy pair
3. **LRU Strategy**: Start simple, upgrade to health-based later
4. **Intelligent Rotation**: Avoid detection with randomization
5. **Auto-Disable**: Failed proxies automatically disabled
6. **Monitoring**: Track proxy health per domain

### Benefits

✅ **Isolation**: Each domain uses dedicated proxy pool
✅ **Rotation**: Automatic rotation every hour
✅ **Intelligence**: Health-based selection avoids bad proxies
✅ **Flexibility**: Easy to assign/remove proxies per domain
✅ **Scalability**: Supports 1000s of domains and proxies
✅ **Observability**: Detailed stats per domain-proxy pair

### Next Steps

1. Create `domain_proxies` table
2. Implement `ProxyService.get_proxy_for_domain()`
3. Update crawler worker to use proxy service
4. Create API endpoints for domain-proxy management
5. Add monitoring dashboard
6. Set up alerts for proxy health issues
