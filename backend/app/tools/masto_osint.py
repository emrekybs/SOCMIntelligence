#!/usr/bin/env python3
"""
Masto OSINT — auto-detect input, multi-strategy discovery, full OSINT
=====================================================================
Smart input (no flags needed):

  python masto.py gargron                       # username scan (all instances)
  python masto.py mastodon.social               # instance + admin info
  python masto.py @gargron@mastodon.social      # targeted + wide scan
  python masto.py https://mastodon.social/@gargron
  python masto.py a b c                         # multiple

Discovery strategy per instance (all tried, results merged):
  1. /api/v1/accounts/lookup?acct=username      (fast path, no auth)
  2. /.well-known/webfinger?resource=acct:...   (federation protocol)
  3. /api/v1/directory?q=...&local=true         (profile directory)

Extra OSINT per hit:
  - Recent 20 statuses: hashtags, mentions, languages, hours/days,
    post frequency, top post, URLs shared, visibility breakdown
  - Pinned posts
  - Avatar download + MD5/SHA256 + EXIF (Pillow opt.) + pHash (imagehash opt.)
  - Custom profile fields (Mastodon "fields")

Requirements:
  pip install requests rich
  # optional, improves avatar analysis:
  pip install Pillow imagehash
"""

import sys, os, re, json, argparse, time, hashlib, io
from urllib.parse       import urlparse, quote
from datetime           import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections        import Counter

try:
    import requests
except ImportError:
    sys.exit("[!] pip install requests")

try:
    from rich.console import Console
    from rich.table   import Table
    from rich.panel   import Panel
    from rich.text    import Text
    from rich         import box
    from rich.rule    import Rule
    HAS_RICH = True
    C = Console()
except ImportError:
    HAS_RICH = False
    C = None


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

INSTANCES_SOCIAL_LIST = "https://instances.social/api/1.0/instances/list"

SEED_INSTANCES = [
    "mastodon.social", "mstdn.social", "mastodon.online",
    "fosstodon.org", "infosec.exchange", "hachyderm.io",
    "mas.to", "mastodon.world", "techhub.social", "toot.community",
    "mastodon.art", "mstdn.jp", "pawoo.net", "mastodon.cloud",
    "social.vivaldi.net", "universeodon.com", "mastodon.gamedev.place",
    "mastodonapp.uk", "toot.wales", "mastodon.scot",
    "counter.social", "mastodon.nl", "masto.ai", "mastodon.xyz",
    "octodon.social", "framapiaf.org", "social.tchncs.de",
    "nerdculture.de", "chaos.social", "troet.cafe",
    "fediscience.org", "scholar.social", "mastodon.green",
    "vis.social", "toot.cafe", "tooter.social",
    "sciencemastodon.com", "mastodon.education", "mastodon.ie",
    "mastodon.au", "aus.social", "defcon.social",
    "infosec.town", "ioc.exchange", "social.liw.fi",
    "masto.es", "mastodon.nz", "ohai.social",
    "tech.lgbt", "queer.party", "social.coop",
    "mastodon.ml", "mastodon.cr", "mstdn.ca",
    "glammr.us", "hcommons.social", "occult.camp",
    "0sint.social", "ruby.social", "phpc.social",
    "hostux.social", "mastodon.top", "mastodon.uno",
    "fediverse.social", "mastodon.sdf.org", "indieweb.social",
    "mastodon.ee", "mastodon.in", "toot.io", "botsin.space",
    "tilde.zone", "librem.one", "sigmoid.social", "mathstodon.xyz",
    "writing.exchange", "famichiki.jp", "mstdn.io", "mastodon.su",
]


class Log:
    def info(self, m):
        if HAS_RICH: C.print(f"[cyan][*][/cyan] {m}")
        else:        print(f"[*] {m}")
    def good(self, m):
        if HAS_RICH: C.print(f"[green][+][/green] {m}")
        else:        print(f"[+] {m}")
    def bad(self, m):
        if HAS_RICH: C.print(f"[red][-][/red] {m}")
        else:        print(f"[-] {m}")
    def warn(self, m):
        if HAS_RICH: C.print(f"[yellow][!][/yellow] {m}")
        else:        print(f"[!] {m}")

LOG = Log()

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept": "application/json"})

def _get(url, timeout=8, accept=None):
    try:
        headers = {}
        if accept: headers["Accept"] = accept
        r = SESSION.get(url, timeout=timeout, headers=headers)
        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                return r.text
        return None
    except requests.RequestException:
        return None

def _get_bytes(url, timeout=15):
    try:
        r = SESSION.get(url, timeout=timeout)
        if r.status_code == 200:
            return r.content
    except requests.RequestException:
        pass
    return None


# ══════════════════════════════════════════════════════
#  Input detection
# ══════════════════════════════════════════════════════

def detect_input_type(raw: str):
    raw = raw.strip().rstrip("/").strip("<>\"'")
    if not raw:
        return "invalid", {"raw": raw}

    m = re.match(
        r"(?:https?://)?(?:www\.)?"
        r"([A-Za-z0-9][A-Za-z0-9\-.]+\.[A-Za-z]{2,})"
        r"/@([A-Za-z0-9_]+)/?$",
        raw
    )
    if m:
        return "qualified", {"username": m.group(2), "instance": m.group(1).lower()}

    m = re.match(r"^@?([A-Za-z0-9_]{1,30})@([A-Za-z0-9\-.]+\.[A-Za-z]{2,})$", raw)
    if m:
        return "qualified", {"username": m.group(1), "instance": m.group(2).lower()}

    if "." in raw and not raw.startswith("@"):
        host = re.sub(r"^https?://", "", raw, flags=re.I)
        host = host.split("/", 1)[0].split("@")[-1]
        if re.match(r"^[A-Za-z0-9][A-Za-z0-9\-.]+\.[A-Za-z]{2,}$", host):
            return "instance", {"instance": host.lower()}

    u = raw.lstrip("@").strip()
    if re.match(r"^[A-Za-z0-9_]{1,30}$", u):
        return "username", {"username": u}

    return "invalid", {"raw": raw}


# ══════════════════════════════════════════════════════
#  Instance list
# ══════════════════════════════════════════════════════

_CACHE = None

def get_instance_list(max_count=500):
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    LOG.info(f"Fetching instance directory (target ≈ {max_count})...")
    try:
        r = SESSION.get(
            INSTANCES_SOCIAL_LIST,
            params={"count": min(max_count, 10000),
                    "sort_by": "users", "sort_order": "desc",
                    "include_down": "false"},
            timeout=15,
        )
        if r.status_code == 200:
            items = (r.json() or {}).get("instances", [])
            names = [it.get("name") for it in items if it.get("name")]
            merged = list(dict.fromkeys(SEED_INSTANCES + names))[:max_count]
            LOG.good(f"Got {len(merged)} instances (seed + directory)")
            _CACHE = merged
            return merged
    except requests.RequestException as e:
        LOG.warn(f"instances.social fetch failed: {e}")
    LOG.warn(f"Using seed list ({len(SEED_INSTANCES)} instances)")
    _CACHE = SEED_INSTANCES[:max_count]
    return _CACHE


