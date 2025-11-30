from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, Numeric, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.core.database import Base


class Product(Base):
    __tablename__ = "products"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)

    # Foreign keys
    domain_id = Column(
        Integer,
        ForeignKey("domains.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Source domain"
    )
    crawl_task_id = Column(
        Integer,
        ForeignKey("crawl_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Original crawl task that created this product"
    )

    # URL information
    url = Column(
        Text,
        nullable=False,
        comment="Product page URL"
    )
    url_hash = Column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="SHA256 hash of URL (deduplication)"
    )

    # Product attributes
    product_name = Column(
        String(512),
        nullable=False,
        index=True,
        comment="Product name/title"
    )
    description = Column(
        Text,
        nullable=True,
        comment="Full product description (indexed in Elasticsearch)"
    )

    # Pricing
    price = Column(
        Numeric(10, 2),
        nullable=True,
        index=True,
        comment="Current price"
    )
    currency = Column(
        String(3),
        default="USD",
        nullable=False,
        comment="Currency code (ISO 4217: USD, EUR, GBP)"
    )

    # Availability
    availability = Column(
        String(50),
        nullable=True,
        index=True,
        comment="Stock status (in_stock, out_of_stock, preorder, discontinued)"
    )

    # Quality signals
    rating = Column(
        Numeric(3, 2),
        nullable=True,
        index=True,
        comment="Product rating (0.00-5.00)"
    )
    review_count = Column(
        Integer,
        nullable=True,
        comment="Number of reviews"
    )

    # Categorization
    brand = Column(
        String(255),
        nullable=True,
        index=True,
        comment="Brand name"
    )
    category = Column(
        String(255),
        nullable=True,
        index=True,
        comment="Product category"
    )
    sku = Column(
        String(100),
        nullable=True,
        comment="Stock keeping unit"
    )

    # Change detection
    content_hash = Column(
        String(64),
        nullable=True,
        comment="SHA256 hash of product data (detect changes)"
    )

    # Flexible metadata
    extra_attributes = Column(
        JSON,
        nullable=True,
        comment="Additional metadata (color, size, weight, etc.)"
    )

    # Timestamps
    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="First crawled timestamp"
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Last updated timestamp"
    )

    # Relationships
    domain = relationship("Domain", back_populates="products")
    crawl_task = relationship("CrawlTask", back_populates="products")
    images = relationship(
        "Image",
        back_populates="product",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return (
            f"<Product(id={self.id}, "
            f"name='{self.product_name[:30]}...', "
            f"price={self.price} {self.currency}, "
            f"brand='{self.brand}')>"
        )

    @property
    def has_price(self) -> bool:
        """Check if product has a price."""
        return self.price is not None

    @property
    def has_rating(self) -> bool:
        """Check if product has a rating."""
        return self.rating is not None

    @property
    def is_in_stock(self) -> bool:
        """Check if product is in stock."""
        return self.availability == "in_stock"

    @property
    def age_days(self) -> int:
        """Calculate product age in days since first crawled."""
        from datetime import datetime
        if not self.created_at:
            return 0
        age = datetime.now(self.created_at.tzinfo) - self.created_at
        return age.days

    def compute_content_hash(self) -> str:
        """
        Compute content hash for change detection.

        Hash is computed from:
        - product_name
        - price
        - description
        - availability

        Returns:
            SHA256 hash as hex string
        """
        import hashlib

        content = (
            f"{self.product_name or ''}"
            f"{self.price or ''}"
            f"{self.description or ''}"
            f"{self.availability or ''}"
        )
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def has_changed(self, new_content_hash: str) -> bool:
        """
        Check if product content has changed.

        Args:
            new_content_hash: New content hash to compare

        Returns:
            True if content has changed
        """
        return self.content_hash != new_content_hash

    def update_from_dict(self, data: dict):
        """
        Update product attributes from dictionary.

        Args:
            data: Dictionary with product attributes
        """
        allowed_fields = {
            'product_name', 'description', 'price', 'currency',
            'availability', 'rating', 'review_count',
            'brand', 'category', 'sku', 'extra_attributes'
        }

        for key, value in data.items():
            if key in allowed_fields and hasattr(self, key):
                setattr(self, key, value)

        # Recompute content hash
        self.content_hash = self.compute_content_hash()
