from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.core.database import Base


class Image(Base):
    __tablename__ = "images"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)

    # Foreign key
    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to product"
    )

    # Image URLs and storage
    image_url = Column(
        Text,
        nullable=False,
        comment="Original image URL from source website"
    )
    image_path = Column(
        String(512),
        nullable=True,
        comment="Local/S3 storage path (NULL if not downloaded yet)"
    )

    # Image metadata
    alt_text = Column(
        String(512),
        nullable=True,
        comment="Image alt text/description"
    )
    image_type = Column(
        String(50),
        default="primary",
        nullable=False,
        index=True,
        comment="Image type (primary, gallery, thumbnail)"
    )
    position = Column(
        Integer,
        default=0,
        nullable=False,
        comment="Display order (0=first, position for gallery carousel)"
    )

    # Image dimensions and size
    width = Column(
        Integer,
        nullable=True,
        comment="Image width in pixels"
    )
    height = Column(
        Integer,
        nullable=True,
        comment="Image height in pixels"
    )
    file_size = Column(
        Integer,
        nullable=True,
        comment="File size in bytes"
    )

    # Timestamp
    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Record creation time"
    )

    # Relationships
    product = relationship("Product", back_populates="images")

    def __repr__(self):
        return (
            f"<Image(id={self.id}, "
            f"product_id={self.product_id}, "
            f"type='{self.image_type}', "
            f"position={self.position})>"
        )

    @property
    def is_primary(self) -> bool:
        """Check if this is the primary product image."""
        return self.image_type == "primary"

    @property
    def is_downloaded(self) -> bool:
        """Check if image has been downloaded to storage."""
        return self.image_path is not None

    @property
    def aspect_ratio(self) -> float:
        """
        Calculate image aspect ratio.

        Returns:
            Aspect ratio (width/height) or 0.0 if dimensions not available
        """
        if not self.width or not self.height:
            return 0.0
        return self.width / self.height

    @property
    def dimensions_str(self) -> str:
        """
        Get dimensions as string.

        Returns:
            Dimensions in format "WxH" or "unknown" if not available
        """
        if not self.width or not self.height:
            return "unknown"
        return f"{self.width}x{self.height}"

    @property
    def file_size_kb(self) -> float:
        """
        Get file size in kilobytes.

        Returns:
            File size in KB or 0.0 if not available
        """
        if not self.file_size:
            return 0.0
        return self.file_size / 1024

    def update_metadata(self, width: int, height: int, file_size: int):
        """
        Update image metadata after download.

        Args:
            width: Image width in pixels
            height: Image height in pixels
            file_size: File size in bytes
        """
        self.width = width
        self.height = height
        self.file_size = file_size

    def mark_downloaded(self, storage_path: str):
        """
        Mark image as downloaded with storage path.

        Args:
            storage_path: Path where image is stored (local or S3)
        """
        self.image_path = storage_path