# ══════════════════════════════════════════════════════
#  Discovery strategies
# ══════════════════════════════════════════════════════

def _fetch_full_account(instance, acc_id):
    """After a lookup, fetch /api/v1/accounts/{id} for the full object
    (lookup endpoint sometimes returns a trimmed profile with null bio)."""
    d = _get(f"https://{instance}/api/v1/accounts/{acc_id}", 8)
    return d if isinstance(d, dict) and d.get("id") else None


def strategy_lookup(instance, username):
    d = _get(f"https://{instance}/api/v1/accounts/lookup?acct={quote(username)}", 8)
    if not (isinstance(d, dict) and d.get("id")):
        return None
    # Always re-fetch full account by ID — lookup trims some fields including
    # the bio ("note") on federated accounts.
    full = _fetch_full_account(instance, d["id"])
    return full or d

def strategy_webfinger(instance, username):
    wf = _get(f"https://{instance}/.well-known/webfinger"
              f"?resource=acct:{quote(username)}@{instance}",
              timeout=8, accept="application/jrd+json")
    if not isinstance(wf, dict):
        return None
    actor_url = None
    for link in wf.get("links", []):
        if link.get("rel") == "self" and \
           (link.get("type") or "").startswith("application/activity+json"):
            actor_url = link.get("href")
            break
    if not actor_url:
        return None
    parsed = urlparse(actor_url)
    api_url = (f"{parsed.scheme}://{parsed.netloc}"
               f"/api/v1/accounts/lookup?acct={quote(username)}")
    d = _get(api_url, 8)
    if not (isinstance(d, dict) and d.get("id")):
        return None
    full = _fetch_full_account(parsed.netloc, d["id"])
    return full or d

def strategy_directory(instance, username):
    d = _get(f"https://{instance}/api/v1/directory"
             f"?q={quote(username)}&limit=40&local=true", 10)
    if not isinstance(d, list):
        return []
    matches = [a for a in d if isinstance(a, dict)
               and (a.get("username") or "").lower() == username.lower()]
    # Directory also sometimes strips bio — re-fetch full object
    full_matches = []
    for m in matches:
        if m.get("id"):
            full = _fetch_full_account(instance, m["id"])
            full_matches.append(full or m)
        else:
            full_matches.append(m)
    return full_matches

def probe_instance_for_user(instance, username):
    acc = strategy_lookup(instance, username)
    if acc: return acc
    acc = strategy_webfinger(instance, username)
    if acc: return acc
    hits = strategy_directory(instance, username)
    if hits: return hits[0]
    return None


# ══════════════════════════════════════════════════════
#  Extra OSINT
# ══════════════════════════════════════════════════════

def fetch_statuses(instance, user_id, limit=20):
    d = _get(f"https://{instance}/api/v1/accounts/{user_id}/statuses"
             f"?limit={limit}&exclude_replies=false", 10)
    return d if isinstance(d, list) else []

def fetch_pinned(instance, user_id):
    d = _get(f"https://{instance}/api/v1/accounts/{user_id}/statuses"
             f"?pinned=true", 10)
    return d if isinstance(d, list) else []


def analyze_statuses(statuses):
    if not statuses:
        return {}
    hours = Counter(); days = Counter(); langs = Counter()
    hashtags = Counter(); mentions = Counter()
    visibility = Counter()
    media = reply = boost = 0
    fav_total = rbg_total = rep_total = 0
    urls = set()
    dates = []

    for s in statuses:
        if not isinstance(s, dict): continue
        if s.get("created_at"):
            try:
                dt = datetime.fromisoformat(s["created_at"].replace("Z", "+00:00"))
                hours[dt.hour] += 1
                days[dt.weekday()] += 1
                dates.append(dt)
            except Exception:
                pass
        if s.get("language"): langs[s["language"]] += 1
        for t in (s.get("tags") or []):
            if t.get("name"): hashtags[t["name"].lower()] += 1
        for m in (s.get("mentions") or []):
            if m.get("acct"): mentions[m["acct"]] += 1
        visibility[s.get("visibility", "public")] += 1
        if s.get("media_attachments"): media += 1
        if s.get("in_reply_to_id"):    reply += 1
        if s.get("reblog"):            boost += 1
        fav_total += s.get("favourites_count") or 0
        rbg_total += s.get("reblogs_count")    or 0
        rep_total += s.get("replies_count")    or 0
        for u in re.findall(r'https?://[^\s"\'<>]+', s.get("content") or ""):
            urls.add(u.rstrip(".,);"))

    day_names = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

    top = None
    for s in statuses:
        if not isinstance(s, dict): continue
        score = (s.get("favourites_count") or 0) + (s.get("reblogs_count") or 0)
        if top is None or score > top[0]:
            top = (score, s)
    top_post = None
    if top:
        s = top[1]
        top_post = {
            "url":              s.get("url"),
            "created_at":       s.get("created_at"),
            "favourites_count": s.get("favourites_count"),
            "reblogs_count":    s.get("reblogs_count"),
            "replies_count":    s.get("replies_count"),
            "text":             _html_to_text(s.get("content") or "")[:250],
            "language":         s.get("language"),
        }

    freq = None
    if len(dates) >= 2:
        span = max((max(dates) - min(dates)).days, 1)
        freq = round(len(dates) / span, 3)

    return {
        "statuses_analyzed":       len(statuses),
        "hour_distribution":       dict(sorted(hours.items())),
        "day_distribution":        {day_names[k]: v for k, v in sorted(days.items())},
        "languages":               dict(langs.most_common()),
        "top_hashtags":            dict(hashtags.most_common(20)),
        "top_mentions":            dict(mentions.most_common(20)),
        "visibility_breakdown":    dict(visibility),
        "media_post_count":        media,
        "reply_post_count":        reply,
        "boost_post_count":        boost,
        "total_favourites":        fav_total,
        "total_boosts":            rbg_total,
        "total_replies_received":  rep_total,
        "urls_shared":             sorted(urls),
        "posts_per_day_avg":       freq,
        "top_post":                top_post,
    }


