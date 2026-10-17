#!/usr/bin/env python3
"""
Hacker News OSINT — profil (Firebase API) + gonderi/yorum gecmisi (Algolia HN Search).
Yanit verilen kullanicilar (yorumlarin ust ogesinin yazari) iliski grafigi icin toplanir.

  python hackernews_osint.py pg
  python hackernews_osint.py "https://news.ycombinator.com/user?id=pg"
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import _toolkit as tk

FB = "https://hacker-news.firebaseio.com/v0"
ALG = "https://hn.algolia.com/api/v1"


def parse_target(raw: str) -> str | None:
    t = (raw or "").strip()
    m = re.search(r"news\.ycombinator\.com/user\?id=([A-Za-z0-9_\-]{2,15})", t)
    if m:
        return m.group(1)
    t = t.lstrip("@")
    return t if re.match(r"^[A-Za-z0-9_\-]{2,15}$", t) else None


def main() -> None:
    ap = argparse.ArgumentParser(description="Hacker News OSINT")
    ap.add_argument("target")
    ap.add_argument("--items", type=int, default=300, help="Incelenecek gonderi+yorum (en fazla 1000)")
    args = ap.parse_args()
    user = parse_target(args.target)
    if not user:
        tk.fail("not_found", f"Gecersiz HN kullanici adi: {args.target}")

    try:
        prof = tk.get_json(f"{FB}/user/{user}.json")
        if not prof:
            tk.fail("not_found", f"Hacker News kullanicisi bulunamadi: {user}")
        hits, page = [], 0
        want = max(20, min(args.items, 1000))
        while len(hits) < want:
            res = tk.get_json(f"{ALG}/search_by_date", params={"tags": f"author_{prof['id']}", "hitsPerPage": min(200, want), "page": page}) or {}
            batch = res.get("hits") or []
            hits.extend(batch)
            page += 1
            if not batch or page >= (res.get("nbPages") or 0):
                break
        hits = hits[:want]

        comments = [h for h in hits if "comment" in (h.get("_tags") or [])]
        stories = [h for h in hits if "story" in (h.get("_tags") or []) and "comment" not in (h.get("_tags") or [])]
        parents = list(dict.fromkeys(str(h.get("parent_id")) for h in comments if h.get("parent_id")))[:80]

        def author_of(pid):
            try:
                it = tk.get_json(f"{FB}/item/{pid}.json")
                return pid, (it or {}).get("by")
            except tk.HttpError:
                return pid, None
        with ThreadPoolExecutor(max_workers=8) as ex:
            parent_by = dict(ex.map(author_of, parents))
    except tk.HttpError as e:
        tk.fail("rate_limited" if e.status == 429 else "error", f"Hacker News: {e}")

    replied = Counter()
    for h in comments:
        by = parent_by.get(str(h.get("parent_id")))
        if by and by != prof["id"]:
            replied[by] += 1
    domains = Counter(tk.domain_of(h["url"]) for h in stories if h.get("url"))
    domains.pop(None, None)
    kinds = Counter()
    for h in hits:
        tags = h.get("_tags") or []
        for k in ("ask_hn", "show_hn", "poll", "job"):
            if k in tags:
                kinds[k] += 1
    kinds["story"] = len(stories)
    kinds["comment"] = len(comments)

    about_html = prof.get("about") or ""
    about = tk.html_to_text(about_html)
    dist = tk.distributions([h.get("created_at_i") for h in hits])
    tk.emit({
        "username": prof.get("id"),
        "profile_url": f"https://news.ycombinator.com/user?id={prof.get('id')}",
        "created": tk.iso(prof.get("created")),
        "karma": prof.get("karma"),
        "about": about,
        "about_links": list(dict.fromkeys(tk.links_from_html(about_html) + tk.find_urls(about))),
        "about_emails": tk.find_emails(about.replace(" at ", "@").replace("[at]", "@").replace("(at)", "@")),
        "about_socials": tk.find_socials(about + " " + about_html),
        "submitted_total": len(prof.get("submitted") or []),
        "items_analyzed": len(hits),
        "kinds": dict(kinds),
        "stories": [{"id": h.get("objectID"), "title": h.get("title"), "url": h.get("url"), "points": h.get("points"),
                     "comments": h.get("num_comments"), "date": tk.iso(h.get("created_at_i")),
                     "hn_url": f"https://news.ycombinator.com/item?id={h.get('objectID')}"} for h in stories],
        "recent_comments": [{"id": h.get("objectID"), "story": h.get("story_title"), "text": tk.html_to_text(h.get("comment_text") or "")[:300],
                             "date": tk.iso(h.get("created_at_i")), "parent_author": parent_by.get(str(h.get("parent_id"))),
                             "hn_url": f"https://news.ycombinator.com/item?id={h.get('objectID')}"} for h in comments[:40]],
        "top_domains": dict(domains.most_common(15)),
        "replied_to": dict(replied.most_common(25)),
        "activity": {"first": dist["first"], "last": dist["last"], "hour_distribution": dist["hour_distribution"],
                     "day_distribution": dist["day_distribution"]},
    })


if __name__ == "__main__":
    main()
