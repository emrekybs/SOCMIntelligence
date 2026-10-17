#!/usr/bin/env python3
"""
TikTok OSINT Tool
Usage:
  python tiktok_osint.py charlidamelio
  python tiktok_osint.py @khaby.lame
  python tiktok_osint.py https://www.tiktok.com/@charlidamelio
  python tiktok_osint.py user1 user2 user3              # auto-comparison
  python tiktok_osint.py user1 user2 --compare          # force comparison
  python tiktok_osint.py user1 --videos 30              # more videos

Requirements:
  pip install requests rich python-whois matplotlib
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

try:
    import whois as _whois
    HAS_WHOIS = True
except ImportError:
    HAS_WHOIS = False

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

C = Console() if HAS_RICH else None

# ══════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════

DAYS_EN = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

NICHE_MAP = {
    "comedy":    ["funny","comedy","meme","humor","lol","fyp","foryou","viral"],
    "gaming":    ["gaming","game","gamer","minecraft","fortnite","roblox","valorant","fps","pubg"],
    "music":     ["music","song","dance","singing","rap","cover","beat","artist","musician"],
    "fitness":   ["fitness","gym","workout","bodybuilding","health","nutrition","diet","gains"],
    "food":      ["food","recipe","cooking","yummy","foodie","chef","eat","restaurant","mukbang"],
    "beauty":    ["makeup","beauty","skincare","fashion","style","ootd","nails","hair","glow"],
    "education": ["learn","education","tutorial","howto","tips","facts","science","history","study"],
    "travel":    ["travel","explore","adventure","wanderlust","trip","vacation","vlog","tour"],
    "tech":      ["tech","technology","coding","programming","ai","software","developer","iphone"],
    "sports":    ["sports","football","basketball","soccer","nba","nfl","athlete","training","goal"],
    "lifestyle": ["lifestyle","daily","motivation","life","goals","mindset","success","routine"],
    "animals":   ["dog","cat","pet","animals","cute","puppy","kitten","wildlife","bird"],
}

# Sentiment lexicons (Turkish + English words, intentionally bilingual)
POSITIVE_WORDS = {
    "harika","mukemmel","guzel","cok iyi","sevdim","begeniyorum","bravo",
    "super","muthis","inanilmaz","love","great","amazing","perfect","best",
    "awesome","beautiful","fantastic","wonderful","excellent","incredible",
    "fire","goat","iconic","legend","queen","king","cute","adorable",
    "😍","❤️","🔥","👏","💯","🎉","✨","👑","💕","😍","🥰","💪",
}
NEGATIVE_WORDS = {
    "kotu","berbat","sacma","rezalet","igrenc","begenmedim","nefret",
    "hate","bad","ugly","terrible","awful","worst","disgusting","trash",
    "boring","cringe","mid","flop","disappointing","waste","fake","lame",
    "😡","👎","💀","🤮","🗑️","😒","😤","🤢",
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


class BlockedError(Exception):
    """TikTok bot-block / rate-limit / captcha (gecici; hesabin yoklugu degil)."""

# ══════════════════════════════════════════════════════
#  NETWORK HELPERS
# ══════════════════════════════════════════════════════

def parse_target(raw: str) -> str:
    """@user, user, or https://tiktok.com/@user → username only"""
    raw = raw.strip()
    m = re.search(r"tiktok\.com/@([^/?&#\s]+)", raw)
    if m:
        return m.group(1)
    return raw.lstrip("@")


def page_headers() -> dict:
    return {
        "User-Agent":              UA,
        "Accept":                  "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language":         "en-US,en;q=0.9",
        "Accept-Encoding":         "gzip, deflate, br",
        "Connection":              "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest":          "document",
        "Sec-Fetch-Mode":          "navigate",
        "Sec-Fetch-Site":          "none",
        "Cache-Control":           "max-age=0",
    }


def api_headers(referer: str) -> dict:
    return {
        "User-Agent":      UA,
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer":         referer,
        "Sec-Fetch-Dest":  "empty",
        "Sec-Fetch-Mode":  "cors",
        "Sec-Fetch-Site":  "same-origin",
    }


def make_session() -> requests.Session:
    s = requests.Session()
    try:
        s.get("https://www.tiktok.com/", headers=page_headers(), timeout=12)
    except Exception:
        pass
    return s

# ══════════════════════════════════════════════════════
#  DATA FETCH
# ══════════════════════════════════════════════════════

# TikTok user-detail statusCode -> gercek "hesap yok" (bot-block degil)
_TT_NOT_FOUND_CODES = {10202, 10221, 10222, 10231}


def _fetch_user_info_once(session: requests.Session, username: str) -> dict:
    """Tek deneme. Ayirt edilebilir hatalar firlatir:
       LookupError  -> hesap gercekten yok (retry anlamsiz)
       BlockedError -> bot-block / rate-limit / bos HTML (retry mantikli)
    """
    resp = session.get(
        f"https://www.tiktok.com/@{username}",
        headers=page_headers(), timeout=20
    )
    if resp.status_code == 404:
        raise LookupError(f"@{username}: hesap yok (404).")
    if resp.status_code == 429:
        raise BlockedError(f"@{username}: rate-limit (429).")
    resp.raise_for_status()

    m = re.search(
        r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
        resp.text, re.DOTALL
    )
    if not m:
        # Script yoksa TikTok bot-block/captcha veriyor demektir (hesabin yoklugu degil)
        raise BlockedError(f"@{username}: profil HTML'i alinamadi (bot-block/captcha olabilir).")

    data = json.loads(m.group(1))
    detail = data.get("__DEFAULT_SCOPE__", {}).get("webapp.user-detail", {})
    status = detail.get("statusCode")
    if status in _TT_NOT_FOUND_CODES:
        raise LookupError(f"@{username}: hesap bulunamadi (statusCode={status}).")
    ui = detail.get("userInfo", {})
    if not ui:
        # statusCode 0 ama userInfo bos -> genelde block; degilse yine yok say
        if status not in (0, None):
            raise LookupError(f"@{username}: hesap bulunamadi (statusCode={status}).")
        raise BlockedError(f"@{username}: userInfo bos (bot-block olabilir).")
    return ui


def fetch_user_info(session: requests.Session, username: str, retries: int = 2) -> dict:
    """Bot-block/rate-limit gecici olabilir; kisa backoff ile yeniden dener.
       Gercek 'hesap yok' durumunda (LookupError) hemen vazgecer."""
    delay = 1.5
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return _fetch_user_info_once(session, username)
        except LookupError:
            raise  # retry anlamsiz
        except (BlockedError, requests.RequestException, ValueError) as e:
            last = e
            if attempt < retries:
                time.sleep(delay)
                delay *= 2
                try:  # taze oturum, yeni cerez
                    session.cookies.clear()
                    session.get("https://www.tiktok.com/", headers=page_headers(), timeout=12)
                except Exception:
                    pass
    raise BlockedError(str(last) if last else f"@{username}: erisilemedi.")


