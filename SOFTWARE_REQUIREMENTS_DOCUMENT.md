# Software Requirements Document

## 1. Functional Requirements

| ID | Requirement | Details | Priority |
|----|-------------|---------|----------|
| **FR-1** | **Crawl Job Lifecycle Management** | Admin can submit single/batch URLs (up to 10K), set priority (1-10), schedule for future execution, configure recrawl frequency (hourly to monthly), pause/resume/cancel/restart tasks. System automatically schedules recurring crawls based on configured frequency. | High |
| **FR-2** | **Task Monitoring & Administration** | Admin can view task details (status, timestamps, errors, proxy used), list/filter tasks (by domain, status, date range, priority), view task statistics (success rate, avg response time), and bulk manage failed tasks. | High |
| **FR-3** | **Web Content Crawling** | System downloads HTML content and images from submitted URLs, saves to storage (local for MVP, S3 for production), uses proxy rotation, respects robots.txt directives, retries failures (3x with exponential backoff), tracks HTTP status/response times, and prevents duplicate URL crawls via SHA256 hashing. | High |
| **FR-4** | **Content Parsing & Extraction** | System extracts product information (name, price, description, rating, images with metadata) using site-specific parsers (Amazon, eBay, Etsy, etc.), detects content changes via hashing, stores structured data in PostgreSQL, indexes descriptions in Elasticsearch for full-text search, and handles parsing failures with retry logic. | High |
| **FR-5** | **Domain Configuration Management** | Admin can add/update domains, configure domain-specific settings (crawl delay, max concurrent requests, assigned parser), enable/disable crawling per domain, view domain statistics (total tasks, success rate, active proxies). System caches and uses robots.txt per domain with manual refresh capability. | High |
| **FR-6** | **Proxy Pool Management** | Admin can add/configure proxies (URL, port, protocol, credentials), enable/disable proxies, assign proxies to domains (many-to-many), view health metrics (success rate, response time, failure count). System automatically disables proxies after 5-10 consecutive failures, uses LRU rotation for selection, tracks usage per domain, and re-enables after successful requests. | High |
| **FR-7** | **Product Search & Discovery** | Users can search products via full-text query (Elasticsearch), filter by attributes (price range, availability, brand, category, rating), sort results (by price, rating, date), paginate through results, view detailed product information including images, and retrieve products by ID. | High |
| **FR-8** | **Analytics & Historical Queries** | Users can query historical product data, analyze price trends over time, compare products across time periods, and perform aggregations on product attributes. System uses ClickHouse for efficient analytics queries at scale. | Medium |
| **FR-9** | **System Health Monitoring** | Admin can view overall system health (database, RabbitMQ, Elasticsearch, ClickHouse), monitor queue status (message counts, consumer counts), view aggregate statistics (total tasks, products, success rates), and access performance metrics (avg crawl/parse time). | High |
| **FR-10** | **Data Integrity & Change Detection** | System prevents duplicate products via URL hashing (SHA256), updates existing products when content changes (detected via content hashing), maintains historical record of all crawl attempts, stores flexible metadata in JSON format, and supports database schema versioning via Alembic migrations. | High |
| **FR-11** | **Error Tracking & Logging** | System logs all errors with stack traces and context, tracks task lifecycle with detailed timestamps (submitted, queued, started, completed/failed), records HTTP status codes and response times, and maintains proxy failure counts. | High |
| **FR-12** | **Compliance & Rate Limiting** | System respects robots.txt crawl-delay directives per domain, uses configurable user-agent strings, implements configurable crawl delays, prevents aggressive crawling via proxy rotation and scheduling, and maintains audit trail for admin actions. | High |

---

## 2. Non-Functional Requirements

| ID | Requirement | Details | Priority |
|----|-------------|---------|----------|
| **NFR-1** | **Global Crawling Capacity** | **System must crawl 4 billion pages/month globally** (1,543 pages/sec, 1B pages/month per region across 4 regions). Worker capacity: 10-50 URLs/sec per crawler worker, 10-50 products/sec per parser worker. Message throughput: 150K msg/sec. At scale: 100 workers per region (50 crawler + 50 parser) with auto-scaling (5-100 workers). | **Critical** |
| **NFR-2** | **Global Query Capacity** | **System must handle 100 billion queries/month globally** (38M queries/sec, 9.7M qps per region across 4 regions). Query distribution: Elasticsearch (35% search queries, 85K qps with 97% caching), ClickHouse (45% analytics queries, 10M+ qps capacity), PostgreSQL (15% operational queries, 500K qps capacity with 90% Redis cache hit rate). API response time: <100ms p95 for simple queries, <3s for complex searches. | **Critical** |
| **NFR-3** | **High Availability & Fault Tolerance** | Service uptime: 99.9%. Component HA: PostgreSQL primary + 2-10 read replicas, RabbitMQ 3-node cluster with queue mirroring, Elasticsearch 3 master + 17 data nodes, ClickHouse 10-15 node cluster. Tolerates single node failures without service disruption. Graceful shutdown with no data loss. Message durability via durable queues (no message loss). Multi-region failover capability at scale. | High |
| **NFR-4** | **Security & Compliance** | Input validation for all API endpoints. SQL injection prevention via parameterized queries. XSS prevention in parsed content. Proxy credentials encrypted in database. Environment variables for sensitive config. API authentication (Phase 2: API keys, Phase 3: JWT). Robots.txt compliance with configurable user-agent and crawl delays per domain. Data residency compliance (GDPR) via regional deployment. Audit trail for admin actions. DDoS protection via CloudFlare at scale. | High |
| **NFR-5** | **Observability & Monitoring** | Health check endpoints for all services. Prometheus metrics collection. Grafana dashboards for visualization. Structured JSON logging with error context. Critical alerts: queue depth monitoring, proxy health monitoring, database connection pool monitoring. API request/response logging. Performance metrics tracking (avg crawl time, avg parse time, success rates). | High |
| **NFR-6** | **Maintainability & Code Quality** | Clean modular architecture with clear separation of concerns (core, API, workers, services, parsers). Database schema versioning via Alembic migrations. Comprehensive error logging with stack traces and context. Code follows PEP 8 style guidelines with type hints. Automated testing (unit, integration). API documentation via OpenAPI/Swagger. | High |
| **NFR-7** | **Technology Stack** | Python 3.13+ as primary language. Docker Compose for MVP deployment, Kubernetes for production/scale. PostgreSQL for ACID compliance and operational queries. Elasticsearch for full-text search. ClickHouse for analytics and historical queries at scale. RabbitMQ for reliable message queuing. Redis for operational query caching. S3/MinIO for distributed storage (production). | High |

---

## 3. References

- [Overall Architecture (Big scale)](SCALE_ARCHITECTURE_DECISIONS.md)
- [Single Region Architecture](ARCHITECTURE_DECISIONS.md)
- [Core Tables Design](CORE_TABLES_DESIGN.md)
- [Core API Design](CORE_API_DESIGN.md)
- [Proxy-Domain Strategy](PROXY_DOMAIN_STRATEGY.md)
- [Architecture Diagram](ARCHITECTURE_DIAGRAM.md)
