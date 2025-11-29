# Core API Design

## Overview

This document describes the FastAPI REST API endpoints for the crawler system, organized into functional groups:

1. **Crawl Task Management** - Submit, monitor, restart, pause/resume tasks
2. **Domain Management** - Configure domains, parsers, crawl settings
3. **Proxy Management** - Manage proxy pool and health
4. **Domain-Proxy Management** - Map proxies to domains, track performance
5. **Product Query API** - Search and retrieve crawled products
6. **System Monitoring** - Health checks, statistics, diagnostics

---

## API Architecture

### Base URL

```
http://localhost:8000/api
```

### Authentication

**Phase 1 (MVP)**: No authentication (internal use only)

**Phase 2**: API key authentication
```http
Authorization: Bearer <api_key>
```

**Phase 3**: JWT tokens with role-based access control (RBAC)

### Response Format

**Success Response**:
```json
{
  "success": true,
  "data": { ... },
  "message": "Operation completed successfully"
}
```

**Error Response**:
```json
{
  "success": false,
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "Task with ID 12345 not found",
    "details": { ... }
  }
}
```

**Pagination**:
```json
{
  "success": true,
  "data": [ ... ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 150,
    "total_pages": 8
  }
}
```

---

## 1. Crawl Task Management API

### 1.1 Submit Crawl Task

**Endpoint**: `POST /api/admin/tasks`

**Description**: Submit a new URL for crawling

**Request Body**:
```json
{
  "domain_id": 1,
  "url": "https://www.amazon.com/dp/B08N5WRWNW",
  "priority": 5,
  "scheduled_at": "2025-11-30T10:00:00Z",
  "crawl_frequency": "1 day",
  "is_recurring": true,
  "max_retries": 3
}
```

**Field Descriptions**:
- `domain_id` (required): Domain ID from domains table
- `url` (required): Full URL to crawl
- `priority` (optional, default: 5): 1 (highest) to 10 (lowest)
- `scheduled_at` (optional, default: NOW): When to execute
- `crawl_frequency` (optional, default: "1 day"): Recrawl interval (PostgreSQL INTERVAL)
- `is_recurring` (optional, default: true): Auto-schedule next crawl
- `max_retries` (optional, default: 3): Max retry attempts

**Response** (201 Created):
```json
{
  "success": true,
  "data": {
    "task_id": 12345,
    "url": "https://www.amazon.com/dp/B08N5WRWNW",
    "url_hash": "a3f5e8d9c2b1...",
    "status": "pending",
    "priority": 5,
    "scheduled_at": "2025-11-30T10:00:00Z",
    "created_at": "2025-11-29T15:30:00Z"
  },
  "message": "Task created successfully"
}
```

**Error Responses**:
- `400 Bad Request`: Invalid URL or parameters
- `409 Conflict`: URL already exists (duplicate url_hash)
- `404 Not Found`: Domain ID not found

---

### 1.2 Submit Batch Crawl Tasks

**Endpoint**: `POST /api/admin/tasks/batch`

**Description**: Submit multiple URLs at once (up to 10,000 URLs)

**Request Body**:
```json
{
  "domain_id": 1,
  "urls": [
    "https://www.amazon.com/dp/B08N5WRWNW",
    "https://www.amazon.com/dp/B08L5KZMR3",
    "https://www.amazon.com/dp/B07XJ8C8F5"
  ],
  "priority": 5,
  "crawl_frequency": "1 day",
  "is_recurring": true
}
```

**Response** (201 Created):
```json
{
  "success": true,
  "data": {
    "total_submitted": 3,
    "total_duplicates": 0,
    "total_failed": 0,
    "task_ids": [12345, 12346, 12347]
  },
  "message": "Batch tasks created successfully"
}
```

---

### 1.3 Get Task Details

**Endpoint**: `GET /api/admin/tasks/{task_id}`

