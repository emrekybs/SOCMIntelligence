#!/usr/bin/env python3
"""
SnapOSINT - Snapchat Public Profile Intelligence Tool
Usage: python3 snaposint.py -u <username> [options]
"""

import argparse, requests, json, re, sys, os
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
from collections import Counter

DAYS     = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
DAYS_SHORT = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

# ─── ANSI Colors ──────────────────────────────────────────────────────────────
R  = "\033[91m"   # red
G  = "\033[92m"   # green
Y  = "\033[93m"   # yellow
B  = "\033[94m"   # blue
M  = "\033[95m"   # magenta
C  = "\033[96m"   # cyan
W  = "\033[97m"   # white
DIM= "\033[2m"    # dim
BLD= "\033[1m"    # bold
RST= "\033[0m"    # reset

def c(color, text): return f"{color}{text}{RST}"
def section(title):
    width = 60
    print(f"\n{BLD}{C}{'─'*width}{RST}")
    print(f"{BLD}{W}  {title}{RST}")
    print(f"{BLD}{C}{'─'*width}{RST}")

def field(key, val, color=W):
    print(f"  {DIM}[+]{RST} {C}{key:<24}{RST} {color}{val}{RST}")

# ─── Banners ──────────────────────────────────────────────────────────────────

BANNER = (
    f"{M}\n"
    "   SnapOSINT - Snapchat Public Profile Intelligence\n"
    f"   {Y}Snapchat OSINT Tool v3.0{M}\n"
    f"   {DIM}github.com/snaposint{RST}\n"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.snapchat.com/",
}

CATEGORY_MAP = {
    "public-profile-category-v3-product-brand":   "Product / Brand",
    "public-profile-category-v3-health-beauty":   "Health & Beauty",
    "public-profile-category-v3-creator":         "Creator",
    "public-profile-category-v3-entertainment":   "Entertainment",
    "public-profile-category-v3-news":            "News & Media",
    "public-profile-category-v3-sports":          "Sports",
    "public-profile-category-v3-gaming":          "Gaming",
    "public-profile-category-v3-food":            "Food & Drink",
    "public-profile-category-v3-travel":          "Travel",
    "public-profile-category-v3-fashion":         "Fashion",
}

# ─── Input normalizer ────────────────────────────────────────────────────────

def parse_snapchat_target(raw: str) -> str:
    """
    Accepts:
      spez
      @spez
      snapchat.com/add/spez
      www.snapchat.com/add/spez
      https://www.snapchat.com/add/spez[/...]
      https://www.snapchat.com/@spez
      https://story.snapchat.com/@spez
    Returns: clean username (without @).
    """
    raw = raw.strip().rstrip("/")

    # Snapchat URL — /add/USERNAME
    m = re.search(r"snapchat\.com/add/([A-Za-z0-9._\-]+)", raw, re.I)
    if m: return m.group(1)

    # Snapchat URL — /@USERNAME
    m = re.search(r"snapchat\.com/@([A-Za-z0-9._\-]+)", raw, re.I)
    if m: return m.group(1)

    # @username (strip ALL leading @'s in case of typo)
    while raw.startswith("@"):
        raw = raw[1:]

    return raw.strip()

# ─── Fetch ────────────────────────────────────────────────────────────────────

def fetch_page(username):
    url = f"https://www.snapchat.com/add/{username}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
    except requests.exceptions.Timeout:
        print(f"Snapchat timeout after 20s (user='{username}', url={url})", file=sys.stderr)
        return None, None, "timeout"
    except requests.exceptions.ConnectionError as e:
        print(f"Snapchat connection error: {e} (user='{username}')", file=sys.stderr)
        return None, None, "network"
    except Exception as e:
        print(f"Snapchat network error: {type(e).__name__}: {e} (user='{username}')", file=sys.stderr)
        return None, None, "network"

    if r.status_code == 404:
        print(f"Snapchat user not found: @{username} (HTTP 404)", file=sys.stderr)
        return None, None, "not_found"
    if r.status_code == 429:
        print(f"Snapchat rate limit (HTTP 429) for @{username} - try again later", file=sys.stderr)
        return None, None, "rate_limited"
    if r.status_code != 200:
        print(f"Snapchat HTTP {r.status_code} for @{username} (url={url})", file=sys.stderr)
        return None, None, f"http_{r.status_code}"

    html = r.text
    if not html or len(html) < 500:
        print(f"Snapchat returned empty/tiny response ({len(html)} bytes) for @{username}", file=sys.stderr)
        return None, None, "empty_response"

    nd = None
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                  html, re.DOTALL)
    if m:
        try:
            nd = json.loads(m.group(1))
        except json.JSONDecodeError as e:
            print(f"Snapchat __NEXT_DATA__ JSON parse failed: {e}", file=sys.stderr)
    else:
        print(f"Snapchat page missing __NEXT_DATA__ script (user may be private or page layout changed)", file=sys.stderr)

    return html, nd, "ok"