def fetch_video_items(session: requests.Session, sec_uid: str,
                      username: str, count: int) -> list:
    try:
        r = session.get(
            "https://www.tiktok.com/api/post/item_list/",
            params={"aid": "1988", "app_name": "tiktok_web",
                    "count": str(count), "cursor": "0",
                    "secUid": sec_uid, "sourceType": "8"},
            headers=api_headers(f"https://www.tiktok.com/@{username}"),
            timeout=20
        )
        r.raise_for_status()
        return r.json().get("itemList", [])
    except Exception:
        return []

# ══════════════════════════════════════════════════════
#  PARSE
# ══════════════════════════════════════════════════════

def parse_profile(ui: dict) -> dict:
    u  = ui.get("user",  {})
    st = ui.get("stats", {})

    followers   = st.get("followerCount",  0) or 0
    following   = st.get("followingCount", 0) or 0
    likes       = st.get("heartCount",     0) or 0
    video_count = st.get("videoCount",     0) or 0
    friend_count= st.get("friendCount",    0) or 0
    create_time = u.get("createTime")
    bio         = u.get("signature", "") or ""

    age_days  = _account_age(create_time)
    er        = _engagement_rate(followers, likes, video_count)
    fake      = _fake_score(followers, likes, video_count, following)

    return {
        # Identity
        "username":      u.get("uniqueId",     "N/A"),
        "display_name":  u.get("nickname",     "N/A"),
        "user_id":       u.get("id",           "N/A"),
        "sec_uid":       u.get("secUid",       ""),
        "bio":           bio or "(empty)",
        "verified":      u.get("verified",     False),
        "private":       u.get("privateAccount", False),
        "region":        u.get("region",       "N/A"),
        "language":      u.get("language",     "N/A"),
        "create_time":   create_time,
        "profile_image": u.get("avatarLarger") or u.get("avatarMedium") or "",
        "profile_url":   f"https://www.tiktok.com/@{u.get('uniqueId','')}",
        # Counts
        "followers":     followers,
        "following":     following,
        "likes":         likes,
        "video_count":   video_count,
        "friend_count":  friend_count,
        # Analyses
        "engagement_rate":   er,
        "account_age_days":  age_days,
        "followers_per_day": round(followers / age_days, 1) if age_days else 0.0,
        "fake_score":        fake,
        "fake_label":        _fake_label(fake),
        # Video analyses (filled in later)
        "videos":             [],
        "viral_videos":       [],
        "hashtag_analysis":   {},
        "schedule_analysis":  {},
        "mention_network":    {},
        "bio_link":           {},
        "comment_analysis":   {},
        "posting_frequency":  {},
        "growth_history":     [],
    }


def parse_videos(items: list) -> list:
    out = []
    for item in items:
        desc   = item.get("desc", "")
        vstats = item.get("stats", {})
        author = item.get("author", {}).get("uniqueId", "")
        vid_id = item.get("id", "")
        ctime  = item.get("createTime", 0)
        out.append({
            "id":       vid_id,
            "title":    (desc[:120] if desc else "(untitled)"),
            "url":      f"https://www.tiktok.com/@{author}/video/{vid_id}",
            "views":    vstats.get("playCount",    0) or 0,
            "likes":    vstats.get("diggCount",    0) or 0,
            "comments": vstats.get("commentCount", 0) or 0,
            "shares":   vstats.get("shareCount",   0) or 0,
            "date":     ctime,
            "hashtags": re.findall(r"#(\w+)", desc),
            "mentions": re.findall(r"@(\w+(?:\.\w+)*)", desc),
        })
    return out

# ══════════════════════════════════════════════════════
#  ANALYSIS FUNCTIONS
# ══════════════════════════════════════════════════════

def _account_age(create_time) -> int:
    if not create_time:
        return 0
    try:
        dt = datetime.fromtimestamp(int(create_time), tz=timezone.utc)
        return max((datetime.now(tz=timezone.utc) - dt).days, 1)
    except Exception:
        return 0


def _engagement_rate(followers, likes, video_count) -> float:
    if followers <= 0 or video_count <= 0:
        return 0.0
    return round((likes / video_count / followers) * 100, 2)


def _er_label(er: float) -> str:
    if er == 0:  return "N/A"
    if er >= 10: return "Excellent  >10%"
    if er >= 6:  return "Very Good  6-10%"
    if er >= 3:  return "Good       3-6%"
    if er >= 1:  return "Average    1-3%"
    return             "Low        <1%"


def _er_color(er: float) -> str:
    if er >= 10: return "bright_green"
    if er >= 6:  return "green"
    if er >= 3:  return "yellow"
    if er >= 1:  return "orange1"
    return "red"


def _fake_score(followers, likes, video_count, following) -> int:
    score = 0
    if followers > 0:
        lr = likes / followers
        if lr < 0.5:  score += 35
        elif lr < 2:  score += 20
        elif lr < 5:  score += 10
    if followers > 0 and following > 0:
        ffr = following / followers
        if ffr > 0.9:   score += 25
        elif ffr > 0.5: score += 15
        elif ffr > 0.2: score += 5
    if video_count > 0 and followers > 0:
        fpv = followers / video_count
        if fpv > 5_000_000:   score += 25
        elif fpv > 1_000_000: score += 15
        elif fpv > 500_000:   score += 8
    if video_count == 0 and followers > 1000:
        score += 15
    return min(score, 100)


def _fake_label(s: int) -> str:
    if s >= 70: return "HIGH RISK"
    if s >= 45: return "MEDIUM RISK"
    if s >= 20: return "LOW RISK"
    return "CLEAN"


def _fake_color(s: int) -> str:
    if s >= 70: return "red"
    if s >= 45: return "orange1"
    if s >= 20: return "yellow"
    return "green"


def analyze_viral(videos: list) -> list:
    views = sorted(v["views"] for v in videos if v["views"] > 0)
    if not views:
        return []
    n      = len(views)
    median = views[n // 2] if n % 2 else (views[n//2-1] + views[n//2]) / 2
    thresh = median * 5
    return [v for v in videos if v["views"] >= thresh]


def analyze_hashtags(videos: list) -> dict:
    all_tags = [t.lower() for v in videos for t in v.get("hashtags", [])]
    counter  = Counter(all_tags)
    niche_scores = {
        niche: sum(counter.get(kw, 0) for kw in kws)
        for niche, kws in NICHE_MAP.items()
    }
    niche_scores = {k: v for k, v in niche_scores.items() if v > 0}
    return {
        "top_tags":    counter.most_common(15),
        "top_niche":   max(niche_scores, key=niche_scores.get) if niche_scores else "Unclassified",
        "niche_scores":dict(sorted(niche_scores.items(), key=lambda x: -x[1])[:5]),
        "unique_tags": len(counter),
        "total_uses":  len(all_tags),
    }


def analyze_schedule(videos: list) -> dict:
    days  = Counter()
    hours = Counter()
    for v in videos:
        if not v.get("date"): continue
        dt = datetime.fromtimestamp(int(v["date"]), tz=timezone.utc)
        days[dt.weekday()] += 1
        hours[dt.hour]     += 1
    bd = days.most_common(1)[0][0]  if days  else None
    bh = hours.most_common(1)[0][0] if hours else None
    return {
        "day_dist":       dict(sorted(days.items())),
        "hour_dist":      dict(sorted(hours.items())),
        "best_day_name":  DAYS_EN[bd] if bd is not None else "N/A",
        "best_hour_str":  f"{bh:02d}:00" if bh is not None else "N/A",
    }


def analyze_mentions(videos: list) -> dict:
    all_m = [m.lower() for v in videos for m in v.get("mentions", [])]
    c     = Counter(all_m)
    return {
        "total":   len(all_m),
        "unique":  len(c),
        "top":     c.most_common(10),
    }


# ══════════════════════════════════════════════════════
#  COMMENT ANALYSIS
# ══════════════════════════════════════════════════════

def fetch_comments(session: requests.Session, video_id: str,
                   username: str, count: int = 30) -> list:
    """Comment list for a single video — caller must rate-limit between calls."""
    try:
        r = session.get(
            "https://www.tiktok.com/api/comment/list/",
            params={"aweme_id": video_id, "count": str(count),
                    "cursor": "0", "aid": "1988"},
            headers=api_headers(f"https://www.tiktok.com/@{username}/video/{video_id}"),
            timeout=15
        )
        r.raise_for_status()
        return r.json().get("comments", []) or []
    except Exception:
        return []


def sentiment_score(text: str) -> str:
    """Simple dictionary-based sentiment classifier."""
    t = text.lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in t)
    neg = sum(1 for w in NEGATIVE_WORDS if w in t)
    if pos > neg:   return "positive"
    if neg > pos:   return "negative"
    return "neutral"


