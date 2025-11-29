# Core Tables Design: domains, crawl_tasks, proxies, domain_proxies

## Overview

This document provides detailed design for the four most critical tables with focus on:
- **Scheduled restart** of crawling/parsing tasks
- **Manual restart** via API
- **State management** for crawl lifecycle
- **Intelligent proxy-domain mapping** for rotation and minimizing proxy usage

---

## 1. domains Table

### Schema

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Auto-increment ID |
| domain_name | VARCHAR(255) | UNIQUE, NOT NULL | Domain name (e.g., "amazon.com") |
| base_url | VARCHAR(512) | NOT NULL | Base URL (e.g., "https://www.amazon.com") |
| parser_name | VARCHAR(100) | NOT NULL | Parser to use (e.g., "amazon", "ebay") |
| crawl_delay_seconds | INTEGER | DEFAULT 1 | Min delay between requests |
| max_concurrent_requests | INTEGER | DEFAULT 5 | Max concurrent requests to domain |
| default_crawl_frequency | INTERVAL | DEFAULT '1 day' | Default recrawl frequency |
| is_active | BOOLEAN | DEFAULT TRUE | Enable/disable crawling for this domain |
| robots_txt_url | VARCHAR(512) | NULL | robots.txt URL |
| robots_txt_content | TEXT | NULL | Cached robots.txt content |
| robots_txt_last_fetched | TIMESTAMP | NULL | When robots.txt was last fetched |
| user_agent | VARCHAR(255) | DEFAULT 'ProductCrawler/1.0' | User agent string for this domain |
| created_at | TIMESTAMP | DEFAULT NOW() | Record creation time |
| updated_at | TIMESTAMP | DEFAULT NOW() | Last update time |

### Indexes

```sql
CREATE INDEX idx_domains_domain_name ON domains(domain_name);
CREATE INDEX idx_domains_is_active ON domains(is_active);
CREATE INDEX idx_domains_parser_name ON domains(parser_name);
```

### Design Decisions

**1. `parser_name` field**:
- Associates domain with specific parser implementation
- Allows different parsers for different domains
- Example: "amazon" → `parsers/amazon.py`

**2. `default_crawl_frequency`**:
- Sets default recrawl interval for new tasks
- Can be overridden per crawl_task
- Allows domain-specific scheduling (e.g., news sites: 1 hour, product catalogs: 1 day)

**3. `robots_txt_*` fields**:
- Cache robots.txt to avoid repeated fetches
- Check `robots_txt_last_fetched` to refresh periodically
- Extract crawl-delay directive and update `crawl_delay_seconds`

**4. `is_active` flag**:
- Global kill switch for domain crawling
- Scheduler skips tasks for inactive domains
- Useful for maintenance or blocking problematic domains

### Sample Data

```sql
INSERT INTO domains (domain_name, base_url, parser_name, crawl_delay_seconds, default_crawl_frequency)
VALUES
  ('amazon.com', 'https://www.amazon.com', 'amazon', 2, INTERVAL '1 day'),
  ('ebay.com', 'https://www.ebay.com', 'ebay', 1, INTERVAL '12 hours'),
  ('etsy.com', 'https://www.etsy.com', 'etsy', 1, INTERVAL '1 day');
```

---

## 2. crawl_tasks Table (Enhanced for Restart Capabilities)

### Schema

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Auto-increment ID |
| domain_id | INTEGER | FK → domains.id, NOT NULL | Reference to domain |
| url | TEXT | NOT NULL | Full URL to crawl |
| url_hash | VARCHAR(64) | UNIQUE, NOT NULL | SHA256 hash of URL (deduplication) |
| status | VARCHAR(50) | NOT NULL | Current task status (see enum) |
| priority | INTEGER | DEFAULT 5 | Priority (1=highest, 10=lowest) |
| scheduled_at | TIMESTAMP | NOT NULL | When to execute task |
| started_at | TIMESTAMP | NULL | When crawling started |
| completed_at | TIMESTAMP | NULL | When task completed/failed |
| retry_count | INTEGER | DEFAULT 0 | Number of retry attempts (current phase) |
| max_retries | INTEGER | DEFAULT 3 | Max retries before marking failed |
| error_message | TEXT | NULL | Last error message |
| crawl_frequency | INTERVAL | DEFAULT '1 day' | How often to re-crawl |
| next_crawl_at | TIMESTAMP | NULL | Next scheduled crawl time |
| recrawl_count | INTEGER | DEFAULT 0 | Total number of times recrawled |
| is_recurring | BOOLEAN | DEFAULT TRUE | Whether to schedule next crawl |
| html_path | VARCHAR(512) | NULL | Path to saved HTML file |
| http_status_code | INTEGER | NULL | HTTP response code (200, 404, 500, etc.) |
| response_time_ms | INTEGER | NULL | Response time in milliseconds |
| proxy_id | INTEGER | FK → proxies.id, NULL | Proxy used for this request |
| created_at | TIMESTAMP | DEFAULT NOW() | First creation time |
| updated_at | TIMESTAMP | DEFAULT NOW() | Last update time |
| created_by | VARCHAR(100) | DEFAULT 'system' | Who created task (system/admin/api) |

