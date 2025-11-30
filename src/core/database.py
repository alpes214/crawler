"""
Database configuration and session management.

Provides SQLAlchemy engine, session factory, and Base class for models.
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from src.core.config import settings

# Create SQLAlchemy engine
engine = create_engine(
    settings.get_database_url_sync(),
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,        # Connection pool size
    max_overflow=20,     # Max overflow connections
    echo=False,          # Set to True for SQL query logging
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Create declarative base for models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency function for FastAPI to get database session.

    Usage in FastAPI endpoints:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            items = db.query(Item).all()
            return items

    Yields:
        Database session

    Ensures:
        Session is properly closed after use
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database - create all tables.

    WARNING: This creates tables directly without migrations.
    For production, use Alembic migrations instead.

    Usage:
        from src.core.database import init_db
        init_db()  # Creates all tables
    """
    # Import all models to ensure they're registered with Base
    from src.core.models import (
        Domain,
        CrawlTask,
        Product,
        Image,
        Proxy,
        DomainProxy
    )

    # Create all tables
    Base.metadata.create_all(bind=engine)


def drop_all():
    """
    Drop all tables from database.

    WARNING: This deletes all data! Use with caution.

    Usage:
        from src.core.database import drop_all
        drop_all()  # Drops all tables
    """
    Base.metadata.drop_all(bind=engine)
