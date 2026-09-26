"""
Bellek ici TTL cache - Redis GEREKTIRMEZ.

Eski Redis sarmalayicisiyla ayni async arayuz (get/set/delete/get_tool_result/
set_tool_result/...), boylece adapter ve moduller degismeden calisir.
Thread-safe: taramalar thread pool'da, her biri kendi event loop'unda kosar.
"""
from __future__ import annotations

import copy
import hashlib
import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TTL = 300  # 5 dakika


class MemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    # Eski API uyumlulugu (Redis connect/disconnect)
    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    def _purge(self) -> None:
        now = time.time()
        for k in [k for k, (exp, _) in self._data.items() if exp < now]:
            self._data.pop(k, None)

    # ─── Generic KV ───────────────────────────────────────────────
    async def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._data.get(key)
            if not item:
                self.misses += 1
                return None
            exp, val = item
            if exp < time.time():
                self._data.pop(key, None)
                self.misses += 1
                return None
            self.hits += 1
            return copy.deepcopy(val)

    async def set(self, key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
        with self._lock:
            self._purge()
            self._data[key] = (time.time() + ttl, copy.deepcopy(value))

    async def delete(self, key: str) -> bool:
        with self._lock:
            return self._data.pop(key, None) is not None

    async def exists(self, key: str) -> bool:
        return (await self.get(key)) is not None

    # ─── Tool sonuc cache ─────────────────────────────────────────
    @staticmethod
    def _tool_key(platform: str, target_type: str, value: str) -> str:
        safe = value.lower().strip()
        if len(safe) > 60 or any(c in safe for c in " /\\:?*\"<>|"):
            safe = hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]
        return f"tool:{platform}:{target_type}:{safe}"

    async def get_tool_result(self, platform: str, target_type: str, value: str) -> dict | None:
        return await self.get(self._tool_key(platform, target_type, value))

    async def set_tool_result(self, platform: str, target_type: str, value: str,
                              result: dict, ttl: int = DEFAULT_TTL) -> None:
        await self.set(self._tool_key(platform, target_type, value), result, ttl=ttl)

    async def invalidate_tool(self, platform: str, target_type: str, value: str) -> bool:
        return await self.delete(self._tool_key(platform, target_type, value))

    async def flush_platform(self, platform: str) -> int:
        prefix = f"tool:{platform}:"
        with self._lock:
            keys = [k for k in self._data if k.startswith(prefix)]
            for k in keys:
                self._data.pop(k, None)
        return len(keys)

    async def flush_all(self) -> int:
        with self._lock:
            n = len(self._data)
            self._data.clear()
        return n

    async def stats(self) -> dict[str, Any]:
        with self._lock:
            self._purge()
            tool = sum(1 for k in self._data if k.startswith("tool:"))
            return {
                "backend": "memory",
                "entries": len(self._data),
                "tool_cache_entries": tool,
                "hits": self.hits,
                "misses": self.misses,
            }


cache = MemoryCache()
