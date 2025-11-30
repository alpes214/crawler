"""
Proxy model - Manages proxy pool configuration and health tracking.

Each proxy represents a connection endpoint used to distribute crawl requests
and avoid IP-based rate limiting.
"""

from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.core.database import Base


class Proxy(Base):
    """
    Proxy configuration and health tracking.

    Tracks proxy endpoints with:
    - Connection details (URL, port, protocol, credentials)
    - Health metrics (success/failure counts, response times)
    - Geographic information (country, city)
    - Cost tracking

    Relationships:
        - One proxy serves many domains (via domain_proxies junction table)
        - One proxy used in many crawl_tasks
    """

    __tablename__ = "proxies"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)

    # Proxy connection details
    proxy_url = Column(
        String(255),
        nullable=False,
        comment="Proxy host/IP address"
    )
    proxy_port = Column(
        Integer,
        nullable=False,
        comment="Proxy port number"
    )
    proxy_protocol = Column(
        String(20),
        default="http",
        nullable=False,
        comment="Protocol (http, https, socks5)"
    )

    # Authentication
    proxy_username = Column(
        String(100),
        nullable=True,
        comment="Authentication username"
    )
    proxy_password = Column(
        String(255),
        nullable=True,
        comment="Authentication password (should be encrypted)"
    )

    # Status
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        comment="Whether proxy is active"
    )

    # Health metrics
    failure_count = Column(
        Integer,
        default=0,
        nullable=False,
        index=True,
        comment="Consecutive failure count"
    )
    success_count = Column(
        Integer,
        default=0,
        nullable=False,
        comment="Total successful requests"
    )

    # Usage tracking
    last_used_at = Column(
        TIMESTAMP(timezone=True),
        nullable=True,
        index=True,
        comment="Last time proxy was used"
    )
    last_success_at = Column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="Last successful request"
    )
    last_failure_at = Column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="Last failed request"
    )

    # Performance metrics
    avg_response_time_ms = Column(
        Integer,
        nullable=True,
        comment="Average response time in milliseconds"
    )

    # Geographic information
    country_code = Column(
        String(2),
        nullable=True,
        index=True,
        comment="Proxy country code (ISO 3166-1 alpha-2)"
    )
    city = Column(
        String(100),
        nullable=True,
        comment="Proxy city"
    )

    # Administrative
    provider = Column(
        String(100),
        nullable=True,
        index=True,
        comment="Proxy provider name"
    )
    monthly_cost = Column(
        Numeric(10, 2),
        nullable=True,
        comment="Monthly cost for cost tracking"
    )
    max_requests_per_hour = Column(
        Integer,
        default=1000,
        nullable=False,
        comment="Rate limit for this proxy"
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
    domain_proxies = relationship(
        "DomainProxy",
        back_populates="proxy",
        cascade="all, delete-orphan"
    )
    crawl_tasks = relationship(
        "CrawlTask",
        back_populates="proxy"
    )

    def __repr__(self):
        return (
            f"<Proxy(id={self.id}, "
            f"url='{self.proxy_url}:{self.proxy_port}', "
            f"is_active={self.is_active}, "
            f"success_rate={self.success_rate:.2%})>"
        )

    @property
    def success_rate(self) -> float:
        """Calculate overall success rate."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total

    @property
    def total_requests(self) -> int:
        """Total requests made through this proxy."""
        return self.success_count + self.failure_count

    @property
    def connection_string(self) -> str:
        """
        Build proxy connection string.

        Returns:
            Proxy URL in format: protocol://username:password@host:port
            or protocol://host:port if no authentication
        """
        if self.proxy_username and self.proxy_password:
            return (
                f"{self.proxy_protocol}://"
                f"{self.proxy_username}:{self.proxy_password}@"
                f"{self.proxy_url}:{self.proxy_port}"
            )
        return f"{self.proxy_protocol}://{self.proxy_url}:{self.proxy_port}"

    def record_success(self, response_time_ms: int):
        """
        Record a successful request.

        Args:
            response_time_ms: Response time in milliseconds
        """
        self.success_count += 1
        self.failure_count = 0  # Reset consecutive failures
        self.last_used_at = func.now()
        self.last_success_at = func.now()

        # Update average response time (moving average)
        if self.avg_response_time_ms is None:
            self.avg_response_time_ms = response_time_ms
        else:
            self.avg_response_time_ms = (
                (self.avg_response_time_ms + response_time_ms) // 2
            )

        # Re-enable if was disabled
        self.is_active = True

    def record_failure(self):
        """
        Record a failed request.
        Auto-disable after 10 consecutive failures.
        """
        self.failure_count += 1
        self.last_used_at = func.now()
        self.last_failure_at = func.now()

        # Auto-disable after 10 consecutive failures
        if self.failure_count >= 10:
            self.is_active = False