def analyze_comments(all_comments: list) -> dict:
    """
    all_comments: [{"video_id":..., "comments":[...]}, ...]
    Output:
      top_commenters  — most active commenters (username, video_count, total_comments)
      top_liked       — most-liked comments
      sentiment       — positive/negative/neutral distribution
      total           — total comment count
    """
    commenter_videos : dict[str, set]  = {}   # username → {video_id, ...}
    commenter_count  : Counter         = Counter()
    all_flat         : list            = []
    sentiment_dist   : Counter         = Counter()

    for bucket in all_comments:
        vid = bucket["video_id"]
        for c in bucket.get("comments", []):
            author = (c.get("user", {}) or {}).get("unique_id", "")
            text   = c.get("text", "")
            likes  = c.get("digg_count", 0) or 0
            ctime  = c.get("create_time", 0)

            if not author:
                continue

            commenter_count[author]             += 1
            commenter_videos.setdefault(author, set()).add(vid)

            sent = sentiment_score(text)
            sentiment_dist[sent] += 1

            all_flat.append({
                "author":   author,
                "text":     text[:200],
                "likes":    likes,
                "date":     ctime,
                "video_id": vid,
                "sentiment":sent,
            })

    top_commenters = [
        {
            "username":     u,
            "total_comments": commenter_count[u],
            "video_count":  len(commenter_videos[u]),
        }
        for u, _ in commenter_count.most_common(10)
    ]

    top_liked = sorted(all_flat, key=lambda x: -x["likes"])[:10]

    total = len(all_flat)
    s     = dict(sentiment_dist)
    pos   = s.get("positive", 0)
    neg   = s.get("negative", 0)
    neu   = s.get("neutral",  0)
    pos_pct = round(pos / total * 100, 1) if total else 0
    neg_pct = round(neg / total * 100, 1) if total else 0

    return {
        "total":          total,
        "videos_scanned": len(all_comments),
        "top_commenters": top_commenters,
        "top_liked":      top_liked,
        "sentiment": {
            "positive": pos, "negative": neg, "neutral": neu,
            "pos_pct": pos_pct, "neg_pct": neg_pct,
        },
    }


# ══════════════════════════════════════════════════════
#  POSTING FREQUENCY SCORE
# ══════════════════════════════════════════════════════

def analyze_posting_frequency(videos: list) -> dict:
    """
    Derives posting routine from video timestamps.
    Activity score 0-100:
      - Posts in last 30 days → base points
      - Weekly average → multiplier
      - Consistency → bonus
    """
    if not videos:
        return {}

    now      = datetime.now(tz=timezone.utc)
    ago30    = now - timedelta(days=30)
    ago90    = now - timedelta(days=90)

    dates = []
    for v in videos:
        if v.get("date"):
            try:
                dt = datetime.fromtimestamp(int(v["date"]), tz=timezone.utc)
                dates.append(dt)
            except Exception:
                pass

    if not dates:
        return {}

    dates.sort(reverse=True)
    last_post   = dates[0]
    days_silent = (now - last_post).days

    videos_30d = sum(1 for d in dates if d >= ago30)
    videos_90d = sum(1 for d in dates if d >= ago90)

    # Average gap (days)
    if len(dates) >= 2:
        spans  = [(dates[i] - dates[i+1]).days for i in range(len(dates)-1)]
        avg_gap= round(sum(spans) / len(spans), 1)
    else:
        avg_gap = None

    per_week = round(videos_30d / 4.3, 1)  # 30 days / 4.3 = weeks

    # Activity score
    score = 0
    score += min(40, videos_30d * 4)          # Last 30 days, max 40 pts
    score += min(20, videos_90d * 1)           # Last 90 days bonus, max 20
    if avg_gap and avg_gap <= 3:   score += 20  # Consistency bonus
    elif avg_gap and avg_gap <= 7: score += 12
    elif avg_gap and avg_gap <= 14:score += 5
    if days_silent <= 7:  score += 20           # Active in last 7 days
    elif days_silent <= 30:score += 10
    score = min(score, 100)

    # Ghost account
    ghost = days_silent > 90

    return {
        "last_post_days_ago": days_silent,
        "last_post_date":     last_post.strftime("%d.%m.%Y"),
        "videos_last_30d":    videos_30d,
        "videos_last_90d":    videos_90d,
        "avg_gap_days":       avg_gap,
        "per_week":           per_week,
        "activity_score":     score,
        "ghost_account":      ghost,
        "activity_label":     (
            "Ghost Account"  if ghost else
            "Very Active"    if score >= 75 else
            "Active"         if score >= 45 else
            "Low Activity"   if score >= 20 else
            "Inactive"
        ),
    }


# ══════════════════════════════════════════════════════
#  GROWTH CHART — ASCII + PNG
# ══════════════════════════════════════════════════════

