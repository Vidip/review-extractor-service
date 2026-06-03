"""Tests for Langfuse prompt compilation fallbacks."""

from unittest.mock import patch

from src.observability.prompts import (
    compile_extract_reviews_prompt,
    compile_extract_total_pages_prompt,
    get_chat_app_system_prompt,
    get_chat_grounding_rules,
    get_chat_greeting_system,
    get_chat_security_rules,
)


def test_compile_extract_reviews_prompt_substitutes_content():
    with patch("src.observability.prompts.is_tracing_enabled", return_value=False):
        compiled, prompt_client = compile_extract_reviews_prompt("Sample review page text")
    assert prompt_client is None
    assert "Sample review page text" in compiled
    assert "Extract every user review" in compiled


def test_compile_extract_total_pages_prompt_substitutes_content():
    with patch("src.observability.prompts.is_tracing_enabled", return_value=False):
        compiled, prompt_client = compile_extract_total_pages_prompt("Page 1 of 5")
    assert prompt_client is None
    assert "Page 1 of 5" in compiled
    assert "totalPages" in compiled


def test_chat_prompts_use_fallback_when_tracing_disabled():
    with patch("src.observability.prompts.is_tracing_enabled", return_value=False):
        assert "product review assistant" in get_chat_app_system_prompt()
        assert "CITE every factual claim" in get_chat_grounding_rules()
        assert "SECURITY RULES" in get_chat_security_rules()
        assert "brief social message" in get_chat_greeting_system()
