#!/usr/bin/env python3
"""
Hashtag cografi analizi — bir hashtag'in nerede / kimlerce atildigi (SOCMIntelligence).

Kaynaklar:
  - Instagram (HIKERAPI_TOKEN varsa): hashtag gonderileri; icinden KONUM ETIKETLI olanlar
    koordinat/yer bazinda toplanir (haritaya nokta). Konum etiketi cogu gonderide YOKTUR,
    yani harita "toplam" degil, konum etiketli gonderilerin ORNEKLEMIDIR.
  - Bluesky (bedava, anahtarsiz): ayni hashtag'in gonderileri; hacim, birlikte gecen etiketler,
    en aktif hesaplar ve saat dagilimi (Bluesky'de konum verisi genelde yoktur).

  python hashtagmap_osint.py osint
  python hashtagmap_osint.py "#İstanbul" --posts 200
"""
from __future__ import annotations

import argparse
import os
import re
from collections import Counter
from datetime import datetime, timezone

import _toolkit as tk

BSKY = "https://public.api.bsky.app/xrpc"
MASTO = "https://mastodon.social"
FLICKR = "https://api.flickr.com/services/rest/"


def normalize(raw: str) -> str | None:
    t = (raw or "").strip().lstrip("#").strip()
    if not t or " " in t:
        return None
    # harf/rakam/altcizgi + unicode harfler
    return t if re.match(r"^[\w][\w]{0,138}$", t, re.UNICODE) else None


# ─── Instagram (HikerAPI) ──────────────────────────────────────────
def ig_client(token: str):
    try:
        from hikerapi import Client  # type: ignore
    except ImportError:
        return None
    return Client(token=token)


def _ig_items(api, tag: str, want: int) -> list:
    items = []
    for meth in ("hashtag_medias_top_v2", "hashtag_medias_recent_v2", "hashtag_medias_top_recent_v2"):
        fn = getattr(api, meth, None)
        if not fn:
            continue
        page = None
        while len(items) < want:
            try:
                res = fn(tag, **({"page_id": page} if page else {}))
            except Exception:  # noqa: BLE001
                break
            batch = (res.get("response", {}) or {}).get("items") if isinstance(res, dict) else None
            batch = batch or (res.get("items") if isinstance(res, dict) else None) or (res.get("medias") if isinstance(res, dict) else None) or []
            items.extend(batch)
            page = res.get("next_page_id") if isinstance(res, dict) else None
            if not page or not batch:
                break
        if len(items) >= want:
            break
    return items[:want]


def ig_collect(token: str, tag: str, want: int) -> dict:
    api = ig_client(token)
    if not api:
        return {"error": "hikerapi paketi kurulu degil"}
    items = _ig_items(api, tag, want)
    geo, cohash, authors, times = {}, Counter(), Counter(), []
    for p in items:
        loc = p.get("location") or {}
        lat, lng = loc.get("lat"), loc.get("lng")
        cap = (p.get("caption") or {}).get("text") or ""
        for w in cap.split():
            if w.startswith("#") and len(w) > 1 and w[1:].lower() != tag.lower():
                cohash[w[1:].lower()] += 1
        au = (p.get("user") or {}).get("username")
        if au:
            authors[au] += 1
        if p.get("taken_at"):
            times.append(p["taken_at"])
        if lat is not None and lng is not None:
            key = f"{round(float(lat), 3)},{round(float(lng), 3)}"
            g = geo.setdefault(key, {"lat": float(lat), "lng": float(lng), "place": loc.get("name"),
                                     "city": loc.get("city"), "country": loc.get("country"), "count": 0, "platform": "instagram"})
            g["count"] += 1
    return {"posts": len(items), "geo": list(geo.values()), "cohash": cohash, "authors": authors, "times": times}


# ─── Bluesky (bedava) ──────────────────────────────────────────────
def bsky_collect(tag: str, want: int) -> dict:
    cohash, authors, times, langs = Counter(), Counter(), [], Counter()
    posts, cursor, fetched = [], None, 0
    while fetched < want:
        params = {"q": f"#{tag}", "limit": min(100, want - fetched)}
        if cursor:
            params["cursor"] = cursor
        try:
            data = tk.get_json(f"{BSKY}/app.bsky.feed.searchPosts", params=params, allow=(400, 404))
        except tk.HttpError:
            break
        if not data:
            break
        batch = data.get("posts") or []
        for p in batch:
            rec = p.get("record") or {}
            text = rec.get("text") or ""
            seen_tags = set()
            for f in rec.get("facets") or []:
                for feat in f.get("features") or []:
                    if (feat.get("$type") or "").endswith("#tag") and feat.get("tag"):
                        seen_tags.add(feat["tag"].lower())
            for w in text.split():
                if w.startswith("#") and len(w) > 1:
                    seen_tags.add(w[1:].lower())
            for tg in seen_tags:
                if tg != tag.lower():
                    cohash[tg] += 1
            au = (p.get("author") or {}).get("handle")
            if au:
                authors[au] += 1
            if rec.get("createdAt"):
                times.append(rec["createdAt"])
            for lg in rec.get("langs") or []:
                langs[lg] += 1
            if len(posts) < 30:
                uri = p.get("uri") or ""
                rk = uri.split("/")[-1] if uri else None
                posts.append({"handle": au, "text": text[:160], "created": rec.get("createdAt"),
                              "likes": p.get("likeCount"), "url": f"https://bsky.app/profile/{au}/post/{rk}" if au and rk else None})
        fetched += len(batch)
        cursor = data.get("cursor")
        if not cursor or not batch:
            break
    return {"posts": fetched, "cohash": cohash, "authors": authors, "times": times, "langs": langs, "sample": posts}


