#!/usr/bin/env python3
"""
Bluesky OSINT — AT Protocol herkese acik API'si (anahtar/oturum gerekmez).

Kaynak: https://public.api.bsky.app  (app.bsky.actor.getProfile, app.bsky.feed.getAuthorFeed)
Cikti: profil, gonderiler, bahsedilen hesaplar, etiketler, paylasilan alan adlari,
       paylasim saatleri (UTC), diller.

  python bluesky_osint.py jay.bsky.team
  python bluesky_osint.py https://bsky.app/profile/nasa.gov --posts 100
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from datetime import datetime, timezone

import _toolkit as tk

BASE = "https://public.api.bsky.app/xrpc"


def normalize(raw: str) -> str | None:
    t = (raw or "").strip()
    if not t:
        return None
    m = re.search(r"bsky\.app/profile/([^/?#\s]+)", t, re.I)
    if m:
        t = m.group(1)
    t = t.strip("/").lstrip("@")
    if t.startswith("did:"):
        return t if re.match(r"^did:[a-z0-9]+:[A-Za-z0-9._%-]+$", t) else None
    # handle: en az bir nokta iceren alan-adi bicimi (nasa.gov, jay.bsky.team)
    if re.match(r"^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)+$", t):
        return t.lower()
    return None


def _facets(record: dict) -> tuple[list[str], list[str], list[str]]:
    """Bir gonderinin facet'lerinden (tag, mention did, link) uc liste."""
    tags, mentions, links = [], [], []
    for f in record.get("facets") or []:
        for feat in f.get("features") or []:
            ty = feat.get("$type") or ""
            if ty.endswith("#tag") and feat.get("tag"):
                tags.append(feat["tag"])
            elif ty.endswith("#mention") and feat.get("did"):
                mentions.append(feat["did"])
            elif ty.endswith("#link") and feat.get("uri"):
                links.append(feat["uri"])
    return tags, mentions, links


def get_profile(actor: str) -> dict:
    try:
        return tk.get_json(f"{BASE}/app.bsky.actor.getProfile", params={"actor": actor}, allow=(400, 404)) or {}
    except tk.HttpError as e:
        if e.status in (400, 404):
            return {}
        raise


def get_feed(did: str, limit: int) -> list:
    out, cursor = [], None
    while len(out) < limit:
        params = {"actor": did, "limit": min(100, limit - len(out))}
        if cursor:
            params["cursor"] = cursor
        try:
            data = tk.get_json(f"{BASE}/app.bsky.feed.getAuthorFeed", params=params, allow=(400, 404))
        except tk.HttpError:
            break
        if not data:
            break
        out.extend(data.get("feed") or [])
        cursor = data.get("cursor")
        if not cursor or not (data.get("feed") or []):
            break
    return out[:limit]


