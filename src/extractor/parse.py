"""Parse Capterra HTML and extract structured reviews via OpenAI."""

import json
import re
from typing import Dict, List, Optional, Set

from bs4 import BeautifulSoup
from openai import OpenAI

from src.observability.prompts import (
    compile_extract_reviews_prompt,
    compile_extract_total_pages_prompt,
)

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "reviews": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "reviewDate": {"type": "string"},
                    "reviewPros": {"type": "string"},
                    "reviewCons": {"type": "string"},
                    "emotion": {"type": "string"},
                    "rating": {"type": "string"},
                    "review": {"type": "string"},
                    "reviewTitle": {"type": "string"},
                    "reviewAuthor": {"type": "string"},
                    "reviewAuthorJobTitle": {"type": "string"},
                },
                "required": ["reviewDate", "reviewPros", "reviewCons", "emotion", "rating", "review", "reviewTitle", "reviewAuthor", "reviewAuthorJobTitle"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["reviews"],
    "additionalProperties": False,
}


def clean_html_for_llm(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def extract_total_pages(html: str) -> Optional[int]:
    soup = BeautifulSoup(html, "html.parser")
    page_numbers: Set[int] = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        match = re.search(r"[?&]page=(\d+)", href)
        if match:
            page_numbers.add(int(match.group(1)))
        match = re.search(r"/reviews/(\d+)/?", href)
        if match:
            page_numbers.add(int(match.group(1)))

    for element in soup.find_all(string=re.compile(r"page\s+\d+\s+of\s+\d+", re.I)):
        match = re.search(r"page\s+(\d+)\s+of\s+(\d+)", str(element), re.I)
        if match:
            page_numbers.add(int(match.group(2)))

    for element in soup.find_all(["span", "div", "p", "button", "a"]):
        text = element.get_text(strip=True)
        if text.isdigit() and 1 <= int(text) <= 500:
            parent_text = element.parent.get_text(" ", strip=True) if element.parent else ""
            if re.search(r"page|pagination|next|prev", parent_text, re.I):
                page_numbers.add(int(text))

    return max(page_numbers) if page_numbers else None


def extract_reviews_with_openai(page_text: str, client: OpenAI, model: str) -> List[Dict]:
    prompt, langfuse_prompt = compile_extract_reviews_prompt(page_text)

    request_kwargs: dict = {
        "model": model,
        "input": prompt,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "capterra_reviews",
                "schema": REVIEW_SCHEMA,
                "strict": True,
            }
        },
    }
    if langfuse_prompt is not None:
        request_kwargs["langfuse_prompt"] = langfuse_prompt

    response = client.responses.create(**request_kwargs)

    payload = json.loads(response.output_text)
    return payload["reviews"]


def extract_total_pages_with_openai(page_text: str, client: OpenAI, model: str) -> int:
    prompt, langfuse_prompt = compile_extract_total_pages_prompt(page_text)

    request_kwargs: dict = {
        "model": model,
        "input": prompt,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "pagination_info",
                "schema": {
                    "type": "object",
                    "properties": {"totalPages": {"type": "integer"}},
                    "required": ["totalPages"],
                    "additionalProperties": False,
                },
                "strict": True,
            }
        },
    }
    if langfuse_prompt is not None:
        request_kwargs["langfuse_prompt"] = langfuse_prompt

    response = client.responses.create(**request_kwargs)

    payload = json.loads(response.output_text)
    return max(1, int(payload["totalPages"]))
