# Architecture Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Product Crawler System                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐                              ┌──────────────┐
│    Admin     │                              │     User     │
│   Client     │                              │    Client    │
└──────┬───────┘                              └──────┬───────┘
       │                                             │
       │ POST /api/crawl/submit                     │ GET /api/products
       │ GET /api/crawl/status                      │ POST /api/products/search
       │                                             │
       └────────────────────┬────────────────────────┘
                            │
                            ▼
                 ┌────────────────────┐
                 │                    │
                 │  FastAPI Server    │
                 │ (Admin + Query API)│
                 │                    │
                 └──────┬─────────────┘
                        │
         ┏━━━━━━━━━━━━━━┻━━━━━━━━━━━━━━┓
         ▼                              ▼
    Write (crawl_tasks)            Read (products)
         │                              │
         ▼                              ▼
┌─────────────────────┐        ┌─────────────────────┐
│                     │        │                     │
│    PostgreSQL       │        │   Elasticsearch     │
│  (Source of Truth)  │        │  (Full-Text Search) │
│                     │        │                     │
│  Tables:            │        │  Indexes:           │
│  - domains          │        │  - products         │
│  - crawl_tasks      │        │                     │
│  - products         │        └─────────────────────┘
│  - images           │                   ▲
│  - proxies          │                   │
│                     │                   │ Write (descriptions)
└──────┬──────────────┘                   │
       │                                  │
       │ Read pending tasks               │
       ▼                                  │
┌─────────────────────────────────────────┴───────────────────────────────────┐
│                                                                             │
│                         RabbitMQ + Celery                                   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Celery Beat Scheduler                                              │   │
│  │  - Reads crawl_tasks from PostgreSQL                                │   │
│  │  - Publishes tasks to queues based on priority                      │   │
│  └────────────────────────────┬────────────────────────────────────────┘   │
│                               │                                             │
│                               │ Publish                                     │
│              ┌────────────────┼────────────────┐                            │
│              │                │                │                            │
│              ▼                ▼                ▼                            │
│      ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                    │
│      │   crawl     │  │    parse    │  │  priority   │                    │
│      │   queue     │  │    queue    │  │   queue     │                    │
│      └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                    │
│             │                │                │                            │
│             │ Consume        │ Consume        │ Consume                    │
│             ▼                ▼                ▼                            │
│      ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                    │
│      │  Crawler    │  │   Parser    │  │  Priority   │                    │
│      │  Workers    │  │   Workers   │  │  Workers    │                    │
│      │  (5-20)     │  │   (5-20)    │  │   (2-5)     │                    │
│      └──────┬──────┘  └──────┬──────┘  └─────────────┘                    │
│             │                │                                             │
└─────────────┼────────────────┼─────────────────────────────────────────────┘
              │                │
              │ Save HTML      │ Read HTML
              ▼                │
       ┌──────────────┐        │
       │    Local     │        │
       │    File      │◄───────┘
       │   Storage    │
       │              │
       │ {task_id}/   │
       │  page.html   │
       │  images/     │
       └──────────────┘
