"""
Discord OSINT modulu - SOCMIntelligence platformu.

Tool: tools/discord_osint.py (herkese acik davet + widget; anahtar gerekmez)
  Input: davet linki/kodu (discord.gg/xxx) veya sunucu ID'si
Graph: topluluk (sunucu) + davet eden hesap + kanal.
"""
from __future__ import annotations

import re
from typing import Any

from app.core.adapter import PlatformAdapter
from app.modules._common import G, make_router, raise_tool_error, slug


class DiscordAdapter(PlatformAdapter):
    platform = "discord"
    script = "discord_osint.py"
    capabilities = ["scan"]
    cache_ttl = 300

    def classify(self, raw: str) -> tuple[str, str]:
        t = (raw or "").strip()
        if not t:
            raise ValueError("Bos input")
        m = re.search(r"(?:discord\.gg|discord(?:app)?\.com/invite)/([A-Za-z0-9\-]+)", t, re.I)
        if m:
            return ("invite", m.group(1))
        if re.match(r"^\d{15,20}$", t):
            return ("guild", t)
        if re.match(r"^[A-Za-z0-9\-]{2,25}$", t):
            return ("invite", t)
        raise ValueError(f"Gecersiz Discord daveti veya sunucu ID'si: {raw}")

    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        result = await self._run_tool(target_type, value, [value], timeout=60)
        raise_tool_error(result, "Discord")
        return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return DiscordGraphConverter.convert(data)


class DiscordGraphConverter:
    @staticmethod
    def convert(d: dict[str, Any]) -> dict[str, list]:
        g = G()
        gid = d.get("guild_id")
        name = d.get("guild_name") or (d.get("code") and f"davet:{d['code']}")
        if not gid and not name:
            return g.export()
        sid = g.node(f"srv_discord_{slug(gid or d.get('code'))}", "community", name or gid, {
            "Platform": "Discord", "Sunucu ID": gid, "Açıklama": (d.get("description") or "")[:160],
            "Üye": d.get("member_count"), "Çevrimiçi": d.get("online_count"), "Doğrulama": d.get("verification_level"),
            "Vanity": d.get("vanity"), "URL": d.get("url"),
        })
        inv = d.get("inviter") or {}
        if inv.get("username"):
            iid = g.node(f"u_discord_{slug(inv.get('id') or inv['username'])}", "username", inv["username"],
                         {"Platforms": "Discord", "Görünen ad": inv.get("global_name"), "Source": "Davet eden"})
            g.edge(iid, sid, "member_of")
        ch = d.get("channel") or {}
        if ch.get("name"):
            cid = g.node(f"chan_discord_{slug(ch.get('id') or ch['name'])}", "content", "#" + ch["name"], {"Tür": "Kanal"})
            g.edge(sid, cid, "appears_in")
        # widget'tan cevrimici uyeler (varsa)
        w = d.get("widget") or {}
        for m in (w.get("members_sample") or [])[:25]:
            if m.get("username"):
                mid = g.node(f"u_discord_{slug(m['username'])}", "username", m["username"],
                             {"Platforms": "Discord", "Durum": m.get("status"), "Oyun": m.get("game"), "Source": "Widget"})
                g.edge(mid, sid, "member_of")
        return g.export()


router = make_router("discord", DiscordAdapter,
                     ["discord.gg/python", "https://discord.com/invite/openai", "267624335836053506"],
                     max_targets=10, input_types=["invite", "guild"])
