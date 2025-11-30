"""
Crawl Task Management API Routes.

Endpoints for submitting, monitoring, and managing crawl tasks.
"""

import hashlib
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, desc, asc

from src.core.database import get_db
from src.core.models import CrawlTask, Domain, Proxy
from src.api.schemas.crawl_job import (
    CrawlTaskCreate,
    CrawlTaskResponse,
    CrawlTaskDetailResponse,
    CrawlTaskFilter
)
from src.api.schemas.response import ApiResponse, PaginatedResponse, PaginationInfo


router = APIRouter()


def compute_url_hash(url: str) -> str:
    """Compute SHA256 hash of URL for deduplication."""
    return hashlib.sha256(url.encode('utf-8')).hexdigest()


@router.post("", response_model=ApiResponse[CrawlTaskResponse], status_code=201)
async def create_crawl_task(
    task_data: CrawlTaskCreate,
    db: Session = Depends(get_db)
):
    """
    Submit a new URL for crawling.

    Creates a new crawl task with the specified parameters. The URL will be
    deduplicated using SHA256 hash to prevent duplicate crawls.

    **Returns:**
    - 201: Task created successfully
    - 400: Invalid parameters
    - 404: Domain not found
    - 409: URL already exists (duplicate)
    """
    # Verify domain exists
    domain = db.query(Domain).filter(Domain.id == task_data.domain_id).first()
    if not domain:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "DOMAIN_NOT_FOUND",
                    "message": f"Domain with ID {task_data.domain_id} not found"
                }
            }
        )

    # Check if domain is active
    if not domain.is_active:
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": {
                    "code": "DOMAIN_INACTIVE",
                    "message": f"Domain {domain.domain_name} is currently disabled"
                }
            }
        )

    # Compute URL hash for deduplication
    url_str = str(task_data.url)
    url_hash = compute_url_hash(url_str)

    # Check for duplicate URL
    existing_task = db.query(CrawlTask).filter(CrawlTask.url_hash == url_hash).first()
    if existing_task:
        raise HTTPException(
            status_code=409,
            detail={
                "success": False,
                "error": {
                    "code": "DUPLICATE_URL",
                    "message": f"URL already exists with task ID {existing_task.id}",
                    "details": {
                        "existing_task_id": existing_task.id,
                        "existing_status": existing_task.status
                    }
                }
            }
        )

    # Create new crawl task
    new_task = CrawlTask(
        domain_id=task_data.domain_id,
        url=url_str,
        url_hash=url_hash,
        priority=task_data.priority,
        scheduled_at=task_data.scheduled_at or datetime.utcnow(),
        crawl_frequency=task_data.crawl_frequency,
        is_recurring=task_data.is_recurring,
        max_retries=task_data.max_retries,
        status="pending",
        retry_count=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    # Build response
    response_data = CrawlTaskResponse(
        id=new_task.id,
        domain_id=new_task.domain_id,
        domain_name=domain.domain_name,
        url=new_task.url,
        url_hash=new_task.url_hash,
        status=new_task.status,
        priority=new_task.priority,
        scheduled_at=new_task.scheduled_at,
        started_at=new_task.started_at,
        completed_at=new_task.completed_at,
        retry_count=new_task.retry_count,
        response_time_ms=new_task.response_time_ms,
        created_at=new_task.created_at
    )

    return ApiResponse(
        success=True,
        data=response_data,
        message="Task created successfully"
    )


@router.get("/{task_id}", response_model=ApiResponse[CrawlTaskDetailResponse])
async def get_task_details(
    task_id: int,
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific crawl task.

    Retrieves complete task details including domain info, proxy info,
    timing information, and error messages if any.

    **Returns:**
    - 200: Task details retrieved successfully
    - 404: Task not found
    """
    # Query with joins to get domain and proxy info
    task = db.query(CrawlTask)\
        .options(joinedload(CrawlTask.domain))\
        .options(joinedload(CrawlTask.proxy))\
        .filter(CrawlTask.id == task_id)\
        .first()

    if not task:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "TASK_NOT_FOUND",
                    "message": f"Task with ID {task_id} not found"
                }
            }
        )

    # Build detailed response
    response_data = CrawlTaskDetailResponse(
        id=task.id,
        domain_id=task.domain_id,
        domain_name=task.domain.domain_name if task.domain else None,
        url=task.url,
        url_hash=task.url_hash,
        status=task.status,
        priority=task.priority,
        scheduled_at=task.scheduled_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        retry_count=task.retry_count,
        max_retries=task.max_retries,
        error_message=task.error_message,
        crawl_frequency=str(task.crawl_frequency) if task.crawl_frequency else None,
        next_crawl_at=task.next_crawl_at,
        recrawl_count=task.recrawl_count,
        is_recurring=task.is_recurring,
        html_path=task.html_path,
        http_status_code=task.http_status_code,
        response_time_ms=task.response_time_ms,
        proxy_id=task.proxy_id,
        proxy_url=task.proxy.proxy_url if task.proxy else None,
        created_at=task.created_at,
        updated_at=task.updated_at,
        created_by=task.created_by
    )

    return ApiResponse(
        success=True,
        data=response_data
    )


@router.get("", response_model=PaginatedResponse[CrawlTaskResponse])
async def list_tasks(
    domain_id: Optional[int] = Query(None, ge=1, description="Filter by domain"),
    status: Optional[str] = Query(None, description="Filter by status"),
    priority_min: Optional[int] = Query(None, ge=1, le=10, description="Minimum priority"),
    priority_max: Optional[int] = Query(None, ge=1, le=10, description="Maximum priority"),
    created_after: Optional[datetime] = Query(None, description="Created after timestamp"),
    created_before: Optional[datetime] = Query(None, description="Created before timestamp"),
    is_recurring: Optional[bool] = Query(None, description="Filter recurring tasks"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Results per page"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
    db: Session = Depends(get_db)
):
    """
    List crawl tasks with filtering, sorting, and pagination.

    Supports various filters to narrow down results and pagination for
    large result sets.

    **Returns:**
    - 200: Tasks list with pagination metadata
    """
    # Validate sort field
    allowed_sort_fields = [
        'id', 'created_at', 'updated_at', 'scheduled_at',
        'completed_at', 'priority', 'status', 'retry_count'
    ]
    if sort_by not in allowed_sort_fields:
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": {
                    "code": "INVALID_SORT_FIELD",
                    "message": f"Invalid sort field: {sort_by}",
                    "details": {"allowed_fields": allowed_sort_fields}
                }
            }
        )

    # Build query with filters
    query = db.query(CrawlTask).options(joinedload(CrawlTask.domain))

    # Apply filters
    filters = []
    if domain_id is not None:
        filters.append(CrawlTask.domain_id == domain_id)
    if status is not None:
        filters.append(CrawlTask.status == status)
    if priority_min is not None:
        filters.append(CrawlTask.priority >= priority_min)
    if priority_max is not None:
        filters.append(CrawlTask.priority <= priority_max)
    if created_after is not None:
        filters.append(CrawlTask.created_at >= created_after)
    if created_before is not None:
        filters.append(CrawlTask.created_at <= created_before)
    if is_recurring is not None:
        filters.append(CrawlTask.is_recurring == is_recurring)

    if filters:
        query = query.filter(and_(*filters))

    # Get total count before pagination
    total_count = query.count()

    # Apply sorting
    sort_column = getattr(CrawlTask, sort_by)
    if sort_order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))

    # Apply pagination
    offset = (page - 1) * per_page
    tasks = query.offset(offset).limit(per_page).all()

    # Build response list
    task_responses = [
        CrawlTaskResponse(
            id=task.id,
            domain_id=task.domain_id,
            domain_name=task.domain.domain_name if task.domain else None,
            url=task.url,
            url_hash=task.url_hash,
            status=task.status,
            priority=task.priority,
            scheduled_at=task.scheduled_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            retry_count=task.retry_count,
            response_time_ms=task.response_time_ms,
            created_at=task.created_at
        )
        for task in tasks
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
        data=task_responses,
        pagination=pagination
    )