```

---

## Component Descriptions

### 1. **FastAPI Server**
- **Role**: HTTP API gateway
- **Endpoints**:
  - Admin API: `/api/crawl/submit`, `/api/crawl/status`, `/api/crawl/pause`
  - Query API: `/api/products`, `/api/products/search`, `/api/products/{id}`
- **Operations**:
  - Write: Insert crawl_tasks to PostgreSQL
  - Read: Query products from PostgreSQL + Elasticsearch

### 2. **PostgreSQL**
- **Role**: Source of truth for all structured data
- **Tables**:
  - `domains` - Domain configurations
  - `crawl_tasks` - Crawl job state and history
  - `products` - Product structured data
  - `images` - Product images metadata
  - `proxies` - Proxy pool configuration
- **Operations**:
  - Admin writes crawl jobs
  - Scheduler reads pending tasks
  - Workers update task status
  - Query API reads product data

### 3. **Elasticsearch**
- **Role**: Full-text search engine
- **Indexes**:
  - `products` - Product descriptions and searchable text
- **Operations**:
  - Parser workers write descriptions
  - Query API reads for full-text search

### 4. **RabbitMQ**
- **Role**: Message broker for task distribution
- **Queues**:
  - `crawl_queue` - URLs to download
  - `parse_queue` - HTML files to parse
  - `priority_queue` - High-priority tasks
- **Operations**:
  - Scheduler publishes tasks
  - Workers consume tasks

### 5. **Celery Scheduler (Beat)**
- **Role**: Periodic task scheduler
- **Operations**:
  - Every N seconds: Query PostgreSQL for tasks where `scheduled_at <= NOW()`
  - Publish tasks to appropriate RabbitMQ queue based on priority
  - Update task status to "queued"

### 6. **RabbitMQ + Celery**
- **Role**: Task queue and distributed task execution
- **Components**:
  - **Celery Beat Scheduler**: Reads pending tasks from PostgreSQL and publishes to queues
  - **crawl_queue**: Tasks for downloading web pages
  - **parse_queue**: Tasks for parsing HTML
  - **priority_queue**: High-priority tasks
  - **Crawler Workers (5-20)**: Download HTML/images via aiohttp with proxies
  - **Parser Workers (5-20)**: Extract product data from HTML
  - **Priority Workers (2-5)**: Handle urgent tasks

### 7. **Crawler Workers**
- **Role**: Download web pages
- **Operations**:
  1. Consume task from `crawl_queue`
  2. Get proxy from PostgreSQL `proxies` table
  3. Download HTML + images via aiohttp
  4. Save to local file storage
  5. Update `crawl_tasks.status = 'downloaded'` in PostgreSQL
  6. Publish parse task to `parse_queue`
  7. Retry on failure (3x with exponential backoff)

### 8. **Parser Workers**
- **Role**: Extract product data from HTML
- **Operations**:
  1. Consume task from `parse_queue`
  2. Read HTML from local file storage
  3. Parse product attributes (name, price, images, description)
  4. Write structured data to PostgreSQL `products` table
  5. Write description to Elasticsearch
  6. Update `crawl_tasks.status = 'completed'`
  7. Retry on failure

### 9. **Local File Storage**
- **Role**: Temporary storage for HTML/images
- **Operations**:
  - Crawler writes: `{task_id}/page.html`, `{task_id}/images/*`
  - Parser reads: `{task_id}/page.html`
  - Cleanup: Delete after successful parse

---

## Data Flow Diagrams

### Flow 1: Admin Submits Crawl Job

```
┌──────┐   1. POST /api/crawl/submit        ┌─────────┐
│Admin │───────────────────────────────────►│ FastAPI │
└──────┘   {urls: [...], priority: 5}       └────┬────┘
                                                  │
                                                  │ 2. INSERT INTO crawl_tasks
                                                  ▼
                                            ┌──────────────┐
                                            │  PostgreSQL  │
                                            │              │
                                            │ crawl_tasks: │
                                            │ - url        │
                                            │ - status:    │
                                            │   'pending'  │
                                            │ - scheduled_ │
                                            │   at: NOW()  │
                                            └──────────────┘
```

### Flow 2: Scheduler Queues Tasks

```
┌──────────────────┐   1. SELECT * FROM crawl_tasks    ┌──────────────┐
│ Celery Scheduler │───────────────────────────────────►│  PostgreSQL  │
│     (Beat)       │◄───────────────────────────────────│              │
└────────┬─────────┘   WHERE status='pending'          └──────────────┘
         │              AND scheduled_at <= NOW()
         │
         │ 2. UPDATE status='queued'
         │
         ▼
┌──────────────┐
│  PostgreSQL  │
└──────────────┘
         │
         │ 3. PUBLISH crawl_task
         ▼
┌──────────────┐
│   RabbitMQ   │
│ crawl_queue  │
└──────────────┘
```

### Flow 3: Crawler Downloads Page

```
┌──────────────┐   1. CONSUME task         ┌───────────┐
│   RabbitMQ   │──────────────────────────►│  Crawler  │
│ crawl_queue  │                           │  Worker   │
└──────────────┘                           └─────┬─────┘
                                                 │
                                                 │ 2. SELECT proxy FROM proxies
                                                 ▼
                                           ┌──────────────┐
                                           │  PostgreSQL  │
                                           │ proxies table│
                                           └──────┬───────┘
                                                  │
                                                  │ 3. Download HTML via proxy
                                                  ▼
                                           ┌───────────┐
                                           │  Target   │
                                           │  Website  │
                                           └─────┬─────┘
                                                 │
                                                 │ 4. Save HTML
                                                 ▼
                                           ┌───────────┐
                                           │   Local   │
                                           │  Storage  │
                                           └─────┬─────┘
                                                 │
                                                 │ 5. UPDATE status='downloaded'
                                                 ▼
                                           ┌──────────────┐
                                           │  PostgreSQL  │
                                           │ crawl_tasks  │
                                           └──────────────┘
                                                 │
                                                 │ 6. PUBLISH parse_task
                                                 ▼
                                           ┌──────────────┐
                                           │   RabbitMQ   │
                                           │ parse_queue  │
                                           └──────────────┘
```

### Flow 4: Parser Extracts Product Data

```
┌──────────────┐   1. CONSUME task         ┌───────────┐
│   RabbitMQ   │──────────────────────────►│  Parser   │
│ parse_queue  │                           │  Worker   │
└──────────────┘                           └─────┬─────┘
                                                 │
                                                 │ 2. Read HTML
                                                 ▼
                                           ┌───────────┐
                                           │   Local   │
                                           │  Storage  │
                                           └─────┬─────┘
                                                 │
                                                 │ 3. Parse data
                                                 ▼
                                           ┌─────────────────┐
                                           │ Extract:        │
                                           │ - name          │
                                           │ - price         │
                                           │ - description   │
                                           │ - images        │
                                           └────────┬────────┘
                                                    │
                              ┌─────────────────────┴────────────────────┐
                              │                                          │
                              │ 4a. INSERT product                       │ 4b. INDEX description
                              ▼                                          ▼
                        ┌──────────────┐                         ┌──────────────┐
                        │  PostgreSQL  │                         │Elasticsearch │
                        │              │                         │              │
                        │ products:    │                         │ products:    │
                        │ - name       │                         │ - id         │
                        │ - price      │                         │ - description│
                        │ - url        │                         │              │
                        └──────────────┘                         └──────────────┘
                              │
                              │ 5. UPDATE status='completed'
                              ▼
                        ┌──────────────┐
                        │  PostgreSQL  │
                        │ crawl_tasks  │
                        └──────────────┘
```

### Flow 5: User Queries Products

```
┌──────┐   1. GET /api/products              ┌─────────┐
│ User │   ?price_min=10&price_max=100       │ FastAPI │
└──────┘───────────────────────────────────►└────┬────┘
                                                  │
                                                  │ 2. SELECT * FROM products
                                                  │    WHERE price BETWEEN 10 AND 100
                                                  ▼
                                            ┌──────────────┐
                                            │  PostgreSQL  │
                                            │              │
                                            │ JOIN images  │
                                            └──────┬───────┘
                                                   │
                                                   │ 3. Return results
                                                   ▼
                                            ┌─────────┐
                                            │ FastAPI │
                                            └────┬────┘
                                                 │
                                                 │ 4. JSON response
                                                 ▼
                                            ┌──────┐
                                            │ User │
                                            └──────┘
```

### Flow 6: User Searches Products (Full-Text)

```
┌──────┐   1. POST /api/products/search      ┌─────────┐
│ User │   {"query": "wireless headphones"}  │ FastAPI │
└──────┘───────────────────────────────────►└────┬────┘
                                                  │
                                                  │ 2. SEARCH description
                                                  │    MATCH "wireless headphones"
                                                  ▼
                                            ┌──────────────┐
                                            │Elasticsearch │
                                            │              │
                                            │ Return IDs   │
                                            └──────┬───────┘
                                                   │
                                                   │ 3. Product IDs: [101, 205, 308]
                                                   ▼
                                            ┌─────────┐
                                            │ FastAPI │
                                            └────┬────┘
                                                 │
                                                 │ 4. SELECT * FROM products
                                                 │    WHERE id IN (101, 205, 308)
                                                 ▼
                                            ┌──────────────┐
                                            │  PostgreSQL  │
                                            └──────┬───────┘
                                                   │
                                                   │ 5. Return full product data
                                                   ▼
                                            ┌─────────┐
                                            │ FastAPI │
                                            └────┬────┘
                                                 │
                                                 │ 6. JSON response
                                                 ▼
                                            ┌──────┐
                                            │ User │
                                            └──────┘
```

---

## Queue Strategy

### Queue Types

```
┌─────────────────┐
│  crawl_queue    │  Priority: Normal
│  (default)      │  Rate: 10-50 msg/sec
└─────────────────┘  Workers: 5-20

┌─────────────────┐
│  parse_queue    │  Priority: Normal
└─────────────────┘  Workers: 5-20

┌─────────────────┐
│ priority_queue  │  Priority: High
│  (urgent tasks) │  Workers: 2-5
└─────────────────┘  Preempts other queues
```

### Task Routing

```python
# Celery routing
task_routes = {
    'crawler.tasks.crawl_url': {
        'queue': 'crawl_queue',
        'routing_key': 'crawl.normal'
    },
    'crawler.tasks.crawl_url_priority': {
        'queue': 'priority_queue',
        'routing_key': 'crawl.high'
    },
    'crawler.tasks.parse_product': {
        'queue': 'parse_queue',
        'routing_key': 'parse.normal'
    }
}
```

---

## State Transitions

### Crawl Task Lifecycle

```
┌─────────┐
│ pending │  Initial state when admin submits
└────┬────┘
     │ Scheduler picks up
     ▼
┌─────────┐
│ queued  │  Sent to RabbitMQ
└────┬────┘
     │ Crawler worker starts
     ▼
┌────────────┐
│ crawling   │  Downloading in progress
└────┬───────┘
     │ Download complete
     ▼
┌─────────────┐
│ downloaded  │  HTML saved, sent to parse queue
└────┬────────┘
     │ Parser starts
     ▼
┌─────────┐
│ parsing │  Extracting data
└────┬────┘
     │ Parse complete
     ▼
┌───────────┐
│ completed │  Final state
└───────────┘

     │ If error occurs at any stage
     ▼
┌─────────┐
│ failed  │  Max retries exceeded
└─────────┘
```

---

## Monitoring Points

### Key Metrics

```
FastAPI:
- Request rate (req/sec)
- Response time (p50, p95, p99)
- Error rate (4xx, 5xx)

PostgreSQL:
- Connection pool usage
- Query latency
- Write throughput (inserts/sec)
- Table sizes

RabbitMQ:
- Queue depth (crawl, parse, priority)
- Message rate (in/out)
- Consumer count
- Unacked messages

Elasticsearch:
- Index size
- Search latency
- Indexing rate

Workers:
- Active workers count
- Task success/failure rate
- Retry count
- Average task duration

Proxies:
- Active proxy count
- Failure rate per proxy
- Request distribution
```

---

## Scalability Strategy

### Horizontal Scaling

```
Single Worker:              Multiple Workers:
┌──────────┐               ┌──────────┐  ┌──────────┐  ┌──────────┐
│ Crawler  │               │ Crawler  │  │ Crawler  │  │ Crawler  │
│ Worker 1 │               │ Worker 1 │  │ Worker 2 │  │ Worker N │
└────┬─────┘               └────┬─────┘  └────┬─────┘  └────┬─────┘
     │                          │             │             │
     ▼                          └─────────────┴─────────────┘
┌──────────┐                              ▼
│RabbitMQ  │                        ┌──────────┐
└──────────┘                        │RabbitMQ  │
                                    │(shared)  │
                                    └──────────┘
```

### Auto-scaling Triggers

```
Scale UP when:
- Queue depth > 1000 messages
- Worker CPU > 80%
- Average task wait time > 60 seconds

Scale DOWN when:
- Queue depth < 100 messages
- Worker CPU < 20%
- Average task wait time < 10 seconds
```

---

## Docker Compose Services

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    container_name: crawler_postgres
    environment:
      POSTGRES_DB: crawler
      POSTGRES_USER: crawler
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - crawler_network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U crawler"]
      interval: 10s
      timeout: 5s
      retries: 5

  elasticsearch:
    image: elasticsearch:8.11.0
    container_name: crawler_elasticsearch
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
    ports:
      - "9200:9200"
    volumes:
      - elasticsearch_data:/usr/share/elasticsearch/data
    networks:
      - crawler_network
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:9200/_cluster/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5

  rabbitmq:
    image: rabbitmq:3.12-management
    container_name: crawler_rabbitmq
    environment:
      RABBITMQ_DEFAULT_USER: crawler
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASSWORD}
    ports:
      - "5672:5672"   # AMQP port
      - "15672:15672" # Management UI
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    networks:
      - crawler_network
    healthcheck:
      test: ["CMD-SHELL", "rabbitmq-diagnostics -q ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  fastapi:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: crawler_api
    command: uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
    environment:
      DATABASE_URL: postgresql://crawler:${POSTGRES_PASSWORD}@postgres:5432/crawler
      ELASTICSEARCH_URL: http://elasticsearch:9200
      RABBITMQ_URL: amqp://crawler:${RABBITMQ_PASSWORD}@rabbitmq:5672/
    ports:
      - "8000:8000"
    volumes:
      - .:/app
      - storage_data:/app/storage
    networks:
      - crawler_network
    depends_on:
      postgres:
        condition: service_healthy
      elasticsearch:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy

  celery-scheduler:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: crawler_celery_beat
    command: celery -A src.core.celery_app beat --loglevel=info
    environment:
      DATABASE_URL: postgresql://crawler:${POSTGRES_PASSWORD}@postgres:5432/crawler
      RABBITMQ_URL: amqp://crawler:${RABBITMQ_PASSWORD}@rabbitmq:5672/
    volumes:
      - .:/app
    networks:
      - crawler_network
    depends_on:
      postgres:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy

  celery-crawler:
    build:
      context: .
      dockerfile: Dockerfile
    command: celery -A src.core.celery_app worker -Q crawl_queue,priority_queue --loglevel=info --concurrency=4
    environment:
      DATABASE_URL: postgresql://crawler:${POSTGRES_PASSWORD}@postgres:5432/crawler
      RABBITMQ_URL: amqp://crawler:${RABBITMQ_PASSWORD}@rabbitmq:5672/
    volumes:
      - .:/app
      - storage_data:/app/storage
    networks:
      - crawler_network
    depends_on:
      postgres:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    deploy:
      replicas: 5

  celery-parser:
    build:
      context: .
      dockerfile: Dockerfile
    command: celery -A src.core.celery_app worker -Q parse_queue --loglevel=info --concurrency=4
    environment:
      DATABASE_URL: postgresql://crawler:${POSTGRES_PASSWORD}@postgres:5432/crawler
      ELASTICSEARCH_URL: http://elasticsearch:9200
      RABBITMQ_URL: amqp://crawler:${RABBITMQ_PASSWORD}@rabbitmq:5672/
    volumes:
      - .:/app
      - storage_data:/app/storage
    networks:
      - crawler_network
    depends_on:
      postgres:
        condition: service_healthy
      elasticsearch:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    deploy:
      replicas: 5

networks:
  crawler_network:
    driver: bridge

volumes:
  postgres_data:
  elasticsearch_data:
  rabbitmq_data:
  storage_data:
```

### Network Configuration

All services are connected to the same `crawler_network` bridge network, which allows:

- **Service Discovery**: Services can communicate using container names (e.g., `postgres:5432`, `elasticsearch:9200`)
- **Internal DNS**: Docker provides automatic DNS resolution for service names
- **Isolation**: The network is isolated from other Docker networks
- **Shared Storage**: `storage_data` volume is mounted on API, crawler, and parser workers for local file storage

### Environment Variables

Create a `.env` file in the project root:

```env
POSTGRES_PASSWORD=your_secure_password
RABBITMQ_PASSWORD=your_secure_password
```

### Service Communication

```
fastapi → postgres:5432        (Database queries)
fastapi → elasticsearch:9200   (Search queries)
fastapi → rabbitmq:5672        (Task submission)

celery-scheduler → postgres:5432  (Read pending tasks)
celery-scheduler → rabbitmq:5672  (Publish tasks)

celery-crawler → rabbitmq:5672    (Consume crawl tasks)
celery-crawler → postgres:5432    (Update task status)

celery-parser → rabbitmq:5672     (Consume parse tasks)
celery-parser → postgres:5432     (Insert products)
celery-parser → elasticsearch:9200 (Index descriptions)
```

All communication happens within the `crawler_network` using internal DNS names.
