# Scale Load Estimations

This document shows the calculation methodology for deriving infrastructure requirements from business workload targets.

---

## Global Requirements

**Input Requirements**:
- Crawl: 4 billion pages/month globally
- Queries: 100 billion queries/month globally

**Time-based Conversion**:
```
Crawl rate:
  4,000,000,000 pages/month
  ÷ 30 days
  ÷ 24 hours
  ÷ 3600 seconds
  = 1,543 pages/sec globally

Query rate:
  100,000,000,000 queries/month
  ÷ 30 days
  ÷ 24 hours
  ÷ 3600 seconds
  = 38,580,000 queries/sec globally (~38M qps)
```

---

## Per-Region Workload (4 regions)

**Crawl Load per Region**:
```
1,543 pages/sec ÷ 4 regions = 385.8 pages/sec per region
385.8 pages/sec × 86,400 sec/day = 33.3M pages/day per region
33.3M pages/day × 30 days = 1 billion pages/month per region
```

**Query Load per Region**:
```
38M queries/sec ÷ 4 regions = 9.7M queries/sec per region
9.7M qps × 86,400 sec/day = 838B queries/day per region
838B queries/day × 30 days = 25 billion queries/month per region
```

---

## Message Queue Throughput Calculation

**Crawl Pipeline Message Flow**:

For each crawled page, the system generates 2 messages:
1. **Scheduler → Crawler**: `crawl_queue` (task submission)
2. **Crawler → Parser**: `parse_queue` (HTML downloaded, ready for parsing)

**Message Rate per Region**:
```
Base message rate:
  385.8 pages/sec × 2 messages per page = 771.6 msg/sec

Priority queue overhead (urgent tasks, retries):
  771.6 msg/sec × 10% = 77 msg/sec

Total sustained message rate per region:
  771.6 + 77 = ~860 msg/sec per region
```

**Peak & Burst Calculations**:
```
Peak load (3x sustained):
  860 msg/sec × 3 = 2,580 msg/sec per region

Burst load (batch uploads, mass retries):
  Assumption: 10,000 msg/sec per region (design target)
```

**Global Message Throughput**:
```
Sustained: 860 msg/sec × 4 regions = 3,440 msg/sec globally
Peak: 2,580 msg/sec × 4 regions = 10,320 msg/sec globally
```

---

## Worker Capacity Requirements

**Crawler Workers** (per region at 100% load):
```
Required throughput: 385.8 pages/sec
Worker throughput: 10 pages/sec per worker (assumed)
Workers needed: 385.8 ÷ 10 = ~39 workers minimum

Deployed: 50 workers (30% headroom for variability)
Total capacity: 50 × 10 = 500 pages/sec
Utilization: 385.8 ÷ 500 = 77%
```

**Parser Workers** (per region at 100% load):
```
Required throughput: 385.8 products/sec
Worker throughput: 10 products/sec per worker (assumed)
Workers needed: 385.8 ÷ 10 = ~39 workers minimum

Deployed: 50 workers (30% headroom)
Total capacity: 50 × 10 = 500 products/sec
Utilization: 385.8 ÷ 500 = 77%
```

**API Pods** (per region at 100% load):
```
Required throughput: 9.7M queries/sec
Pod throughput: 10,000 qps per pod (2 CPU, 4Gi RAM)
Pods needed: 9,700,000 ÷ 10,000 = 970 pods minimum

Deployed: 1,000 pods (3% headroom)
Total capacity: 1,000 × 10,000 = 10M qps
Utilization: 9.7M ÷ 10M = 97%
```

---

## Query Load Distribution by Type

**Total User Queries**: 9.7M queries/sec per region

**Query Type Breakdown** (estimated distribution):

| Query Type | % of Total | Queries/Sec | Backend System |
|------------|-----------|-------------|----------------|
| **Full-text search** | 35% | ~3.4M qps | Elasticsearch |
| **Analytics/Historical** | 45% | ~4.4M qps | ClickHouse |
| **Operational lookups** | 15% | ~1.0M qps | PostgreSQL + Redis |
| **Internal queries** | 5% | ~10K qps | PostgreSQL |

