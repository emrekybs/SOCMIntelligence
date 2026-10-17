"""
X (Twitter) OSINT modulu - SOCMIntelligence platformu.

Tool: tools/x_osint.py
  Resmi X API v2 (X_BEARER_TOKEN varsa gercek veri; yoksa acikca isaretli ornek veri).
Graph: kisi + kullanici adi + bahsedilen hesaplar + etiketler + alan adlari + e-postalar.
"""
from __future__ import annotations

import re
from typing import Any

from app.core.adapter import PlatformAdapter
from app.modules._common import G, make_router, raise_tool_error, slug


class XAdapter(PlatformAdapter):
    platform = "x"
    script = "x_osint.py"
    capabilities = ["scan"]
    cache_ttl = 600
    env_keys = ["X_BEARER_TOKEN"]

    def classify(self, raw: str) -> tuple[str, str]:
        t = (raw or "").strip()
        if not t:
            raise ValueError("Bos input")
        m = re.search(r"(?:twitter|x)\.com/(?!intent|share|home|search|hashtag|i/)([A-Za-z0-9_]{1,15})", t)
        if m:
            return ("username", m.group(1))
        t = t.lstrip("@")
        if not re.match(r"^[A-Za-z0-9_]{1,15}$", t):
            raise ValueError(f"Gecersiz X kullanici adi: {raw}")
        return ("username", t)

    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        result = await self._run_tool(target_type, value, [value, "--tweets", "40"],
                                      env_keys=self.env_keys, timeout=90)
        raise_tool_error(result, "X")
        return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return XGraphConverter.convert(data)


class XGraphConverter:
    @staticmethod
    def convert(d: dict[str, Any]) -> dict[str, list]:
        g = G()
        u = d.get("username")
        if not u:
            return g.export()
        note = "ÖRNEK VERİ" if d.get("mock") else None
        pid = g.node(f"p_twitter_{slug(u)}", "person", d.get("name") or u, {
            "Platform": "X (Twitter)", "Kullanıcı adı": u, "Bio": (d.get("bio") or "")[:160],
            "Konum": d.get("location"), "Takipçi": d.get("followers"), "Takip": d.get("following"),
            "Gönderi": d.get("tweet_count"), "Doğrulanmış": "Evet" if d.get("verified") else None,
            "Oluşturma": (d.get("created_at") or "")[:10], "Profil": d.get("url"), "Not": note,
        })
        uid = g.node(f"u_twitter_{slug(u)}", "username", f"@{u}",
                     {"Platforms": "X (Twitter)", "URL": d.get("url"), "Not": note})
        g.edge(pid, uid, "owns")
        if d.get("website"):
            g.domain(pid, d["website"], "X bio", "linked_to")
        for e in d.get("emails") or []:
            g.email(pid, e, "X bio")
        for m in d.get("mentions") or []:
            mid = g.social(pid, "twitter", m.get("handle"), url=f"https://x.com/{m.get('handle')}",
                           etype="mentioned", source="X gönderileri")
            if mid and m.get("count"):
                g.edge(pid, mid, "mentioned", m["count"])
        for t in d.get("hashtags") or []:
            g.hashtag(pid, t.get("tag"), "X (Twitter)", t.get("count"))
        for dom in d.get("domains") or []:
            g.domain(pid, dom.get("domain"), "X gönderileri", "posted", dom.get("count"))
        return g.export()


router = make_router("x", XAdapter, ["nasa", "@github", "https://x.com/jack"],
                     input_types=["username"], requires_env=["X_BEARER_TOKEN"])
