"""
Wayback Machine OSINT modulu - SOCMIntelligence platformu.

Tool: tools/wayback_osint.py (CDX API + arsiv kopyalarinin icerigi)
  Input: alan adi (example.com) veya URL (profil sayfasi dahil: https://x.com/kullanici)
Graph: hedef sayfa/alan adi + arsiv kopyalarinda gecen e-postalar, sosyal hesaplar, dis alan adlari
"""
from __future__ import annotations

import re
from typing import Any

from app.core.adapter import PlatformAdapter
from app.modules._common import G, make_router, raise_tool_error, slug


class WaybackAdapter(PlatformAdapter):
    platform = "wayback"
    script = "wayback_osint.py"
    capabilities = ["scan"]
    cache_ttl = 3600

    def classify(self, raw: str) -> tuple[str, str]:
        t = (raw or "").strip()
        if not t or " " in t:
            raise ValueError("Bos veya gecersiz input")
        bare = re.sub(r"^https?://", "", t, flags=re.I).rstrip("/")
        if not re.match(r"^[A-Za-z0-9.\-]+\.[A-Za-z]{2,}(?::\d+)?(/.*)?$", bare):
            raise ValueError(f"Gecersiz URL / alan adi: {raw}")
        return ("domain" if "/" not in bare else "url", bare)

    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        result = await self._run_tool(target_type, value, [value], timeout=150)
        raise_tool_error(result, "Wayback Machine")
        return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return WaybackGraphConverter.convert(data)


class WaybackGraphConverter:
    @staticmethod
    def convert(d: dict[str, Any]) -> dict[str, list]:
        g = G()
        target = d.get("target")
        if not target:
            return g.export()
        meta = {"Source": "Wayback Machine", "Captures": d.get("total_captures"), "First": d.get("first_capture"),
                "Last": d.get("last_capture"), "Versions": d.get("unique_versions"), "URL": d.get("last_capture_url")}
        if d.get("is_domain"):
            anchor = g.node(f"d_ext_{slug(target.split(':')[0])}", "domain", target, meta)
        else:
            anchor = g.node(f"c_wb_{slug(target)}", "content", target, {"Tür": "Arşivlenmiş sayfa", **meta})
            dom = target.split("/")[0]
            did = g.node(f"d_ext_{slug(dom)}", "domain", dom, {"Source": "Wayback hedefi"})
            g.edge(anchor, did, "appears_in")
        for s in d.get("socials") or []:
            g.social(anchor, s["platform"], s["handle"], s.get("url"), source=f"Wayback arşivi ({s.get('first_seen') or ''})".strip(),
                     extra={"İlk_görülme": s.get("first_seen")})
        for e in d.get("emails") or []:
            g.email(anchor, e, "Wayback arşivi", etype="linked_to")
        doms = {}
        for sn in d.get("snapshots") or []:
            for k, v in (sn.get("domains") or {}).items():
                doms[k] = doms.get(k, 0) + v
        for k, v in sorted(doms.items(), key=lambda x: -x[1])[:12]:
            g.domain(anchor, k, "Wayback arşivindeki dış bağlantı", "linked_to", v)
        return g.export()


router = make_router("wayback", WaybackAdapter, ["example.com", "https://example.com/about", "https://twitter.com/jack"],
                     input_types=["domain", "url"])
