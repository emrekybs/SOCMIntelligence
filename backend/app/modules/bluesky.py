"""
Bluesky OSINT modulu - SOCMIntelligence platformu.

Tool: tools/bluesky_osint.py (AT Protocol public API; oturum/anahtar gerekmez)
  Input: handle (nasa.gov), @handle, DID (did:plc:...) veya bsky.app profil URL'si
Graph: kisi + Bluesky hesabi, bahsedilen hesaplar, etiketler, paylasilan alan adlari.
"""
from __future__ import annotations

import re
from typing import Any

from app.core.adapter import PlatformAdapter
from app.modules._common import G, make_router, raise_tool_error, slug


class BlueskyAdapter(PlatformAdapter):
    platform = "bluesky"
    script = "bluesky_osint.py"
    capabilities = ["scan"]
    cache_ttl = 600

    def classify(self, raw: str) -> tuple[str, str]:
        t = (raw or "").strip()
        if not t:
            raise ValueError("Bos input")
        m = re.search(r"bsky\.app/profile/([^/?#\s]+)", t, re.I)
        if m:
            t = m.group(1)
        t = t.strip("/").lstrip("@")
        if t.startswith("did:"):
            if not re.match(r"^did:[a-z0-9]+:[A-Za-z0-9._%-]+$", t):
                raise ValueError(f"Gecersiz Bluesky DID: {raw}")
            return ("did", t)
        if not re.match(r"^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)+$", t):
            raise ValueError(f"Gecersiz Bluesky handle: {raw}")
        return ("handle", t.lower())

    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        result = await self._run_tool(target_type, value, [value], timeout=120)
        raise_tool_error(result, "Bluesky")
        return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return BlueskyGraphConverter.convert(data)


class BlueskyGraphConverter:
    @staticmethod
    def convert(d: dict[str, Any]) -> dict[str, list]:
        g = G()
        h = d.get("handle")
        if not h:
            return g.export()
        pid = g.node(f"p_bluesky_{slug(h)}", "person", d.get("display_name") or h, {
            "Platform": "Bluesky", "Kullanıcı adı": h, "DID": d.get("did"), "Bio": (d.get("description") or "")[:160],
            "Takipçi": d.get("followers"), "Takip": d.get("following"), "Gönderi": d.get("posts_count"),
            "Oluşturma": (d.get("created_at") or "")[:10], "Profil": d.get("url"),
        })
        g.social(pid, "bluesky", h, d.get("url"), etype="owns", source="Bluesky")
        for e in d.get("emails") or []:
            g.email(pid, e, "Bluesky bio")
        for m in (d.get("mentions") or [])[:30]:
            if m.get("handle"):
                g.social(pid, "bluesky", m["handle"], f"https://bsky.app/profile/{m['handle']}",
                         etype="mentioned", source="Bluesky gönderileri", extra={"Bahsetme": m.get("count")})
        for dm in (d.get("domains") or [])[:20]:
            if dm.get("domain"):
                g.domain(pid, dm["domain"], "Bluesky gönderileri", weight=dm.get("count"))
        for h2 in (d.get("hashtags") or [])[:15]:
            g.hashtag(pid, h2.get("hashtag", ""), "Bluesky", weight=h2.get("count"))
        return g.export()


router = make_router("bluesky", BlueskyAdapter,
                     ["nasa.gov", "@jay.bsky.team", "https://bsky.app/profile/bsky.app"],
                     max_targets=10, input_types=["handle", "did"])
