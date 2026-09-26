"""
Tool runner - OSINT scriptlerini subprocess + asyncio ile calistirir.

Ozellikler:
  - Async subprocess (non-blocking)
  - Timeout + graceful kill (SIGTERM sonra SIGKILL)
  - stdout JSON parse
  - Hata tipi ayristirma (not_found, rate_limit, private, error)
  - Process izolasyonu (her tool crash'i backend'i etkilemez)

Kullanim:
    result = await run_tool(
        script="github_osint.py",
        args=["torvalds", "--json"],
        timeout=45,
        env={"GITHUB_TOKEN": "ghp_xxx"}
    )
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import signal
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Script'lerin bulundugu dizin - Dockerfile'da /app/app/tools/'a kopyalaniyor
TOOLS_DIR = Path(__file__).parent.parent / "tools"


class ToolError(Exception):
    """Tool runner base exception."""
    pass


class ToolNotFound(ToolError):
    """Tool dosyasi yok."""
    pass


class ToolTimeout(ToolError):
    """Tool timeout suresi icinde bitmedi."""
    pass


class ToolCrashed(ToolError):
    """Tool non-zero exit code ile bitti."""
    def __init__(self, code: int, stderr: str, stdout: str = ""):
        self.code = code
        self.stderr = stderr
        self.stdout = stdout
        super().__init__(f"Exit {code}: {stderr[:200]}")


class ToolBadJson(ToolError):
    """Tool stdout JSON parse edilemedi."""
    def __init__(self, stdout: str, parse_error: str):
        self.stdout = stdout
        self.parse_error = parse_error
        super().__init__(f"JSON parse hatasi: {parse_error}")


async def run_tool(
    script: str,
    args: list[str],
    timeout: int = 60,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """
    OSINT script'ini async subprocess olarak calistir, JSON parse et, don.

    Args:
        script: tools/ altindaki dosya ismi, orn. "github_osint.py"
        args: script'e gidecek argumanlar, orn. ["torvalds", "--json"]
        timeout: saniye - bu sureyi asarsa SIGTERM -> SIGKILL
        env: ek env var'lar (GITHUB_TOKEN gibi) - mevcut env'e merge edilir
        cwd: calisma dizini (default: TOOLS_DIR)

    Returns:
        Tool'un stdout'unda bastigi JSON dict.

    Raises:
        ToolNotFound: script yok
        ToolTimeout: timeout dolmadi bitmedi
        ToolCrashed: non-zero exit
        ToolBadJson: stdout JSON degil
    """
    script_path = TOOLS_DIR / script
    if not script_path.exists():
        raise ToolNotFound(f"Tool bulunamadi: {script_path}")

    # Env - mevcut env + tool'a ozel env
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    try:
        from app.core import settings_store
        full_env.update(settings_store.rotate_proxy_env())
    except Exception:
        pass

    logger.info(f"[tool] {script} {args}  (timeout={timeout}s)")

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-u",  # unbuffered - stdout hemen aksin
        str(script_path),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=full_env,
        cwd=str(cwd) if cwd else str(TOOLS_DIR),
        # Process grubu olustur - kill yapinca child'lar da olsun
        preexec_fn=os.setsid if hasattr(os, "setsid") else None,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.warning(f"[tool] {script} timeout ({timeout}s) - SIGTERM gonderiliyor")
        _kill_process_group(proc)
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            logger.warning(f"[tool] {script} SIGTERM'e yanit vermedi - SIGKILL")
            _kill_process_group(proc, sig=signal.SIGKILL)
            await proc.wait()
        raise ToolTimeout(f"{script} {timeout}s icinde bitmedi")

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")

    if proc.returncode != 0:
        logger.error(f"[tool] {script} exit {proc.returncode}: {stderr[:300]}")
        raise ToolCrashed(proc.returncode, stderr, stdout)

    # stdout'u JSON parse et - bazi tool'lar loglarla mix edebilir
    # o yuzden once son "{" ile baslayan satiri dene, olmazsa tamamini dene
    stdout_stripped = stdout.strip()
    if not stdout_stripped:
        raise ToolBadJson("", "stdout bos")

    try:
        return json.loads(stdout_stripped)
    except json.JSONDecodeError as e:
        # Belki tool stdout'una log + sonunda JSON yazmis. Son JSON blogunu bul.
        last_json = _extract_last_json(stdout_stripped)
        if last_json is not None:
            return last_json
        logger.error(f"[tool] {script} JSON parse hatasi: {e}\nstdout: {stdout[:500]}")
        raise ToolBadJson(stdout, str(e))


def _kill_process_group(proc: asyncio.subprocess.Process, sig: int = signal.SIGTERM) -> None:
    """Process grubunu oldur - child process'ler de dahil."""
    if proc.returncode is not None:
        return  # zaten bitti
    try:
        if hasattr(os, "killpg"):
            os.killpg(os.getpgid(proc.pid), sig)
        else:
            proc.send_signal(sig)
    except (ProcessLookupError, PermissionError):
        pass


def _extract_last_json(text: str) -> dict | None:
    """
    Stdout'ta log + JSON karismis olabilir. Son '{' ile baslayan ve
    dengeli '}'  ile biten blogu bul ve parse et.
    """
    idx = text.rfind("\n{")
    if idx < 0:
        idx = text.rfind("{") if text.startswith("{") else -1
    if idx < 0:
        return None
    candidate = text[idx:].strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None