# ─── Value unwrappers ─────────────────────────────────────────────────────────

def _unwrap(val):
    if isinstance(val, dict) and "value" in val:
        return val["value"]
    return val

def _str(val):
    v = _unwrap(val)
    return str(v).strip() if v else ""

def _int(val):
    v = _unwrap(val)
    if v is None: return 0
    try: return int(str(v).replace(",",""))
    except: return 0

def _ts(val):
    v = _unwrap(val)
    if not v: return None
    try:
        ts = int(str(v))
        if ts > 1_000_000_000_000: ts //= 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except: return None

def _snap_url(s):
    urls = s.get("snapUrls") or {}
    return (_str(urls.get("mediaUrl")) or _str(urls.get("overlayUrl"))
            or _str(s.get("mediaUrl")) or _str(s.get("url")))

def _snap_type(s):
    mt = s.get("snapMediaType", s.get("mediaType", -1))
    if isinstance(mt, int):
        return "Image (JPG)" if mt == 1 else "Video (MP4)"
    return str(mt)

def _parse_snaps(raw):
    out = []
    for s in (raw or []):
        if not isinstance(s, dict): continue
        ts_raw = (s.get("timestampInSec") or s.get("timestamp")
                  or s.get("captureTimeSecs") or s.get("uploadTimestampMs"))
        sid = s.get("snapId")
        snap_id = _str(sid) if isinstance(sid, dict) else str(sid or "")
        out.append({
            "id":       snap_id,
            "url":      _snap_url(s),
            "type":     _snap_type(s),
            "dt":       _ts(ts_raw),
            "duration": float(_unwrap(s.get("durationSecs") or s.get("duration")) or 0),
        })
    return out

# ─── Parse ────────────────────────────────────────────────────────────────────

