"""Langfuse tracing helpers (OpenAI integration + trace context)."""

from __future__ import annotations

import os
import logging
from typing import Any, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


def _ensure_langfuse_env() -> None:
    """Ensure Langfuse SDK env vars are present before get_client() runs."""
    from src.config import get_settings

    settings = get_settings()

    if settings.langfuse_public_key:
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
    if settings.langfuse_secret_key:
        os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key

    host = settings.langfuse_host or settings.langfuse_base_url
    if not host:
        host = os.environ.get("LANGFUSE_HOST") or os.environ.get("LANGFUSE_BASE_URL")
    if host:
        os.environ["LANGFUSE_HOST"] = host.rstrip("/")


def get_langfuse_client():
    """Return Langfuse client after env (especially LANGFUSE_HOST) is configured."""
    _ensure_langfuse_env()
    from langfuse import get_client

    return get_client()


def is_tracing_enabled() -> bool:
    _ensure_langfuse_env()
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))


def create_openai_client(api_key: str) -> OpenAI:
    """Return an OpenAI client; uses Langfuse drop-in when tracing is configured."""
    if is_tracing_enabled():
        try:
            from langfuse.openai import OpenAI as LangfuseOpenAI

            return LangfuseOpenAI(api_key=api_key)
        except Exception:
            # Langfuse OpenAI integration can be version-sensitive; never break crawls.
            logger.debug("Langfuse OpenAI wrapper unavailable; falling back to OpenAI", exc_info=True)
    return OpenAI(api_key=api_key)


def flush_traces() -> None:
    if not is_tracing_enabled():
        return
    get_langfuse_client().flush()


def update_trace_context(
    *,
    session_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    tags: Optional[list[str]] = None,
    output: Optional[Any] = None,
) -> None:
    if not is_tracing_enabled():
        return
    # Langfuse SDK API differs across versions. Prefer context-based updates when
    # running inside an @observe-decorated call; fall back to client if present.
    try:
        from langfuse.decorators import langfuse_context

        if hasattr(langfuse_context, "update_current_trace"):
            langfuse_context.update_current_trace(
                session_id=session_id,
                metadata=metadata,
                tags=tags,
                output=output,
            )
            return
    except Exception:
        # Tracing must never break application behavior.
        logger.debug("Langfuse trace context update via langfuse_context failed", exc_info=True)

    try:
        client = get_langfuse_client()
        if hasattr(client, "update_current_trace"):
            client.update_current_trace(
                session_id=session_id,
                metadata=metadata,
                tags=tags,
                output=output,
            )
    except Exception:
        logger.debug("Langfuse trace context update via client failed", exc_info=True)


def update_span_context(
    *,
    input: Optional[Any] = None,
    output: Optional[Any] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    if not is_tracing_enabled():
        return
    try:
        from langfuse.decorators import langfuse_context

        # Some versions expose span updates on the context, others call it "observation".
        if hasattr(langfuse_context, "update_current_span"):
            langfuse_context.update_current_span(input=input, output=output, metadata=metadata)
            return
        if hasattr(langfuse_context, "update_current_observation"):
            langfuse_context.update_current_observation(input=input, output=output, metadata=metadata)
            return
    except Exception:
        logger.debug("Langfuse span context update via langfuse_context failed", exc_info=True)

    try:
        client = get_langfuse_client()
        if hasattr(client, "update_current_span"):
            client.update_current_span(input=input, output=output, metadata=metadata)
    except Exception:
        logger.debug("Langfuse span context update via client failed", exc_info=True)