### Status Enum (Detailed)

```python
class CrawlTaskStatus(str, Enum):
    # Initial states
    PENDING = "pending"          # Waiting to be queued
    QUEUED = "queued"            # Sent to RabbitMQ crawl_queue

    # Crawling phase
    CRAWLING = "crawling"        # HTTP request in progress
    DOWNLOADED = "downloaded"    # HTML saved, ready for parsing

    # Parsing phase
    QUEUED_PARSE = "queued_parse"  # Sent to RabbitMQ parse_queue
    PARSING = "parsing"          # Extraction in progress

    # Terminal states
    COMPLETED = "completed"      # Successfully completed both phases
    FAILED = "failed"            # Failed after max retries

    # Admin control states
    PAUSED = "paused"            # Admin paused this task
    CANCELLED = "cancelled"      # Admin cancelled this task
```

### Indexes

```sql
CREATE INDEX idx_crawl_tasks_status ON crawl_tasks(status);
CREATE INDEX idx_crawl_tasks_scheduled_at ON crawl_tasks(scheduled_at) WHERE status = 'pending';
CREATE INDEX idx_crawl_tasks_domain_id ON crawl_tasks(domain_id);
CREATE INDEX idx_crawl_tasks_url_hash ON crawl_tasks(url_hash);
CREATE INDEX idx_crawl_tasks_next_crawl_at ON crawl_tasks(next_crawl_at) WHERE is_recurring = TRUE;
CREATE INDEX idx_crawl_tasks_priority ON crawl_tasks(priority, scheduled_at);
CREATE INDEX idx_crawl_tasks_created_by ON crawl_tasks(created_by);
```

### State Transitions

```
┌─────────────────────────────────────────────────────────────────┐
│                     Crawl Task Lifecycle                         │
└─────────────────────────────────────────────────────────────────┘

[CREATED]
    ↓
PENDING ────────────────┐
    ↓                   │
QUEUED                  │ Admin pause
    ↓                   │
CRAWLING ───────────────┼──→ PAUSED ──────┐
    ↓                   │       ↑          │
    ├─ Success ─────────┤       │          │ Admin resume
    │                   │       │          │
DOWNLOADED              │       │          ↓
    ↓                   │   [Restart]   PENDING
QUEUED_PARSE            │               (retry_count++)
    ↓                   │
PARSING ────────────────┤
    ↓                   │
    ├─ Success         │
    │                   │
COMPLETED ──────────────┤
    │                   │
    │ (if is_recurring) │
    │                   │
    └──→ Schedule       │
         next_crawl_at  │
         Create new     │
         PENDING task   │
                        │
    ├─ Failure ─────────┤
    │                   │
    └──→ FAILED ────────┘
         (retry_count >= max_retries)


Admin Actions:
- PAUSE:   pending/queued/crawling/parsing → paused
- RESUME:  paused → pending (requeue)
- CANCEL:  any state → cancelled
- RESTART: failed/completed → pending (reset retry_count)
- PRIORITY: Update priority field (requeue if needed)
```

### Restart Mechanisms

#### 1. Scheduled Recrawl (Automatic)

**Trigger**: Completed task with `is_recurring = TRUE`

**Process**:
1. Task completes successfully (`status = 'completed'`)
2. Calculate `next_crawl_at = completed_at + crawl_frequency`
3. Scheduler (Celery Beat) runs every 10 seconds:
   ```sql
   SELECT * FROM crawl_tasks
   WHERE status = 'completed'
     AND is_recurring = TRUE
     AND next_crawl_at <= NOW()
   LIMIT 100;
   ```
4. For each task found:
   - Insert new task: `INSERT INTO crawl_tasks (...) VALUES (...)`
   - Copy: url, domain_id, priority, crawl_frequency
   - Set: status='pending', scheduled_at=NOW(), retry_count=0
   - Increment: recrawl_count++
   - Update original: `next_crawl_at = next_crawl_at + crawl_frequency`

