"""FastAPI application for product ingestion (Path A trigger)."""

from contextlib import asynccontextmanager

import src.config  # noqa: F401 — load .env into os.environ before Langfuse initializes

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import products
from src.config import get_settings
from src.observability.langfuse_tracing import flush_traces


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from src.observability.langfuse_tracing import _ensure_langfuse_env

    _ensure_langfuse_env()
    yield
    flush_traces()


app = FastAPI(title="Capterra Review Extractor", version="0.1.0", lifespan=lifespan)

_settings = get_settings()
_cors_origins = _settings.cors_origins_list()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
def root():
    return {"ok": True}


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}

app.include_router(products.router)
