"""
Hacker News OSINT modulu - SOCMIntelligence platformu.

Tool: tools/hackernews_osint.py (Firebase + Algolia, anahtar gerekmez)
Graph: kullanici + yanit verdigi kullanicilar (agirlikli) + paylastigi alan adlari + about'taki hesaplar
"""
from __future__ import annotations

import re
from typing import Any

from app.core.adapter import PlatformAdapter
from app.modules._common import G, make_router, raise_tool_error, slug


class HackerNewsAdapter(PlatformAdapter):
    platform = "hackernews"
    script = "hackernews_osint.py"
    capabilities = ["scan"]
    cache_ttl = 900

    def classify(self, raw: str) -> tuple[str, str]:
        t = (raw or "").strip()
        if not t:
            raise ValueError("Bos input")
        m = re.search(r"news\.ycombinator\.com/user\?id=([A-Za-z0-9_\-]{2,15})", t)
        if m:
            return ("username", m.group(1))
        t = t.lstrip("@")
        if not re.match(r"^[A-Za-z0-9_\-]{2,15}$", t):
            raise ValueError(f"Gecersiz Hacker News kullanici adi: {raw}")
        return ("username", t)

    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        result = await self._run_tool(target_type, value, [value, "--items", "300"], timeout=120)
        raise_tool_error(result, "Hacker News")
        return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return HackerNewsGraphConverter.convert(data)


class HackerNewsGraphConverter:
    @staticmethod
    def convert(d: dict[str, Any]) -> dict[str, list]:
        g = G()
        u = d.get("username")
        if not u:
            return g.export()
        pid = g.node(f"p_hackernews_{slug(u)}", "person", u, {
            "Platform": "Hacker News", "Karma": d.get("karma"), "Created": (d.get("created") or "")[:10],
            "About": (d.get("about") or "")[:160], "Items": d.get("items_analyzed"),
        })
        uid = g.node(f"u_hackernews_{slug(u)}", "username", u, {"Platforms": "Hacker News", "Profile": d.get("profile_url")})
        g.edge(pid, uid, "owns")
        for other, cnt in list((d.get("replied_to") or {}).items())[:25]:
            oid = g.node(f"u_hackernews_{slug(other)}", "username", other, {"Platforms": "Hacker News",
                                                                          "Profile": f"https://news.ycombinator.com/user?id={other}"})
            g.edge(pid, oid, "replied", cnt)
        for dom, cnt in list((d.get("top_domains") or {}).items())[:12]:
            g.domain(pid, dom, "HN'de paylaştığı linkler", "posted", cnt)
        for s in d.get("about_socials") or []:
            g.social(pid, s["platform"], s["handle"], s.get("url"), source="HN about")
        for e in d.get("about_emails") or []:
            g.email(pid, e, "HN about")
        for l in d.get("about_links") or []:
            g.domain(pid, l, "HN about")
        return g.export()


router = make_router("hackernews", HackerNewsAdapter, ["pg", "dang", "https://news.ycombinator.com/user?id=pg"], input_types=["username"])
