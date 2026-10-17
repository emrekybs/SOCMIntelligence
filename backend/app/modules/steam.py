"""
Steam OSINT modulu - SOCMIntelligence platformu.

Tool: tools/steam_osint.py  (STEAM_API_KEY opsiyonel)
  Input: ozel URL adi, 17 haneli SteamID64, steamcommunity.com/id/.. veya /profiles/..
Graph: profil + arkadaslar + gruplar + profil ozetindeki sosyal hesaplar
"""
from __future__ import annotations

import re
from typing import Any

from app.core.adapter import PlatformAdapter
from app.modules._common import G, make_router, raise_tool_error, slug


class SteamAdapter(PlatformAdapter):
    platform = "steam"
    script = "steam_osint.py"
    capabilities = ["scan"]
    cache_ttl = 900

    def classify(self, raw: str) -> tuple[str, str]:
        t = (raw or "").strip().rstrip("/")
        if not t:
            raise ValueError("Bos input")
        m = re.search(r"steamcommunity\.com/profiles/(\d{17})", t)
        if m:
            return ("id64", m.group(1))
        m = re.search(r"steamcommunity\.com/id/([A-Za-z0-9_\-]{2,64})", t)
        if m:
            return ("vanity", m.group(1))
        if re.match(r"^7656119\d{10}$", t):
            return ("id64", t)
        t = t.lstrip("@")
        if not re.match(r"^[A-Za-z0-9_\-]{2,64}$", t):
            raise ValueError(f"Gecersiz Steam hedefi: {raw}")
        return ("vanity", t)

    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        result = await self._run_tool(target_type, value, [value], timeout=90)
        raise_tool_error(result, "Steam")
        return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return SteamGraphConverter.convert(data)


class SteamGraphConverter:
    @staticmethod
    def convert(d: dict[str, Any]) -> dict[str, list]:
        g = G()
        sid = d.get("steamid")
        if not sid:
            return g.export()
        handle = d.get("custom_url") or sid
        pid = g.node(f"p_steam_{sid}", "person", d.get("persona") or handle, {
            "Platform": "Steam", "SteamID64": sid, "Real_name": d.get("real_name"), "Location": d.get("location") or d.get("country"),
            "Member_since": d.get("member_since") or (d.get("time_created") or "")[:10], "Privacy": d.get("privacy") or d.get("visibility"),
            "VAC": "Var" if d.get("vac_banned") or ((d.get("bans") or {}).get("vac") or 0) > 0 else "Yok",
            "Eski_adlar": ", ".join(a["name"] for a in (d.get("aliases") or [])[:8]),
        })
        # Kimlik: SteamID64 (arkadas listelerindeki dugumlerle ayni ID) + varsa ozel URL adi
        uid = g.node(f"u_steam_{sid}", "username", d.get("persona") or sid,
                     {"Platforms": "Steam", "Profile": d.get("profile_url"), "SteamID64": sid})
        g.edge(pid, uid, "owns")
        if d.get("custom_url"):
            vid = g.node(f"u_steam_{slug(d['custom_url'])}", "username", f"@{d['custom_url']}",
                         {"Platforms": "Steam", "Profile": f"https://steamcommunity.com/id/{d['custom_url']}", "SteamID64": sid})
            g.edge(pid, vid, "owns")
        for f in (d.get("friends") or [])[:80]:
            fsid = f.get("steamid")
            if not fsid:
                continue
            fid = g.node(f"u_steam_{fsid}", "username", f.get("name") or fsid, {
                "Platforms": "Steam", "SteamID64": fsid, "Profile": f.get("profile_url"), "Friend_since": (f.get("since") or "")[:10], "Country": f.get("country")})
            g.edge(pid, fid, "friend")
        for gr in (d.get("groups") or [])[:25]:
            if not gr.get("id"):
                continue
            gid = g.node(f"c_steamgrp_{gr['id']}", "community", gr.get("name") or gr["id"], {
                "Tür": "Steam grubu", "Members": gr.get("members"), "URL": f"https://steamcommunity.com/groups/{gr.get('url')}" if gr.get("url") else None,
                "Primary": "Evet" if gr.get("primary") else None})
            g.edge(pid, gid, "member_of")
        for s in d.get("summary_socials") or []:
            if s["platform"] != "steam":
                g.social(pid, s["platform"], s["handle"], s.get("url"), source="Steam profil özeti")
        for e in d.get("summary_emails") or []:
            g.email(pid, e, "Steam profil özeti")
        return g.export()


router = make_router("steam", SteamAdapter, ["gabelogannewell", "76561197960287930", "https://steamcommunity.com/id/gabelogannewell"],
                     input_types=["vanity", "id64"], requires_env=["STEAM_API_KEY (opsiyonel)"])