def download_avatar(url, username, instance):
    if not url: return {}
    out = {"url": url}
    data = _get_bytes(url)
    if not data:
        out["error"] = "download failed"
        return out
    safe = re.sub(r"[^A-Za-z0-9_\-]+", "_", f"{username}_{instance}")
    fname = f"masto_{safe}_avatar.jpg"
    try:
        with open(fname, "wb") as f:
            f.write(data)
        out["path"]        = fname
        out["size_bytes"]  = len(data)
        out["md5"]         = hashlib.md5(data).hexdigest()
        out["sha256"]      = hashlib.sha256(data).hexdigest()
    except Exception as e:
        out["error"] = f"save failed: {e}"
        return out

    # Optional EXIF
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS
        with Image.open(io.BytesIO(data)) as img:
            out["dimensions"] = list(img.size)
            out["format"]     = img.format
            exif_raw = img._getexif() if hasattr(img, "_getexif") else None
            if exif_raw:
                exif = {}
                for tag_id, value in exif_raw.items():
                    tag = TAGS.get(tag_id, tag_id)
                    if tag == "GPSInfo":
                        gps = {}
                        for gps_id, gps_val in value.items():
                            gps[str(GPSTAGS.get(gps_id, gps_id))] = str(gps_val)
                        exif["GPSInfo"] = gps
                    elif isinstance(value, (str, int, float)):
                        exif[str(tag)] = value
                if exif: out["exif"] = exif
                else:    out["exif_stripped"] = True
            else:
                out["exif_stripped"] = True
    except ImportError:
        pass
    except Exception:
        pass

    # Optional pHash
    try:
        import imagehash
        from PIL import Image
        with Image.open(io.BytesIO(data)) as img:
            out["phash"] = str(imagehash.phash(img))
            out["dhash"] = str(imagehash.dhash(img))
    except ImportError:
        pass
    except Exception:
        pass

    return out


# ══════════════════════════════════════════════════════
#  Normalisers
# ══════════════════════════════════════════════════════

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\s\-().]{7,18}\d")
BTC_RE   = re.compile(r"\b(?:bc1[a-z0-9]{25,90}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b")
ETH_RE   = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
TON_RE   = re.compile(r"\b(?:UQ|EQ)[A-Za-z0-9_\-]{46}\b")
XMR_RE   = re.compile(r"\b4[0-9AB][0-9a-zA-Z]{93}\b")
PGP_RE   = re.compile(r"[0-9A-F]{40}\b|[0-9A-F]{16}\b", re.I)

# Social handles / profiles detectable in bios
SOCIAL_PATTERNS = {
    "twitter":     re.compile(r"(?:https?://)?(?:www\.|mobile\.)?(?:twitter\.com|x\.com)/(@?[A-Za-z0-9_]{1,15})", re.I),
    "github":      re.compile(r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9][A-Za-z0-9\-]{0,38})", re.I),
    "gitlab":      re.compile(r"(?:https?://)?(?:www\.)?gitlab\.com/([A-Za-z0-9][A-Za-z0-9\-._]{0,38})", re.I),
    "instagram":   re.compile(r"(?:https?://)?(?:www\.)?instagram\.com/([A-Za-z0-9_.]{1,30})", re.I),
    "tiktok":      re.compile(r"(?:https?://)?(?:www\.)?tiktok\.com/@([A-Za-z0-9_.]{1,24})", re.I),
    "youtube":     re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/(@[A-Za-z0-9_\-.]{3,}|c/[A-Za-z0-9_\-]+|channel/UC[A-Za-z0-9_\-]{22})", re.I),
    "linkedin":    re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/([A-Za-z0-9\-]{3,100})", re.I),
    "telegram":    re.compile(r"(?:https?://)?t\.me/([A-Za-z0-9_]{4,32})", re.I),
    "reddit":      re.compile(r"(?:https?://)?(?:www\.)?reddit\.com/(?:u|user)/([A-Za-z0-9_\-]{3,20})", re.I),
    "keybase":     re.compile(r"(?:https?://)?keybase\.io/([A-Za-z0-9_]{2,25})", re.I),
    "bluesky":     re.compile(r"(?:https?://)?bsky\.app/profile/([A-Za-z0-9\-.]+)", re.I),
    "threads":     re.compile(r"(?:https?://)?(?:www\.)?threads\.net/@([A-Za-z0-9_.]{1,30})", re.I),
    "discord":     re.compile(r"(?:https?://)?(?:www\.)?discord\.(?:gg|com/invite)/([A-Za-z0-9]+)", re.I),
    "facebook":    re.compile(r"(?:https?://)?(?:www\.)?facebook\.com/([A-Za-z0-9.]{3,50})", re.I),
    "twitch":      re.compile(r"(?:https?://)?(?:www\.)?twitch\.tv/([A-Za-z0-9_]{3,25})", re.I),
    "medium":      re.compile(r"(?:https?://)?(?:www\.)?medium\.com/@([A-Za-z0-9_.-]{3,30})", re.I),
    "substack":    re.compile(r"(?:https?://)?([A-Za-z0-9\-]+)\.substack\.com", re.I),
    "patreon":     re.compile(r"(?:https?://)?(?:www\.)?patreon\.com/([A-Za-z0-9_\-]{3,30})", re.I),
    "ko-fi":       re.compile(r"(?:https?://)?ko-fi\.com/([A-Za-z0-9_\-]{3,30})", re.I),
    "pixelfed":    re.compile(r"(?:https?://)?pixelfed\.[a-z.]+/([A-Za-z0-9_]{1,30})", re.I),
    "peertube":    re.compile(r"(?:https?://)?[A-Za-z0-9\-.]+/a/([A-Za-z0-9_]{1,30})", re.I),
    "matrix":      re.compile(r"@([A-Za-z0-9._\-]{1,40}):([A-Za-z0-9.\-]+\.[A-Za-z]{2,})"),
    "xmpp_jid":    re.compile(r"(?:xmpp:)?([A-Za-z0-9._\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})"),
    "signal":      re.compile(r"signal\.me/#p/([+\d]+)", re.I),
    "session":     re.compile(r"\b05[a-f0-9]{64}\b", re.I),  # Session Messenger ID
    "mastodon":    re.compile(r"@([A-Za-z0-9_]+)@([A-Za-z0-9\-.]+\.[A-Za-z]{2,})"),
}


def _extract_social_handles(text, html):
    """Try to find social handles/profiles in bio + custom field values."""
    blob = (text or "") + " " + (html or "")
    hits = {}
    for platform, pat in SOCIAL_PATTERNS.items():
        found = []
        for m in pat.finditer(blob):
            if platform == "matrix":
                found.append(f"@{m.group(1)}:{m.group(2)}")
            elif platform == "mastodon":
                found.append(f"@{m.group(1)}@{m.group(2)}")
            elif platform in ("xmpp_jid",):
                found.append(m.group(1))
            else:
                found.append(m.group(1) if m.groups() else m.group(0))
        if found:
            # Deduplicate case-insensitively
            seen_lc = set()
            uniq = []
            for f in found:
                key = f.lower()
                if key in seen_lc: continue
                seen_lc.add(key)
                uniq.append(f)
            hits[platform] = uniq
    return hits


