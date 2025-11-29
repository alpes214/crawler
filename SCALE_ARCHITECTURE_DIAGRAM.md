# Scale Architecture Diagram

This document describes the architecture for **massive scale**: 4 billion pages/month (1B per region) across 4 geographic regions.

---

## Diagram 1: Global Multi-Region Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Global Traffic Distribution                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
            ┌───────────────┐               ┌───────────────┐
            │  Global CDN   │               │   GeoDNS      │
            │  (CloudFlare) │               │ (Route53/NS1) │
            │               │               │               │
            │ - Cache hot   │               │ - Route to    │
            │   queries     │               │   nearest     │
            │ - DDoS prot.  │               │   region      │
            │ - 85-90%      │               │ - Health      │
            │   cache hit   │               │   checks      │
            └───────┬───────┘               └───────┬───────┘
                    │                               │
        ┌───────────┴───────────┬───────────────────┴──────────┬─────────────┐
        │                       │                              │             │
        ▼                       ▼                              ▼             ▼
┌────────────────┐      ┌────────────────┐           ┌────────────────┐  ┌────────────────┐
│   US-EAST      │      │   EU-WEST      │           │  ASIA-SOUTH    │  │   US-WEST      │
│   Region 1     │      │   Region 2     │           │   Region 3     │  │   Region 4     │
│                │      │                │           │                │  │   (Failover)   │
│ Load: 1B/mo    │      │ Load: 1B/mo    │           │ Load: 1B/mo    │  │ Load: 1B/mo    │
│ 385 pages/sec  │      │ 385 pages/sec  │           │ 385 pages/sec  │  │ 385 pages/sec  │
│ 860 msg/sec    │      │ 860 msg/sec    │           │ 860 msg/sec    │  │ 860 msg/sec    │
│                │      │                │           │                │  │                │
│ [Full Stack]   │      │ [Full Stack]   │           │ [Full Stack]   │  │ [Full Stack]   │
│ See Diagram 2  │      │ See Diagram 2  │           │ See Diagram 2  │  │ See Diagram 2  │
└────────┬───────┘      └────────┬───────┘           └────────┬───────┘  └────────┬───────┘
         │                       │                            │                   │
         │                       │                            │                   │
         └───────────────────────┴────────────────────────────┴───────────────────┘
                        Cross-Region Data Replication (Async)

┌─────────────────────────────────────────────────────────────────────────────┐
│                      Cross-Region Replication Layer                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Elasticsearch Cross-Cluster Search:                                        │
│  ├─ Each region searches local cluster (fast)                               │
│  ├─ Async replication of product index updates                              │
│  └─ Eventual consistency across regions                                     │
│                                                                             │
│  S3 Cross-Region Replication:                                               │
│  ├─ HTML/Images replicated to 2 backup regions                              │
│  ├─ Lifecycle: Delete after 90 days                                         │
│  └─ Glacier archival for compliance                                         │
│                                                                             │
│  PostgreSQL Replication:                                                    │
│  ├─ Each region: Primary + 10 read replicas (local)                         │
│  ├─ Cross-region: Async replication to 1 standby per region                 │
│  └─ Failover: Promote standby to primary if region fails                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