**Description**: Get detailed information about a specific task

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "id": 12345,
    "domain_id": 1,
    "domain_name": "amazon.com",
    "url": "https://www.amazon.com/dp/B08N5WRWNW",
    "url_hash": "a3f5e8d9c2b1...",
    "status": "completed",
    "priority": 5,
    "scheduled_at": "2025-11-29T10:00:00Z",
    "started_at": "2025-11-29T10:00:05Z",
    "completed_at": "2025-11-29T10:00:12Z",
    "retry_count": 0,
    "max_retries": 3,
    "error_message": null,
    "crawl_frequency": "1 day",
    "next_crawl_at": "2025-11-30T10:00:12Z",
    "recrawl_count": 5,
    "is_recurring": true,
    "html_path": "storage/12345/page.html",
    "http_status_code": 200,
    "response_time_ms": 487,
    "proxy_id": 3,
    "proxy_url": "proxy3.example.com",
    "created_at": "2025-11-28T15:30:00Z",
    "updated_at": "2025-11-29T10:00:12Z",
    "created_by": "admin"
  }
}
```

**Error Responses**:
- `404 Not Found`: Task ID not found

---

### 1.4 List Tasks with Filters

**Endpoint**: `GET /api/admin/tasks`

**Description**: List tasks with filtering, sorting, pagination

**Query Parameters**:
```
?domain_id=1
&status=completed
&priority_min=1
&priority_max=3
&created_after=2025-11-28T00:00:00Z
&created_before=2025-11-30T00:00:00Z
&is_recurring=true
&page=1
&per_page=20
&sort_by=created_at
&sort_order=desc
```

**Parameter Descriptions**:
- `domain_id` (optional): Filter by domain
- `status` (optional): Filter by status (pending, queued, crawling, etc.)
- `priority_min`, `priority_max` (optional): Priority range
- `created_after`, `created_before` (optional): Date range
- `is_recurring` (optional): Filter recurring tasks
- `page` (optional, default: 1): Page number
- `per_page` (optional, default: 20, max: 100): Results per page
- `sort_by` (optional, default: created_at): Sort field
- `sort_order` (optional, default: desc): asc or desc

**Response** (200 OK):
```json
{
  "success": true,
  "data": [
    {
      "id": 12345,
      "domain_name": "amazon.com",
      "url": "https://www.amazon.com/dp/B08N5WRWNW",
      "status": "completed",
      "priority": 5,
      "scheduled_at": "2025-11-29T10:00:00Z",
      "completed_at": "2025-11-29T10:00:12Z",
      "response_time_ms": 487
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 150,
    "total_pages": 8
  }
}
```

---

### 1.5 Restart Task (Full Re-crawl)

**Endpoint**: `POST /api/admin/tasks/{task_id}/restart`

**Description**: Restart a failed or completed task from scratch

**Request Body** (optional):
```json
{
  "reset_retry_count": true,
  "priority": 1,
  "scheduled_at": "2025-11-30T10:00:00Z"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "task_id": 12345,
    "status": "pending",
    "scheduled_at": "2025-11-30T10:00:00Z",
    "retry_count": 0,
    "priority": 1
  },
  "message": "Task restarted successfully"
}
```

---

### 1.6 Restart Parsing Only

**Endpoint**: `POST /api/admin/tasks/{task_id}/restart-parsing`

**Description**: Restart only the parsing phase (HTML already downloaded)

**Request Body** (optional):
```json
{
  "reset_retry_count": true
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "task_id": 12345,
    "status": "downloaded",
    "html_path": "storage/12345/page.html"
  },
  "message": "Parsing phase restarted successfully"
}
```

**Error Responses**:
- `400 Bad Request`: HTML not available (html_path is NULL)

---

### 1.7 Bulk Restart Failed Tasks

**Endpoint**: `POST /api/admin/tasks/restart-failed`

**Description**: Restart multiple failed tasks at once

**Request Body**:
```json
{
  "domain_id": 1,
  "failed_after": "2025-11-28T00:00:00Z",
  "limit": 1000
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "total_restarted": 247,
    "task_ids": [12345, 12346, 12347, ...]
  },
  "message": "247 failed tasks restarted successfully"
}
```

---

### 1.8 Pause Task

**Endpoint**: `POST /api/admin/tasks/{task_id}/pause`

**Description**: Pause a pending, queued, or running task

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "task_id": 12345,
    "status": "paused",
    "previous_status": "crawling"
  },
  "message": "Task paused successfully"
}
```

**Note**: If task is already in RabbitMQ queue, worker will check status before processing

