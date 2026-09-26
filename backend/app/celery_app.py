"""
Yerel gorev calistirici - Celery/Redis GEREKTIRMEZ.

Moduller hala `celery_app.send_task("scan_platform_targets", args=[platform, targets])`
cagiriyor; bu dosya ayni arayuzu saglar ama isi uvicorn surecinin icindeki bir
thread pool'da calistirir. Boylece tum arac `uvicorn server:app` ile tek komutla
ayaga kalkar ve modul dosyalarinda tek satir degismez.
"""
from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass


@dataclass
class _TaskHandle:
    id: str


class LocalTaskApp:
    """Celery'nin `send_task` arayuzunu taklit eden hafif calistirici."""

    def __init__(self, max_workers: int = 4):
        self.workers = max_workers
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="socmint-job")

    def set_workers(self, n: int) -> None:
        """Ayarlardan paralel is sayisini degistir (calisan isler eski havuzda biter)."""
        n = max(1, min(16, int(n)))
        if n == self.workers:
            return
        old, self.workers = self._pool, n
        self._pool = ThreadPoolExecutor(max_workers=n, thread_name_prefix="socmint-job")
        old.shutdown(wait=False)

    def submit(self, fn, *args):
        return self._pool.submit(fn, *args)

    def send_task(self, name: str, args: list | None = None, kwargs: dict | None = None) -> _TaskHandle:
        if name != "scan_platform_targets":
            raise ValueError(f"Bilinmeyen gorev: {name}")
        args = list(args or [])
        platform, targets = args[0], args[1]
        job_id = uuid.uuid4().hex

        from app.core import job_store
        from app.tasks.scan_tasks import run_scan_job

        job_store.create(job_id, platform, targets)
        self._pool.submit(run_scan_job, job_id, platform, targets)
        return _TaskHandle(id=job_id)


celery_app = LocalTaskApp(max_workers=int(os.environ.get("SOCMINT_WORKERS", "4")))