**Alternative Design**: Update existing task instead of creating new one
- Pro: No duplicate rows, simpler queries
- Con: Lose historical data (when was it last crawled?)
- **Recommendation**: Create new task (preserves history)

#### 2. Manual Restart via API (Admin Control)

##### API Endpoint: `POST /api/admin/tasks/{task_id}/restart`

**Request Body**:
```json
{
  "reset_retry_count": true,      // Optional: reset to 0
  "priority": 1,                   // Optional: change priority
  "scheduled_at": "2025-11-30T10:00:00Z"  // Optional: schedule for later
}
```

**Response**:
```json
{
  "task_id": 12345,
  "status": "pending",
  "scheduled_at": "2025-11-30T10:00:00Z",
  "retry_count": 0,
  "message": "Task restarted successfully"
}
```

**SQL Logic**:
```sql
-- Restart from any state
UPDATE crawl_tasks
SET
  status = 'pending',
  scheduled_at = COALESCE(:scheduled_at, NOW()),
  priority = COALESCE(:priority, priority),
  retry_count = CASE WHEN :reset_retry_count THEN 0 ELSE retry_count END,
  error_message = NULL,
  started_at = NULL,
  completed_at = NULL,
  updated_at = NOW()
WHERE id = :task_id;

-- Then publish to RabbitMQ
```

##### API Endpoint: `POST /api/admin/tasks/{task_id}/restart-parsing`

**Use Case**: Crawling succeeded but parsing failed, restart only parsing phase

**Request Body**:
```json
{
  "reset_retry_count": true
}
```

**SQL Logic**:
```sql
-- Restart from 'downloaded' state (skip crawling)
UPDATE crawl_tasks
SET
  status = 'downloaded',  -- Back to ready for parsing
  retry_count = CASE WHEN :reset_retry_count THEN 0 ELSE retry_count END,
  error_message = NULL,
  updated_at = NOW()
WHERE id = :task_id
  AND html_path IS NOT NULL;  -- Ensure HTML exists

-- Then publish to parse_queue
```

##### API Endpoint: `POST /api/admin/tasks/restart-failed`

**Use Case**: Restart ALL failed tasks (bulk operation)

**Request Body**:
```json
{
  "domain_id": 1,           // Optional: filter by domain
  "failed_after": "2025-11-28T00:00:00Z",  // Optional: filter by failure date
  "limit": 1000             // Optional: max tasks to restart
}
```

**SQL Logic**:
```sql
-- Restart multiple failed tasks
UPDATE crawl_tasks
SET
  status = 'pending',
  scheduled_at = NOW(),
  retry_count = 0,
  error_message = NULL,
  started_at = NULL,
  completed_at = NULL,
  updated_at = NOW()
WHERE status = 'failed'
  AND domain_id = COALESCE(:domain_id, domain_id)
  AND completed_at >= COALESCE(:failed_after, '1970-01-01')
LIMIT :limit
RETURNING id, url;

-- Then bulk publish to RabbitMQ
```

#### 3. Pause/Resume Mechanism

##### API Endpoint: `POST /api/admin/tasks/{task_id}/pause`

**SQL Logic**:
```sql
UPDATE crawl_tasks
SET status = 'paused', updated_at = NOW()
WHERE id = :task_id
  AND status IN ('pending', 'queued', 'crawling', 'parsing');
```

**RabbitMQ Handling**:
- If status is 'queued': Message already in queue (will be processed)
- Worker checks task status before starting:
  ```python
  def crawl_task(task_id):
      task = db.query(CrawlTask).get(task_id)
      if task.status == 'paused':
          # Re-queue for later or skip
          return
  ```

##### API Endpoint: `POST /api/admin/tasks/{task_id}/resume`

**SQL Logic**:
```sql
UPDATE crawl_tasks
SET status = 'pending', scheduled_at = NOW(), updated_at = NOW()
WHERE id = :task_id
  AND status = 'paused';

-- Then publish to RabbitMQ
```

#### 4. Priority Change (Re-prioritize)

##### API Endpoint: `PATCH /api/admin/tasks/{task_id}/priority`

**Request Body**:
```json
{
  "priority": 1
}
```

**SQL Logic**:
```sql
UPDATE crawl_tasks
SET priority = :priority, updated_at = NOW()
WHERE id = :task_id;
```