Global Totals:
├─ Total Crawl Rate: 1,543 pages/second (4 regions × 385.8)
├─ Total Message Rate: 3,440 msg/second sustained
├─ Peak Message Rate: 10,320 msg/second (3x burst)
├─ Total Workers: 400 (100 per region)
├─ Total API Capacity: 40M queries/second (4 regions × 10M)
└─ Monthly Cost: ~$576,000 (4 regions × $144,000)
```

---

## Diagram 2: Single Region Architecture (1B pages/month)

Each region is independent and identical. This shows the detailed architecture for ONE region.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  SINGLE REGION: 1 Billion Pages/Month                        │
│                  Load: 385 pages/sec | 860 msg/sec sustained                 │
└─────────────────────────────────────────────────────────────────────────────┘

                            ┌──────────────────┐
                            │  Regional CDN    │
                            │  Edge Nodes      │
                            │  (Cache Layer 1) │
                            └────────┬─────────┘
                                     │
                            ┌────────▼─────────┐
                            │  Load Balancer   │
                            │   (ALB/NLB)      │
                            │  - Health checks │
                            │  - SSL term.     │
                            └────────┬─────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
                    ▼                ▼                ▼
            ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
            │  API Tier   │  │  API Tier   │  │  API Tier   │
            │  Pod Pool   │  │  Pod Pool   │  │  Pod Pool   │
            │             │  │             │  │             │
            │ K8s Deploy: │  │ K8s Deploy: │  │ K8s Deploy: │
            │ 100-1000    │  │ 100-1000    │  │ 100-1000    │
            │ replicas    │  │ replicas    │  │ replicas    │
            │             │  │             │  │             │
            │ Resources:  │  │ Resources:  │  │ Resources:  │
            │ - 2 CPU     │  │ - 2 CPU     │  │ - 2 CPU     │
            │ - 4Gi RAM   │  │ - 4Gi RAM   │  │ - 4Gi RAM   │
            └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
                   │                │                │
                   └────────────────┼────────────────┘
                                    │
                    ┌───────────────┴──────────────┐
                    │                              │
                    ▼                              ▼
        ┌───────────────────────┐      ┌──────────────────────┐
        │   Redis Cache Cluster │      │  PostgreSQL Cluster  │
        │                       │      │                      │
        │ Nodes: 20             │      │ Primary (Write):     │
        │ Memory/node: 64GB     │      │ - 32 CPU             │
        │ Total: 1.28TB         │      │ - 256GB RAM          │
        │                       │      │ - 10TB SSD           │
        │ Cache Strategy:       │      │                      │
        │ - Hot: 100% hit       │      │ Read Replicas: 10    │
        │ - Warm: 80% hit       │      │ - 16 CPU each        │
        │ - Cold: DB read       │      │ - 128GB RAM each     │
        │                       │      │                      │
        │ Expected: 85-90%      │      │ Connection Pool:     │
        │ cache hit rate        │      │ - pgBouncer × 5      │
        │                       │      │ - 10K max conn       │
        └───────────────────────┘      │                      │
                                       │ Capacity:            │
                                       │ - Write: 50K/sec     │
                                       │ - Read: 500K/sec     │
                                       └──────┬───────────────┘
                                              │
                                              │ Data sync
                                              ▼
                                    ┌──────────────────────┐
                                    │  Elasticsearch       │
                                    │  Cluster             │
                                    │                      │
                                    │ Topology:            │
                                    │ - Master nodes: 3    │
                                    │ - Data nodes: 7      │
                                    │                      │
                                    │ Per data node:       │
                                    │ - 16 CPU             │
                                    │ - 64GB RAM           │
                                    │ - 5TB SSD            │
                                    │                      │
                                    │ Total:               │
                                    │ - Storage: 35TB      │
                                    │ - Index: 100K doc/s  │
                                    │ - Search: 50K qry/s  │
                                    └──────────────────────┘
                                              ▲
                                              │
                                              │ Index products
                                              │
┌─────────────────────────────────────────────┴───────────────────────────────┐
│                                                                             │
│                    RabbitMQ 3-Node Cluster + Celery Workers                 │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────┐     │
│  │  RabbitMQ Cluster Configuration                                   │     │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │     │
│  │  │ RabbitMQ     │  │ RabbitMQ     │  │ RabbitMQ     │            │     │
│  │  │ Node 1       │  │ Node 2       │  │ Node 3       │            │     │
│  │  │              │  │              │  │              │            │     │
│  │  │ - 8 CPU      │  │ - 8 CPU      │  │ - 8 CPU      │            │     │
│  │  │ - 16GB RAM   │  │ - 16GB RAM   │  │ - 16GB RAM   │            │     │
│  │  │ - Mirrored   │  │ - Mirrored   │  │ - Mirrored   │            │     │
│  │  │   queues     │  │   queues     │  │   queues     │            │     │
│  │  └──────────────┘  └──────────────┘  └──────────────┘            │     │
│  │                                                                   │     │
│  │  Cluster Capacity:                                                │     │
│  │  - Throughput: 30,000-150,000 msg/sec                             │     │
│  │  - Your load: 860 msg/sec (0.6-2.9% utilization)                  │     │
│  │  - Peak load: 2,571 msg/sec (1.7-8.6% utilization)                │     │
│  │  - Burst load: 10,000 msg/sec (6.7-33% utilization)               │     │
│  └───────────────────────────────────────────────────────────────────┘     │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────┐     │
│  │  Celery Beat Scheduler                                            │     │
│  │  - Reads PostgreSQL crawl_tasks table                             │     │
│  │  - Finds tasks where scheduled_at <= NOW() AND status='pending'   │     │
│  │  - Publishes to appropriate queue based on priority               │     │
│  │  - Runs every 10 seconds                                          │     │
│  └─────────────────────────────┬─────────────────────────────────────┘     │
│                                │                                           │
│                                │ Publish tasks                             │
│               ┌────────────────┼────────────────┐                          │
│               │                │                │                          │
│               ▼                ▼                ▼                          │
│       ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│       │   crawl     │  │    parse    │  │  priority   │                  │
│       │   queue     │  │    queue    │  │   queue     │                  │
│       │             │  │             │  │             │                  │
│       │ ~430 msg/s  │  │ ~430 msg/s  │  │ ~0-50 msg/s │                  │
│       └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                  │
│              │                │                │                          │
│              │ Consume        │ Consume        │ Consume                  │
│              ▼                ▼                ▼                          │
│       ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│       │  Crawler    │  │   Parser    │  │  Priority   │                  │
│       │  Workers    │  │   Workers   │  │  Workers    │                  │
│       │             │  │             │  │             │                  │
│       │ K8s Deploy: │  │ K8s Deploy: │  │ K8s Deploy: │                  │
│       │ 50 replicas │  │ 50 replicas │  │ 10 replicas │                  │
│       │             │  │             │  │             │                  │
│       │ Resources:  │  │ Resources:  │  │ Resources:  │                  │
│       │ - 1 CPU     │  │ - 1 CPU     │  │ - 1 CPU     │                  │
│       │ - 2Gi RAM   │  │ - 2Gi RAM   │  │ - 2Gi RAM   │                  │
│       │             │  │             │  │             │                  │
│       │ Throughput: │  │ Throughput: │  │ Throughput: │                  │
│       │ 10 URLs/sec │  │ 10 prod/sec │  │ 20 URLs/sec │                  │
│       │ per worker  │  │ per worker  │  │ per worker  │                  │
│       │             │  │             │  │             │                  │
│       │ Total:      │  │ Total:      │  │ Total:      │                  │
│       │ 500 URLs/s  │  │ 500 prod/s  │  │ 200 URLs/s  │                  │
│       └──────┬──────┘  └──────┬──────┘  └─────────────┘                  │
│              │                │                                           │
└──────────────┼────────────────┼───────────────────────────────────────────┘
               │                │
               │ Save HTML      │ Read HTML
               ▼                │
        ┌──────────────┐        │
        │     S3       │        │
        │   Storage    │◄───────┘
        │   (Regional) │
        │              │
        │ Bucket:      │
        │ crawler-     │
        │ {region}-    │
        │ data         │
        │              │
        │ Lifecycle:   │
        │ - 90d→Glacier│
        │ - 365d→Delete│
        │              │
        │ Replication: │
        │ - To 2 other │
        │   regions    │
        └──────────────┘

Regional Metrics:
├─ Crawl Rate: 385.8 pages/second
├─ Message Rate: 860 msg/second sustained
├─ Peak Message Rate: 2,571 msg/second (3x)
├─ Burst Message Rate: 10,000 msg/second (batch uploads)
├─ Workers: 110 total (50 crawler + 50 parser + 10 priority)
├─ API Capacity: 10M queries/second (1,000 pods × 10K qps)
├─ Cache Hit Rate: 85-90%
├─ Database Write: 50K inserts/second capacity
├─ Database Read: 500K queries/second capacity
├─ Elasticsearch: 100K docs/second indexing, 50K queries/second
└─ Monthly Cost: ~$144,000 per region
```