---

### 1.9 Resume Task

**Endpoint**: `POST /api/admin/tasks/{task_id}/resume`

**Description**: Resume a paused task

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "task_id": 12345,
    "status": "pending",
    "scheduled_at": "2025-11-29T16:00:00Z"
  },
  "message": "Task resumed successfully"
}
```

---

### 1.10 Change Task Priority

**Endpoint**: `PATCH /api/admin/tasks/{task_id}/priority`

**Description**: Change task priority

**Request Body**:
```json
{
  "priority": 1
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "task_id": 12345,
    "priority": 1,
    "previous_priority": 5
  },
  "message": "Task priority updated successfully"
}
```

---

### 1.11 Cancel Task

**Endpoint**: `DELETE /api/admin/tasks/{task_id}`

**Description**: Cancel a task (set status to 'cancelled')

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "task_id": 12345,
    "status": "cancelled"
  },
  "message": "Task cancelled successfully"
}
```

---

### 1.12 Get Task Statistics

**Endpoint**: `GET /api/admin/tasks/stats`

**Description**: Get aggregate statistics for tasks

**Query Parameters**:
```
?domain_id=1
&time_range=24h
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "total_tasks": 15000,
    "by_status": {
      "pending": 500,
      "queued": 200,
      "crawling": 50,
      "downloaded": 30,
      "parsing": 20,
      "completed": 13800,
      "failed": 300,
      "paused": 100
    },
    "success_rate": 97.85,
    "avg_response_time_ms": 523,
    "total_recrawls": 45000,
    "time_range": "last_24_hours"
  }
}
```

---

## 2. Domain Management API

### 2.1 Create Domain

**Endpoint**: `POST /api/admin/domains`

**Description**: Add a new domain to crawl

**Request Body**:
```json
{
  "domain_name": "amazon.com",
  "base_url": "https://www.amazon.com",
  "parser_name": "amazon",
  "crawl_delay_seconds": 2,
  "max_concurrent_requests": 5,
  "default_crawl_frequency": "1 day",
  "user_agent": "ProductCrawler/1.0 (+https://example.com/bot)"
}
```

**Response** (201 Created):
```json
{
  "success": true,
  "data": {
    "id": 1,
    "domain_name": "amazon.com",
    "base_url": "https://www.amazon.com",
    "parser_name": "amazon",
    "is_active": true,
    "created_at": "2025-11-29T15:00:00Z"
  },
  "message": "Domain created successfully"
}
```

---

### 2.2 Get Domain Details

**Endpoint**: `GET /api/admin/domains/{domain_id}`

**Description**: Get detailed domain information

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "id": 1,
    "domain_name": "amazon.com",
    "base_url": "https://www.amazon.com",
    "parser_name": "amazon",
    "crawl_delay_seconds": 2,
    "max_concurrent_requests": 5,
    "default_crawl_frequency": "1 day",
    "is_active": true,
    "robots_txt_url": "https://www.amazon.com/robots.txt",
    "robots_txt_content": "User-agent: *\nCrawl-delay: 2\n...",
    "robots_txt_last_fetched": "2025-11-29T12:00:00Z",
    "user_agent": "ProductCrawler/1.0",
    "created_at": "2025-11-28T10:00:00Z",
    "updated_at": "2025-11-29T12:00:00Z",
    "stats": {
      "total_tasks": 5000,
      "active_proxies": 5,
      "success_rate": 98.5
    }
  }
}
```

---

### 2.3 List Domains

**Endpoint**: `GET /api/admin/domains`

**Description**: List all domains

**Query Parameters**:
```
?is_active=true
&page=1
&per_page=20
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "domain_name": "amazon.com",
      "parser_name": "amazon",
      "is_active": true,
      "total_tasks": 5000,
      "active_proxies": 5
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 3,
    "total_pages": 1
  }
}
```

---

### 2.4 Update Domain Settings

**Endpoint**: `PATCH /api/admin/domains/{domain_id}`

**Description**: Update domain configuration

**Request Body** (partial update):
```json
{
  "crawl_delay_seconds": 3,
  "max_concurrent_requests": 10,
  "is_active": true
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "id": 1,
    "domain_name": "amazon.com",
    "crawl_delay_seconds": 3,
    "max_concurrent_requests": 10,
    "is_active": true,
    "updated_at": "2025-11-29T16:00:00Z"
  },
  "message": "Domain updated successfully"
}
```

---

### 2.5 Enable Domain

**Endpoint**: `POST /api/admin/domains/{domain_id}/enable`

**Description**: Enable crawling for domain

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "domain_id": 1,
    "is_active": true
  },
  "message": "Domain enabled successfully"
}
```

