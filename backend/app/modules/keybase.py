"""
Keybase OSINT modulu - SOCMIntelligence platformu.

Tool: tools/keybase_osint.py
  Input: chris, keybase.io/chris, github:kullanici, twitter:kullanici, reddit:, hackernews:, domain:
Graph: kriptografik kanitla dogrulanmis hesaplar ("kanıtlı bağ"), PGP anahtari, kripto adresleri,
       takipci / takip edilenler.
"""
from __future__ import annotations

import re
from typing import Any

from app.core.adapter import PlatformAdapter
from app.modules._common import G, make_router, raise_tool_error, slug

PROOF_PLATFORM = {"twitter": "twitter", "github": "github", "reddit": "reddit", "hackernews": "hackernews", "facebook": "facebook"}


class KeybaseAdapter(PlatformAdapter):
    platform = "keybase"
    script = "keybase_osint.py"
    capabilities = ["scan"]
    cache_ttl = 900

    def classify(self, raw: str) -> tuple[str, str]:
        t = (raw or "").strip().rstrip("/")
        if not t:
            raise ValueError("Bos input")
        m = re.search(r"keybase\.io/([A-Za-z0-9_]{2,16})", t, re.I)
        if m:
            return ("username", m.group(1))
        m = re.match(r"^(github|twitter|reddit|hackernews|domain|facebook)\s*:\s*(\S+)$", t, re.I)
        if m:
            return (m.group(1).lower(), m.group(2).lstrip("@"))
        t = t.lstrip("@")
        if not re.match(r"^[A-Za-z0-9_]{2,16}$", t):
            raise ValueError(f"Gecersiz Keybase hedefi: {raw}")
        return ("username", t)

    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        arg = value if target_type == "username" else f"{target_type}:{value}"
        result = await self._run_tool(target_type, value, [arg], timeout=60)
        raise_tool_error(result, "Keybase")
        return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return KeybaseGraphConverter.convert(data)


class KeybaseGraphConverter:
    @staticmethod
    def convert(d: dict[str, Any]) -> dict[str, list]:
        g = G()
        u = d.get("username")
        if not u:
            return g.export()
        pid = g.node(f"p_keybase_{slug(u)}", "person", d.get("full_name") or u, {
            "Platform": "Keybase", "Username": u, "Location": d.get("location"), "Bio": (d.get("bio") or "")[:160],
            "Created": (d.get("created") or "")[:10], "Proofs": len(d.get("proofs") or []),
        })
        uid = g.node(f"u_keybase_{slug(u)}", "username", f"@{u}", {"Platforms": "Keybase", "Profile": d.get("profile_url")})
        g.edge(pid, uid, "owns")
        for p in d.get("proofs") or []:
            ptype, tag = (p.get("type") or "").lower(), p.get("nametag")
            if not tag:
                continue
            meta = {"Kanıt": p.get("proof_url") or p.get("human_url"), "Durum": "Geçerli" if p.get("state") == 1 else f"state={p.get('state')}"}
            if ptype in PROOF_PLATFORM:
                g.social(pid, PROOF_PLATFORM[ptype], tag, p.get("service_url"), etype="verified", source="Keybase kanıtı", extra=meta)
            elif ptype in ("generic_web_site", "dns") or "." in tag:
                nid = g.node(f"d_ext_{slug(tag)}", "domain", tag, {"Source": "Keybase alan adı kanıtı", **meta})
                g.edge(pid, nid, "verified")
            else:
                g.social(pid, ptype, tag, p.get("service_url"), etype="verified", source="Keybase kanıtı", extra=meta)
        for k in d.get("pgp_keys") or []:
            fp = k.get("fingerprint")
            if fp:
                aid = g.node(f"a_pgp_{slug(fp[-16:])}", "artifact", fp[-16:].upper(), {"Tür": "PGP anahtarı", "Parmak izi": fp.upper()})
                g.edge(pid, aid, "owns")
        for coin, addrs in (d.get("crypto") or {}).items():
            for ad in addrs[:3]:
                aid = g.node(f"a_crypto_{slug(ad)}", "artifact", ad[:18], {"Tür": f"Kripto ({coin})", "Adres": ad})
                g.edge(pid, aid, "owns")
        for e in d.get("bio_emails") or []:
            g.email(pid, e, "Keybase bio")
        for s in d.get("bio_socials") or []:
            g.social(pid, s["platform"], s["handle"], s.get("url"), source="Keybase bio")
        for f in (d.get("followers") or [])[:40]:
            fid = g.node(f"u_keybase_{slug(f['username'])}", "username", f"@{f['username']}", {
                "Platforms": "Keybase", "Display_Name": f.get("full_name"), "Profile": f"https://keybase.io/{f['username']}"})
            g.edge(fid, uid, "follows")
        for f in (d.get("following") or [])[:40]:
            fid = g.node(f"u_keybase_{slug(f['username'])}", "username", f"@{f['username']}", {
                "Platforms": "Keybase", "Display_Name": f.get("full_name"), "Profile": f"https://keybase.io/{f['username']}"})
            g.edge(uid, fid, "follows")
        return g.export()


router = make_router("keybase", KeybaseAdapter, ["chris", "https://keybase.io/chris", "github:torvalds", "twitter:jack"],
                     input_types=["username", "github", "twitter", "reddit", "hackernews", "domain"])
