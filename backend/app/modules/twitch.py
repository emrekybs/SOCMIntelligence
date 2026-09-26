"""
Twitch OSINT modulu - SOCMIntelligence platformu.

Tool: tools/twitch_osint.py (resmi Helix API; TWITCH_CLIENT_ID + TWITCH_CLIENT_SECRET)
Graph: kisi + Twitch hesabi, oynadigi oyun(lar), bio'daki sosyal hesaplar / alan adlari.
"""
from __future__ import annotations

import re
from typing import Any

from app.core.adapter import PlatformAdapter
from app.modules._common import G, make_router, raise_tool_error, slug


class TwitchAdapter(PlatformAdapter):
    platform = "twitch"
    script = "twitch_osint.py"
    capabilities = ["scan"]
    cache_ttl = 600
    env_keys = ["TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET"]

    def classify(self, raw: str) -> tuple[str, str]:
        t = (raw or "").strip()
        if not t:
            raise ValueError("Bos input")
        m = re.search(r"twitch\.tv/([^/?#\s]+)", t, re.I)
        if m:
            t = m.group(1)
        t = t.strip("/").lstrip("@").lower()
        if not re.match(r"^[a-z0-9_]{3,25}$", t):
            raise ValueError(f"Gecersiz Twitch kullanici adi: {raw}")
        return ("username", t)

    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        result = await self._run_tool(target_type, value, [value], env_keys=self.env_keys, timeout=90)
        raise_tool_error(result, "Twitch")
        return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return TwitchGraphConverter.convert(data)


class TwitchGraphConverter:
    @staticmethod
    def convert(d: dict[str, Any]) -> dict[str, list]:
        g = G()
        login = d.get("login")
        if not login:
            return g.export()
        note = "ÖRNEK VERİ" if d.get("mock") else None
        ch = d.get("channel") or {}
        pid = g.node(f"p_twitch_{slug(login)}", "person", d.get("display_name") or login, {
            "Platform": "Twitch", "Kullanıcı adı": login, "Tür": d.get("type"), "Bio": (d.get("description") or "")[:160],
            "Takipçi": d.get("followers"), "Oyun": ch.get("game"), "Oluşturma": (d.get("created_at") or "")[:10],
            "Profil": d.get("url"), "Not": note,
        })
        g.social(pid, "twitch", login, d.get("url"), etype="owns", source="Twitch")
        if ch.get("game"):
            gid = g.node(f"game_{slug(ch['game'])}", "content", ch["game"], {"Tür": "Oyun / kategori"})
            g.edge(pid, gid, "interest")
        for s in d.get("socials") or []:
            g.social(pid, s["platform"], s["handle"], s.get("url"), etype="linked_to", source="Twitch bio")
        for e in d.get("emails") or []:
            g.email(pid, e, "Twitch bio")
        for dm in d.get("domains") or []:
            g.domain(pid, dm, "Twitch bio")
        return g.export()


router = make_router("twitch", TwitchAdapter, ["ninja", "@pokimane", "https://twitch.tv/xqc"],
                     max_targets=10, input_types=["username"], requires_env=["TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET"])
