"""
LinkedIn OSINT modulu - SOCMIntelligence platformu.

Tool: tools/linkedin_osint.py
  Input: profil URL'si (linkedin.com/in/kullanici) veya profil kisa adi
  Kaynak: herkese acik (oturumsuz) profil sayfasi + Wayback Machine kopyalari. Oturum/cerez kullanilmaz.
Graph: kisi + LinkedIn hesabi, sirketler, okullar, konum, bio'daki sosyal hesaplar / e-postalar / alan adlari
"""
from __future__ import annotations

import re
from typing import Any

from app.core.adapter import PlatformAdapter
from app.modules._common import G, make_router, raise_tool_error, slug


class LinkedInAdapter(PlatformAdapter):
    platform = "linkedin"
    script = "linkedin_osint.py"
    capabilities = ["scan"]
    cache_ttl = 3600

    def classify(self, raw: str) -> tuple[str, str]:
        t = (raw or "").strip()
        if not t:
            raise ValueError("Bos input")
        m = re.search(r"linkedin\.com/(?:mwlite/)?(in|company|school)/([^/?#\s]+)", t, re.I)
        if m:
            if m.group(1).lower() != "in":
                raise ValueError("Sadece kisi profilleri (linkedin.com/in/...) destekleniyor")
            t = m.group(2)
        elif "/" in t or " " in t:
            raise ValueError(f"Gecersiz LinkedIn profil adresi: {raw}")
        t = t.strip("/").lstrip("@")
        if not re.match(r"^[A-Za-z0-9\-_%.]{2,100}$", t):
            raise ValueError(f"Gecersiz LinkedIn profil adresi: {raw}")
        return ("profile", t)

    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        result = await self._run_tool(target_type, value, [value], timeout=150)
        raise_tool_error(result, "LinkedIn")
        return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return LinkedInGraphConverter.convert(data)


class LinkedInGraphConverter:
    @staticmethod
    def convert(d: dict[str, Any]) -> dict[str, list]:
        g = G()
        s = d.get("slug")
        if not s:
            return g.export()
        src = "LinkedIn (canlı)" if d.get("source_used") == "live" else f"LinkedIn — Wayback {d.get('source_date') or ''}".strip()
        pid = g.node(f"p_linkedin_{slug(s)}", "person", d.get("name") or s, {
            "Platform": "LinkedIn", "Unvan": d.get("headline"), "Konum": d.get("location"),
            "Takipçi": d.get("followers"), "Bağlantı": d.get("connections"), "Profil": d.get("url"), "Kaynak": src,
        })
        g.social(pid, "linkedin", s, d.get("url"), etype="owns", source=src)

        def org(o: dict, etype: str, kind: str):
            name = o.get("name")
            if not name:
                return
            oid = g.node(f"org_{slug(name)}", "community", name, {"Tür": kind, "URL": o.get("url"), "Konum": o.get("location")})
            g.edge(pid, oid, etype)
            if o.get("url") and "linkedin.com" not in o["url"]:
                g.domain(oid, o["url"], src)

        for o in d.get("current") or []:
            org(o, "member_of", "Şirket (güncel)")
        for o in d.get("experience") or []:
            org(o, "linked_to", "Şirket (geçmiş)")
        for o in d.get("education") or []:
            org(o, "linked_to", "Okul")
        for o in d.get("member_of") or []:
            org(o, "member_of", "Kuruluş")
        for so in d.get("socials") or []:
            g.social(pid, so["platform"], so["handle"], so.get("url"), source=f"LinkedIn hakkında ({so.get('first_seen') or ''})".strip())
        for e in d.get("emails") or []:
            g.email(pid, e, "LinkedIn hakkında", etype="linked_to")
        for u in d.get("urls") or []:
            g.domain(pid, u, "LinkedIn hakkında")
        for a in (d.get("articles") or [])[:15]:
            if a.get("title"):
                cid = g.node(f"c_li_{slug(a.get('url') or a['title'])}", "content", a["title"][:80],
                             {"Tür": "LinkedIn yazısı", "Tarih": (a.get("date") or "")[:10], "URL": a.get("url")})
                g.edge(pid, cid, "posted")
        return g.export()


router = make_router("linkedin", LinkedInAdapter,
                     ["https://www.linkedin.com/in/williamhgates", "linkedin.com/in/satyanadella", "williamhgates"],
                     max_targets=5, input_types=["profile"])
