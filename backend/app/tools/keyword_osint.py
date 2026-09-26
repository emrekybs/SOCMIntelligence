#!/usr/bin/env python3
"""
Kelime / mention arama — social-searcher tarzi, cok platformlu herkese acik arama (SOCMIntelligence).

Kaynaklar:
  - Bluesky  : app.bsky.feed.searchPosts (kelime araması) — bedava
  - Reddit   : www.reddit.com/search.json (oturumsuz) — bedava
  - Mastodon : tek kelimelik sorgu bir hashtag gibi mastodon.social etiket zaman tunelinden okunur — bedava
  - Web      : arama motoru (Google Custom Search anahtari varsa; yoksa DuckDuckGo HTML) — social-searcher'in
               "Web" sekmesi gibi Instagram DAHIL tum platformlarin herkese acik SAYFA linklerini getirir.
               (Bu Instagram API'si degildir; arama motorunun indeksledigi acik sayfalardir.)

Cikti: birlesik gonderi listesi, web linkleri (platforma gore), en aktif hesaplar, etiketler, saat dagilimi.

  python keyword_osint.py "veri sızıntısı"
  python keyword_osint.py "#hacker" --limit 100
"""
from __future__ import annotations

import argparse
import os
import re
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urlparse

import _toolkit as tk

BSKY = "https://public.api.bsky.app/xrpc"
MASTO_INSTANCE = "https://mastodon.social"

# alan adi -> platform etiketi (web sonuclarini gruplamak icin)
DOMAIN_PLATFORM = [
    ("instagram.com", "Instagram"), ("tiktok.com", "TikTok"), ("x.com", "X (Twitter)"), ("twitter.com", "X (Twitter)"),
    ("facebook.com", "Facebook"), ("linkedin.com", "LinkedIn"), ("youtube.com", "YouTube"), ("youtu.be", "YouTube"),
    ("reddit.com", "Reddit"), ("t.me", "Telegram"), ("telegram.me", "Telegram"), ("pinterest.", "Pinterest"),
    ("tumblr.com", "Tumblr"), ("bsky.app", "Bluesky"), ("mastodon.", "Mastodon"), ("threads.net", "Threads"),
    ("twitch.tv", "Twitch"), ("kick.com", "Kick"), ("vk.com", "VK"), ("flickr.com", "Flickr"),
]


def platform_of(url: str) -> str:
    d = (tk.domain_of(url) or "").lower()
    for frag, name in DOMAIN_PLATFORM:
        if frag in d:
            return name
    return "Web"


def _dt(v):
    return tk.to_dt(v)


# ─── Bluesky ───────────────────────────────────────────────────────
def search_bluesky(q: str, limit: int) -> list[dict]:
    out, cursor = [], None
    while len(out) < limit:
        params = {"q": q, "limit": min(100, limit - len(out))}
        if cursor:
            params["cursor"] = cursor
        try:
            data = tk.get_json(f"{BSKY}/app.bsky.feed.searchPosts", params=params, allow=(400, 404))
        except tk.HttpError:
            break
        if not data:
            break
        for p in data.get("posts") or []:
            rec = p.get("record") or {}
            au = (p.get("author") or {}).get("handle")
            uri = p.get("uri") or ""
            rk = uri.split("/")[-1] if uri else None
            tags = [f["tag"] for fac in (rec.get("facets") or []) for f in (fac.get("features") or [])
                    if (f.get("$type") or "").endswith("#tag") and f.get("tag")]
            out.append({"platform": "bluesky", "author": au, "text": rec.get("text") or "",
                        "date": rec.get("createdAt"), "score": p.get("likeCount"),
                        "url": f"https://bsky.app/profile/{au}/post/{rk}" if au and rk else None,
                        "hashtags": tags, "lang": (rec.get("langs") or [None])[0]})
        cursor = data.get("cursor")
        if not cursor or not (data.get("posts") or []):
            break
    return out