---

### 2.6 Disable Domain

**Endpoint**: `POST /api/admin/domains/{domain_id}/disable`

**Description**: Disable crawling for domain (stops scheduling new tasks)

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "domain_id": 1,
    "is_active": false
  },
  "message": "Domain disabled successfully"
}
```

---

### 2.7 Refresh robots.txt

**Endpoint**: `POST /api/admin/domains/{domain_id}/refresh-robots`

**Description**: Fetch and cache latest robots.txt

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "domain_id": 1,
    "robots_txt_url": "https://www.amazon.com/robots.txt",
    "robots_txt_last_fetched": "2025-11-29T16:30:00Z",
    "crawl_delay_found": 2,
    "updated_settings": {
      "crawl_delay_seconds": 2
    }
  },
  "message": "robots.txt refreshed successfully"
}
```

---

## 3. Proxy Management API

### 3.1 Add Proxy

**Endpoint**: `POST /api/admin/proxies`

**Description**: Add a new proxy to the pool

**Request Body**:
```json
{
  "proxy_url": "proxy1.example.com",
  "proxy_port": 8080,
  "proxy_protocol": "http",
  "proxy_username": "user123",
  "proxy_password": "pass456",
  "country_code": "US",
  "city": "New York",
  "provider": "ProxyProvider Inc",
  "monthly_cost": 50.00,
  "max_requests_per_hour": 1000
}
```

**Response** (201 Created):
```json
{
  "success": true,
  "data": {
    "id": 3,
    "proxy_url": "proxy1.example.com",
    "proxy_port": 8080,
    "proxy_protocol": "http",
    "country_code": "US",
    "is_active": true,
    "created_at": "2025-11-29T15:00:00Z"
  },
  "message": "Proxy created successfully"
}
```

---

### 3.2 Get Proxy Details

**Endpoint**: `GET /api/admin/proxies/{proxy_id}`

**Description**: Get detailed proxy information

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "id": 3,
    "proxy_url": "proxy1.example.com",
    "proxy_port": 8080,
    "proxy_protocol": "http",
    "country_code": "US",
    "city": "New York",
    "provider": "ProxyProvider Inc",
    "is_active": true,
    "failure_count": 2,
    "success_count": 1543,
    "last_used_at": "2025-11-29T16:00:00Z",
    "last_success_at": "2025-11-29T16:00:00Z",
    "last_failure_at": "2025-11-28T12:00:00Z",
    "avg_response_time_ms": 487,
    "monthly_cost": 50.00,
    "max_requests_per_hour": 1000,
    "created_at": "2025-11-28T10:00:00Z",
    "stats": {
      "success_rate": 99.87,
      "total_requests": 1545,
      "domains_using": 3
    }
  }
}
```

---

### 3.3 List Proxies

**Endpoint**: `GET /api/admin/proxies`

**Description**: List all proxies with health status

**Query Parameters**:
```
?is_active=true
&country_code=US
&provider=ProxyProvider Inc
&page=1
&per_page=20
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": [
    {
      "id": 3,
      "proxy_url": "proxy1.example.com",
      "proxy_port": 8080,
      "country_code": "US",
      "is_active": true,
      "success_count": 1543,
      "failure_count": 2,
      "success_rate": 99.87,
      "avg_response_time_ms": 487,
      "last_used_at": "2025-11-29T16:00:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 15,
    "total_pages": 1
  }
}
```

---

### 3.4 Update Proxy

**Endpoint**: `PATCH /api/admin/proxies/{proxy_id}`

**Description**: Update proxy settings

**Request Body**:
```json
{
  "is_active": true,
  "monthly_cost": 60.00,
  "max_requests_per_hour": 1200
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "id": 3,
    "is_active": true,
    "monthly_cost": 60.00,
    "updated_at": "2025-11-29T16:30:00Z"
  },
  "message": "Proxy updated successfully"
}
```

---

### 3.5 Enable Proxy

**Endpoint**: `POST /api/admin/proxies/{proxy_id}/enable`

**Description**: Enable proxy and reset failure count

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "proxy_id": 3,
    "is_active": true,
    "failure_count": 0
  },
  "message": "Proxy enabled successfully"
}
```

