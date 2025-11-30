"""
Proxy Management API Routes.

Endpoints for managing proxy pool and health monitoring.
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from src.core.database import get_db
from src.core.models import Proxy, DomainProxy
from src.api.schemas.proxy import (
    ProxyCreate,
    ProxyUpdate,
    ProxyResponse,
    ProxyDetailResponse
)
from src.api.schemas.response import ApiResponse, PaginatedResponse, PaginationInfo


router = APIRouter()


def calculate_success_rate(success_count: int, failure_count: int) -> float:
    """Calculate success rate percentage."""
    total = success_count + failure_count
    if total == 0:
        return 0.0
    return round((success_count / total) * 100, 2)


@router.post("", response_model=ApiResponse[ProxyDetailResponse], status_code=201)
async def create_proxy(
    proxy_data: ProxyCreate,
    db: Session = Depends(get_db)
):
    """
    Add a new proxy to the pool.

    **Returns:**
    - 201: Proxy created successfully
    - 409: Proxy already exists
    """
    # Check for duplicate proxy
    existing_proxy = db.query(Proxy).filter(
        and_(
            Proxy.proxy_url == proxy_data.proxy_url,
            Proxy.proxy_port == proxy_data.proxy_port
        )
    ).first()

    if existing_proxy:
        raise HTTPException(
            status_code=409,
            detail={
                "success": False,
                "error": {
                    "code": "DUPLICATE_PROXY",
                    "message": f"Proxy {proxy_data.proxy_url}:{proxy_data.proxy_port} already exists",
                    "details": {"existing_proxy_id": existing_proxy.id}
                }
            }
        )

    # Create new proxy
    new_proxy = Proxy(
        proxy_url=proxy_data.proxy_url,
        proxy_port=proxy_data.proxy_port,
        proxy_protocol=proxy_data.proxy_protocol,
        proxy_username=proxy_data.proxy_username,
        proxy_password=proxy_data.proxy_password,
        country_code=proxy_data.country_code,
        city=proxy_data.city,
        provider=proxy_data.provider,
        is_active=True,
        failure_count=0,
        success_count=0,
        monthly_cost=proxy_data.monthly_cost,
        max_requests_per_hour=proxy_data.max_requests_per_hour,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    db.add(new_proxy)
    db.commit()
    db.refresh(new_proxy)

    # Build response
    response_data = ProxyDetailResponse(
        id=new_proxy.id,
        proxy_url=new_proxy.proxy_url,
        proxy_port=new_proxy.proxy_port,
        proxy_protocol=new_proxy.proxy_protocol,
        proxy_username=new_proxy.proxy_username,
        country_code=new_proxy.country_code,
        city=new_proxy.city,
        provider=new_proxy.provider,
        is_active=new_proxy.is_active,
        failure_count=new_proxy.failure_count,
        success_count=new_proxy.success_count,
        last_used_at=new_proxy.last_used_at,
        last_success_at=new_proxy.last_success_at,
        last_failure_at=new_proxy.last_failure_at,
        avg_response_time_ms=new_proxy.avg_response_time_ms,
        monthly_cost=new_proxy.monthly_cost,
        max_requests_per_hour=new_proxy.max_requests_per_hour,
        created_at=new_proxy.created_at,
        updated_at=new_proxy.updated_at
    )

    return ApiResponse(
        success=True,
        data=response_data,
        message="Proxy created successfully"
    )


@router.get("/{proxy_id}", response_model=ApiResponse[ProxyDetailResponse])
async def get_proxy_details(
    proxy_id: int,
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific proxy.

    **Returns:**
    - 200: Proxy details retrieved successfully
    - 404: Proxy not found
    """
    proxy = db.query(Proxy).filter(Proxy.id == proxy_id).first()

    if not proxy:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "PROXY_NOT_FOUND",
                    "message": f"Proxy with ID {proxy_id} not found"
                }
            }
        )

    # Build detailed response
    response_data = ProxyDetailResponse(
        id=proxy.id,
        proxy_url=proxy.proxy_url,
        proxy_port=proxy.proxy_port,
        proxy_protocol=proxy.proxy_protocol,
        proxy_username=proxy.proxy_username,
        country_code=proxy.country_code,
        city=proxy.city,
        provider=proxy.provider,
        is_active=proxy.is_active,
        failure_count=proxy.failure_count,
        success_count=proxy.success_count,
        last_used_at=proxy.last_used_at,
        last_success_at=proxy.last_success_at,
        last_failure_at=proxy.last_failure_at,
        avg_response_time_ms=proxy.avg_response_time_ms,
        monthly_cost=proxy.monthly_cost,
        max_requests_per_hour=proxy.max_requests_per_hour,
        created_at=proxy.created_at,
        updated_at=proxy.updated_at
    )

    return ApiResponse(
        success=True,
        data=response_data
    )


