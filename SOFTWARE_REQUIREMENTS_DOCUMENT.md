# Software Requirements Document

## 1. Introduction

### 1.1 Purpose
This document specifies the functional and non-functional requirements for a scalable web crawler system designed to extract product information from e-commerce websites.

### 1.2 Scope
The system crawls product pages, extracts structured data, stores it in a searchable database, and provides REST APIs for managing crawl jobs and querying products. The architecture supports scaling from MVP (10K products) to global deployment (100M+ products across 4 regions).

### 1.3 Intended Audience
- Software developers implementing the system
- System architects designing infrastructure
- DevOps engineers deploying and maintaining the system
- Product managers planning features and capacity

---

## 2. Functional Requirements

### 2.1 Crawl Job Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1.1 | Admin can submit single URL for crawling via API | High |
| FR-1.2 | Admin can submit batch of URLs (up to 10,000) for crawling via API | High |
| FR-1.3 | Admin can set priority for crawl tasks (1=highest, 10=lowest) | Medium |
| FR-1.4 | Admin can schedule crawl tasks for future execution | Medium |
| FR-1.5 | Admin can configure recrawl frequency per task (hourly, daily, weekly, etc.) | High |
| FR-1.6 | System automatically schedules recurring crawls based on crawl_frequency | High |
| FR-1.7 | Admin can pause active crawl tasks | Medium |
| FR-1.8 | Admin can resume paused crawl tasks | Medium |
| FR-1.9 | Admin can cancel crawl tasks | Medium |
| FR-1.10 | Admin can restart failed tasks (full re-crawl or parsing-only) | High |
| FR-1.11 | Admin can bulk restart multiple failed tasks | Medium |
| FR-1.12 | Admin can view task details (status, timestamps, errors, proxy used) | High |
| FR-1.13 | Admin can list tasks with filtering (domain, status, date range, priority) | High |
| FR-1.14 | Admin can view task statistics (success rate, avg response time, etc.) | Medium |

### 2.2 Web Crawling

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.1 | System downloads HTML content from submitted URLs | High |
| FR-2.2 | System downloads product images from pages | Medium |
| FR-2.3 | System saves HTML and images to storage (local for MVP, S3 for production) | High |
| FR-2.4 | System uses proxy rotation to distribute load | High |
| FR-2.5 | System respects robots.txt crawl-delay directives | High |
| FR-2.6 | System retries failed downloads up to 3 times with exponential backoff | High |
| FR-2.7 | System tracks HTTP status codes and response times | Medium |
| FR-2.8 | System prevents duplicate URL crawls using URL hashing (SHA256) | High |

### 2.3 Content Parsing

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-3.1 | System extracts product information from HTML (name, price, description, rating, etc.) | High |
| FR-3.2 | System uses site-specific parsers (Amazon, eBay, Etsy, etc.) | High |
| FR-3.3 | System extracts product images with metadata (alt text, dimensions) | Medium |
| FR-3.4 | System detects content changes using content hashing | Medium |
| FR-3.5 | System stores structured product data in PostgreSQL | High |
| FR-3.6 | System indexes product descriptions in Elasticsearch for full-text search | High |
| FR-3.7 | System handles parsing failures with retry logic | High |

### 2.4 Domain Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-4.1 | Admin can add new domains to crawl | High |
| FR-4.2 | Admin can configure domain-specific settings (crawl delay, max concurrent requests) | High |
| FR-4.3 | Admin can assign parser to domain (amazon, ebay, etc.) | High |
| FR-4.4 | Admin can enable/disable crawling for specific domains | Medium |
| FR-4.5 | Admin can update domain settings | Medium |
| FR-4.6 | Admin can view domain statistics (total tasks, success rate, active proxies) | Medium |
| FR-4.7 | System caches and uses robots.txt per domain | High |
| FR-4.8 | Admin can manually refresh robots.txt for domain | Low |

### 2.5 Proxy Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-5.1 | Admin can add proxies to the pool | High |
| FR-5.2 | Admin can configure proxy settings (URL, port, protocol, credentials) | High |
| FR-5.3 | Admin can enable/disable individual proxies | Medium |
| FR-5.4 | Admin can assign specific proxies to specific domains (many-to-many) | High |
| FR-5.5 | Admin can view proxy health metrics (success rate, response time, failure count) | Medium |
| FR-5.6 | System automatically disables proxies after 5-10 consecutive failures | High |
| FR-5.7 | System tracks proxy usage per domain | High |
| FR-5.8 | System selects least recently used proxy for domain (LRU rotation) | High |
| FR-5.9 | System re-enables proxies after successful requests | Medium |
| FR-5.10 | Admin can manually re-enable disabled proxies | Low |