def build_growth_history(profile: dict) -> list:
    """
    Extrapolates the last 30 days backwards from the current
    followers/day average. Produces 8 estimated points for the
    ASCII + PNG charts.
    """
    fpd      = profile.get("followers_per_day", 0)
    now_ts   = datetime.now(tz=timezone.utc)
    current  = profile["followers"]
    likes_now= profile["likes"]
    vc_now   = profile["video_count"]

    # Split 30 days into 7 equal intervals (8 points incl. today)
    history = []
    for i in range(7, -1, -1):          # from 7 periods ago to today
        days_back = i * (30 // 7)
        dt        = now_ts - timedelta(days=days_back)
        est_foll  = max(0, round(current - fpd * days_back))
        # Estimate likes proportionally too
        ratio     = est_foll / current if current else 1
        history.append({
            "date":      dt.strftime("%Y-%m-%d %H:%M"),
            "followers": est_foll,
            "likes":     round(likes_now * ratio),
            "video_count": vc_now,
            "estimated": True,
        })

    return history


# ══════════════════════════════════════════════════════
#  PROFILE IMAGE DOWNLOAD
# ══════════════════════════════════════════════════════

def download_profile_image(session: requests.Session, profile: dict) -> str:
    """
    Downloads profile picture, saves as tiktok_<username>_avatar.jpg.
    Tries both avatarLarger and avatarMedium.
    """
    urls = [url for url in [
        profile.get("profile_image"),
    ] if url and url.startswith("http")]

    if not urls:
        return ""

    headers = {
        "User-Agent": UA,
        "Referer":    "https://www.tiktok.com/",
    }
    for url in urls:
        try:
            r = session.get(url, headers=headers, timeout=15, stream=True)
            if r.status_code == 200 and "image" in r.headers.get("Content-Type",""):
                ext  = "jpg" if "jpeg" in r.headers.get("Content-Type","") else "png"
                path = f"tiktok_{profile['username']}_avatar.{ext}"
                with open(path, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
                return path
        except Exception:
            continue
    return ""


def plot_growth_ascii(history: list, username: str) -> str:
    """
    Renders growth history as an ASCII chart.
    All points are estimates (back-projected from current followers/day).
    """
    if not history:
        return ""

    lines = []
    title = f"  Follower Growth (estimated) — @{username}"
    lines.append(title)
    lines.append("  " + "─" * 52)

    vals  = [h["followers"] for h in history]
    dates = [h["date"][:10] for h in history]
    mn, mx= min(vals), max(vals)
    rng   = mx - mn or 1
    width = 30

    for i, (d, v, h) in enumerate(zip(dates, vals, history)):
        char   = "░"
        bar_len= max(1, int((v - mn) / rng * width))
        bar    = char * bar_len
        delta  = ""
        if i > 0:
            diff  = v - vals[i-1]
            sign  = "+" if diff >= 0 else ""
            delta = f"  {sign}{diff:,}"
        lines.append(f"  ~{d}  {bar:<{width}}  {v:>10,}{delta}")

    change = vals[-1] - vals[0]
    pct    = change / vals[0] * 100 if vals[0] else 0
    lines.append("  " + "─" * 52)
    lines.append(f"  30-day change: {change:+,} ({pct:+.1f}%)")
    return "\n".join(lines)


def export_growth_png(history: list, username: str) -> str | None:
    """Saves follower growth chart as PNG via matplotlib.
    All data is back-projected (estimated), rendered with dashed line."""
    if not HAS_MPL or not history:
        return None

    try:
        dates     = [datetime.strptime(h["date"][:16], "%Y-%m-%d %H:%M")
                     for h in history]
        followers = [h["followers"]  for h in history]
        likes     = [h["likes"]      for h in history]
    except Exception:
        return None

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    fig.patch.set_facecolor("#0d0d0d")
    for ax in (ax1, ax2):
        ax.set_facecolor("#141414")
        ax.tick_params(colors="#888888", labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor("#2a2a2a")

    ls = "--"

    # Followers
    ax1.plot(dates, followers, color="#00c8ff", linewidth=2, linestyle=ls,
             marker="o", markersize=4, markerfacecolor="#ffffff")
    ax1.fill_between(dates, followers, alpha=0.10, color="#00c8ff")
    ax1.set_ylabel("Followers", color="#888888", fontsize=9)
    ax1.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda x, _:
            f"{x/1e6:.1f}M" if x >= 1e6 else f"{x/1e3:.0f}K" if x >= 1e3 else str(int(x))))
    ax1.grid(axis="y", color="#2a2a2a", linewidth=0.5, linestyle="--")

    # Likes
    ax2.plot(dates, likes, color="#ff4d88", linewidth=2, linestyle=ls,
             marker="o", markersize=4, markerfacecolor="#ffffff")
    ax2.fill_between(dates, likes, alpha=0.10, color="#ff4d88")
    ax2.set_ylabel("Total Likes", color="#888888", fontsize=9)
    ax2.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda x, _:
            f"{x/1e6:.1f}M" if x >= 1e6 else f"{x/1e3:.0f}K" if x >= 1e3 else str(int(x))))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    ax2.grid(axis="y", color="#2a2a2a", linewidth=0.5, linestyle="--")
    fig.autofmt_xdate(rotation=30, ha="right")

    fig.suptitle(f"@{username} — Last 30 Days Growth (estimated)",
                 color="#dddddd", fontsize=11, y=0.99)

    # SOCMIntelligence watermark
    fig.text(0.99, 0.01, "SOCMIntelligence", ha="right", va="bottom",
             color="#333333", fontsize=8, style="italic")

    fig.tight_layout(rect=[0, 0.02, 1, 0.97])
    path = f"tiktok_{username}_growth.png"
    fig.savefig(path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def analyze_bio_link(bio: str) -> dict:
    if not bio or bio == "(empty)":
        return {}
    url_pat = re.compile(r"https?://[^\s\"'<>()]+|(?<!\w)www\.[^\s\"'<>()]+", re.I)
    matches = [m.group(0) for m in url_pat.finditer(bio)]
    if not matches:
        return {}
    raw = matches[0]
    if not raw.startswith("http"):
        raw = "https://" + raw
    result = {"original_url": raw, "final_url": None, "redirect_chain": [], "domain": None, "whois": {}}
    try:
        r = requests.get(raw, headers={"User-Agent": UA}, timeout=10, allow_redirects=True)
        result["final_url"]      = r.url
        result["http_code"]      = r.status_code
        result["redirect_chain"] = [h.url for h in r.history] + [r.url]
    except Exception as e:
        result["error"] = str(e)
    try:
        domain = urlparse(result["final_url"] or raw).netloc.lstrip("www.")
        result["domain"] = domain
    except Exception:
        pass
    if HAS_WHOIS and result.get("domain"):
        try:
            w = _whois.whois(result["domain"])
            def _first(v):
                return str(v[0] if isinstance(v, list) else v or "")
            result["whois"] = {
                "registrar":  str(w.registrar or ""),
                "created":    _first(w.creation_date),
                "expires":    _first(w.expiration_date),
                "country":    str(w.country or ""),
                "org":        str(w.org or ""),
                "nameservers":list(w.name_servers or [])[:3],
            }
        except Exception as e:
            result["whois"] = {"error": str(e)}
    return result

# ══════════════════════════════════════════════════════
#  FORMAT HELPERS
# ══════════════════════════════════════════════════════

def fn(n) -> str:
    try: n = int(n)
    except: return str(n)
    if n >= 1_000_000_000: return f"{n/1e9:.2f}B"
    if n >= 1_000_000:     return f"{n/1e6:.2f}M"
    if n >= 1_000:         return f"{n/1e3:.1f}K"
    return f"{n:,}"


def fts(ts, fmt="%d.%m.%Y") -> str:
    if not ts: return "N/A"
    try: return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime(fmt)
    except: return str(ts)


def fage(days: int) -> str:
    if days <= 0: return "N/A"
    y, m = days // 365, (days % 365) // 30
    parts = []
    if y: parts.append(f"{y} year"  + ("s" if y != 1 else ""))
    if m: parts.append(f"{m} month" + ("s" if m != 1 else ""))
    return ", ".join(parts) or f"{days} day" + ("s" if days != 1 else "")


def ascii_bar(val, max_val, width=16) -> str:
    if max_val == 0: return ""
    filled = max(1, int(val / max_val * width))
    return "█" * filled + "░" * (width - filled)

# ══════════════════════════════════════════════════════
#  OUTPUT — SINGLE PROFILE
# ══════════════════════════════════════════════════════

def print_profile(p: dict):
    c = C

    # ── Header
    vtag  = "[green]✦ Verified[/green]"    if p["verified"] else "[dim]○ Unverified[/dim]"
    ptag  = "[yellow]🔒 Private[/yellow]"   if p["private"]  else "[green]🌐 Public[/green]"
    hdr   = Text()
    hdr.append(f"\n  {p['display_name']}", style="bold white")
    hdr.append(f"  @{p['username']}\n",    style="bold cyan")
    hdr.append(f"  {vtag}  {ptag}\n\n")
    hdr.append(f"  {p['bio']}\n",          style="italic dim")
    hdr.append(f"  {p['profile_url']}\n",  style="dim underline")
    if p.get("avatar_path"):
        hdr.append(f"  Avatar: {p['avatar_path']}", style="dim green")
    c.print(Panel(hdr, title="[bold]Profile[/bold]", border_style="cyan", padding=(0,2)))

    # ── Statistics
    st = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
               border_style="dim", min_width=62, padding=(0,2))
    st.add_column("Metric",  style="dim",        width=22)
    st.add_column("Value",   style="bold white",  justify="right", width=12)
    st.add_column("",        style="dim",         width=28)
    st.add_row("Followers",      fn(p["followers"]),  "")
    st.add_row("Following",      fn(p["following"]),  "")
    st.add_row("Total Likes",    fn(p["likes"]),      "")
    st.add_row("Video Count",    fn(p["video_count"]),"")
    st.add_row("Friends",        fn(p["friend_count"]),"")
    st.add_row("Region / Lang",  f"{p['region']} / {p['language']}", "")
    st.add_row("User ID",        p["user_id"],         "")
    st.add_row("Created",        fts(p["create_time"]), "")
    c.print(Panel(st, title="[bold]Statistics[/bold]", border_style="magenta"))

    # ── Analysis
    er = p["engagement_rate"]; fs = p["fake_score"]
    at = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
               border_style="dim", min_width=62, padding=(0,2))
    at.add_column("Analysis",style="dim",  width=24)
    at.add_column("Score",   justify="right", width=14)
    at.add_column("Note",    style="dim",  width=24)
    at.add_row(
        "Engagement Rate",
        f"[{_er_color(er)}]{er}%[/{_er_color(er)}]",
        _er_label(er)
    )
    at.add_row(
        "Account Age",
        fage(p["account_age_days"]),
        f"created: {fts(p['create_time'])}"
    )
    at.add_row(
        "Growth (followers/day)",
        fn(p["followers_per_day"]),
        ""
    )
    at.add_row(
        "Fake Follower Score",
        f"[{_fake_color(fs)}]{fs}/100[/{_fake_color(fs)}]",
        f"[{_fake_color(fs)}]{p['fake_label']}[/{_fake_color(fs)}]"
    )
    c.print(Panel(at, title="[bold]Profile Analysis[/bold]", border_style="yellow"))

    # ── Recent Videos
    videos = p.get("videos", [])
    if videos:
        viral_ids = {v["id"] for v in p.get("viral_videos", [])}
        vt = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                   border_style="dim", padding=(0,1))
        vt.add_column("#",          style="dim",         width=3)
        vt.add_column("Date",       style="dim",         width=11)
        vt.add_column("Views",      justify="right",     width=11)
        vt.add_column("Likes",      justify="right",     width=8)
        vt.add_column("Comm.",      justify="right",     width=7)
        vt.add_column("Title",                           min_width=28, no_wrap=True)
        vt.add_column("",           width=6)
        for i, v in enumerate(videos[:20], 1):
            viral_tag = "[bright_red]VIRAL[/bright_red]" if v["id"] in viral_ids else ""
            title     = v["title"][:40].replace("\n"," ")
            vt.add_row(str(i), fts(v["date"]),
                       fn(v["views"]), fn(v["likes"]), fn(v["comments"]),
                       title, viral_tag)
        c.print(Panel(vt, title=f"[bold]Last {min(len(videos),20)} Videos[/bold]",
                      border_style="bright_magenta"))

    # ── Viral
    viral = p.get("viral_videos", [])
    if viral:
        all_views = [v["views"] for v in videos if v["views"] > 0]
        median    = sorted(all_views)[len(all_views)//2] if all_views else 1
        vvt = Table(box=box.SIMPLE, show_header=True, header_style="bold red",
                    border_style="dim", padding=(0,1))
        vvt.add_column("Title",        min_width=38, no_wrap=True)
        vvt.add_column("Views",        justify="right", width=12)
        vvt.add_column("Mult.",        justify="right", width=8)
        for v in viral:
            mult  = v["views"] / median if median else 0
            title = v["title"][:38].replace("\n"," ")
            vvt.add_row(title, fn(v["views"]),
                        f"[bright_red]{mult:.1f}x[/bright_red]")
        c.print(Panel(vvt, title=f"[bold]Viral Videos — {len(viral)} (median 5x+)[/bold]",
                      border_style="red"))

    # ── Hashtag
    ht = p.get("hashtag_analysis", {})
    if ht.get("top_tags"):
        htbl = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                     border_style="dim", padding=(0,1))
        htbl.add_column("Hashtag",  style="cyan",    width=20)
        htbl.add_column("Uses",     justify="right", width=8)
        htbl.add_column("",         min_width=18)
        max_c = ht["top_tags"][0][1] if ht["top_tags"] else 1
        for tag, cnt in ht["top_tags"][:12]:
            htbl.add_row(f"#{tag}", str(cnt),
                         f"[green]{ascii_bar(cnt, max_c)}[/green]")
        niche_str = "  ".join(f"{n}({s})" for n,s in list(ht["niche_scores"].items())[:4])
        summary   = (f"  Niche: [bold cyan]{ht['top_niche'].upper()}[/bold cyan]"
                     f"  [dim]{niche_str}[/dim]\n"
                     f"  Unique tags: {ht['unique_tags']}   Total uses: {ht['total_uses']}")
        c.print(Panel(Text.from_markup(summary), title="[bold]Hashtag Summary[/bold]",
                      border_style="dim"))
        c.print(Panel(htbl, title="[bold]Hashtag Analysis[/bold]", border_style="green"))

    # ── Posting Time
    sched = p.get("schedule_analysis", {})
    if sched.get("day_dist"):
        day_h  = {i: DAYS_EN[i][:3] for i in range(7)}
        day_mx = max(sched["day_dist"].values(), default=1)
        hr_mx  = max(sched["hour_dist"].values(), default=1)
        day_lines  = [f"  {day_h.get(k,'?'):<5} {ascii_bar(v, day_mx, 14)}  {v}"
                      for k, v in sorted(sched["day_dist"].items())]
        hour_lines = [f"  {k:02d}:00 {ascii_bar(v, hr_mx, 14)}  {v}"
                      for k, v in sorted(sched["hour_dist"].items())]
        summary = (f"  Most active day : [bold yellow]{sched['best_day_name']}[/bold yellow]\n"
                   f"  Most active hour: [bold yellow]{sched['best_hour_str']}[/bold yellow]")
        c.print(Panel(
            Text.from_markup(
                summary + "\n\n[dim]── Days ──[/dim]\n" +
                "\n".join(day_lines) +
                "\n\n[dim]── Hours ──[/dim]\n" +
                "\n".join(hour_lines)
            ),
            title="[bold]Posting Time Analysis[/bold]", border_style="blue"
        ))

    # ── Mention Network
    mn = p.get("mention_network", {})
    if mn.get("top"):
        mnt = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                    border_style="dim", padding=(0,1))
        mnt.add_column("Account",  style="cyan", width=22)
        mnt.add_column("Mention",  justify="right", width=8)
        mnt.add_column("",         min_width=16)
        max_m = mn["top"][0][1] if mn["top"] else 1
        for acc, cnt in mn["top"][:10]:
            mnt.add_row(f"@{acc}", str(cnt),
                        f"[cyan]{ascii_bar(cnt, max_m)}[/cyan]")
        c.print(Panel(mnt,
                      title=f"[bold]Mention Network — {mn['total']} mentions, {mn['unique']} accounts[/bold]",
                      border_style="blue"))

    # ── Bio Link
    bl = p.get("bio_link", {})
    if bl:
        lines = []
        lines.append(f"  [dim]Raw URL       :[/dim] [cyan]{bl.get('original_url','')}[/cyan]")
        if bl.get("final_url") and bl["final_url"] != bl.get("original_url"):
            lines.append(f"  [dim]Final URL      :[/dim] [cyan]{bl['final_url']}[/cyan]")
        chain = bl.get("redirect_chain", [])
        if len(chain) > 1:
            lines.append(f"  [dim]Redirect ({len(chain)-1}x) :[/dim] " +
                         " → ".join(u[:60] for u in chain))
        lines.append(f"  [dim]Domain        :[/dim] [bold]{bl.get('domain','')}[/bold]")
        lines.append(f"  [dim]HTTP Code     :[/dim] {bl.get('http_code','')}")
        w = bl.get("whois", {})
        if w and "error" not in w:
            for label, key in [("Registrar","registrar"),("Created","created"),
                                ("Expires","expires"),("Country","country"),("Org","org")]:
                if w.get(key):
                    lines.append(f"  [dim]{label:<14}:[/dim] {w[key]}")
            if w.get("nameservers"):
                lines.append(f"  [dim]Nameservers   :[/dim] {', '.join(w['nameservers'])}")
        elif w.get("error"):
            lines.append(f"  [dim]WHOIS Error   :[/dim] [red]{w['error']}[/red]")
        elif not HAS_WHOIS:
            lines.append("  [dim]WHOIS         :[/dim] [dim]pip install python-whois[/dim]")
        c.print(Panel("\n".join(lines), title="[bold]Bio Link Analysis[/bold]",
                      border_style="magenta"))

    # ── Posting Frequency Score
    pf = p.get("posting_frequency", {})
    if pf:
        score  = pf.get("activity_score", 0)
        ghost  = pf.get("ghost_account", False)
        label  = pf.get("activity_label", "")
        scolor = ("red" if ghost or score < 20 else
                  "yellow" if score < 45 else
                  "green"  if score < 75 else "bright_green")
        bar    = ascii_bar(score, 100, 20)
        pf_lines = [
            f"  Activity Score  [{scolor}]{score}/100[/{scolor}]  [{scolor}]{bar}[/{scolor}]  [{scolor}]{label}[/{scolor}]",
            f"  Last post       {pf.get('last_post_date','?')}  ({pf.get('last_post_days_ago','?')} days ago)",
            f"  Last 30 days    {pf.get('videos_last_30d',0)} videos",
            f"  Last 90 days    {pf.get('videos_last_90d',0)} videos",
            f"  Weekly avg.     {pf.get('per_week','?')} videos/week",
        ]
        if pf.get("avg_gap_days") is not None:
            pf_lines.append(f"  Avg. gap        {pf['avg_gap_days']} days")
        if ghost:
            pf_lines.append("  [bright_red]⚠  No posts for 90+ days — ghost account[/bright_red]")
        c.print(Panel(Text.from_markup("\n".join(pf_lines)),
                      title="[bold]Posting Frequency Score[/bold]", border_style="yellow"))

    # ── Comment Analysis
    ca = p.get("comment_analysis", {})
    if ca:
        # Top commenters
        if ca.get("top_commenters"):
            ct = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                       border_style="dim", padding=(0,1))
            ct.add_column("Commenter",     style="cyan", width=22)
            ct.add_column("Comments",      justify="right", width=9)
            ct.add_column("Videos",        justify="right", width=9)
            ct.add_column("",              min_width=16)
            max_c = ca["top_commenters"][0]["total_comments"]
            for cm in ca["top_commenters"]:
                ct.add_row(
                    f"@{cm['username']}",
                    str(cm["total_comments"]),
                    str(cm["video_count"]),
                    f"[cyan]{ascii_bar(cm['total_comments'], max_c)}[/cyan]",
                )
            header = (f"  Scanned: {ca['videos_scanned']} videos   "
                      f"Total comments: {ca['total']:,}")
            c.print(Panel(Text.from_markup(header),
                          title="[bold]Comment Analysis — Summary[/bold]", border_style="dim"))
            c.print(Panel(ct, title="[bold]Most Active Commenters[/bold]",
                          border_style="cyan"))

        # Most-liked comments
        if ca.get("top_liked"):
            lt = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                       border_style="dim", padding=(0,1))
            lt.add_column("Author",  style="cyan", width=18)
            lt.add_column("Likes",   justify="right", width=8)
            lt.add_column("Sent.",   width=10)
            lt.add_column("Comment", min_width=28, no_wrap=True)
            sent_color = {"positive":"green","negative":"red","neutral":"dim"}
            for cm in ca["top_liked"]:
                sc = sent_color.get(cm["sentiment"],"dim")
                lt.add_row(
                    f"@{cm['author']}",
                    str(cm["likes"]),
                    f"[{sc}]{cm['sentiment']}[/{sc}]",
                    cm["text"][:55].replace("\n"," "),
                )
            c.print(Panel(lt, title="[bold]Most-Liked Comments[/bold]",
                          border_style="green"))

        # Sentiment distribution
        sent = ca.get("sentiment", {})
        if sent:
            total_s = sent.get("positive",0) + sent.get("negative",0) + sent.get("neutral",0)
            if total_s:
                pos_bar = ascii_bar(sent.get("positive",0), total_s, 18)
                neg_bar = ascii_bar(sent.get("negative",0), total_s, 18)
                neu_bar = ascii_bar(sent.get("neutral",0),  total_s, 18)
                sent_text = (
                    f"  [green]Positive[/green]  [green]{pos_bar}[/green]  "
                    f"{sent['positive']:>5}  ({sent['pos_pct']}%)\n"
                    f"  [red]Negative[/red]  [red]{neg_bar}[/red]  "
                    f"{sent['negative']:>5}  ({sent['neg_pct']}%)\n"
                    f"  [dim]Neutral [/dim]  [dim]{neu_bar}[/dim]  "
                    f"{sent.get('neutral',0):>5}"
                )
                c.print(Panel(Text.from_markup(sent_text),
                              title="[bold]Sentiment Analysis[/bold]", border_style="yellow"))

    # ── Growth Chart (always show)
    hist = p.get("growth_history", [])
    if hist:
        ascii_chart = plot_growth_ascii(hist, p["username"])
        c.print(Panel(ascii_chart,
                      title="[bold]Last 30 Days — Growth Estimate[/bold]",
                      border_style="dim"))

    c.print(Rule(style="dim"))
    c.print()

