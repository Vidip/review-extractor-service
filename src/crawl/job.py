"""In-process crawl job parameters (one reviews page)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass
class CrawlPageJob:
    product_id: str
    capterra_url: str
    page: int
    sync_run_id: str

    @classmethod
    def create(
        cls,
        product_id: uuid.UUID,
        capterra_url: str,
        page: int,
        sync_run_id: uuid.UUID,
    ) -> CrawlPageJob:
        return cls(
            product_id=str(product_id),
            capterra_url=capterra_url,
            page=page,
            sync_run_id=str(sync_run_id),
        )
