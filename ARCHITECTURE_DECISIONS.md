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

## Data Storage: PostgreSQL + Elasticsearch

**Decision**: Store product data in PostgreSQL AND descriptions in Elasticsearch

**Rationale**:
- **PostgreSQL**: Optimal for structured product queries (filtering by price, rating, availability)
- **Elasticsearch**: Superior full-text search performance, especially at scale
- **Trade-off**: Accept data duplication for MVP simplicity
- **Future**: Re-evaluate when PostgreSQL FTS becomes bottleneck

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

### Stage 3: Scale (100M+ products)
- Consider removing some indexes from products table
- Implement ETL pipeline to columnar database (ClickHouse)
- Archive old/inactive products

### Index Strategy (Stage 1)
```sql
-- crawl_tasks table
CREATE INDEX idx_crawl_tasks_status ON crawl_tasks(status);
CREATE INDEX idx_crawl_tasks_scheduled_at ON crawl_tasks(scheduled_at);
CREATE INDEX idx_crawl_tasks_domain_id ON crawl_tasks(domain_id);
CREATE INDEX idx_crawl_tasks_url_hash ON crawl_tasks(url_hash);

-- products table
CREATE INDEX idx_products_domain_id ON products(domain_id);
CREATE INDEX idx_products_name ON products(product_name);
CREATE INDEX idx_products_price ON products(price);
CREATE INDEX idx_products_availability ON products(availability);
CREATE INDEX idx_products_created_at ON products(created_at);

-- images table
CREATE INDEX idx_images_product_id ON images(product_id);

-- proxies table
CREATE INDEX idx_proxies_is_active ON proxies(is_active);
CREATE INDEX idx_proxies_last_used_at ON proxies(last_used_at);
```

---

## Rate Limiting Strategy

### Stage 1: MVP
- **No rate limiting implementation**
- Use proxy rotation to distribute load
- Each proxy can make requests independently

### Stage 2: Production
- **Per-domain, per-proxy rate limiting**: 1-5 req/sec max
- Track request counts: `(domain_id, proxy_id) → request_count, window_start`
- Implement in-memory rate limiter (Redis or Python dict)
- Respect robots.txt crawl-delay directives

**Implementation approach**:
```python
# Stage 2: Rate limiter service
class RateLimiter:
    def can_crawl(self, domain_id: int, proxy_id: int) -> bool:
        key = f"{domain_id}:{proxy_id}"
        # Check request count in current time window
        # Return True if under limit
```

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

### Proposed Schema Additions:
```sql
ALTER TABLE crawl_tasks ADD COLUMN url_hash VARCHAR(64) UNIQUE;
ALTER TABLE crawl_tasks ADD COLUMN crawl_frequency INTERVAL DEFAULT '1 day';
ALTER TABLE crawl_tasks ADD COLUMN next_crawl_at TIMESTAMP;
ALTER TABLE crawl_tasks ADD COLUMN priority INTEGER DEFAULT 5;

ALTER TABLE domains ADD COLUMN crawl_delay_seconds INTEGER DEFAULT 1;
ALTER TABLE domains ADD COLUMN max_concurrent_requests INTEGER DEFAULT 5;
```

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
- Consider PostgreSQL FTS instead of Elasticsearch
- Spot/preemptible instances for Celery workers
- Implement caching (Redis) for frequent queries
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
- Monitoring (Prometheus/Grafana)
- Data validation and quality checks

### Phase 3: Scale
- ClickHouse for analytics
- Advanced caching strategies
- Multi-region deployment
- Machine learning for parse accuracy

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

### Import Patterns

```python
# Models (from core)
from src.core.models.product import Product
from src.core.models.crawl_task import CrawlTask
from src.core.models.proxy import Proxy

# Database setup
from src.core.database import get_db, SessionLocal
from src.core.config import settings

# API Schemas
from src.api.schemas.product import ProductResponse, ProductFilter
from src.api.schemas.crawl_job import CrawlJobCreate, CrawlJobStatus

# Workers
from src.workers.crawler import crawl_url_task
from src.workers.parser import parse_product_task
from src.workers.scheduler import schedule_pending_tasks

# Services
from src.services.proxy_service import ProxyService
from src.services.storage_service import StorageService
from src.services.elasticsearch_service import ElasticsearchService

# Utils
from src.utils.url_utils import normalize_url, hash_url
from src.utils.validators import validate_product_data

# Parsers
from parsers.amazon import AmazonParser
from parsers.base import BaseParser
```
