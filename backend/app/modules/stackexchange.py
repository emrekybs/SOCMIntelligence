"""
Stack Exchange OSINT modulu - SOCMIntelligence platformu.

Tool: tools/stackexchange_osint.py (STACKEXCHANGE_KEY opsiyonel)
  Input: profil URL'si, site:id (superuser:123), sayisal id (stackoverflow) veya ad
Graph: profil + ag genelindeki diger SE hesaplari + yanit verdigi soru sahipleri + etiketler + sosyal hesaplar
"""
from __future__ import annotations

import re
from typing import Any

from app.core.adapter import PlatformAdapter
from app.modules._common import G, make_router, raise_tool_error, slug

SITE_MAP = {"stackoverflow.com": "stackoverflow", "superuser.com": "superuser", "serverfault.com": "serverfault",
            "askubuntu.com": "askubuntu", "mathoverflow.net": "mathoverflow.net", "stackapps.com": "stackapps"}


def site_key(url_or_host: str) -> str:
    host = re.sub(r"^https?://", "", url_or_host or "").split("/")[0].lower().replace("www.", "")
    if host in SITE_MAP:
        return SITE_MAP[host]
    if host.endswith(".stackexchange.com"):
        return host.split(".stackexchange.com")[0]
    return host.split(".")[0] or "stackoverflow"


class StackExchangeAdapter(PlatformAdapter):
    platform = "stackexchange"
    script = "stackexchange_osint.py"
    capabilities = ["scan"]
    cache_ttl = 1800

    def classify(self, raw: str) -> tuple[str, str]:
        t = (raw or "").strip()
        if not t:
            raise ValueError("Bos input")
        m = re.search(r"https?://([A-Za-z0-9.\-]+)/users/(-?\d+)", t)
        if m:
            return ("id", f"{site_key(m.group(1))}:{m.group(2)}")
        m = re.match(r"^([a-z.\-]+):(\d+)$", t, re.I)
        if m:
            return ("id", f"{m.group(1).lower()}:{m.group(2)}")
        if t.isdigit():
            return ("id", f"stackoverflow:{t}")
        if len(t) < 2 or len(t) > 60:
            raise ValueError(f"Gecersiz hedef: {raw}")
        return ("name", t)

    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        result = await self._run_tool(target_type, value, [value], timeout=90)
        raise_tool_error(result, "Stack Exchange")
        return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return StackExchangeGraphConverter.convert(data)


class StackExchangeGraphConverter:
    @staticmethod
    def convert(d: dict[str, Any]) -> dict[str, list]:
        g = G()
        uid_ = d.get("user_id")
        site = d.get("site") or "stackoverflow"
        if not uid_:
            return g.export()
        pid = g.node(f"p_se_{slug(site)}_{uid_}", "person", d.get("display_name") or str(uid_), {
            "Platform": f"Stack Exchange ({site})", "Reputation": d.get("reputation"), "Location": d.get("location"),
            "Created": (d.get("created") or "")[:10], "Account_ID": d.get("account_id"), "Profile": d.get("link"),
        })
        uid = g.node(f"u_se_{slug(site)}_{uid_}", "username", d.get("display_name") or str(uid_), {"Platforms": f"Stack Exchange ({site})", "Profile": d.get("link")})
        g.edge(pid, uid, "owns")
        for n in d.get("network") or []:
            sk = site_key(n.get("site_url") or "")
            if sk == slug(site) and n.get("user_id") == uid_:
                continue
            nid = g.node(f"u_se_{slug(sk)}_{n.get('user_id')}", "username", f"{d.get('display_name')} · {n.get('site')}", {
                "Platforms": f"Stack Exchange ({n.get('site')})", "Profile": n.get("link"), "Reputation": n.get("reputation"),
                "Source": "Aynı Stack Exchange hesabı (account_id)"})
            g.edge(pid, nid, "owns")
        for a in (d.get("answered_users") or [])[:25]:
            oid = g.node(f"u_se_{slug(site)}_{a['user_id']}", "username", a.get("name") or str(a["user_id"]), {
                "Platforms": f"Stack Exchange ({site})", "Profile": a.get("link"), "Source": "Sorusuna yanıt verdiği kullanıcı"})
            g.edge(pid, oid, "replied", a.get("count"))
        for t in (d.get("top_tags") or [])[:10]:
            g.hashtag(pid, t.get("tag"), f"Stack Exchange ({site})", t.get("answers"), etype="interest")
        for s in d.get("socials") or []:
            g.social(pid, s["platform"], s["handle"], s.get("url"), source="Stack Exchange profili")
        if d.get("website"):
            g.domain(pid, d["website"], "Stack Exchange web sitesi", "owns")
        for e in d.get("about_emails") or []:
            g.email(pid, e, "Stack Exchange about")
        return g.export()


router = make_router("stackexchange", StackExchangeAdapter,
                     ["https://stackoverflow.com/users/22656/jon-skeet", "22656", "superuser:12345", "Jon Skeet"],
                     input_types=["id", "name"], requires_env=["STACKEXCHANGE_KEY (opsiyonel)"])