---

### 3.6 Disable Proxy

**Endpoint**: `POST /api/admin/proxies/{proxy_id}/disable`

**Description**: Disable proxy (stops using it for crawling)

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "proxy_id": 3,
    "is_active": false
  },
  "message": "Proxy disabled successfully"
}
```

---

### 3.7 Delete Proxy

**Endpoint**: `DELETE /api/admin/proxies/{proxy_id}`

**Description**: Remove proxy from pool (cascade deletes domain_proxies mappings)

**Response** (200 OK):
```json
{
  "success": true,
  "message": "Proxy deleted successfully"
}
```

---

## 4. Domain-Proxy Management API

### 4.1 Assign Proxies to Domain

**Endpoint**: `POST /api/admin/domains/{domain_id}/proxies`

**Description**: Assign one or more proxies to a domain

**Request Body**:
```json
{
  "proxy_ids": [1, 2, 3, 4, 5],
  "priority": 5
}
```

**Response** (201 Created):
```json
{
  "success": true,
  "data": {
    "domain_id": 1,
    "domain_name": "amazon.com",
    "proxies_assigned": 5,
    "proxy_ids": [1, 2, 3, 4, 5],
    "total_proxies": 5
  },
  "message": "5 proxies assigned to domain successfully"
}
```

---

### 4.2 List Domain's Proxies

**Endpoint**: `GET /api/admin/domains/{domain_id}/proxies`

**Description**: Get all proxies assigned to a domain with performance stats

**Query Parameters**:
```
?is_active=true
&sort_by=success_rate
&sort_order=desc
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "domain_id": 1,
    "domain_name": "amazon.com",
    "total_proxies": 5,
    "active_proxies": 4,
    "proxies": [
      {
        "proxy_id": 1,
        "proxy_url": "proxy1.example.com",
        "proxy_port": 8080,
        "country_code": "US",
        "is_active": true,
        "priority": 5,
        "success_count": 1543,
        "failure_count": 12,
        "success_rate_percent": 99.23,
        "avg_response_time_ms": 487,
        "last_used_at": "2025-11-29T14:30:00Z"
      },
      {
        "proxy_id": 2,
        "proxy_url": "proxy2.example.com",
        "proxy_port": 8080,
        "country_code": "DE",
        "is_active": true,
        "priority": 5,
        "success_count": 1502,
        "failure_count": 45,
        "success_rate_percent": 97.09,
        "avg_response_time_ms": 623,
        "last_used_at": "2025-11-29T13:30:00Z"
      }
    ]
  }
}
```

---

### 4.3 Remove Proxy from Domain

**Endpoint**: `DELETE /api/admin/domains/{domain_id}/proxies/{proxy_id}`

**Description**: Remove proxy assignment from domain

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "domain_id": 1,
    "proxy_id": 3,
    "remaining_proxies": 4
  },
  "message": "Proxy removed from domain successfully"
}
```

---

### 4.4 Enable Domain-Proxy Mapping

**Endpoint**: `POST /api/admin/domains/{domain_id}/proxies/{proxy_id}/enable`

**Description**: Enable specific proxy for specific domain and reset failure count

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "domain_id": 1,
    "proxy_id": 3,
    "is_active": true,
    "failure_count": 0
  },
  "message": "Domain-proxy mapping enabled successfully"
}
```

---

### 4.5 Disable Domain-Proxy Mapping

**Endpoint**: `POST /api/admin/domains/{domain_id}/proxies/{proxy_id}/disable`

**Description**: Disable specific proxy for specific domain (keeps mapping, just disables)

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "domain_id": 1,
    "proxy_id": 3,
    "is_active": false
  },
  "message": "Domain-proxy mapping disabled successfully"
}
```

---

