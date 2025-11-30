"""
Domain-Proxy Management API Routes.

Endpoints for managing proxy-to-domain mappings and performance tracking.
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, func

from src.core.database import get_db
from src.core.models import Domain, Proxy, DomainProxy
from src.api.schemas.proxy import (
    DomainProxyAssign,
    DomainProxyResponse,
    DomainProxyStatsResponse
)
from src.api.schemas.response import ApiResponse


router = APIRouter()


def calculate_success_rate_percent(success_count: int, failure_count: int) -> float:
    """Calculate success rate percentage."""
    total = success_count + failure_count
    if total == 0:
        return 0.0
    return round((success_count / total) * 100, 2)


@router.post("", response_model=ApiResponse[dict], status_code=201)
async def assign_proxies_to_domain(
    domain_id: int,
    assignment_data: DomainProxyAssign,
    db: Session = Depends(get_db)
):
    """
    Assign one or more proxies to a domain.

    **Returns:**
    - 201: Proxies assigned successfully
    - 404: Domain or proxy not found
    - 409: Proxy already assigned to domain
    """
    # Verify domain exists
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "DOMAIN_NOT_FOUND",
                    "message": f"Domain with ID {domain_id} not found"
                }
            }
        )

    # Verify all proxies exist
    proxies = db.query(Proxy).filter(Proxy.id.in_(assignment_data.proxy_ids)).all()
    if len(proxies) != len(assignment_data.proxy_ids):
        found_ids = {p.id for p in proxies}
        missing_ids = set(assignment_data.proxy_ids) - found_ids
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "PROXY_NOT_FOUND",
                    "message": f"Proxies not found: {missing_ids}"
                }
            }
        )

    # Assign proxies
    assigned_count = 0
    for proxy_id in assignment_data.proxy_ids:
        # Check if already assigned
        existing = db.query(DomainProxy).filter(
            and_(
                DomainProxy.domain_id == domain_id,
                DomainProxy.proxy_id == proxy_id
            )
        ).first()

        if not existing:
            domain_proxy = DomainProxy(
                domain_id=domain_id,
                proxy_id=proxy_id,
                is_active=True,
                priority=assignment_data.priority,
                success_count=0,
                failure_count=0,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(domain_proxy)
            assigned_count += 1

    db.commit()

    # Get total proxies count
    total_proxies = db.query(func.count(DomainProxy.id))\
        .filter(DomainProxy.domain_id == domain_id)\
        .scalar() or 0

    return ApiResponse(
        success=True,
        data={
            "domain_id": domain_id,
            "domain_name": domain.domain_name,
            "proxies_assigned": assigned_count,
            "proxy_ids": assignment_data.proxy_ids,
            "total_proxies": total_proxies
        },
        message=f"{assigned_count} proxies assigned to domain successfully"
    )


@router.get("", response_model=ApiResponse[dict])
async def list_domain_proxies(
    domain_id: int,
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    sort_by: str = Query("success_rate", description="Sort field"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
    db: Session = Depends(get_db)
):
    """
    Get all proxies assigned to a domain with performance stats.

    **Returns:**
    - 200: Domain proxies list
    - 404: Domain not found
    """
    # Verify domain exists
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "DOMAIN_NOT_FOUND",
                    "message": f"Domain with ID {domain_id} not found"
                }
            }
        )

    # Build query
    query = db.query(DomainProxy)\
        .options(joinedload(DomainProxy.proxy))\
        .filter(DomainProxy.domain_id == domain_id)

    if is_active is not None:
        query = query.filter(DomainProxy.is_active == is_active)

    domain_proxies = query.all()

    # Build response
    proxies_list = []
    for dp in domain_proxies:
        proxies_list.append(
            DomainProxyResponse(
                proxy_id=dp.proxy.id,
                proxy_url=dp.proxy.proxy_url,
                proxy_port=dp.proxy.proxy_port,
                country_code=dp.proxy.country_code,
                is_active=dp.is_active,
                priority=dp.priority,
                success_count=dp.success_count,
                failure_count=dp.failure_count,
                success_rate_percent=calculate_success_rate_percent(dp.success_count, dp.failure_count),
                avg_response_time_ms=dp.avg_response_time_ms,
                last_used_at=dp.last_used_at
            )
        )

    # Sort
    if sort_by == "success_rate":
        proxies_list.sort(
            key=lambda x: x.success_rate_percent,
            reverse=(sort_order == "desc")
        )

    # Count active proxies
    active_proxies = sum(1 for p in proxies_list if p.is_active)

    return ApiResponse(
        success=True,
        data={
            "domain_id": domain_id,
            "domain_name": domain.domain_name,
            "total_proxies": len(proxies_list),
            "active_proxies": active_proxies,
            "proxies": proxies_list
        }
    )


@router.delete("/{proxy_id}", response_model=ApiResponse[dict])
async def remove_proxy_from_domain(
    domain_id: int,
    proxy_id: int,
    db: Session = Depends(get_db)
):
    """
    Remove proxy assignment from domain.

    **Returns:**
    - 200: Proxy removed successfully
    - 404: Mapping not found
    """
    domain_proxy = db.query(DomainProxy).filter(
        and_(
            DomainProxy.domain_id == domain_id,
            DomainProxy.proxy_id == proxy_id
        )
    ).first()

    if not domain_proxy:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "MAPPING_NOT_FOUND",
                    "message": f"Proxy {proxy_id} is not assigned to domain {domain_id}"
                }
            }
        )

    db.delete(domain_proxy)
    db.commit()

    # Get remaining proxies count
    remaining_proxies = db.query(func.count(DomainProxy.id))\
        .filter(DomainProxy.domain_id == domain_id)\
        .scalar() or 0

    return ApiResponse(
        success=True,
        data={
            "domain_id": domain_id,
            "proxy_id": proxy_id,
            "remaining_proxies": remaining_proxies
        },
        message="Proxy removed from domain successfully"
    )


@router.post("/{proxy_id}/enable", response_model=ApiResponse[dict])
async def enable_domain_proxy_mapping(
    domain_id: int,
    proxy_id: int,
    db: Session = Depends(get_db)
):
    """
    Enable specific proxy for specific domain and reset failure count.

    **Returns:**
    - 200: Mapping enabled successfully
    - 404: Mapping not found
    """
    domain_proxy = db.query(DomainProxy).filter(
        and_(
            DomainProxy.domain_id == domain_id,
            DomainProxy.proxy_id == proxy_id
        )
    ).first()

    if not domain_proxy:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "MAPPING_NOT_FOUND",
                    "message": f"Proxy {proxy_id} is not assigned to domain {domain_id}"
                }
            }
        )

    domain_proxy.is_active = True
    domain_proxy.failure_count = 0
    domain_proxy.updated_at = datetime.utcnow()

    db.commit()

    return ApiResponse(
        success=True,
        data={
            "domain_id": domain_id,
            "proxy_id": proxy_id,
            "is_active": True,
            "failure_count": 0
        },
        message="Domain-proxy mapping enabled successfully"
    )


@router.post("/{proxy_id}/disable", response_model=ApiResponse[dict])
async def disable_domain_proxy_mapping(
    domain_id: int,
    proxy_id: int,
    db: Session = Depends(get_db)
):
    """
    Disable specific proxy for specific domain (keeps mapping, just disables).

    **Returns:**
    - 200: Mapping disabled successfully
    - 404: Mapping not found
    """
    domain_proxy = db.query(DomainProxy).filter(
        and_(
            DomainProxy.domain_id == domain_id,
            DomainProxy.proxy_id == proxy_id
        )
    ).first()

    if not domain_proxy:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "MAPPING_NOT_FOUND",
                    "message": f"Proxy {proxy_id} is not assigned to domain {domain_id}"
                }
            }
        )

    domain_proxy.is_active = False
    domain_proxy.updated_at = datetime.utcnow()

    db.commit()

    return ApiResponse(
        success=True,
        data={
            "domain_id": domain_id,
            "proxy_id": proxy_id,
            "is_active": False
        },
        message="Domain-proxy mapping disabled successfully"
    )


@router.get("/stats", response_model=ApiResponse[DomainProxyStatsResponse])
async def get_domain_proxy_stats(
    domain_id: int,
    db: Session = Depends(get_db)
):
    """
    Get aggregate statistics for domain's proxy usage.

    **Returns:**
    - 200: Domain-proxy statistics
    - 404: Domain not found
    """
    # Verify domain exists
    domain = db.query(Domain).filter(Domain.id == domain_id).first()
    if not domain:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "DOMAIN_NOT_FOUND",
                    "message": f"Domain with ID {domain_id} not found"
                }
            }
        )

    # Get all domain proxies with proxy info
    domain_proxies = db.query(DomainProxy)\
        .options(joinedload(DomainProxy.proxy))\
        .filter(DomainProxy.domain_id == domain_id)\
        .all()

    # Calculate stats
    total_proxies = len(domain_proxies)
    active_proxies = sum(1 for dp in domain_proxies if dp.is_active)
    failing_proxies = sum(1 for dp in domain_proxies if dp.failure_count > 5)

    total_success = sum(dp.success_count for dp in domain_proxies)
    total_failures = sum(dp.failure_count for dp in domain_proxies)
    total_requests = total_success + total_failures

    overall_success_rate = calculate_success_rate_percent(total_success, total_failures)

    # Calculate average response time
    response_times = [dp.avg_response_time_ms for dp in domain_proxies if dp.avg_response_time_ms]
    avg_response_time_ms = int(sum(response_times) / len(response_times)) if response_times else None

    # Proxy distribution by country
    proxy_distribution = {}
    for dp in domain_proxies:
        if dp.proxy and dp.proxy.country_code:
            country = dp.proxy.country_code
            proxy_distribution[country] = proxy_distribution.get(country, 0) + 1

    # Build response
    stats = DomainProxyStatsResponse(
        domain_id=domain_id,
        domain_name=domain.domain_name,
        total_proxies=total_proxies,
        active_proxies=active_proxies,
        failing_proxies=failing_proxies,
        overall_success_rate=overall_success_rate,
        avg_response_time_ms=avg_response_time_ms,
        total_requests=total_requests,
        total_success=total_success,
        total_failures=total_failures,
        proxy_distribution=proxy_distribution
    )

    return ApiResponse(
        success=True,
        data=stats
    )
