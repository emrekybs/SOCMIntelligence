"""
Instagram OSINT modulu - SOCMIntelligence platformu.

Tool: tools/instagram_osint.py (HikerAPI; oturum/cerez kullanmaz)
  Input: kullanici adi veya profil URL'si
Graph: kisi + Instagram hesabi, isletme iletisimi, bio linkleri, gonderi konumlari,
       yorum yapanlar / etiketleyenler / etiketlenenler, Instagram'in onerdigi iliskili hesaplar.
"""
from __future__ import annotations

import re
from typing import Any

from app.core.adapter import PlatformAdapter
from app.modules._common import G, make_router, raise_tool_error, slug


class InstagramAdapter(PlatformAdapter):
    platform = "instagram"
    script = "instagram_osint.py"
    capabilities = ["scan"]
    cache_ttl = 900
    env_keys = ["HIKERAPI_TOKEN"]

    def classify(self, raw: str) -> tuple[str, str]:
        t = (raw or "").strip()
        if not t:
            raise ValueError("Bos input")
        m = re.search(r"instagram\.com/([^/?#\s]+)", t, re.I)
        if m:
            t = m.group(1)
        t = t.strip("/").lstrip("@").split("?")[0]
        if not re.match(r"^[A-Za-z0-9._]{1,30}$", t):
            raise ValueError(f"Gecersiz Instagram kullanici adi: {raw}")
        return ("username", t)

    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        result = await self._run_tool(target_type, value, [value], env_keys=self.env_keys, timeout=150)
        raise_tool_error(result, "Instagram")
        return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return InstagramGraphConverter.convert(data)


class InstagramGraphConverter:
    @staticmethod
    def convert(d: dict[str, Any]) -> dict[str, list]:
        g = G()
        u = d.get("username")
        if not u:
            return g.export()
        p = d.get("profile") or {}
        about = d.get("about") or {}
        note = "ÖRNEK VERİ" if d.get("mock") else None
        pid = g.node(f"p_instagram_{slug(u)}", "person", p.get("full_name") or u, {
            "Platform": "Instagram", "Kullanıcı adı": u, "Bio": (p.get("biography") or "")[:160],
            "Takipçi": p.get("follower_count"), "Takip": p.get("following_count"), "Gönderi": p.get("media_count"),
            "Doğrulanmış": "Evet" if p.get("is_verified") else None, "Kategori": p.get("category_name") or p.get("category"),
            "Ülke": about.get("country"), "Oluşturma": about.get("date_joined"),
            "Profil": f"https://www.instagram.com/{u}/", "Not": note,
        })
        g.social(pid, "instagram", u, f"https://www.instagram.com/{u}/", etype="owns", source="Instagram")

        # Hesabin KENDI yayinladigi isletme iletisimi
        if p.get("public_email"):
            g.email(pid, p["public_email"], "Instagram işletme iletişimi")
        if p.get("fbid_v2"):
            fid = g.node(f"u_facebook_{slug(p['fbid_v2'])}", "username", f"fb:{p['fbid_v2']}",
                         {"Platforms": "Facebook", "Source": "Instagram bağlı hesap"})
            g.edge(pid, fid, "linked_to")
        for l in p.get("bio_links") or []:
            if l.get("url"):
                g.domain(pid, l["url"], "Instagram bio linki")
        if p.get("external_url"):
            g.domain(pid, p["external_url"], "Instagram bio linki")

        # Gonderi konumlari
        for loc in (d.get("locations") or [])[:20]:
            if loc.get("name"):
                lid = g.node(f"loc_ig_{slug(loc['name'])}", "domain", loc["name"],
                             {"Tür": "Konum", "Enlem": loc.get("lat"), "Boylam": loc.get("lng"), "Tarih": loc.get("time")})
                g.edge(pid, lid, "appears_in")

        # Etkilesen kisiler
        for c in (d.get("top_commenters") or [])[:25]:
            if c.get("username"):
                g.social(pid, "instagram", c["username"], f"https://www.instagram.com/{c['username']}/",
                         etype="commented", source="Instagram yorumları", extra={"Yorum": c.get("count")})
        for tgr in (d.get("tagged_by") or [])[:25]:
            if tgr.get("username"):
                g.social(pid, "instagram", tgr["username"], f"https://www.instagram.com/{tgr['username']}/",
                         etype="mentioned", source="Etiketleyen", extra={"Etiket": tgr.get("count")})
        for tg in (d.get("tagged_users") or [])[:25]:
            if tg.get("username"):
                g.social(pid, "instagram", tg["username"], f"https://www.instagram.com/{tg['username']}/",
                         etype="mentioned", source="Hedefin etiketledikleri", extra={"Etiket": tg.get("count")})
        for s in (d.get("suggested_profiles") or [])[:25]:
            if s.get("username"):
                g.social(pid, "instagram", s["username"], f"https://www.instagram.com/{s['username']}/",
                         etype="related", source="Instagram önerilen hesaplar")

        # Hashtag'ler
        for h in (d.get("hashtags") or [])[:15]:
            g.hashtag(pid, h.get("hashtag", ""), "Instagram", weight=h.get("count"))
        return g.export()


router = make_router("instagram", InstagramAdapter,
                     ["nasa", "@natgeo", "https://www.instagram.com/instagram/"],
                     max_targets=10, input_types=["username"], requires_env=["HIKERAPI_TOKEN"])


@router.get("/card/{username}")
async def instagram_card_png(username: str):
    """Profil kanit karti PNG'si — dis araca gerek yok, arac matplotlib ile cizer."""
    import asyncio
    import tempfile
    from pathlib import Path

    from fastapi import HTTPException, Response

    from app.core.tool_runner import TOOLS_DIR

    try:
        _, clean = InstagramAdapter().classify(username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    script = TOOLS_DIR / "instagram_osint.py"
    if not script.exists():
        raise HTTPException(status_code=500, detail="Instagram tool bulunamadi")

    with tempfile.TemporaryDirectory(prefix="ig_card_") as tmp:
        png = Path(tmp) / f"instagram_card_{clean}.png"
        proc = await asyncio.create_subprocess_exec(
            "python3", "-u", str(script), clean, "--card", str(png),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=tmp,
        )
        try:
            _, err = await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError:
            proc.kill(); await proc.wait()
            raise HTTPException(status_code=504, detail="Kart zaman asimi")
        if proc.returncode != 0 or not png.exists():
            raise HTTPException(status_code=500, detail=f"Kart uretilemedi: {err.decode('utf-8', 'replace')[:200]}")
        return Response(content=png.read_bytes(), media_type="image/png",
                        headers={"Content-Disposition": f'inline; filename="instagram_card_{clean}.png"'})