### 4.6 Get Domain-Proxy Stats

**Endpoint**: `GET /api/admin/domains/{domain_id}/proxies/stats`

**Description**: Get aggregate statistics for domain's proxy usage

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "domain_id": 1,
    "domain_name": "amazon.com",
    "total_proxies": 5,
    "active_proxies": 4,
    "failing_proxies": 1,
    "overall_success_rate": 98.45,
    "avg_response_time_ms": 523,
    "total_requests": 7500,
    "total_success": 7384,
    "total_failures": 116,
    "proxy_distribution": {
      "US": 3,
      "DE": 1,
      "FR": 1
    }
  }
}
```

---

## 5. Product Query API

### 5.1 Search Products (Full-Text)

**Endpoint**: `GET /api/products/search`

**Description**: Full-text search using Elasticsearch

**Query Parameters**:
```
?q=wireless headphones
&domain_id=1
&price_min=20
&price_max=100
&availability=in_stock
&brand=Sony
&page=1
&per_page=20
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": [
    {
      "id": 5001,
      "domain_name": "amazon.com",
      "url": "https://www.amazon.com/dp/B08N5WRWNW",
      "product_name": "Sony WH-1000XM4 Wireless Headphones",
      "description": "Industry-leading noise canceling...",
      "price": 349.99,
      "currency": "USD",
      "availability": "in_stock",
      "rating": 4.8,
      "review_count": 12543,
      "brand": "Sony",
      "category": "Electronics",
      "images": [
        {
          "image_url": "https://...",
          "image_type": "primary"
        }
      ],
      "created_at": "2025-11-28T10:00:00Z",
      "updated_at": "2025-11-29T15:00:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 156,
    "total_pages": 8
  }
}
```

---

### 5.2 Get Product Details

**Endpoint**: `GET /api/products/{product_id}`

**Description**: Get detailed product information

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "id": 5001,
    "domain_id": 1,
    "domain_name": "amazon.com",
    "crawl_task_id": 12345,
    "url": "https://www.amazon.com/dp/B08N5WRWNW",
    "product_name": "Sony WH-1000XM4 Wireless Headphones",
    "description": "Industry-leading noise canceling...",
    "price": 349.99,
    "currency": "USD",
    "availability": "in_stock",
    "rating": 4.8,
    "review_count": 12543,
    "brand": "Sony",
    "category": "Electronics",
    "sku": "WH1000XM4/B",
    "metadata": {
      "color": "Black",
      "connectivity": "Bluetooth",
      "battery_life": "30 hours"
    },
    "images": [
      {
        "id": 101,
        "image_url": "https://...",
        "image_path": "storage/5001/image1.jpg",
        "alt_text": "Sony WH-1000XM4 Front View",
        "image_type": "primary",
        "position": 0,
        "width": 1500,
        "height": 1500
      }
    ],
    "created_at": "2025-11-28T10:00:00Z",
    "updated_at": "2025-11-29T15:00:00Z"
  }
}
```

---

### 5.3 List Products

**Endpoint**: `GET /api/products`

**Description**: List products with filtering and sorting

**Query Parameters**:
```
?domain_id=1
&brand=Sony
&category=Electronics
&price_min=100
&price_max=500
&availability=in_stock
&rating_min=4.0
&sort_by=price
&sort_order=asc
&page=1
&per_page=20
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": [
    {
      "id": 5001,
      "product_name": "Sony WH-1000XM4",
      "price": 349.99,
      "brand": "Sony",
      "rating": 4.8,
      "availability": "in_stock"
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 45,
    "total_pages": 3
  }
}
```

---

## 6. System Monitoring API

### 6.1 Health Check

**Endpoint**: `GET /api/health`