### 2.6 Product Query API

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-6.1 | Users can search products by full-text query (Elasticsearch) | High |
| FR-6.2 | Users can filter products by price range | High |
| FR-6.3 | Users can filter products by availability (in_stock, out_of_stock) | High |
| FR-6.4 | Users can filter products by brand | Medium |
| FR-6.5 | Users can filter products by category | Medium |
| FR-6.6 | Users can filter products by rating | Medium |
| FR-6.7 | Users can sort results by price, rating, date | Medium |
| FR-6.8 | Users can paginate through results | High |
| FR-6.9 | Users can view detailed product information including images | High |
| FR-6.10 | Users can retrieve product by ID | High |

### 2.7 Monitoring & System Status

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-7.1 | Admin can view overall system health (database, RabbitMQ, Elasticsearch) | High |
| FR-7.2 | Admin can view queue status (message counts, consumer counts) | High |
| FR-7.3 | Admin can view aggregate statistics (total tasks, products, success rates) | Medium |
| FR-7.4 | Admin can view performance metrics (avg crawl time, avg parse time) | Medium |
| FR-7.5 | System logs errors with stack traces | High |
| FR-7.6 | System tracks task lifecycle with timestamps (submitted, started, completed) | High |

### 2.8 Data Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-8.1 | System prevents duplicate products using URL hashing | High |
| FR-8.2 | System updates existing products when content changes | High |
| FR-8.3 | System maintains historical record of all crawl attempts | Medium |
| FR-8.4 | System stores metadata in JSON format for flexible attributes | Medium |
| FR-8.5 | System supports database migrations via Alembic | High |

---

## 3. Non-Functional Requirements

### 3.1 Performance

| ID | Requirement | Target | Priority |
|----|-------------|--------|----------|
| NFR-1.1 | System crawls URLs per second per worker | 10-50 URLs/sec | High |
| NFR-1.2 | System parses products per second per worker | 10-50 products/sec | High |
| NFR-1.3 | Product search query response time | < 3 seconds | High |
| NFR-1.4 | API response time (p95) for simple queries | < 100ms | High |
| NFR-1.5 | Database write capacity (at scale) | 50,000 inserts/sec | Medium |
| NFR-1.6 | Database read capacity (at scale) | 500,000 queries/sec | Medium |
| NFR-1.7 | Elasticsearch indexing rate (at scale) | 100,000 docs/sec | Medium |
| NFR-1.8 | Average HTTP response time | < 500ms | High |

### 3.2 Scalability

| ID | Requirement | Target | Priority |
|----|-------------|--------|----------|
| NFR-2.1 | Product capacity (MVP) | 10K to 1M products | High |
| NFR-2.2 | Product capacity (future) | 100M+ products | Low |
| NFR-2.3 | Celery worker scaling per region | 5 to 100+ workers | Medium |
| NFR-2.4 | Horizontal scaling support | Via Kubernetes | Medium |
| NFR-2.5 | Multi-region deployment support | 4 regions at scale | Low |
| NFR-2.6 | Pages per month per region (at scale) | 1 billion pages/month | Low |
| NFR-2.7 | Global query capacity (at scale) | 100 billion queries/month | Low |
| NFR-2.8 | RabbitMQ message throughput | 150,000 msg/sec | Medium |
| NFR-2.9 | API query capacity per region (at scale) | 10M queries/sec | Low |

### 3.3 Reliability

| ID | Requirement | Target | Priority |
|----|-------------|--------|----------|
| NFR-3.1 | Retry attempts for failed crawls | 3 retries with exponential backoff | High |
| NFR-3.2 | Automatic recovery from proxy failures | Immediate | High |
| NFR-3.3 | RabbitMQ node failure tolerance | Tolerates 1 node failure | High |
| NFR-3.4 | Elasticsearch node failure tolerance | Tolerates 1 node failure | High |
| NFR-3.5 | Data consistency across replicas | Eventual consistency | Medium |
| NFR-3.6 | Database replication lag | < 60 seconds | Medium |
| NFR-3.7 | API service uptime | 99.9% | High |
| NFR-3.8 | Message durability | No message loss (durable queues) | High |
| NFR-3.9 | Graceful shutdown support | No data loss on shutdown | High |

### 3.4 Availability

| ID | Requirement | Configuration | Priority |
|----|-------------|---------------|----------|
| NFR-4.1 | PostgreSQL high availability | Primary + 2-10 read replicas | High |
| NFR-4.2 | RabbitMQ high availability | 3-node cluster with queue mirroring | High |
| NFR-4.3 | Elasticsearch high availability | 3 master + 7-10 data nodes | Medium |
| NFR-4.4 | Cross-region replication | Async replication for disaster recovery | Low |
| NFR-4.5 | Multi-region failover (at scale) | Automatic failover | Low |
| NFR-4.6 | CDN cache hit rate (at scale) | 85-90% | Low |
| NFR-4.7 | Redis cache hit rate (at scale) | 85-90% | Low |