def _html_to_text(html):
    if not html: return ""
    t = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    t = re.sub(r"</p>\s*<p>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _extract_urls_from_html(html):
    """Mastodon wraps URLs in <a href='...'> with invisible span prefixes.
    Extract only the actual href values, not the reassembled span text.
    This avoids getting half-URLs like 'https://www.' on their own."""
    if not html:
        return []
    # Grab every href in anchor tags
    hrefs = re.findall(r'<a[^>]+href=["\']([^"\']+)["\']', html, flags=re.I)
    # Filter out mailto / javascript etc.
    return [h for h in hrefs if h.lower().startswith(("http://", "https://"))]


def _extract_hashtags_from_html(html, text):
    """Mastodon renders hashtags as <a class='mention hashtag' href='.../tags/X'>#X</a>.
    The plain regex on text misses them because #-chars get lost in HTML entities
    and the span splitting. Pull them from the anchor URLs + from plain text."""
    tags = set()
    if html:
        # Extract from tag URLs (canonical form)
        for m in re.finditer(r'/tags/([A-Za-z0-9_]+)', html):
            tags.add(m.group(1).lower())
        # Also inner text of hashtag spans
        for m in re.finditer(
            r'class="[^"]*hashtag[^"]*"[^>]*>#?<span>([A-Za-z0-9_]+)</span>',
            html, flags=re.I
        ):
            tags.add(m.group(1).lower())
    if text:
        for m in re.finditer(r"#(\w+)", text):
            tags.add(m.group(1).lower())
    return sorted(tags)


def _extract_labeled_handles(text):
    """Users often write 'Twitter: @foo', 'IG: @bar' in bios. Catch those.
    Also tolerate whitespace after @ (Mastodon HTML→text often leaves 'Twitter: @ foo')."""
    out = {}
    patterns = {
        "twitter":   r"(?:twitter|tw|x)\s*[:：]\s*@?\s*([A-Za-z0-9_]{1,15})\b",
        "instagram": r"(?:instagram|insta|ig)\s*[:：]\s*@?\s*([A-Za-z0-9_.]{1,30})\b",
        "tiktok":    r"(?:tiktok|tt)\s*[:：]\s*@?\s*([A-Za-z0-9_.]{1,24})\b",
        "github":    r"(?:github|gh)\s*[:：]\s*@?\s*([A-Za-z0-9][A-Za-z0-9\-]{0,38})\b",
        "telegram":  r"(?:telegram|tg)\s*[:：]\s*@?\s*([A-Za-z0-9_]{4,32})\b",
        "signal":    r"signal\s*[:：]\s*(\+\d[\d\s\-]{7,16})",
    }
    for plat, pat in patterns.items():
        found = [m.group(1) for m in re.finditer(pat, text, re.I)]
        if found:
            out[plat] = list(dict.fromkeys(found))
    return out


def normalize_account(acc, origin_instance=None):
    if not isinstance(acc, dict):
        acc = {}
    url = acc.get("url")
    acct = acc.get("acct") or ""
    instance = origin_instance
    if "@" in acct:
        instance = acct.split("@", 1)[1]
    elif url:
        try:
            instance = urlparse(url).netloc or instance
        except Exception:
            pass
    bio_html = acc.get("note") or ""
    bio_text = _html_to_text(bio_html)

    # Custom profile fields (Mastodon: name + value pairs, max 4)
    fields = [{
        "name":        f.get("name"),
        "value":       _html_to_text(f.get("value") or ""),
        "value_html":  f.get("value"),
        "verified_at": f.get("verified_at"),
    } for f in (acc.get("fields") or [])]

    # Combine bio + all field values for regex sweeps
    fields_text_blob = " ".join(f.get("value") or "" for f in fields)
    fields_html_blob = " ".join(f.get("value_html") or "" for f in fields)
    sweep_text = bio_text + " " + fields_text_blob
    sweep_html = bio_html + " " + fields_html_blob

    # Contact extraction (bio + fields combined)
    emails   = list(dict.fromkeys(EMAIL_RE.findall(sweep_text)))
    phones   = list(dict.fromkeys(
        re.sub(r"[\s\-().]", "", m)
        for m in PHONE_RE.findall(sweep_text)
        if len(re.sub(r"[\s\-().]", "", m)) >= 8
        and len(re.sub(r"[\s\-().]", "", m)) <= 16
    ))
    btc_addrs = list(dict.fromkeys(BTC_RE.findall(sweep_text)))
    eth_addrs = list(dict.fromkeys(ETH_RE.findall(sweep_text)))
    ton_addrs = list(dict.fromkeys(TON_RE.findall(sweep_text)))
    xmr_addrs = list(dict.fromkeys(XMR_RE.findall(sweep_text)))

    # URLs: from anchor hrefs only (avoids fragmented span garbage)
    sites = list(dict.fromkeys(_extract_urls_from_html(sweep_html)))

    # Hashtags — from tag URLs + hashtag spans + plain text
    hashtags_from_api = [t.get("name") for t in (acc.get("tags") or []) if t.get("name")]
    hashtags_from_html = _extract_hashtags_from_html(sweep_html, sweep_text)
    hashtags = list(dict.fromkeys(hashtags_from_api + hashtags_from_html))

    # Social handles: URL regex + labeled "Twitter: @foo" form
    socials = _extract_social_handles(sweep_text, sweep_html)
    labeled = _extract_labeled_handles(sweep_text)
    for plat, hs in labeled.items():
        merged = list(dict.fromkeys((socials.get(plat) or []) + hs))
        socials[plat] = merged

    full_handle = None
    if acc.get("username") and instance:
        full_handle = f"@{acc['username']}@{instance}"

    return {
        "user_id":            acc.get("id"),
        "username":           acc.get("username"),
        "acct":               acct or None,
        "account":            full_handle,
        "display_name":       acc.get("display_name"),
        "profile_url":        url,
        "instance":           instance,
        "profile_locked":     acc.get("locked"),
        "discoverable":       acc.get("discoverable"),
        "bot":                acc.get("bot"),
        "group":              acc.get("group"),
        "noindex":            acc.get("noindex"),
        "suspended":          acc.get("suspended"),
        "limited":            acc.get("limited"),
        "profile_created_at": acc.get("created_at"),
        "last_status_at":     acc.get("last_status_at"),
        "followers_count":    acc.get("followers_count"),
        "following_count":    acc.get("following_count"),
        "statuses_count":     acc.get("statuses_count"),
        "bio":                bio_text or None,
        "bio_html":           bio_html or None,
        "avatar_link":        acc.get("avatar") or acc.get("avatar_static"),
        "header_link":        acc.get("header") or acc.get("header_static"),
        "custom_fields":      fields,
        "emails":             emails,
        "phone_numbers":      phones,
        "crypto_addresses":   {
            "btc": btc_addrs,
            "eth": eth_addrs,
            "ton": ton_addrs,
            "xmr": xmr_addrs,
        },
        "urls":               sites,
        "hashtags":           hashtags,
        "social_handles":     socials,
        # Back-compat keys:
        "emails_in_bio":      emails,
        "urls_in_bio":        sites,
        "hashtags_in_bio":    hashtags,
    }


def normalize_instance(v2, v1, instance):
    v2 = v2 if isinstance(v2, dict) else {}
    v1 = v1 if isinstance(v1, dict) else {}
    contact = v2.get("contact") or {}
    admin_v2 = contact.get("account") or {}
    email = contact.get("email") or v1.get("email")
    thumb_v2 = (v2.get("thumbnail") or {}).get("url")
    thumb = thumb_v2 or v1.get("thumbnail")
    reg = v2.get("registrations") or {}
    reg_enabled  = reg.get("enabled", v1.get("registrations"))
    reg_approval = reg.get("approval_required", v1.get("approval_required"))
    stats = v1.get("stats") or {}
    return {
        "instance":                         instance,
        "name":                             v2.get("domain") or instance,
        "title":                            v2.get("title") or v1.get("title"),
        "short_description":                v1.get("short_description") or v2.get("description"),
        "detailed_description":             v1.get("description"),
        "email":                            email,
        "languages":                        v2.get("languages") or v1.get("languages") or [],
        "registrations_open":               bool(reg_enabled) if reg_enabled is not None else None,
        "registration_approval_required":   bool(reg_approval) if reg_approval is not None else None,
        "thumbnail_link":                   thumb,
        "version":                          v2.get("version") or v1.get("version"),
        "user_count":                       stats.get("user_count"),
        "status_count":                     stats.get("status_count"),
        "domain_count":                     stats.get("domain_count"),
        "streaming_url":                    (v1.get("urls") or {}).get("streaming_api"),
        "admin": normalize_account(admin_v2, origin_instance=instance) if admin_v2 else None,
    }


# ══════════════════════════════════════════════════════
#  Enrich
# ══════════════════════════════════════════════════════

def enrich_account(acc_raw, instance, fetch_posts=True, fetch_avatar=True):
    acc = normalize_account(acc_raw, origin_instance=instance)
    if fetch_posts and acc.get("user_id"):
        statuses = fetch_statuses(instance, acc["user_id"], limit=20)
        pinned   = fetch_pinned(instance, acc["user_id"])
        acc["status_analysis"] = analyze_statuses(statuses)
        acc["pinned_statuses"] = [{
            "url":        p.get("url"),
            "created_at": p.get("created_at"),
            "text":       _html_to_text(p.get("content") or "")[:200],
            "favourites": p.get("favourites_count"),
            "reblogs":    p.get("reblogs_count"),
        } for p in pinned if isinstance(p, dict)][:5]
    if fetch_avatar and acc.get("avatar_link"):
        acc["avatar_analysis"] = download_avatar(
            acc["avatar_link"],
            acc.get("username") or "user",
            instance
        )
    return acc


# ══════════════════════════════════════════════════════
#  Scans
# ══════════════════════════════════════════════════════

def scan_username(username, max_instances=500, workers=30):
    instances = get_instance_list(max_instances)
    LOG.info(f"Probing {len(instances)} instances for @{username} "
             f"({workers} workers, 3 strategies each)...")
    found = []
    seen = set()
    def probe(inst):
        return inst, probe_instance_for_user(inst, username)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(probe, i) for i in instances]
        done = 0
        for fut in as_completed(futs):
            done += 1
            if HAS_RICH and done % 50 == 0:
                C.print(f"  [dim]  ...{done}/{len(instances)} checked, "
                        f"{len(found)} hits so far[/dim]")
            try:
                inst, acc = fut.result()
            except Exception:
                continue
            if acc and acc.get("id"):
                key = (inst, acc["id"])
                if key in seen: continue
                seen.add(key)
                # If the probe returned a trimmed profile (no bio / no fields),
                # re-fetch the full /accounts/{id} to guarantee complete data
                if not acc.get("note") or not acc.get("fields"):
                    full = _fetch_full_account(inst, acc["id"])
                    if full:
                        acc = full
                found.append(normalize_account(acc, origin_instance=inst))
    LOG.good(f"Hits: {len(found)} instance(s) have @{username}")
    return found


