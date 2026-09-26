#!/usr/bin/env python3
"""
YouTube OSINT Tool — SOCMIntelligence
═══════════════════════════════
Usage:
  python youtube_osint.py @MrBeast
  python youtube_osint.py https://youtube.com/@MrBeast
  python youtube_osint.py UCX6OQ3DkcsbYNE6H8uQQuVA
  python youtube_osint.py @channel1 @channel2              # auto-comparison
  python youtube_osint.py @channel1 @channel2 --compare    # force comparison
  python youtube_osint.py @channel --videos 30
  python youtube_osint.py @channel --no-color

Requirements:
  pip install requests rich
API key:
  console.cloud.google.com → YouTube Data API v3 → Credentials → API Key
"""

import sys, re, json, argparse, time, os
from collections import Counter
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests

try:
    from rich.console import Console
    from rich.table   import Table
    from rich.panel   import Panel
    from rich.text    import Text
    from rich         import box
    from rich.rule    import Rule
    from rich.padding import Padding
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# ── API Key ───────────────────────────────────────────
# paste the key you got from console.cloud.google.com here
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")   # <-- paste here
# ─────────────────────────────────────────────────────

C  = Console() if HAS_RICH else None
UA = "SOCMIntelligence/1.0"

YT_API = "https://www.googleapis.com/youtube/v3"

CATEGORY_MAP = {
    "1":"Film & Animation","2":"Autos & Vehicles","10":"Music",
    "15":"Pets & Animals","17":"Sports","18":"Short Movies",
    "19":"Travel & Events","20":"Gaming","21":"Videoblogging",
    "22":"People & Blogs","23":"Comedy","24":"Entertainment",
    "25":"News & Politics","26":"Howto & Style","27":"Education",
    "28":"Science & Technology","29":"Nonprofits & Activism","30":"Movies",
    "31":"Anime/Animation","32":"Action/Adventure","33":"Classics",
    "34":"Comedy","35":"Documentary","36":"Drama","37":"Family",
    "38":"Foreign","39":"Horror","40":"Sci-Fi/Fantasy","41":"Thriller",
    "42":"Shorts","43":"Shows","44":"Trailers",
}

POS_WORDS = {"great","love","amazing","awesome","excellent","perfect","best",
             "fantastic","wonderful","brilliant","nice","good","thanks","helpful",
             "incredible","outstanding","superb","fire","goat","insane","wow"}
NEG_WORDS = {"bad","hate","terrible","awful","worst","boring","trash","garbage",
             "stupid","lame","cringe","mid","disgusting","horrible","pathetic",
             "disappointing","waste","fake","annoying","dumb","ugly","skip"}


# ══════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════

def parse_target(raw: str) -> str:
    raw = raw.strip().rstrip("/")
    # Channel ID (UC...)
    if re.match(r"^UC[A-Za-z0-9_\-]{22}$", raw):
        return raw
    # URL ile @handle
    m = re.search(r"youtube\.com/@([A-Za-z0-9_\.\-]+)", raw)
    if m: return "@" + m.group(1)
    # URL ile /channel/UCxxx
    m = re.search(r"youtube\.com/channel/(UC[A-Za-z0-9_\-]{22})", raw)
    if m: return m.group(1)
    # URL ile /user/xxx veya /c/xxx
    m = re.search(r"youtube\.com/(?:user|c)/([A-Za-z0-9_\.\-]+)", raw)
    if m: return "@" + m.group(1)
    # @handle or just username — both normalized to @-prefix
    return "@" + raw.lstrip("@")


def yapi(endpoint: str, **params) -> dict | None:
    params["key"] = YOUTUBE_API_KEY
    try:
        r = requests.get(f"{YT_API}/{endpoint}", params=params,
                         headers={"User-Agent": UA}, timeout=15)
        if r.status_code == 403:
            raise ValueError("API key invalid or quota exceeded (403).")
        if r.status_code == 200:
            return r.json()
        return None
    except ValueError:
        raise
    except Exception:
        return None


def fn(n) -> str:
    try: n = int(n)
    except: return str(n)
    if n >= 1_000_000_000: return f"{n/1e9:.2f}B"
    if n >= 1_000_000:     return f"{n/1e6:.2f}M"
    if n >= 1_000:         return f"{n/1e3:.1f}K"
    return f"{n:,}"


def fts(s) -> str:
    if not s: return "N/A"
    try:
        dt = datetime.fromisoformat(s.replace("Z","+00:00"))
        return dt.strftime("%d.%m.%Y")
    except: return str(s)


def fts_full(s) -> str:
    if not s: return "N/A"
    try:
        dt = datetime.fromisoformat(s.replace("Z","+00:00"))
        return dt.strftime("%d.%m.%Y %H:%M UTC")
    except: return str(s)


def fage(s) -> str:
    if not s: return "N/A"
    try:
        dt   = datetime.fromisoformat(s.replace("Z","+00:00"))
        days = (datetime.now(tz=timezone.utc) - dt).days
        y, m = days // 365, (days % 365) // 30
        parts = []
        if y: parts.append(f"{y} year"  + ("s" if y != 1 else ""))
        if m: parts.append(f"{m} month" + ("s" if m != 1 else ""))
        return ", ".join(parts) or f"{days} day" + ("s" if days != 1 else "")
    except: return "N/A"


def parse_duration(iso: str) -> int:
    """ISO 8601 duration → seconds"""
    if not iso: return 0
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m: return 0
    h, mn, s = (int(x or 0) for x in m.groups())
    return h*3600 + mn*60 + s


def ascii_bar(v, mx, w=16) -> str:
    if mx == 0: return ""
    f = max(1, int(v / mx * w))
    return "█" * f + "░" * (w - f)


def is_empty(v) -> bool:
    if v is None or v == "" or v == "N/A": return True
    if isinstance(v, bool):  return False
    if isinstance(v, (int, float)): return v == 0 and not isinstance(v, bool)
    if isinstance(v, list):  return len(v) == 0
    if isinstance(v, dict):  return len(v) == 0
    return False