**Rationale**:
- Full-text search: Users searching for products by keywords, descriptions
- Analytics: Price history, trend analysis, product comparisons over time
- Operational: Current product details, category browsing, filtered lists
- Internal: Scheduler reads, worker metadata, proxy selection

---

## Database Capacity Requirements

### PostgreSQL

**Write Load** (per region):
```
Products inserted: 385.8 inserts/sec
Crawl task updates: 385.8 × 2 updates/sec (status changes)
Total write load: ~1,200 operations/sec

Deployed capacity: 50,000 inserts/sec
Utilization: 1,200 ÷ 50,000 = 2.4%
```

**Read Load** (per region):
```
Operational queries from users: ~1.0M qps
Internal queries (scheduler, workers): ~10K qps
Total queries to PostgreSQL: ~1.01M qps

With Redis cache (90% hit rate):
  Cache hits: 1.0M × 90% = 900K (served by Redis)
  Cache misses: 1.0M × 10% = 100K (hit PostgreSQL)
  Internal queries: 10K (always hit PostgreSQL)
  Total PostgreSQL read load: 100K + 10K = ~110K reads/sec

Deployed capacity: 500K reads/sec (1 primary + 10 replicas)
Utilization: 110K ÷ 500K = 22%
Headroom: 4.5x
```

**Key insight**: By routing analytics to ClickHouse and full-text search to Elasticsearch, PostgreSQL only handles ~10% of user queries (operational lookups), which with 90% Redis cache hit rate results in only ~110K reads/sec - well within capacity.

---

### Elasticsearch

**Indexing Load** (per region):
```
Products indexed: 385.8 docs/sec
Deployed capacity: 100,000 docs/sec
Utilization: 385.8 ÷ 100,000 = 0.4%
```

**Search Load** (per region):
```
Full-text search queries: ~3.4M qps

Search result caching strategy:
  CDN cache (5 min TTL): 70% hit rate → 3.4M × 70% = 2.38M cached
  Redis cache (search results): 20% hit rate → 3.4M × 20% = 680K cached
  Actual Elasticsearch queries: 3.4M × 10% = ~340K qps

Deployed capacity: 50,000 searches/sec (10 data nodes)
Utilization: 340K ÷ 50K = 680%

CAPACITY ISSUE: Over capacity by 6.8x
```

**Solutions**:
```
Option 1: Scale Elasticsearch cluster
  Required nodes: 340K ÷ 5K per node = 68 data nodes
  Cost: ~$136K/month per region (expensive!)

Option 2: Aggressive caching (recommended)
  CDN cache: 85% hit rate (longer TTL for popular searches)
  Redis cache: 10% hit rate (recent unique searches)
  Actual ES queries: 3.4M × 5% = 170K qps
  Required nodes: 170K ÷ 5K = 34 data nodes
  Cost: ~$68K/month per region

Option 3: Hybrid approach
  Elasticsearch (20 nodes): ~100K qps capacity
  CDN + Redis caching: 97% combined hit rate
  Actual ES queries: 3.4M × 3% = ~102K qps
  Cost: ~$40K/month per region
  Utilization: 102K ÷ 100K = ~100% (at capacity)

RECOMMENDATION: Option 3 with aggressive caching
```

---

### ClickHouse (Analytics Database)

**Write Load** (per region):
```
ETL from PostgreSQL: 385.8 inserts/sec (product updates)
Batch inserts: Products inserted into ClickHouse via periodic ETL (every 5-10 min)

ClickHouse capacity: 1M+ inserts/sec
Utilization: 385.8 ÷ 1,000,000 = 0.04%
```

**Read Load** (per region):
```
Analytical queries: ~4.4M qps
Query types: Price history, trends, comparisons, aggregations

ClickHouse capacity: 10M+ qps (columnar storage, highly optimized for analytics)
Utilization: 4.4M ÷ 10M = 44%

Deployed cluster size: 10-15 nodes (16 CPU, 128GB RAM each)
Cost: ~$30K/month per region
```

