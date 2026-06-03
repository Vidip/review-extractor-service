from __future__ import annotations

import argparse
import inspect
from collections.abc import Generator

import src.config  # noqa: F401 — load .env before Langfuse prompt fetch

import gradio as gr
from openai import OpenAI

from src.chat.guardrails import (
    BLOCKED_JAILBREAK,
    BLOCKED_OFF_TOPIC,
    Intent,
    classify_intent,
    detect_prompt_injection,
)
from src.chat.retrieval import RetrievedReview, search_reviews_by_embedding
from src.config import get_settings
from src.db.session import get_session_factory
from src.observability.prompts import (
    get_chat_app_system_prompt,
    get_chat_greeting_system,
    get_chat_grounding_rules,
    get_chat_security_rules,
)
from src.rag.embed import embed_texts

DEFAULT_TOP_K = 8

Message = dict[str, str]

BLACK_THEME = (
    gr.themes.Monochrome()
    .set(
        body_background_fill="#000000",
        background_fill_primary="#000000",
        background_fill_secondary="#0a0a0a",
        block_background_fill="#141414",
        input_background_fill="#1f1f1f",
        body_text_color="#f5f5f5",
        block_title_text_color="#ffffff",
        block_label_text_color="#e5e5e5",
        border_color_primary="#2a2a2a",
        button_primary_background_fill="#2a2a2a",
        button_primary_background_fill_hover="#3a3a3a",
        button_primary_text_color="#ffffff",
        color_accent_soft="#f0f0f0",
        color_accent_soft_dark="#f0f0f0",
        body_background_fill_dark="#000000",
        background_fill_primary_dark="#000000",
        background_fill_secondary_dark="#0a0a0a",
        block_background_fill_dark="#141414",
        input_background_fill_dark="#1f1f1f",
    )
)

# User bubbles use --color-accent-soft; body text is light, so force dark text there.
CHAT_CSS = """
.message-wrap .flex-wrap.user,
.message-wrap .flex-wrap.user :where(p, span, div, li, a, strong, em) {
    color: #000000 !important;
}
.message-wrap .flex-wrap.user :where(pre, code) {
    color: #111111 !important;
}
"""


def _format_retrieved_reviews(reviews: list[RetrievedReview]) -> str:
    if not reviews:
        return "No relevant reviews found in the database."

    blocks: list[str] = []
    for i, r in enumerate(reviews, start=1):
        parts: list[str] = []
        if r.rating:
            parts.append(f"rating={r.rating}/5")
        if r.review_date:
            parts.append(f"date={r.review_date}")
        if r.author_job_title:
            parts.append(f"job_title={r.author_job_title}")
        meta = ", ".join(parts)
        header = f"[Review {i} | id={r.id}{' | ' + meta if meta else ''}]"

        body_lines: list[str] = []
        if r.title:
            body_lines.append(f"Title: {r.title}")
        if r.pros:
            body_lines.append(f"Pros: {r.pros}")
        if r.cons:
            body_lines.append(f"Cons: {r.cons}")
        if r.review:
            body_lines.append(f"Review: {r.review}")

        blocks.append(header + "\n" + "\n".join(body_lines))

    return "\n\n---\n\n".join(blocks)


def build_messages(
    history: list[Message],
    user_message: str,
    retrieved_context: str,
) -> list[Message]:
    messages: list[Message] = [
        {"role": "system", "content": get_chat_app_system_prompt()},
        {"role": "system", "content": get_chat_security_rules()},
        {"role": "system", "content": get_chat_grounding_rules()},
        {
            "role": "system",
            "content": "Review excerpts for this message:\n\n" + retrieved_context,
        },
    ]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    return messages


def build_direct_messages(history: list[Message], user_message: str) -> list[Message]:
    messages: list[Message] = [
        {"role": "system", "content": get_chat_app_system_prompt()},
        {"role": "system", "content": get_chat_security_rules()},
        {"role": "system", "content": get_chat_greeting_system()},
    ]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    return messages


def _stream_openai(
    client: OpenAI,
    messages: list[Message],
    model: str,
    *,
    temperature: float = 0.2,
) -> Generator[str, None, None]:
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        temperature=temperature,
    )
    accumulated = ""
    for event in stream:
        delta = event.choices[0].delta.content or ""
        if not delta:
            continue
        accumulated += delta
        yield accumulated


