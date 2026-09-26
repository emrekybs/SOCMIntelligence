#!/usr/bin/env python3
"""
X (Twitter) OSINT — resmi X API v2.

Ortam degiskeni X_BEARER_TOKEN varsa gercek veri cekilir:
  - Kullanici: ad, bio, konum, web sitesi, katilma tarihi, dogrulanmis mi, sayilar
  - Son gonderiler (API planinin izin verdigi kadar): tarih, begeni/RT/yanit
  - Bio + gonderilerden: bahsedilen hesaplar (@), etiketler (#), paylasilan alan adlari
  - Gonderi saatleri dagilimi (UTC)

Token yoksa: acikca "ornek veri" olarak isaretlenmis mock cikti doner (mock=True),
boylece API girildiginde ne tur cikti alinacagi arayuzde gorunur.

  python x_osint.py johndoe
  python x_osint.py @nasa --tweets 50
"""
from __future__ import annotations

import argparse
import os
import re
from collections import Counter

import _toolkit as tk

API = "https://api.twitter.com/2"
HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")


def parse_target(raw: str) -> str | None:
    t = (raw or "").strip()
    m = re.search(r"(?:twitter|x)\.com/(?!intent|share|home|search|hashtag|i/)([A-Za-z0-9_]{1,15})", t)
    if m:
        return m.group(1)
    t = t.lstrip("@")
    return t if HANDLE_RE.match(t) else None


def _auth() -> dict:
    return {"Authorization": f"Bearer {os.environ['X_BEARER_TOKEN']}"}


def _extract(text: str) -> tuple[list[str], list[str], list[str]]:
    mentions = list(dict.fromkeys(m.lower() for m in re.findall(r"(?<![\w@])@([A-Za-z0-9_]{1,15})", text or "")))
    tags = list(dict.fromkeys(h.lower() for h in re.findall(r"(?<![\w&])#([A-Za-z0-9_]{1,60})", text or "")))
    urls = tk.find_urls(text or "")
    return mentions, tags, urls


def fetch_real(handle: str, want: int) -> dict:
    ufields = "description,location,url,verified,verified_type,created_at,profile_image_url,public_metrics,entities,pinned_tweet_id,protected"
    r = tk.get_json(f"{API}/users/by/username/{handle}", params={"user.fields": ufields},
                    headers=_auth(), allow=(400, 401, 403, 404, 429))
    if not r or "data" not in r:
        errs = (r or {}).get("errors") or []
        title = (r or {}).get("title") or (errs[0].get("detail") if errs else "")
        low = str(title).lower()
        if "not found" in low or (errs and errs[0].get("title") == "Not Found Error"):
            tk.fail("not_found", f"X hesabi bulunamadi: @{handle}")
        if "unauthor" in low or "401" in low:
            tk.fail("error", "X API: token gecersiz veya yetkisiz (X_BEARER_TOKEN kontrol edin).")
        tk.fail("error", f"X API: {title or 'kullanici alinamadi'}")

    u = r["data"]
    pm = u.get("public_metrics") or {}
    ent = u.get("entities") or {}
    # Bio linkleri (kisaltilmis t.co -> expanded_url)
    bio_urls = [e.get("expanded_url") or e.get("url") for e in (ent.get("url", {}).get("urls") or [])]
    bio_urls += [e.get("expanded_url") or e.get("url") for e in (ent.get("description", {}).get("urls") or [])]
    website = None
    if u.get("url"):
        website = bio_urls[0] if bio_urls else u["url"]

    tweets, tw_err = [], None
    uid = u["id"]
    tr = tk.get_json(f"{API}/users/{uid}/tweets",
                     params={"max_results": max(5, min(want, 100)),
                             "tweet.fields": "created_at,public_metrics,entities,lang",
                             "exclude": "retweets,replies"},
                     headers=_auth(), allow=(400, 401, 403, 429))
    if tr and "data" in tr:
        for tw in tr["data"]:
            m = tw.get("public_metrics") or {}
            tweets.append({
                "id": tw.get("id"), "date": tw.get("created_at"), "text": tw.get("text"),
                "likes": m.get("like_count"), "retweets": m.get("retweet_count"),
                "replies": m.get("reply_count"), "quotes": m.get("quote_count"),
                "url": f"https://x.com/{handle}/status/{tw.get('id')}", "lang": tw.get("lang"),
            })
    elif tr and (tr.get("errors") or tr.get("title")):
        tw_err = (tr.get("title") or "gonderiler alinamadi")  # plan tweet okumaya izin vermiyor olabilir

    # Bahsetme / etiket / alan adi topla (bio + tweetler)
    men, tags, doms = Counter(), Counter(), Counter()
    bm, bt, bu = _extract(u.get("description") or "")
    for x in bm:
        if x != handle.lower():
            men[x] += 1
    for x in bt:
        tags[x] += 1
    for du in bio_urls:
        d = tk.domain_of(du)
        if d:
            doms[d] += 1
    for tw in tweets:
        tm, tt, tu = _extract(tw.get("text") or "")
        for x in tm:
            if x != handle.lower():
                men[x] += 1
        for x in tt:
            tags[x] += 1
        for du in tu:
            d = tk.domain_of(du)
            if d and "t.co" not in d:
                doms[d] += 1

    dist = tk.distributions([tw.get("date") for tw in tweets])
    emails = tk.find_emails(u.get("description") or "")

    return {
        "mock": False,
        "username": u.get("username"),
        "user_id": uid,
        "name": u.get("name"),
        "bio": u.get("description"),
        "location": u.get("location"),
        "website": website,
        "verified": bool(u.get("verified")),
        "verified_type": u.get("verified_type"),
        "protected": bool(u.get("protected")),
        "created_at": u.get("created_at"),
        "profile_image": (u.get("profile_image_url") or "").replace("_normal", ""),
        "followers": pm.get("followers_count"),
        "following": pm.get("following_count"),
        "tweet_count": pm.get("tweet_count"),
        "listed": pm.get("listed_count"),
        "url": f"https://x.com/{u.get('username')}",
        "tweets": tweets,
        "tweets_error": tw_err,
        "mentions": [{"handle": h, "count": c} for h, c in men.most_common(30)],
        "hashtags": [{"tag": h, "count": c} for h, c in tags.most_common(30)],
        "domains": [{"domain": d, "count": c} for d, c in doms.most_common(20)],
        "emails": emails,
        "hour_distribution": dist.get("hour_distribution", {}),
        "day_distribution": dist.get("day_distribution", {}),
    }