**Note**: Already queued messages in RabbitMQ won't be re-ordered. Priority only affects:
- Future scheduling queries (ORDER BY priority)
- Priority queue routing

---

## 3. proxies Table

### Schema

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Auto-increment ID |
| proxy_url | VARCHAR(255) | NOT NULL | Proxy host/IP |
| proxy_port | INTEGER | NOT NULL | Proxy port |
| proxy_protocol | VARCHAR(20) | DEFAULT 'http' | Protocol (http, https, socks5) |
| proxy_username | VARCHAR(100) | NULL | Authentication username |
| proxy_password | VARCHAR(255) | NULL | Authentication password (encrypted) |
| is_active | BOOLEAN | DEFAULT TRUE | Whether proxy is active |
| failure_count | INTEGER | DEFAULT 0 | Consecutive failure count |
| success_count | INTEGER | DEFAULT 0 | Total successful requests |
| last_used_at | TIMESTAMP | NULL | Last time proxy was used |
| last_success_at | TIMESTAMP | NULL | Last successful request |
| last_failure_at | TIMESTAMP | NULL | Last failed request |
| avg_response_time_ms | INTEGER | NULL | Average response time |
| country_code | VARCHAR(2) | NULL | Proxy country (US, DE, etc.) |
| city | VARCHAR(100) | NULL | Proxy city |
| provider | VARCHAR(100) | NULL | Proxy provider name |
| monthly_cost | DECIMAL(10,2) | NULL | Cost tracking |
| max_requests_per_hour | INTEGER | DEFAULT 1000 | Rate limit for this proxy |
| created_at | TIMESTAMP | DEFAULT NOW() | Record creation time |
| updated_at | TIMESTAMP | DEFAULT NOW() | Last update time |

### Indexes

```sql
CREATE INDEX idx_proxies_is_active ON proxies(is_active);
CREATE INDEX idx_proxies_last_used_at ON proxies(last_used_at);
CREATE INDEX idx_proxies_failure_count ON proxies(failure_count);
CREATE INDEX idx_proxies_country_code ON proxies(country_code);
CREATE INDEX idx_proxies_provider ON proxies(provider);
```

### Proxy Selection Strategy

**Least Recently Used (LRU) with Health Check**:

```sql
-- Select best available proxy
SELECT id, proxy_url, proxy_port, proxy_protocol
FROM proxies
WHERE is_active = TRUE
  AND failure_count < 5  -- Avoid failing proxies
ORDER BY
  last_used_at ASC NULLS FIRST,  -- Prefer least recently used
  avg_response_time_ms ASC NULLS LAST  -- Prefer faster proxies
LIMIT 1;
```

**Domain-Specific Proxy Selection** (if needed):

```sql
-- Select proxy for specific country (e.g., Amazon.de needs German proxy)
SELECT id FROM proxies
WHERE is_active = TRUE
  AND country_code = 'DE'
ORDER BY last_used_at ASC
LIMIT 1;
```

### Proxy Health Management

**Auto-disable failing proxies**:

```sql
-- After proxy failure
UPDATE proxies
SET
  failure_count = failure_count + 1,
  last_failure_at = NOW(),
  is_active = CASE
    WHEN failure_count + 1 >= 10 THEN FALSE
    ELSE is_active
  END,
  updated_at = NOW()
WHERE id = :proxy_id;
```

**Auto-enable after success**:

```sql
-- After proxy success
UPDATE proxies
SET
  failure_count = 0,  -- Reset consecutive failures
  success_count = success_count + 1,
  last_success_at = NOW(),
  last_used_at = NOW(),
  is_active = TRUE,  -- Re-enable if was disabled
  avg_response_time_ms = (:response_time_ms + COALESCE(avg_response_time_ms, 0)) / 2,
  updated_at = NOW()
WHERE id = :proxy_id;
```

**Manual proxy re-enable via API**:

##### API Endpoint: `POST /api/admin/proxies/{proxy_id}/enable`

```sql
UPDATE proxies
SET
  is_active = TRUE,
  failure_count = 0,
  updated_at = NOW()
WHERE id = :proxy_id;
```

---

## 4. domain_proxies Table (Junction Table)

### Purpose

Maps domains to their allowed proxy pool, enabling:
- **Dedicated proxy sets** per domain (not global pool)
- **Per-domain performance tracking** for each proxy
- **Intelligent rotation** within domain's proxy pool
- **Domain-specific proxy health** (same proxy may perform differently for different domains)

