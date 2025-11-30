from enum import Enum
from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, Boolean, Interval, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.core.database import Base


class CrawlTaskStatus(str, Enum):
    """Crawl task status enumeration."""
    # Initial states
    PENDING = "pending"              # Waiting to be queued
    QUEUED = "queued"                # Sent to RabbitMQ crawl_queue

    # Crawling phase
    CRAWLING = "crawling"            # HTTP request in progress
    DOWNLOADED = "downloaded"        # HTML saved, ready for parsing

    # Parsing phase
    QUEUED_PARSE = "queued_parse"    # Sent to RabbitMQ parse_queue
    PARSING = "parsing"              # Extraction in progress

    # Terminal states
    COMPLETED = "completed"          # Successfully completed both phases
    FAILED = "failed"                # Failed after max retries

    # Admin control states
    PAUSED = "paused"                # Admin paused this task
    CANCELLED = "cancelled"          # Admin cancelled this task


class CrawlTask(Base):
    __tablename__ = "crawl_tasks"

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
        ForeignKey("proxies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Proxy used for this request"
    )

    # URL information
    url = Column(
        Text,
        nullable=False,
        comment="Full URL to crawl"
    )
    url_hash = Column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="SHA256 hash of URL (deduplication)"
    )

    # Status and priority
    status = Column(
        String(50),
        nullable=False,
        index=True,
        default=CrawlTaskStatus.PENDING.value,
        comment="Current task status"
    )
    priority = Column(
        Integer,
        default=5,
        nullable=False,
        index=True,
        comment="Priority (1=highest, 10=lowest)"
    )

    # Scheduling
    scheduled_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        index=True,
        comment="When to execute task"
    )
    started_at = Column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="When crawling started"
    )
    completed_at = Column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="When task completed/failed"
    )

    # Retry logic
    retry_count = Column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of retry attempts (current phase)"
    )
    max_retries = Column(
        Integer,
        default=3,
        nullable=False,
        comment="Max retries before marking failed"
    )
    error_message = Column(
        Text,
        nullable=True,
        comment="Last error message"
    )

    # Recurring crawl settings
    crawl_frequency = Column(
        Interval,
        server_default="1 day",
        nullable=False,
        comment="How often to re-crawl (PostgreSQL INTERVAL)"
    )
    next_crawl_at = Column(
        TIMESTAMP(timezone=True),
        nullable=True,
        index=True,
        comment="Next scheduled crawl time"
    )
    recrawl_count = Column(
        Integer,
        default=0,
        nullable=False,
        comment="Total number of times recrawled"
    )
    is_recurring = Column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        comment="Whether to schedule next crawl"
    )

    # Storage paths
    html_path = Column(
        String(512),
        nullable=True,
        comment="Path to saved HTML file (local or S3)"
    )

    # Performance metrics
    http_status_code = Column(
        Integer,
        nullable=True,
        comment="HTTP response code (200, 404, 500, etc.)"
    )
    response_time_ms = Column(
        Integer,
        nullable=True,
        comment="Response time in milliseconds"
    )

    # Metadata
    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="First creation time"
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Last update time"
    )
    created_by = Column(
        String(100),
        default="system",
        nullable=False,
        index=True,
        comment="Who created task (system/admin/api)"
    )

    # Relationships
    domain = relationship("Domain", back_populates="crawl_tasks")
    proxy = relationship("Proxy", back_populates="crawl_tasks")
    products = relationship(
        "Product",
        back_populates="crawl_task",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return (
            f"<CrawlTask(id={self.id}, "
            f"url='{self.url[:50]}...', "
            f"status='{self.status}', "
            f"priority={self.priority})>"
        )

    @property
    def is_terminal_state(self) -> bool:
        """Check if task is in a terminal state."""
        return self.status in [
            CrawlTaskStatus.COMPLETED.value,
            CrawlTaskStatus.FAILED.value,
            CrawlTaskStatus.CANCELLED.value
        ]

    @property
    def can_retry(self) -> bool:
        """Check if task can be retried."""
        return (
            self.status == CrawlTaskStatus.FAILED.value
            and self.retry_count < self.max_retries
        )

    @property
    def duration_seconds(self) -> float:
        """Calculate task duration in seconds."""
        if not self.started_at or not self.completed_at:
            return 0.0
        duration = self.completed_at - self.started_at
        return duration.total_seconds()

    def mark_started(self):
        """Mark task as started."""
        self.status = CrawlTaskStatus.CRAWLING.value
        self.started_at = func.now()

    def mark_downloaded(self, html_path: str, http_status: int, response_time: int):
        """
        Mark task as downloaded.

        Args:
            html_path: Path to saved HTML file
            http_status: HTTP status code
            response_time: Response time in milliseconds
        """
        self.status = CrawlTaskStatus.DOWNLOADED.value
        self.html_path = html_path
        self.http_status_code = http_status
        self.response_time_ms = response_time

    def mark_completed(self):
        """Mark task as completed."""
        self.status = CrawlTaskStatus.COMPLETED.value
        self.completed_at = func.now()
        self.error_message = None

        # Schedule next crawl if recurring
        if self.is_recurring:
            from datetime import datetime, timedelta
            self.next_crawl_at = datetime.now() + self.crawl_frequency

    def mark_failed(self, error: str):
        """
        Mark task as failed.

        Args:
            error: Error message
        """
        self.retry_count += 1
        self.error_message = error

        if self.retry_count >= self.max_retries:
            self.status = CrawlTaskStatus.FAILED.value
            self.completed_at = func.now()
        else:
            # Reset to pending for retry with exponential backoff
            self.status = CrawlTaskStatus.PENDING.value
            from datetime import datetime, timedelta
            delay_minutes = 2 ** self.retry_count
            self.scheduled_at = datetime.now() + timedelta(minutes=delay_minutes)
