"""
Domain request and response schemas.

Used for domain configuration and management.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, HttpUrl


class DomainCreate(BaseModel):
    """Request schema for creating a new domain."""

    domain_name: str = Field(..., min_length=1, max_length=255, description="Domain name (e.g., amazon.com)")
    base_url: HttpUrl = Field(..., description="Base URL (e.g., https://www.amazon.com)")
    parser_name: str = Field(..., min_length=1, max_length=100, description="Parser identifier")
    crawl_delay_seconds: int = Field(1, ge=0, le=60, description="Delay between requests (seconds)")
    max_concurrent_requests: int = Field(5, ge=1, le=100, description="Max concurrent requests")
    default_crawl_frequency: str = Field("1 day", description="Default recrawl interval")
    user_agent: str = Field("ProductCrawler/1.0", max_length=255, description="User agent string")
    robots_txt_url: Optional[str] = Field(None, description="robots.txt URL (optional)")


class DomainUpdate(BaseModel):
    """Request schema for updating domain settings."""

    crawl_delay_seconds: Optional[int] = Field(None, ge=0, le=60)
    max_concurrent_requests: Optional[int] = Field(None, ge=1, le=100)
    default_crawl_frequency: Optional[str] = None
    is_active: Optional[bool] = None
    user_agent: Optional[str] = Field(None, max_length=255)


class DomainResponse(BaseModel):
    """Response schema for domain (list view)."""

    id: int
    domain_name: str
    parser_name: str
    is_active: bool
    total_tasks: int = 0
    active_proxies: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class DomainDetailResponse(BaseModel):
    """Detailed response schema for single domain."""

    id: int
    domain_name: str
    base_url: str
    parser_name: str
    crawl_delay_seconds: int
    max_concurrent_requests: int
    default_crawl_frequency: str
    is_active: bool
    robots_txt_url: Optional[str] = None
    robots_txt_content: Optional[str] = None
    robots_txt_last_fetched: Optional[datetime] = None
    user_agent: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
