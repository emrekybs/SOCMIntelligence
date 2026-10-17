"""
Hashtag cografi analizi modulu - SOCMIntelligence platformu.

Tool: tools/hashtagmap_osint.py (Instagram/HikerAPI + Bluesky bedava arama)
  Input: bir hashtag (hedef hesap gerekmez)
Graph: hashtag dugumu + birlikte gecen etiketler, en aktif hesaplar, konumlar.
"""
from __future__ import annotations

import re
from typing import Any

from app.core.adapter import PlatformAdapter
from app.modules._common import G, make_router, raise_tool_error, slug


class HashtagMapAdapter(PlatformAdapter):
    platform = "hashtagmap"
    script = "hashtagmap_osint.py"
    capabilities = ["scan"]
    cache_ttl = 900
    env_keys = ["HIKERAPI_TOKEN"]

    def classify(self, raw: str) -> tuple[str, str]:
        t = (raw or "").strip().lstrip("#").strip()
        if not t or " " in t:
            raise ValueError(f"Gecersiz hashtag: {raw}")
        if not re.match(r"^[\w][\w]{0,138}$", t, re.UNICODE):
            raise ValueError(f"Gecersiz hashtag: {raw}")
        return ("hashtag", t)

    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        result = await self._run_tool(target_type, value, [value], env_keys=self.env_keys, timeout=180)
        raise_tool_error(result, "Hashtag")
        return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return HashtagMapGraphConverter.convert(data)


class HashtagMapGraphConverter:
    @staticmethod
    def convert(d: dict[str, Any]) -> dict[str, list]:
        g = G()
        tag = d.get("hashtag")
        if not tag:
            return g.export()
        hid = g.node(f"h_{slug(tag)}", "hashtag", "#" + tag, {
            "Platform": "Hashtag", "Instagram gönderi": d.get("instagram_posts"), "Bluesky gönderi": d.get("bluesky_posts"),
            "Konum etiketli": d.get("geotagged_posts"),
        })
        for c in (d.get("co_hashtags") or [])[:20]:
            cid = g.node(f"h_{slug(c['hashtag'].lstrip('#'))}", "hashtag", c["hashtag"], {"Platform": "Birlikte geçen"})
            g.edge(hid, cid, "tagged", c.get("count"))
        for a in (d.get("top_authors") or [])[:20]:
            if a.get("username"):
                g.social(hid, a.get("platform") or "instagram", a["username"],
                         etype="tagged", source="Hashtag'i kullanan", extra={"Gönderi": a.get("count")})
        for p in (d.get("places") or [])[:20]:
            if p.get("place"):
                pid = g.node(f"loc_ht_{slug(p['place'])}", "domain", p["place"], {"Tür": "Konum", "Gönderi": p.get("count")})
                g.edge(hid, pid, "appears_in", p.get("count"))
        return g.export()


router = make_router("hashtagmap", HashtagMapAdapter,
                     ["osint", "#İstanbul", "siber"],
                     max_targets=5, input_types=["hashtag"], requires_env=["HIKERAPI_TOKEN"])
