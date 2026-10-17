#!/usr/bin/env python3
"""
GitLab OSINT — profil, projeler, takipci/takip, aktivite, commit e-postalari.
gitlab.com varsayilan; baska bir GitLab sunucusunun URL'si verilirse o kullanilir.

  python gitlab_osint.py gitlab-bot
  python gitlab_osint.py https://gitlab.com/someuser
  python gitlab_osint.py https://git.kurum.local/kullanici
"""
from __future__ import annotations

import argparse
import os
import re
from collections import Counter, defaultdict
from urllib.parse import urlparse

import _toolkit as tk

TOKEN = os.environ.get("GITLAB_TOKEN", "").strip()
HDR = {"PRIVATE-TOKEN": TOKEN} if TOKEN else None


def parse_target(raw: str) -> tuple[str, str] | None:
    t = (raw or "").strip().rstrip("/")
    if re.match(r"^https?://", t):
        u = urlparse(t)
        parts = [p for p in u.path.split("/") if p and p != "-"]
        if parts and parts[0] == "users" and len(parts) > 1:
            parts = parts[1:]
        if not parts:
            return None
        return f"{u.scheme}://{u.netloc}", parts[0]
    m = re.match(r"^(?:gitlab\.com/)?@?([A-Za-z0-9_.\-]{1,255})$", t)
    return ("https://gitlab.com", m.group(1)) if m else None


def main() -> None:
    ap = argparse.ArgumentParser(description="GitLab OSINT")
    ap.add_argument("target")
    ap.add_argument("--commit-projects", type=int, default=6)
    args = ap.parse_args()
    parsed = parse_target(args.target)
    if not parsed:
        tk.fail("not_found", f"Gecersiz GitLab hedefi: {args.target}")
    base, username = parsed
    A = f"{base}/api/v4"

    def j(path, **params):
        return tk.get_json(f"{A}{path}", params=params or None, headers=HDR, allow=(401, 403, 404))

    try:
        found = j("/users", username=username) or []
        if not found:
            tk.fail("not_found", f"GitLab kullanicisi bulunamadi: {username} ({base})")
        uid = found[0]["id"]
        u = j(f"/users/{uid}") or found[0]
        projects = j(f"/users/{uid}/projects", per_page=100, order_by="last_activity_at") or []
        starred = j(f"/users/{uid}/starred_projects", per_page=50) or []
        followers = j(f"/users/{uid}/followers", per_page=100) or []
        following = j(f"/users/{uid}/following", per_page=100) or []
        events = j(f"/users/{uid}/events", per_page=100) or []

        emails = defaultdict(lambda: {"count": 0, "names": set(), "repos": set(), "last": None})
        name_keys = {str(x).lower() for x in (u.get("name"), u.get("username")) if x}
        own = [p for p in projects if not p.get("forked_from_project")][: args.commit_projects]
        for p in own:
            commits = j(f"/projects/{p['id']}/repository/commits", per_page=50) or []
            if not isinstance(commits, list):
                continue
            for c in commits:
                for role in ("author", "committer"):
                    em = (c.get(f"{role}_email") or "").lower()
                    if not em:
                        continue
                    e = emails[em]
                    e["count"] += 1
                    if c.get(f"{role}_name"):
                        e["names"].add(c[f"{role}_name"])
                    e["repos"].add(p.get("path_with_namespace"))
                    d = c.get(f"{role}_date") or c.get("created_at")
                    if d and (not e["last"] or d > e["last"]):
                        e["last"] = d
    except tk.HttpError as e:
        tk.fail("rate_limited" if e.status == 429 else "error", f"GitLab API: {e}")

    commit_emails = []
    for em, e in sorted(emails.items(), key=lambda x: -x[1]["count"]):
        commit_emails.append({
            "email": em, "count": e["count"], "names": sorted(e["names"]), "repos": sorted(r for r in e["repos"] if r),
            "last": e["last"], "noreply": "noreply" in em,
            "likely_self": bool({n.lower() for n in e["names"]} & name_keys) or any(k in em for k in name_keys if len(k) > 3),
        })

    ev_dates = [e.get("created_at") for e in events if isinstance(e, dict)]
    actions = Counter(e.get("action_name") for e in events if isinstance(e, dict) and e.get("action_name"))
    ev_projects = Counter(e.get("project_id") for e in events if isinstance(e, dict) and e.get("project_id"))
    namespaces = Counter()
    for p in projects:
        ns = p.get("namespace") or {}
        if ns.get("kind") == "group":
            namespaces[ns.get("full_path")] += 1

    bio = u.get("bio") or ""
    txt = " ".join(str(x) for x in (bio, u.get("website_url"), u.get("twitter"), u.get("linkedin"), u.get("discord"), u.get("skype")) if x)
    socials = tk.find_socials(txt)
    if u.get("twitter"):
        socials.append({"platform": "twitter", "handle": u["twitter"].lstrip("@"), "url": f"https://x.com/{u['twitter'].lstrip('@')}"})
    if u.get("linkedin"):
        socials.append({"platform": "linkedin", "handle": u["linkedin"], "url": f"https://linkedin.com/in/{u['linkedin']}"})
    if u.get("github"):
        socials.append({"platform": "github", "handle": u["github"], "url": f"https://github.com/{u['github']}"})

    def proj(p):
        return {"id": p.get("id"), "name": p.get("name"), "path": p.get("path_with_namespace"), "url": p.get("web_url"),
                "description": (p.get("description") or "")[:200], "stars": p.get("star_count"), "forks": p.get("forks_count"),
                "created": p.get("created_at"), "last_activity": p.get("last_activity_at"), "topics": p.get("topics") or p.get("tag_list") or [],
                "fork": bool(p.get("forked_from_project")), "visibility": p.get("visibility")}

    dist = tk.distributions(ev_dates)
    tk.emit({
        "base_url": base, "id": u.get("id"), "username": u.get("username"), "name": u.get("name"), "state": u.get("state"),
        "avatar_url": u.get("avatar_url"), "web_url": u.get("web_url"), "bio": bio, "location": u.get("location"),
        "public_email": u.get("public_email") or None, "website_url": u.get("website_url") or None, "organization": u.get("organization") or None,
        "job_title": u.get("job_title") or None, "pronouns": u.get("pronouns") or None, "twitter": u.get("twitter") or None,
        "linkedin": u.get("linkedin") or None, "discord": u.get("discord") or None, "skype": u.get("skype") or None,
        "created_at": u.get("created_at"), "bot": u.get("bot"), "local_time": u.get("local_time"),
        "followers_count": u.get("followers"), "following_count": u.get("following"),
        "bio_emails": tk.find_emails(bio), "socials": socials,
        "projects": [proj(p) for p in projects], "starred": [proj(p) for p in starred],
        "followers": [{"username": f.get("username"), "name": f.get("name"), "url": f.get("web_url")} for f in followers if isinstance(f, dict)],
        "following": [{"username": f.get("username"), "name": f.get("name"), "url": f.get("web_url")} for f in following if isinstance(f, dict)],
        "groups": [{"path": k, "projects": v} for k, v in namespaces.most_common()],
        "commit_emails": commit_emails,
        "activity": {"events": len(ev_dates), "actions": dict(actions.most_common()), "first": dist["first"], "last": dist["last"],
                     "hour_distribution": dist["hour_distribution"], "day_distribution": dist["day_distribution"],
                     "active_project_ids": dict(ev_projects.most_common(10))},
    })


if __name__ == "__main__":
    main()