def parse_all(username, html, nd, debug=False):
    data = {
        "page_title": "", "page_description": "", "is_public": False,
        "username": username, "display_name": "", "badge": "None",
        "profile_pic": "", "background_pic": "",
        "subscriber_count": 0, "bio": "", "website": "None",
        "category": "", "subcategory": "",
        "created_at": None, "last_updated": None,
        "related_accounts": [],
        "snapcode_url": (f"https://app.snapchat.com/web/deeplink/snapcode"
                         f"?username={username}&type=SVG&bitmoji=enable"),
        "stories": [], "highlights": [], "spotlights": [], "lenses": [],
    }

    soup = BeautifulSoup(html, "html.parser")
    t = soup.find("title")
    if t: data["page_title"] = t.get_text(strip=True)
    for sel in [{"name":"description"},{"property":"og:description"}]:
        d = soup.find("meta", attrs=sel)
        if d and d.get("content"): data["page_description"] = d["content"]; break
    for sel in [{"property":"og:image"},{"name":"twitter:image"}]:
        og = soup.find("meta", attrs=sel)
        if og and og.get("content"): data["profile_pic"] = og["content"]; break

    if not nd: return data

    pp = nd.get("props",{}).get("pageProps",{})

    if debug:
        print(f"{Y}[DEBUG] pageProps keys:{RST}", list(pp.keys()))

    try:
        pub = (pp.get("userProfile",{}) or {}).get("publicProfileInfo") or {}

        data["is_public"]        = True
        data["display_name"]     = _str(pub.get("title") or pub.get("displayName"))
        data["bio"]              = _str(pub.get("bio") or pub.get("description"))
        data["subscriber_count"] = _int(pub.get("subscriberCount"))
        website = _str(pub.get("websiteUrl") or pub.get("website"))
        data["website"]          = website if website else "None"
        data["profile_pic"]      = _str(pub.get("profilePictureUrl")
                                        or pub.get("bitmoji3dUrl")
                                        or pub.get("snapcodeImageUrl"))
        data["background_pic"]   = _str(pub.get("squareHeroImageUrl")
                                        or pub.get("backgroundImageUrl"))

        badge = pub.get("badge")
        data["badge"] = str(badge) if badge else "None"

        # Category
        cat_id  = _str(pub.get("categoryStringId"))
        sub_id  = _str(pub.get("subcategoryStringId"))
        data["category"]    = CATEGORY_MAP.get(cat_id, cat_id) if cat_id else ""
        data["subcategory"] = CATEGORY_MAP.get(sub_id, sub_id) if sub_id else ""

        # Timestamps
        data["created_at"]   = _ts(pub.get("creationTimestampMs"))
        data["last_updated"] = _ts(pub.get("lastUpdateTimestampMs"))

        # Related accounts
        for rel in (pub.get("relatedAccountsInfo") or []):
            rp = rel.get("publicProfileInfo") or {}
            data["related_accounts"].append({
                "username":    _str(rp.get("username")),
                "title":       _str(rp.get("title") or rp.get("displayName")),
                "subscribers": _int(rp.get("subscriberCount")),
                "pic":         _str(rp.get("profilePictureUrl")),
            })

        # Stories
        story_node = pp.get("story") or {}
        data["stories"] = _parse_snaps(story_node.get("snapList") or [])

        # Highlights
        for hl in (pp.get("curatedHighlights") or []):
            snaps = _parse_snaps(hl.get("snapList") or [])
            title = _str(hl.get("storyTitle") or hl.get("title"))
            thumb = _str(hl.get("thumbnailUrl"))
            data["highlights"].append({"title": title, "thumbnail": thumb, "snaps": snaps})

        # Spotlights
        for sp in (pp.get("spotlightHighlights") or pp.get("spotlights") or []):
            raw_snaps = sp.get("snapList") or sp.get("snaps") or []
            snaps = []
            for s in raw_snaps:
                if not isinstance(s, dict): continue
                ts_raw = (s.get("timestampInSec") or s.get("timestamp")
                          or s.get("captureTimeSecs"))
                # Spotlight URLs may be under snapUrls or directly as mediaUrl
                urls = s.get("snapUrls") or {}
                url  = (_str(urls.get("mediaUrl")) or _str(urls.get("overlayUrl"))
                        or _str(s.get("mediaUrl")) or _str(s.get("url")))
                # Duration: durationMillis or durationSecs
                dur_raw = (s.get("durationMillis") or s.get("durationMs")
                           or s.get("durationSecs") or s.get("duration") or 0)
                dur_val = _unwrap(dur_raw)
                try:
                    dur = float(dur_val)
                    # If in milliseconds (>1000 for a typical snap duration)
                    if dur > 1000:
                        dur /= 1000
                except:
                    dur = 0.0
                snaps.append({
                    "id":       "",
                    "url":      url,
                    "type":     _snap_type(s),
                    "dt":       _ts(ts_raw),
                    "duration": dur,
                })
            thumb = _str(sp.get("thumbnailUrl") or sp.get("previewImageUrl"))
            name  = _str(sp.get("title") or sp.get("name")) or "Spotlight Snap"
            tags  = sp.get("hashtags") or sp.get("tags") or []
            # Total duration fallback from snap-level durationSecs on spotlight obj
            if not any(sn["duration"] for sn in snaps):
                sp_dur = _unwrap(sp.get("durationSecs") or sp.get("duration") or 0)
                try:
                    total_dur = float(sp_dur or 0)
                    if total_dur > 1000: total_dur /= 1000
                    if snaps: snaps[0]["duration"] = total_dur
                except: pass
            data["spotlights"].append({"name": name, "thumbnail": thumb,
                                       "snaps": snaps, "hashtags": tags})

        data["lenses"] = pp.get("lenses") or []

    except Exception as e:
        import traceback
        print(f"{R}[!] Parse error: {e}{RST}")
        if debug: traceback.print_exc()

    if data["subscriber_count"] == 0 and data["page_description"]:
        m = re.search(r"([\d,.]+)\s*[kK]\s+Abone", data["page_description"])
        if m: data["subscriber_count"] = int(float(m.group(1).replace(",","")) * 1000)

    if data["page_title"]: data["is_public"] = True
    return data

# ─── Analytics ────────────────────────────────────────────────────────────────