### 3.5 Maintainability

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-5.1 | Clean code with modular architecture | High |
| NFR-5.2 | Clear separation of concerns (core, API, workers, services, parsers) | High |
| NFR-5.3 | Database schema versioning with Alembic migrations | High |
| NFR-5.4 | Comprehensive error logging with context | High |
| NFR-5.5 | Code follows PEP 8 style guidelines | Medium |
| NFR-5.6 | Type hints for function parameters and returns | Medium |
| NFR-5.7 | Automated testing (unit, integration) | Medium |
| NFR-5.8 | API documentation via OpenAPI/Swagger | High |

### 3.6 Security

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-6.1 | API authentication via API keys (Phase 2) | Medium |
| NFR-6.2 | API authentication via JWT tokens (Phase 3) | Low |
| NFR-6.3 | Proxy credentials encrypted in database | High |
| NFR-6.4 | Environment variables for sensitive configuration | High |
| NFR-6.5 | Input validation for all API endpoints | High |
| NFR-6.6 | SQL injection prevention via parameterized queries | High |
| NFR-6.7 | XSS prevention in parsed content | High |
| NFR-6.8 | DDoS protection via CloudFlare (at scale) | Low |

### 3.7 Cost Efficiency

| ID | Requirement | Target | Priority |
|----|-------------|--------|----------|
| NFR-7.1 | MVP infrastructure cost | < $500/month | High |
| NFR-7.2 | Single region cost at 10% load | ~$33K/month | Medium |
| NFR-7.3 | Single region cost at 100% load | ~$144K/month | Medium |
| NFR-7.4 | Cost reduction via auto-scaling | ~40% vs fixed capacity | Medium |
| NFR-7.5 | 4-region global deployment cost (100% load) | ~$575K/month | Low |
| NFR-7.6 | Storage lifecycle policy | Delete HTML after 90 days | Medium |

### 3.8 Data Freshness

| ID | Requirement | Target | Priority |
|----|-------------|--------|----------|
| NFR-8.1 | Product recrawl frequency | Configurable: 1 hour to 1 month | High |
| NFR-8.2 | Proxy rotation frequency | Different proxy every hour | High |
| NFR-8.3 | robots.txt refresh frequency | Periodic refresh | Medium |
| NFR-8.4 | Content change detection | Via content hashing | Medium |

### 3.9 Observability

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-9.1 | Prometheus metrics for all services | Medium |
| NFR-9.2 | Grafana dashboards for visualization | Medium |
| NFR-9.3 | Structured logging in JSON format | Medium |
| NFR-9.4 | Health check endpoints for all services | High |
| NFR-9.5 | Queue depth monitoring with alerts | High |
| NFR-9.6 | Proxy health monitoring with alerts | High |
| NFR-9.7 | Database connection pool monitoring | Medium |
| NFR-9.8 | API request/response logging | High |

### 3.10 Compliance & Data Management

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-10.1 | Respect robots.txt directives | High |
| NFR-10.2 | Configurable user-agent per domain | High |
| NFR-10.3 | Configurable crawl delay per domain | High |
| NFR-10.4 | Data residency compliance (GDPR) via regional deployment | Low |
| NFR-10.5 | Audit trail for all admin actions (created_by field) | Medium |
| NFR-10.6 | Data retention policies (90-day HTML retention) | Medium |

### 3.11 Technology Constraints

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-11.1 | Python 3.13+ as primary language | High |
| NFR-11.2 | Docker Compose for MVP deployment | High |
| NFR-11.3 | Kubernetes for production/scale deployment | Medium |
| NFR-11.4 | PostgreSQL for ACID compliance | High |
| NFR-11.5 | Elasticsearch for full-text search capabilities | High |
| NFR-11.6 | RabbitMQ for reliable message queuing | High |

---

## 4. Glossary

| Term | Definition |
|------|------------|
| **Crawl Task** | A unit of work representing one URL to be downloaded and parsed |
| **Domain** | A website (e.g., amazon.com) with associated crawl settings and parser |
| **Parser** | Site-specific code to extract product data from HTML |
| **Proxy** | Intermediate server used to make HTTP requests to avoid IP blocking |
| **Proxy Rotation** | Technique of using different proxies for different requests |
| **LRU** | Least Recently Used - algorithm for proxy selection |
| **Recrawl** | Re-downloading and re-parsing a previously crawled URL |
| **URL Hash** | SHA256 hash of normalized URL for deduplication |
| **Content Hash** | Hash of product data to detect changes |
| **Priority Queue** | Queue for high-priority urgent tasks |
| **Scheduled Task** | Task with future execution time |
| **Recurring Task** | Task that automatically reschedules after completion |

---

## 5. References

- [Overall Architecture (Big scale)](SCALE_ARCHITECTURE_DECISIONS.md)
- [Single Region Architecture](ARCHITECTURE_DECISIONS.md)
- [Core Tables Design](CORE_TABLES_DESIGN.md)
- [Core API Design](CORE_API_DESIGN.md)
- [Proxy-Domain Strategy](PROXY_DOMAIN_STRATEGY.md)
- [Architecture Diagram](ARCHITECTURE_DIAGRAM.md)

---

## 8. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-29 | System | Initial requirements document |
