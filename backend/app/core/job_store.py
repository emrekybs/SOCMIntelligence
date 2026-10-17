"""
Bellek ici is (job) deposu - tarama durumu, ilerleme ve sonuclar.
Thread-safe; uvicorn sureci yasadigi surece tutulur, 6 saat sonra temizlenir.
"""
from __future__ import annotations

import threading
import time
from typing import Any

_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}
_TTL = 6 * 3600


def _gc() -> None:
    now = time.time()
    for jid in [j for j, v in _JOBS.items() if now - v["created"] > _TTL]:
        _JOBS.pop(jid, None)


def create(job_id: str, platform: str, targets: list[dict]) -> None:
    with _LOCK:
        _gc()
        _JOBS[job_id] = {
            "job_id": job_id,
            "platform": platform,
            "target_count": len(targets),
            "state": "PENDING",
            "current": 0,
            "results": [],
            "error": None,
            "created": time.time(),
        }


def update(job_id: str, **fields: Any) -> None:
    with _LOCK:
        if job_id in _JOBS:
            _JOBS[job_id].update(fields)


def append_result(job_id: str, result: dict) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is not None:
            job["results"] = job["results"] + [result]
            job["current"] = len(job["results"])


def get(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None