def compute_analytics(data):
    now = datetime.now(tz=timezone.utc)
    ana = {}

    # Account age
    created = data["created_at"]
    if created:
        delta = now - created
        years  = delta.days // 365
        months = (delta.days % 365) // 30
        days_r = delta.days % 30
        ana["account_age"] = f"{years}  yr, {months} mo, {days_r} days"
    else:
        ana["account_age"] = "N/A"

    # Last activity
    last = data["last_updated"]
    if last:
        diff = now - last
        if diff.days == 0:
            h = diff.seconds // 3600
            ana["last_active"] = f"{h} hours ago" if h > 0 else "today"
        elif diff.days == 1:
            ana["last_active"] = "yesterday"
        else:
            ana["last_active"] = f"{diff.days} days ago"
    else:
        ana["last_active"] = "N/A"

    # All snaps combined
    all_snaps = list(data["stories"])
    for hl in data["highlights"]: all_snaps.extend(hl["snaps"])
    for sp in data["spotlights"]: all_snaps.extend(sp["snaps"])

    timestamped = [s for s in all_snaps if s["dt"]]
    videos  = [s for s in all_snaps if "Video" in s["type"]]
    images  = [s for s in all_snaps if "Image" in s["type"]]
    total   = len(all_snaps)

    ana["total_snaps"]   = total
    ana["video_count"]   = len(videos)
    ana["image_count"]   = len(images)
    ana["video_pct"]     = (len(videos)/total*100) if total else 0
    ana["image_pct"]     = (len(images)/total*100) if total else 0

    # Spotlight duration stats
    sp_snaps = [sn for sp in data["spotlights"] for sn in sp["snaps"] if sn["duration"]>0]
    if sp_snaps:
        avg_dur = sum(s["duration"] for s in sp_snaps) / len(sp_snaps)
        ana["avg_spotlight_duration"] = f"{avg_dur:.1f}s"
    else:
        ana["avg_spotlight_duration"] = "N/A"

    if timestamped:
        dts = [s["dt"] for s in timestamped]
        oldest = min(dts); newest = max(dts)
        span_days = max((newest - oldest).days, 1)
        ana["first_snap"]  = oldest.strftime("%Y-%m-%d %H:%M UTC")
        ana["last_snap"]   = newest.strftime("%Y-%m-%d %H:%M UTC")
        ana["avg_per_day"] = f"{len(timestamped)/span_days:.2f} snaps/day"

        # Most active day & hour
        day_counter  = Counter(s["dt"].weekday() for s in timestamped)
        hour_counter = Counter(s["dt"].hour      for s in timestamped)
        best_day  = day_counter.most_common(1)[0]
        best_hour = hour_counter.most_common(1)[0]
        ana["most_active_day"]  = f"{DAYS[best_day[0]]} ({best_day[1]} snap)"
        ana["most_active_hour"] = f"{best_hour[0]:02d}:00 UTC ({best_hour[1]} snap)"
        ana["day_counter"]  = day_counter
        ana["hour_counter"] = hour_counter
    else:
        ana["first_snap"] = ana["last_snap"] = ana["avg_per_day"] = "N/A"
        ana["most_active_day"] = ana["most_active_hour"] = "N/A"
        ana["day_counter"] = Counter()
        ana["hour_counter"] = Counter()

    return ana

# ─── Terminal heatmap ─────────────────────────────────────────────────────────

def print_terminal_heatmap(all_snaps):
    timestamped = [s for s in all_snaps if s["dt"]]
    if not timestamped: return

    # Build 24x7 grid
    grid = [[0]*7 for _ in range(24)]
    for s in timestamped:
        grid[s["dt"].hour][s["dt"].weekday()] += 1

    max_val = max(v for row in grid for v in row) or 1

    # Color blocks by density
    def heat_char(v, max_v):
        ratio = v / max_v
        if v == 0:   return f"{DIM}·{RST}", f"{DIM}  {RST}"
        if ratio < 0.25: blk = f"{B}▪{RST}"; num = f"{B}{v:2d}{RST}"
        elif ratio < 0.5: blk = f"{C}▪{RST}"; num = f"{C}{v:2d}{RST}"
        elif ratio < 0.75: blk = f"{Y}▪{RST}"; num = f"{Y}{v:2d}{RST}"
        else: blk = f"{R}▪{RST}"; num = f"{R}{v:2d}{RST}"
        return blk, num

    section("TERMINAL HEATMAP  (UTC)")

    # Header row
    header = "       " + "  ".join(f"{BLD}{W}{d:^5}{RST}" for d in DAYS_SHORT)
    print(header)
    print()

    for h in range(24):
        row_label = f"{DIM}{h:02d}:00{RST} "
        cells = []
        for d in range(7):
            v = grid[h][d]
            _, num = heat_char(v, max_val)
            cells.append(f"{num:>2}")
        # Bar indicator (filled based on hour total)
        hour_total = sum(grid[h])
        bar_len = int((hour_total / max(sum(grid[r][d] for d in range(7)) for r in range(24) if any(grid[r])) * 20)) if any(any(row) for row in grid) else 0
        bar = f"{M}{'█'*bar_len}{DIM}{'░'*(20-bar_len)}{RST}"
        print(f"{row_label}{'  '.join(cells)}  {bar}")

    # Day totals footer
    print()
    footer = "       " + "  ".join(
        f"{Y}{sum(grid[h][d] for h in range(24)):^5}{RST}" for d in range(7)
    )
    print(f"{DIM}TOTAL  {RST}" + "  ".join(
        f"{Y}{sum(grid[h][d] for h in range(24)):^5}{RST}" for d in range(7)
    ))
    print()

    # Legend
    print(f"  {DIM}·{RST} = 0  {B}▪{RST} = low  {C}▪{RST} = mid  {Y}▪{RST} = high  {R}▪{RST} = en high")