def strip_empty(obj):
    if isinstance(obj, dict):
        return {k: strip_empty(v) for k, v in obj.items()
                if not is_empty(strip_empty(v))}
    if isinstance(obj, list):
        return [strip_empty(i) for i in obj if not is_empty(strip_empty(i))]
    return obj


# ══════════════════════════════════════════════════════
#  DATA FETCH
# ══════════════════════════════════════════════════════

def resolve_channel(target: str) -> str | None:
    """Handle or username → Channel ID"""
    if re.match(r"^UC[A-Za-z0-9_\-]{22}$", target):
        return target

    handle = target.lstrip("@")

    # try forHandle
    data = yapi("channels", part="id", forHandle=handle)
    if data and data.get("items"):
        return data["items"][0]["id"]

    # try forUsername
    data = yapi("channels", part="id", forUsername=handle)
    if data and data.get("items"):
        return data["items"][0]["id"]

    # try search endpoint
    data = yapi("search", part="snippet", q=handle,
                type="channel", maxResults=1)
    if data and data.get("items"):
        return data["items"][0].get("snippet",{}).get("channelId") or \
               data["items"][0].get("id",{}).get("channelId")
    return None


def fetch_channel(channel_id: str) -> dict | None:
    data = yapi("channels", part="snippet,statistics,brandingSettings,contentDetails,topicDetails,status",
                id=channel_id)
    if not data or not data.get("items"):
        return None
    return data["items"][0]


def fetch_videos(channel_id: str, limit: int = 20) -> list:
    items   = []
    token   = None
    per_req = min(limit, 50)

    while len(items) < limit:
        params = {"part":"snippet", "channelId":channel_id,
                  "order":"date", "maxResults":per_req, "type":"video"}
        if token: params["pageToken"] = token
        data = yapi("search", **params)
        if not data: break

        video_ids = [i["id"]["videoId"] for i in data.get("items",[])
                     if i.get("id",{}).get("videoId")]
        if not video_ids: break

        # Video details
        details = yapi("videos", part="snippet,statistics,contentDetails",
                       id=",".join(video_ids))
        if details:
            items.extend(details.get("items",[]))

        token = data.get("nextPageToken")
        if not token or len(items) >= limit:
            break
        time.sleep(0.3)

    return items[:limit]


def fetch_playlists(channel_id: str) -> list:
    data = yapi("playlists", part="snippet,contentDetails",
                channelId=channel_id, maxResults=25)
    if not data: return []
    return data.get("items", [])


def fetch_comments(video_id: str, limit: int = 50) -> list:
    data = yapi("commentThreads", part="snippet",
                videoId=video_id, order="relevance",
                maxResults=min(limit, 100),
                textFormat="plainText")
    if not data: return []
    results = []
    for item in data.get("items", []):
        top = item.get("snippet",{}).get("topLevelComment",{}).get("snippet",{})
        results.append({
            "author":  top.get("authorDisplayName",""),
            "text":    top.get("textDisplay","")[:200],
            "likes":   top.get("likeCount", 0),
            "date":    fts(top.get("publishedAt")),
        })
    return results


def wayback_check(channel_url: str) -> dict:
    result = {}
    try:
        r = requests.get(
            "https://web.archive.org/cdx/search/cdx",
            params={"url": channel_url, "output":"json",
                    "limit":20, "fl":"timestamp,statuscode"},
            headers={"User-Agent": UA}, timeout=10
        )
        if r.status_code == 200:
            snaps = r.json()
            if len(snaps) > 1:
                result["snapshots"] = len(snaps) - 1
                result["first"]     = snaps[1][0][:8]
                result["last"]      = snaps[-1][0][:8]
    except Exception:
        pass
    return result


# ══════════════════════════════════════════════════════
#  ANALYSES
# ══════════════════════════════════════════════════════

