"""
SOCMIntelligence - FastAPI ana uygulamasi.

Tek komutla calisir (Redis / Celery / nginx gerekmez):
    uvicorn server:app --host 0.0.0.0 --port 8000        (proje kokunden)
    uvicorn app.main:app --port 8000                      (backend/ dizininden)

Arayuz: http://localhost:8000/      API dokumani: http://localhost:8000/docs
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


def _load_dotenv() -> None:
    """.env dosyasini os.environ'a yukle (tool subprocess'leri env'den okur)."""
    for p in (PROJECT_DIR / ".env", BACKEND_DIR / ".env"):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and v and k not in os.environ:
                os.environ[k] = v


_load_dotenv()
os.environ.setdefault("CASES_DB_PATH", str(PROJECT_DIR / "data" / "cases.db"))

from app.config import settings  # noqa: E402
from app.core import cases_store  # noqa: E402
from app.core.cache import cache  # noqa: E402
from app.modules import github as github_module  # noqa: E402
from app.modules import mastodon as mastodon_module  # noqa: E402
from app.modules import reddit as reddit_module  # noqa: E402
from app.modules import snapchat as snapchat_module  # noqa: E402
from app.modules import tiktok as tiktok_module  # noqa: E402
from app.modules import youtube as youtube_module  # noqa: E402
from app.modules import telegram as telegram_module  # noqa: E402
from app.modules import keybase as keybase_module  # noqa: E402
from app.modules import steam as steam_module  # noqa: E402
from app.modules import gravatar as gravatar_module  # noqa: E402
from app.modules import gitlab as gitlab_module  # noqa: E402
from app.modules import hackernews as hackernews_module  # noqa: E402
from app.modules import stackexchange as stackexchange_module  # noqa: E402
from app.modules import wayback as wayback_module  # noqa: E402
from app.modules import x as x_module  # noqa: E402
from app.modules import linkedin as linkedin_module  # noqa: E402
from app.modules import instagram as instagram_module  # noqa: E402
from app.modules import bluesky as bluesky_module  # noqa: E402
from app.modules import twitch as twitch_module  # noqa: E402
from app.modules import discord as discord_module  # noqa: E402
from app.modules import kick as kick_module  # noqa: E402
from app.modules import hashtagmap as hashtagmap_module  # noqa: E402
from app.modules import keyword as keyword_module  # noqa: E402
from app.routers import cases as cases_router  # noqa: E402
from app.routers import jobs  # noqa: E402
from app.routers import extra as extra_router  # noqa: E402
from app.core import settings_store, watch  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("socmint")

FRONTEND_DIR = Path(os.environ.get("SOCMINT_FRONTEND_DIR", PROJECT_DIR / "frontend"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    try:
        cases_store.init_db()
        watch.init_db()
        logger.info(f"Vaka veritabani: {cases_store.DB_PATH}")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Vaka DB baslatilamadi: {e}")
    try:
        settings_store.apply()
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ayarlar uygulanamadi: {e}")
    stop = asyncio.Event()
    sched = asyncio.create_task(watch.scheduler_loop(stop))
    logger.info("SOCMIntelligence hazir -> http://localhost:8000/")
    yield
    stop.set()
    sched.cancel()


app = FastAPI(
    title="SOCMIntelligence API",
    description="Cok platformlu sosyal medya istihbarati (SOCMINT) tarama servisi",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins + ["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)
app.include_router(extra_router.router)
app.include_router(cases_router.router)
app.include_router(github_module.router)
app.include_router(mastodon_module.router)
app.include_router(reddit_module.router)
app.include_router(snapchat_module.router)
app.include_router(tiktok_module.router)
app.include_router(youtube_module.router)
for _m in (telegram_module, keybase_module, steam_module, gravatar_module, gitlab_module,
           hackernews_module, stackexchange_module, wayback_module, x_module, linkedin_module, instagram_module, bluesky_module, twitch_module, discord_module, kick_module, hashtagmap_module, keyword_module):
    app.include_router(_m.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "cache": "memory", "queue": "local-threadpool"}


@app.get("/api/socmint/status")
async def status() -> dict:
    """Arayuzun gosterdigi ortam bilgisi (anahtar degeri ASLA donmez)."""
    return {
        "youtube_api_key": bool(os.environ.get("YOUTUBE_API_KEY")),
        "steam_api_key": bool(os.environ.get("STEAM_API_KEY")),
        "x_bearer_token": bool(os.environ.get("X_BEARER_TOKEN")),
        "hikerapi_token": bool(os.environ.get("HIKERAPI_TOKEN")),
        "twitch_api_key": bool(os.environ.get("TWITCH_CLIENT_ID") and os.environ.get("TWITCH_CLIENT_SECRET")),
        "cache": await cache.stats(),
    }


@app.get("/api/admin/cache/stats")
async def cache_stats() -> dict:
    return await cache.stats()


@app.post("/api/admin/cache/flush")
async def cache_flush() -> dict:
    return {"flushed": await cache.flush_all()}


# ─── Arayuz (statik) ──────────────────────────────────────────────
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-store"})
else:  # pragma: no cover
    @app.get("/", include_in_schema=False)
    async def index_missing():
        return JSONResponse({"service": "SOCMIntelligence", "docs": "/docs", "ui": "frontend/ bulunamadi"})
