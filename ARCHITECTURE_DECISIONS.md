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

---

## Database Schema

### Overview

PostgreSQL database schema for the crawler project. All tables use SQLAlchemy ORM models.

### Tables

#### 1. domains

Stores information about domains to be crawled.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Auto-increment ID |
| domain_name | VARCHAR(255) | UNIQUE, NOT NULL | Domain name (e.g., "amazon.com") |
| base_url | VARCHAR(512) | NOT NULL | Base URL (e.g., "https://www.amazon.com") |
| crawl_delay_seconds | INTEGER | DEFAULT 1 | Delay between requests (respect robots.txt) |
| max_concurrent_requests | INTEGER | DEFAULT 5 | Max concurrent requests to this domain |
| is_active | BOOLEAN | DEFAULT TRUE | Whether domain is active for crawling |
| created_at | TIMESTAMP | DEFAULT NOW() | Record creation time |
| updated_at | TIMESTAMP | DEFAULT NOW() | Last update time |

**Indexes**:
- `idx_domains_domain_name` on `domain_name`
- `idx_domains_is_active` on `is_active`

#### 2. crawl_tasks

Stores crawl job state and history.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Auto-increment ID |
| domain_id | INTEGER | FK → domains.id, NOT NULL | Reference to domain |
| url | TEXT | NOT NULL | Full URL to crawl |
| url_hash | VARCHAR(64) | UNIQUE, NOT NULL | SHA256 hash of URL (deduplication) |
| status | VARCHAR(50) | NOT NULL | Task status (see enum below) |
| priority | INTEGER | DEFAULT 5 | Priority (1=highest, 10=lowest) |
| scheduled_at | TIMESTAMP | NOT NULL | When to execute task |
| started_at | TIMESTAMP | NULL | When crawling started |
| completed_at | TIMESTAMP | NULL | When task completed |
| retry_count | INTEGER | DEFAULT 0 | Number of retry attempts |
| max_retries | INTEGER | DEFAULT 3 | Maximum retry attempts |
| error_message | TEXT | NULL | Error message if failed |
| crawl_frequency | INTERVAL | DEFAULT '1 day' | How often to re-crawl |
| next_crawl_at | TIMESTAMP | NULL | Next scheduled crawl time |
| html_path | VARCHAR(512) | NULL | Path to saved HTML file |
| created_at | TIMESTAMP | DEFAULT NOW() | Record creation time |
| updated_at | TIMESTAMP | DEFAULT NOW() | Last update time |

**Status Enum**:
- `pending` - Initial state when submitted
- `queued` - Sent to RabbitMQ
- `crawling` - Download in progress
- `downloaded` - HTML saved, ready for parsing
- `parsing` - Parsing in progress
- `completed` - Successfully completed
- `failed` - Failed after max retries

**Indexes**:
- `idx_crawl_tasks_status` on `status`
- `idx_crawl_tasks_scheduled_at` on `scheduled_at`
- `idx_crawl_tasks_domain_id` on `domain_id`
- `idx_crawl_tasks_url_hash` on `url_hash` (UNIQUE)
- `idx_crawl_tasks_next_crawl_at` on `next_crawl_at`

#### 3. products

Stores extracted product information.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Auto-increment ID |
| domain_id | INTEGER | FK → domains.id, NOT NULL | Source domain |
| crawl_task_id | INTEGER | FK → crawl_tasks.id, NULL | Original crawl task |
| url | TEXT | NOT NULL | Product page URL |
| url_hash | VARCHAR(64) | UNIQUE, NOT NULL | SHA256 hash of URL |
| product_name | VARCHAR(512) | NOT NULL | Product name/title |
| description | TEXT | NULL | Full product description |
| price | DECIMAL(10,2) | NULL | Current price |
| currency | VARCHAR(3) | DEFAULT 'USD' | Currency code (ISO 4217) |
| availability | VARCHAR(50) | NULL | Stock status (in_stock, out_of_stock, etc.) |
| rating | DECIMAL(3,2) | NULL | Product rating (0.00-5.00) |
| review_count | INTEGER | NULL | Number of reviews |
| brand | VARCHAR(255) | NULL | Brand name |
| category | VARCHAR(255) | NULL | Product category |
| sku | VARCHAR(100) | NULL | Stock keeping unit |
| content_hash | VARCHAR(64) | NULL | Hash of product data (detect changes) |
| metadata | JSON | NULL | Additional metadata (flexible storage) |
| created_at | TIMESTAMP | DEFAULT NOW() | First crawled |
| updated_at | TIMESTAMP | DEFAULT NOW() | Last updated |

