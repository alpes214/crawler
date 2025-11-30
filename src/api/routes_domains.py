"""
Domain Management API Routes.

Endpoints for managing crawl domains and their configurations.
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from src.core.database import get_db
from src.core.models import Domain, CrawlTask, DomainProxy
from src.api.schemas.domain import (
    DomainCreate,
    DomainUpdate,
    DomainResponse,
    DomainDetailResponse
)
from src.api.schemas.response import ApiResponse, PaginatedResponse, PaginationInfo


router = APIRouter()


@router.post("", response_model=ApiResponse[DomainDetailResponse], status_code=201)
async def create_domain(
    domain_data: DomainCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new domain for crawling.

    Registers a new domain with parser configuration and crawl settings.

    **Returns:**
    - 201: Domain created successfully
    - 409: Domain name already exists
    """
    # Check for duplicate domain name
    existing_domain = db.query(Domain).filter(Domain.domain_name == domain_data.domain_name).first()
    if existing_domain:
        raise HTTPException(
            status_code=409,
            detail={
                "success": False,
                "error": {
                    "code": "DUPLICATE_DOMAIN",
                    "message": f"Domain '{domain_data.domain_name}' already exists",
                    "details": {"existing_domain_id": existing_domain.id}
                }
            }
        )

    # Create new domain
    new_domain = Domain(
        domain_name=domain_data.domain_name,
        base_url=str(domain_data.base_url),
        parser_name=domain_data.parser_name,
        crawl_delay_seconds=domain_data.crawl_delay_seconds,
        max_concurrent_requests=domain_data.max_concurrent_requests,
        default_crawl_frequency=domain_data.default_crawl_frequency,
        is_active=True,
        user_agent=domain_data.user_agent,
        robots_txt_url=domain_data.robots_txt_url,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    db.add(new_domain)
    db.commit()
    db.refresh(new_domain)

    # Build response
    response_data = DomainDetailResponse(
        id=new_domain.id,
        domain_name=new_domain.domain_name,
        base_url=new_domain.base_url,
        parser_name=new_domain.parser_name,
        crawl_delay_seconds=new_domain.crawl_delay_seconds,
        max_concurrent_requests=new_domain.max_concurrent_requests,
        default_crawl_frequency=str(new_domain.default_crawl_frequency),
        is_active=new_domain.is_active,
        robots_txt_url=new_domain.robots_txt_url,
        robots_txt_content=new_domain.robots_txt_content,
        robots_txt_last_fetched=new_domain.robots_txt_last_fetched,
        user_agent=new_domain.user_agent,
        created_at=new_domain.created_at,
        updated_at=new_domain.updated_at
    )

    return ApiResponse(
        success=True,
        data=response_data,
        message="Domain created successfully"
    )


@router.get("/{domain_id}", response_model=ApiResponse[DomainDetailResponse])
async def get_domain_details(
    domain_id: int,
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific domain.

    **Returns:**
    - 200: Domain details retrieved successfully
    - 404: Domain not found
    """
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

    # Build detailed response
    response_data = DomainDetailResponse(
        id=domain.id,
        domain_name=domain.domain_name,
        base_url=domain.base_url,
        parser_name=domain.parser_name,
        crawl_delay_seconds=domain.crawl_delay_seconds,
        max_concurrent_requests=domain.max_concurrent_requests,
        default_crawl_frequency=str(domain.default_crawl_frequency),
        is_active=domain.is_active,
        robots_txt_url=domain.robots_txt_url,
        robots_txt_content=domain.robots_txt_content,
        robots_txt_last_fetched=domain.robots_txt_last_fetched,
        user_agent=domain.user_agent,
        created_at=domain.created_at,
        updated_at=domain.updated_at
    )

    return ApiResponse(
        success=True,
        data=response_data
    )


@router.get("", response_model=PaginatedResponse[DomainResponse])
async def list_domains(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Results per page"),
    db: Session = Depends(get_db)
):
    """
    List all domains with optional filtering and pagination.

    **Returns:**
    - 200: Domains list with pagination metadata
    """
    # Build query with filters
    query = db.query(Domain)

    if is_active is not None:
        query = query.filter(Domain.is_active == is_active)

    # Get total count
    total_count = query.count()

    # Apply pagination
    offset = (page - 1) * per_page
    domains = query.offset(offset).limit(per_page).all()

    # Build response list with stats
    domain_responses = []
    for domain in domains:
        # Count total tasks for this domain
        total_tasks = db.query(func.count(CrawlTask.id))\
            .filter(CrawlTask.domain_id == domain.id)\
            .scalar() or 0

        # Count active proxies for this domain
        active_proxies = db.query(func.count(DomainProxy.id))\
            .filter(
                and_(
                    DomainProxy.domain_id == domain.id,
                    DomainProxy.is_active == True
                )
            ).scalar() or 0

        domain_responses.append(
            DomainResponse(
                id=domain.id,
                domain_name=domain.domain_name,
                parser_name=domain.parser_name,
                is_active=domain.is_active,
                total_tasks=total_tasks,
                active_proxies=active_proxies,
                created_at=domain.created_at
            )
        )

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
        data=domain_responses,
        pagination=pagination
    )