# ══════════════════════════════════════════════════════
#  OUTPUT — COMPARISON
# ══════════════════════════════════════════════════════

def print_compare(profiles: list):
    c = C
    c.print()
    c.print(Rule("[bold cyan]Comparison[/bold cyan]", style="cyan"))
    c.print()
    names = [p["username"] for p in profiles]

    def mtbl(title, rows_fn, border="cyan"):
        tbl = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                    border_style="dim", padding=(0,2))
        tbl.add_column("Metric", style="dim", min_width=22)
        for n in names:
            tbl.add_column(f"@{n}", justify="right", min_width=14)
        for label, fn_l in rows_fn:
            tbl.add_row(label, *[fn_l(p) for p in profiles])
        c.print(Panel(tbl, title=f"[bold]{title}[/bold]", border_style=border))

    mtbl("General", [
        ("Display Name",    lambda p: p["display_name"]),
        ("Verified",        lambda p: "✓" if p["verified"] else "✗"),
        ("Private",         lambda p: "Yes" if p["private"] else "No"),
        ("Followers",       lambda p: fn(p["followers"])),
        ("Following",       lambda p: fn(p["following"])),
        ("Total Likes",     lambda p: fn(p["likes"])),
        ("Video Count",     lambda p: fn(p["video_count"])),
        ("Created",         lambda p: fts(p["create_time"])),
        ("Account Age",     lambda p: fage(p["account_age_days"])),
        ("Region",          lambda p: p["region"]),
    ])

    def er_cell(p):
        er = p["engagement_rate"]
        return f"[{_er_color(er)}]{er}%[/{_er_color(er)}]"
    def fake_cell(p):
        s = p["fake_score"]
        return f"[{_fake_color(s)}]{s}/100[/{_fake_color(s)}]"

    mtbl("Analysis Comparison", [
        ("Engagement Rate",     er_cell),
        ("ER Label",            lambda p: _er_label(p["engagement_rate"])),
        ("Growth (foll./day)",  lambda p: fn(p["followers_per_day"])),
        ("Fake Score",          fake_cell),
        ("Risk",                lambda p: p["fake_label"]),
        ("Niche",               lambda p: p.get("hashtag_analysis",{}).get("top_niche","N/A")),
        ("Most Active Day",     lambda p: p.get("schedule_analysis",{}).get("best_day_name","N/A")),
        ("Most Active Hour",    lambda p: p.get("schedule_analysis",{}).get("best_hour_str","N/A")),
        ("Viral Videos",        lambda p: str(len(p.get("viral_videos",[])))),
        ("Top Mentions",        lambda p: (", ".join(f"@{a}" for a,_ in p.get("mention_network",{}).get("top",[])[:2]) or "—")),
    ], border="yellow")

    # Diff — winners
    diff = Table(box=box.SIMPLE, show_header=True, header_style="bold green",
                 border_style="dim", padding=(0,2))
    diff.add_column("Category", style="dim", min_width=26)
    diff.add_column("Winner",   min_width=18)
    diff.add_column("Value",    justify="right")

    def winner(key, label, rev=False):
        valid = [p for p in profiles if isinstance(p.get(key),(int,float)) and p[key] > 0]
        if not valid: return
        best = (min if rev else max)(valid, key=lambda p: p[key])
        diff.add_row(label, f"[green]@{best['username']}[/green]", fn(best[key]))

    winner("followers",          "Most Followers")
    winner("likes",              "Most Likes")
    winner("video_count",        "Most Videos")
    winner("engagement_rate",    "Highest Engagement")
    winner("followers_per_day",  "Fastest Growing")
    winner("fake_score",         "Lowest Fake Score", rev=True)
    c.print(Panel(diff, title="[bold]Diff — Winners[/bold]", border_style="green"))
    c.print(Rule(style="dim"))
    c.print()

