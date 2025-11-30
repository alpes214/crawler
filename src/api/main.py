"""
FastAPI main application entry point.

Configures the application, registers routes, and provides global exception handling.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes_tasks import router as tasks_router
from src.api.routes_domains import router as domains_router
from src.api.routes_proxies import router as proxies_router
from src.api.routes_domain_proxies import router as domain_proxies_router

# Create FastAPI application
app = FastAPI(
    title="Crawler API",
    description="Web crawler system for product data extraction",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS (adjust for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(
    tasks_router,
    prefix="/api/admin/tasks",
    tags=["Crawl Tasks"]
)

app.include_router(
    domains_router,
    prefix="/api/admin/domains",
    tags=["Domains"]
)

app.include_router(
    proxies_router,
    prefix="/api/admin/proxies",
    tags=["Proxies"]
)

app.include_router(
    domain_proxies_router,
    prefix="/api/admin/domains/{domain_id}/proxies",
    tags=["Domain-Proxy Mappings"]
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "details": {"error": str(exc)}
            }
        }
    )


# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Basic health check endpoint."""
    return {
        "success": True,
        "data": {
            "status": "healthy",
            "version": "1.0.0"
        }
    }


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Crawler API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/health"
    }
