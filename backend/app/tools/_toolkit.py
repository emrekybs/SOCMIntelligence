"""
SOCMIntelligence — yeni araclar icin ortak yardimcilar.

- Tek requests.Session (proxy: HTTP(S)_PROXY / ALL_PROXY ortam degiskenleri otomatik)
- 429 / 5xx icin geri cekilerek tekrar deneme
- Metinden e-posta, URL, sosyal hesap cikarma
- Saat / gun dagilimi
- Sonucu stdout'a tek JSON olarak yazma (adapter _run_tool bunu okur)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

UA = os.environ.get("SOCMINT_USER_AGENT") or (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
TIMEOUT = 20
_DELAY = float(os.environ.get("SOCMINT_REQUEST_DELAY", "0") or 0)

S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.8"})


class HttpError(Exception):
    def __init__(self, status: int, url: str, body: str = ""):
        self.status = status
        self.url = url
        self.body = body
        super().__init__(f"HTTP {status} {url}")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def get(url: str, params: dict | None = None, headers: dict | None = None,
        retries: int = 3, allow: tuple[int, ...] = ()) -> requests.Response:
    """GET + tekrar deneme. `allow` icindeki kodlar hata sayilmaz (or. 404)."""
    last = None
    for attempt in range(retries):
        if _DELAY:
            time.sleep(_DELAY)
        try:
            r = S.get(url, params=params, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
            continue
        if r.status_code in allow or r.status_code < 400:
            return r
        if r.status_code == 429 or r.status_code >= 500:
            wait = r.headers.get("Retry-After")
            time.sleep(min(float(wait), 20) if wait and wait.isdigit() else 2.0 * (attempt + 1))
            last = HttpError(r.status_code, r.url, r.text[:300])
            continue
        raise HttpError(r.status_code, r.url, r.text[:300])
    if isinstance(last, HttpError):
        raise last
    raise HttpError(0, url, str(last))


def get_json(url: str, **kw):
    r = get(url, **kw)
    if r.status_code in kw.get("allow", ()) and r.status_code >= 400:
        return None
    try:
        return r.json()
    except ValueError:
        return None


# ─── Metin cikarma ────────────────────────────────────────────────
EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}(?![\w-])")
URL_RE = re.compile(r"https?://[^\s\"'<>()\[\]]+", re.I)

SOCIAL_PATTERNS = [
    ("twitter", r"(?:twitter|x)\.com/(?!intent|share|home|search|hashtag|i/)([A-Za-z0-9_]{1,15})"),
    ("instagram", r"instagram\.com/(?!p/|reel/|explore/)([A-Za-z0-9_.]{1,30})"),
    ("tiktok", r"tiktok\.com/@([A-Za-z0-9_.]{2,24})"),
    ("youtube", r"youtube\.com/@([A-Za-z0-9_.\-]{2,30})"),
    ("github", r"github\.com/(?!orgs/|sponsors/|features|about|pricing)([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))"),
    ("gitlab", r"gitlab\.com/(?!explore|help|users/sign)([A-Za-z0-9_.\-]{2,255})"),
    ("telegram", r"(?:t\.me|telegram\.me)/(?!s/|joinchat|\+|share)([A-Za-z0-9_]{5,32})"),
    ("reddit", r"reddit\.com/(?:u|user)/([A-Za-z0-9_\-]{3,20})"),
    ("linkedin", r"linkedin\.com/in/([A-Za-z0-9_\-%]{2,100})"),
    ("facebook", r"facebook\.com/(?!sharer|share|profile\.php|pages/)([A-Za-z0-9.]{3,50})"),
    ("snapchat", r"snapchat\.com/(?:add/|@)([A-Za-z0-9_.\-]{3,32})"),
    ("keybase", r"keybase\.io/([A-Za-z0-9_]{2,16})"),
    ("steam", r"steamcommunity\.com/(?:id|profiles)/([A-Za-z0-9_\-]{2,64})"),
    ("twitch", r"twitch\.tv/([A-Za-z0-9_]{3,25})"),
    ("hackernews", r"news\.ycombinator\.com/user\?id=([A-Za-z0-9_\-]{2,15})"),
    ("mastodon", r"https?://([a-z0-9.\-]+\.[a-z]{2,})/@([A-Za-z0-9_]{1,30})(?:$|[/?#\s])"),
]


def find_emails(text: str) -> list[str]:
    out = []
    for m in EMAIL_RE.findall(text or ""):
        m = m.strip(".").lower()
        if m.endswith((".png", ".jpg", ".gif", ".svg", ".webp")):
            continue
        if m not in out:
            out.append(m)
    return out


def find_urls(text: str) -> list[str]:
    out = []
    for u in URL_RE.findall(text or ""):
        u = u.rstrip(".,);:!?'\"")
        if u not in out:
            out.append(u)
    return out


def find_socials(text: str) -> list[dict]:
    """Metin/URL'lerden {platform, handle, url} listesi."""
    out, seen = [], set()
    text = text or ""
    for plat, pat in SOCIAL_PATTERNS:
        for m in re.finditer(pat, text, re.I):
            if plat == "mastodon":
                inst, user = m.group(1).lower(), m.group(2)
                if inst.endswith(("twitter.com", "x.com", "instagram.com", "tiktok.com", "youtube.com", "medium.com", "threads.net")):
                    continue
                handle, url = f"{user}@{inst}", f"https://{inst}/@{user}"
            else:
                handle = m.group(1).rstrip("/.")
                url = None
            key = (plat, handle.lower())
            if key in seen or handle.lower() in ("share", "home", "login", "signup", "about"):
                continue
            seen.add(key)
            out.append({"platform": plat, "handle": handle, "url": url or _profile_url(plat, handle)})
    return out