**Description**: Check system health

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "timestamp": "2025-11-29T16:00:00Z",
    "version": "1.0.0",
    "services": {
      "database": {
        "status": "up",
        "response_time_ms": 5
      },
      "rabbitmq": {
        "status": "up",
        "response_time_ms": 3
      },
      "elasticsearch": {
        "status": "up",
        "response_time_ms": 12
      }
    }
  }
}
```

---

### 6.2 System Statistics

**Endpoint**: `GET /api/admin/stats`

**Description**: Get overall system statistics

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "tasks": {
      "total": 50000,
      "pending": 500,
      "queued": 200,
      "running": 70,
      "completed": 48500,
      "failed": 730
    },
    "domains": {
      "total": 5,
      "active": 4,
      "disabled": 1
    },
    "proxies": {
      "total": 20,
      "active": 18,
      "failing": 2
    },
    "products": {
      "total": 1250000,
      "added_today": 15000
    },
    "performance": {
      "avg_crawl_time_ms": 487,
      "avg_parse_time_ms": 125,
      "success_rate": 97.85
    }
  }
}
```

---

### 6.3 Queue Status

**Endpoint**: `GET /api/admin/queues`

**Description**: Get RabbitMQ queue status

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "crawl_queue": {
      "messages_ready": 450,
      "messages_unacked": 50,
      "consumers": 50
    },
    "parse_queue": {
      "messages_ready": 120,
      "messages_unacked": 30,
      "consumers": 50
    },
    "priority_queue": {
      "messages_ready": 5,
      "messages_unacked": 2,
      "consumers": 10
    }
  }
}
```

---

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `TASK_NOT_FOUND` | 404 | Task ID not found |
| `DOMAIN_NOT_FOUND` | 404 | Domain ID not found |
| `PROXY_NOT_FOUND` | 404 | Proxy ID not found |
| `DUPLICATE_URL` | 409 | URL already exists (url_hash conflict) |
| `INVALID_URL` | 400 | URL format invalid |
| `INVALID_PRIORITY` | 400 | Priority must be 1-10 |
| `INVALID_STATUS` | 400 | Invalid status value |
| `HTML_NOT_AVAILABLE` | 400 | HTML file not found (for restart-parsing) |
| `NO_PROXIES_AVAILABLE` | 400 | No active proxies for domain |
| `DATABASE_ERROR` | 500 | Database operation failed |
| `RABBITMQ_ERROR` | 500 | RabbitMQ connection failed |
| `ELASTICSEARCH_ERROR` | 500 | Elasticsearch operation failed |

---

## Rate Limiting

**Phase 2**: Implement rate limiting per API key

```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 950
X-RateLimit-Reset: 2025-11-29T17:00:00Z
```

**Limits**:
- `/api/admin/*`: 1000 requests/hour
- `/api/products/*`: 5000 requests/hour

---

## Webhook Notifications (Future)

**Phase 3**: Webhook support for task completion

**Configuration**:
```json
{
  "webhook_url": "https://example.com/webhook",
  "events": ["task.completed", "task.failed"]
}
```

**Webhook Payload**:
```json
{
  "event": "task.completed",
  "timestamp": "2025-11-29T16:00:00Z",
  "data": {
    "task_id": 12345,
    "url": "https://www.amazon.com/dp/B08N5WRWNW",
    "status": "completed",
    "product_id": 5001
  }
}
```

---

## Implementation Notes

### FastAPI Route Organization

```python
# src/api/main.py
from fastapi import FastAPI
from src.api.routes import tasks, domains, proxies, products, system

app = FastAPI(title="Crawler API", version="1.0.0")

app.include_router(tasks.router, prefix="/api/admin/tasks", tags=["Tasks"])
app.include_router(domains.router, prefix="/api/admin/domains", tags=["Domains"])
app.include_router(proxies.router, prefix="/api/admin/proxies", tags=["Proxies"])
app.include_router(products.router, prefix="/api/products", tags=["Products"])
app.include_router(system.router, prefix="/api", tags=["System"])
```

### Pydantic Schemas

Located in `src/api/schemas/`:
- `crawl_job.py` - CrawlJobCreate, CrawlJobResponse
- `product.py` - ProductResponse, ProductFilter
- `proxy.py` - ProxyCreate, ProxyResponse
- `domain.py` - DomainCreate, DomainResponse
- `response.py` - ApiResponse, ErrorResponse, PaginationInfo

### Authentication Decorator (Phase 2)

```python
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    api_key = credentials.credentials
    # Validate API key
    if not is_valid_api_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key

# Usage
@router.post("/tasks")
async def create_task(task: CrawlJobCreate, api_key: str = Depends(verify_api_key)):
    ...
```
