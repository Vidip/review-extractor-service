"""Process one Capterra reviews page: fetch, extract, embed, store."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from langfuse import observe
from src.db.models import SyncRun
from src.db.repository import ProductRepository, ReviewRepository, SyncRunRepository
from src.extractor.fetch import fetch_page
from src.extractor.hash import hash_review
from src.extractor.parse import (
    clean_html_for_llm,
    extract_reviews_with_openai,
    extract_total_pages,
    extract_total_pages_with_openai,
)
from src.crawl.job import CrawlPageJob
from src.extractor.urls import build_reviews_page_url
from src.observability.langfuse_tracing import (
    create_openai_client,
    update_span_context,
    update_trace_context,
)
from src.rag.embed import embed_reviews

logger = logging.getLogger(__name__)


class CrawlPageResult:
    def __init__(
        self,
        product_id: uuid.UUID,
        page: int,
        new_reviews: int,
        total_pages: int,
        hit_duplicate: bool,
    ):
        self.product_id = product_id
        self.page = page
        self.new_reviews = new_reviews
        self.total_pages = total_pages
        self.hit_duplicate = hit_duplicate


def _resolve_total_pages(html: str, page_text: str, client, model: str) -> int:
    total = extract_total_pages(html)
    if total is not None:
        return total
    return extract_total_pages_with_openai(page_text, client, model)


def reviews_until_duplicate(reviews: list[dict], existing_hashes: set[str]) -> tuple[list[dict], bool]:
    """Walk newest-first reviews; stop at the first hash already stored for this product."""
    new_reviews: list[dict] = []
    for review in reviews:
        if hash_review(review) in existing_hashes:
            return new_reviews, True
        new_reviews.append(review)
    return new_reviews, False


@observe(name="crawl-page", capture_input=False)
def process_crawl_page(session: Session, job: CrawlPageJob, settings: Settings | None = None) -> CrawlPageResult:
    """Fetch and persist one reviews page. Pagination total is read on page 1 only."""
    settings = settings or get_settings()
    if not settings.openai_key:
        raise ValueError("OPENAI_KEY is required")

    product_id = uuid.UUID(job.product_id)
    sync_run_id = uuid.UUID(job.sync_run_id)

    page_url = build_reviews_page_url(job.capterra_url, job.page)
    update_trace_context(
        session_id=str(sync_run_id),
        metadata={
            "product_id": str(product_id),
            "page": job.page,
            "page_url": page_url,
        },
        tags=["capterra-crawl", "crawl-page"],
    )
    update_span_context(input={"page_url": page_url, "page": job.page})

    products = ProductRepository(session)
    reviews_repo = ReviewRepository(session)
    sync_runs = SyncRunRepository(session)

    product = products.get_by_id(product_id)
    if not product:
        raise ValueError(f"Product not found: {product_id}")

    run = session.get(SyncRun, sync_run_id)
    if not run:
        raise ValueError(f"Sync run not found: {sync_run_id}")

    products.mark_syncing(product)

    logger.info("Crawling %s (page %s)", page_url, job.page)

    html = fetch_page(
        page_url,
        timeout=settings.fetch_timeout,
        firecrawl_key=settings.firecrawl_api_key or None,
        session=session,
    )

    page_text = clean_html_for_llm(html)
    client = create_openai_client(settings.openai_key)

    extracted = extract_reviews_with_openai(page_text, client, settings.openai_model)
    if job.page == 1:
        total_pages = _resolve_total_pages(html, page_text, client, settings.openai_model)
        products.update_pagination(product, total_pages)
    else:
        total_pages = product.pagination_total_pages or 1

    page_hashes = [hash_review(review) for review in extracted]
    existing_hashes = reviews_repo.existing_hashes(product_id, page_hashes)
    new_reviews_raw, hit_duplicate = reviews_until_duplicate(extracted, existing_hashes)
    if hit_duplicate:
        logger.info("Hit existing review on page %s; stopping after %s new review(s)", job.page, len(new_reviews_raw))

    product_name = product.name or product.slug or "Unknown Product"
    embedded = embed_reviews(client, product_name, new_reviews_raw, settings.embedding_model)
    new_count = reviews_repo.insert_batch(product, embedded)

    run.pages_crawled += 1
    run.new_reviews += new_count
    session.flush()

    update_span_context(
        output={
            "new_reviews": new_count,
            "extracted_count": len(extracted),
            "hit_duplicate": hit_duplicate,
            "total_pages": total_pages,
        }
    )

    return CrawlPageResult(
        product_id=product_id,
        page=job.page,
        new_reviews=new_count,
        total_pages=total_pages,
        hit_duplicate=hit_duplicate,
    )
