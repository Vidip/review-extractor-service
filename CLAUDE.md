# CLAUDE.md

Guidance for Claude Code working on **capterra-review-extractor**. Read this before making changes.

> Kept in sync with [AGENTS.md](AGENTS.md). Update both when project conventions change.

## What this project is

A Python pipeline that:

1. **Ingests** Capterra product review pages (fetch HTML → OpenAI structured extraction → embeddings → PostgreSQL/pgvector)
2. **Serves** a FastAPI endpoint to trigger synchronous crawls
3. **Powers** a Gradio chat UI that answers questions via RAG over stored reviews

This is a **sample / development / learning project** — not for production or commercial use. Automated scraping of Capterra may violate [Capterra Terms of Use](https://www.capterra.com/legal/terms-of-use/). Do not build features aimed at large-scale production crawling without licensed data sources.

## Tech stack

| Layer | Choice |
|-------|--------|
| Language | Python ≥ 3.9 (Docker images use 3.11) |
| Web API | FastAPI + uvicorn |
| Chat UI | Gradio 4.x |
| Database | PostgreSQL 16 + pgvector |
| ORM / migrations | SQLAlchemy 2.x + Alembic |
| LLM | OpenAI (`gpt-4o-mini` default, `text-embedding-3-small` default) |
| Fetch | Firecrawl API (optional; mock HTML is the current dev default) |
| Observability | Langfuse (optional — app runs without it) |
| Config | pydantic-settings + `.env` via python-dotenv |
| Tests | pytest |

## Repository layout

```
src/
  extractor/       # URL normalization, Firecrawl fetch, HTML cleanup, OpenAI parse, content hashing
  crawl/           # Synchronous crawl orchestration (handler) + per-page processor (jobs)
  db/              # SQLAlchemy models, repositories, session factory
  rag/             # Embedding generation + vector retrieval helpers
  api/              # FastAPI app and /products routes
  chat/            # Gradio UI, ChatService (RAG streaming), guardrails, prompt templates
  observability/   # Langfuse tracing helpers + prompt management (Langfuse + fallbacks)
scripts/
  run_crawl_local.py          # CLI crawl (same flow as API)
  sync_langfuse_prompts.py    # Upload prompts to Langfuse
  push-ecr.sh / push-ecr-gradio.sh
tests/               # Unit tests (no live DB/OpenAI required for most)
fixtures/            # Sample HTML for local testing
alembic/             # DB migrations
.claude/agents/      # Claude Code subagents (api-tester, extraction-reviewer)
```

Import paths use the `src.` package prefix (e.g. `from src.config import get_settings`).

## Setup (local dev)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Set OPENAI_KEY (required). FIRECRAWL_API_KEY optional while mock fetch is active.

docker compose up -d          # PostgreSQL + pgvector on :5432
alembic upgrade head
pytest
```

**Required env:** `OPENAI_KEY`, `DATABASE_URL`, `FIRECRAWL_API_KEY`, `LANGFUSE_*`, `OPENAI_MODEL`, `EMBEDDING_MODEL`, `GRADIO_PORT`, `CORS_ORIGINS`. See `.env.example`.

Never commit `.env`, cookies, or API keys.

## Architecture (data flow)

```
Capterra URL
  → normalize URL (append /reviews/)
  → fetch HTML (Firecrawl or mock)
  → clean HTML → OpenAI extract reviews (JSON schema)
  → dedupe by content hash (newest-first, stop at first duplicate)
  → embed new reviews → insert into PostgreSQL (pgvector)

Chat query
  → input guardrails (injection detection, intent classification)
  → embed query → pgvector similarity search (top-k)
  → build RAG system prompt with review excerpts
  → stream OpenAI chat completion
```

Crawls are **synchronous** in the API request path. There is no job queue yet (README describes a future Lambda/SQS ideal architecture).

### Crawl pagination & incremental sync

- Reviews on each page are processed **newest-first**.
- Each review gets a stable `content_hash` from key fields (`hash_review`).
- On re-sync, paging stops at the **first hash already in DB** for that product — only new head reviews are fetched.
- Page 1 determines `pagination_total_pages` (HTML heuristics first, OpenAI fallback).

### Important defaults and gotchas

1. **Mock fetch is active.** `src/extractor/fetch.py` returns fixed mock HTML after `crawl_count >= 2` (tracked in the `crawl` table singleton). This lets you test extraction, embeddings, DB, and Langfuse without hitting Capterra/Firecrawl. To restore live fetching, adjust `fetch_page` accordingly. Sample HTML also lives in `fixtures/sample_reviews.html`.

2. **API crawl page cap.** `run_product_crawl()` defaults to `max_pages=1`. The FastAPI `POST /products` route does not override this, so the API only crawls one page unless you change the call site. The local script `scripts/run_crawl_local.py` passes `max_pages=None` (uncapped after pagination detection).

3. **Langfuse env ordering.** `src/config.py` must load before any Langfuse import. It maps `LANGFUSE_BASE_URL` → `LANGFUSE_HOST`. FastAPI lifespan and crawl entrypoints call `_ensure_langfuse_env()` early. Restart the server after changing Langfuse env vars.

4. **Tracing must never break the app.** Langfuse helpers in `src/observability/langfuse_tracing.py` swallow errors and fall back to plain OpenAI. Keep this pattern when adding observability.

5. **`sync_langfuse_prompts.py` imports chat prompt constants** that may not all exist in `src/observability/prompts.py` after refactors. Chat currently uses local templates in `src/chat/prompts.py`. When adding Langfuse-managed chat prompts, keep constants, fallbacks, and the sync script in sync.

## Running services

```bash
# API (port 8000)
uvicorn src.api.main:app --reload --port 8000

# Trigger crawl
curl -X POST http://localhost:8000/products \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.capterra.com/p/121248/When-I-Work/reviews/"}'

# Gradio chat (port 7860)
capterra-chat-ui
# or: python scripts/run_chat_ui.py

# Local crawl CLI
python scripts/run_crawl_local.py "https://www.capterra.com/p/121248/When-I-Work/reviews/"
python scripts/run_crawl_local.py URL --max-pages 5   # optional cap
```

## Database model (mental model)

- **products** — one row per normalized Capterra reviews URL; tracks sync status, pagination, review count
- **reviews** — extracted review fields + `content_hash` (unique per product) + `embedding` vector
- **sync_runs** — audit trail per crawl (pages crawled, new reviews, errors)
- **crawl** — singleton row counting live Firecrawl fetches (drives mock cutoff)

Use repositories in `src/db/repository.py` for DB access — do not scatter raw SQL in feature code unless there is a strong reason.

Migrations live in `alembic/versions/`. After model changes: generate a migration, review it, then `alembic upgrade head`.

## Langfuse

When `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set:

- OpenAI calls in the crawl path use `langfuse.openai.OpenAI` via `create_openai_client()`
- Pipeline steps use `@observe` spans: `product-crawl` → `crawl-page` → `fetch-page`
- `session_id` = sync run UUID (groups pages in Langfuse Sessions)
- Prompts fetched with label **`production`**, with hardcoded fallbacks in `src/observability/prompts.py`

Extraction prompts (managed in Langfuse):

| Name | Variable |
|------|----------|
| `capterra-extract-reviews` | `{{page_content}}` |
| `capterra-extract-total-pages` | `{{page_content}}` |

Upload after prompt text changes:

```bash
python scripts/sync_langfuse_prompts.py
```

Langfuse skill/docs: `.agents/skills/langfuse/SKILL.md`

## Coding conventions (good practices for this repo)

Follow existing patterns — don't introduce new ones without reason:

- **Minimal diffs.** Do not refactor unrelated code. Match naming, imports, and module boundaries.
- **Settings:** use `get_settings()` from `src/config.py`; add new config as a pydantic `Field` with env alias. Never read `os.environ` directly in feature code.
- **Sessions:** FastAPI uses the `get_db` dependency; scripts/services use `get_session_factory()()` with try/finally close. Always close sessions; always `db.rollback()` on exception before re-raising.
- **OpenAI structured output:** extraction uses the JSON schema in `src/extractor/parse.py` (`REVIEW_SCHEMA`) — extend schema + repository mapping + Alembic migration together, never one without the others.
- **Prompts:** extraction prompts go through `compile_extract_*_prompt()` so Langfuse linking works; chat prompts currently live in `src/chat/prompts.py`. Don't hardcode prompt text inline in call sites.
- **Logging:** use `logging.getLogger(__name__)`; INFO for crawl progress, WARNING/ERROR for recoverable/unrecoverable failures. Never log secrets, full HTML payloads, or raw OpenAI request bodies.
- **Type hints:** use modern syntax (`list[str]`, `X | None`) consistent with existing files.
- **Comments:** only for non-obvious business logic (e.g. mock fetch rationale, Langfuse env ordering) — not restating what the code does.
- **Tests:** add focused unit tests under `tests/`; mock Langfuse with `patch("...is_tracing_enabled", return_value=False)` when testing prompt compilation. Prefer testing pure functions (URL normalize, hash, dedupe) over integration unless necessary.
- **Error handling:** raise/propagate real exceptions in new code (this repo is moving away from silent `except: pass`); only swallow errors where already established as intentional (Langfuse tracing, best-effort notifications).
- **No commits** unless the user explicitly asks.

## Guardrails

These are hard constraints, not suggestions — violating them is a defect even if the surrounding change "works":

1. **Compliance / scraping scope.** Never add a code path that defaults to live, uncapped, multi-page scraping of real Capterra URLs. Keep the mock-fetch dev default (`src/extractor/fetch.py`) and the `max_pages` cap intact unless a human explicitly asks to change them, and if asked, flag the ToS implication back to them first.
2. **Chat guardrails stay in front of the model.** `src/chat/guardrails.py`'s `detect_prompt_injection` / `classify_intent` must run *before* any RAG retrieval or chat completion call, and a `JAILBREAK`/`OFF_TOPIC` classification must actually short-circuit the response (not just get computed and ignored). Any change to `src/chat/gradio_app.py` or `src/chat/retrieval.py` that touches this ordering needs the `extraction-reviewer` subagent's review before it ships.
3. **Secrets never leave config.** `OPENAI_KEY`, `DATABASE_URL`, `FIRECRAWL_API_KEY`, `LANGFUSE_SECRET_KEY`, cookies — only in `.env` / ECS task env. Never in code, commits, logs, or HTTP error responses (`detail=` strings must not leak exception internals that could contain secrets).
4. **No destructive git/DB operations without asking.** No `alembic downgrade`, force-push, `git reset --hard`, or dropping tables as a shortcut to "fix" a broken migration or branch state — investigate and ask first.
5. **Extraction correctness over speed.** Don't relax the `REVIEW_SCHEMA` `required`/`additionalProperties: False` constraints or the content-hash dedupe to make a crawl "just pass" — a loosened schema silently corrupts downstream RAG data.
6. **CORS defaults.** Don't widen `CORS_ORIGINS` beyond what's already configured for an environment as a debugging shortcut.

## Subagents

Two Claude Code subagents live in `.claude/agents/` for this repo:

- **`api-tester`** — exercises the FastAPI surface (`src/api/main.py`, `src/api/routes/products.py`): status codes, response schemas, error handling, idempotency, CORS. Use after any API change or when asked to test/verify the API.
- **`extraction-reviewer`** — reviews extraction output quality (schema conformance, hallucination risk, dedupe correctness) and enforces the Guardrails section above (prompt-injection defenses, jailbreak/off-topic handling, ToS/scraping scope, secret handling). Use after any crawl run, or when touching `src/extractor/*`, `src/chat/guardrails.py`, or observability prompts.

Both subagents report findings; they do not silently patch code or commit. Route their findings back through the normal review/commit flow.

## Deployment

Two Docker images:

- `Dockerfile` — API on port 8000 → `./scripts/push-ecr.sh`
- `Dockerfile.gradio` — chat UI on port 7860 → `./scripts/push-ecr-gradio.sh`

ECS task definitions must inject `DATABASE_URL`, `OPENAI_KEY`, and Langfuse/Firecrawl vars. Size timeouts for synchronous multi-page crawls if you raise `max_pages`.

## Security

- Secrets only in `.env` / ECS task env — never in code or commits
- CORS configurable via `CORS_ORIGINS` (default `*`)

## Known roadmap

- Compress chat history before LLM calls
- Dynamic model selection per use case
- Per-user agent memory (Mem0 or similar)

## When changing common areas

| Change | Also check |
|--------|------------|
| Review fields / extraction schema | `parse.py`, `repository.py`, `models.py`, Alembic migration, `format_review_for_context` |
| URL handling | `extractor/urls.py`, tests in `test_crawl.py` |
| Crawl behavior | `crawl/handler.py`, `crawl/jobs.py`, API route, `run_crawl_local.py` |
| Chat / RAG / guardrails | `chat/guardrails.py`, `chat/gradio_app.py`, `rag/retrieve.py`, `chat/prompts.py` |
| Prompts / Langfuse | `observability/prompts.py`, `sync_langfuse_prompts.py`, `test_prompts.py` |
| Config / env | `config.py`, `.env.example`, README setup section |

## Quick verification checklist

After substantive changes:

```bash
pytest
# If DB-related: alembic upgrade head && smoke-test crawl or API
# If Langfuse prompts changed: python scripts/sync_langfuse_prompts.py
```

Do not run live Capterra crawls at scale. Prefer mock/sample HTML for pipeline testing.
