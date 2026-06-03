"""Synchronous product crawl (API, ECS, local scripts)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from langfuse import observe
from src.crawl.job import CrawlPageJob
from src.crawl.jobs import process_crawl_page
from src.db.models import SyncRun
from src.db.repository import ProductRepository, SyncRunRepository
from src.extractor.urls import normalize_capterra_url
from src.observability.langfuse_tracing import update_trace_context

logger = logging.getLogger(__name__)


@dataclass
class CrawlRunResult:
    product_id: uuid.UUID
    sync_run_id: uuid.UUID
    reviews_url: str
    pages_crawled: int
    new_reviews: int
    total_pages: int


@observe(name="product-crawl", capture_input=False)
def run_product_crawl(
    session: Session,
    product_id: uuid.UUID,
    url: str,
    sync_run_id: uuid.UUID,
    settings: Settings | None = None,
    max_pages: int = 1,
) -> CrawlRunResult:
    """Crawl review pages synchronously.

    After page 1, ``total_pages`` from pagination drives the loop (1 .. total_pages).
    Stops early if a stored review hash is seen (newest-first), so re-syncs only
    fetch new head reviews.
    """
    settings = settings or get_settings()
    reviews_url = normalize_capterra_url(url)

    update_trace_context(
        session_id=str(sync_run_id),
        metadata={
            "product_id": str(product_id),
            "capterra_url": reviews_url,
            "max_pages": max_pages,
        },
        tags=["capterra-crawl"],
    )

    products = ProductRepository(session)
    sync_runs = SyncRunRepository(session)

    page = 1
    pages_crawled = 0
    new_reviews = 0
    total_pages: int | None = None

    try:
        while True:
            job = CrawlPageJob.create(product_id, reviews_url, page, sync_run_id)
            logger.info("Crawling product %s page %s", product_id, page)

            result = process_crawl_page(session, job, settings)
            pages_crawled += 1
            new_reviews += result.new_reviews

            if total_pages is None:
                detected = result.total_pages
                total_pages = min(detected, max_pages) if max_pages is not None else detected
                logger.info(
                    "Pagination: %s total page(s)%s",
                    total_pages,
                    f" (capped from {detected})" if max_pages is not None and detected > max_pages else "",
                )

            if result.hit_duplicate:
                logger.info("Stopping crawl: existing review found on page %s", page)
                break

            if page >= total_pages:
                break

            page += 1

        run = session.get(SyncRun, sync_run_id)
        product = products.get_by_id(product_id)
        if run and product:
            sync_runs.complete(run, run.pages_crawled, run.new_reviews)
            products.mark_ready(product)
        session.commit()
    except Exception as exc:
        job = CrawlPageJob.create(product_id, reviews_url, page, sync_run_id)
        _mark_failure(session, job, str(exc))
        session.commit()
        raise

    assert total_pages is not None
    update_trace_context(
        output={
            "pages_crawled": pages_crawled,
            "new_reviews": new_reviews,
            "total_pages": total_pages,
        }
    )
    return CrawlRunResult(
        product_id=product_id,
        sync_run_id=sync_run_id,
        reviews_url=reviews_url,
        pages_crawled=pages_crawled,
        new_reviews=new_reviews,
        total_pages=total_pages,
    )


def _mark_failure(session: Session, job: CrawlPageJob, error: str) -> None:
    products = ProductRepository(session)
    sync_runs = SyncRunRepository(session)

    product = products.get_by_id(uuid.UUID(job.product_id))
    if product:
        products.mark_error(product)

    run = session.get(SyncRun, uuid.UUID(job.sync_run_id))
    if run:
        sync_runs.fail(run, error)
