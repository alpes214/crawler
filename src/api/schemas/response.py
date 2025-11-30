"""
Common response schemas for API endpoints.

Provides standardized response formats for success, errors, and pagination.
"""

from typing import Generic, TypeVar, Optional, Any
from pydantic import BaseModel, Field


DataT = TypeVar('DataT')


class PaginationInfo(BaseModel):
    """Pagination metadata."""
    page: int = Field(..., ge=1, description="Current page number")
    per_page: int = Field(..., ge=1, le=100, description="Items per page")
    total: int = Field(..., ge=0, description="Total number of items")
    total_pages: int = Field(..., ge=0, description="Total number of pages")


class ErrorDetail(BaseModel):
    """Error detail structure."""
    code: str = Field(..., description="Error code (e.g., TASK_NOT_FOUND)")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[dict[str, Any]] = Field(None, description="Additional error context")


class ApiResponse(BaseModel, Generic[DataT]):
    """
    Standard API response wrapper.

    All API endpoints return this structure for consistency.
    """
    success: bool = Field(..., description="Whether the operation succeeded")
    data: Optional[DataT] = Field(None, description="Response data (null on error)")
    message: Optional[str] = Field(None, description="Optional success message")
    error: Optional[ErrorDetail] = Field(None, description="Error details (null on success)")


class PaginatedResponse(BaseModel, Generic[DataT]):
    """
    Paginated API response wrapper.

    Used for list endpoints with pagination support.
    """
    success: bool = Field(..., description="Whether the operation succeeded")
    data: list[DataT] = Field(..., description="List of items")
    pagination: PaginationInfo = Field(..., description="Pagination metadata")
    message: Optional[str] = Field(None, description="Optional message")
