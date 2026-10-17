"""
Ortak Pydantic schema'lari - tum platformlar icin paylasilir.
"""
from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class ScanStatus(str, Enum):
    """Celery task durumlari ile birebir esit."""
    PENDING = "pending"       # kuyruga girdi, henuz baslamadi
    STARTED = "started"       # worker aldi, calisiyor
    SUCCESS = "success"       # basariyla bitti
    FAILURE = "failure"       # hata aldi
    RETRY = "retry"           # yeniden deneniyor


class TargetStatus(str, Enum):
    """Tek bir hedef icin scan sonucu."""
    OK = "ok"
    NOT_FOUND = "not_found"
    PRIVATE = "private"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"


class TargetResult(BaseModel):
    """
    Tek bir hedefin scan sonucu - tum platformlar bunu doner.
    `data` alani platform-specific sema ile doldurulur.
    """
    target: str                           # kullanicinin yazdigi ham input
    type: str                             # user / subreddit / channel / vs
    value: str                            # normalize edilmis deger
    status: TargetStatus
    data: dict[str, Any] | None = None    # platform-specific payload
    error: str | None = None              # status != OK ise aciklama
    duration_ms: int | None = None        # tek hedef icin tarama suresi


class JobCreated(BaseModel):
    """POST /scan endpoint'leri bunu doner - frontend polling icin."""
    job_id: str
    platform: str
    target_count: int
    created_at: datetime = Field(default_factory=datetime.utcnow)


class JobStatusResponse(BaseModel):
    """GET /jobs/{job_id} bunu doner."""
    job_id: str
    status: ScanStatus
    platform: str
    target_count: int
    results: list[TargetResult] = []
    error: str | None = None
    progress: float = 0.0                 # 0.0 - 1.0