### Schema

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Auto-increment ID |
| domain_id | INTEGER | FK → domains.id, NOT NULL | Domain reference |
| proxy_id | INTEGER | FK → proxies.id, NOT NULL | Proxy reference |
| is_active | BOOLEAN | DEFAULT TRUE | Enable/disable this mapping |
| priority | INTEGER | DEFAULT 5 | Proxy priority for this domain (1=highest) |
| last_used_at | TIMESTAMP | NULL | Last time this proxy was used for THIS domain |
| success_count | INTEGER | DEFAULT 0 | Successful requests for this domain |
| failure_count | INTEGER | DEFAULT 0 | Failed requests for this domain |
| avg_response_time_ms | INTEGER | NULL | Average response time for this domain |
| created_at | TIMESTAMP | DEFAULT NOW() | Record creation time |
| updated_at | TIMESTAMP | DEFAULT NOW() | Last update time |

### Constraints

```sql
-- Unique constraint: one mapping per domain-proxy pair
ALTER TABLE domain_proxies ADD CONSTRAINT unique_domain_proxy
UNIQUE (domain_id, proxy_id);

-- Foreign keys with cascade delete
ALTER TABLE domain_proxies
  ADD CONSTRAINT fk_domain_proxies_domain
  FOREIGN KEY (domain_id) REFERENCES domains(id) ON DELETE CASCADE;

ALTER TABLE domain_proxies
  ADD CONSTRAINT fk_domain_proxies_proxy
  FOREIGN KEY (proxy_id) REFERENCES proxies(id) ON DELETE CASCADE;
```

### Indexes

```sql
CREATE INDEX idx_domain_proxies_domain_id ON domain_proxies(domain_id);
CREATE INDEX idx_domain_proxies_proxy_id ON domain_proxies(proxy_id);
CREATE INDEX idx_domain_proxies_is_active ON domain_proxies(is_active);
CREATE INDEX idx_domain_proxies_last_used_at ON domain_proxies(domain_id, last_used_at);
CREATE INDEX idx_domain_proxies_priority ON domain_proxies(domain_id, priority, last_used_at);
```

### Relationships

```
domains (1) ──< (N) domain_proxies ──> (1) proxies

One domain has many proxies
One proxy can serve many domains
```

### Design Rationale

**Why separate table instead of storing in proxies?**
- One proxy can serve multiple domains with different performance
- Track per-domain success/failure rates
- Different last_used_at per domain (ensures rotation per domain)
- Domain-specific proxy priority

**Example**:
```
Proxy #5 for Amazon.com:
  - success_rate: 98%
  - avg_response_time: 450ms
  - last_used_at: 2025-11-29 10:00

Proxy #5 for eBay.com:
  - success_rate: 75%
  - avg_response_time: 1200ms
  - last_used_at: 2025-11-29 14:00

→ Same proxy, different performance per domain!
```

### Proxy Selection Strategy: Least Recently Used (LRU)

**Goal**: Ensure different proxy every hour, minimize proxy usage

**Query**:
```sql
-- Select least recently used proxy for domain
SELECT
  dp.proxy_id,
  p.proxy_url,
  p.proxy_port,
  p.proxy_protocol,
  p.proxy_username,
  p.proxy_password,
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

**Rotation Example**:
```
Domain: amazon.com
Proxy Pool: [proxy1, proxy2, proxy3, proxy4, proxy5]

Hour 1, 10:00 - Use proxy1 (last_used_at = NULL → oldest)
Hour 2, 11:00 - Use proxy2 (last_used_at = NULL → oldest)
Hour 3, 12:00 - Use proxy3 (last_used_at = NULL → oldest)
Hour 4, 13:00 - Use proxy4 (last_used_at = NULL → oldest)
Hour 5, 14:00 - Use proxy5 (last_used_at = NULL → oldest)
Hour 6, 15:00 - Use proxy1 (last_used_at = 10:00 → oldest)
Hour 7, 16:00 - Use proxy2 (last_used_at = 11:00 → oldest)
...

Result: Automatic rotation through all 5 proxies!
```

### Update After Use

**On Success**:
```sql
UPDATE domain_proxies
SET
  last_used_at = NOW(),
  success_count = success_count + 1,
  failure_count = 0,  -- Reset consecutive failures
  avg_response_time_ms = CASE
    WHEN avg_response_time_ms IS NULL THEN :response_time_ms
    ELSE (avg_response_time_ms + :response_time_ms) / 2
  END,
  updated_at = NOW()
WHERE domain_id = :domain_id
  AND proxy_id = :proxy_id;
