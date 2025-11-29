# Scale Architecture Decisions

## Overview

This document outlines the architectural decisions for scaling the crawler to handle:
- **4 billion pages/month** globally (133M pages/day, 1,543 pages/sec)
- **100 billion queries/month** globally (3.3B queries/day, 38M queries/sec)

## Regional Distribution Strategy

### Multi-Region Architecture

**Decision**: Split workload across **4 geographic regions**

**Regions**:
1. **US-EAST** (Primary)
2. **EU-WEST** (Europe, Middle East, Africa)
3. **ASIA-SOUTH** (Asia Pacific)
4. **US-WEST** (Failover + West Coast)

**Per-Region Load**:
- Crawling: 1 billion pages/month per region (385.8 pages/sec)
- Queries: 25 billion queries/month per region (9.7M queries/sec)

**Rationale**:
- Geographic proximity reduces latency (CDN + regional endpoints)
- Load distribution prevents single region bottleneck
- Fault tolerance (region failure doesn't take down entire system)
- Compliance with data residency requirements (GDPR, etc.)

---

## Scaling Strategy: 10% to 100% Workload Per Region

### Design Principle

**Each region must be able to scale from 10% to 100% capacity dynamically:**

- **10% workload**: 38.5 pages/sec, 970K queries/sec
- **100% workload**: 385.8 pages/sec, 9.7M queries/sec

### Kubernetes Auto-Scaling

**Decision**: Use Kubernetes HorizontalPodAutoscaler (HPA) for dynamic worker scaling

**Worker Scaling Configuration**:

```yaml
# Crawler Workers
minReplicas: 5    # Handles 10% load (50 URLs/sec)
maxReplicas: 50   # Handles 100% load (500 URLs/sec)
targetCPUUtilization: 70%
targetQueueDepth: 100 messages

# Parser Workers
minReplicas: 5    # Handles 10% load (50 products/sec)
maxReplicas: 50   # Handles 100% load (500 products/sec)
targetCPUUtilization: 70%
targetQueueDepth: 100 messages

# API Pods
minReplicas: 100   # Handles 10% load (1M queries/sec)
maxReplicas: 1000  # Handles 100% load (10M queries/sec)
targetCPUUtilization: 60%
targetLatency: 50ms p95
```

**Scale-up Policy**:
- Trigger when CPU > 70% for 60 seconds
- Trigger when queue depth > 100 messages per worker
- Scale up by 50% of current replicas (max 10 pods per minute)
- Stabilization window: 60 seconds

**Scale-down Policy**:
- Trigger when CPU < 30% for 300 seconds
- Scale down by 5 pods per minute (gradual)
- Stabilization window: 300 seconds
- Never scale below minReplicas

**Rationale**:
- Kubernetes provides automatic, reactive scaling
- Cost-efficient: only pay for resources when needed
- Handles traffic spikes (batch uploads, traffic surges)
- Prevents over-provisioning during low traffic periods

---

## Infrastructure Component Scaling

### 1. RabbitMQ Cluster

**Decision**: Fixed 3-node cluster sized for 100% peak load + 3x burst capacity

**Configuration**:
```yaml
nodes: 3
resources_per_node:
  cpu: 8 cores
  memory: 16Gi
  storage: 500Gi SSD

clustering:
  policy: ha-all
  queue_mirroring: automatic
  sync_mode: automatic

capacity:
  sustained_100%: 860 msg/sec
  peak_3x: 2,571 msg/sec
  burst_capacity: 10,000 msg/sec
  theoretical_max: 150,000 msg/sec
```

**Why not auto-scale RabbitMQ?**:
- Clustering/de-clustering is complex and risky
- Queue mirroring requires stable node membership
- Message redistribution during scaling causes latency spikes
- Fixed 3-node cluster has 174x headroom (860 � 150,000 msg/sec)
- Cost is only $3,600/month per region (minimal)

**Queue Configuration**:
```yaml
crawl_queue:
  mirrored: true
  durable: true
  message_ttl: 86400  # 24 hours
  max_length: 1000000
  prefetch_count: 10  # Per worker

parse_queue:
  mirrored: true
  durable: true
  message_ttl: 86400
  max_length: 1000000
  prefetch_count: 10

priority_queue:
  mirrored: true
  durable: true
  message_ttl: 3600   # 1 hour (urgent)
  max_length: 100000
  prefetch_count: 5
```

**Rationale**:
- Over-provision for burst capacity (batch uploads)
- High availability (tolerates 1 node failure)
- Simpler than Kafka for this workload
- Predictable performance

---

### 2. PostgreSQL Cluster

**Decision**: Fixed cluster sized for 100% load with vertical scaling capability

**Configuration**:
```yaml
primary:
  cpu: 32 cores
  memory: 256Gi
  storage: 10Ti SSD (NVMe)

read_replicas: 10
  cpu: 16 cores each
  memory: 128Gi each
  storage: 10Ti SSD each

connection_pooling:
  pooler: pgBouncer
  instances: 5
  max_connections: 10000
  pool_mode: transaction

capacity:
  write_throughput: 50,000 inserts/sec
  read_throughput: 500,000 queries/sec
  current_write_load: 400 inserts/sec (0.8%)
  current_read_load: 50,000 queries/sec (10%)
```

**Scaling Strategy**:
- deploying 100% capacity for inserts/updates
- possible use of replicas for internal queries
- for API queries implementing replicas or ETL and column store database engine like ClickHouse to manage read load (prefer ETL)

---

### 3. Elasticsearch Cluster

**Decision**: Fixed cluster sized for 100% load with dynamic shard allocation

**Configuration**:
```yaml
master_nodes: 3
  cpu: 4 cores each
  memory: 16Gi each
  storage: 500Gi SSD each

data_nodes: 7
  cpu: 16 cores each
  memory: 64Gi each
  storage: 5Ti SSD each

total_capacity:
  storage: 35Ti
  indexing: 100,000 docs/sec
  search: 50,000 queries/sec
  current_load: 400 docs/sec (0.4%)

index_configuration:
  products:
    shards: 14  # 2 per data node
    replicas: 1 # For HA
    refresh_interval: 30s

  content:
    shards: 14
    replicas: 1
    refresh_interval: 30s
```

**Scaling Strategy**:
- **10% load**: Elasticsearch auto-balances shards across all nodes
- **100% load**: All data nodes actively indexing and searching
- No need to add/remove nodes (fixed cluster handles 0.4% � 100% load)

**Why fixed cluster?**:
- Shard rebalancing during node add/remove is expensive
- Current capacity (100K docs/sec) is 250x our peak load (400 docs/sec)
- Memory/CPU scales linearly with shard count (no bottleneck)
- Cost is predictable ($20K/month per region)

**Rationale**:
- Over-provisioned for burst indexing (batch imports)
- High availability (1 replica per shard)
- Fast search performance (distributed across 7 nodes)
- Simpler ops than dynamic cluster sizing

---

### 4. Redis Cache Cluster

**Decision**: Fixed cluster sized for 100% query load + 90% cache hit rate. In general we do not deploy Redis cache at the beginning. Only when required.

**Configuration**:
```yaml
nodes: 20
  memory_per_node: 64Gi
  cpu_per_node: 4 cores
  total_memory: 1.28Ti

clustering:
  mode: cluster
  shards: 20
  replicas: 1  # For HA

cache_strategy:
  eviction_policy: allkeys-lru
  maxmemory_policy: allkeys-lru
  expected_hit_rate: 85-90%

capacity:
  queries_per_second: 500,000/sec per node
  total_capacity: 10M queries/sec
  current_load_10%: 970K queries/sec (9.7%)
  current_load_100%: 9.7M queries/sec (97%)
```

**Scaling Strategy**:
- Redis cluster auto-distributes load across shards
- No need to scale nodes (20 nodes handle 10M queries/sec)
- Cache hit rate auto-adjusts based on traffic patterns

**Rationale**:
- Reduces PostgreSQL read load by 85-90%
- Fixed cluster sized for peak capacity
- LRU eviction naturally prioritizes hot data
- Cost: $8,000/month per region (worth it for 90% hit rate)

---

## Component Comparison: Auto-Scale vs Fixed

| Component | Strategy | Min � Max | Rationale |
|-----------|----------|-----------|-----------|
| **Crawler Workers** | Auto-scale (K8s HPA) | 5 � 50 pods | Linear scaling, stateless, cost-sensitive |
| **Parser Workers** | Auto-scale (K8s HPA) | 5 � 50 pods | Linear scaling, stateless, cost-sensitive |
| **API Pods** | Auto-scale (K8s HPA) | 100 � 1000 pods | Handles query spikes, stateless, latency-critical |
| **RabbitMQ** | Fixed 3-node cluster | 3 nodes | Clustering complexity, 174x headroom, minimal cost |
| **PostgreSQL** | Fixed + read replicas | 1 primary + 2-10 replicas | Vertical scaling sufficient, sharding unnecessary |
| **Elasticsearch** | Fixed 10-node cluster | 10 nodes | Shard rebalancing expensive, 250x headroom |
| **Redis** | Fixed 20-node cluster | 20 nodes | LRU auto-adapts, 10M qps capacity, predictable cost |

---

**Cost Savings**:
- Running 50 workers 24/7: $1,800/month
- Running 5-50 workers (auto-scale): ~$800/month (56% savings)

---

## Regional Independence

### Data Isolation

**Decision**: Each region maintains independent data stores

**Regional Components**:
```
Region 1 (US-EAST):
  PostgreSQL (independent database)
  Elasticsearch (independent index)
  RabbitMQ (independent queues)
  Redis (independent cache)
  S3 (regional bucket: crawler-us-east-data)

Region 2 (EU-WEST):
  PostgreSQL (independent database)
  Elasticsearch (independent index)
  RabbitMQ (independent queues)
  Redis (independent cache)
  S3 (regional bucket: crawler-eu-west-data)

... same for ASIA-SOUTH, US-WEST
```

**Cross-Region Replication** (async):
```yaml
postgresql:
  replication:
    mode: async
    replicate_to: [other 3 regions]
    lag_tolerance: 60 seconds

elasticsearch:
  cross_cluster_search: enabled
  remote_clusters: [us-east, eu-west, asia-south, us-west]

s3:
  cross_region_replication:
    enabled: true
    destinations: [2 other regions]
    lifecycle:
      - glacier: 90 days
      - delete: 365 days
```

**Why regional independence?**:
- Latency: Local reads are fast (5-10ms vs 100-200ms cross-region)
- Resilience: Region failure doesn't cascade
- Compliance: Data stays in region (GDPR, etc.)
- Cost: No cross-region data transfer for normal operations

**Why cross-region replication?**:
- Disaster recovery (region failure � failover to another region)
- Global search (search across all regions from any region)
- Data durability (S3 replication for critical HTML)

---

## Monitoring & Auto-Scaling Metrics

### Key Metrics Per Region

**RabbitMQ**:
```
rabbitmq_queue_depth{queue="crawl_queue"} > 1000 � Alert
rabbitmq_queue_depth{queue="parse_queue"} > 1000 � Alert
rabbitmq_consumer_utilization < 0.3 � Scale down workers
rabbitmq_consumer_utilization > 0.7 � Scale up workers
rabbitmq_messages_unacked > 5000 � Worker lag alert
```

**Kubernetes Workers**:
```
hpa_current_replicas{deployment="crawler-workers"}
hpa_desired_replicas{deployment="crawler-workers"}
worker_cpu_utilization > 0.7 � Scale up
worker_cpu_utilization < 0.3 � Scale down
worker_task_duration_p95 > 30s � Performance degradation alert
```

**PostgreSQL**:
```
pg_stat_database_tup_inserted (write load)
pg_stat_database_tup_fetched (read load)
pg_replication_lag_seconds > 60 � Alert
pg_connection_pool_usage > 0.8 � Add pooler instance
```

**Elasticsearch**:
```
es_indexing_rate_docs_per_sec
es_search_query_rate_per_sec
es_cluster_health != "green" � Alert
es_jvm_memory_usage > 0.8 � Alert
```

**Redis**:
```
redis_cache_hit_rate < 0.7 � Investigate cache strategy
redis_evicted_keys_per_sec > 1000 � Memory pressure
redis_used_memory > 0.9 * redis_max_memory � Alert
```

**API Tier**:
```
api_request_rate_per_sec
api_latency_p95 > 100ms � Alert
api_error_rate_5xx > 0.01 � Alert
api_pod_cpu_utilization > 0.6 � Scale up
```

---

## Cost Analysis: 10% vs 100% Load

### Per Region Monthly Costs

| Component | 10% Load | 100% Load | Notes |
|-----------|----------|-----------|-------|
| **API Pods** | $7,200 (100 pods) | $72,000 (1000 pods) | Auto-scales |
| **Crawler Workers** | $180 (5 pods) | $1,800 (50 pods) | Auto-scales |
| **Parser Workers** | $180 (5 pods) | $1,800 (50 pods) | Auto-scales |
| **Priority Workers** | $360 (10 pods) | $360 (10 pods) | Fixed |
| **RabbitMQ** | $3,600 (3 nodes) | $3,600 (3 nodes) | Fixed |
| **PostgreSQL** | $7,500 (1+2 replicas) | $15,000 (1+10 replicas) | Semi-fixed |
| **Elasticsearch** | $20,000 (10 nodes) | $20,000 (10 nodes) | Fixed |
| **Redis** | $8,000 (20 nodes) | $8,000 (20 nodes) | Fixed |
| **S3 Storage** | $1,150 (50TB) | $1,150 (50TB) | Fixed |
| **Data Transfer** | $2,000 | $10,000 | Scales with traffic |
| **Load Balancers** | $2,000 | $2,000 | Fixed |
| **Monitoring** | $3,000 | $3,000 | Fixed |
| **K8s Control Plane** | $5,000 | $5,000 | Fixed |
| **Total per region** | **$60,170** | **$143,710** | |

**4 Regions**:
- 10% load: $240,680/month
- 100% load: $574,840/month

**Savings from Auto-Scaling**:
- Without auto-scaling: $574,840/month (always 100%)
- With auto-scaling at 40% average: ~$350,000/month (39% savings)

---

## Migration Path

### Phase 1: Current Single-Node Setup
```
Current: docker-compose (single machine)
Load: Development/testing only
Cost: ~$200/month (single VPS)
```

### Phase 2: Single Region K8s (US-EAST)
```
Deploy: Kubernetes cluster in US-EAST
Workers: 5 � 50 auto-scaling
Load: 10-100% of single region (385 pages/sec max)
Cost: $60K-$144K/month (based on load)
```

### Phase 3: Multi-Region (4 regions)
```
Deploy: Replicate to EU-WEST, ASIA-SOUTH, US-WEST
Load: 4 � 385 pages/sec = 1,543 pages/sec global
Cost: $240K-$575K/month (based on load)
```

### Phase 4: Global CDN + GeoDNS
```
Add: CloudFlare CDN, Route53 GeoDNS
Traffic: Route users to nearest region
Cache: 85-90% hit rate at CDN edge
Cost: +$11K/month
```

---

## Decision Summary

### Auto-Scale Components (K8s HPA)
 **API Pods**: 100 � 1000 replicas (query spikes)
 **Crawler Workers**: 5 � 50 replicas (crawl load)
 **Parser Workers**: 5 � 50 replicas (parse load)

### Fixed Components (Sized for 100% + Headroom)
 **RabbitMQ**: 3 nodes (174x headroom)
 **PostgreSQL**: 1 primary + 2-10 read replicas (125x write headroom)
 **Elasticsearch**: 10 nodes (250x headroom)
 **Redis**: 20 nodes (sized for 10M qps)

### Regional Strategy
 **4 Regions**: US-EAST, EU-WEST, ASIA-SOUTH, US-WEST
 **Independent**: Each region has full stack
 **Async Replication**: Cross-region backup + global search
 **GeoDNS**: Route traffic to nearest region

### Rationale
- **Cost-Efficient**: Auto-scale stateless workers, fix infrastructure
- **Simple Ops**: Avoid complex distributed systems (no Kafka, no sharding)
- **Massive Headroom**: Infrastructure over-provisioned for burst capacity
- **Geographic Performance**: Multi-region reduces latency
- **Fault Tolerant**: Region failure doesn't take down entire system

---

## Initial Deployment Strategy: Right-Sizing from Day 1

### Philosophy

**Question**: Do we deploy all infrastructure for 100% load on day 1?

**Answer**: It depends on how easy the component is to scale later.

### Scaling Difficulty by Component

| Component | Initial Size | Scale Later? | Difficulty | Rationale |
|-----------|--------------|--------------|------------|-----------|
| **PostgreSQL** | 100% capacity | ❌ Hard | **CRITICAL** | Vertical scaling requires downtime, sharding is architectural change. **Size for 100% upfront.** |
| **Celery Workers** | 10% capacity | ✅ Trivial | Auto-scale via K8s HPA. Start small, let it scale. |
| **RabbitMQ** | 100% capacity | ⚠️ Moderate | Can add nodes, but queue migration is disruptive. **Deploy 3-node cluster upfront.** |
| **Elasticsearch** | 50-75% capacity | ⚠️ Moderate | Can add nodes, but rebalancing is slow. **Start with 5-7 nodes, grow to 10.** |
| **Redis** | 10-20% capacity | ✅ Easy | Redis Cluster resharding is automated. **Start with 4-5 nodes, grow to 20.** |

---

### Recommended Initial Deployment (Single Region)

#### PostgreSQL: Size for 100% Upfront ❌

**Deploy Day 1**:
```yaml
primary:
  cpu: 32 cores           # Full 100% capacity
  memory: 256Gi           # Full 100% capacity
  storage: 10Ti SSD       # Full 100% capacity

read_replicas: 2          # Start with 2, scale to 10
  cpu: 16 cores each
  memory: 128Gi each
  storage: 10Ti SSD each
```

**Why size for 100% immediately?**
- **Vertical scaling requires downtime**: Changing CPU/memory means instance restart (5-30 min downtime)
- **Storage cannot shrink**: If you start with 1TB, you can grow to 10TB, but can't go back
- **Sharding is architectural**: Moving from single DB to sharded requires app rewrite
- **Cost is manageable**: Primary costs ~$5,000/month (worth it for peace of mind)

**What you CAN scale later**:
- Read replicas: 2 → 10 (add more without downtime)
- Connection poolers: 1 → 5 pgBouncer instances

**Migration pain if undersized**:
```
Day 1: Deploy with 8 cores, 64GB RAM
Month 6: Hit 80% CPU during peak hours
         → Need to upgrade to 32 cores
         → Requires downtime window (maintenance mode)
         → Risk: Downtime during business hours, potential data loss if failover fails
         → Better to just start with 32 cores
```

---

#### RabbitMQ: Deploy 3-Node Cluster Upfront ⚠️

**Deploy Day 1**:
```yaml
nodes: 3                  # Full cluster (not 1 node)
resources_per_node:
  cpu: 8 cores
  memory: 16Gi
  storage: 500Gi
```

**Why 3 nodes from day 1?**
- **Adding nodes later requires queue migration**: Existing queues don't auto-distribute to new nodes
- **Queue mirroring needs to be configured upfront**: Can't easily change mirroring policy on live queues
- **Cost is small**: 3 nodes = $3,600/month (vs 1 node = $1,200/month, only $2,400 difference)
- **High availability**: Tolerates 1 node failure from day 1

**What happens if you start with 1 node?**
```
Day 1: Deploy 1 RabbitMQ node
Month 3: Need HA, add 2 more nodes
         → Existing queues still on node 1 (not mirrored)
         → Need to recreate queues with mirroring enabled
         → Requires draining queues, deleting, recreating
         → Risk: Message loss, downtime
```

**Can you scale to 5-7 nodes later?**
- Yes, but you won't need to (3 nodes handle 150K msg/sec, you need 860/sec)
- If you do need more: Adding nodes 4-7 is easier than adding nodes 2-3

---

#### Elasticsearch: Start with 5-7 Nodes, Scale to 10 ⚠️

**Deploy Day 1**:
```yaml
master_nodes: 3           # Full 3 masters (HA requirement)
  cpu: 4 cores each
  memory: 16Gi each

data_nodes: 5             # Start with 5, scale to 10
  cpu: 16 cores each
  memory: 64Gi each
  storage: 5Ti SSD each

index_configuration:
  products:
    shards: 10            # Plan for 10 data nodes
    replicas: 1
```

**Why start with 5-7 nodes instead of 10?**
- **Adding nodes is possible**: Elasticsearch will auto-rebalance shards to new nodes
- **Rebalancing is slow but non-blocking**: Cluster stays online, just slower during rebalance
- **Cost savings**: 5 nodes = $10K/month vs 10 nodes = $20K/month (save $10K initially)
- **10 shards work on 5 nodes**: Each node hosts 2 shards initially

**Growth path**:
```
Month 1-3: 5 data nodes (2 shards per node)
Month 4-6: 7 data nodes (1-2 shards per node) [if indexing rate increases]
Month 7+:  10 data nodes (1 shard per node) [at 100% load]
```

**Important: Create 10 shards from day 1**
- You CANNOT change shard count later without reindexing
- Start with 10 shards even if you only have 5 nodes
- When you add nodes 6-10, shards automatically rebalance

**What happens if you start with 3 nodes and 3 shards?**
```
Day 1: 3 data nodes, 3 shards
Month 6: Need more capacity, want to scale to 10 nodes
         → Problem: Only 3 shards, can't utilize 10 nodes efficiently
         → Solution: Reindex entire dataset with 10 shards
         → Pain: Hours/days of reindexing, potential downtime
```

---

#### Redis: Start with 4-5 Nodes, Scale to 20 ✅

**Deploy Day 1**:
```yaml
nodes: 5                  # Start small
  memory_per_node: 64Gi
  cpu_per_node: 4 cores
  total_memory: 320Gi     # vs 1.28Ti at full scale

clustering:
  mode: cluster
  shards: 5               # Start with 5, scale to 20
  replicas: 1
```

**Why start small?**
- **Easiest to scale**: Redis Cluster resharding is automated and fast
- **Cost savings**: 5 nodes = $2K/month vs 20 nodes = $8K/month (save $6K)
- **No downtime**: Can add nodes online, automatic resharding

**Growth path**:
```
Month 1-3: 5 nodes (handles 2.5M queries/sec)
Month 4-6: 10 nodes (handles 5M queries/sec)
Month 7+:  20 nodes (handles 10M queries/sec)
```

**How to scale Redis later**:
```bash
# Add a new node to cluster (zero downtime)
redis-cli --cluster add-node new-node:6379 existing-node:6379

# Rebalance shards (automatic, online)
redis-cli --cluster rebalance existing-node:6379 --cluster-use-empty-masters
```

**Why this is safe**:
- Resharding happens in background
- Keys are gradually moved to new nodes
- No client downtime (clients follow redirects)
- Process takes minutes, not hours

---

#### Celery Workers: Start Small, Auto-Scale ✅

**Deploy Day 1**:
```yaml
crawler_workers:
  minReplicas: 5          # Start at 10%
  maxReplicas: 50         # Scale to 100%

parser_workers:
  minReplicas: 5
  maxReplicas: 50
```

**Why start small?**
- Kubernetes HPA scales automatically based on CPU and queue depth
- No migration complexity (workers are stateless)
- Cost-efficient: Only pay for what you use

---

### Initial Deployment Summary

**Day 1 Deployment (Single Region)**:

| Component | Initial Size | Full Size | Cost Day 1 | Cost at 100% | Savings |
|-----------|--------------|-----------|------------|---------------|---------|
| PostgreSQL Primary | 32 CPU, 256GB | Same | $5,000 | $5,000 | $0 |
| PostgreSQL Replicas | 2 replicas | 10 replicas | $5,000 | $15,000 | $10,000 |
| RabbitMQ | 3 nodes | 3 nodes | $3,600 | $3,600 | $0 |
| Elasticsearch | 5 data nodes | 10 data nodes | $10,000 | $20,000 | $10,000 |
| Redis | **0 nodes (optional)** | 20 nodes | $0 | $8,000 | $8,000 |
| Celery Workers | 5+5 workers | 50+50 workers | $360 | $3,600 | $3,240 |
| API Pods | 100 pods | 1000 pods | $7,200 | $72,000 | $64,800 |
| **Total** | | | **$31,160** | **$143,710** | **$112,550** |

**Savings**: Start at **$31K/month** instead of **$144K/month** (78% savings)

**Note**: Redis is optional initially. Add when PostgreSQL read load reaches 100K+ queries/sec or when cache hit rate analysis shows benefit.

**What you size for 100% upfront**:
- ✅ PostgreSQL primary (32 CPU, 256GB RAM)
- ✅ RabbitMQ cluster (3 nodes)

**What you start small and scale later**:
- 📈 PostgreSQL read replicas (2 → 10)
- 📈 Elasticsearch data nodes (5 → 10)
- 📈 Redis nodes (0 → 20, add when needed)
- 📈 Celery workers (auto-scale)
- 📈 API pods (auto-scale)

---

### Scaling Timeline Example

**Month 1-2** (10% load):
```
PostgreSQL: 1 primary (32 CPU) + 2 replicas
RabbitMQ: 3 nodes
Elasticsearch: 3 masters + 5 data nodes
Redis: Not deployed yet (monitor PostgreSQL read load first)
Workers: 5-10 (auto-scaling)
Cost: ~$33K/month
```

**Month 3-6** (50% load):
```
PostgreSQL: 1 primary + 5 replicas (add 3)
RabbitMQ: 3 nodes (no change)
Elasticsearch: 3 masters + 7 data nodes (add 2)
Redis: 5-10 nodes (add if PostgreSQL read load > 100K qps)
Workers: 20-30 (auto-scaling)
Cost: ~$68-70K/month (depending on Redis deployment)
```

**Month 7+** (100% load):
```
PostgreSQL: 1 primary + 10 replicas (add 5)
RabbitMQ: 3 nodes (no change)
Elasticsearch: 3 masters + 10 data nodes (add 3)
Redis: 20 nodes (if deployed, scale from 5-10 → 20)
ClickHouse: Consider ETL from PostgreSQL for analytics queries
Workers: 50 (auto-scaling)
Cost: ~$136-144K/month (depending on Redis + ClickHouse)
```

---

## Open Questions

1. **Should we use Kafka instead of RabbitMQ at this scale?**
   - Current answer: No. RabbitMQ 3-node cluster handles 150K msg/sec (we need 860/sec)
   - Revisit if message rate exceeds 50K/sec sustained

2. **Should we shard PostgreSQL?**
   - Current answer: No. Single primary handles 50K writes/sec (we need 400/sec)
   - Revisit if write load exceeds 50K/sec or storage exceeds 50TB

3. **Do we need Redis if we have Elasticsearch?**
   - Current answer: Yes. Redis for hot query caching (sub-millisecond), Elasticsearch for full-text search
   - Redis reduces PostgreSQL read load by 85-90%

4. **Should we use serverless (Lambda/Cloud Run) instead of K8s?**
   - Current answer: No. Persistent workers with connection pooling are more efficient
   - Serverless has cold-start latency and connection pooling issues
   - K8s gives more control over resource allocation

5. **Should we use managed services (RDS, ElastiCache, OpenSearch) or self-hosted?**
   - **Managed pros**: Less ops burden, automated backups, easier scaling
   - **Managed cons**: 2-3x cost, less control, vendor lock-in
   - **Recommendation**: Start with managed for PostgreSQL (RDS), consider self-hosted for others
   - **Cost difference**: Managed RDS = $15K/month vs self-hosted = $5K/month

6. **When should we add ClickHouse for analytics queries?**
   - **Current answer**: Add ClickHouse when PostgreSQL read replicas struggle with analytics/reporting queries
   - **Use case**: Aggregations, time-series analysis, dashboards, heavy reporting
   - **Architecture**: ETL from PostgreSQL → ClickHouse (preferred over direct replication)
   - **Triggers**:
     - Analytics queries taking >1 second on PostgreSQL
     - Dashboard queries causing high CPU on read replicas
     - Need for complex aggregations across millions of rows
   - **Cost**: ~$5-10K/month for ClickHouse cluster
   - **Alternative**: Continue using PostgreSQL read replicas + materialized views (simpler but less performant)

---

## References

- SCALE_ARCHITECTURE_DIAGRAM.md (detailed diagrams)
- ARCHITECTURE_DECISIONS.md (current single-node decisions)
- docker-compose.yml (current implementation)