**Indexes**:
- `idx_products_domain_id` on `domain_id`
- `idx_products_product_name` on `product_name`
- `idx_products_price` on `price`
- `idx_products_availability` on `availability`
- `idx_products_created_at` on `created_at`
- `idx_products_url_hash` on `url_hash` (UNIQUE)
- `idx_products_brand` on `brand`
- `idx_products_category` on `category`

#### 4. images

Stores product image information.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Auto-increment ID |
| product_id | INTEGER | FK → products.id, NOT NULL | Reference to product |
| image_url | TEXT | NOT NULL | Original image URL |
| image_path | VARCHAR(512) | NULL | Local storage path |
| alt_text | VARCHAR(512) | NULL | Image alt text/description |
| image_type | VARCHAR(50) | DEFAULT 'primary' | Type (primary, gallery, thumbnail) |
| position | INTEGER | DEFAULT 0 | Display order |
| width | INTEGER | NULL | Image width in pixels |
| height | INTEGER | NULL | Image height in pixels |
| file_size | INTEGER | NULL | File size in bytes |
| created_at | TIMESTAMP | DEFAULT NOW() | Record creation time |

**Indexes**:
- `idx_images_product_id` on `product_id`

#### 5. proxies

Stores proxy configuration for rotation.

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
| created_at | TIMESTAMP | DEFAULT NOW() | Record creation time |
| updated_at | TIMESTAMP | DEFAULT NOW() | Last update time |

**Indexes**:
- `idx_proxies_is_active` on `is_active`
- `idx_proxies_last_used_at` on `last_used_at`
- `idx_proxies_failure_count` on `failure_count`

### Relationships

```
domains (1) ──< (N) crawl_tasks
domains (1) ──< (N) products

crawl_tasks (1) ──< (0..1) products

products (1) ──< (N) images
```

### Constraints & Business Rules

1. **URL Deduplication**:
   - `url_hash` ensures unique URLs per table
   - Hash = SHA256(normalized_url)

2. **Crawl Scheduling**:
   - `next_crawl_at = completed_at + crawl_frequency`
   - Scheduler queries: `SELECT * FROM crawl_tasks WHERE scheduled_at <= NOW() AND status = 'pending'`

3. **Proxy Rotation**:
   - Select proxy: `WHERE is_active = TRUE ORDER BY last_used_at ASC LIMIT 1`
   - Disable after failures: `UPDATE proxies SET is_active = FALSE WHERE failure_count > 10`

4. **Product Updates**:
   - Check `content_hash` to detect changes
   - Update `updated_at` only if content changed

### Elasticsearch Schema

#### Index: products

Stores product descriptions for full-text search.

```json
{
  "mappings": {
    "properties": {
      "product_id": {"type": "integer"},
      "product_name": {"type": "text", "analyzer": "standard"},
      "description": {"type": "text", "analyzer": "standard"},
      "brand": {"type": "keyword"},
      "category": {"type": "keyword"},
      "domain_name": {"type": "keyword"},
      "created_at": {"type": "date"}
    }
  }
}
```

### Migration Strategy

#### Initial Setup

1. Create database: PostgreSQL auto-creates via `POSTGRES_DB` env var
2. Run Alembic migrations: `alembic upgrade head`
3. Create Elasticsearch index: Via `elasticsearch_service.py`

#### Schema Updates

1. Modify SQLAlchemy models in `src/core/models/`
2. Generate migration: `alembic revision --autogenerate -m "description"`
3. Review migration file in `alembic/versions/`
4. Apply migration: `alembic upgrade head`

#### Rollback

```bash
alembic downgrade -1  # Rollback one version
alembic downgrade <revision>  # Rollback to specific version
```

### Sample Queries

#### Admin: Submit crawl job
```sql
INSERT INTO crawl_tasks (domain_id, url, url_hash, status, priority, scheduled_at)
VALUES (1, 'https://example.com/product1', SHA256('...'), 'pending', 5, NOW());
```

#### Scheduler: Find pending tasks
```sql
SELECT * FROM crawl_tasks
WHERE status = 'pending'
  AND scheduled_at <= NOW()
ORDER BY priority ASC, scheduled_at ASC
LIMIT 100;
```

#### API: Query products by price
```sql
SELECT p.*, d.domain_name
FROM products p
JOIN domains d ON p.domain_id = d.id
WHERE p.price BETWEEN 10 AND 100
  AND p.availability = 'in_stock'
ORDER BY p.created_at DESC
LIMIT 20;
```

#### API: Full-text search (PostgreSQL alternative)
```sql
SELECT * FROM products
WHERE to_tsvector('english', product_name || ' ' || COALESCE(description, ''))
  @@ to_tsquery('english', 'wireless & headphones')
ORDER BY ts_rank(to_tsvector('english', product_name || ' ' || description),
                  to_tsquery('english', 'wireless & headphones')) DESC;
```