def fetch_instance_info(instance):
    v2 = _get(f"https://{instance}/api/v2/instance", 12)
    v1 = _get(f"https://{instance}/api/v1/instance", 12)
    return normalize_instance(v2, v1, instance)


# ══════════════════════════════════════════════════════
#  Analyze
# ══════════════════════════════════════════════════════

def analyze(raw, force_kind=None, max_instances=500, enrich_hits=False):
    kind, parsed = detect_input_type(raw)
    if force_kind == "user":
        if "username" not in parsed:
            parsed["username"] = raw.lstrip("@").strip()
        kind = "qualified" if parsed.get("instance") else "username"
    elif force_kind == "instance":
        host = re.sub(r"^https?://", "", raw, flags=re.I).split("/", 1)[0]
        parsed = {"instance": host.lower()}
        kind = "instance"
    result = {
        "input":            raw,
        "kind":             kind,
        "scanned_at":       datetime.now(timezone.utc).isoformat(),
        "targeted_account": None,
        "instance_info":    None,
        "username_scan":    [],
    }
    if kind == "invalid":
        LOG.bad(f"Unrecognized input: {raw!r}")
        return result

    if kind == "qualified":
        username = parsed["username"]
        instance = parsed["instance"]
        LOG.info(f"Qualified → @{username}@{instance}")
        raw_acc = probe_instance_for_user(instance, username)
        if raw_acc:
            result["targeted_account"] = enrich_account(raw_acc, instance)
            LOG.good(f"Targeted: {result['targeted_account']['account']}")
        else:
            LOG.warn(f"Not found at @{username}@{instance}")
        LOG.info("Now searching through the Masto OSINT tool instances database")
        result["username_scan"] = scan_username(username, max_instances=max_instances)

    elif kind == "username":
        LOG.info("Now searching through the Masto OSINT tool instances database")
        hits = scan_username(parsed["username"], max_instances=max_instances)
        if enrich_hits:
            LOG.info(f"Enriching {len(hits)} hits (posts + avatars)...")
            enriched = []
            for h in hits:
                inst = h.get("instance")
                if inst and h.get("username"):
                    raw_acc = strategy_lookup(inst, h["username"])
                    enriched.append(enrich_account(raw_acc, inst)
                                    if raw_acc else h)
                else:
                    enriched.append(h)
            hits = enriched
        else:
            if hits:
                inst = hits[0].get("instance")
                if inst and hits[0].get("username"):
                    raw_acc = strategy_lookup(inst, hits[0]["username"])
                    if raw_acc:
                        hits[0] = enrich_account(raw_acc, inst)
        result["username_scan"] = hits

    elif kind == "instance":
        LOG.info(f"Instance → {parsed['instance']}")
        inst_info = fetch_instance_info(parsed["instance"])
        if inst_info.get("admin") and inst_info["admin"].get("user_id"):
            admin_raw = strategy_lookup(parsed["instance"],
                                         inst_info["admin"]["username"])
            if admin_raw:
                inst_info["admin"] = enrich_account(admin_raw, parsed["instance"])
        result["instance_info"] = inst_info
        if inst_info.get("title"):
            LOG.good(f"Instance: {inst_info['title']}")

    return result


