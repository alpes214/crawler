"""
Crawl task/job request and response schemas.

Used for task submission, retrieval, and filtering.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, HttpUrl, field_validator


class CrawlTaskCreate(BaseModel):
    """Request schema for creating a new crawl task."""

    domain_id: int = Field(..., ge=1, description="Domain ID from domains table")
    url: HttpUrl = Field(..., description="Full URL to crawl")
    priority: int = Field(5, ge=1, le=10, description="Priority: 1 (highest) to 10 (lowest)")
    scheduled_at: Optional[datetime] = Field(None, description="When to execute (default: NOW)")
    crawl_frequency: str = Field("1 day", description="Recrawl interval (PostgreSQL INTERVAL)")
    is_recurring: bool = Field(True, description="Auto-schedule next crawl")
    max_retries: int = Field(3, ge=0, le=10, description="Max retry attempts")

    @field_validator('crawl_frequency')
    @classmethod
    def validate_interval(cls, v: str) -> str:
        """Validate PostgreSQL interval format."""
        # Basic validation - could be more strict
        valid_units = ['second', 'minute', 'hour', 'day', 'week', 'month', 'year']
        parts = v.lower().split()
        if len(parts) != 2:
            raise ValueError(f"Invalid interval format: {v}. Expected format: '1 day'")
        try:
            int(parts[0])
        except ValueError:
            raise ValueError(f"Invalid interval number: {parts[0]}")
        if not any(unit in parts[1] for unit in valid_units):
            raise ValueError(f"Invalid interval unit: {parts[1]}")
        return v


class CrawlTaskResponse(BaseModel):
    """Response schema for crawl task (minimal for list view)."""

    id: int = Field(..., description="Task ID")
    domain_id: int = Field(..., description="Domain ID")
    domain_name: Optional[str] = Field(None, description="Domain name")
    url: str = Field(..., description="Target URL")
    url_hash: str = Field(..., description="SHA256 hash of URL")
    status: str = Field(..., description="Current task status")
    priority: int = Field(..., description="Priority (1-10)")
    scheduled_at: Optional[datetime] = Field(None, description="When task is scheduled")
    started_at: Optional[datetime] = Field(None, description="When crawling started")
    completed_at: Optional[datetime] = Field(None, description="When task completed")
    retry_count: int = Field(..., description="Number of retries so far")
    response_time_ms: Optional[int] = Field(None, description="Response time in milliseconds")
    created_at: datetime = Field(..., description="When task was created")

    class Config:
        from_attributes = True


class CrawlTaskDetailResponse(BaseModel):
    """Detailed response schema for single task retrieval."""

    id: int
    domain_id: int
    domain_name: Optional[str] = None
    url: str
    url_hash: str
    status: str
    priority: int
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int
    max_retries: int
    error_message: Optional[str] = None
    crawl_frequency: Optional[str] = None
    next_crawl_at: Optional[datetime] = None
    recrawl_count: int = 0
    is_recurring: bool
    html_path: Optional[str] = None
    http_status_code: Optional[int] = None
    response_time_ms: Optional[int] = None
    proxy_id: Optional[int] = None
    proxy_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


class CrawlTaskFilter(BaseModel):
    """Query parameters for filtering crawl tasks."""

    domain_id: Optional[int] = Field(None, ge=1, description="Filter by domain")
    status: Optional[str] = Field(None, description="Filter by status")
    priority_min: Optional[int] = Field(None, ge=1, le=10, description="Minimum priority")
    priority_max: Optional[int] = Field(None, ge=1, le=10, description="Maximum priority")
    created_after: Optional[datetime] = Field(None, description="Created after timestamp")
    created_before: Optional[datetime] = Field(None, description="Created before timestamp")
    is_recurring: Optional[bool] = Field(None, description="Filter recurring tasks")
    page: int = Field(1, ge=1, description="Page number")
    per_page: int = Field(20, ge=1, le=100, description="Results per page")
    sort_by: str = Field("created_at", description="Sort field")
    sort_order: str = Field("desc", pattern="^(asc|desc)$", description="Sort order")

    @field_validator('sort_by')
    @classmethod
    def validate_sort_field(cls, v: str) -> str:
        """Validate sort field."""
        allowed_fields = [
            'id', 'created_at', 'updated_at', 'scheduled_at',
            'completed_at', 'priority', 'status', 'retry_count'
        ]
        if v not in allowed_fields:
            raise ValueError(f"Invalid sort field: {v}. Allowed: {allowed_fields}")
        return v