# ─── Display ──────────────────────────────────────────────────────────────────

def _fmt(dt): return dt.strftime("%Y-%m-%d %H:%M:%S UTC") if dt else "unknown"

def print_report(data, ana):
    print(BANNER)

    # ── Account Info ──
    section("ACCOUNT INFORMATION")
    field("Page title",        data["page_title"],          W)
    field("Page description",  data["page_description"][:80]+"..." if len(data["page_description"])>80 else data["page_description"], DIM)
    field("Profile",            "🔓 Public" if data["is_public"] else "🔒 Private",
          G if data["is_public"] else R)
    field("Username",          f"@{data['username']}",      Y)
    field("Display name",      data["display_name"] or "N/A", W)
    field("Badge",             data["badge"],               Y if data["badge"]!="None" else DIM)
    field("Subscriber count",  f"{data['subscriber_count']:,}", G)
    field("Bio",               data["bio"] or "(empty)",    W)
    field("Website",           data["website"],             C if data["website"]!="None" else DIM)
    field("Category",          data["category"] or "N/A",  M)
    if data["subcategory"]:
        field("Subcategory",   data["subcategory"],         M)
    field("Profile picture",   data["profile_pic"] or "N/A",  DIM)
    field("Background picture",data["background_pic"] or "N/A", DIM)
    field("Snap code",         data["snapcode_url"],        DIM)

    section("ACCOUNT ANALYSIS")
    field("Account age",        ana["account_age"],          G)
    if data["created_at"]:
        field("Created at", _fmt(data["created_at"]), DIM)
    field("Last active",      ana["last_active"],
          G if "hours ago" in ana["last_active"] or "today" in ana["last_active"]
          else Y if "days ago" in ana["last_active"] and int(ana["last_active"].split()[0])<7
          else R)
    if data["last_updated"]:
        field("Last updated", _fmt(data["last_updated"]),  DIM)

    # Related accounts
    if data["related_accounts"]:
        section("RELATED ACCOUNTS")
        for i, rel in enumerate(data["related_accounts"]):
            subs = f"{rel['subscribers']:,}" if rel["subscribers"] else "hidden"
            print(f"  {C}[{i}]{RST} {BLD}{W}@{rel['username']}{RST}  {DIM}{rel['title']}{RST}  "
                  f"{Y}({subs} subscribers){RST}")

    # ── Stories ──
    section(f"STORIES  [{c(Y, len(data['stories']))} snaps]")
    for i, s in enumerate(data["stories"]):
        typ_color = B if "Video" in s["type"] else M
        print(f"  {DIM}[{i:>2}]{RST} {typ_color}{s['type']:<12}{RST} "
              f"{DIM}{_fmt(s['dt'])}{RST}")
        print(f"       {DIM}{s['url'][:90]}...{RST}" if len(s["url"])>90 else
              f"       {DIM}{s['url']}{RST}")

    # ── Highlights ──
    total_hl_snaps = sum(len(h["snaps"]) for h in data["highlights"])
    section(f"CURATED HIGHLIGHTS  [{c(Y, len(data['highlights']))} groups / "
            f"{c(Y, total_hl_snaps)} snaps]")
    for idx, hl in enumerate(data["highlights"]):
        title = hl["title"] or f"Highlight {idx}"
        print(f"\n  {BLD}{W}[+] Story: {title or '(untitled)'}  "
              f"{Y}{len(hl['snaps'])} snap{RST}")
        for j, s in enumerate(hl["snaps"]):
            typ_color = B if "Video" in s["type"] else M
            print(f"      {DIM}[{j}]{RST} {typ_color}{s['type']:<12}{RST} "
                  f"{DIM}{_fmt(s['dt'])}{RST}")
            print(f"          {DIM}{s['url'][:85]}...{RST}" if len(s["url"])>85 else
                  f"          {DIM}{s['url']}{RST}")

    # ── Spotlights ──
    total_sp_secs = sum(sn["duration"] for sp in data["spotlights"] for sn in sp["snaps"])
    m_sp, s_sp = divmod(int(total_sp_secs), 60)
    section(f"SPOTLIGHTS  [{c(Y, len(data['spotlights']))} spotlight / "
            f"{c(Y, f'{m_sp}m{s_sp:02d}s')} total]")
    print(f"\n  {G}[+]{RST} {W}Number of spotlights:{RST} {Y}{len(data['spotlights'])}{RST}")
    for sp in data["spotlights"]:
        dt_sp = sp["snaps"][0]["dt"] if sp["snaps"] else None
        dur = sum(sn["duration"] for sn in sp["snaps"])
        m2, s2 = divmod(int(dur), 60)
        tags_str = ", ".join(sp["hashtags"]) if sp["hashtags"] else ""
        print()
        print(f"  {G}[+]{RST} {C}Spotlight name:{RST}  {W}{sp['name']}{RST}")
        print(f"  {G}[+]{RST} {C}Thumbnail:{RST}       {DIM}{sp['thumbnail']}{RST}")
        print(f"  {G}[+]{RST} {C}Duration:{RST}        {Y}{m2}m{s2:02d}s{RST}")
        print(f"  {G}[+]{RST} {C}Upload date:{RST}     {W}{_fmt(dt_sp)}{RST}")
        print(f"  {G}[+]{RST} {C}Hashtags:{RST}        {M}{tags_str}{RST}")
        print(f"  {G}[+]{RST} {C}Snaps:{RST}")
        for j, sn in enumerate(sp["snaps"]):
            print(f"  \t{G}[+]{RST} {C}ID:{RST} {W}{j}{RST}")
            print(f"  \t{G}[+]{RST} {C}URL:{RST} {DIM}{sn['url']}{RST}")
    print()
    print(f"  {G}[+]{RST} {C}Total snaps' duration in spotlights:{RST} {Y}{m_sp}m{s_sp:02d}s{RST}")

    # ── Lenses ──
    section(f"LENSES  [{c(Y, len(data['lenses']))}]")
    if not data["lenses"]:
        print(f"  {DIM}No lenses found.{RST}")

    # ── Snap Analytics ──
    section("SNAP ANALYTICS")
    all_snaps = list(data["stories"])
    for hl in data["highlights"]: all_snaps.extend(hl["snaps"])
    for sp in data["spotlights"]: all_snaps.extend(sp["snaps"])

    field("Total snaps",       str(ana["total_snaps"]),     Y)
    field("Video",             f"{ana['video_count']} ({ana['video_pct']:.1f}%)", B)
    field("Image",             f"{ana['image_count']} ({ana['image_pct']:.1f}%)", M)
    field("Avg per day",      ana["avg_per_day"],          G)
    field("First snap",          ana["first_snap"],           DIM)
    field("Last snap",          ana["last_snap"],            DIM)
    field("Most active day",      ana["most_active_day"],      Y)
    field("Most active hour",     ana["most_active_hour"],     Y)
    field("Avg spotlight dur.", ana["avg_spotlight_duration"], C)

    # Mini bar chart per day
    if ana["day_counter"]:
        print(f"\n  {BLD}{W}Daily Distribution:{RST}")
        max_day = max(ana["day_counter"].values()) or 1
        for d in range(7):
            cnt = ana["day_counter"].get(d, 0)
            bar_len = int(cnt / max_day * 25)
            bar_color = R if cnt == max(ana["day_counter"].values()) else C
            bar = f"{bar_color}{'█'*bar_len}{DIM}{'░'*(25-bar_len)}{RST}"
            print(f"    {W}{DAYS[d]:<10}{RST} {bar} {Y}{cnt}{RST}")

    # Terminal heatmap
    print_terminal_heatmap(all_snaps)

