"""
Domain model - Stores domain configurations and parser assignments.

Each domain represents a website to crawl with specific settings like
crawl delay, parser assignment, and robots.txt caching.
"""

from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, Text, Interval
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.core.database import Base


class Domain(Base):
    """
    Domain configuration and settings.

    Represents a website/domain to crawl with associated configuration:
    - Parser assignment (which parser to use)
    - Crawl delay and concurrency limits
    - Robots.txt caching
    - Active/inactive status

    Relationships:
        - One domain has many crawl_tasks
        - One domain has many products
        - One domain has many domain_proxies (proxy mappings)
    """

    __tablename__ = "domains"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)

    # Domain identification
    domain_name = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Domain name (e.g., 'amazon.com')"
    )
    base_url = Column(
        String(512),
        nullable=False,
        comment="Base URL (e.g., 'https://www.amazon.com')"
    )

    # Parser configuration
    parser_name = Column(
        String(100),
        nullable=False,
        index=True,
        comment="Parser to use (e.g., 'amazon', 'ebay')"
    )

    # Crawl settings
    crawl_delay_seconds = Column(
        Integer,
        default=1,
        nullable=False,
        comment="Minimum delay between requests (seconds)"
    )
    max_concurrent_requests = Column(
        Integer,
        default=5,
        nullable=False,
        comment="Maximum concurrent requests to this domain"
    )
    default_crawl_frequency = Column(
        Interval,
        server_default="1 day",
        nullable=False,
        comment="Default recrawl frequency (PostgreSQL INTERVAL)"
    )

    # Status
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        comment="Enable/disable crawling for this domain"
    )

    # Robots.txt caching
    robots_txt_url = Column(
        String(512),
        nullable=True,
        comment="robots.txt URL"
    )
    robots_txt_content = Column(
        Text,
        nullable=True,
        comment="Cached robots.txt content"
    )
    robots_txt_last_fetched = Column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="When robots.txt was last fetched"
    )

    # User agent
    user_agent = Column(
        String(255),
        default="ProductCrawler/1.0",
        nullable=False,
        comment="User agent string for this domain"
    )

    # Timestamps
    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Record creation time"
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Last update time"
    )

    # Relationships
    crawl_tasks = relationship(
        "CrawlTask",
        back_populates="domain",
        cascade="all, delete-orphan"
    )
    products = relationship(
        "Product",
        back_populates="domain",
        cascade="all, delete-orphan"
    )
    domain_proxies = relationship(
        "DomainProxy",
        back_populates="domain",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return (
            f"<Domain(id={self.id}, "
            f"domain_name='{self.domain_name}', "
            f"parser='{self.parser_name}', "
            f"is_active={self.is_active})>"
        )

    @property
    def robots_txt_age_hours(self) -> float:
        """Calculate how old the cached robots.txt is (in hours)."""
        if not self.robots_txt_last_fetched:
            return float('inf')
        from datetime import datetime
        age = datetime.now(self.robots_txt_last_fetched.tzinfo) - self.robots_txt_last_fetched
        return age.total_seconds() / 3600

    def needs_robots_refresh(self, max_age_hours: int = 24) -> bool:
        """
        Check if robots.txt needs to be refreshed.

        Args:
            max_age_hours: Maximum age before refresh (default: 24 hours)

        Returns:
            True if robots.txt should be refreshed
        """
        return self.robots_txt_age_hours > max_age_hours
