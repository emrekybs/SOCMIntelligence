#!/usr/bin/env python3
"""
Twitch OSINT — resmi Helix API (SOCMIntelligence).

Anahtar: TWITCH_CLIENT_ID + TWITCH_CLIENT_SECRET (Ayarlar). App access token
client_credentials ile alinir. Anahtar yoksa acikca "ORNEK VERI" doner.

  python twitch_osint.py ninja
  python twitch_osint.py https://twitch.tv/pokimane
"""
from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timezone

import _toolkit as tk

HELIX = "https://api.twitch.tv/helix"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"


def normalize(raw: str) -> str | None:
    t = (raw or "").strip()
    if not t:
        return None
    m = re.search(r"twitch\.tv/([^/?#\s]+)", t, re.I)
    if m:
        t = m.group(1)
    t = t.strip("/").lstrip("@").lower()
    return t if re.match(r"^[a-z0-9_]{3,25}$", t) else None


def app_token(cid: str, secret: str) -> str:
    r = tk.S.post(TOKEN_URL, params={"client_id": cid, "client_secret": secret, "grant_type": "client_credentials"}, timeout=20)
    if r.status_code != 200:
        raise tk.HttpError(r.status_code, TOKEN_URL, r.text[:200])
    return r.json()["access_token"]


def helix(path: str, token: str, cid: str, **params):
    r = tk.get(f"{HELIX}/{path}", params=params, headers={"Client-Id": cid, "Authorization": f"Bearer {token}"}, allow=(400, 401, 404))
    if r.status_code >= 400:
        return {}
    return r.json() or {}


def _age_days(iso: str | None) -> int | None:
    dt = tk.to_dt(iso)
    return (datetime.now(timezone.utc) - dt).days if dt else None


def analyze(login: str, token: str, cid: str) -> dict:
    users = helix("users", token, cid, login=login).get("data") or []
    if not users:
        tk.fail("not_found", f"Twitch kanali bulunamadi: {login}")
    u = users[0]
    uid = u["id"]
    ch = (helix("channels", token, cid, broadcaster_id=uid).get("data") or [{}])[0]
    stream = (helix("streams", token, cid, user_id=uid).get("data") or [{}])
    live = stream[0] if stream and stream[0] else None
    videos = (helix("videos", token, cid, user_id=uid, first=20, sort="time").get("data") or [])
    clips = (helix("clips", token, cid, broadcaster_id=uid, first=20).get("data") or [])
    # takipci sayisi bazen scope ister; denenir, olmazsa atlanir
    follows = helix("channels/followers", token, cid, broadcaster_id=uid)
    followers = follows.get("total") if isinstance(follows, dict) else None

    desc = u.get("description") or ""
    return {
        "id": uid, "login": u.get("login"), "display_name": u.get("display_name"), "description": desc,
        "type": u.get("broadcaster_type") or u.get("type") or None,
        "profile_image_url": u.get("profile_image_url"), "offline_image_url": u.get("offline_image_url"),
        "created_at": u.get("created_at"), "account_age_days": _age_days(u.get("created_at")),
        "view_count": u.get("view_count"), "followers": followers,
        "url": f"https://twitch.tv/{u.get('login')}",
        "channel": {"game": ch.get("game_name"), "title": ch.get("title"),
                    "language": ch.get("broadcaster_language"), "tags": ch.get("tags") or [],
                    "content_labels": ch.get("content_classification_labels") or []},
        "live": bool(live),
        "stream": {"title": live.get("title"), "game": live.get("game_name"), "viewers": live.get("viewer_count"),
                   "started_at": live.get("started_at"), "language": live.get("language")} if live else None,
        "videos": [{"title": v.get("title"), "type": v.get("type"), "views": v.get("view_count"),
                    "duration": v.get("duration"), "date": (v.get("created_at") or "")[:10], "url": v.get("url")} for v in videos],
        "clips": [{"title": c.get("title"), "views": c.get("view_count"), "creator": c.get("creator_name"),
                   "game_id": c.get("game_id"), "date": (c.get("created_at") or "")[:10], "url": c.get("url")} for c in clips],
        "socials": [s for s in tk.find_socials(desc) if s["platform"] != "twitch"],
        "domains": list(dict.fromkeys(tk.domain_of(u) for u in tk.find_urls(desc) if tk.domain_of(u)))[:15],
        "emails": tk.find_emails(desc),
    }


def mock(login: str) -> dict:
    return {"login": login, "display_name": login, "mock": True,
            "description": "Bu örnek veridir. Gerçek veri için Ayarlar'dan TWITCH_CLIENT_ID ve secret girin.",
            "type": "partner", "created_at": "2015-03-01T00:00:00Z", "account_age_days": 3800, "view_count": 120000000,
            "followers": 5000000, "url": f"https://twitch.tv/{login}", "profile_image_url": None,
            "channel": {"game": "Just Chatting", "title": "örnek yayın", "language": "en", "tags": ["English", "IRL"], "content_labels": []},
            "live": False, "stream": None,
            "videos": [{"title": "Örnek yayın tekrarı", "type": "archive", "views": 50000, "duration": "3h20m", "date": "2024-06-01", "url": "https://twitch.tv/videos/1"}],
            "clips": [{"title": "Örnek klip", "views": 12000, "creator": "biri", "game_id": "1", "date": "2024-06-02", "url": "https://clips.twitch.tv/x"}],
            "socials": [{"platform": "twitter", "handle": login, "url": f"https://x.com/{login}"}], "domains": [], "emails": []}


def main() -> None:
    ap = argparse.ArgumentParser(description="Twitch OSINT (Helix API)")
    ap.add_argument("target")
    args = ap.parse_args()
    login = normalize(args.target)
    if not login:
        tk.fail("error", f"Gecersiz Twitch kullanici adi: {args.target}")

    cid = os.environ.get("TWITCH_CLIENT_ID")
    secret = os.environ.get("TWITCH_CLIENT_SECRET")
    if not cid or not secret:
        tk.emit(mock(login))
        return
    try:
        token = app_token(cid, secret)
        result = analyze(login, token, cid)
    except tk.HttpError as e:
        if e.status in (401, 403):
            tk.fail("error", f"Twitch anahtari gecersiz/yetkisiz: {e}")
        tk.fail("rate_limited" if e.status in (429, 503) else "error", f"Twitch: {e}")
    tk.emit(result)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        tk.fail("error", f"Twitch araci beklenmedik hata: {e}")
