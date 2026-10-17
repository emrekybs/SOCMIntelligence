"""`socmintelligence` command — starts the web UI with a single command.

    pipx install socmintelligence        (or: pip install socmintelligence)
    socmintelligence                     -> http://127.0.0.1:8000
    socmintelligence --host 0.0.0.0 --port 9000 --no-browser
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser
from pathlib import Path

from socmintelligence import __version__

PKG = Path(__file__).resolve().parent


def _find(sub: str, marker: str) -> Path | None:
    # Installed wheel: socmintelligence/<sub>;  source checkout: <repo>/<sub>
    for base in (PKG, PKG.parent):
        cand = base / sub
        if (cand / marker).exists():
            return cand
    return None


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="socmintelligence", description="SOCMIntelligence — multi-platform SOCMINT / OSINT web tool")
    ap.add_argument("--host", default=os.environ.get("SOCMINT_HOST", "127.0.0.1"),
                    help="bind address (default 127.0.0.1; use 0.0.0.0 to expose on the network)")
    ap.add_argument("--port", type=int, default=int(os.environ.get("SOCMINT_PORT", "8000")), help="port (default 8000)")
    ap.add_argument("--data-dir", help="where cases and settings are stored (default ~/.local/share/socmintelligence)")
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")
    ap.add_argument("--reload", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--version", action="version", version=f"SOCMIntelligence {__version__}")
    args = ap.parse_args(argv)

    backend = _find("backend", "app/main.py")
    frontend = _find("frontend", "index.html")
    if backend is None:
        sys.exit("SOCMIntelligence: backend files not found — the installation looks broken (reinstall the package).")
    if frontend is not None:
        os.environ.setdefault("SOCMINT_FRONTEND_DIR", str(frontend))
    if args.data_dir:
        os.environ["SOCMINT_DATA_DIR"] = str(Path(args.data_dir).expanduser().resolve())
    elif not (backend.parent / "server.py").exists():
        os.environ.setdefault("SOCMINT_DATA_DIR", str(Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "socmintelligence"))
    sys.path.insert(0, str(backend))

    try:
        import uvicorn
    except ImportError:  # pragma: no cover
        sys.exit("SOCMIntelligence: uvicorn is missing — reinstall with: pip install socmintelligence")

    shown = "localhost" if args.host in ("0.0.0.0", "::", "127.0.0.1") else args.host
    url = f"http://{shown}:{args.port}/"
    print(f"\n  SOCMIntelligence {__version__}\n  UI   {url}\n  API  {url}docs\n  Data {os.environ.get('SOCMINT_DATA_DIR') or backend.parent / 'data'}\n  Stop Ctrl+C\n", flush=True)
    gui = not sys.platform.startswith("linux") or os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    if not args.no_browser and gui and sys.stdout.isatty():
        threading.Timer(1.4, lambda: webbrowser.open(url)).start()
    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="info", reload=args.reload,
                app_dir=str(backend))


if __name__ == "__main__":
    main()
