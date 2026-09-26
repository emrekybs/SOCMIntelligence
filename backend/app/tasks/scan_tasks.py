"""
Tarama gorevi - yerel thread pool'da calisir (Celery yok).

Akis (her hedef icin):
  1. adapter.scan()            -> modulun kendi dogrulanmis ciktisi
  2. ham tool ciktisi (cache)  -> Pydantic'in dusurdugu alanlari geri ekle
  3. adapter.to_graph()        -> modulun kendi graph donusturucusu
  4. enrich.enrich_graph()     -> iliski grafigi (yorumcular, mention, hashtag...)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import logging
import os
import time
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from app.core import job_store
from app.core.cache import cache
from app.core.enrich import build_graph, fill_missing
from app.schemas.common import TargetResult, TargetStatus

logger = logging.getLogger(__name__)


ADAPTERS = {
    "github": ("app.modules.github", "GithubAdapter"),
    "mastodon": ("app.modules.mastodon", "MastoAdapter"),
    "reddit": ("app.modules.reddit", "RedditAdapter"),
    "snapchat": ("app.modules.snapchat", "SnapAdapter"),
    "tiktok": ("app.modules.tiktok", "TikTokAdapter"),
    "youtube": ("app.modules.youtube", "YouTubeAdapter"),
    "telegram": ("app.modules.telegram", "TelegramAdapter"),
    "keybase": ("app.modules.keybase", "KeybaseAdapter"),
    "steam": ("app.modules.steam", "SteamAdapter"),
    "gravatar": ("app.modules.gravatar", "GravatarAdapter"),
    "gitlab": ("app.modules.gitlab", "GitLabAdapter"),
    "hackernews": ("app.modules.hackernews", "HackerNewsAdapter"),
    "stackexchange": ("app.modules.stackexchange", "StackExchangeAdapter"),
    "wayback": ("app.modules.wayback", "WaybackAdapter"),
    "x": ("app.modules.x", "XAdapter"),
    "linkedin": ("app.modules.linkedin", "LinkedInAdapter"),
    "instagram": ("app.modules.instagram", "InstagramAdapter"),
    "bluesky": ("app.modules.bluesky", "BlueskyAdapter"),
    "twitch": ("app.modules.twitch", "TwitchAdapter"),
    "discord": ("app.modules.discord", "DiscordAdapter"),
    "kick": ("app.modules.kick", "KickAdapter"),
    "hashtagmap": ("app.modules.hashtagmap", "HashtagMapAdapter"),
    "keyword": ("app.modules.keyword", "KeywordAdapter"),
}


def _get_adapter(platform: str):
    """Platform ismine gore adapter instance - lazy import."""
    if platform not in ADAPTERS:
        raise ValueError(f"Bilinmeyen platform: {platform}")
    import importlib
    mod, cls = ADAPTERS[platform]
    return getattr(importlib.import_module(mod), cls)()


_JS_MAX_INT = 2 ** 53


def js_safe(o: Any) -> Any:
    """Tarayicidan gidip gelince degismeyecek bicim: 2^53 ustu tamsayilar metne, NaN/sonsuz null'a."""
    if isinstance(o, bool) or o is None:
        return o
    if isinstance(o, int):
        return str(o) if abs(o) > _JS_MAX_INT else o
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {str(k): js_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [js_safe(v) for v in o]
    return o


def _canon(o: Any) -> Any:
    # JSON.parse/stringify 5.0 -> 5 yapar; hash tarayicidan donen veriyle ayni cikmali.
    if isinstance(o, float) and math.isfinite(o) and o.is_integer() and abs(o) <= _JS_MAX_INT:
        return int(o)
    if isinstance(o, dict):
        return {str(k): _canon(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_canon(v) for v in o]
    return o


def canonical_json(data: Any) -> str:
    """Delil hash'i icin kanonik JSON (anahtar sirali, bosluksuz, UTF-8; tam sayi degerli ondaliklar tamsayi)."""
    return json.dumps(_canon(js_safe(data)), sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def sha256_of(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


@lru_cache(maxsize=64)
def _file_sha256(path: str, mtime: float) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def tool_fingerprint(adapter) -> dict[str, Any]:
    from app.core.tool_runner import TOOLS_DIR
    override = os.environ.get(f"SOCMINT_SCRIPT_{adapter.platform.upper()}")
    path = TOOLS_DIR / (override or adapter.script)
    try:
        return {"tool": adapter.script, "tool_sha256": _file_sha256(str(path), path.stat().st_mtime)}
    except OSError:
        return {"tool": adapter.script, "tool_sha256": None}


def _classify_error(e: Exception) -> tuple[TargetStatus, str]:
    msg = str(e)
    low = msg.lower()
    if isinstance(e, LookupError):
        return TargetStatus.NOT_FOUND, msg
    if isinstance(e, PermissionError):
        return TargetStatus.PRIVATE, msg
    if isinstance(e, TimeoutError):
        return TargetStatus.ERROR, f"timeout: {msg}"
    if isinstance(e, RuntimeError):
        if "rate" in low or "429" in low:
            return TargetStatus.RATE_LIMITED, msg
        # Snapchat tool'u bulunamayan hesapta exit=2 + "not found" doner
        if "not found" in low or "exit=2" in low:
            return TargetStatus.NOT_FOUND, msg
        return TargetStatus.ERROR, msg
    return TargetStatus.ERROR, f"{type(e).__name__}: {msg}"


async def _scan_one(adapter, target: dict[str, Any]) -> dict[str, Any]:
    raw_in = target["raw"]
    target_type = target["type"]
    value = target["value"]
    start = time.perf_counter()

    extra: dict[str, Any] = {}
    if target.get("compare_with"):
        extra["compare_with"] = target["compare_with"]
    if target.get("video_count"):
        try:
            extra["video_count"] = int(target["video_count"])
        except (TypeError, ValueError):
            pass

    def _done(status, data=None, error=None, graph=None):
        res = TargetResult(
            target=raw_in, type=target_type, value=value, status=status,
            data=data, error=error,
            duration_ms=int((time.perf_counter() - start) * 1000),
        ).model_dump(mode="json")
        res["graph"] = graph
        if res.get("data") is not None:
            res["data"] = js_safe(res["data"])
        if data is not None:
            # Delil butunlugu: saklanan verinin SHA-256'si + toplama zamani + aracin kendi hash'i
            res["evidence"] = {
                "sha256": sha256_of(res["data"]),
                "algorithm": "SHA-256 / kanonik JSON (sort_keys, ayırıcı ',' ':', UTF-8)",
                "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "platform": adapter.platform, "input": raw_in, "input_type": target_type, "value": value,
                **tool_fingerprint(adapter),
            }
        return res

    try:
        data = await adapter.scan(target_type, value, **extra) if extra \
            else await adapter.scan(target_type, value)
    except Exception as e:  # noqa: BLE001
        status, msg = _classify_error(e)
        logger.warning(f"[{adapter.platform}] {value}: {status.value} - {msg[:200]}")
        return _done(status, error=msg)

    # Modul semasi disinda kalan (Pydantic'in sessizce dusurdugu) ham alanlari geri ekle
    try:
        raw = await cache.get_tool_result(adapter.platform, target_type, value)
        if isinstance(raw, dict) and isinstance(data, dict):
            data = fill_missing(data, raw)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"raw merge atlandi: {e}")

    try:
        graph = build_graph(adapter, data)
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[{adapter.platform}] graph olusturulamadi: {e}")
        graph = {"nodes": [], "edges": []}

    return _done(TargetStatus.OK, data=data, graph=graph)


async def _scan_all(job_id: str, platform: str, targets: list[dict[str, Any]]) -> None:
    adapter = _get_adapter(platform)
    job_store.update(job_id, state="STARTED")
    for t in targets:
        res = await _scan_one(adapter, t)
        job_store.append_result(job_id, res)
    job_store.update(job_id, state="SUCCESS")


def run_scan_job(job_id: str, platform: str, targets: list[dict[str, Any]]) -> None:
    """Thread pool girisi - kendi event loop'unu acar."""
    try:
        asyncio.run(_scan_all(job_id, platform, targets))
    except Exception as e:  # noqa: BLE001
        logger.exception(f"Job {job_id} basarisiz: {e}")
        job_store.update(job_id, state="FAILURE", error=f"{type(e).__name__}: {e}")
