"""
Arayuzden yonetilen ayarlar: API anahtarlari, proxy / Tor, paralel is sayisi, istek gecikmesi.
data/settings.json dosyasinda tutulur, os.environ'a uygulanir (araclar alt surecte env'den okur).
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[3]
PATH = Path(os.environ.get("SOCMINT_SETTINGS_PATH", PROJECT_DIR / "data" / "settings.json"))

KEYS = {
    "YOUTUBE_API_KEY": "YouTube Data API v3",
    "STEAM_API_KEY": "Steam Web API",
    "STACKEXCHANGE_KEY": "Stack Exchange",
    "GRAVATAR_API_KEY": "Gravatar",
    "GITLAB_TOKEN": "GitLab",
    "X_BEARER_TOKEN": "X (Twitter) API — Bearer Token",
    "HIKERAPI_TOKEN": "HikerAPI (Instagram)",
    "TWITCH_CLIENT_ID": "Twitch — Client ID",
    "TWITCH_CLIENT_SECRET": "Twitch — Client Secret",
    "GOOGLE_CSE_KEY": "Google Programmable Search — API Key (web araması)",
    "GOOGLE_CSE_CX": "Google Programmable Search — Engine ID (cx)",
    "FLICKR_API_KEY": "Flickr (hashtag haritası — ücretsiz API key)",
}
PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
DEFAULTS: dict[str, Any] = {"keys": {}, "proxy": {"mode": "none", "url": ""}, "proxies": [], "workers": 4, "request_delay": 0.0}

_lock = threading.Lock()
_ORIGINAL = {k: os.environ.get(k) for k in (*KEYS, *PROXY_VARS, "NO_PROXY", "no_proxy", "SOCMINT_REQUEST_DELAY")}

# Proxy listesi rotasyonu (her tarama alt sureci sirayla farkli proxy alir)
_rot_lock = threading.Lock()
_rot_i = 0


def _valid_proxy(u: str) -> bool:
    return bool(re.match(r"^(https?|socks5h?|socks4)://", u.strip(), re.I))


def rotate_proxy_env() -> dict[str, str]:
    """Proxy listesi modunda bir sonraki proxy'yi env sozlugu olarak dondurur; degilse {}."""
    global _rot_i
    s = load()
    if (s.get("proxy") or {}).get("mode") != "list":
        return {}
    lst = [u for u in (s.get("proxies") or []) if _valid_proxy(u)]
    if not lst:
        return {}
    with _rot_lock:
        u = lst[_rot_i % len(lst)]
        _rot_i += 1
    return {"HTTP_PROXY": u, "HTTPS_PROXY": u, "ALL_PROXY": u,
            "http_proxy": u, "https_proxy": u, "all_proxy": u,
            "NO_PROXY": "localhost,127.0.0.1", "no_proxy": "localhost,127.0.0.1"}


