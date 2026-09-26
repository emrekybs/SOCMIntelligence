#!/usr/bin/env python3
"""
Kick OSINT — herkese acik kanal bilgisi (SOCMIntelligence).

Kick, Cloudflare korumasi arkasindadir; oturumsuz istekler cogu zaman engellenir.
Engellenirse arac acikca "engellendi" durumu doner (LinkedIn modulundeki gibi).

  python kick_osint.py trainwreckstv
  python kick_osint.py https://kick.com/xqc
"""
from __future__ import annotations

import argparse
import re

import _toolkit as tk

API = "https://kick.com/api/v2/channels"


def normalize(raw: str) -> str | None:
    t = (raw or "").strip()
    if not t:
        return None
    m = re.search(r"kick\.com/([^/?#\s]+)", t, re.I)
    if m:
        t = m.group(1)
    t = t.strip("/").lstrip("@").lower()
    return t if re.match(r"^[a-z0-9_]{2,25}$", t) else None


def main() -> None:
    ap = argparse.ArgumentParser(description="Kick OSINT (v2 public)")
    ap.add_argument("target")
    args = ap.parse_args()
    slug = normalize(args.target)
    if not slug:
        tk.fail("error", f"Gecersiz Kick kullanici adi: {args.target}")

    try:
        r = tk.get(f"{API}/{slug}", headers={"Accept": "application/json"}, retries=2, allow=(403, 404, 429, 503))
    except tk.HttpError as e:
        tk.fail("error", f"Kick'e erisilemedi: {e}")
    if r.status_code in (403, 503):
        tk.fail("private", "Kick Cloudflare korumasi istegi engelledi (oturumsuz okunamadi)")
    if r.status_code == 404:
        tk.fail("not_found", f"Kick kanali bulunamadi: {slug}")
    if r.status_code == 429:
        tk.fail("rate_limited", "Kick hiz siniri")
    try:
        d = r.json() or {}
    except ValueError:
        tk.fail("private", "Kick beklenen JSON yerine Cloudflare sayfasi dondurdu (engellendi)")
    if not d or not d.get("id"):
        tk.fail("not_found", f"Kick kanali bulunamadi: {slug}")

    u = d.get("user") or {}
    live = d.get("livestream") or None
    cats = []
    for c in (d.get("recent_categories") or []):
        name = (c.get("category") or {}).get("name") or c.get("name")
        if name:
            cats.append(name)
    bio = u.get("bio") or ""
    socials = {k: v for k, v in {
        "twitter": u.get("twitter"), "instagram": u.get("instagram"), "youtube": u.get("youtube"),
        "discord": u.get("discord"), "tiktok": u.get("tiktok"), "facebook": u.get("facebook"),
    }.items() if v}

    tk.emit({
        "slug": d.get("slug") or slug, "id": d.get("id"), "user_id": d.get("user_id"),
        "username": u.get("username"), "bio": bio, "profile_pic": u.get("profile_pic"),
        "followers": d.get("followers_count"), "verified": bool(d.get("verified")),
        "is_banned": bool(d.get("is_banned")), "vod_enabled": d.get("vod_enabled"),
        "subscription_enabled": d.get("subscription_enabled"),
        "url": f"https://kick.com/{d.get('slug') or slug}",
        "live": bool(live),
        "stream": {"title": live.get("session_title"), "viewers": live.get("viewer_count"),
                   "started_at": live.get("created_at"),
                   "categories": [c.get("name") for c in (live.get("categories") or []) if c.get("name")]} if live else None,
        "recent_categories": list(dict.fromkeys(cats))[:20],
        "declared_socials": socials,
        "socials": tk.find_socials(bio + " " + " ".join(socials.values())),
        "domains": list(dict.fromkeys(tk.domain_of(u2) for u2 in tk.find_urls(bio) if tk.domain_of(u2)))[:15],
        "emails": tk.find_emails(bio),
    })


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        tk.fail("error", f"Kick araci beklenmedik hata: {e}")
