from sqlalchemy import Column, Integer, Boolean, TIMESTAMP, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.core.database import Base


class DomainProxy(Base):
    __tablename__ = "domain_proxies"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)

    # Foreign keys
    domain_id = Column(
        Integer,
        ForeignKey("domains.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to domain"
    )
    proxy_id = Column(
        Integer,
        ForeignKey("proxies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to proxy"
    )

    # Status
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        comment="Enable/disable this mapping"
    )

    # Configuration
    priority = Column(
        Integer,
        default=5,
        nullable=False,
        comment="Proxy priority for this domain (1=highest, 10=lowest)"
    )

    # Usage tracking
    last_used_at = Column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="Last time this proxy was used for THIS domain"
    )

    # Performance metrics (per domain)
    success_count = Column(
        Integer,
        default=0,
        nullable=False,
        comment="Successful requests for this domain"
    )
    failure_count = Column(
        Integer,
        default=0,
        nullable=False,
        comment="Failed requests for this domain"
    )
    avg_response_time_ms = Column(
        Integer,
        nullable=True,
        comment="Average response time for this domain (milliseconds)"
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
    domain = relationship("Domain", back_populates="domain_proxies")
    proxy = relationship("Proxy", back_populates="domain_proxies")

    # Table constraints
    __table_args__ = (
        # Unique constraint: one mapping per domain-proxy pair
        UniqueConstraint(
            'domain_id',
            'proxy_id',
            name='unique_domain_proxy'
        ),
        # Composite indexes for LRU selection
        Index('idx_domain_proxies_lru', 'domain_id', 'last_used_at'),
        Index('idx_domain_proxies_priority_lru', 'domain_id', 'priority', 'last_used_at'),
    )

    def __repr__(self):
        return (
            f"<DomainProxy(id={self.id}, "
            f"domain_id={self.domain_id}, "
            f"proxy_id={self.proxy_id}, "
            f"is_active={self.is_active}, "
            f"success_rate={self.success_rate:.2%})>"
        )

    @property
    def success_rate(self) -> float:
        """Calculate success rate for this domain-proxy mapping."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total

    @property
    def total_requests(self) -> int:
        """Total requests for this domain-proxy mapping."""
        return self.success_count + self.failure_count

    def record_success(self, response_time_ms: int):
        """
        Record a successful request for this domain-proxy mapping.

        Args:
            response_time_ms: Response time in milliseconds
        """
        self.success_count += 1
        self.failure_count = 0  # Reset consecutive failures
        self.last_used_at = func.now()

        # Update average response time (moving average)
        if self.avg_response_time_ms is None:
            self.avg_response_time_ms = response_time_ms
        else:
            self.avg_response_time_ms = (
                (self.avg_response_time_ms + response_time_ms) // 2
            )

    def record_failure(self):
        """
        Record a failed request for this domain-proxy mapping.
        Auto-disable after 5 consecutive failures.
        """
        self.failure_count += 1
        self.last_used_at = func.now()

        # Auto-disable after 5 consecutive failures
        if self.failure_count >= 5:
            self.is_active = False