def analyze_videos(videos: list) -> dict:
    if not videos: return {}

    views_list, likes_list, comments_list = [], [], []
    hour_c, day_c = Counter(), Counter()
    tag_c, cat_c  = Counter(), Counter()
    dur_buckets   = {"shorts(0-60s)":0,"short(1-5min)":0,"medium(5-20min)":0,"long(20min+)":0}
    days_en       = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    total_dur     = 0

    for v in videos:
        sn   = v.get("snippet",{})
        st   = v.get("statistics",{})
        cd   = v.get("contentDetails",{})

        views    = int(st.get("viewCount",0)    or 0)
        likes    = int(st.get("likeCount",0)    or 0)
        comms    = int(st.get("commentCount",0) or 0)
        dur_sec  = parse_duration(cd.get("duration",""))
        pub      = sn.get("publishedAt","")
        tags     = sn.get("tags",[]) or []
        cat_id   = sn.get("categoryId","")

        views_list.append(views)
        likes_list.append(likes)
        comments_list.append(comms)
        total_dur += dur_sec
        tag_c.update([t.lower() for t in tags[:10]])
        if cat_id: cat_c[CATEGORY_MAP.get(cat_id, cat_id)] += 1

        if dur_sec <= 60:                    dur_buckets["shorts(0-60s)"]  += 1
        elif dur_sec <= 300:                 dur_buckets["short(1-5min)"]   += 1
        elif dur_sec <= 1200:                dur_buckets["medium(5-20min)"] += 1
        else:                                dur_buckets["long(20min+)"]    += 1

        if pub:
            try:
                dt = datetime.fromisoformat(pub.replace("Z","+00:00"))
                hour_c[dt.hour]     += 1
                day_c[dt.weekday()] += 1
            except: pass

    n        = len(videos)
    avg_view = round(sum(views_list) / n) if n else 0
    avg_like = round(sum(likes_list) / n) if n else 0

    # Viral detection — median-based
    sorted_v = sorted(views_list)
    median   = sorted_v[n//2] if n % 2 else (sorted_v[n//2-1]+sorted_v[n//2])//2
    viral    = [v for v in videos
                if int(v.get("statistics",{}).get("viewCount",0) or 0) >= median * 5]

    # Engagement rate
    er_list  = []
    for v in views_list:
        idx = views_list.index(v)
        if v > 0:
            er_list.append(round(likes_list[idx] / v * 100, 2))
    avg_er = round(sum(er_list)/len(er_list), 2) if er_list else 0

    # Fake sub score
    # Variables come from outside; prepare here
    best_hour = hour_c.most_common(1)[0][0] if hour_c else None
    best_day  = day_c.most_common(1)[0][0]  if day_c  else None
    tz_offset = None
    if best_hour is not None:
        off = (14 - best_hour) % 24
        if off > 12: off -= 24
        if -12 <= off <= 14:
            tz_offset = f"UTC{'+' if off>=0 else ''}{off} (estimated)"

    top_tags = [{"tag":t,"count":c} for t,c in tag_c.most_common(15)]
    top_cats = [{"category":c,"count":n} for c,n in cat_c.most_common(5)]

    top_by_views = sorted(videos, key=lambda v: int(v.get("statistics",{}).get("viewCount",0) or 0), reverse=True)[:5]
    top_by_likes = sorted(videos, key=lambda v: int(v.get("statistics",{}).get("likeCount",0) or 0), reverse=True)[:5]

    def vinfo(v):
        sn = v.get("snippet",{})
        st = v.get("statistics",{})
        return {
            "title":    sn.get("title","")[:100],
            "video_id": v.get("id",""),
            "url":      f"https://youtu.be/{v.get('id','')}",
            "views":    int(st.get("viewCount",0) or 0),
            "likes":    int(st.get("likeCount",0) or 0),
            "comments": int(st.get("commentCount",0) or 0),
            "date":     fts(sn.get("publishedAt","")),
            "duration": f"{parse_duration(v.get('contentDetails',{}).get('duration',''))//60}min",
            "category": CATEGORY_MAP.get(sn.get("categoryId",""),""),
        }

    return {
        "total":              n,
        "avg_views":          avg_view,
        "avg_likes":          avg_like,
        "avg_engagement_pct": avg_er,
        "median_views":       median,
        "total_duration_h":   round(total_dur / 3600, 1),
        "duration_buckets":   dur_buckets,
        "best_upload_hour":   f"{best_hour:02d}:00" if best_hour is not None else "N/A",
        "best_upload_day":    days_en[best_day] if best_day is not None else "N/A",
        "timezone_est":       tz_offset,
        "hour_distribution":  dict(sorted(hour_c.items())),
        "day_distribution":   dict(sorted(day_c.items())),
        "top_tags":           top_tags,
        "top_categories":     top_cats,
        "viral_videos":       [vinfo(v) for v in viral],
        "top_by_views":       [vinfo(v) for v in top_by_views],
        "top_by_likes":       [vinfo(v) for v in top_by_likes],
        "latest_videos":      [vinfo(v) for v in videos[:10]],
    }


def analyze_comments_bulk(videos: list, max_vids: int = 5) -> dict:
    all_comments = []
    authors      = Counter()
    vid_comment_map = []

    for v in videos[:max_vids]:
        vid_id = v.get("id","")
        if not vid_id: continue
        cmts = fetch_comments(vid_id, limit=50)
        for c in cmts:
            authors[c["author"]] += 1
            all_comments.append(c)
        if cmts:
            vid_comment_map.append({"video_id":vid_id,"count":len(cmts)})
        time.sleep(0.3)

    if not all_comments:
        return {}

    # Sentiment
    pos = neg = neu = 0
    for c in all_comments:
        text = c["text"].lower()
        p = sum(1 for w in POS_WORDS if w in text)
        n = sum(1 for w in NEG_WORDS if w in text)
        if p > n:   pos += 1
        elif n > p: neg += 1
        else:       neu += 1

    total_s = pos + neg + neu
    top_liked = sorted(all_comments, key=lambda x: x["likes"], reverse=True)[:8]
    top_auth  = [{"author":a,"count":c} for a,c in authors.most_common(10)]

    return {
        "total_comments":    len(all_comments),
        "videos_scanned":    len(vid_comment_map),
        "top_commenters":    top_auth,
        "top_liked_comments":[{"author":c["author"],"text":c["text"][:100],
                                "likes":c["likes"],"date":c["date"]}
                               for c in top_liked],
        "sentiment": {
            "positive": pos, "negative": neg, "neutral": neu,
            "pos_pct": round(pos/total_s*100,1) if total_s else 0,
            "neg_pct": round(neg/total_s*100,1) if total_s else 0,
        },
    }


def fake_sub_score(channel: dict, vid_analysis: dict) -> dict:
    """Heuristic fake-subscriber detection score (0-100)."""
    score  = 0
    flags  = []
    subs   = int(channel.get("statistics",{}).get("subscriberCount",0) or 0)
    views  = int(channel.get("statistics",{}).get("viewCount",0) or 0)
    vcount = int(channel.get("statistics",{}).get("videoCount",0) or 0)
    avg_v  = vid_analysis.get("avg_views", 0)
    avg_er = vid_analysis.get("avg_engagement_pct", 0)

    if subs > 0 and views > 0:
        vpsr = views / subs  # views per sub
        if vpsr < 1:
            score += 35
            flags.append(f"Very low views per subscriber ({vpsr:.2f})")
        elif vpsr < 3:
            score += 15

    if subs > 1000 and avg_v > 0:
        ratio = avg_v / subs
        if ratio < 0.01:
            score += 30
            flags.append(f"Avg video views are {ratio*100:.1f}% of subscriber count")
        elif ratio < 0.05:
            score += 15

    if avg_er < 0.5 and subs > 10000:
        score += 20
        flags.append(f"Very low engagement rate: {avg_er}%")

    if vcount == 0 and subs > 1000:
        score += 15
        flags.append("No videos but has subscribers")

    label = ("HIGH RISK"   if score >= 60 else
             "MEDIUM RISK" if score >= 35 else
             "LOW RISK"    if score >= 15 else "CLEAN")
    return {"score": min(score,100), "label": label, "flags": flags}


def analyze_bio_links(description: str) -> dict:
    """
    Extracts URLs and social media accounts from channel description.
    Follows http/https links + matches known platform patterns.
    """
    if not description:
        return {}

    # ── Find all URLs
    url_pat = re.compile(r"https?://[^\s\"'<>()\[\]]+", re.I)
    raw_urls = [m.group(0).rstrip(".,)>") for m in url_pat.finditer(description)]

    # Follow URLs and analyze
    links = []
    seen  = set()
    for url in raw_urls[:8]:
        if url in seen: continue
        seen.add(url)
        entry = {"original": url, "domain": urlparse(url).netloc.lstrip("www.")}
        try:
            r = requests.get(url, headers={"User-Agent": UA},
                             timeout=8, allow_redirects=True)
            final = r.url.rstrip("/")
            entry["final"]     = final
            entry["domain"]    = urlparse(final).netloc.lstrip("www.")
            entry["http_code"] = r.status_code
        except Exception:
            entry["error"] = True
        links.append(entry)

    # ── Find social accounts (inside URLs and from plain text)
    social_patterns = [
        (r"instagram\.com/([A-Za-z0-9_\.]{1,30})",          "Instagram"),
        (r"(?:twitter|x)\.com/([A-Za-z0-9_]{1,15})",        "Twitter/X"),
        (r"tiktok\.com/@([A-Za-z0-9_\.]{1,30})",            "TikTok"),
        (r"twitch\.tv/([A-Za-z0-9_]{1,25})",                "Twitch"),
        (r"discord\.gg/([A-Za-z0-9_\-]{2,32})",             "Discord"),
        (r"discord\.com/invite/([A-Za-z0-9_\-]{2,32})",     "Discord"),
        (r"t\.me/([A-Za-z0-9_]{3,32})",                     "Telegram"),
        (r"facebook\.com/([A-Za-z0-9_\.]{2,50})",           "Facebook"),
        (r"linkedin\.com/in/([A-Za-z0-9_\-]{2,50})",        "LinkedIn"),
        (r"github\.com/([A-Za-z0-9_\-]{1,39})",             "GitHub"),
        (r"patreon\.com/([A-Za-z0-9_]{1,30})",              "Patreon"),
        (r"spotify\.com/(?:artist|user)/([A-Za-z0-9]{10,30})","Spotify"),
        (r"snapchat\.com/add/([A-Za-z0-9_\-\.]{1,30})",     "Snapchat"),
        (r"pinterest\.com/([A-Za-z0-9_\-\.]{1,30})",        "Pinterest"),
        (r"reddit\.com/(?:u|user)/([A-Za-z0-9_\-]{1,30})",  "Reddit"),
        (r"twitch\.tv/([A-Za-z0-9_]{1,25})",                "Twitch"),
        (r"kick\.com/([A-Za-z0-9_]{1,25})",                 "Kick"),
        (r"rumble\.com/(?:c|user)/([A-Za-z0-9_\-]{1,40})",  "Rumble"),
    ]

    social = []
    seen_s = set()
    for pattern, platform in social_patterns:
        for m in re.finditer(pattern, description, re.I):
            handle = m.group(1).rstrip(".,/")
            key    = f"{platform}:{handle.lower()}"
            if key in seen_s: continue
            # Filter out generic words
            if handle.lower() in ("the","and","for","com","www","http","https"):
                continue
            seen_s.add(key)
            social.append({
                "platform": platform,
                "handle":   handle,
                "url":      f"https://{m.group(0).split(m.group(1))[0].lstrip('https://').lstrip('http://')}{handle}",
            })

    result = {}
    if links:  result["links"]   = links
    if social: result["social_accounts"] = social
    return result


# ══════════════════════════════════════════════════════
#  FULL ANALYSIS
# ══════════════════════════════════════════════════════

def full_analyze(target: str, video_limit: int) -> dict:
    result = {
        "target":     target,
        "scanned_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }

    # Resolve Channel ID
    channel_id = resolve_channel(target)
    if not channel_id:
        result["error"] = f"Channel not found: {target}"
        return result

    result["channel_id"]  = channel_id
    result["channel_url"] = f"https://www.youtube.com/channel/{channel_id}"

    # Channel info
    channel = fetch_channel(channel_id)
    if not channel:
        result["error"] = "Could not fetch channel data."
        return result

    sn = channel.get("snippet",{})
    st = channel.get("statistics",{})
    br = channel.get("brandingSettings",{}).get("channel",{})

    handle   = sn.get("customUrl","") or target
    subs     = int(st.get("subscriberCount",0)  or 0)
    views    = int(st.get("viewCount",0)         or 0)
    vcount   = int(st.get("videoCount",0)        or 0)
    pub_at   = sn.get("publishedAt","")

    # Age in days — for growth metrics
    age_days = 0
    try:
        dt = datetime.fromisoformat(pub_at.replace("Z","+00:00"))
        age_days = max((datetime.now(tz=timezone.utc) - dt).days, 1)
    except Exception:
        pass

    result["channel"] = {
        "title":          sn.get("title",""),
        "handle":         handle,
        "description":    sn.get("description",""),
        "channel_url":    f"https://www.youtube.com/{handle}" if handle else result["channel_url"],
        "country":        sn.get("country",""),
        "created_date":   fts(pub_at),
        "account_age":    fage(pub_at),
        "account_age_days": age_days,
        "subscribers":    subs,
        "total_views":    views,
        "video_count":    vcount,
        "avg_views_per_video": round(views/vcount) if vcount else 0,
        "subs_per_day":   round(subs / age_days, 1)  if age_days else 0,
        "views_per_day":  round(views / age_days)    if age_days else 0,
        "verified":       channel.get("status",{}).get("longUploadsStatus") == "allowed",
        "made_for_kids":  channel.get("status",{}).get("madeForKids", False),
        "keywords":       (br.get("keywords","") or "")[:300],
    }

    # Bio link + social media analysis
    desc      = sn.get("description","")
    bio_data  = analyze_bio_links(desc)

    # YouTube brandingSettings.channel.links — verified social links
    # This field holds accounts shown on the "About" page
    channel_links = channel.get("brandingSettings",{}).get("channel",{}).get("links",[]) or []
    if channel_links:
        verified_social = []
        for lnk in channel_links:
            url   = lnk.get("linkUrl","")
            title = lnk.get("linkTitle","")
            if not url: continue
            # Detect platform
            platform = "Link"
            for pat, plat in [
                ("instagram.com",  "Instagram"),
                ("twitter.com",    "Twitter/X"),
                ("x.com",          "Twitter/X"),
                ("tiktok.com",     "TikTok"),
                ("facebook.com",   "Facebook"),
                ("twitch.tv",      "Twitch"),
                ("discord.gg",     "Discord"),
                ("discord.com",    "Discord"),
                ("t.me",           "Telegram"),
                ("spotify.com",    "Spotify"),
                ("patreon.com",    "Patreon"),
                ("github.com",     "GitHub"),
                ("kick.com",       "Kick"),
                ("snapchat.com",   "Snapchat"),
                ("linkedin.com",   "LinkedIn"),
                ("reddit.com",     "Reddit"),
            ]:
                if pat in url.lower():
                    platform = plat
                    break
            verified_social.append({
                "platform": platform,
                "title":    title,
                "url":      url,
            })

        if verified_social:
            existing = bio_data.get("social_accounts", [])
            # Merge with existing, skip duplicates
            existing_urls = {s.get("url","") for s in existing}
            for vs in verified_social:
                if vs["url"] not in existing_urls:
                    existing.append({
                        "platform": vs["platform"],
                        "handle":   vs["title"] or vs["url"],
                        "url":      vs["url"],
                        "verified": True,
                    })
            bio_data["social_accounts"] = existing

    if bio_data:
        result["bio_links"] = bio_data

    # Wayback
    wb = wayback_check(f"youtube.com/channel/{channel_id}")
    if wb:
        result["wayback"] = wb

    # Playlists
    playlists = fetch_playlists(channel_id)
    if playlists:
        result["playlists"] = [
            {"title": p.get("snippet",{}).get("title",""),
             "video_count": p.get("contentDetails",{}).get("itemCount",0),
             "url": f"https://youtube.com/playlist?list={p.get('id','')}"}
            for p in playlists
        ]

    # Videos
    videos = fetch_videos(channel_id, limit=video_limit)
    if videos:
        vid_analysis = analyze_videos(videos)
        result["video_analysis"] = vid_analysis
        result["fake_score"]     = fake_sub_score(channel, vid_analysis)

        # Comment analysis (always runs now)
        result["comment_analysis"] = analyze_comments_bulk(videos, max_vids=5)

    return result


# ══════════════════════════════════════════════════════
#  PRINT
# ══════════════════════════════════════════════════════

def print_result(r: dict):
    c   = C
    ch  = r.get("channel",{})
    va  = r.get("video_analysis",{})
    ca  = r.get("comment_analysis",{})
    fs  = r.get("fake_score",{})

    c.print()
    c.print(Rule(f"[bold red]{ch.get('title','?')}[/bold red]", style="red"))

    # Header
    hdr = Text()
    hdr.append(f"\n  {ch.get('title','')}\n",   style="bold white")
    hdr.append(f"  {ch.get('handle','')}\n",     style="bold red")
    if ch.get("description"):
        hdr.append(f"\n  {ch['description']}\n", style="italic dim")
    hdr.append(f"\n  {ch.get('channel_url','')}", style="dim underline")
    if ch.get("country"):
        hdr.append(f"  🌍 {ch['country']}", style="dim")
    c.print(Panel(hdr, title="[bold]YouTube Channel[/bold]",
                  border_style="red", padding=(0,2)))

    # Statistics
    st = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
               border_style="dim", min_width=62, padding=(0,2))
    st.add_column("Field",  style="dim", width=24)
    st.add_column("Value",  style="bold white", justify="right")
    st.add_column("",       style="dim", width=18)
    st.add_row("Subscribers",        fn(ch.get("subscribers",0)),       "")
    st.add_row("Total Views",        fn(ch.get("total_views",0)),        "")
    st.add_row("Video Count",        fn(ch.get("video_count",0)),        "")
    st.add_row("Avg Views/Video",    fn(ch.get("avg_views_per_video",0)),"")
    st.add_row("Created",            ch.get("created_date","?"),         ch.get("account_age",""))
    if ch.get("made_for_kids"): st.add_row("Content",  "Made for kids", "")
    st.add_row("Channel ID",         r.get("channel_id",""),             "")
    c.print(Panel(st, title="[bold]Statistics[/bold]", border_style="magenta"))

    # Video analysis
    if va:
        days_en = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
        hd  = va.get("hour_distribution",{})
        dd  = va.get("day_distribution",{})
        mx_h = max(hd.values(), default=1)
        mx_d = max(dd.values(), default=1)
        hour_lines = [f"  {k:02d}:00  {ascii_bar(v,mx_h,12)}  {v}"
                      for k,v in sorted(hd.items())]
        day_lines  = [f"  {days_en[k]:<4}  {ascii_bar(v,mx_d,12)}  {v}"
                      for k,v in sorted(dd.items())]

        dur = va.get("duration_buckets",{})
        dur_str = "  ".join(f"[dim]{k}:[/dim]{v}" for k,v in dur.items() if v)

        er_color = ("bright_green" if va.get("avg_engagement_pct",0) >= 5 else
                    "green"        if va.get("avg_engagement_pct",0) >= 2 else
                    "yellow"       if va.get("avg_engagement_pct",0) >= 0.5 else "red")

        c.print(Panel(Text.from_markup(
            f"  Avg. Views          [bold]{fn(va.get('avg_views',0))}[/bold]   "
            f"Median: {fn(va.get('median_views',0))}\n"
            f"  Engagement Rate     [{er_color}]{va.get('avg_engagement_pct',0)}%[/{er_color}]\n"
            f"  Total Duration      {va.get('total_duration_h',0)} hours\n"
            f"  Duration Breakdown  {dur_str}\n"
            f"  Viral Videos        [bright_red]{len(va.get('viral_videos',[]))} (median 5x+)[/bright_red]\n"
            f"  Peak Upload Hour    [bold]{va.get('best_upload_hour','?')}[/bold]\n"
            f"  Peak Upload Day     [bold]{va.get('best_upload_day','?')}[/bold]\n"
            f"  Timezone (est.)     [yellow]{va.get('timezone_est','?')}[/yellow]\n\n"
            "[dim]── Upload Hours ──[/dim]\n" + "\n".join(hour_lines) +
            "\n\n[dim]── Days ──[/dim]\n" + "\n".join(day_lines)
        ), title="[bold]Video Analysis[/bold]", border_style="yellow"))

        # Top tags
        if va.get("top_tags"):
            mx_t = va["top_tags"][0]["count"]
            tt = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                       border_style="dim", padding=(0,1))
            tt.add_column("Tag",     style="cyan", width=22)
            tt.add_column("Count",   justify="right", width=6)
            tt.add_column("",        min_width=16)
            for t in va["top_tags"][:10]:
                tt.add_row(t["tag"], str(t["count"]),
                           f"[cyan]{ascii_bar(t['count'],mx_t)}[/cyan]")
            c.print(Panel(tt, title="[bold]Most Used Tags[/bold]",
                          border_style="cyan"))

        # Viral videos
        if va.get("viral_videos"):
            vt = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                       border_style="dim", padding=(0,1))
            vt.add_column("Views",   justify="right", width=10)
            vt.add_column("Likes",   justify="right", width=8)
            vt.add_column("Date",    style="dim",     width=11, no_wrap=True)
            vt.add_column("Title",   min_width=30,    no_wrap=True)
            med = va.get("median_views",1)
            for v in va["viral_videos"]:
                mult = round(v["views"]/med,1) if med else 0
                vt.add_row(
                    f"[bright_red]{fn(v['views'])} ({mult}x)[/bright_red]",
                    fn(v["likes"]), v["date"], v["title"][:45]
                )
            c.print(Panel(vt, title=f"[bold]Viral Videos — {len(va['viral_videos'])}[/bold]",
                          border_style="bright_red"))

        # Top videos
        if va.get("top_by_views"):
            bvt = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                        border_style="dim", padding=(0,1))
            bvt.add_column("Views",   justify="right", width=10)
            bvt.add_column("Likes",   justify="right", width=8)
            bvt.add_column("Date",    style="dim",     width=11, no_wrap=True)
            bvt.add_column("Title",   min_width=28,    no_wrap=True)
            for v in va["top_by_views"]:
                bvt.add_row(fn(v["views"]), fn(v["likes"]), v["date"], v["title"][:50])
            c.print(Panel(bvt, title="[bold]Most Viewed Videos[/bold]",
                          border_style="green"))

        # Latest videos
        if va.get("latest_videos"):
            lvt = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                        border_style="dim", padding=(0,1))
            lvt.add_column("Date",    style="dim",     width=11, no_wrap=True)
            lvt.add_column("Views",   justify="right", width=10)
            lvt.add_column("Likes",   justify="right", width=8)
            lvt.add_column("Dur.",    style="dim",     width=7)
            lvt.add_column("Title",   min_width=28,    no_wrap=True)
            for v in va["latest_videos"]:
                lvt.add_row(v["date"], fn(v["views"]), fn(v["likes"]),
                            v.get("duration",""), v["title"][:50])
            c.print(Panel(lvt, title="[bold]Latest Videos[/bold]",
                          border_style="bright_magenta"))

    # Fake subscriber score
    if fs:
        sc = fs["score"]
        sc_color = ("red" if sc>=60 else "orange1" if sc>=35
                    else "yellow" if sc>=15 else "green")
        lines = [f"  Score  [{sc_color}]{sc}/100[/{sc_color}]  [{sc_color}]{fs['label']}[/{sc_color}]"]
        for f in fs.get("flags",[]):
            lines.append(f"  [dim]•[/dim] {f}")
        c.print(Panel(Text.from_markup("\n".join(lines)),
                      title="[bold]Fake Subscriber Score[/bold]", border_style=sc_color))

    # Bio links + social accounts
    bl = r.get("bio_links", {})
    if bl:
        links   = bl.get("links", [])
        socials = bl.get("social_accounts", [])

        if links:
            blt = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                        border_style="dim", padding=(0,1))
            blt.add_column("Domain",  style="cyan", width=24)
            blt.add_column("HTTP",    justify="right", width=6)
            blt.add_column("URL",     style="dim", min_width=32, no_wrap=True)
            for b in links:
                co  = "green" if b.get("http_code") == 200 else "red"
                url = b.get("final", b.get("original",""))[:60]
                blt.add_row(b.get("domain","?"),
                            f"[{co}]{b.get('http_code','?')}[/{co}]", url)
            c.print(Panel(blt, title="[bold]Bio Links[/bold]",
                          border_style="magenta"))

        if socials:
            sct = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                        border_style="dim", padding=(0,1))
            sct.add_column("Platform", style="dim",  width=14)
            sct.add_column("Handle",   style="cyan", min_width=22)
            sct.add_column("URL",      style="dim",  min_width=28, no_wrap=True)
            sct.add_column("",         width=9)
            for s in socials:
                verified_tag = "[green]✦ YT[/green]" if s.get("verified") else ""
                sct.add_row(
                    s["platform"],
                    s.get("handle",""),
                    s.get("url","")[:50],
                    verified_tag,
                )
            c.print(Panel(sct, title="[bold]Social Accounts[/bold]",
                          border_style="bright_cyan"))

    # Wayback
    wb = r.get("wayback",{})
    if wb:
        c.print(Panel(
            f"  Snapshot count  : [bold]{wb.get('snapshots','?')}[/bold]\n"
            f"  First archive   : {wb.get('first','?')}\n"
            f"  Last archive    : {wb.get('last','?')}",
            title="[bold]Wayback Machine[/bold]", border_style="dim"
        ))

    # Comment analysis
    if ca:
        sent = ca.get("sentiment",{})
        total_s = sent.get("positive",0)+sent.get("negative",0)+sent.get("neutral",0)
        if total_s:
            pb = ascii_bar(sent["positive"], total_s, 14)
            nb = ascii_bar(sent["negative"], total_s, 14)
            ob = ascii_bar(sent["neutral"],  total_s, 14)
            c.print(Panel(Text.from_markup(
                f"  Videos scanned : {ca.get('videos_scanned',0)}  "
                f"Total comments: {fn(ca.get('total_comments',0))}\n\n"
                f"  [green]Positive[/green]  [green]{pb}[/green]  {sent['positive']} ({sent['pos_pct']}%)\n"
                f"  [red]Negative[/red]  [red]{nb}[/red]  {sent['negative']} ({sent['neg_pct']}%)\n"
                f"  [dim]Neutral [/dim]  [dim]{ob}[/dim]  {sent['neutral']}"
            ), title="[bold]Comment Sentiment Analysis[/bold]", border_style="yellow"))

        if ca.get("top_commenters"):
            mx_c = ca["top_commenters"][0]["count"]
            cmt = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                        border_style="dim", padding=(0,1))
            cmt.add_column("User",      style="cyan", width=28)
            cmt.add_column("Comments",  justify="right", width=9)
            cmt.add_column("",          min_width=16)
            for item in ca["top_commenters"]:
                cmt.add_row(item["author"], str(item["count"]),
                            f"[cyan]{ascii_bar(item['count'],mx_c)}[/cyan]")
            c.print(Panel(cmt, title="[bold]Most Active Commenters[/bold]",
                          border_style="cyan"))

        if ca.get("top_liked_comments"):
            lct = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                        border_style="dim", padding=(0,1))
            lct.add_column("Likes",  justify="right", width=7)
            lct.add_column("Author", style="cyan",    width=20)
            lct.add_column("Date",   style="dim",     width=11, no_wrap=True)
            lct.add_column("Comment",min_width=28,    no_wrap=True)
            for cm in ca["top_liked_comments"]:
                lct.add_row(fn(cm["likes"]), cm["author"], cm["date"],
                            cm["text"][:55].replace("\n"," "))
            c.print(Panel(lct, title="[bold]Top Liked Comments[/bold]",
                          border_style="green"))

    c.print(Rule(style="dim"))
    c.print()


