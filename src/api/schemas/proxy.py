"""
Proxy request and response schemas.

Used for proxy pool management.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ProxyCreate(BaseModel):
    """Request schema for adding a new proxy."""

    proxy_url: str = Field(..., min_length=1, max_length=255, description="Proxy hostname or IP")
    proxy_port: int = Field(..., ge=1, le=65535, description="Proxy port")
    proxy_protocol: str = Field("http", pattern="^(http|https|socks5)$", description="Proxy protocol")
    proxy_username: Optional[str] = Field(None, max_length=100, description="Proxy username")
    proxy_password: Optional[str] = Field(None, max_length=255, description="Proxy password")
    country_code: Optional[str] = Field(None, min_length=2, max_length=2, description="ISO country code")
    city: Optional[str] = Field(None, max_length=100, description="City location")
    provider: Optional[str] = Field(None, max_length=100, description="Proxy provider name")
    monthly_cost: Optional[float] = Field(None, ge=0, description="Monthly cost in USD")
    max_requests_per_hour: Optional[int] = Field(None, ge=0, description="Rate limit")


class ProxyUpdate(BaseModel):
    """Request schema for updating proxy settings."""

    is_active: Optional[bool] = None
    monthly_cost: Optional[float] = Field(None, ge=0)
    max_requests_per_hour: Optional[int] = Field(None, ge=0)
    proxy_username: Optional[str] = Field(None, max_length=100)
    proxy_password: Optional[str] = Field(None, max_length=255)


class ProxyResponse(BaseModel):
    """Response schema for proxy (list view)."""

    id: int
    proxy_url: str
    proxy_port: int
    proxy_protocol: str
    country_code: Optional[str] = None
    is_active: bool
    success_count: int
    failure_count: int
    success_rate: float = 0.0
    avg_response_time_ms: Optional[int] = None
    last_used_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProxyDetailResponse(BaseModel):
    """Detailed response schema for single proxy."""

    id: int
    proxy_url: str
    proxy_port: int
    proxy_protocol: str
    proxy_username: Optional[str] = None
    country_code: Optional[str] = None
    city: Optional[str] = None
    provider: Optional[str] = None
    is_active: bool
    failure_count: int
    success_count: int
    last_used_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    avg_response_time_ms: Optional[int] = None
    monthly_cost: Optional[float] = None
    max_requests_per_hour: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DomainProxyAssign(BaseModel):
    """Request schema for assigning proxies to domain."""

    proxy_ids: list[int] = Field(..., min_length=1, description="List of proxy IDs to assign")
    priority: int = Field(5, ge=1, le=10, description="Priority for all proxies")


class DomainProxyResponse(BaseModel):
    """Response schema for domain-proxy mapping."""

    proxy_id: int
    proxy_url: str
    proxy_port: int
    country_code: Optional[str] = None
    is_active: bool
    priority: int
    success_count: int
    failure_count: int
    success_rate_percent: float
    avg_response_time_ms: Optional[int] = None
    last_used_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DomainProxyStatsResponse(BaseModel):
    """Response schema for domain-proxy statistics."""

    domain_id: int
    domain_name: str
    total_proxies: int
    active_proxies: int
    failing_proxies: int
    overall_success_rate: float
    avg_response_time_ms: Optional[int] = None
    total_requests: int
    total_success: int
    total_failures: int
    proxy_distribution: dict[str, int]
