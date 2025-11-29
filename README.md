# Product Crawler

A scalable web crawler system for extracting product information from e-commerce websites.

## Features

- **Distributed Crawling**: Async crawlers with proxy rotation
- **Intelligent Parsing**: Site-specific parsers for accurate data extraction
- **Task Management**: Celery-based distributed task queue with priority support
- **Full-Text Search**: Elasticsearch integration for product descriptions
- **Admin API**: REST API for managing crawl jobs and monitoring progress
- **Query API**: REST API for filtering and searching products

## Architecture

- **FastAPI**: Web framework for REST APIs
- **PostgreSQL**: Primary database for structured data
- **Elasticsearch**: Full-text search engine
- **RabbitMQ + Celery**: Distributed task queue
- **aiohttp**: Async HTTP client for crawling
- **Docker Compose**: Container orchestration

## Project Structure

```
crawler/
├── src/
│   ├── core/           # Configuration, database, Celery, models
│   ├── api/            # FastAPI endpoints and schemas
│   ├── workers/        # Celery tasks (crawler, parser, scheduler)
│   ├── services/       # Business logic services
│   └── utils/          # Helper utilities
├── parsers/            # Site-specific HTML parsers
├── tests/              # Test suite
├── alembic/            # Database migrations
└── storage/            # Local file storage
```

## Setup

### Prerequisites

- Docker & Docker Compose
- Python 3.13+

### Quick Start

1. **Clone the repository**
   ```bash
   cd ~/work/forager/crawler
   ```

2. **Create environment file**
   ```bash
   cp .env.example .env
   # Edit .env and set your passwords
   ```

3. **Start services**
   ```bash
   docker-compose up -d
   ```

   Note: The database 'crawler' is automatically created on first startup via the init script in `docker/init-db/`.

4. **Run database migrations**
   ```bash
   docker-compose exec fastapi alembic upgrade head
   ```

5. **Access services**
   - API: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - RabbitMQ Management: http://localhost:15672 (user: crawler)
   - Elasticsearch: http://localhost:9200

## Development

### Install dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
```

### Run tests

```bash
pytest
pytest -v                    # Verbose
pytest -k test_crawler      # Run specific tests
pytest --cov               # With coverage
```

### Code quality

```bash
black .                     # Format code
flake8 src/                # Lint
mypy src/                  # Type check
isort .                    # Sort imports
```

### Database migrations

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Usage

### Submit crawl job

```bash
curl -X POST http://localhost:8000/api/crawl/submit \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://example.com/product1", "https://example.com/product2"],
    "priority": 5
  }'
```

### Query products

```bash
# Filter by price
curl "http://localhost:8000/api/products?price_min=10&price_max=100"

# Full-text search
curl -X POST http://localhost:8000/api/products/search \
  -H "Content-Type: application/json" \
  -d '{"query": "wireless headphones"}'
```

### Monitor crawl status

```bash
curl http://localhost:8000/api/crawl/status
```

## Configuration

See `.env.example` for all configuration options.

Key settings:
- `DATABASE_URL`: PostgreSQL connection string
- `ELASTICSEARCH_URL`: Elasticsearch endpoint
- `RABBITMQ_URL`: RabbitMQ connection string
- `MAX_RETRIES`: Retry attempts for failed crawls
- `REQUEST_TIMEOUT`: HTTP request timeout in seconds

## Scaling

### Scale workers

```bash
# Scale crawler workers
docker-compose up -d --scale celery-crawler=10

# Scale parser workers
docker-compose up -d --scale celery-parser=10
```

### Monitor queues

Access RabbitMQ management UI at http://localhost:15672

## Documentation

- [Architecture Decisions](ARCHITECTURE_DECISIONS.md)
- [Architecture Diagram](ARCHITECTURE_DIAGRAM.md)
- [API Documentation](http://localhost:8000/docs) (when running)

## License

MIT
