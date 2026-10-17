"""
GitLab OSINT modulu - SOCMIntelligence platformu.

Tool: tools/gitlab_osint.py (gitlab.com veya kurum ici GitLab URL'si; GITLAB_TOKEN opsiyonel)
Graph: profil + e-postalar (profil / commit) + commit e-postalarinin gectigi repolar + gruplar
       + takipci / takip + sosyal hesaplar
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from app.core.adapter import PlatformAdapter
from app.modules._common import G, make_router, raise_tool_error, slug


class GitLabAdapter(PlatformAdapter):
    platform = "gitlab"
    script = "gitlab_osint.py"
    capabilities = ["scan"]
    cache_ttl = 600

    def classify(self, raw: str) -> tuple[str, str]:
        t = (raw or "").strip().rstrip("/")
        if not t:
            raise ValueError("Bos input")
        if re.match(r"^https?://", t):
            u = urlparse(t)
            parts = [p for p in u.path.split("/") if p and p != "-"]
            if parts and parts[0] == "users":
                parts = parts[1:]
            if not parts:
                raise ValueError("URL'de kullanici adi yok")
            return ("url", f"{u.scheme}://{u.netloc}/{parts[0]}")
        t = re.sub(r"^gitlab\.com/", "", t).lstrip("@")
        if not re.match(r"^[A-Za-z0-9_.\-]{1,255}$", t):
            raise ValueError(f"Gecersiz GitLab kullanici adi: {raw}")
        return ("username", t)

    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        result = await self._run_tool(target_type, value, [value], timeout=120)
        raise_tool_error(result, "GitLab")
        return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return GitLabGraphConverter.convert(data)


class GitLabGraphConverter:
    @staticmethod
    def convert(d: dict[str, Any]) -> dict[str, list]:
        g = G()
        u = d.get("username")
        if not u:
            return g.export()
        host = urlparse(d.get("base_url") or "https://gitlab.com").netloc
        pref = "gitlab" if host == "gitlab.com" else f"gitlab_{slug(host)}"
        pid = g.node(f"p_{pref}_{slug(u)}", "person", d.get("name") or u, {
            "Platform": "GitLab" if host == "gitlab.com" else f"GitLab ({host})", "Username": u, "Location": d.get("location"),
            "Organization": d.get("organization"), "Job": d.get("job_title"), "Bio": (d.get("bio") or "")[:160],
            "Created": (d.get("created_at") or "")[:10], "Followers": d.get("followers_count"), "Projects": len(d.get("projects") or []),
        })
        uid = g.node(f"u_{pref}_{slug(u)}", "username", f"@{u}", {"Platforms": "GitLab", "Profile": d.get("web_url")})
        g.edge(pid, uid, "owns")
        if d.get("public_email"):
            g.email(pid, d["public_email"], "GitLab profil e-postası")
        for e in d.get("bio_emails") or []:
            g.email(pid, e, "GitLab bio")
        for c in (d.get("commit_emails") or [])[:25]:
            em = c.get("email")
            if not em or c.get("noreply"):
                continue
            eid = g.node(f"e_{slug(em)}", "email", em, {"Source": "Commit meta verisi", "Commit_adları": ", ".join(c.get("names") or []),
                                                        "Commit_sayısı": c.get("count")})
            if c.get("likely_self"):
                g.edge(pid, eid, "owns")
            for r in (c.get("repos") or [])[:5]:
                rid = g.node(f"c_gl_repo_{slug(r)}", "content", r, {"Tür": "Repo", "URL": f"{d.get('base_url')}/{r}"})
                g.edge(eid, rid, "appears_in", c.get("count"))
        for gr in d.get("groups") or []:
            gid = g.node(f"c_glgrp_{slug(gr['path'])}", "community", gr["path"], {"Tür": "GitLab grubu", "URL": f"{d.get('base_url')}/{gr['path']}"})
            g.edge(pid, gid, "member_of", gr.get("projects"))
        for f in (d.get("followers") or [])[:40]:
            if f.get("username"):
                fid = g.node(f"u_{pref}_{slug(f['username'])}", "username", f"@{f['username']}", {"Platforms": "GitLab", "Display_Name": f.get("name"), "Profile": f.get("url")})
                g.edge(fid, uid, "follows")
        for f in (d.get("following") or [])[:40]:
            if f.get("username"):
                fid = g.node(f"u_{pref}_{slug(f['username'])}", "username", f"@{f['username']}", {"Platforms": "GitLab", "Display_Name": f.get("name"), "Profile": f.get("url")})
                g.edge(uid, fid, "follows")
        for s in d.get("socials") or []:
            g.social(pid, s["platform"], s["handle"], s.get("url"), source="GitLab profili")
        if d.get("website_url"):
            g.domain(pid, d["website_url"], "GitLab web sitesi", "owns")
        topics = {}
        for p in d.get("projects") or []:
            for t in p.get("topics") or []:
                topics[t] = topics.get(t, 0) + 1
        for t, c in sorted(topics.items(), key=lambda x: -x[1])[:8]:
            g.hashtag(pid, t, "GitLab (proje konusu)", c, etype="interest")
        return g.export()


router = make_router("gitlab", GitLabAdapter, ["gitlab-bot", "https://gitlab.com/gitlab-bot", "https://git.kurum.local/kullanici"],
                     input_types=["username", "url"], requires_env=["GITLAB_TOKEN (opsiyonel)"])