def _yield_once(text: str) -> Generator[str, None, None]:
    yield text


def chat_stream(
    user_message: str,
    history: list[Message],
) -> Generator[str, None, None]:
    """Guardrails → route by intent → RAG or direct/blocked response."""
    settings = get_settings()
    if not settings.openai_key:
        yield "Missing `OPENAI_KEY` in your environment/.env."
        return

    client = OpenAI(api_key=settings.openai_key)

    # Layer 2: regex injection detection (before embed / classify)
    if detect_prompt_injection(user_message):
        yield from _yield_once(BLOCKED_JAILBREAK)
        return

    # Layer 1: intent classification (before RAG)
    intent = classify_intent(client, user_message, history)

    if intent == Intent.JAILBREAK:
        yield from _yield_once(BLOCKED_JAILBREAK)
        return
    if intent == Intent.OFF_TOPIC:
        yield from _yield_once(BLOCKED_OFF_TOPIC)
        return
    if intent == Intent.GREETING:
        messages = build_direct_messages(history, user_message)
        yield from _stream_openai(client, messages, settings.openai_model, temperature=0.7)
        return

    # PRODUCT_REVIEW and CATALOG → RAG (Layer 3 rules included in build_messages)
    query_vecs = embed_texts(client, [user_message], model=settings.embedding_model)
    query_vec = query_vecs[0] if query_vecs else None
    if not query_vec:
        yield "Failed to compute query embedding."
        return

    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        retrieved = search_reviews_by_embedding(session, query_vec, k=DEFAULT_TOP_K)

    context = _format_retrieved_reviews(retrieved)
    messages = build_messages(history, user_message, context)
    yield from _stream_openai(client, messages, settings.openai_model)


def _component_accepts(component: type, param: str) -> bool:
    return param in inspect.signature(component.__init__).parameters


def build_ui() -> gr.ChatInterface:
    # ChatInterface sets message format; older Gradio builds reject `type` on Chatbot.
    chatbot_kwargs: dict = {"height": 560, "show_label": False}
    if _component_accepts(gr.Chatbot, "type"):
        chatbot_kwargs["type"] = "messages"

    interface_kwargs: dict = {
        "fn": chat_stream,
        "theme": BLACK_THEME,
        "css": CHAT_CSS,
        "title": "Product Review Chat",
        "description": "Answers are grounded in similar reviews retrieved via vector search (pgvector).",
        "chatbot": gr.Chatbot(**chatbot_kwargs),
        "textbox": gr.Textbox(
            placeholder="Ask about product reviews...",
            show_label=False,
            lines=1,
            max_lines=4,
            scale=7,
        ),
        "submit_btn": "Send",
        "stop_btn": None,
        "retry_btn": None,
        "undo_btn": None,
        "clear_btn": None,
        "fill_height": True,
    }
    if _component_accepts(gr.ChatInterface, "type"):
        interface_kwargs["type"] = "messages"

    return gr.ChatInterface(**interface_kwargs)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capterra reviews chat UI")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Server port (default: GRADIO_PORT env or 7860)",
    )
    return parser.parse_args()


def _skip_gradio_localhost_check(settings) -> bool:
    """ECS/Docker often cannot pass Gradio's localhost HEAD probe (proxies, bind 0.0.0.0)."""
    if settings.gradio_skip_localhost_check:
        return True
    return settings.gradio_server_name in ("0.0.0.0", "::")


def main(port: int | None = None) -> None:
    settings = get_settings()
    server_port = port if port is not None else settings.gradio_port
    demo = build_ui()
    demo.queue(default_concurrency_limit=16).launch(
        server_name=settings.gradio_server_name,
        server_port=server_port,
        share=False,
        inbrowser=False,
        quiet=True,
        # When False, Gradio skips the localhost accessibility check that fails in ECS.
        _frontend=not _skip_gradio_localhost_check(settings),
    )


def cli() -> None:
    """Console entry point (e.g. `capterra-chat-ui --port 7861`)."""
    main(port=parse_args().port)


if __name__ == "__main__":
    cli()