# ══════════════════════════════════════════════════════
#  Output
# ══════════════════════════════════════════════════════

def _val(v):
    if v is None: return "—"
    if v is True: return "Yes"
    if v is False: return "No"
    if isinstance(v, list) and not v: return "—"
    return str(v)


def print_account_section(acc, index=None):
    if not HAS_RICH:
        print("\n" + "═" * 10)
        if index is not None:
            print(f"Account: {index}")
        print("═" * 10)
        print(f"  user ID                  : {_val(acc.get('user_id'))}")
        print(f"  profile url              : {_val(acc.get('profile_url'))}")
        print(f"  account locked           : {_val(acc.get('profile_locked'))}")
        print(f"  username                 : {_val(acc.get('username'))}")
        print(f"  account                  : {_val(acc.get('account') or acc.get('acct'))}")
        print(f"  display name             : {_val(acc.get('display_name'))}")
        print(f"  instance                 : {_val(acc.get('instance'))}")
        print(f"  profile creation date    : {_val(acc.get('profile_created_at'))}")
        print(f"  user is a bot            : {_val(acc.get('bot'))}")
        print(f"  user on profile directory: {_val(acc.get('discoverable'))}")
        print(f"  followers                : {_val(acc.get('followers_count'))}")
        print(f"  following                : {_val(acc.get('following_count'))}")
        print(f"  number of posts          : {_val(acc.get('statuses_count'))}")
        print(f"  user last message date   : {_val((acc.get('last_status_at') or '')[:10] or None)}")
        print(f"  user is a group          : {_val(acc.get('group'))}")
        if acc.get("bio"):
            print(f"  user bio                 : {acc['bio'][:500]}")
        print(f"  user's avatar link       : {_val(acc.get('avatar_link'))}")
        if acc.get("header_link"):
            print(f"  user's header link       : {_val(acc.get('header_link'))}")
        return

    title = f"Account: {index}" if index is not None else "Account"
    C.print(Rule(f"[bold red]{title}[/bold red]", style="red"))
    C.print()

    # Core list (matching your required output format)
    t = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
              border_style="dim", padding=(0, 2), min_width=70)
    t.add_column("Field", style="dim", width=34)
    t.add_column("Value", style="bold white", overflow="fold")
    rows = [
        ("user ID",                       _val(acc.get("user_id"))),
        ("profile url",                   _val(acc.get("profile_url"))),
        ("account locked",                _val(acc.get("profile_locked"))),
        ("username",                      _val(acc.get("username"))),
        ("account",                       _val(acc.get("account") or acc.get("acct"))),
        ("display name",                  _val(acc.get("display_name"))),
        ("instance",                      _val(acc.get("instance"))),
        ("profile creation date",         _val(acc.get("profile_created_at"))),
        ("user is a bot",                 _val(acc.get("bot"))),
        ("user on profile directory",     _val(acc.get("discoverable"))),
        ("noindex (search opt-out)",      _val(acc.get("noindex"))),
        ("suspended",                     _val(acc.get("suspended"))),
        ("limited",                       _val(acc.get("limited"))),
        ("followers",                     _val(acc.get("followers_count"))),
        ("following",                     _val(acc.get("following_count"))),
        ("number of posts",               _val(acc.get("statuses_count"))),
        ("user last message date",        _val((acc.get("last_status_at") or "")[:10] or None)),
        ("user is a group",               _val(acc.get("group"))),
    ]
    for k, v in rows:
        t.add_row(k, v)
    C.print(Panel(t, title="[bold]Account Data[/bold]", border_style="magenta"))

    # Bio
    if acc.get("bio"):
        C.print(Panel(acc["bio"], title="[bold]User Bio[/bold]",
                      border_style="cyan"))

    # Media links
    media_lines = []
    if acc.get("avatar_link"):
        media_lines.append(f"  [dim]Avatar link :[/dim] [cyan]{acc['avatar_link']}[/cyan]")
    if acc.get("header_link"):
        media_lines.append(f"  [dim]Header link :[/dim] [cyan]{acc['header_link']}[/cyan]")
    if media_lines:
        C.print(Panel(Text.from_markup("\n".join(media_lines)),
                      title="[bold]Media Links[/bold]", border_style="blue"))

    # Avatar analysis
    av = acc.get("avatar_analysis") or {}
    if av and not av.get("error") and av.get("path"):
        lines = []
        lines.append(f"  [dim]Downloaded   :[/dim] [cyan]{av['path']}[/cyan]")
        if av.get("dimensions"):
            lines.append(f"  [dim]Dimensions   :[/dim] "
                         f"{av['dimensions'][0]}x{av['dimensions'][1]}")
        if av.get("size_bytes"):
            lines.append(f"  [dim]Size         :[/dim] {av['size_bytes']} bytes")
        if av.get("md5"):
            lines.append(f"  [dim]MD5          :[/dim] {av['md5']}")
        if av.get("sha256"):
            lines.append(f"  [dim]SHA256       :[/dim] {av['sha256']}")
        if av.get("phash"):
            lines.append(f"  [dim]pHash        :[/dim] {av['phash']}")
        if av.get("exif"):
            lines.append(f"  [yellow]EXIF present ({len(av['exif'])} fields)[/yellow]")
            if av["exif"].get("GPSInfo"):
                lines.append(f"  [bright_red]!! GPS data in avatar: "
                             f"{av['exif']['GPSInfo']}[/bright_red]")
        elif av.get("exif_stripped"):
            lines.append(f"  [dim]EXIF         :[/dim] stripped")
        C.print(Panel(Text.from_markup("\n".join(lines)),
                      title="[bold]Avatar Analysis[/bold]",
                      border_style="bright_magenta"))

    # Custom fields
    if acc.get("custom_fields"):
        ft = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                   border_style="dim", padding=(0, 1))
        ft.add_column("Name",     style="cyan",   min_width=16)
        ft.add_column("Value",                    min_width=28, overflow="fold")
        ft.add_column("Verified", style="dim",    width=22)
        for f in acc["custom_fields"]:
            ft.add_row(f.get("name") or "—",
                       f.get("value") or "—",
                       f.get("verified_at") or "—")
        C.print(Panel(ft, title="[bold]Custom Profile Fields[/bold]",
                      border_style="blue"))

    # Bio extraction — all contact & social handles
    extracted = []
    if acc.get("emails"):
        extracted.append(f"  [dim]Emails      :[/dim] "
                         f"[cyan]{', '.join(acc['emails'])}[/cyan]")
    if acc.get("phone_numbers"):
        extracted.append(f"  [dim]Phones      :[/dim] "
                         f"[cyan]{', '.join(acc['phone_numbers'])}[/cyan]")
    crypto = acc.get("crypto_addresses") or {}
    for coin, addrs in crypto.items():
        if addrs:
            extracted.append(f"  [dim]{coin.upper()} addrs   :[/dim] "
                             + ", ".join(f"[yellow]{a}[/yellow]" for a in addrs))
    if acc.get("urls"):
        extracted.append("  [dim]URLs        :[/dim] "
                         + "\n                  ".join(
                             f"[cyan]{u}[/cyan]" for u in acc["urls"][:12]))
    if acc.get("hashtags"):
        extracted.append("  [dim]Hashtags    :[/dim] "
                         + " ".join(f"[magenta]#{h}[/magenta]"
                                     for h in acc["hashtags"][:20]))
    if extracted:
        C.print(Panel(Text.from_markup("\n".join(extracted)),
                      title="[bold]Bio Extraction — Contacts[/bold]",
                      border_style="bright_cyan"))

    # Social handles found in bio + fields
    socials = acc.get("social_handles") or {}
    if socials:
        st = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                   border_style="dim", padding=(0, 1))
        st.add_column("Platform", style="bold cyan", width=14)
        st.add_column("Handle(s)", style="white",    overflow="fold")
        for plat, handles in socials.items():
            st.add_row(plat, ", ".join(handles))
        C.print(Panel(st,
                      title="[bold]Social Handles (cross-platform pivots)[/bold]",
                      border_style="bright_yellow"))

    # Pinned posts
    if acc.get("pinned_statuses"):
        pt = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                   border_style="dim", padding=(0, 1))
        pt.add_column("Date",  style="dim",  width=11, no_wrap=True)
        pt.add_column("Favs",  justify="right", width=6)
        pt.add_column("Boost", justify="right", width=6)
        pt.add_column("Text",  min_width=40, overflow="fold")
        for p in acc["pinned_statuses"]:
            pt.add_row(
                (p.get("created_at") or "")[:10],
                str(p.get("favourites") or 0),
                str(p.get("reblogs") or 0),
                (p.get("text") or "")[:200],
            )
        C.print(Panel(pt, title="[bold]Pinned Posts[/bold]",
                      border_style="yellow"))

    # Activity analysis
    sa = acc.get("status_analysis") or {}
    if sa:
        t2 = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                   border_style="dim", padding=(0, 2))
        t2.add_column("Metric", style="dim", width=26)
        t2.add_column("Value",  style="bold white")
        for k, v in [
            ("Posts analyzed",         sa.get("statuses_analyzed")),
            ("Posts per day (avg)",    sa.get("posts_per_day_avg")),
            ("Media posts",            sa.get("media_post_count")),
            ("Reply posts",            sa.get("reply_post_count")),
            ("Boost posts",            sa.get("boost_post_count")),
            ("Total favourites",       sa.get("total_favourites")),
            ("Total boosts received",  sa.get("total_boosts")),
            ("Total replies received", sa.get("total_replies_received")),
        ]:
            t2.add_row(k, _val(v))
        C.print(Panel(t2, title="[bold]Recent Activity Summary[/bold]",
                      border_style="green"))

        chart_lines = []
        hd = sa.get("hour_distribution") or {}
        dd = sa.get("day_distribution") or {}
        if hd:
            mx = max(hd.values(), default=1)
            chart_lines.append("[dim]── Posting Hours (UTC) ──[/dim]")
            for h, v in sorted(hd.items(), key=lambda x: int(x[0])):
                bar = "█" * max(1, int(v / mx * 20))
                chart_lines.append(f"  {int(h):02d}:00 [cyan]{bar:<20}[/cyan] {v}")
        if dd:
            mx = max(dd.values(), default=1)
            if chart_lines: chart_lines.append("")
            chart_lines.append("[dim]── Posting Days ──[/dim]")
            for d, v in dd.items():
                bar = "█" * max(1, int(v / mx * 20))
                chart_lines.append(f"  {d:<4} [green]{bar:<20}[/green] {v}")
        if chart_lines:
            C.print(Panel(Text.from_markup("\n".join(chart_lines)),
                          title="[bold]Activity Pattern[/bold]",
                          border_style="cyan"))

        th = sa.get("top_hashtags") or {}
        if th:
            hashtag_str = "  " + "  ".join(
                f"[magenta]#{k}[/magenta][dim] ×{v}[/dim]"
                for k, v in list(th.items())[:25])
            C.print(Panel(Text.from_markup(hashtag_str),
                          title="[bold]Top Hashtags in Posts[/bold]",
                          border_style="magenta"))

        tm = sa.get("top_mentions") or {}
        if tm:
            mention_str = "  " + "  ".join(
                f"[cyan]@{k}[/cyan][dim] ×{v}[/dim]"
                for k, v in list(tm.items())[:20])
            C.print(Panel(Text.from_markup(mention_str),
                          title="[bold]Top Mentions (Network)[/bold]",
                          border_style="bright_cyan"))

        lg = sa.get("languages") or {}
        if lg:
            C.print(Panel(
                Text.from_markup("  " + "   ".join(
                    f"[cyan]{k}[/cyan]: {v}" for k, v in lg.items())),
                title="[bold]Post Languages[/bold]", border_style="blue"))

        us = sa.get("urls_shared") or []
        if us:
            url_str = "\n".join(f"  [cyan]{u}[/cyan]" for u in us[:20])
            C.print(Panel(Text.from_markup(url_str),
                          title=f"[bold]URLs Shared in Posts — {len(us)}[/bold]",
                          border_style="blue"))

        tp = sa.get("top_post") or {}
        if tp and tp.get("url"):
            lines = [
                f"  [dim]URL        :[/dim] [cyan]{tp.get('url')}[/cyan]",
                f"  [dim]Date       :[/dim] {(tp.get('created_at') or '')[:19]}",
                f"  [dim]Favourites :[/dim] {tp.get('favourites_count')}",
                f"  [dim]Boosts     :[/dim] {tp.get('reblogs_count')}",
                f"  [dim]Replies    :[/dim] {tp.get('replies_count')}",
                f"  [dim]Language   :[/dim] {tp.get('language') or '—'}",
                "",
                f"  {tp.get('text') or ''}",
            ]
            C.print(Panel(Text.from_markup("\n".join(lines)),
                          title="[bold]Top Post (most engagement)[/bold]",
                          border_style="bright_red"))