# ─── Reddit ────────────────────────────────────────────────────────
def search_reddit(q: str, limit: int) -> list[dict]:
    hdr = {"Accept": "application/json", "User-Agent": "SOCMIntelligence/1.0 (OSINT research; contact via app)"}
    data = None
    for host in ("https://www.reddit.com", "https://old.reddit.com"):
        try:
            data = tk.get_json(f"{host}/search.json",
                               params={"q": q, "limit": min(100, limit), "sort": "new", "raw_json": 1},
                               headers=hdr, allow=(403, 429, 503))
        except tk.HttpError:
            data = None
        if data and ((data.get("data") or {}).get("children")):
            break
    out = []
    for ch in ((data or {}).get("data") or {}).get("children") or []:
        p = ch.get("data") or {}
        out.append({"platform": "reddit", "author": p.get("author"),
                    "text": (p.get("title") or "") + ((" — " + p["selftext"][:200]) if p.get("selftext") else ""),
                    "date": datetime.fromtimestamp(p["created_utc"], tz=timezone.utc).isoformat() if p.get("created_utc") else None,
                    "score": p.get("score"), "url": "https://www.reddit.com" + p.get("permalink", ""),
                    "subreddit": p.get("subreddit"), "hashtags": [], "lang": None})
    return out


# ─── Hacker News (Algolia — tamamen bedava, anahtarsiz) ────────────
def search_hn(q: str, limit: int) -> list[dict]:
    try:
        data = tk.get_json("https://hn.algolia.com/api/v1/search_by_date",
                           params={"query": q, "tags": "(story,comment)", "hitsPerPage": min(50, limit)}, allow=(400,))
    except tk.HttpError:
        return []
    out = []
    for h in (data or {}).get("hits") or []:
        text = h.get("title") or h.get("story_title") or (h.get("comment_text") or "")[:200]
        oid = h.get("objectID")
        out.append({"platform": "hackernews", "author": h.get("author"),
                    "text": tk.html_to_text(text or "")[:220],
                    "date": h.get("created_at"), "score": h.get("points"),
                    "url": h.get("url") or (f"https://news.ycombinator.com/item?id={oid}" if oid else None),
                    "hashtags": [], "lang": None})
    return out


# ─── Mastodon (tek kelime -> etiket) ───────────────────────────────
def search_mastodon(q: str, limit: int) -> list[dict]:
    if " " in q.strip():
        return []  # oturumsuz Mastodon yalnizca etiket zaman tunelini verir
    tag = re.sub(r"[^\w]", "", q, flags=re.UNICODE)
    if not tag:
        return []
    try:
        data = tk.get_json(f"{MASTO_INSTANCE}/api/v1/timelines/tag/{tag}", params={"limit": min(40, limit)}, allow=(404, 401))
    except tk.HttpError:
        return []
    out = []
    for st in data or []:
        acc = st.get("account") or {}
        out.append({"platform": "mastodon", "author": acc.get("acct"),
                    "text": tk.html_to_text(st.get("content") or "")[:400], "date": st.get("created_at"),
                    "score": st.get("favourites_count"), "url": st.get("url") or st.get("uri"),
                    "hashtags": [tg.get("name") for tg in (st.get("tags") or []) if tg.get("name")], "lang": st.get("language")})
    return out


# ─── Web araması (arama motoru) ────────────────────────────────────
def search_web_google(q: str, key: str, cx: str, want: int) -> list[dict]:
    out = []
    start = 1
    while len(out) < want and start <= 91:
        try:
            data = tk.get_json("https://www.googleapis.com/customsearch/v1",
                               params={"key": key, "cx": cx, "q": q, "num": 10, "start": start}, allow=(400, 403, 429))
        except tk.HttpError:
            break
        items = (data or {}).get("items") or []
        for it in items:
            url = it.get("link")
            if not url:
                continue
            out.append({"platform": platform_of(url), "title": it.get("title"), "url": url,
                        "snippet": it.get("snippet"), "domain": tk.domain_of(url)})
        if not items:
            break
        start += 10
    return out[:want]


