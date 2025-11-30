"""
SQLAlchemy ORM models for the crawler system.

Exports all database models for easy importing:
    from src.core.models import Domain, CrawlTask, Product, Image, Proxy, DomainProxy
"""

from src.core.models.domain import Domain
from src.core.models.crawl_task import CrawlTask, CrawlTaskStatus
from src.core.models.product import Product
from src.core.models.image import Image
from src.core.models.proxy import Proxy
from src.core.models.domain_proxy import DomainProxy

__all__ = [
    "Domain",
    "CrawlTask",
    "CrawlTaskStatus",
    "Product",
    "Image",
    "Proxy",
    "DomainProxy",
]