def print_instance_section(inst):
    if not HAS_RICH:
        print("\n" + "═"*20)
        print(f"Instance: {inst.get('instance')}")
        print("═"*20)
        for k in ["name","title","short_description","email","languages",
                  "registrations_open","registration_approval_required",
                  "thumbnail_link","version","user_count","status_count",
                  "domain_count"]:
            print(f"  {k:<32}: {_val(inst.get(k))}")
        if inst.get("admin"):
            print("\n--- Instance Admin ---")
            print_account_section(inst["admin"])
        return

    hdr = Text()
    hdr.append(f"  {inst.get('title') or inst.get('instance')}\n",
               style="bold white")
    hdr.append(f"  {inst.get('instance')}\n", style="bold cyan")
    if inst.get("short_description"):
        hdr.append(f"\n  {inst['short_description'][:300]}", style="italic dim")
    C.print(Panel(hdr, title="[bold]Mastodon Instance[/bold]",
                  border_style="cyan", padding=(0, 2)))

    t = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
              border_style="dim", padding=(0, 2), min_width=70)
    t.add_column("Field", style="dim", width=34)
    t.add_column("Value", style="bold white", overflow="fold")
    for k, v in [
        ("Name",                            inst.get("name")),
        ("Title",                           inst.get("title")),
        ("Short description",               inst.get("short_description")),
        ("Detailed description",
         (inst.get("detailed_description") or "")[:200] or None),
        ("Email",                           inst.get("email")),
        ("Languages",
         ", ".join(inst["languages"]) if inst.get("languages") else None),
        ("Registrations open",              inst.get("registrations_open")),
        ("Registration approval required",  inst.get("registration_approval_required")),
        ("Thumbnail link",                  inst.get("thumbnail_link")),
        ("Version",                         inst.get("version")),
        ("User count",                      inst.get("user_count")),
        ("Status count",                    inst.get("status_count")),
        ("Known peer domains",              inst.get("domain_count")),
        ("Streaming URL",                   inst.get("streaming_url")),
    ]:
        t.add_row(k, _val(v))
    C.print(Panel(t, title="[bold]Instance Data[/bold]", border_style="magenta"))

    if inst.get("admin"):
        C.print()
        C.print(Rule("[bold red]Instance Admin[/bold red]", style="red"))
        C.print()
        print_account_section(inst["admin"])


