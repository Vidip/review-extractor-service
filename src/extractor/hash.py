"""Content hashing for review deduplication."""

import hashlib
from typing import Any, Dict


def hash_review(review: Dict[str, Any]) -> str:
    """Stable hash from review fields for dedup within a product."""
    parts = [
        str(review.get("reviewDate", "")).strip().lower(),
        str(review.get("reviewPros", "")).strip().lower(),
        str(review.get("reviewCons", "")).strip().lower(),
        str(review.get("rating", "")).strip().lower(),
    ]
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