# ─── PNG Heatmap ──────────────────────────────────────────────────────────────

def generate_heatmap(data, out_path=None):
    username  = data["username"]
    all_snaps = list(data["stories"])
    for hl in data["highlights"]: all_snaps.extend(hl["snaps"])
    for sp in data["spotlights"]: all_snaps.extend(sp["snaps"])

    timestamped = [s for s in all_snaps if s["dt"]]
    if not timestamped:
        print(f"{R}[-] No timestamped snaps for heatmap.{RST}"); return

    grid = np.zeros((24, 7), dtype=int)
    for s in timestamped:
        grid[s["dt"].hour][s["dt"].weekday()] += 1

    fig, axes = plt.subplots(1, 2, figsize=(16, 8),
                              gridspec_kw={"width_ratios":[3,1]})
    fig.patch.set_facecolor("#0d1117")

    # ── Left: Heatmap ──
    ax = axes[0]
    ax.set_facecolor("#0d1117")
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "snap", ["#161b22","#1f6feb","#388bfd","#a371f7","#f85149"])
    im = ax.imshow(grid, aspect="auto", cmap=cmap, vmin=0, vmax=max(grid.max(),1))

    ax.set_xticks(range(7)); ax.set_xticklabels(DAYS, color="#c9d1d9", fontsize=10)
    ax.set_yticks(range(24)); ax.set_yticklabels(
        [f"{h:02d}:00" for h in range(24)], color="#c9d1d9", fontsize=8)
    ax.set_xlabel("Day of the Week", color="#8b949e", labelpad=10)
    ax.set_ylabel("Hour of the Day (UTC)", color="#8b949e", labelpad=10)
    ax.set_title(f"Upload Time Heatmap — @{username}",
                 color="#ffffff", fontsize=13, pad=15, fontweight="bold")
    for sp in ax.spines.values(): sp.set_edgecolor("#30363d")
    ax.tick_params(colors="#8b949e")

    for r in range(24):
        for c2 in range(7):
            v = grid[r][c2]
            if v > 0:
                ax.text(c2, r, str(v), ha="center", va="center",
                        color="white", fontsize=8, fontweight="bold")

    cbar = fig.colorbar(im, ax=ax, pad=0.02)
    cbar.ax.yaxis.set_tick_params(color="#8b949e")
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="#8b949e")
    cbar.set_label("Snap count", color="#8b949e", labelpad=8)

    # ── Right: Bar charts ──
    ax2 = axes[1]
    ax2.set_facecolor("#0d1117")
    ax2.set_title("Daily Summary", color="#ffffff", fontsize=11, pad=10)

    day_totals = [sum(grid[h][d] for h in range(24)) for d in range(7)]
    colors_bar = ["#f85149" if v == max(day_totals) else "#388bfd" for v in day_totals]
    bars = ax2.barh(DAYS, day_totals, color=colors_bar, height=0.6)
    ax2.set_facecolor("#0d1117")
    ax2.tick_params(colors="#c9d1d9", labelsize=9)
    ax2.set_xlabel("Snap count", color="#8b949e", fontsize=9)
    for spine in ax2.spines.values(): spine.set_edgecolor("#30363d")
    ax2.invert_yaxis()
    for bar, val in zip(bars, day_totals):
        if val > 0:
            ax2.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height()/2,
                     str(val), va="center", color="#c9d1d9", fontsize=9)

    plt.tight_layout(pad=2)
    if out_path is None: out_path = f"snaposint_{username}_heatmap.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"\n{G}[+] Heatmap saved → {os.path.abspath(out_path)}{RST}")

# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        prog="snaposint",
        description="Snapchat public profile OSINT tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 snaposint.py spez
  python3 snaposint.py @spez
  python3 snaposint.py -u spez
  python3 snaposint.py https://www.snapchat.com/add/spez
  python3 snaposint.py https://www.snapchat.com/@spez
  python3 snaposint.py snapchat.com/add/spez
        """
    )
    p.add_argument("target", nargs="?", default=None,
                   help="username, @username, or full Snapchat URL")
    p.add_argument("-u","--username",  default=None,
                   help="(alternative to positional) Snapchat username or URL")
    p.add_argument("-o","--output",    default=None, help="Heatmap PNG output path")
    p.add_argument("--no-heatmap",     action="store_true", help="Skip PNG heatmap")
    p.add_argument("--save-json",      default=None, help="JSON output path (default: snaposint_<username>.json)")
    p.add_argument("--debug-keys",     action="store_true")
    args = p.parse_args()

    raw = args.target or args.username
    if not raw:
        p.error("provide a username (positional argument or -u/--username)")

    username = parse_snapchat_target(raw)
    if not username:
        p.error(f"could not extract a username from: {raw!r}")

    print(f"{C}[*] Target: {Y}@{username}{RST}")
    print(f"{C}[*] Fetching...{RST}\n")

    html, nd, status = fetch_page(username)
    if html is None:
        # status: not_found / rate_limited / timeout / network / empty_response / http_XXX
        # Exit code'lari adapter'a anlamli sinyal olsun diye:
        #   2  = user not found (LookupError)
        #   3  = rate limited / temp failure
        #   1  = diger hata
        if status == "not_found":
            print(f"ERROR: Snapchat user @{username} not found", file=sys.stderr)
            sys.exit(2)
        if status == "rate_limited":
            print(f"ERROR: Snapchat rate-limited scan of @{username}", file=sys.stderr)
            sys.exit(3)
        print(f"ERROR: Snapchat fetch failed ({status}) for @{username}", file=sys.stderr)
        sys.exit(1)

    # __NEXT_DATA__ yoksa da devam etmeyelim - parse calismaz
    if nd is None:
        print(f"ERROR: Snapchat page has no usable data for @{username} (private account, or page structure changed)", file=sys.stderr)
        sys.exit(1)

    try:
        data = parse_all(username, html, nd, debug=args.debug_keys)
        ana  = compute_analytics(data)
    except Exception as e:
        import traceback
        print(f"ERROR: Snapchat parse failed for @{username}: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    json_path = args.save_json or f"snaposint_{username}.json"
    # nd None olsaydi yukaridan exit edilirdi, artik garanti var
    # Build heatmap grid (24h x 7d)
    all_snaps_for_grid = list(data["stories"])
    for hl in data["highlights"]: all_snaps_for_grid.extend(hl["snaps"])
    for sp in data["spotlights"]: all_snaps_for_grid.extend(sp["snaps"])
    grid = [[0]*7 for _ in range(24)]
    for s in all_snaps_for_grid:
        if s["dt"]:
            grid[s["dt"].hour][s["dt"].weekday()] += 1

    data_to_save = {
        "account_information": {
            "page_title":         data["page_title"],
            "page_description":   data["page_description"],
            "is_public":          data["is_public"],
            "username":           data["username"],
            "display_name":       data["display_name"],
            "badge":              data["badge"],
            "profile_picture":    data["profile_pic"],
            "background_picture": data["background_pic"],
            "subscriber_count":   data["subscriber_count"],
            "bio":                data["bio"],
            "website":            data["website"],
            "category":           data["category"],
            "subcategory":        data["subcategory"],
            "snapcode_url":       data["snapcode_url"],
        },
        "account_analysis": {
            "account_age":      ana["account_age"],
            "created_at":       _fmt(data["created_at"]),
            "last_updated":     _fmt(data["last_updated"]),
            "last_active":      ana["last_active"],
            "most_active_day":  ana["most_active_day"],
            "most_active_hour": ana["most_active_hour"],
        },
        "related_accounts": data["related_accounts"],
        "stories": {
            "count": len(data["stories"]),
            "snaps": [
                {
                    "id":          s["id"],
                    "url":         s["url"],
                    "type":        s["type"],
                    "upload_date": _fmt(s["dt"]),
                }
                for s in data["stories"]
            ],
        },
        "curated_highlights": {
            "count":       len(data["highlights"]),
            "total_snaps": sum(len(h["snaps"]) for h in data["highlights"]),
            "highlights": [
                {
                    "title":      hl["title"],
                    "thumbnail":  hl["thumbnail"],
                    "snap_count": len(hl["snaps"]),
                    "snaps": [
                        {
                            "id":          s["id"],
                            "url":         s["url"],
                            "type":        s["type"],
                            "upload_date": _fmt(s["dt"]),
                        }
                        for s in hl["snaps"]
                    ],
                }
                for hl in data["highlights"]
            ],
        },
        "spotlights": {
            "count": len(data["spotlights"]),
            "total_duration_s": sum(
                sn["duration"] for sp in data["spotlights"] for sn in sp["snaps"]
            ),
            "spotlights": [
                {
                    "name":      sp["name"],
                    "thumbnail": sp["thumbnail"],
                    "hashtags":  sp["hashtags"],
                    "snaps": [
                        {
                            "url":         sn["url"],
                            "type":        sn["type"],
                            "upload_date": _fmt(sn["dt"]),
                            "duration_s":  sn["duration"],
                        }
                        for sn in sp["snaps"]
                    ],
                }
                for sp in data["spotlights"]
            ],
        },
        "lenses": {
            "count":  len(data["lenses"]),
            "lenses": data["lenses"],
        },
        "snap_analytics": {
            "total_snaps":            ana["total_snaps"],
            "video_count":            ana["video_count"],
            "video_pct":              round(ana["video_pct"], 1),
            "image_count":            ana["image_count"],
            "image_pct":              round(ana["image_pct"], 1),
            "avg_per_day":            ana["avg_per_day"],
            "first_snap":             ana["first_snap"],
            "last_snap":              ana["last_snap"],
            "most_active_day":        ana["most_active_day"],
            "most_active_hour":       ana["most_active_hour"],
            "avg_spotlight_duration": ana["avg_spotlight_duration"],
            "daily_distribution": {
                DAYS[d]: ana["day_counter"].get(d, 0) for d in range(7)
            },
            "hourly_distribution": {
                f"{h:02d}:00": ana["hour_counter"].get(h, 0) for h in range(24)
            },
        },
        "heatmap": {
            "description": "Grid[hour][day] — hour=0-23 UTC, day=0=Monday..6=Sunday",
            "days":        DAYS,
            "grid": {
                f"{h:02d}:00": {
                    DAYS[d]: grid[h][d] for d in range(7)
                }
                for h in range(24)
            },
        },
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, indent=2, ensure_ascii=False)
    print(f"{G}[+] JSON saved → {json_path}{RST}\n")

    print_report(data, ana)

    if not args.no_heatmap:
        generate_heatmap(data, args.output)

if __name__ == "__main__":
    main()