def _profile_url(plat: str, h: str) -> str:
    return {
        "twitter": f"https://x.com/{h}", "instagram": f"https://instagram.com/{h}", "tiktok": f"https://www.tiktok.com/@{h}",
        "youtube": f"https://youtube.com/@{h}", "github": f"https://github.com/{h}", "gitlab": f"https://gitlab.com/{h}",
        "telegram": f"https://t.me/{h}", "reddit": f"https://www.reddit.com/user/{h}", "linkedin": f"https://linkedin.com/in/{h}",
        "facebook": f"https://facebook.com/{h}", "snapchat": f"https://www.snapchat.com/add/{h}", "keybase": f"https://keybase.io/{h}",
        "steam": f"https://steamcommunity.com/id/{h}", "twitch": f"https://twitch.tv/{h}",
        "hackernews": f"https://news.ycombinator.com/user?id={h}",
    }.get(plat, "")


def domain_of(url: str) -> str | None:
    try:
        host = urlparse(url if "://" in url else "https://" + url).netloc.lower()
    except ValueError:
        return None
    host = host.split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else (host or None)


def html_to_text(html: str) -> str:
    if not html:
        return ""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        for br in soup.find_all(["br", "p"]):
            br.insert_before("\n")
        return re.sub(r"\n{3,}", "\n\n", soup.get_text()).strip()
    except Exception:
        return re.sub(r"<[^>]+>", " ", html).strip()


def links_from_html(html: str) -> list[str]:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html or "", "lxml")
        out = []
        for a in soup.find_all("a", href=True):
            h = a["href"].strip()
            if h.startswith("http") and h not in out:
                out.append(h)
        return out
    except Exception:
        return find_urls(html)


# ─── Zaman ────────────────────────────────────────────────────────
def to_dt(v) -> datetime | None:
    if v is None or v == "":
        return None
    try:
        if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
            return datetime.fromtimestamp(int(v), tz=timezone.utc)
        s = str(v).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None


def iso(v) -> str | None:
    dt = to_dt(v)
    return dt.isoformat() if dt else None


def distributions(datetimes: list) -> dict:
    dts = [d for d in (to_dt(x) if not isinstance(x, datetime) else x for x in datetimes) if d]
    hours, days = Counter(), Counter()
    for d in dts:
        hours[d.hour] += 1
        days[d.weekday()] += 1
    return {
        "hour_distribution": {str(h): hours[h] for h in sorted(hours)},
        "day_distribution": {str(d): days[d] for d in sorted(days)},
        "first": min(dts).isoformat() if dts else None,
        "last": max(dts).isoformat() if dts else None,
        "count": len(dts),
    }


def emit(obj: dict) -> None:
    """Tek JSON satiri - adapter bunu okur."""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def fail(kind: str, message: str) -> None:
    """kind: not_found | private | rate_limited | error"""
    emit({"error": kind, "message": message})
    sys.exit(0)