# ─── Mastodon (bedava, anahtarsiz) ─────────────────────────────────
def masto_collect(tag: str, want: int) -> dict:
    cohash, authors, times = Counter(), Counter(), []
    tagn = re.sub(r"[^\w]", "", tag, flags=re.UNICODE)
    if not tagn:
        return {"posts": 0, "cohash": cohash, "authors": authors, "times": times}
    try:
        data = tk.get_json(f"{MASTO}/api/v1/timelines/tag/{tagn}", params={"limit": min(40, want)}, allow=(404, 401))
    except tk.HttpError:
        return {"posts": 0, "cohash": cohash, "authors": authors, "times": times}
    for st in data or []:
        acc = (st.get("account") or {}).get("acct")
        if acc:
            authors[acc] += 1
        for tg in st.get("tags") or []:
            n = (tg.get("name") or "").lower()
            if n and n != tag.lower():
                cohash[n] += 1
        if st.get("created_at"):
            times.append(st["created_at"])
    return {"posts": len(data or []), "cohash": cohash, "authors": authors, "times": times}


# ─── Flickr (bedava API anahtari) — cografi foto = harita noktalari ─
def flickr_collect(tag: str, want: int) -> dict:
    key = os.environ.get("FLICKR_API_KEY")
    if not key:
        return {"posts": 0, "geo": [], "cohash": Counter(), "authors": Counter(), "times": [], "skipped": True}
    try:
        data = tk.get_json(FLICKR, params={
            "method": "flickr.photos.search", "api_key": key, "tags": tag, "has_geo": 1,
            "extras": "geo,url_m,date_taken,owner_name,tags", "format": "json", "nojsoncallback": 1,
            "per_page": min(250, want), "sort": "date-posted-desc"}, allow=(400,))
    except tk.HttpError:
        return {"posts": 0, "geo": [], "cohash": Counter(), "authors": Counter(), "times": []}
    photos = ((data or {}).get("photos") or {}).get("photo") or []
    geo, cohash, authors, times = {}, Counter(), Counter(), []
    for ph in photos:
        try:
            lat, lng = float(ph.get("latitude")), float(ph.get("longitude"))
        except (TypeError, ValueError):
            continue
        if lat == 0 and lng == 0:
            continue
        key3 = f"{round(lat, 3)},{round(lng, 3)}"
        g = geo.setdefault(key3, {"lat": lat, "lng": lng, "place": ph.get("title") or None,
                                  "city": None, "country": None, "count": 0, "platform": "flickr"})
        g["count"] += 1
        if ph.get("ownername"):
            authors[ph["ownername"]] += 1
        for w in (ph.get("tags") or "").split():
            if w and w.lower() != tag.lower():
                cohash[w.lower()] += 1
        if ph.get("datetaken"):
            times.append(ph["datetaken"])
    return {"posts": len(photos), "geo": list(geo.values()), "cohash": cohash, "authors": authors, "times": times}


def hour_day(times: list) -> tuple[dict, dict]:
    hd = {f"{h:02d}": 0 for h in range(24)}
    dd = {str(i): 0 for i in range(7)}
    for tval in times:
        dt = tk.to_dt(tval)
        if dt:
            hd[f"{dt.hour:02d}"] += 1
            dd[str(dt.weekday())] += 1
    return hd, dd