def print_scan_summary(hits, username):
    if not hits:
        LOG.warn(f"No hits for @{username}")
        return
    if HAS_RICH:
        for a in hits:
            if a.get("instance"):
                C.print(f"[green][+][/green] Target found ✓ on: "
                        f"[bold cyan]{a['instance']}[/bold cyan]")
                if a.get("profile_url"):
                    C.print(f"    [dim]Profile URL:[/dim] {a['profile_url']}")
        C.print()
        t = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                  border_style="dim", padding=(0, 1))
        t.add_column("#",         width=3)
        t.add_column("Instance",  style="cyan", min_width=24)
        t.add_column("URL",       style="dim", min_width=30, overflow="fold")
        t.add_column("Followers", justify="right", width=10)
        t.add_column("Posts",     justify="right", width=7)
        t.add_column("Created",   style="dim",     width=11, no_wrap=True)
        for i, a in enumerate(hits, 1):
            t.add_row(
                str(i),
                a.get("instance") or "—",
                a.get("profile_url") or "—",
                _val(a.get("followers_count")),
                _val(a.get("statuses_count")),
                (a.get("profile_created_at") or "")[:10] or "—",
            )
        C.print(Panel(t,
                      title=f"[bold]Instances Database Scan — @{username} "
                            f"({len(hits)} hit{'s' if len(hits)!=1 else ''})[/bold]",
                      border_style="green"))
    else:
        for a in hits:
            print(f"[+] Target found ✓ on: {a.get('instance')}")
            print(f"    Profile URL: {a.get('profile_url')}")


def render(result):
    if HAS_RICH:
        C.print()
        C.print(Rule(f"[bold cyan]{result['input']}[/bold cyan] "
                      f"[dim]({result['kind']})[/dim]", style="cyan"))
        C.print()

    if result.get("targeted_account"):
        print_account_section(result["targeted_account"], index=1)

    if result.get("username_scan"):
        username = detect_input_type(result["input"])[1].get("username") or result["input"]
        if not result.get("targeted_account"):
            # Show first hit deeply (it was enriched)
            for i, h in enumerate(result["username_scan"], 1):
                if h.get("status_analysis") or h.get("avatar_analysis"):
                    print_account_section(h, index=i)
                    break
        print_scan_summary(result["username_scan"], username)

    if result.get("instance_info"):
        print_instance_section(result["instance_info"])


def save_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    LOG.good(f"JSON saved: {path}")


def main():
    ap = argparse.ArgumentParser(
        description="Masto OSINT — Mastodon user + instance intel (auto-detect)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python masto.py gargron
  python masto.py mastodon.social
  python masto.py @gargron@mastodon.social
  python masto.py https://mastodon.social/@gargron
  python masto.py a b c
  python masto.py gargron --enrich-all
  python masto.py gargron -o out.json
        """,
    )
    ap.add_argument("targets", nargs="+",
                    help="Username, instance, @user@instance, or URL")
    ap.add_argument("--as-user",     action="store_true")
    ap.add_argument("--as-instance", action="store_true")
    ap.add_argument("--max",     type=int, default=500, metavar="N",
                    help="Max instances to scan (default: 500)")
    ap.add_argument("--enrich-all", action="store_true",
                    help="Fetch posts + avatar for EVERY hit (slow)")
    ap.add_argument("-o", "--output", default=None)
    args = ap.parse_args()

    if args.as_user and args.as_instance:
        sys.exit("[!] --as-user and --as-instance are mutually exclusive")
    force_kind = "user" if args.as_user else ("instance" if args.as_instance else None)

    if HAS_RICH:
        C.print()
        C.print(Rule("[bold red]Masto OSINT Tool[/bold red]", style="red"))
        C.print()

    all_results = []
    for raw in args.targets:
        res = analyze(raw, force_kind=force_kind,
                      max_instances=args.max,
                      enrich_hits=args.enrich_all)
        render(res)
        all_results.append(res)

    if args.output:
        out = args.output if args.output.endswith(".json") else args.output + ".json"
        save_json(out, all_results if len(all_results) > 1 else all_results[0])
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = "_".join(
            re.sub(r"[^A-Za-z0-9_]+", "_", t)[:30] for t in args.targets
        )[:60]
        save_json(f"masto_{slug}_{ts}.json",
                  all_results if len(all_results) > 1 else all_results[0])


if __name__ == "__main__":
    main()
