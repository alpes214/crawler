# Architecture Decisions & Design Rationale

## Dual Queue System (PostgreSQL + RabbitMQ)

**Decision**: Keep both PostgreSQL crawl_tasks table AND RabbitMQ/Celery queue

**Rationale**:
- **Admin Control**: Ability to pause/stop/resume crawling jobs
- **Status Visibility**: Clear view of crawl job status and progress
- **Error Tracking**: Persistent error logs in crawl_tasks table
- **Batch Scheduling**: Schedule multiple URLs with different priorities
- **Priority Management**: Prioritize certain domains/products
- **Recrawl Management**: Control crawl frequency and repetition rates
- **Audit Trail**: Historical record of all crawl attempts

**Flow**:
```
Admin API → PostgreSQL (crawl_tasks) → Celery Scheduler → RabbitMQ → Workers → Update PostgreSQL
```

PostgreSQL serves as the source of truth for job state, while RabbitMQ handles task distribution.

---

## File Storage Strategy

### MVP (Stage 1)
- **Local file storage** for HTML/images
- Simple implementation for proof of concept
- Acceptable for single-worker development setup

### Production (Stage 2+)
- **S3/MinIO** for distributed storage
- Required when scaling to multiple workers
- Implement cleanup policies and retention rules

---

## Data Storage: PostgreSQL + Elasticsearch + ClickHouse

### PostgreSQL (Primary Database)
**Decision**: Store all operational data in PostgreSQL

**Rationale**:
- **PostgreSQL**: Optimal for structured product queries (filtering by price, rating, availability)
- ACID compliance for transactional operations
- Source of truth for crawl tasks, products, domains, proxies

### Elasticsearch (Search Engine)
**Decision**: Store product descriptions in Elasticsearch for full-text search

**Rationale**:
- **Elasticsearch**: Superior full-text search performance, especially at scale
- Handles 3.4M search qps with 97% caching at scale
- **Trade-off**: Accept data duplication for MVP simplicity

### ClickHouse (Analytics Database)
**Decision**: Add ClickHouse for analytics queries and ML feature storage

**Rationale**:
- **Stage 2+**: Precomputed ML features stored in ClickHouse for fast retrieval
- Columnar storage enables 30-50ms batch feature fetch for 1000 products
- Handles 4.4M analytics qps at 44% utilization
- ETL pipeline: PostgreSQL → ClickHouse (periodic sync)

---

## Performance & Scalability Strategy

### Stage 1: MVP (0-100K products)
- Basic PostgreSQL setup
- Standard indexes on foreign keys and product_name
- Monitor performance, no premature optimization

### Stage 2: Growth (100K-1M products)
- Add connection pooling (pgBouncer)
- Batch inserts (100-500 products)
- Optimize indexes based on query patterns
- **Redis cache for operational queries** (90% hit rate target)
- **ML-based search ranking** (LightGBM/XGBoost for result reranking)

### Stage 3: Scale + ML (100M+ products)
- Consider removing some indexes from products table
- ETL pipeline: PostgreSQL → ClickHouse (hourly sync)
- **Precompute ML features during parsing**, store in ClickHouse
- **ML Ranking Service** (K8s deployment, 10-50 pods, auto-scaling)
- Archive old/inactive products

---

## Error Handling Strategy

### Stage 1: MVP
- Store error messages in `crawl_tasks.error_message` field
- Retry logic: 3 attempts with exponential backoff
- Basic error tracking in main table

### Stage 2: Production
- **Separate error_logs table**:
  - `crawl_task_id`, `error_type`, `error_message`, `stack_trace`, `occurred_at`
  - Enables detailed error analysis and debugging
  - Track error patterns across tasks
- **Dead Letter Queue** for permanently failed tasks
- **Error categorization**: network errors, parse errors, validation errors
- possible use of ELK (Kibana)

---

## Data Quality & Validation

### Stage 2: Future Implementation

**Parsing Validation**:
- Schema versioning for parsers (`parser_version` field)
- Validation rules for extracted data (price format, required fields)
- Confidence scores for extracted attributes

**Site Structure Changes**:
- Parser version tracking per domain
- Alerts when parse success rate drops
- A/B testing new parsers before rollout

**Data Consistency**:
- Unique constraints on product URLs
- Foreign key integrity checks
- Periodic data quality audits

---

## Crawl Scheduling Logic

### Questions to Address (Stage 1):
1. **Recrawl frequency**: How often to re-crawl same URLs?
   - Default: Daily, weekly, monthly?
   - Per-domain configuration?

2. **Deduplication**: Prevent duplicate crawls
   - URL normalization strategy
   - `url_hash` unique constraint

3. **Priority queue**: How to prioritize?
   - High-priority products (popular items)
   - Recently failed crawls
   - Staleness (last_crawled_at)

4. **Recrawl triggers**:
   - Time-based (scheduled)
   - Event-based (price change detection)
   - Manual admin request

---

## Cost Optimization

### Stage 1: MVP Budget (<$500/month)
- Docker Compose on single VPS: $50-100/month
- Small PostgreSQL instance: $50-100/month
- Elasticsearch single node: $50-100/month
- Development proxies: $50-150/month
- **Total**: ~$200-450/month

### Stage 2: Optimization Strategies
- Use managed PostgreSQL with auto-scaling
- **Redis cache cluster** (20 nodes at scale, 90% hit rate for operational queries)
- **ClickHouse cluster** (10-15 nodes at scale for analytics)
- **ML Ranking Service** (auto-scaling K8s deployment)
- Spot/preemptible instances for Celery workers
- Proxy cost monitoring and rotation optimization