def load() -> dict[str, Any]:
    with _lock:
        try:
            data = json.loads(PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            data = {}
    out = json.loads(json.dumps(DEFAULTS))
    out.update({k: v for k, v in data.items() if k in DEFAULTS})
    return out


def _save(data: dict[str, Any]) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(PATH)
    try:
        os.chmod(PATH, 0o600)
    except OSError:
        pass


def _restore(var: str) -> None:
    if _ORIGINAL.get(var) is None:
        os.environ.pop(var, None)
    else:
        os.environ[var] = _ORIGINAL[var]


def proxy_url(s: dict[str, Any]) -> str | None:
    p = s.get("proxy") or {}
    if p.get("mode") == "tor":
        return p.get("url") or "socks5h://127.0.0.1:9050"
    if p.get("mode") == "custom" and p.get("url"):
        return p["url"]
    if p.get("mode") == "list":
        lst = [u for u in (s.get("proxies") or []) if _valid_proxy(u)]
        return lst[0] if lst else None  # test icin ilk proxy
    return None


def apply(s: dict[str, Any] | None = None) -> dict[str, Any]:
    s = s or load()
    for k in KEYS:
        v = (s.get("keys") or {}).get(k)
        if v:
            os.environ[k] = v
        else:
            _restore(k)
    # Liste modunda global proxy AYARLANMAZ; her tarama alt sureci rotate_proxy_env ile sirayla alir.
    is_list = (s.get("proxy") or {}).get("mode") == "list"
    purl = None if is_list else proxy_url(s)
    for var in PROXY_VARS:
        if purl:
            os.environ[var] = purl
        else:
            _restore(var)
    if purl:
        os.environ["NO_PROXY"] = os.environ["no_proxy"] = "localhost,127.0.0.1"
    else:
        _restore("NO_PROXY"); _restore("no_proxy")
    delay = float(s.get("request_delay") or 0)
    if delay > 0:
        os.environ["SOCMINT_REQUEST_DELAY"] = str(delay)
    else:
        _restore("SOCMINT_REQUEST_DELAY")
    try:
        from app.celery_app import celery_app
        celery_app.set_workers(int(s.get("workers") or 4))
    except Exception:
        pass
    return s


def update(patch: dict[str, Any]) -> dict[str, Any]:
    s = load()
    if "keys" in patch and isinstance(patch["keys"], dict):
        for k, v in patch["keys"].items():
            if k not in KEYS or v is None:
                continue  # None = degistirme
            v = str(v).strip()
            if v:
                s["keys"][k] = v
            else:
                s["keys"].pop(k, None)
    if "proxies" in patch:
        raw = patch["proxies"]
        if isinstance(raw, str):
            raw = re.split(r"[\r\n,]+", raw)
        lst, bad = [], []
        for u in (raw or []):
            u = str(u).strip()
            if not u:
                continue
            (lst if _valid_proxy(u) else bad).append(u)
        if bad:
            raise ValueError("Geçersiz proxy (http://, https://, socks5h:// ile başlamalı): " + ", ".join(bad[:3]))
        s["proxies"] = lst[:100]
    if isinstance(patch.get("proxy"), dict):
        mode = patch["proxy"].get("mode", s["proxy"]["mode"])
        if mode not in ("none", "tor", "custom", "list"):
            raise ValueError("proxy.mode: none | tor | custom | list")
        s["proxy"] = {"mode": mode, "url": str(patch["proxy"].get("url", s["proxy"].get("url")) or "").strip()}
        if mode == "custom" and not s["proxy"]["url"]:
            raise ValueError("Özel proxy için adres gerekli (ör. http://127.0.0.1:8080 veya socks5h://127.0.0.1:1080)")
        if mode == "list" and not [u for u in (s.get("proxies") or []) if _valid_proxy(u)]:
            raise ValueError("Proxy listesi boş — en az bir geçerli proxy girin.")
    if "workers" in patch:
        s["workers"] = max(1, min(16, int(patch["workers"])))
    if "request_delay" in patch:
        s["request_delay"] = max(0.0, min(10.0, float(patch["request_delay"])))
    with _lock:
        _save(s)
    return apply(s)


def public_view(s: dict[str, Any] | None = None) -> dict[str, Any]:
    """Anahtar degerleri ASLA donmez; sadece ayarli mi + son 4 karakter."""
    s = s or load()
    keys = {}
    for k, label in KEYS.items():
        v = (s.get("keys") or {}).get(k) or ""
        from_env = not v and bool(_ORIGINAL.get(k))
        src = v or (_ORIGINAL.get(k) or "")
        keys[k] = {"label": label, "set": bool(src), "hint": ("…" + src[-4:]) if len(src) >= 8 else ("…" if src else ""),
                   "source": "ayarlar" if v else (".env" if from_env else None)}
    return {"keys": keys, "proxy": s.get("proxy"), "proxies": s.get("proxies") or [],
            "workers": s.get("workers"), "request_delay": s.get("request_delay")}