# ══════════════════════════════════════════════════════
#  PRINT — COMPARISON
# ══════════════════════════════════════════════════════

def print_compare(results: list):
    """Side-by-side comparison table for 2-5 channels."""
    c = C
    valid = [r for r in results if not r.get("error")]
    if len(valid) < 2:
        for r in results:
            if not r.get("error"):
                print_result(r)
        return

    c.print()
    c.print(Rule("[bold red]Comparison[/bold red]", style="red"))
    c.print()
    channels = [r.get("channel", {}) for r in valid]
    titles   = [ch.get("title", "?") for ch in channels]

    def mtbl(title, rows_fn, border="red"):
        tbl = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                    border_style="dim", padding=(0, 2))
        tbl.add_column("Metric", style="dim", min_width=24)
        for t in titles:
            tbl.add_column(t[:20], justify="right", min_width=14)
        for label, fn_l in rows_fn:
            tbl.add_row(label, *[fn_l(r) for r in valid])
        c.print(Panel(tbl, title=f"[bold]{title}[/bold]", border_style=border))

    mtbl("General", [
        ("Handle",              lambda r: r["channel"].get("handle", "?")),
        ("Country",             lambda r: r["channel"].get("country", "—") or "—"),
        ("Subscribers",         lambda r: fn(r["channel"].get("subscribers", 0))),
        ("Total Views",         lambda r: fn(r["channel"].get("total_views", 0))),
        ("Video Count",         lambda r: fn(r["channel"].get("video_count", 0))),
        ("Avg Views/Video",     lambda r: fn(r["channel"].get("avg_views_per_video", 0))),
        ("Created",             lambda r: r["channel"].get("created_date", "?")),
        ("Account Age",         lambda r: r["channel"].get("account_age", "?")),
    ])

    mtbl("Growth", [
        ("Subs/day (avg)",      lambda r: fn(r["channel"].get("subs_per_day", 0))),
        ("Views/day (avg)",     lambda r: fn(r["channel"].get("views_per_day", 0))),
    ], border="bright_cyan")

    def er_cell(r):
        er = r.get("video_analysis", {}).get("avg_engagement_pct", 0)
        co = ("bright_green" if er >= 5 else "green" if er >= 2
              else "yellow" if er >= 0.5 else "red")
        return f"[{co}]{er}%[/{co}]"

    def fake_cell(r):
        fs = r.get("fake_score", {})
        s  = fs.get("score", 0)
        co = ("red" if s >= 60 else "orange1" if s >= 35
              else "yellow" if s >= 15 else "green")
        return f"[{co}]{s}/100[/{co}]"

    mtbl("Analysis", [
        ("Engagement Rate",     er_cell),
        ("Median Views",        lambda r: fn(r.get("video_analysis", {}).get("median_views", 0))),
        ("Viral Videos",        lambda r: str(len(r.get("video_analysis", {}).get("viral_videos", [])))),
        ("Total Duration (h)",  lambda r: str(r.get("video_analysis", {}).get("total_duration_h", 0))),
        ("Peak Upload Hour",    lambda r: r.get("video_analysis", {}).get("best_upload_hour", "N/A")),
        ("Peak Upload Day",     lambda r: r.get("video_analysis", {}).get("best_upload_day", "N/A")),
        ("Fake Score",          fake_cell),
        ("Risk",                lambda r: r.get("fake_score", {}).get("label", "N/A")),
    ], border="yellow")

    # ── Diff: winners per metric
    diff = Table(box=box.SIMPLE, show_header=True, header_style="bold green",
                 border_style="dim", padding=(0, 2))
    diff.add_column("Category", style="dim", min_width=26)
    diff.add_column("Winner",   min_width=20)
    diff.add_column("Value",    justify="right")

    def winner(getter, label, rev=False):
        scored = [(r, getter(r)) for r in valid]
        scored = [(r, v) for r, v in scored if isinstance(v, (int, float)) and v > 0]
        if not scored:
            return
        best = (min if rev else max)(scored, key=lambda x: x[1])
        diff.add_row(label, f"[green]{best[0]['channel'].get('title','?')[:20]}[/green]",
                     fn(best[1]))

    winner(lambda r: r["channel"].get("subscribers", 0),       "Most Subscribers")
    winner(lambda r: r["channel"].get("total_views", 0),       "Most Total Views")
    winner(lambda r: r["channel"].get("video_count", 0),       "Most Videos")
    winner(lambda r: r["channel"].get("avg_views_per_video",0),"Best Avg Views")
    winner(lambda r: r["channel"].get("subs_per_day", 0),      "Fastest Subs/day")
    winner(lambda r: r["channel"].get("views_per_day", 0),     "Fastest Views/day")
    winner(lambda r: r.get("video_analysis", {}).get("avg_engagement_pct", 0),
           "Highest Engagement")
    winner(lambda r: r.get("fake_score", {}).get("score", 0),
           "Lowest Fake Score", rev=True)

    c.print(Panel(diff, title="[bold]Diff — Winners[/bold]", border_style="green"))
    c.print(Rule(style="dim"))
    c.print()


