#!/usr/bin/env python3
"""
Discord OSINT — herkese acik davet + widget bilgisi (SOCMIntelligence). Anahtar gerekmez.

Iki girdi:
  - Davet linki / kodu (discord.gg/xxx) -> sunucu adi, yaklasik uye/cevrimici sayisi, kanal, davet eden
  - Sunucu ID'si (sayisal) -> widget.json (yalnizca widget'i acik sunucularda): kanallar, cevrimici uyeler, anlik davet

  python discord_osint.py discord.gg/python
  python discord_osint.py 267624335836053506
"""
from __future__ import annotations

import argparse
import re

import _toolkit as tk

API = "https://discord.com/api/v10"
VERIF = {0: "Yok", 1: "Düşük", 2: "Orta", 3: "Yüksek", 4: "Çok yüksek"}


def classify(raw: str) -> tuple[str, str] | None:
    t = (raw or "").strip()
    if not t:
        return None
    m = re.search(r"(?:discord\.gg|discord(?:app)?\.com/invite)/([A-Za-z0-9\-]+)", t, re.I)
    if m:
        return ("invite", m.group(1))
    if re.match(r"^\d{15,20}$", t):
        return ("guild", t)
    if re.match(r"^[A-Za-z0-9\-]{2,25}$", t):
        return ("invite", t)
    return None


def fetch_invite(code: str) -> dict:
    r = tk.get(f"{API}/invites/{code}", params={"with_counts": "true", "with_expiration": "true"}, allow=(404, 403, 429))
    if r.status_code == 404:
        tk.fail("not_found", f"Discord daveti bulunamadi / suresi dolmus: {code}")
    if r.status_code == 429:
        tk.fail("rate_limited", "Discord hiz siniri")
    if r.status_code >= 400:
        tk.fail("error", f"Discord: HTTP {r.status_code}")
    d = r.json() or {}
    g = d.get("guild") or {}
    ch = d.get("channel") or {}
    inv = d.get("inviter") or {}
    gid = g.get("id")
    icon = f"https://cdn.discordapp.com/icons/{gid}/{g.get('icon')}.png" if gid and g.get("icon") else None
    out = {
        "kind": "invite", "code": code, "guild_id": gid, "guild_name": g.get("name"),
        "description": g.get("description"), "icon": icon, "features": g.get("features") or [],
        "verification_level": VERIF.get(g.get("verification_level"), g.get("verification_level")),
        "vanity": g.get("vanity_url_code"), "nsfw_level": g.get("nsfw_level"),
        "member_count": d.get("approximate_member_count"), "online_count": d.get("approximate_presence_count"),
        "boosts": g.get("premium_subscription_count"),
        "channel": {"name": ch.get("name"), "id": ch.get("id"), "type": ch.get("type")},
        "inviter": {"username": inv.get("username"), "global_name": inv.get("global_name"), "id": inv.get("id")} if inv else None,
        "expires_at": d.get("expires_at"),
        "url": f"https://discord.gg/{code}",
    }
    if gid:
        out["widget"] = fetch_widget(gid, soft=True)
    return out


def fetch_widget(guild_id: str, soft: bool = False) -> dict | None:
    r = tk.get(f"{API}/guilds/{guild_id}/widget.json", allow=(403, 404, 429))
    if r.status_code != 200:
        if soft:
            return {"enabled": False, "reason": f"HTTP {r.status_code}"}
        if r.status_code in (403, 404):
            tk.fail("private", "Sunucu widget'i kapali veya bulunamadi (yalnizca widget acik sunucular okunabilir)")
        tk.fail("error", f"Discord widget: HTTP {r.status_code}")
    d = r.json() or {}
    return {
        "enabled": True, "guild_id": guild_id, "guild_name": d.get("name"),
        "instant_invite": d.get("instant_invite"), "online_count": d.get("presence_count"),
        "channels": [{"name": c.get("name"), "id": c.get("id"), "position": c.get("position")} for c in (d.get("channels") or [])][:50],
        "members_sample": [{"username": m.get("username"), "status": m.get("status"), "game": (m.get("game") or {}).get("name")}
                           for m in (d.get("members") or [])][:50],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Discord OSINT (davet / widget)")
    ap.add_argument("target")
    args = ap.parse_args()
    c = classify(args.target)
    if not c:
        tk.fail("error", f"Gecersiz Discord daveti veya sunucu ID'si: {args.target}")
    kind, val = c
    if kind == "invite":
        tk.emit(fetch_invite(val))
    else:
        w = fetch_widget(val)
        tk.emit({"kind": "guild", "guild_id": val, "guild_name": (w or {}).get("guild_name"),
                 "member_count": None, "online_count": (w or {}).get("online_count"), "widget": w,
                 "url": (w or {}).get("instant_invite")})


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except tk.HttpError as e:
        tk.fail("rate_limited" if e.status in (429, 503) else "error", f"Discord: {e}")
    except Exception as e:  # noqa: BLE001
        tk.fail("error", f"Discord araci beklenmedik hata: {e}")