**Key insight**: ClickHouse handles the bulk of user queries (analytics) efficiently due to columnar storage optimized for aggregations and time-series data.

---

## RabbitMQ Capacity Analysis

**Per Region**:
```
Sustained load: 860 msg/sec
Peak load (3x): 2,580 msg/sec
Burst load (target): 10,000 msg/sec

Deployed: 3-node cluster
Capacity: 30,000 - 150,000 msg/sec (depends on message size)

Utilization:
  Sustained: 860 ÷ 50,000 = 1.7%
  Peak: 2,580 ÷ 50,000 = 5.2%
  Burst: 10,000 ÷ 50,000 = 20%

Headroom: 58x sustained, 19x peak, 5x burst
```

---

## Assumptions & Validation

**Key Assumptions**:
1. Crawler throughput: 10 pages/sec per worker (needs benchmarking)
2. Parser throughput: 10 products/sec per worker (needs benchmarking)
3. API pod throughput: 10,000 qps per pod (needs load testing)
4. **Query type distribution**: 35% search, 45% analytics, 15% operational, 5% other (needs user behavior analysis)
5. Redis cache hit rate: 90% for operational queries (needs monitoring data)
6. CDN cache hit rate for search: 70-85% (depends on TTL strategy)
7. Message overhead: 10% for priority queue and retries
8. Elasticsearch search capacity: 5,000 qps per data node (needs benchmarking)
9. ClickHouse query capacity: 10M qps for analytics (based on vendor specs)

**Validation Strategy**:
1. Benchmark single crawler worker with realistic sites
2. Benchmark single parser worker with real HTML samples
3. Load test API pod with realistic query patterns for all query types
4. **Analyze user behavior**: Track actual query type distribution (search vs analytics vs operational)
5. Monitor cache hit rates across CDN, Redis, and query result caching
6. Benchmark Elasticsearch with realistic search queries and concurrency
7. Adjust worker counts and infrastructure based on actual performance

**Risk Factors**:
- Slow websites reduce crawler throughput (mitigate with timeouts)
- Complex HTML reduces parser throughput (mitigate with timeout + fallback)
- **Query distribution differs from assumptions** (e.g., 60% search instead of 35%) - significant impact on Elasticsearch sizing
- Cache hit rates lower than expected (add more Redis nodes or Elasticsearch nodes)
- **Elasticsearch over capacity** even with caching - may need 20-30 nodes instead of 10
- Burst traffic patterns different than assumed (over-provision RabbitMQ)
- ClickHouse ETL lag causes stale analytics data (optimize ETL frequency)

---

## Scaling Decisions Summary

Based on these calculations, the following infrastructure decisions were made:

| Component | Sizing Rationale |
|-----------|------------------|
| **Crawler Workers** | 50 per region (77% utilization, 30% headroom) |
| **Parser Workers** | 50 per region (77% utilization, 30% headroom) |
| **API Pods** | 1,000 per region (97% utilization, minimal headroom - auto-scales) |
| **RabbitMQ** | 3-node cluster (58x headroom, over-provisioned for stability) |
| **PostgreSQL** | 1 primary + 10 replicas (22% utilization with query routing) |
| **Redis** | 20 nodes (critical for 90% cache hit rate on operational queries) |
| **Elasticsearch** | 20 nodes (handles 3.4M search qps with 97% cache hit rate) |
| **ClickHouse** | 10-15 nodes (handles 4.4M analytics qps at 44% utilization) |

**Key Architectural Insight**:

The query load (9.7M qps) is distributed across three specialized systems:
- **Elasticsearch** (35%): Full-text search with aggressive CDN/Redis caching
- **ClickHouse** (45%): Analytics/historical queries with columnar storage
- **PostgreSQL** (15%): Operational lookups with Redis caching

This distribution keeps each system well within capacity and avoids the need for massive PostgreSQL read replica scaling.

See [SCALE_ARCHITECTURE_DECISIONS.md](SCALE_ARCHITECTURE_DECISIONS.md) for detailed architectural decisions.