```

**On Failure**:
```sql
UPDATE domain_proxies
SET
  last_used_at = NOW(),
  failure_count = failure_count + 1,
  is_active = CASE
    WHEN failure_count + 1 >= 5 THEN FALSE  -- Auto-disable after 5 failures
    ELSE is_active
  END,
  updated_at = NOW()
WHERE domain_id = :domain_id
  AND proxy_id = :proxy_id;
```

### Management Operations

**Note**: API endpoint specifications with request/response formats are in **CORE_API_DESIGN.md** (Section 4: Domain-Proxy Management API).

**SQL Operations Available**:

1. **Assign Proxies to Domain**:
```sql
INSERT INTO domain_proxies (domain_id, proxy_id, priority)
VALUES (:domain_id, :proxy_id, :priority)
ON CONFLICT (domain_id, proxy_id) DO NOTHING;
```

2. **Remove Proxy from Domain**:
```sql
DELETE FROM domain_proxies
WHERE domain_id = :domain_id AND proxy_id = :proxy_id;
```

3. **List Domain's Proxies with Stats**:
```sql
SELECT dp.*, p.proxy_url, p.proxy_port,
  ROUND(dp.success_count::FLOAT / NULLIF(dp.success_count + dp.failure_count, 0) * 100, 2) as success_rate_percent
FROM domain_proxies dp
JOIN proxies p ON dp.proxy_id = p.id
WHERE dp.domain_id = :domain_id
ORDER BY dp.priority ASC, dp.last_used_at ASC;
```

4. **Enable/Disable Mapping**:
```sql
UPDATE domain_proxies
SET is_active = :is_active, failure_count = 0, updated_at = NOW()
WHERE domain_id = :domain_id AND proxy_id = :proxy_id;
```

### Proxy Pool Sizing Strategy

**Formula**:
```
Required Proxies = (URLs per Hour / Max Requests per Proxy per Hour) + Buffer

Example:
- Amazon.com: 100 URLs/hour
- Each proxy: Max 20 requests/hour to amazon.com (avoid rate limiting)
- Required: 100 / 20 = 5 proxies
- With 20% buffer: 5 * 1.2 = 6 proxies
```

**Recommended Pool Sizes**:

| Crawl Rate | Proxies Needed | Each Proxy Handles |
|------------|----------------|-------------------|
| 10 URLs/hour | 2-3 proxies | 3-5 URLs/hour |
| 100 URLs/hour | 5-7 proxies | 15-20 URLs/hour |
| 1000 URLs/hour | 50-70 proxies | 15-20 URLs/hour |

### Sample Data

```sql
-- Create domains
INSERT INTO domains (domain_name, base_url, parser_name)
VALUES
  ('amazon.com', 'https://www.amazon.com', 'amazon'),
  ('ebay.com', 'https://www.ebay.com', 'ebay');

-- Create proxies
INSERT INTO proxies (proxy_url, proxy_port, country_code)
VALUES
  ('proxy1.example.com', 8080, 'US'),
  ('proxy2.example.com', 8080, 'DE'),
  ('proxy3.example.com', 8080, 'US'),
  ('proxy4.example.com', 8080, 'FR'),
  ('proxy5.example.com', 8080, 'US');

-- Assign proxies to amazon.com (3 proxies)
INSERT INTO domain_proxies (domain_id, proxy_id, priority)
VALUES
  (1, 1, 5),  -- Amazon → proxy1
  (1, 3, 5),  -- Amazon → proxy3
  (1, 5, 5);  -- Amazon → proxy5

-- Assign proxies to ebay.com (2 proxies)
INSERT INTO domain_proxies (domain_id, proxy_id, priority)
VALUES
  (2, 2, 5),  -- eBay → proxy2
  (2, 4, 5);  -- eBay → proxy4
```

**Result**:
- Amazon.com uses: proxy1, proxy3, proxy5 (3 US proxies)
- eBay.com uses: proxy2, proxy4 (1 DE + 1 FR proxy)
- Each domain has dedicated pool for rotation

### Monitoring & Alerts

**Alert 1: Low Active Proxy Count**
```sql
-- Alert if domain has fewer than 3 active proxies
SELECT
  d.domain_name,
  COUNT(*) as active_proxy_count
FROM domains d
LEFT JOIN domain_proxies dp ON d.id = dp.domain_id
WHERE dp.is_active = TRUE
  AND d.is_active = TRUE