def fetch_mock(handle: str) -> dict:
    """Token yokken gosterilen ornek veri. Gercek kisi verisi DEGILDIR."""
    h = handle.lower()
    tweets = []
    for i in range(8):
        tweets.append({
            "id": f"mock{i}", "date": f"2026-09-{10 + i:02d}T{9 + i:02d}:15:00.000Z",
            "text": f"Örnek gönderi {i + 1} #osint #siber — kaynak: example.com @kaynak_hesap",
            "likes": 100 + i * 13, "retweets": 20 + i * 3, "replies": 5 + i, "quotes": i,
            "url": f"https://x.com/{h}/status/mock{i}", "lang": "tr",
        })
    return {
        "mock": True,
        "username": handle,
        "user_id": "0",
        "name": f"{handle} (örnek)",
        "bio": "Bu bir ÖRNEK profildir. Gerçek X verisi için Ayarlar'dan X_BEARER_TOKEN girin. İletişim: ornek@example.com",
        "location": "İstanbul, TR",
        "website": "https://example.com",
        "verified": True,
        "verified_type": "blue",
        "protected": False,
        "created_at": "2013-05-01T12:00:00.000Z",
        "profile_image": None,
        "followers": 45200, "following": 512, "tweet_count": 12800, "listed": 340,
        "url": f"https://x.com/{handle}",
        "tweets": tweets,
        "tweets_error": None,
        "mentions": [{"handle": "kaynak_hesap", "count": 8}, {"handle": "ornek_kurum", "count": 3}],
        "hashtags": [{"tag": "osint", "count": 8}, {"tag": "siber", "count": 6}, {"tag": "ctf", "count": 2}],
        "domains": [{"domain": "example.com", "count": 8}, {"domain": "github.com", "count": 2}],
        "emails": ["ornek@example.com"],
        "hour_distribution": {f"{9 + (i % 6):02d}:00": 3 + (i % 4) for i in range(8)},
        "day_distribution": {"Mon": 4, "Tue": 3, "Wed": 5, "Thu": 2, "Fri": 6, "Sat": 1, "Sun": 2},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="X (Twitter) OSINT")
    ap.add_argument("target")
    ap.add_argument("--tweets", type=int, default=30)
    args = ap.parse_args()
    handle = parse_target(args.target)
    if not handle:
        tk.fail("not_found", f"Gecersiz X kullanici adi: {args.target}")

    if os.environ.get("X_BEARER_TOKEN"):
        try:
            tk.emit(fetch_real(handle, args.tweets))
        except tk.HttpError as e:
            tk.fail("rate_limited" if e.status == 429 else "error", f"X API: {e}")
    else:
        tk.emit(fetch_mock(handle))


if __name__ == "__main__":
    main()
