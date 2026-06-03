"""Fetch Capterra review pages via Firecrawl and fallback strategies."""

from typing import List, Optional

import httpx

from src.config import get_settings  # noqa: F401 — ensure .env loaded before Langfuse
from langfuse import observe

from src.observability.langfuse_tracing import update_span_context

# TODO: remove — temporary stub HTML while testing Langfuse integration
_MOCK_FIRECRAWL_HTML = """<!DOCTYPE html>
<html>
<body>
<div class="reviews">
  <article class="review">
    <h3>Great scheduling tool</h3>
    <span class="rating">5</span>
    <span class="author">Jane Doe</span>
    <span class="job-title">Operations Manager</span>
    <span class="date">January 15, 2024</span>
    <p class="review-text">Easy to use and reliable for our team.</p>
    <p class="pros">Simple UI, good mobile app</p>
    <p class="cons">Pricing could be lower</p>
  </article>
  <article class="review">
    <h3>Solid for hourly staff</h3>
    <span class="rating">4</span>
    <span class="author">John Smith</span>
    <span class="job-title">Store Manager</span>
    <span class="date">February 2, 2024</span>
    <p class="review-text">Helps us manage shifts without spreadsheets.</p>
    <p class="pros">Shift swaps, notifications</p>
    <p class="cons">Learning curve for new hires</p>
  </article>
</div>
<nav class="pagination"><span>Page 1 of 1</span></nav>
</body>
</html>"""


def fetch_with_firecrawl(url: str, api_key: str, timeout: float = 60.0) -> str:
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"url": url, "formats": ["html"], "onlyMainContent": False},
        )
        response.raise_for_status()
        data = response.json()

    html = (data.get("data") or {}).get("html")
    if not html:
        raise httpx.HTTPError(f"Firecrawl returned no HTML: {data}")
    return html


@observe(name="fetch-page", capture_input=False)
def fetch_page(
    url: str,
    timeout: float = 30.0,
    firecrawl_key: Optional[str] = None,
) -> str:
    """Fetch HTML for a reviews page URL."""
    update_span_context(input={"url": url})

    # TODO: remove — mock Firecrawl response for Langfuse testing
    html = _MOCK_FIRECRAWL_HTML
    update_span_context(output={"strategy": "firecrawl-mock", "html_bytes": len(html)})
    return html

    # errors: List[str] = []
    #
    # if firecrawl_key:
    #     try:
    #         html = fetch_with_firecrawl(url, firecrawl_key, timeout=max(timeout, 60))
    #         update_span_context(output={"strategy": "firecrawl", "html_bytes": len(html)})
    #         return html
    #     except Exception as exc:  # noqa: BLE001
    #         errors.append(f"firecrawl: {exc}")
    #
    # raise httpx.HTTPError(
    #     "All fetch strategies failed.\n"
    #     + "\n".join(errors)
    # )
