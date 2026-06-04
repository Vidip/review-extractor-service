"""Database operations for products, reviews, and sync runs."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.db.models import Crawl, Product, Review, SyncMode, SyncRun, SyncStatus
from src.extractor.hash import hash_review
from src.extractor.urls import extract_slug_from_url, normalize_capterra_url


def parse_review_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value.strip()[:20], fmt).date()
        except ValueError:
            continue
    return None


def parse_rating(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(str(value).strip())
    except InvalidOperation:
        return None


_CRAWL_SINGLETON_ID = 1


class CrawlRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_crawl_count(self) -> int:
        row = self.session.get(Crawl, _CRAWL_SINGLETON_ID)
        if row is None:
            row = Crawl(id=_CRAWL_SINGLETON_ID, crawl_count=0)
            self.session.add(row)
            self.session.flush()
        return row.crawl_count

    def increment_crawl_count(self) -> None:
        row = self.session.get(Crawl, _CRAWL_SINGLETON_ID)
        if row is None:
            row = Crawl(id=_CRAWL_SINGLETON_ID, crawl_count=0)
            self.session.add(row)
        row.crawl_count += 1
        self.session.flush()


class ProductRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, product_id: uuid.UUID) -> Product | None:
        return self.session.get(Product, product_id)

    def get_by_url(self, capterra_url: str) -> Product | None:
        normalized = normalize_capterra_url(capterra_url)
        return self.session.scalar(select(Product).where(Product.capterra_url == normalized))

    def create_or_get(self, capterra_url: str, name: str | None = None) -> Product:
        normalized = normalize_capterra_url(capterra_url)
        existing = self.get_by_url(normalized)
        if existing:
            return existing

        product = Product(
            capterra_url=normalized,
            slug=extract_slug_from_url(normalized),
            name=name or extract_slug_from_url(normalized),
            sync_status=SyncStatus.PENDING,
        )
        self.session.add(product)
        self.session.flush()
        return product

    def mark_syncing(self, product: Product) -> None:
        product.sync_status = SyncStatus.SYNCING
        self.session.flush()

    def mark_ready(self, product: Product) -> None:
        product.sync_status = SyncStatus.READY
        product.last_synced_at = datetime.now(timezone.utc)
        self.session.flush()

    def mark_error(self, product: Product) -> None:
        product.sync_status = SyncStatus.ERROR
        self.session.flush()

    def update_pagination(self, product: Product, total_pages: int) -> None:
        product.pagination_total_pages = total_pages
        self.session.flush()


class SyncRunRepository:
    def __init__(self, session: Session):
        self.session = session

    def start(self, product_id: uuid.UUID, mode: SyncMode) -> SyncRun:
        run = SyncRun(product_id=product_id, mode=mode)
        self.session.add(run)
        self.session.flush()
        return run

    def complete(self, run: SyncRun, pages_crawled: int, new_reviews: int) -> None:
        run.pages_crawled = pages_crawled
        run.new_reviews = new_reviews
        run.completed_at = datetime.now(timezone.utc)
        self.session.flush()

    def fail(self, run: SyncRun, error: str) -> None:
        run.error = error
        run.completed_at = datetime.now(timezone.utc)
        self.session.flush()


class ReviewRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_by_product_id(self, product_id: uuid.UUID) -> list[Review]:
        return list(
            self.session.scalars(
                select(Review)
                .where(Review.product_id == product_id)
                .order_by(Review.review_date.desc().nullslast(), Review.created_at.desc())
            )
        )

    def existing_hashes(self, product_id: uuid.UUID, hashes: Sequence[str]) -> set[str]:
        if not hashes:
            return set()
        rows = self.session.scalars(
            select(Review.content_hash).where(
                Review.product_id == product_id,
                Review.content_hash.in_(hashes),
            )
        )
        return set(rows.all())

    def insert_batch(
        self,
        product: Product,
        items: Iterable[tuple[dict, list[float], str]],
    ) -> int:
        inserted = 0
        latest_date = product.last_review_date

        for review_dict, embedding, search_text in items:
            content_hash = hash_review(review_dict)
            if self.session.scalar(
                select(Review.id).where(
                    Review.product_id == product.id,
                    Review.content_hash == content_hash,
                )
            ):
                continue

            review_date = parse_review_date(review_dict.get("reviewDate"))
            if review_date and (latest_date is None or review_date > latest_date):
                latest_date = review_date

            review = Review(
                product_id=product.id,
                content_hash=content_hash,
                review_date=review_date,
                pros=review_dict.get("reviewPros", "") or "",
                cons=review_dict.get("reviewCons", "") or "",
                emotion=review_dict.get("emotion", "") or "",
                rating=parse_rating(review_dict.get("rating")),
                search_text=search_text,
                review=review_dict.get("review", "") or "",
                review_title=review_dict.get("reviewTitle", "") or "",
                review_author_job_title=review_dict.get("reviewAuthorJobTitle", "") or "",
                embedding=embedding,
            )
            self.session.add(review)
            inserted += 1

        if inserted:
            self.session.flush()
            product.known_review_count = self.session.scalar(
                select(func.count()).select_from(Review).where(Review.product_id == product.id)
            ) or 0
            product.last_review_date = latest_date
            self.session.flush()

        return inserted