@router.get("", response_model=PaginatedResponse[ProxyResponse])
async def list_proxies(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    country_code: Optional[str] = Query(None, min_length=2, max_length=2, description="Filter by country"),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Results per page"),
    db: Session = Depends(get_db)
):
    """
    List all proxies with filtering and pagination.

    **Returns:**
    - 200: Proxies list with pagination metadata
    """
    # Build query with filters
    query = db.query(Proxy)

    filters = []
    if is_active is not None:
        filters.append(Proxy.is_active == is_active)
    if country_code is not None:
        filters.append(Proxy.country_code == country_code)
    if provider is not None:
        filters.append(Proxy.provider == provider)

    if filters:
        query = query.filter(and_(*filters))

    # Get total count
    total_count = query.count()

    # Apply pagination
    offset = (page - 1) * per_page
    proxies = query.offset(offset).limit(per_page).all()

    # Build response list
    proxy_responses = [
        ProxyResponse(
            id=proxy.id,
            proxy_url=proxy.proxy_url,
            proxy_port=proxy.proxy_port,
            proxy_protocol=proxy.proxy_protocol,
            country_code=proxy.country_code,
            is_active=proxy.is_active,
            success_count=proxy.success_count,
            failure_count=proxy.failure_count,
            success_rate=calculate_success_rate(proxy.success_count, proxy.failure_count),
            avg_response_time_ms=proxy.avg_response_time_ms,
            last_used_at=proxy.last_used_at
        )
        for proxy in proxies
    ]

    # Calculate pagination info
    total_pages = (total_count + per_page - 1) // per_page

    pagination = PaginationInfo(
        page=page,
        per_page=per_page,
        total=total_count,
        total_pages=total_pages
    )

    return PaginatedResponse(
        success=True,
        data=proxy_responses,
        pagination=pagination
    )


@router.patch("/{proxy_id}", response_model=ApiResponse[ProxyDetailResponse])
async def update_proxy(
    proxy_id: int,
    update_data: ProxyUpdate,
    db: Session = Depends(get_db)
):
    """
    Update proxy settings.

    **Returns:**
    - 200: Proxy updated successfully
    - 404: Proxy not found
    """
    proxy = db.query(Proxy).filter(Proxy.id == proxy_id).first()

    if not proxy:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "PROXY_NOT_FOUND",
                    "message": f"Proxy with ID {proxy_id} not found"
                }
            }
        )

    # Update fields
    if update_data.is_active is not None:
        proxy.is_active = update_data.is_active
    if update_data.monthly_cost is not None:
        proxy.monthly_cost = update_data.monthly_cost
    if update_data.max_requests_per_hour is not None:
        proxy.max_requests_per_hour = update_data.max_requests_per_hour
    if update_data.proxy_username is not None:
        proxy.proxy_username = update_data.proxy_username
    if update_data.proxy_password is not None:
        proxy.proxy_password = update_data.proxy_password

    proxy.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(proxy)

    # Build response
    response_data = ProxyDetailResponse(
        id=proxy.id,
        proxy_url=proxy.proxy_url,
        proxy_port=proxy.proxy_port,
        proxy_protocol=proxy.proxy_protocol,
        proxy_username=proxy.proxy_username,
        country_code=proxy.country_code,
        city=proxy.city,
        provider=proxy.provider,
        is_active=proxy.is_active,
        failure_count=proxy.failure_count,
        success_count=proxy.success_count,
        last_used_at=proxy.last_used_at,
        last_success_at=proxy.last_success_at,
        last_failure_at=proxy.last_failure_at,
        avg_response_time_ms=proxy.avg_response_time_ms,
        monthly_cost=proxy.monthly_cost,
        max_requests_per_hour=proxy.max_requests_per_hour,
        created_at=proxy.created_at,
        updated_at=proxy.updated_at
    )

    return ApiResponse(
        success=True,
        data=response_data,
        message="Proxy updated successfully"
    )


@router.post("/{proxy_id}/enable", response_model=ApiResponse[dict])
async def enable_proxy(
    proxy_id: int,
    db: Session = Depends(get_db)
):
    """
    Enable proxy and reset failure count.

    **Returns:**
    - 200: Proxy enabled successfully
    - 404: Proxy not found
    """
    proxy = db.query(Proxy).filter(Proxy.id == proxy_id).first()

    if not proxy:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "PROXY_NOT_FOUND",
                    "message": f"Proxy with ID {proxy_id} not found"
                }
            }
        )

    proxy.is_active = True
    proxy.failure_count = 0
    proxy.updated_at = datetime.utcnow()

    db.commit()

    return ApiResponse(
        success=True,
        data={
            "proxy_id": proxy.id,
            "is_active": proxy.is_active,
            "failure_count": proxy.failure_count
        },
        message="Proxy enabled successfully"
    )


@router.post("/{proxy_id}/disable", response_model=ApiResponse[dict])
async def disable_proxy(
    proxy_id: int,
    db: Session = Depends(get_db)
):
    """
    Disable proxy (stops using it for crawling).

    **Returns:**
    - 200: Proxy disabled successfully
    - 404: Proxy not found
    """
    proxy = db.query(Proxy).filter(Proxy.id == proxy_id).first()

    if not proxy:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "PROXY_NOT_FOUND",
                    "message": f"Proxy with ID {proxy_id} not found"
                }
            }
        )

    proxy.is_active = False
    proxy.updated_at = datetime.utcnow()

    db.commit()

    return ApiResponse(
        success=True,
        data={
            "proxy_id": proxy.id,
            "is_active": proxy.is_active
        },
        message="Proxy disabled successfully"
    )


@router.delete("/{proxy_id}", response_model=ApiResponse[None])
async def delete_proxy(
    proxy_id: int,
    db: Session = Depends(get_db)
):
    """
    Remove proxy from pool (cascade deletes domain_proxies mappings).

    **Returns:**
    - 200: Proxy deleted successfully
    - 404: Proxy not found
    """
    proxy = db.query(Proxy).filter(Proxy.id == proxy_id).first()

    if not proxy:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "PROXY_NOT_FOUND",
                    "message": f"Proxy with ID {proxy_id} not found"
                }
            }
        )

    db.delete(proxy)
    db.commit()

    return ApiResponse(
        success=True,
        data=None,
        message="Proxy deleted successfully"
    )
