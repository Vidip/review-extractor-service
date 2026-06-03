from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from src.db.models import Review


@dataclass(frozen=True)
class RetrievedReview:
    id: uuid.UUID
    review_date: Optional[str]
    rating: Optional[str]
    title: str
    pros: str
    cons: str
    review: str
    author_job_title: str


def _review_to_retrieved(r: Review) -> RetrievedReview:
    return RetrievedReview(
        id=r.id,
        review_date=r.review_date.isoformat() if r.review_date else None,
        rating=str(r.rating) if r.rating is not None else None,
        title=(r.review_title or "").strip(),
        pros=(r.pros or "").strip(),
        cons=(r.cons or "").strip(),
        review=(r.review or "").strip(),
        author_job_title=(r.review_author_job_title or "").strip(),
    )


def search_reviews_by_embedding(
    session: Session,
    query_embedding: List[float],
    *,
    product_id: uuid.UUID | None = None,
    k: int = 8,
) -> list[RetrievedReview]:
    """
    Vector-search `reviews.embedding` (pgvector) by cosine distance.
    Assumes embeddings are already stored on `reviews.embedding`.
    """
    stmt: Select = select(Review).where(Review.embedding.is_not(None))
    if product_id is not None:
        stmt = stmt.where(Review.product_id == product_id)

    # pgvector SQLAlchemy adds cosine_distance() comparator.
    stmt = stmt.order_by(Review.embedding.cosine_distance(query_embedding)).limit(k)
    rows = session.scalars(stmt).all()
    return [_review_to_retrieved(r) for r in rows]

