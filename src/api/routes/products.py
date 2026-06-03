"""Product ingestion endpoints."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from src.crawl.handler import run_product_crawl
from src.db.models import SyncMode, SyncStatus
from src.db.repository import ProductRepository, ReviewRepository, SyncRunRepository
from src.db.session import get_db

router = APIRouter(prefix="/products", tags=["products"])


class CreateProductRequest(BaseModel):
    url: HttpUrl


class ProductResponse(BaseModel):
    id: uuid.UUID
    capterra_url: str
    slug: Optional[str]
    name: Optional[str]
    sync_status: SyncStatus
    known_review_count: int
    pagination_total_pages: Optional[int]
    last_synced_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ReviewResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    review_date: Optional[date]
    pros: str
    cons: str
    rating: Optional[Decimal]
    review: Optional[str]
    review_title: Optional[str]
    review_author_job_title: Optional[str]

    model_config = {"from_attributes": True}


class CreateProductResponse(BaseModel):
    product: ProductResponse
    sync_run_id: uuid.UUID
    pages_crawled: int
    new_reviews: int
    message: str

@router.get("/", include_in_schema=False)
def root():
    return {"ok": True}

@router.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}

@router.post("", response_model=CreateProductResponse)
def create_product(body: CreateProductRequest, db: Session = Depends(get_db)) -> CreateProductResponse:
    products = ProductRepository(db)
    sync_runs = SyncRunRepository(db)

    product = products.create_or_get(str(body.url))
    sync_mode = SyncMode.INCREMENTAL if product.known_review_count > 0 else SyncMode.FULL
    run = sync_runs.start(product.id, sync_mode)
    products.mark_syncing(product)
    db.commit()

    try:
        crawl = run_product_crawl(db, product.id, str(body.url), run.id)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Crawl failed: {exc}") from exc

    db.refresh(product)
    return CreateProductResponse(
        product=ProductResponse.model_validate(product),
        sync_run_id=run.id,
        pages_crawled=crawl.pages_crawled,
        new_reviews=crawl.new_reviews,
        message="Crawl completed",
    )


@router.get("/{product_id}", response_model=list[ReviewResponse])
def get_product(product_id: uuid.UUID, db: Session = Depends(get_db)) -> list[ReviewResponse]:
    if not ProductRepository(db).get_by_id(product_id):
        raise HTTPException(status_code=404, detail="Product not found")
    reviews = ReviewRepository(db).list_by_product_id(product_id)
    return [ReviewResponse.model_validate(r) for r in reviews]