GROUP BY d.id, d.domain_name
HAVING COUNT(*) < 3;
```

**Alert 2: High Failure Rate for Domain**
```sql
-- Alert if domain's proxies have >10% failure rate
SELECT
  d.domain_name,
  SUM(dp.success_count) as total_success,
  SUM(dp.failure_count) as total_failures,
  ROUND(
    SUM(dp.failure_count)::FLOAT / NULLIF(SUM(dp.success_count + dp.failure_count), 0) * 100,
    2
  ) as failure_rate_percent
FROM domains d
JOIN domain_proxies dp ON d.id = dp.domain_id
GROUP BY d.id, d.domain_name
HAVING failure_rate_percent > 10;
```

**Dashboard Query: Proxy Health per Domain**
```sql
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

---

## Scheduler Logic

### Celery Beat Configuration

**Task**: `schedule_pending_tasks` (runs every 10 seconds)

**Pseudo-code**:
```python
@celery_app.task
def schedule_pending_tasks():
    """
    Find pending tasks and publish to RabbitMQ
    """
    # 1. Find tasks ready to execute
    tasks = db.query(CrawlTask).join(Domain).filter(
        CrawlTask.status == 'pending',
        CrawlTask.scheduled_at <= datetime.now(),
        Domain.is_active == True
    ).order_by(
        CrawlTask.priority.asc(),
        CrawlTask.scheduled_at.asc()
    ).limit(100).all()

    # 2. Publish to appropriate RabbitMQ queue
    for task in tasks:
        if task.priority <= 2:
            queue = 'priority_queue'
        else:
            queue = 'crawl_queue'

        # Publish to RabbitMQ
        crawl_url_task.apply_async(
            args=[task.id],
            queue=queue
        )

        # Update status
        task.status = 'queued'
        task.updated_at = datetime.now()

    db.commit()

    # 3. Schedule recurring tasks
    schedule_recurring_tasks()

def schedule_recurring_tasks():
    """
    Create new tasks for recurring crawls
    """
    completed_tasks = db.query(CrawlTask).filter(
        CrawlTask.status == 'completed',
        CrawlTask.is_recurring == True,
        CrawlTask.next_crawl_at <= datetime.now()
    ).limit(100).all()

    for task in completed_tasks:
        # Create new task
        new_task = CrawlTask(
            domain_id=task.domain_id,
            url=task.url,
            url_hash=task.url_hash,  # Will fail if duplicate - that's ok
            status='pending',
            priority=task.priority,
            scheduled_at=datetime.now(),
            crawl_frequency=task.crawl_frequency,
            is_recurring=True,
            recrawl_count=task.recrawl_count + 1,
            created_by='scheduler'
        )

        try:
            db.add(new_task)
            db.commit()

            # Update original task's next_crawl_at
            task.next_crawl_at = task.next_crawl_at + task.crawl_frequency
            db.commit()

        except IntegrityError:
            # Duplicate url_hash - task already exists
            db.rollback()
            continue
```

---

## API Endpoints

**Note**: Complete API documentation including request/response formats, authentication, and error handling is available in **CORE_API_DESIGN.md**.

**Quick Reference** - Available endpoint groups:
- **Crawl Task Management** (12 endpoints) - Submit, monitor, restart, pause/resume tasks
- **Domain Management** (7 endpoints) - Configure domains and parsers
- **Proxy Management** (7 endpoints) - Manage proxy pool
- **Domain-Proxy Management** (6 endpoints) - Map proxies to domains
- **Product Query API** (3 endpoints) - Search and retrieve products
- **System Monitoring** (3 endpoints) - Health checks and statistics

See **CORE_API_DESIGN.md** for detailed specifications.

---

## Sample Queries

### 1. Submit Crawl Task

```sql
INSERT INTO crawl_tasks (
  domain_id, url, url_hash, status, priority, scheduled_at,
  crawl_frequency, is_recurring, created_by
)
VALUES (
  1,  -- Amazon
  'https://www.amazon.com/product/B08N5WRWNW',
  SHA256('https://www.amazon.com/product/B08N5WRWNW'),
  'pending',
  5,
  NOW(),
  INTERVAL '1 day',
  TRUE,
  'admin'
);
```

### 2. Scheduler: Find Pending Tasks

```sql
SELECT ct.id, ct.url, ct.priority, d.domain_name, d.parser_name
FROM crawl_tasks ct
JOIN domains d ON ct.domain_id = d.id
WHERE ct.status = 'pending'
  AND ct.scheduled_at <= NOW()
  AND d.is_active = TRUE
ORDER BY ct.priority ASC, ct.scheduled_at ASC
LIMIT 100;
```

