#!/usr/bin/env python3
"""Upload Capterra extraction prompts to Langfuse (run once per environment)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.config  # noqa: F401 — load .env before Langfuse

from src.observability.langfuse_tracing import is_tracing_enabled
from src.observability.prompts import (
    CHAT_APP_SYSTEM_PROMPT_FALLBACK,
    CHAT_APP_SYSTEM_PROMPT_NAME,
    CHAT_GREETING_SYSTEM_FALLBACK,
    CHAT_GREETING_SYSTEM_NAME,
    CHAT_GROUNDING_RULES_FALLBACK,
    CHAT_GROUNDING_RULES_NAME,
    CHAT_SECURITY_RULES_FALLBACK,
    CHAT_SECURITY_RULES_NAME,
    EXTRACT_REVIEWS_FALLBACK,
    EXTRACT_REVIEWS_PROMPT_NAME,
    EXTRACT_TOTAL_PAGES_FALLBACK,
    EXTRACT_TOTAL_PAGES_PROMPT_NAME,
    PROMPT_LABEL,
)


def main() -> int:
    if not is_tracing_enabled():
        print(
            "Error: set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in .env",
            file=sys.stderr,
        )
        return 1

    from langfuse import get_client

    client = get_client()

    reviews = client.create_prompt(
        name=EXTRACT_REVIEWS_PROMPT_NAME,
        prompt=EXTRACT_REVIEWS_FALLBACK,
        type="text",
        labels=[PROMPT_LABEL],
        commit_message="Initial Capterra review extraction prompt",
    )
    print(f"Created {EXTRACT_REVIEWS_PROMPT_NAME} v{reviews.version} (label={PROMPT_LABEL})")

    pagination = client.create_prompt(
        name=EXTRACT_TOTAL_PAGES_PROMPT_NAME,
        prompt=EXTRACT_TOTAL_PAGES_FALLBACK,
        type="text",
        labels=[PROMPT_LABEL],
        commit_message="Initial Capterra pagination detection prompt",
    )
    print(f"Created {EXTRACT_TOTAL_PAGES_PROMPT_NAME} v{pagination.version} (label={PROMPT_LABEL})")

    chat_prompts = [
        (CHAT_APP_SYSTEM_PROMPT_NAME, CHAT_APP_SYSTEM_PROMPT_FALLBACK, "Chat app system prompt"),
        (CHAT_GROUNDING_RULES_NAME, CHAT_GROUNDING_RULES_FALLBACK, "Chat grounding rules"),
        (CHAT_SECURITY_RULES_NAME, CHAT_SECURITY_RULES_FALLBACK, "Chat security rules"),
        (CHAT_GREETING_SYSTEM_NAME, CHAT_GREETING_SYSTEM_FALLBACK, "Chat greeting system prompt"),
    ]
    for name, text, commit_message in chat_prompts:
        created = client.create_prompt(
            name=name,
            prompt=text,
            type="text",
            labels=[PROMPT_LABEL],
            commit_message=commit_message,
        )
        print(f"Created {name} v{created.version} (label={PROMPT_LABEL})")

    client.flush()
    print("Done. Re-run only when prompt text changes (creates a new version).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
