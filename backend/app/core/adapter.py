"""
PlatformAdapter - tum SOCMINT modullerin kullandigi base sinif.

Ozellikler:
  - classify(raw)   : ham input'u (type, value) cift'ine donustur
  - scan(type,value): subprocess ile tool'u calistir, cache kullan
  - _run_tool(...)  : alt siniflarin calistiracagi yardimci
  - capabilities    : modulun destekledigi ek feature'lar
  - to_graph(data)  : scan sonucunu SOCMIntelligence graph node/edge'e cevir

Kullanim (alt sinif):
    class GithubAdapter(PlatformAdapter):
        platform = "github"
        script = "github_osint.py"
        capabilities = ["scan"]

        def classify(self, raw): ...
        async def scan(self, target_type, value):
            return await self._run_tool(target_type, value, [value, "--json"])
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.cache import cache
from app.core.tool_runner import (
    ToolBadJson, ToolCrashed, ToolNotFound, ToolTimeout, run_tool,
    _extract_last_json, TOOLS_DIR,
)

logger = logging.getLogger(__name__)


class PlatformAdapter(ABC):
    """Her SOCMINT modulu icin somut adapter."""

    platform: str = ""                    # "github", "reddit", "telegram"
    script: str = ""                      # "github_osint.py"
    capabilities: list[str] = ["scan"]    # ["scan", "compare", "sentiment"]
    cache_ttl: int = 300                  # saniye

    # ─── Alt sinifin implemente etmesi gerekenler ────────────────

    @abstractmethod
    def classify(self, raw: str) -> tuple[str, str]:
        """Ham input'u (type, value) tuple'ina donustur."""
        ...

    @abstractmethod
    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        """Hedefi tara, normalize dict don. Hata -> Python exception."""
        ...

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        """Default: bos graph. Alt sinif override eder."""
        return {"nodes": [], "edges": []}

    # ─── Ortak yardimci - alt siniflarin scan()'i bunu cagirir ────

    async def _run_tool(
        self,
        target_type: str,
        value: str,
        args: list[str],
        env_keys: list[str] | None = None,
        timeout: int | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Subprocess + cache + error mapping."""
        if not self.script:
            raise RuntimeError(f"{self.platform} adapter'i 'script' tanimlamamis")

        # Script ENV override - test/debug icin.
        # SOCMINT_SCRIPT_GITHUB=/path/to/mock.py -> GitHub icin bu script
        script_override = os.environ.get(f"SOCMINT_SCRIPT_{self.platform.upper()}")
        script_name = script_override or self.script

        # Cache kontrol
        if use_cache:
            cached = await cache.get_tool_result(self.platform, target_type, value)
            if cached is not None:
                logger.info(f"[{self.platform}] cache HIT {target_type}={value}")
                self._raise_if_error(cached)
                return cached

        # Env vars
        env: dict[str, str] = {}
        for key in env_keys or []:
            val = os.environ.get(key)
            if val:
                env[key] = val

        # Tool calistir
        try:
            result = await run_tool(
                script=script_name,
                args=args,
                timeout=timeout or settings.tool_timeout_default,
                env=env,
            )
        except ToolNotFound as e:
            raise RuntimeError(str(e))
        except ToolTimeout as e:
            raise TimeoutError(str(e))
        except ToolCrashed as e:
            # Belki tool hata JSON'ini stdout'a yazdi
            if e.stdout:
                maybe = _extract_last_json(e.stdout)
                if maybe is not None:
                    self._raise_if_error(maybe)
                    return maybe
            raise RuntimeError(f"Tool crashed: {e.stderr[:200]}")
        except ToolBadJson as e:
            raise RuntimeError(f"Tool invalid JSON: {e.parse_error}")

        # Tool hata doverdiyse exception'a cevir
        self._raise_if_error(result)

        # Cache'e yaz
        if use_cache:
            await cache.set_tool_result(
                self.platform, target_type, value, result, ttl=self.cache_ttl,
            )

        return result

    async def _run_tool_file_output(
        self,
        target_type: str,
        value: str,
        args_builder,  # callable: (output_path) -> list[str]
        env_keys: list[str] | None = None,
        timeout: int | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Tool'un stdout yerine dosyaya JSON yazmasi durumu (Mastodon gibi).
        args_builder'a output path verilir, tool oraya yazar, biz okur cache'e koyariz.
        """
        if not self.script:
            raise RuntimeError(f"{self.platform} adapter'i 'script' tanimlamamis")

        # Cache kontrol
        if use_cache:
            cached = await cache.get_tool_result(self.platform, target_type, value)
            if cached is not None:
                logger.info(f"[{self.platform}] cache HIT {target_type}={value}")
                self._raise_if_error(cached)
                return cached

        # ENV override
        script_override = os.environ.get(f"SOCMINT_SCRIPT_{self.platform.upper()}")
        script_name = script_override or self.script

        env: dict[str, str] = {}
        for key in env_keys or []:
            val = os.environ.get(key)
            if val:
                env[key] = val

        # Temp dosya olustur - script buraya yazacak
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, dir="/tmp", prefix=f"{self.platform}_"
        ) as tf:
            output_path = tf.name

        try:
            args = args_builder(output_path)
            result = await self._subprocess_with_file(
                script_name, args, env, timeout, output_path
            )
            self._raise_if_error(result)
            if use_cache:
                await cache.set_tool_result(
                    self.platform, target_type, value, result, ttl=self.cache_ttl,
                )
            return result
        finally:
            try:
                Path(output_path).unlink(missing_ok=True)
            except Exception:
                pass

    async def _run_tool_auto_output(
        self,
        target_type: str,
        value: str,
        args: list[str],
        output_pattern: str,  # glob pattern, orn. "reddit_*.json"
        env_keys: list[str] | None = None,
        timeout: int | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Tool kendi output dosyasi olusturur (Reddit gibi -o flag'i yok).
        Temp dir'de calisir, pattern ile sonuc dosyasini bulur.
        """
        if not self.script:
            raise RuntimeError(f"{self.platform} adapter'i 'script' tanimlamamis")

        # Cache kontrol
        if use_cache:
            cached = await cache.get_tool_result(self.platform, target_type, value)
            if cached is not None:
                logger.info(f"[{self.platform}] cache HIT {target_type}={value}")
                self._raise_if_error(cached)
                return cached

        script_override = os.environ.get(f"SOCMINT_SCRIPT_{self.platform.upper()}")
        script_name = script_override or self.script

        env: dict[str, str] = {}
        for key in env_keys or []:
            val = os.environ.get(key)
            if val:
                env[key] = val

        # Temp working dir - tool cwd olarak buraya yazacak
        with tempfile.TemporaryDirectory(prefix=f"{self.platform}_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            result = await self._subprocess_with_glob(
                script_name, args, env, timeout, tmpdir_path, output_pattern,
            )
            self._raise_if_error(result)
            if use_cache:
                await cache.set_tool_result(
                    self.platform, target_type, value, result, ttl=self.cache_ttl,
                )
            return result

    # ─── Internal subprocess helpers ──────────────────────────────

    async def _subprocess_with_file(
        self, script_name, args, env, timeout, output_path,
    ):
        """Subprocess calistir, belli bir dosyadan JSON oku."""
        import asyncio
        import json as _json

        script_path = TOOLS_DIR / script_name
        if not script_path.exists():
            raise RuntimeError(f"Tool bulunamadi: {script_path}")

        full_env = os.environ.copy()
        full_env.update(env)
        try:
            from app.core import settings_store
            full_env.update(settings_store.rotate_proxy_env())
        except Exception:
            pass
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-u", str(script_path), *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=full_env,
            cwd=str(TOOLS_DIR),
        )
        try:
            _, stderr_b = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout or settings.tool_timeout_default,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise TimeoutError(f"{script_name} timeout")

        if proc.returncode != 0:
            stderr = stderr_b.decode("utf-8", errors="replace")
            raise RuntimeError(f"Tool crashed exit={proc.returncode}: {stderr[:200]}")

        out_file = Path(output_path)
        if not out_file.exists() or out_file.stat().st_size == 0:
            raise RuntimeError(f"Tool output bos/yok: {output_path}")
        try:
            result = _json.loads(out_file.read_text(encoding="utf-8"))
        except _json.JSONDecodeError as e:
            raise RuntimeError(f"Tool output JSON parse: {e}")

        if isinstance(result, list):
            if not result:
                raise LookupError("Tool bos list dondu")
            result = result[0]
        return result

    async def _subprocess_with_glob(
        self, script_name, args, env, timeout, cwd, output_pattern,
    ):
        """Subprocess calistir, cwd'de pattern'e uyan dosyayi bul ve oku."""
        import asyncio
        import json as _json

        script_path = TOOLS_DIR / script_name
        if not script_path.exists():
            raise RuntimeError(f"Tool bulunamadi: {script_path}")

        full_env = os.environ.copy()
        full_env.update(env)
        try:
            from app.core import settings_store
            full_env.update(settings_store.rotate_proxy_env())
        except Exception:
            pass
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-u", str(script_path), *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=full_env,
            cwd=str(cwd),
        )
        try:
            _, stderr_b = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout or settings.tool_timeout_default,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise TimeoutError(f"{script_name} timeout")

        if proc.returncode != 0:
            stderr = stderr_b.decode("utf-8", errors="replace")
            raise RuntimeError(f"Tool crashed exit={proc.returncode}: {stderr[:200]}")

        # Glob ile output dosyasini bul
        matches = sorted(cwd.glob(output_pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        if not matches:
            raise RuntimeError(f"Tool output bulunamadi (pattern={output_pattern})")

        out_file = matches[0]
        try:
            result = _json.loads(out_file.read_text(encoding="utf-8"))
        except _json.JSONDecodeError as e:
            raise RuntimeError(f"Tool output JSON parse: {e}")

        # Coklu sonuclar listesi gelirse
        if isinstance(result, list):
            if not result:
                raise LookupError("Tool bos list dondu")
            # Reddit tool'u: tek hedef varsa dict, coklu ise list doner.
            # Tek eleman -> dict. Birden fazla eleman (TikTok/YouTube karsilastirma
            # modu) -> list olarak birak; moduller bu durumu 'profiles' ile isler.
            if len(result) == 1:
                result = result[0]
        return result

    # ─── Hata JSON'larini Python exception'a cevir ────────────────

    def _raise_if_error(self, result: dict[str, Any]) -> None:
        """Tool'un result dict'inde error varsa uygun exception raise et."""
        if not isinstance(result, dict):
            return
        err = result.get("error") or result.get("status")
        if not err or err in ("ok", "success"):
            return
        err_str = str(err).lower()

        if "not_found" in err_str or "not found" in err_str:
            raise LookupError(result.get("message") or err_str)
        if "private" in err_str or "forbidden" in err_str:
            raise PermissionError(result.get("message") or err_str)
        if "rate" in err_str or "limit" in err_str or "429" in err_str:
            raise RuntimeError(f"rate_limit: {result.get('message') or err_str}")
        if "auth" in err_str or "unauthorized" in err_str or "401" in err_str:
            raise PermissionError(f"auth: {result.get('message') or err_str}")