### 3. Restart Failed Task

```sql
UPDATE crawl_tasks
SET
  status = 'pending',
  scheduled_at = NOW(),
  retry_count = 0,
  error_message = NULL,
  started_at = NULL,
  completed_at = NULL,
  updated_at = NOW()
WHERE id = :task_id
  AND status = 'failed';
```

### 4. Find Tasks Ready for Recrawl

```sql
SELECT * FROM crawl_tasks
WHERE status = 'completed'
  AND is_recurring = TRUE
  AND next_crawl_at <= NOW()
ORDER BY next_crawl_at ASC
LIMIT 100;
```

### 5. Select Best Proxy for Domain

```sql
-- Select least recently used proxy for specific domain
SELECT
  dp.proxy_id,
  p.proxy_url,
  p.proxy_port,
  p.proxy_protocol
FROM domain_proxies dp
JOIN proxies p ON dp.proxy_id = p.id
WHERE dp.domain_id = :domain_id
  AND dp.is_active = TRUE
  AND p.is_active = TRUE
  AND dp.failure_count < 5
ORDER BY dp.last_used_at ASC NULLS FIRST
LIMIT 1;
```

### 6. Get Task Statistics

```sql
SELECT
  status,
  COUNT(*) as count,
  AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration_seconds
FROM crawl_tasks
WHERE created_at >= NOW() - INTERVAL '1 day'
GROUP BY status;
```

---

## Key Design Principles

### 1. **Idempotency**
- `url_hash` ensures no duplicate crawls
- Restart operations are idempotent (can be called multiple times safely)

### 2. **Auditability**
- Track who created task (`created_by`)
- Preserve error messages for debugging
- Timestamp every state change

### 3. **Flexibility**
- Per-task `crawl_frequency` override
- Per-task `max_retries` override
- Priority-based scheduling

### 4. **Observability**
- Status enum covers all states
- Detailed timestamps (scheduled, started, completed)
- HTTP status codes and response times tracked

### 5. **Resilience**
- Automatic proxy rotation
- Auto-disable failing proxies
- Retry logic with exponential backoff
- Graceful handling of paused tasks

---

## Implementation Notes

### 1. URL Normalization

Before hashing, normalize URLs:
```python
from urllib.parse import urlparse, urlunparse

def normalize_url(url):
    parsed = urlparse(url.strip())
    # Remove fragment, sort query params, lowercase domain
    normalized = urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path,
        parsed.params,
        '&'.join(sorted(parsed.query.split('&'))) if parsed.query else '',
        ''  # Remove fragment
    ))
    return normalized

url_hash = hashlib.sha256(normalize_url(url).encode()).hexdigest()
```

### 2. Retry Logic with Exponential Backoff

```python
def schedule_retry(task):
    if task.retry_count < task.max_retries:
        # Exponential backoff: 1min, 2min, 4min, 8min, ...
        delay_minutes = 2 ** task.retry_count
        task.scheduled_at = datetime.now() + timedelta(minutes=delay_minutes)
        task.status = 'pending'
        task.retry_count += 1
    else:
        task.status = 'failed'
        task.completed_at = datetime.now()
```

### 3. Transaction Safety

Always wrap multi-step operations in transactions:
```python
with db.begin():
    task.status = 'pending'
    db.commit()

    # Publish to RabbitMQ
    crawl_url_task.apply_async(args=[task.id])
```

---

## Future Enhancements

### 1. Task Dependencies
```sql
ALTER TABLE crawl_tasks ADD COLUMN parent_task_id INTEGER REFERENCES crawl_tasks(id);
```
- Crawl product page, then crawl all related product pages

### 2. Task Groups/Batches
```sql
CREATE TABLE crawl_batches (
  id INTEGER PRIMARY KEY,
  name VARCHAR(255),
  created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE crawl_tasks ADD COLUMN batch_id INTEGER REFERENCES crawl_batches(id);
```
- Restart entire batch: "Restart all tasks from Black Friday crawl"

### 3. Webhook Notifications
```sql
ALTER TABLE crawl_tasks ADD COLUMN webhook_url VARCHAR(512);
```
- Notify external system when task completes

### 4. Scheduled Maintenance Windows
```sql
ALTER TABLE domains ADD COLUMN maintenance_start TIME;
ALTER TABLE domains ADD COLUMN maintenance_end TIME;
```
- Don't crawl domain during maintenance hours
