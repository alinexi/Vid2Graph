"""FastAPI application: lifecycle hooks, CORS, static media, demo auto-seeding."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app import __version__
from app.api.routes import router
from app.core import runtime_settings
from app.core.config import settings
from app.db.database import get_db
from app.db.seed_demo import seed_if_missing

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("vid2graph")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = get_db()
    runtime_settings.load_overrides(db.get_setting("model_overrides", {}) or {})
    if settings.seed_demo and seed_if_missing(db):
        log.info("Seeded demo graph")
    ms = runtime_settings.current()
    log.info("Vid2Graph %s · data=%s · llm=%s:%s @ %s", __version__, settings.resolved_data_dir,
             ms.llm_provider, ms.llm_model, ms.llm_base_url)
    yield
    db.close()


app = FastAPI(title="Vid2Graph API", version=__version__, lifespan=lifespan,
              description="Turn videos, podcasts and lectures into interactive knowledge graphs — locally.")
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origin_list, allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"],
)
app.include_router(router)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/docs")