# ══════════════════════════════════════════════════════
#  PLAIN OUTPUT
# ══════════════════════════════════════════════════════

def print_plain(p: dict):
    SEP = "=" * 60
    print(SEP)
    print(f"  @{p['username']}  —  {p['display_name']}")
    if p.get("avatar_path"):
        print(f"  Avatar          : {p['avatar_path']}")
    print(SEP)
    print(f"  Followers       : {fn(p['followers'])}")
    print(f"  Following       : {fn(p['following'])}")
    print(f"  Total Likes     : {fn(p['likes'])}")
    print(f"  Videos          : {fn(p['video_count'])}")
    print(f"  Created         : {fts(p['create_time'])}")
    print(f"  Region / Lang   : {p['region']} / {p['language']}")
    print(SEP)
    print(f"  Engagement Rate : {p['engagement_rate']}%  {_er_label(p['engagement_rate'])}")
    print(f"  Account Age     : {fage(p['account_age_days'])}")
    print(f"  Growth (f/day)  : {fn(p['followers_per_day'])}")
    print(f"  Fake Score      : {p['fake_score']}/100  {p['fake_label']}")
    ht = p.get("hashtag_analysis",{})
    if ht.get("top_tags"):
        print(f"  Niche           : {ht['top_niche']}")
        print(f"  Top Tags        : {', '.join('#'+t for t,_ in ht['top_tags'][:5])}")
    sc = p.get("schedule_analysis",{})
    if sc:
        print(f"  Most Active Day : {sc.get('best_day_name','?')}")
        print(f"  Most Active Hour: {sc.get('best_hour_str','?')}")
    mn = p.get("mention_network",{})
    if mn.get("top"):
        print(f"  Top Mentions    : {', '.join('@'+a for a,_ in mn['top'][:3])}")
    print(f"  Viral Videos    : {len(p.get('viral_videos',[]))}")
    print(SEP)
    bl = p.get("bio_link",{})
    if bl:
        print(f"  Bio Link        : {bl.get('original_url','')}")
        print(f"  Domain          : {bl.get('domain','')}")
    print(SEP)
    videos = p.get("videos",[])
    if videos:
        viral_ids = {v["id"] for v in p.get("viral_videos",[])}
        print(f"\n  Last {min(len(videos),20)} Videos:")
        print(f"  {'#':<3} {'Date':<12} {'Views':<13} {'Likes':<9} Title")
        print("  " + "-"*65)
        for i, v in enumerate(videos[:20],1):
            tag = " [VIRAL]" if v["id"] in viral_ids else ""
            print(f"  {i:<3} {fts(v['date']):<12} {fn(v['views']):<13} "
                  f"{fn(v['likes']):<9} {v['title'][:35]}{tag}")