def main() -> None:
    ap = argparse.ArgumentParser(description="Bluesky OSINT (AT Protocol, oturumsuz)")
    ap.add_argument("target")
    ap.add_argument("--posts", type=int, default=100, help="Taranacak gonderi sayisi")
    args = ap.parse_args()

    actor = normalize(args.target)
    if not actor:
        tk.fail("error", f"Gecersiz Bluesky handle / DID: {args.target}")

    prof = get_profile(actor)
    if not prof or not prof.get("did"):
        tk.fail("not_found", f"Bluesky hesabi bulunamadi: {actor}")

    did = prof["did"]
    handle = prof.get("handle") or actor
    feed = get_feed(did, max(1, min(args.posts, 200)))

    htags, mentions, domains = Counter(), {}, Counter()
    langs = Counter()
    times = []
    posts_preview = []
    reposts = replies = 0
    for item in feed:
        post = item.get("post") or {}
        rec = post.get("record") or {}
        if item.get("reason"):  # repost
            reposts += 1
            continue
        if rec.get("reply"):
            replies += 1
        text = rec.get("text") or ""
        tags, mens, links = _facets(rec)
        # metinden de #etiket yakala (facet'siz istemciler)
        for w in text.split():
            if w.startswith("#") and len(w) > 1:
                tags.append(w[1:])
        # ayni gonderide facet + metin ayni etiketi iki kez saymasin
        for tg in {t.lower() for t in tags if t}:
            htags[tg] += 1
        for did_m in mens:
            mentions[did_m] = mentions.get(did_m, 0) + 1
        for uri in links + tk.find_urls(text):
            d = tk.domain_of(uri)
            if d and "bsky.app" not in d:
                domains[d] += 1
        for lg in rec.get("langs") or []:
            langs[lg] += 1
        created = rec.get("createdAt")
        if created:
            times.append(created)
        if len(posts_preview) < 24:
            uri = post.get("uri") or ""
            rkey = uri.split("/")[-1] if uri else None
            posts_preview.append({
                "text": text[:200], "created": created,
                "likes": post.get("likeCount"), "reposts": post.get("repostCount"), "replies": post.get("replyCount"),
                "url": f"https://bsky.app/profile/{handle}/post/{rkey}" if rkey else None,
                "langs": rec.get("langs") or [],
            })

    # bahsedilen hesaplarin did -> handle cozumu (tek istek, ilk 25)
    men_resolved = []
    if mentions:
        top = sorted(mentions.items(), key=lambda kv: -kv[1])[:25]
        try:
            dids = ",".join(d for d, _ in top)
            data = tk.get_json(f"{BASE}/app.bsky.actor.getProfiles", params={"actors": dids}, allow=(400,))
            by_did = {p["did"]: p for p in (data or {}).get("profiles", [])}
        except tk.HttpError:
            by_did = {}
        for d, c in top:
            p = by_did.get(d, {})
            men_resolved.append({"did": d, "handle": p.get("handle"), "display_name": p.get("displayName"), "count": c})

    # saat / gun dagilimi (UTC)
    hour_dist, day_dist = {f"{h:02d}": 0 for h in range(24)}, {str(i): 0 for i in range(7)}
    dts = []
    for c in times:
        dt = tk.to_dt(c)
        if dt:
            dts.append(dt)
            hour_dist[f"{dt.hour:02d}"] += 1
            day_dist[str(dt.weekday())] += 1

    assoc = prof.get("associated") or {}
    tk.emit({
        "input": args.target, "did": did, "handle": handle,
        "display_name": prof.get("displayName"), "description": prof.get("description"),
        "avatar": prof.get("avatar"), "banner": prof.get("banner"),
        "followers": prof.get("followersCount"), "following": prof.get("followsCount"),
        "posts_count": prof.get("postsCount"), "created_at": prof.get("createdAt"),
        "url": f"https://bsky.app/profile/{handle}",
        "pds": re.sub(r"^did:web:", "", did) if did.startswith("did:web:") else None,
        "labels": [l.get("val") for l in prof.get("labels") or [] if l.get("val")],
        "lists": assoc.get("lists"), "feedgens": assoc.get("feedgens"),
        "scanned_posts": len(feed), "own_posts": len(feed) - reposts, "reposts": reposts, "replies_count": replies,
        "hashtags": [{"hashtag": "#" + h, "count": c} for h, c in htags.most_common(40)],
        "mentions": men_resolved,
        "domains": [{"domain": d, "count": c} for d, c in domains.most_common(25)],
        "languages": [{"lang": l, "count": c} for l, c in langs.most_common()],
        "hour_distribution": hour_dist, "day_distribution": day_dist,
        "first_post": min(dts).strftime("%Y-%m-%d") if dts else None,
        "last_post": max(dts).strftime("%Y-%m-%d") if dts else None,
        "posts": posts_preview,
        "emails": tk.find_emails(prof.get("description") or ""),
    })


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except tk.HttpError as e:
        tk.fail("rate_limited" if e.status in (429, 503) else "error", f"Bluesky: {e}")
    except Exception as e:  # noqa: BLE001
        tk.fail("error", f"Bluesky araci beklenmedik hata: {e}")