---

## Component Details

### RabbitMQ Cluster Configuration

**3-Node Setup**:
TBD
---

## Worker Scaling Strategy

### Auto-Scaling Configuration

**Crawler Workers**:
TBD

---

## Data Flow (Single Region)

### 1. Admin Submits Batch Crawl Job
```
Admin → API (POST /api/crawl/submit)
      → PostgreSQL (INSERT 100K URLs into crawl_tasks)
      → Status: pending
```

### 2. Scheduler Picks Up Tasks
```
Celery Beat (every 10 seconds)
      → PostgreSQL (SELECT WHERE status='pending' AND scheduled_at <= NOW())
      → RabbitMQ (PUBLISH to crawl_queue)
      → PostgreSQL (UPDATE status='queued')
```

### 3. Crawler Processes Task
```
Crawler Worker
      → RabbitMQ (CONSUME from crawl_queue)
      → PostgreSQL (SELECT proxy FROM proxies WHERE is_active=true)
      → Target Website (GET via proxy)
      → S3 (UPLOAD HTML to crawler-{region}-data/{task_id}/)
      → PostgreSQL (UPDATE status='downloaded', html_path='s3://...')
      → RabbitMQ (PUBLISH to parse_queue)
```

### 4. Parser Processes Task
```
Parser Worker
      → RabbitMQ (CONSUME from parse_queue)
      → S3 (DOWNLOAD HTML from crawler-{region}-data/{task_id}/)
      → Parse (Extract: name, price, description, images)
      → PostgreSQL (INSERT INTO products)
      → Elasticsearch (INDEX description into products index)
      → PostgreSQL (UPDATE crawl_tasks SET status='completed')
```

