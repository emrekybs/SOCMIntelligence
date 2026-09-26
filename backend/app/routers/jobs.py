"""
Job polling endpoint - frontend taramanin durumunu buradan ceker.
Yerel bellek ici job deposunu okur (Celery/Redis yok).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.core import job_store

router = APIRouter(prefix="/api/socmint/jobs", tags=["jobs"])

_STATE_MAP = {
    "PENDING": "pending",
    "STARTED": "started",
    "SUCCESS": "success",
    "FAILURE": "failure",
}


def register_job(job_id: str, platform: str, target_count: int) -> None:
    """Moduller /scan sonrasi cagiriyor - job zaten send_task'ta olusturuldu."""
    if job_store.get(job_id) is None:
        job_store.create(job_id, platform, [{}] * target_count)


@router.get("/{job_id}")
def get_job_status(job_id: str) -> dict[str, Any]:
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job bulunamadi")
    total = job["target_count"] or 1
    return {
        "job_id": job_id,
        "status": _STATE_MAP.get(job["state"], "pending"),
        "platform": job["platform"],
        "target_count": job["target_count"],
        "results": job["results"],
        "error": job["error"],
        "progress": 1.0 if job["state"] == "SUCCESS" else job["current"] / total,
    }