# ══════════════════════════════════════════════════════
#  SAVE JSON
# ══════════════════════════════════════════════════════

def save_json(profiles: list) -> str:
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = "_".join(p["username"] for p in profiles)[:50]
    path = f"tiktok_{name}_{ts}.json"

    def clean(p):
        cp = {}
        for k, v in p.items():
            if k == "sec_uid":
                continue
            cp[k] = v

        # ── Convert tuple lists to dict lists (tuples are not JSON-serializable)
        ht = cp.get("hashtag_analysis", {})
        if ht.get("top_tags") and isinstance(ht["top_tags"][0], tuple):
            ht["top_tags"] = [{"tag": t, "count": c} for t, c in ht["top_tags"]]
        if ht.get("niche_scores") and isinstance(ht["niche_scores"], dict):
            pass  # already dict

        mn = cp.get("mention_network", {})
        if mn.get("top") and mn["top"] and isinstance(mn["top"][0], tuple):
            mn["top"] = [{"account": a, "count": c} for a, c in mn["top"]]

        # ── comment_analysis.top_commenters is already a dict list, OK
        # ── growth_history: estimated bool serializes fine, OK

        # ── Keep everything — no empty-value stripping, full data goes to JSON
        return cp

    data = [clean(p) for p in profiles]
    obj  = data if len(data) > 1 else data[0]

    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)
    return path

