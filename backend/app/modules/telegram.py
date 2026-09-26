"""
Telegram OSINT modulu - SOCMIntelligence platformu.

Tool: tools/telegram_osint.py (t.me herkese acik sayfalari, API anahtari gerekmez)
  Input: durov, @durov, t.me/durov, https://t.me/s/kanal
Graph: kanal/kullanici + iletilen kaynak kanallar + bahsedilen hesaplar + etiketler + dis alan adlari
"""
from __future__ import annotations

import re
from typing import Any

from app.core.adapter import PlatformAdapter
from app.modules._common import G, make_router, raise_tool_error, slug


class TelegramAdapter(PlatformAdapter):
    platform = "telegram"
    script = "telegram_osint.py"
    capabilities = ["scan"]
    cache_ttl = 600

    def classify(self, raw: str) -> tuple[str, str]:
        t = (raw or "").strip().rstrip("/")
        if not t:
            raise ValueError("Bos input")
        m = re.search(r"(?:t\.me|telegram\.me|telegram\.dog)/(?:s/)?([A-Za-z0-9_]{4,32})", t, re.I)
        if m:
            return ("username", m.group(1))
        t = t.lstrip("@")
        if not re.match(r"^[A-Za-z][A-Za-z0-9_]{3,31}$", t):
            raise ValueError(f"Gecersiz Telegram kullanici adi: {raw}")
        return ("username", t)

    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        result = await self._run_tool(target_type, value, [value, "--pages", "4"], timeout=120)
        raise_tool_error(result, "Telegram")
        return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return TelegramGraphConverter.convert(data)


class TelegramGraphConverter:
    KIND = {"channel": "Kanal", "group": "Grup", "user": "Kullanıcı", "bot": "Bot"}

    @staticmethod
    def convert(d: dict[str, Any]) -> dict[str, list]:
        g = G()
        u = d.get("username")
        if not u:
            return g.export()
        a = d.get("analysis") or {}
        pid = g.node(f"p_telegram_{slug(u)}", "person", d.get("title") or u, {
            "Platform": "Telegram", "Tür": TelegramGraphConverter.KIND.get(d.get("kind"), d.get("kind")),
            "Subscribers": d.get("subscribers"), "Verified": "Yes" if d.get("verified") else "No",
            "Description": (d.get("description") or "")[:160], "Posts_analyzed": a.get("posts_analyzed"),
        })
        uid = g.node(f"u_telegram_{slug(u)}", "username", f"@{u}", {"Platforms": "Telegram", "Profile": d.get("url")})
        g.edge(pid, uid, "owns")
        for src, cnt in (a.get("top_forward_sources") or {}).items():
            if src and src != "?" and re.match(r"^[A-Za-z0-9_]{4,32}$", src):
                sid = g.node(f"u_telegram_{slug(src)}", "username", f"@{src}", {"Platforms": "Telegram", "Profile": f"https://t.me/{src}",
                                                                              "Source": f"@{u} kanalına iletilen gönderi kaynağı"})
                g.edge(pid, sid, "forwarded", cnt)
        for m, cnt in (a.get("top_mentions") or {}).items():
            mid = g.node(f"u_telegram_{slug(m)}", "username", f"@{m}", {"Platforms": "Telegram", "Profile": f"https://t.me/{m}"})
            g.edge(pid, mid, "mentioned", cnt)
        for m in d.get("description_mentions") or []:
            mid = g.node(f"u_telegram_{slug(m)}", "username", f"@{m}", {"Platforms": "Telegram", "Profile": f"https://t.me/{m}", "Source": "Açıklama"})
            g.edge(pid, mid, "mentioned")
        for tag, cnt in list((a.get("top_hashtags") or {}).items())[:12]:
            g.hashtag(pid, tag, "Telegram", cnt)
        for dom, cnt in list((a.get("top_domains") or {}).items())[:12]:
            g.domain(pid, dom, "Telegram gönderi linkleri", "linked_to", cnt)
        for s in d.get("description_socials") or []:
            if s.get("platform") == "telegram":
                continue
            g.social(pid, s["platform"], s["handle"], s.get("url"), source="Telegram açıklaması")
        for e in d.get("description_emails") or []:
            g.email(pid, e, "Telegram açıklaması")
        return g.export()


router = make_router("telegram", TelegramAdapter, ["durov", "@durov", "https://t.me/durov", "https://t.me/s/telegram"],
                     input_types=["username"])