def _ddg_href(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    if "duckduckgo.com/l/" in href or href.startswith("/l/"):
        qs = parse_qs(urlparse(href).query)
        if qs.get("uddg"):
            return unquote(qs["uddg"][0])
    return href


def _ddg_parse(html: str, want: int) -> list[dict]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    # html endpoint: a.result__a ; lite endpoint: a.result-link
    anchors = soup.select("a.result__a") or soup.select("a.result-link") or soup.select("a[href]")
    for a in anchors:
        href = (a.get("href") or "").strip()
        if not href:
            continue
        url = _ddg_href(href)
        if not url.startswith("http") or "duckduckgo.com" in url or url in seen:
            continue
        seen.add(url)
        out.append({"platform": platform_of(url), "title": a.get_text(" ", strip=True) or url, "url": url,
                    "snippet": None, "domain": tk.domain_of(url)})
        if len(out) >= want:
            break
    return out


def search_web_ddg(q: str, want: int) -> list[dict]:
    hdr = {"Accept": "text/html", "Accept-Language": "en-US,en;q=0.8"}
    # once html, olmazsa lite (daha az engellenir)
    for url in ("https://html.duckduckgo.com/html/", "https://lite.duckduckgo.com/lite/"):
        try:
            r = tk.get(url, params={"q": q}, headers=hdr, allow=(202, 403, 429, 503))
        except tk.HttpError:
            continue
        if r.status_code == 200:
            res = _ddg_parse(r.text, want)
            if res:
                return res
    return []


def search_web(q: str, want: int) -> tuple[list[dict], str | None]:
    """Google Custom Search (anahtar varsa) yoksa DuckDuckGo. (sonuclar, kullanilan motor)."""
    key, cx = os.environ.get("GOOGLE_CSE_KEY"), os.environ.get("GOOGLE_CSE_CX")
    if key and cx:
        res = search_web_google(q, key, cx, want)
        if res:
            return res, "google"
    return search_web_ddg(q, want), "duckduckgo"


def main() -> None:
    ap = argparse.ArgumentParser(description="Cok platformlu kelime aramasi")
    ap.add_argument("target")
    ap.add_argument("--limit", type=int, default=80, help="Kaynak basina gonderi sayisi")
    ap.add_argument("--no-web", action="store_true", help="Arama motoru (web) kaynagini kullanma")
    args = ap.parse_args()
    q = (args.target or "").strip()
    if not q or len(q) > 200:
        tk.fail("error", f"Gecersiz arama sorgusu: {args.target}")
    limit = max(10, min(args.limit, 150))

    posts = (search_bluesky(q, limit) + search_reddit(q, limit)
             + search_mastodon(q, limit) + search_hn(q, limit))
    web, web_engine = ([], None) if args.no_web else search_web(q, min(50, limit))
    web_by_platform = Counter(w["platform"] for w in web)
    if not posts and not web:
        tk.fail("not_found", f"'{q}' icin herkese acik gonderi/sayfa bulunamadi")

    authors, htags, langs, hd, dd = Counter(), Counter(), Counter(), {f"{h:02d}": 0 for h in range(24)}, {str(i): 0 for i in range(7)}
    by_platform = Counter()
    for p in posts:
        by_platform[p["platform"]] += 1
        if p.get("author"):
            authors[(p["platform"], p["author"])] += 1
        for h in p.get("hashtags") or []:
            htags[h.lower()] += 1
        if p.get("lang"):
            langs[p["lang"]] += 1
        dt = _dt(p.get("date"))
        if dt:
            hd[f"{dt.hour:02d}"] += 1
            dd[str(dt.weekday())] += 1

    posts_sorted = sorted(posts, key=lambda p: _dt(p.get("date")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    tk.emit({
        "query": q, "total": len(posts),
        "by_platform": dict(by_platform),
        "web_engine": web_engine, "web_total": len(web),
        "web_by_platform": dict(web_by_platform.most_common()),
        "web_results": web,
        "sources": {"bluesky": by_platform.get("bluesky", 0) > 0, "reddit": by_platform.get("reddit", 0) > 0,
                    "mastodon": by_platform.get("mastodon", 0) > 0, "web": len(web) > 0},
        "top_accounts": [{"platform": pl, "author": au, "count": c} for (pl, au), c in authors.most_common(30)],
        "hashtags": [{"hashtag": "#" + h, "count": c} for h, c in htags.most_common(40)],
        "languages": [{"lang": l, "count": c} for l, c in langs.most_common()],
        "hour_distribution": hd, "day_distribution": dd,
        "posts": [{"platform": p["platform"], "author": p.get("author"), "text": (p.get("text") or "")[:220],
                   "date": p.get("date"), "score": p.get("score"), "url": p.get("url"), "subreddit": p.get("subreddit")}
                  for p in posts_sorted[:80]],
    })


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except tk.HttpError as e:
        tk.fail("rate_limited" if e.status in (429, 503) else "error", f"Arama: {e}")
    except Exception as e:  # noqa: BLE001
        tk.fail("error", f"Arama araci beklenmedik hata: {e}")
