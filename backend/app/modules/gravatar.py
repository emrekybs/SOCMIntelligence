"""
Gravatar OSINT modulu - SOCMIntelligence platformu.

Tool: tools/gravatar_osint.py
  Input: e-posta, MD5/SHA-256 hash, gravatar kullanici adi veya gravatar.com/... URL'si
Graph: e-posta -> profil -> dogrulanmis hesaplar, linkler, kripto adresleri
"""
from __future__ import annotations

import re
from typing import Any

from app.core.adapter import PlatformAdapter
from app.modules._common import G, make_router, raise_tool_error, slug


class GravatarAdapter(PlatformAdapter):
    platform = "gravatar"
    script = "gravatar_osint.py"
    capabilities = ["scan"]
    cache_ttl = 1800

    def classify(self, raw: str) -> tuple[str, str]:
        t = (raw or "").strip()
        if not t:
            raise ValueError("Bos input")
        m = re.search(r"gravatar\.com/([A-Za-z0-9._\-]+)", t, re.I)
        if m and m.group(1).lower() not in ("avatar", "profile"):
            t = m.group(1)
        if re.match(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$", t):
            return ("email", t.lower())
        if re.fullmatch(r"[a-fA-F0-9]{32}|[a-fA-F0-9]{64}", t):
            return ("hash", t.lower())
        t = t.lstrip("@")
        if not re.match(r"^[A-Za-z0-9._\-]{2,64}$", t):
            raise ValueError(f"Gecersiz Gravatar hedefi: {raw}")
        return ("username", t)

    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        result = await self._run_tool(target_type, value, [value], timeout=60)
        raise_tool_error(result, "Gravatar")
        return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return GravatarGraphConverter.convert(data)


class GravatarGraphConverter:
    @staticmethod
    def convert(d: dict[str, Any]) -> dict[str, list]:
        g = G()
        key = d.get("username") or d.get("md5") or d.get("sha256") or d.get("input")
        if not key:
            return g.export()
        pid = g.node(f"p_gravatar_{slug(key)}", "person", d.get("display_name") or d.get("name") or d.get("username") or d.get("input"), {
            "Platform": "Gravatar", "Location": d.get("location"), "Company": d.get("company"), "Job": d.get("job_title"),
            "About": (d.get("about") or "")[:160], "Avatar": "Var" if d.get("has_avatar") else "Yok", "MD5": d.get("md5"),
            "Profile": d.get("profile_url"),
        })
        if d.get("email"):
            g.email(pid, d["email"], "Gravatar sorgusu (girdi)")
        if d.get("username"):
            uid = g.node(f"u_gravatar_{slug(d['username'])}", "username", f"@{d['username']}", {"Platforms": "Gravatar", "Profile": d.get("profile_url")})
            g.edge(pid, uid, "owns")
        for a in d.get("accounts") or []:
            plat = (a.get("type") or a.get("service") or "").lower()
            handle = a.get("username")
            if a.get("url") and plat == "mastodon":
                m = re.search(r"https?://([^/]+)/@([A-Za-z0-9_]+)", a["url"])
                handle = f"{m.group(2)}@{m.group(1)}" if m else handle
            if handle:
                g.social(pid, plat or "link", handle, a.get("url"), etype="verified" if a.get("verified") else "linked_to", source="Gravatar hesapları")
            elif a.get("url"):
                g.domain(pid, a["url"], "Gravatar hesapları")
        for l in d.get("links") or []:
            if l.get("url"):
                g.domain(pid, l["url"], f"Gravatar linki: {l.get('title') or ''}".strip())
        for s in d.get("socials") or []:
            g.social(pid, s["platform"], s["handle"], s.get("url"), source="Gravatar profili")
        for c in d.get("crypto") or []:
            if c.get("address"):
                aid = g.node(f"a_crypto_{slug(c['address'])}", "artifact", c["address"][:18], {"Tür": f"Kripto ({c.get('label') or '?'})", "Adres": c["address"]})
                g.edge(pid, aid, "owns")
        for ph in d.get("phones") or []:
            aid = g.node(f"a_phone_{slug(ph)}", "artifact", ph, {"Tür": "Telefon", "Source": "Gravatar"})
            g.edge(pid, aid, "owns")
        for e in d.get("emails") or []:
            if e != d.get("email"):
                g.email(pid, e, "Gravatar profili")
        return g.export()


router = make_router("gravatar", GravatarAdapter, ["kisi@ornek.com", "205e460b479e2e5b48aec07710c08d50", "beau", "https://gravatar.com/beau"],
                     input_types=["email", "hash", "username"])