# ══════════════════════════════════════════════════════
#  SAVE JSON
# ══════════════════════════════════════════════════════

def save_json(results: list) -> str:
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = "_".join(
        (r.get("channel",{}).get("title") or r.get("target","?"))[:20]
        for r in results
    )[:50]
    path = f"youtube_{name}_{ts}.json"
    cleaned = [strip_empty(r) for r in results]
    with open(path,"w",encoding="utf-8") as f:
        json.dump(cleaned if len(cleaned)>1 else cleaned[0],
                  f, ensure_ascii=False, indent=2, default=str)
    return path


# ══════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════

def main():
    if not YOUTUBE_API_KEY:
        sys.exit("[!] YOUTUBE_API_KEY is empty! Paste your key into the YOUTUBE_API_KEY line at the top of the file.")

    ap = argparse.ArgumentParser(
        description="YouTube OSINT Tool — SOCMIntelligence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python youtube_osint.py @MrBeast
  python youtube_osint.py https://youtube.com/@MrBeast
  python youtube_osint.py UCX6OQ3DkcsbYNE6H8uQQuVA
  python youtube_osint.py @channel1 @channel2              # auto-comparison
  python youtube_osint.py @channel1 @channel2 --compare    # force comparison
  python youtube_osint.py @channel --videos 30
  python youtube_osint.py @channel --no-color
        """
    )
    ap.add_argument("targets",    nargs="+", help="@handle, URL, or Channel ID (1-5 targets)")
    ap.add_argument("--compare",  action="store_true", help="Comparison mode")
    ap.add_argument("--videos",   type=int,  default=20, metavar="N",
                    help="Number of videos to fetch (default: 20, max: 50)")
    ap.add_argument("--no-color", action="store_true", help="Plain output without Rich")
    args = ap.parse_args()

    use_rich     = HAS_RICH and not args.no_color
    targets      = list(dict.fromkeys(parse_target(t) for t in args.targets))
    if len(targets) > 5:
        sys.exit("[!] At most 5 channels.")
    video_limit  = min(max(args.videos, 5), 50)
    compare_mode = args.compare or len(targets) > 1

    if use_rich:
        C.print()
        C.print(Rule("[bold red]YouTube OSINT — SOCMIntelligence[/bold red]", style="red"))
        C.print()
        for t in targets:
            C.print(f"  [dim]Target >[/dim] [red]{t}[/red]")
        C.print()

    results = []

    def run_one(target):
        if use_rich:
            C.print(f"  [dim]Scanning >[/dim] [red]{target}[/red]")
        return full_analyze(target, video_limit)

    with ThreadPoolExecutor(max_workers=min(len(targets), 2)) as ex:
        futs = {ex.submit(run_one, t): t for t in targets}
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as e:
                t = futs[fut]
                if use_rich: C.print(f"  [red][!] {t}: {e}[/red]")
                else: print(f"[!] {t}: {e}")

    order = {t: i for i, t in enumerate(targets)}
    results.sort(key=lambda r: order.get(r.get("target",""), 99))

    if not results:
        sys.exit("[!] No results retrieved.")

    if use_rich: C.print()

    # Print errors first, separately
    for r in results:
        if r.get("error"):
            if use_rich:
                C.print(Panel(f"  [red]{r['error']}[/red]",
                              title=f"[bold]{r.get('target','?')}[/bold]",
                              border_style="red"))
            else:
                print(f"[!] {r.get('target','?')}: {r['error']}")

    # Render per-channel or comparison
    if compare_mode and use_rich and len([r for r in results if not r.get("error")]) >= 2:
        print_compare(results)
    else:
        for r in results:
            if r.get("error"):
                continue
            if use_rich:
                print_result(r)
            else:
                ch = r.get("channel",{})
                print(f"{ch.get('title','?')}  {fn(ch.get('subscribers',0))} subs  "
                      f"{fn(ch.get('total_views',0))} views  {ch.get('created_date','?')}")

    fname = save_json(results)
    if use_rich:
        C.print(Padding(f"[green]✔ JSON saved:[/green] [bold]{fname}[/bold]",
                        pad=(0,0,1,2)))
    else:
        print(f"\n[✔] JSON saved: {fname}")


if __name__ == "__main__":
    main()
