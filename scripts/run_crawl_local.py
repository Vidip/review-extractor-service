#!/usr/bin/env python3
"""Run Path A crawl locally (same synchronous flow as the API)."""

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.config  # noqa: F401 — load .env before Langfuse

from src.config import get_settings
from src.observability.langfuse_tracing import flush_traces
from src.crawl.handler import run_product_crawl
from src.db.repository import ProductRepository, SyncRunRepository
from src.db.models import SyncMode
from src.db.session import get_session_factory

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run crawl pipeline locally (Path A)")
    parser.add_argument("url", help="Capterra product or reviews URL")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Optional safety cap applied after pagination is read from page 1",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.openai_key:
        print("Error: OPENAI_KEY not set in .env", file=sys.stderr)
        return 1
    if not settings.firecrawl_api_key:
        print("Warning: FIRECRAWL_API_KEY not set; fetch may fail against Cloudflare.", file=sys.stderr)

    session_factory = get_session_factory()
    session = session_factory()

    try:
        products = ProductRepository(session)
        sync_runs = SyncRunRepository(session)

        product = products.create_or_get(args.url)
        sync_mode = SyncMode.INCREMENTAL if product.known_review_count > 0 else SyncMode.FULL
        run = sync_runs.start(product.id, sync_mode)
        products.mark_syncing(product)
        session.commit()

        crawl = run_product_crawl(
            session,
            product.id,
            args.url,
            run.id,
            settings=settings,
            max_pages=args.max_pages,
        )
        session.commit()

        session.refresh(product)
        print(
            f"Product {product.id} status={product.sync_status.value} "
            f"reviews={product.known_review_count} "
            f"pages={crawl.pages_crawled}/{crawl.total_pages} new={crawl.new_reviews}"
        )
        return 0
    except Exception as exc:
        session.rollback()
        logger.exception("Crawl failed")
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()
        flush_traces()


if __name__ == "__main__":
    raise SystemExit(main())
