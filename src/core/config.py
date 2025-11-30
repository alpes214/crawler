"""
Configuration management using Pydantic Settings.

Loads configuration from environment variables with validation and type checking.
"""

from pydantic_settings import BaseSettings
from pydantic import Field, PostgresDsn
from typing import Optional


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Environment variables can be set in .env file or system environment.
    """

    # Database Configuration
    database_url: PostgresDsn = Field(
        default="postgresql://crawler:password@localhost:5432/crawler",
        description="PostgreSQL database URL"
    )

    # RabbitMQ Configuration
    rabbitmq_url: str = Field(
        default="amqp://crawler:password@localhost:5672/",
        description="RabbitMQ connection URL"
    )

    # Elasticsearch Configuration
    elasticsearch_url: str = Field(
        default="http://localhost:9200",
        description="Elasticsearch connection URL"
    )

    # Application Configuration
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )
    pythonpath: str = Field(
        default="/app",
        description="Python path for imports"
    )

    # Storage Configuration
    storage_path: str = Field(
        default="./storage",
        description="Path for local file storage (HTML/images)"
    )

    # Crawler Configuration
    max_retries: int = Field(
        default=3,
        description="Maximum retry attempts for failed requests"
    )
    retry_backoff_base: int = Field(
        default=2,
        description="Exponential backoff base for retries"
    )
    request_timeout: int = Field(
        default=30,
        description="HTTP request timeout in seconds"
    )
    user_agent: str = Field(
        default="Mozilla/5.0 (compatible; ProductCrawler/1.0)",
        description="User agent string for HTTP requests"
    )

    # Celery Configuration
    celery_broker_url: str = Field(
        default="amqp://crawler:password@localhost:5672/",
        description="Celery broker URL (RabbitMQ)"
    )
    celery_result_backend: Optional[str] = Field(
        default="redis://localhost:6379/0",
        description="Celery result backend (Redis)"
    )

    # API Configuration
    api_host: str = Field(
        default="0.0.0.0",
        description="FastAPI host binding"
    )
    api_port: int = Field(
        default=8000,
        description="FastAPI port"
    )

    # Proxy Configuration
    proxy_failure_threshold: int = Field(
        default=10,
        description="Consecutive failures before disabling proxy"
    )

    # Domain Configuration
    default_crawl_delay: int = Field(
        default=1,
        description="Default delay between requests (seconds)"
    )
    default_max_concurrent: int = Field(
        default=5,
        description="Default max concurrent requests per domain"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def get_database_url_sync(self) -> str:
        """Get database URL as string for SQLAlchemy."""
        if isinstance(self.database_url, str):
            return self.database_url
        return str(self.database_url)


# Global settings instance
settings = Settings()
