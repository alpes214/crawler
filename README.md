# Product Crawler

A scalable web crawler system for extracting product information from e-commerce websites.

## Documentation

### Requirements & Features
- [Software Requirements Document](SOFTWARE_REQUIREMENTS_DOCUMENT.md) - Functional and non-functional requirements
- [ML Ranking Search Design](ML_RANKING_SEARCH_DESIGN.md) - Machine learning search ranking (future)

### Architecture & Design
- [Architecture Decisions (MVP)](ARCHITECTURE_DECISIONS.md) - Single region MVP architecture
- [Architecture Diagram (MVP)](ARCHITECTURE_DIAGRAM.md) - Visual system overview for MVP
- [Scale Architecture Decisions](SCALE_ARCHITECTURE_DECISIONS.md) - Multi-region scale architecture
- [Scale Architecture Diagram](SCALE_ARCHITECTURE_DIAGRAM.md) - Visual system overview at scale
- [Scale Load Estimations](SCALE_LOAD_ESTIMATIONS.md) - Capacity planning and calculations

### Database & API Design
- [Core Tables Design](CORE_TABLES_DESIGN.md) - Database schema and state machines
- [Core API Design](CORE_API_DESIGN.md) - Complete API endpoint specifications
- [Proxy Domain Strategy](PROXY_DOMAIN_STRATEGY.md) - Proxy rotation and domain mapping

### API Documentation
- [Swagger UI](http://localhost:8000/docs) - Interactive API testing (when running)
- [ReDoc](http://localhost:8000/redoc) - Alternative API documentation (when running)

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

### Debugging & Development Workflow

```bash
# View logs
docker-compose logs -f fastapi
docker-compose logs -f crawler-worker
docker-compose logs -f parser-worker

# Rebuild after code changes
docker-compose up -d --build

# Rebuild specific service
docker-compose up -d --build fastapi

# Run shell in container
docker-compose exec fastapi bash

# Check service status
docker-compose ps

# Restart service
docker-compose restart fastapi
```

## Configuration

See `.env.example` for all configuration options.

Key settings:
- `DATABASE_URL`: PostgreSQL connection string
- `ELASTICSEARCH_URL`: Elasticsearch endpoint
- `RABBITMQ_URL`: RabbitMQ connection string
- `MAX_RETRIES`: Retry attempts for failed crawls
- `REQUEST_TIMEOUT`: HTTP request timeout in seconds

## License

MIT