# ══════════════════════════════════════════════════════
#  MAIN FLOW
# ══════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description="TikTok OSINT Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tiktok_osint.py charlidamelio
  python tiktok_osint.py @khaby.lame
  python tiktok_osint.py https://www.tiktok.com/@charlidamelio
  python tiktok_osint.py user1 user2 user3              # auto-comparison
  python tiktok_osint.py user1 user2 --compare          # force comparison
  python tiktok_osint.py charlidamelio --videos 30
        """
    )
    ap.add_argument("targets",    nargs="+", help="1-5 username, @username, or TikTok URL")
    ap.add_argument("--compare",  action="store_true", help="Comparison mode")
    ap.add_argument("--videos",   type=int,  default=20, metavar="N",
                    help="Number of videos to fetch (default: 20)")
    args = ap.parse_args()

    targets = list(dict.fromkeys(parse_target(t) for t in args.targets))
    if len(targets) > 5:
        sys.exit("[!] At most 5 accounts.")

    use_rich     = HAS_RICH
    compare_mode = args.compare or len(targets) > 1
    video_limit  = min(max(args.videos, 5), 35)

    if use_rich:
        C.print()
        C.print(Rule("[bold cyan]TikTok OSINT[/bold cyan]", style="cyan"))
        C.print()
        for t in targets:
            C.print(f"  [dim]Target >[/dim] [cyan]@{t}[/cyan]")
        C.print()

    profiles, errors = [], []

    def fetch_all(username: str):
        try:
            session = make_session()
            ui      = fetch_user_info(session, username)
            profile = parse_profile(ui)

            if use_rich:
                C.print(f"  [dim]Profile OK >[/dim] [green]@{username}[/green]  "
                        f"[dim]loading analyses...[/dim]")

            # ── Download profile picture (first job)
            avatar_path = download_profile_image(session, profile)
            profile["avatar_path"] = avatar_path
            if use_rich and avatar_path:
                C.print(f"  [dim]Avatar    >[/dim] [green]{avatar_path}[/green]")

            # Videos
            items = []
            if profile["sec_uid"] and not profile["private"]:
                items = fetch_video_items(session, profile["sec_uid"], username, video_limit)
            videos = parse_videos(items)

            profile["videos"]            = videos
            profile["viral_videos"]      = analyze_viral(videos)
            profile["hashtag_analysis"]  = analyze_hashtags(videos)
            profile["schedule_analysis"] = analyze_schedule(videos)
            profile["mention_network"]   = analyze_mentions(videos)
            profile["posting_frequency"] = analyze_posting_frequency(videos)
            profile["bio_link"]          = analyze_bio_link(profile["bio"])

            # Build growth chart data (always estimated — no persistent DB)
            profile["growth_history"] = build_growth_history(profile)

            # Comment analysis — always runs, first 10 videos, ~1.5s delay each
            if videos and not profile["private"]:
                if use_rich:
                    C.print(f"  [dim]Fetching comments ({min(len(videos),10)} videos)...[/dim]")
                comment_buckets = []
                for v in videos[:10]:
                    cmts = fetch_comments(session, v["id"], username, count=30)
                    comment_buckets.append({"video_id": v["id"], "comments": cmts})
                    time.sleep(1.5)
                profile["comment_analysis"] = analyze_comments(comment_buckets)

            return profile, None
        except LookupError as e:
            return None, (username, f"NOTFOUND: {e}")
        except BlockedError as e:
            return None, (username, f"BLOCKED: {e}")
        except Exception as e:
            return None, (username, str(e))

    with ThreadPoolExecutor(max_workers=min(len(targets), 3)) as ex:
        futs = {ex.submit(fetch_all, t): t for t in targets}
        for fut in as_completed(futs):
            p, err = fut.result()
            if err: errors.append(err)
            else:   profiles.append(p)

    order = {t: i for i, t in enumerate(targets)}
    profiles.sort(key=lambda p: order.get(p["username"], 99))

    for uname, msg in errors:
        if use_rich: C.print(f"[red][!] @{uname}: {msg}[/red]")
        else:        print(f"[!] @{uname}: {msg}")

    if not profiles:
        # Ilk hatanin nedenini disari tasi ki modul dogru siniflandirsin
        reason = errors[0][1] if errors else "No profiles retrieved."
        if "NOTFOUND" in reason:
            sys.exit(f"[!] not found: {reason}")
        if "BLOCKED" in reason:
            sys.exit(f"[!] blocked/rate-limited: {reason}")
        sys.exit(f"[!] No profiles retrieved. {reason}")

    if use_rich: C.print()

    # Output
    if compare_mode and len(profiles) > 1:
        if use_rich: print_compare(profiles)
        else:
            for p in profiles: print_plain(p)
    else:
        for p in profiles:
            if use_rich:
                C.print(Rule(f"[bold cyan]@{p['username']}[/bold cyan]", style="cyan"))
                print_profile(p)
            else:
                print_plain(p)

    # Automatic JSON save
    fname = save_json(profiles)
    if use_rich:
        C.print(Padding(f"[green]✔ JSON saved:[/green] [bold]{fname}[/bold]",
                        pad=(0,0,0,2)))
    else:
        print(f"\n[✔] JSON saved: {fname}")

    # Growth chart PNG export — always (even if estimated)
    for p in profiles:
        hist = p.get("growth_history", [])
        if hist:
            png = export_growth_png(hist, p["username"])
            if png:
                if use_rich:
                    C.print(Padding(f"[green]✔ Growth chart:[/green] [bold]{png}[/bold]",
                                    pad=(0,0,0,2)))
                else:
                    print(f"[✔] Growth chart: {png}")


if __name__ == "__main__":
    main()