def main() -> None:
    ap = argparse.ArgumentParser(description="Hashtag cografi analizi")
    ap.add_argument("target")
    ap.add_argument("--posts", type=int, default=150, help="Kaynak basina taranacak gonderi sayisi")
    args = ap.parse_args()

    tag = normalize(args.target)
    if not tag:
        tk.fail("error", f"Gecersiz hashtag: {args.target}")
    want = max(10, min(args.posts, 500))

    token = os.environ.get("HIKERAPI_TOKEN") or os.environ.get("HIKER_API_KEY")
    ig = ig_collect(token, tag, want) if token else {"posts": 0, "geo": [], "cohash": Counter(), "authors": Counter(), "times": [], "skipped": not token}
    bs = bsky_collect(tag, want)
    ms = masto_collect(tag, want)      # bedava, anahtarsiz
    fl = flickr_collect(tag, want)     # bedava (API anahtari) — koordinat/harita noktalari

    # Web araması (ANAHTARSIZ — DuckDuckGo) — social-searcher "Web" sekmesi gibi.
    # Instagram/TikTok/... cikmasi icin platform-hedefli (site:) sorgular calistirilir.
    web, web_engine, web_by_platform = [], None, {}
    try:
        import keyword_osint as _kw
        seen = set()
        queries = [f"#{tag}", f"{tag} site:instagram.com", f"{tag} site:tiktok.com",
                   f"{tag} site:x.com", f"{tag} site:youtube.com", f"{tag} site:reddit.com", f"{tag} site:facebook.com"]
        for q in queries:
            try:
                res, eng = _kw.search_web(q, 10)
            except Exception:  # noqa: BLE001
                continue
            web_engine = web_engine or eng
            for w in res:
                if w.get("url") and w["url"] not in seen:
                    seen.add(w["url"])
                    web.append(w)
            if len(web) >= 70:
                break
        web = web[:70]
        web_by_platform = dict(Counter(w["platform"] for w in web).most_common())
    except Exception:  # noqa: BLE001
        pass

    total_posts = ig.get("posts", 0) + bs.get("posts", 0) + ms.get("posts", 0) + fl.get("posts", 0) + len(web)
    if total_posts == 0:
        tk.fail("not_found", f"#{tag} icin hicbir kaynaktan veri bulunamadi (Web/Bluesky/Mastodon/Flickr/Instagram)")

    # birlestir
    cohash = (Counter(ig.get("cohash") or {}) + Counter(bs.get("cohash") or {})
              + Counter(ms.get("cohash") or {}) + Counter(fl.get("cohash") or {}))
    authors = ([{"username": u, "platform": "instagram", "count": c} for u, c in (ig.get("authors") or Counter()).most_common(20)]
               + [{"username": u, "platform": "bluesky", "count": c} for u, c in (bs.get("authors") or Counter()).most_common(20)]
               + [{"username": u, "platform": "mastodon", "count": c} for u, c in (ms.get("authors") or Counter()).most_common(20)]
               + [{"username": u, "platform": "flickr", "count": c} for u, c in (fl.get("authors") or Counter()).most_common(20)])
    times = (ig.get("times") or []) + (bs.get("times") or []) + (ms.get("times") or []) + (fl.get("times") or [])
    hd, dd = hour_day(times)

    # harita noktalari: Instagram (varsa) + Flickr (bedava)
    geo = sorted((ig.get("geo") or []) + (fl.get("geo") or []), key=lambda g: -g["count"])
    places, countries = Counter(), Counter()
    for g in geo:
        if g.get("place") or g.get("city"):
            places[g.get("place") or g.get("city")] += g["count"]
        if g.get("country"):
            countries[g["country"]] += g["count"]

    free_note = "" if os.environ.get("FLICKR_API_KEY") else " Daha çok harita noktası için Ayarlar'dan FLICKR_API_KEY (ücretsiz) girin."
    tk.emit({
        "hashtag": tag, "query": f"#{tag}",
        "sources": {"instagram": ig.get("posts", 0) > 0, "bluesky": bs.get("posts", 0) > 0,
                    "mastodon": ms.get("posts", 0) > 0, "flickr": fl.get("posts", 0) > 0, "web": len(web) > 0},
        "instagram_error": ig.get("error"),
        "instagram_posts": ig.get("posts", 0), "bluesky_posts": bs.get("posts", 0),
        "mastodon_posts": ms.get("posts", 0), "flickr_posts": fl.get("posts", 0),
        "web_engine": web_engine, "web_total": len(web),
        "web_by_platform": web_by_platform, "web_results": web,
        "geotagged_posts": sum(g["count"] for g in geo), "geo_points": geo[:300],
        "countries": [{"country": c, "count": n} for c, n in countries.most_common(30)],
        "places": [{"place": p, "count": n} for p, n in places.most_common(30)],
        "co_hashtags": [{"hashtag": "#" + h, "count": c} for h, c in cohash.most_common(40)],
        "top_authors": authors,
        "languages": [{"lang": l, "count": c} for l, c in (bs.get("langs") or Counter()).most_common()],
        "hour_distribution": hd, "day_distribution": dd,
        "sample_posts": bs.get("sample") or [],
        "note": "Harita yalnızca konum etiketli gönderileri gösterir (çoğu gönderide konum yoktur); örneklemdir." + free_note,
    })


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except tk.HttpError as e:
        tk.fail("rate_limited" if e.status in (429, 503) else "error", f"Hashtag: {e}")
    except Exception as e:  # noqa: BLE001
        tk.fail("error", f"Hashtag araci beklenmedik hata: {e}")
