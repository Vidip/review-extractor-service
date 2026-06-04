from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from src.rag.embed import EMBEDDING_DIMENSIONS


class Base(DeclarativeBase):
    pass


class SyncStatus(str, enum.Enum):
    PENDING = "pending"
    SYNCING = "syncing"
    READY = "ready"
    ERROR = "error"


class SyncMode(str, enum.Enum):
    FULL = "full"
    INCREMENTAL = "incremental"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    capterra_url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    slug: Mapped[Optional[str]] = mapped_column(String(512))
    name: Mapped[Optional[str]] = mapped_column(String(512))
    sync_status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus, name="sync_status", values_callable=lambda x: [e.value for e in x]),
        default=SyncStatus.PENDING,
        nullable=False,
    )
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_review_date: Mapped[Optional[date]] = mapped_column(Date)
    known_review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pagination_total_pages: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    reviews: Mapped[List["Review"]] = relationship(back_populates="product")
    sync_runs: Mapped[List["SyncRun"]] = relationship(back_populates="product")


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("product_id", "content_hash", name="uq_reviews_product_hash"),
        Index("ix_reviews_product_date", "product_id", "review_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    review_date: Mapped[Optional[date]] = mapped_column(Date)
    pros: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cons: Mapped[str] = mapped_column(Text, default="", nullable=False)
    emotion: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    rating: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 1))
    search_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    review: Mapped[Optional[str]] = mapped_column(Text)
    review_title: Mapped[Optional[str]] = mapped_column(Text)
    review_author_job_title: Mapped[Optional[str]] = mapped_column(Text)
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped["Product"] = relationship(back_populates="reviews")


class Crawl(Base):
    """Singleton row tracking how many live page fetches have been performed."""

    __tablename__ = "crawl"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    crawl_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    mode: Mapped[SyncMode] = mapped_column(
        Enum(SyncMode, name="sync_mode", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    pages_crawled: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_reviews: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    product: Mapped["Product"] = relationship(back_populates="sync_runs")