### 5. User Queries Products
```
User → CDN (cache check)
     → [HIT] Return cached response
     → [MISS] → Load Balancer
              → API Pod
              → Redis (cache check)
              → [HIT] Return cached data
              → [MISS] → PostgreSQL (SELECT FROM products WHERE ...)
                       → Redis (SET cache)
                       → Return response
```

### 6. User Searches Products (Full-Text)
```
User → API (POST /api/products/search {"query": "wireless headphones"})
     → Elasticsearch (SEARCH products index)
     → [Returns product IDs]
     → PostgreSQL (SELECT FROM products WHERE id IN (...))
     → Return results
```

---

## Capacity Planning

### Current vs Max Capacity (Per Region)

| Component | Current Load | Max Capacity | Utilization | Headroom |
|-----------|--------------|--------------|-------------|----------|
| **RabbitMQ Cluster** | 860 msg/sec | 50,000 msg/sec | 1.7% | 58x |
| **Crawler Workers** | 385 URLs/sec | 500 URLs/sec | 77% | 1.3x |
| **Parser Workers** | 385 prod/sec | 500 prod/sec | 77% | 1.3x |
| **PostgreSQL Write** | ~400 ins/sec | 50,000 ins/sec | 0.8% | 125x |
| **PostgreSQL Read** | ~50K qry/sec | 500K qry/sec | 10% | 10x |
| **Elasticsearch** | ~400 doc/sec | 100K doc/sec | 0.4% | 250x |
| **API** | 10M qry/sec | 10M qry/sec | 100% | At capacity |

**Bottleneck**: API tier at full capacity for query load target.

**Scaling Recommendations**:
1. Workers at 77% → Add 10-20 more replicas for burst handling
2. API tier → Already sized for 10M qps target
3. All other components have massive headroom

---

## Cost Breakdown (Per Region)

| Component | Monthly Cost | Notes |
|-----------|-------------|-------|
| **API Pods (1,000 × 2 CPU)** | $72,000 | K8s managed nodes |
| **RabbitMQ Cluster (3 nodes)** | $3,600 | 8 CPU, 16GB RAM each |
| **Redis Cache (20 nodes)** | $8,000 | 64GB RAM per node |
| **PostgreSQL Cluster** | $15,000 | Primary + 10 replicas |
| **Elasticsearch (10 nodes)** | $20,000 | 16 CPU, 64GB, 5TB SSD |
| **Crawler Workers (50)** | $1,800 | 1 CPU, 2Gi RAM each |
| **Parser Workers (50)** | $1,800 | 1 CPU, 2Gi RAM each |
| **Priority Workers (10)** | $360 | 1 CPU, 2Gi RAM each |
| **S3 Storage (50TB)** | $1,150 | Regional storage |
| **Data Transfer** | $10,000 | Cross-region + egress |
| **Load Balancers** | $2,000 | ALB + NLB |
| **Monitoring** | $3,000 | Prometheus, Grafana, logs |
| **K8s Control Plane** | $5,000 | Managed Kubernetes |
| **Total per region** | **$143,710** | |

**4 Regions Total**: **$574,840/month**

Plus global services:
- CDN (CloudFlare): $10,000/month
- GeoDNS (Route53): $1,000/month

**Grand Total**: **$585,840/month**

---
