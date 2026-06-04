"""Capterra URL helpers."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def normalize_capterra_url(url: str) -> str:
    """Ensure URL points at the reviews listing (page 1, no query params).

    Supported inputs (all normalize to ``.../p/{id}/{slug}/reviews/``):
    - .../p/121248/When-I-Work/
    - .../p/121248/When-I-Work/#reviews
    - .../p/121248/When-I-Work/reviews/  (query params stripped)
    """
    parsed = urlparse(url.strip())
    path = parsed.path.rstrip("/")
    if not path.endswith("/reviews"):
        if "/reviews/" in path:
            path = path.split("/reviews/")[0] + "/reviews"
        else:
            path = path + "/reviews"
    return urlunparse((parsed.scheme, parsed.netloc, path + "/", "", "", ""))


def extract_slug_from_url(url: str) -> str | None:
    match = re.search(r"/p/\d+/([^/]+)/", url)
    return match.group(1) if match else None


def extract_product_name_from_url(url: str) -> str:
    """Derive product name from the Capterra URL slug (e.g. When-I-Work)."""
    return extract_slug_from_url(url) or "Unknown Product"


def build_reviews_page_url(base_url: str, page: int) -> str:
    """Build paginated Capterra reviews URL."""
    normalized = normalize_capterra_url(base_url)
    if page <= 1:
        return normalized

    parsed = urlparse(normalized)
    query = parse_qs(parsed.query)
    query["page"] = [str(page)]
    new_query = urlencode(query, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