---

## Implementation Phases

### Phase 1: MVP (Current)
- ✅ Dual queue system (PostgreSQL + RabbitMQ)
- ✅ Local file storage
- ✅ PostgreSQL + Elasticsearch
- ✅ Basic indexes
- ❌ No rate limiting
- ❌ Basic error handling in crawl_tasks table
- ❌ No data validation

### Phase 2: Production Ready
- Rate limiting per domain/proxy
- Separate error_logs table
- S3/MinIO storage
- Connection pooling
- **Redis cache** for operational queries (product lookups, domain configs)
- **ClickHouse cluster** (10-15 nodes) with ETL pipeline
- **ML-based search ranking** (basic LightGBM model)
- Monitoring (Prometheus/Grafana)
- Data validation and quality checks

### Phase 3: Scale
- **ML Ranking Service** (K8s deployment, feature precomputation)
- **Redis cluster** (20 nodes, 90% hit rate)
- Advanced caching strategies (CDN + Redis)
- Multi-region deployment (4 regions)
- A/B testing for ML models

---

## Project Structure

### Finalized Folder Structure

```
~/work/forager/crawler/
├── alembic/                    # Database migrations
│   ├── versions/
│   └── env.py
├── alembic.ini
├── src/
│   ├── core/                   # Core configuration + models
│   │   ├── __init__.py
│   │   ├── config.py           # Settings/environment variables
│   │   ├── database.py         # SQLAlchemy setup
│   │   ├── celery_app.py       # Celery configuration
│   │   └── models/             # SQLAlchemy models
│   │       ├── __init__.py
│   │       ├── domain.py
│   │       ├── crawl_task.py
│   │       ├── product.py
│   │       ├── image.py
│   │       └── proxy.py
│   ├── api/                    # FastAPI endpoints + schemas
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI app
│   │   ├── admin.py            # Admin endpoints
│   │   ├── products.py         # Product query endpoints
│   │   └── schemas/            # Pydantic schemas for API
│   │       ├── __init__.py
│   │       ├── crawl_job.py
│   │       ├── product.py
│   │       └── response.py
│   ├── workers/                # Celery workers (crawler + parser)
│   │   ├── __init__.py
│   │   ├── crawler.py          # Crawler worker tasks
│   │   ├── parser.py           # Parser worker tasks
│   │   └── scheduler.py        # Scheduler tasks
│   ├── services/               # Business logic services
│   │   ├── __init__.py
│   │   ├── proxy_service.py    # Proxy pool management
│   │   ├── storage_service.py  # Local file storage operations
│   │   └── elasticsearch_service.py  # Elasticsearch operations
│   └── utils/                  # Utilities
│       ├── __init__.py
│       ├── url_utils.py        # URL normalization, hashing
│       └── validators.py       # Data validation helpers
├── parsers/                    # Site-specific parsers
│   ├── __init__.py
│   ├── base.py                 # Base parser class
│   └── amazon.py               # Amazon-specific parser
├── tests/
│   ├── __init__.py
│   ├── test_api/
│   ├── test_workers/
│   ├── test_services/
│   └── test_utils/
├── storage/                    # Local file storage (gitignored)
│   └── .gitkeep
├── Dockerfile                  # Docker build file
├── docker-compose.yml          # Docker compose config
├── requirements.txt
├── requirements-dev.txt
├── .env
├── .env.example
├── .gitignore
├── pytest.ini
└── README.md
```

### Module Responsibilities

| Module | Responsibility |
|--------|----------------|
| `alembic/` | Database schema migrations (at project root) |
| `src/core/` | Configuration, database setup, Celery config, SQLAlchemy models |
| `src/core/models/` | SQLAlchemy ORM models (domain, crawl_task, product, image, proxy) |
| `src/api/` | FastAPI endpoints and application |
| `src/api/schemas/` | Pydantic schemas for request/response validation |
| `src/workers/` | Celery worker tasks (crawler, parser, scheduler) |
| `src/services/` | Business logic (proxy management, storage, Elasticsearch) |
| `src/utils/` | Helper functions (URL utils, validators) |
| `parsers/` | Site-specific HTML parsing logic |
| `tests/` | Unit and integration tests |
| `storage/` | Local file storage for HTML/images (gitignored) |

### Design Decisions

**1. Alembic at Project Root**
- Standard convention for Python projects
- Easier CLI usage: `alembic upgrade head`
- `alembic.ini` expects root-level configuration

**2. Models in `src/core/models/`**
- Models are core infrastructure, not business logic
- Centralized with database configuration
- Shared across all modules (API, workers, services)

**3. Schemas in `src/api/schemas/`**
- Co-located with API endpoints
- Pydantic schemas specific to API contracts
- Separate from SQLAlchemy models (separation of concerns)

**4. Workers in `src/workers/`**
- Dedicated module for Celery tasks
- Clear separation: crawler workers, parser workers, scheduler
- Independent from business logic in services

**5. Services Pattern**
- Encapsulates business logic (proxy pool, storage, search)
- Reusable across workers and API
- Easier to test and mock

**6. Utils Pattern**
- Shared utility functions
- No business logic, pure helpers
- URL normalization, validation, etc.

**7. Parsers as Separate Module**
- Site-specific parsing logic
- Easily extensible (add new parsers for new sites)
- Not tightly coupled to workers (can be used independently)

