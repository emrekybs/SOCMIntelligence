"""
Kick OSINT modulu - SOCMIntelligence platformu.

Tool: tools/kick_osint.py (v2 public; Cloudflare korumasi nedeniyle engellenebilir)
Graph: kisi + Kick hesabi, yayin kategorileri, bio/beyan edilen sosyal hesaplar.
"""
from __future__ import annotations

import re
from typing import Any

from app.core.adapter import PlatformAdapter
from app.modules._common import G, make_router, raise_tool_error, slug


class KickAdapter(PlatformAdapter):
    platform = "kick"
    script = "kick_osint.py"
    capabilities = ["scan"]
    cache_ttl = 600

    def classify(self, raw: str) -> tuple[str, str]:
        t = (raw or "").strip()
        if not t:
            raise ValueError("Bos input")
        m = re.search(r"kick\.com/([^/?#\s]+)", t, re.I)
        if m:
            t = m.group(1)
        t = t.strip("/").lstrip("@").lower()
        if not re.match(r"^[a-z0-9_]{2,25}$", t):
            raise ValueError(f"Gecersiz Kick kullanici adi: {raw}")
        return ("username", t)

    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        result = await self._run_tool(target_type, value, [value], timeout=90)
        raise_tool_error(result, "Kick")
        return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return KickGraphConverter.convert(data)


class KickGraphConverter:
    @staticmethod
    def convert(d: dict[str, Any]) -> dict[str, list]:
        g = G()
        s = d.get("slug")
        if not s:
            return g.export()
        pid = g.node(f"p_kick_{slug(s)}", "person", d.get("username") or s, {
            "Platform": "Kick", "Kullanıcı adı": s, "Bio": (d.get("bio") or "")[:160],
            "Takipçi": d.get("followers"), "Doğrulanmış": "Evet" if d.get("verified") else None,
            "Profil": d.get("url"),
        })
        g.social(pid, "kick", s, d.get("url"), etype="owns", source="Kick")
        for c in (d.get("recent_categories") or [])[:15]:
            cid = g.node(f"game_{slug(c)}", "content", c, {"Tür": "Oyun / kategori"})
            g.edge(pid, cid, "interest")
        for plat, handle in (d.get("declared_socials") or {}).items():
            g.social(pid, plat, handle, source="Kick beyan edilen")
        for so in d.get("socials") or []:
            if so["platform"] != "kick":
                g.social(pid, so["platform"], so["handle"], so.get("url"), etype="linked_to", source="Kick bio")
        for e in d.get("emails") or []:
            g.email(pid, e, "Kick bio")
        for dm in d.get("domains") or []:
            g.domain(pid, dm, "Kick bio")
        return g.export()


router = make_router("kick", KickAdapter, ["xqc", "@trainwreckstv", "https://kick.com/adin"],
                     max_targets=10, input_types=["username"])
