#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# osgint.py — GitHub OSINT Tool

import json, requests, binascii, re, sys, base64, argparse, time

try:
    from colorama import Fore, Style, init
    init(autoreset=True)
    GREEN, YELLOW, RED, CYAN = Fore.GREEN, Fore.YELLOW, Fore.RED, Fore.CYAN
    RESET, BOLD = Style.RESET_ALL, Style.BRIGHT
except ImportError:
    GREEN = YELLOW = RED = CYAN = RESET = BOLD = ""

# ─────────────────────────────────────────────────────────────
# GLOBALS
# ─────────────────────────────────────────────────────────────
from datetime import datetime, timezone

# Default schema — every scan always returns these keys so the consuming
# platform sees a consistent shape (null / [] / {} for empty fields).
def _default_schema():
    return {
        # Scan metadata
        "scanned_at":             None,
        # Core profile (GitHub user object)
        "login":                  None,
        "id":                     None,
        "avatar_url":             None,
        "name":                   None,
        "blog":                   None,
        "location":               None,
        "twitter_username":       None,
        "email":                  None,
        "company":                None,
        "bio":                    None,
        "public_repos":           None,
        "followers":              None,
        "following":              None,
        "created_at":             None,
        "updated_at":             None,
        "profile_readme":         None,
        # Collections — always present, may be empty
        "emails_all":             [],
        "social_accounts":        [],
        "social_media":           {},
        "organizations":          [],
        "secrets_found":          [],
        "sensitive_files":        [],
        "public_events_emails":   [],
        "commit_search_emails":   [],
        "gist_count":             0,
        "GPG_ids":                [],
        "GPG_keys":               None,
        "starred_top_languages":  {},
        "starred_top_topics":     {},
    }

jsonOutput = _default_schema()
email_out  = []
session    = requests.Session()

UA = 'Mozilla/5.0 (X11; Linux x86_64) osgint/2.0'
session.headers.update({'User-Agent': UA})
GH_HEADERS = {'Accept': 'application/vnd.github.v3+json', 'User-Agent': UA}

# ─────────────────────────────────────────────────────────────
# PATTERNS
# ─────────────────────────────────────────────────────────────
SECRET_PATTERNS = {
    "AWS Access Key"      : r'AKIA[0-9A-Z]{16}',
    "AWS Secret Key"      : r'(?i)aws[_\-\s]?secret[_\-\s]?access[_\-\s]?key[\s]*[=:]\s*["\']?([A-Za-z0-9/+=]{40})',
    "Private Key Header"  : r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----',
    "Bearer Token"        : r'(?i)bearer\s+[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.?[A-Za-z0-9\-_.+/=]*',
    "Generic API Key"     : r'(?i)(api_key|apikey|api-key)\s*[=:]\s*["\']?([A-Za-z0-9\-_]{20,})',
    "DB Connection String": r'(?i)(mysql|postgres|mongodb|redis|amqp)://[^\s\'"<>]+',
    "GitHub Token"        : r'gh[pousr]_[A-Za-z0-9]{36,}',
    "Slack Token"         : r'xox[baprs]-[0-9A-Za-z\-]{10,}',
    "Stripe Key"          : r'sk_live_[0-9a-zA-Z]{24}',
    "Google API Key"      : r'AIza[0-9A-Za-z\-_]{35}',
    "JWT Token"           : r'eyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_.+/=]+',
}

SOCIAL_PATTERNS = {
    "Twitter/X" : r'(?:(?:twitter\.com|x\.com)/([A-Za-z0-9_]{1,15})\b|(?<![a-zA-Z0-9_.])@([A-Za-z0-9_]{1,15})\b)',
    "LinkedIn"  : r'(?:linkedin\.com/in/|(?<![a-zA-Z0-9])in/)([A-Za-z0-9\-]{3,})',
    "Instagram" : r'(?:instagram\.com/|(?:instagram|ig)\s*[:/]\s*@?)([A-Za-z0-9_.]{3,30})',
    "Discord"   : r'(?:discord(?:app)?\.(?:com|gg)/(?:invite/)?|discord\s*[:/]\s*)([A-Za-z0-9\-]{2,})',
    "Telegram"  : r'(?:t\.me/|telegram\.me/|telegram\s*[:/]\s*@?)([A-Za-z0-9_]{5,})',
    "YouTube"   : r'youtube\.com/(?:channel/|c/|user/|@)([A-Za-z0-9_\-]+)',
    "Reddit"    : r'reddit\.com/u(?:ser)?/([A-Za-z0-9_\-]+)',
    "Medium"    : r'medium\.com/@([A-Za-z0-9_\-]+)',
    # Mastodon: match both URL form (instance.com/@user) AND webfinger form (@user@instance.com)
    "Mastodon"  : r'(?:(?:https?://)?([A-Za-z0-9][A-Za-z0-9\-]*(?:\.[A-Za-z0-9\-]+)+)/@([A-Za-z0-9_]+)|@([A-Za-z0-9_]+)@([A-Za-z0-9.\-]+\.[a-z]{2,}))',
    "Keybase"   : r'keybase\.io/([A-Za-z0-9_]+)',
    "TikTok"    : r'(?:tiktok\.com/@|tiktok\s*[:/]\s*@?)([A-Za-z0-9_.]{2,24})',
    "Facebook"  : r'(?:facebook\.com|fb\.com)/([A-Za-z0-9.]{3,})',
    "Twitch"    : r'twitch\.tv/([A-Za-z0-9_]{3,25})',
    "GitLab"    : r'gitlab\.com/([A-Za-z0-9][A-Za-z0-9._\-]{1,38})',
    "Bluesky"   : r'bsky\.app/profile/([A-Za-z0-9.\-]+)',
    "Threads"   : r'threads\.net/@([A-Za-z0-9_.]{1,30})',
    "Patreon"   : r'patreon\.com/([A-Za-z0-9_\-]{3,30})',
    "Ko-Fi"     : r'ko-fi\.com/([A-Za-z0-9_\-]{3,30})',
    "BuyMeACoffee": r'(?:buymeacoffee|buymeacoff)\.com/([A-Za-z0-9_\-]{3,30})',
    "Matrix"    : r'(?<![a-zA-Z0-9])@([A-Za-z0-9._\-]{1,40}):([A-Za-z0-9.\-]+\.[A-Za-z]{2,})',
    "XMPP"      : r'(?:xmpp:|jabber:)([A-Za-z0-9._\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})',
    "Signal"    : r'signal\.me/#p/(\+\d[\d]{7,16})',
    "Session"   : r'(?<![a-fA-F0-9])(05[a-fA-F0-9]{64})(?![a-fA-F0-9])',
    "Hack The Box": r'(?:hackthebox\.com/profile/|app\.hackthebox\.com/profile/)(\d+|[A-Za-z0-9_\-]+)',
    "TryHackMe" : r'tryhackme\.com/p/([A-Za-z0-9_\-]+)',
    "StackOverflow": r'stackoverflow\.com/users/(\d+)',
    "DevTo"     : r'dev\.to/([A-Za-z0-9_\-]{2,})',
    "HashNode"  : r'hashnode\.(?:com|dev)/@([A-Za-z0-9_\-]{2,})',
    "Pixelfed"  : r'pixelfed\.[a-z.]+/([A-Za-z0-9_]{2,30})',
    "PeerTube"  : r'peertube\.[A-Za-z0-9.\-]+/a/([A-Za-z0-9_]{2,30})',
}

SENSITIVE_FILENAMES = [
    '.env', '.env.local', '.env.prod', '.env.production',
    'secrets.yml', 'secrets.yaml', 'secrets.json',
    'config.json', 'credentials', 'credentials.json',
    'id_rsa', 'id_dsa', 'id_ecdsa', 'id_ed25519',
    '.htpasswd', 'wp-config.php', 'database.yml',
]

SKIP_LOCATIONS = {'your ip address', 'none', ''}
EMAIL_RE = re.compile(r'[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-.]+')
MAX_SCAN_BYTES = 512 * 1024

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def _get(url, gh=True, **kwargs):
    headers = GH_HEADERS if gh else {'User-Agent': UA}
    while True:
        try:
            resp = session.get(url, headers=headers, timeout=12, **kwargs)
        except requests.RequestException:
            return None
        if gh:
            remaining = int(resp.headers.get('X-RateLimit-Remaining', 1))
            if resp.status_code == 403 and remaining == 0:
                reset_ts = int(resp.headers.get('X-RateLimit-Reset', time.time() + 60))
                wait = max(reset_ts - int(time.time()), 1) + 2
                print(f"{YELLOW}[!] Rate limit — waiting {wait}s...{RESET}")
                time.sleep(wait)
                continue
        return resp

def _section(title):
    print(f"\n{CYAN}{BOLD}{'─'*52}{RESET}")
    print(f"{CYAN}{BOLD}  {title}{RESET}")
    print(f"{CYAN}{BOLD}{'─'*52}{RESET}")

def _hit(label, value):
    print(f"{GREEN}[+]{RESET} {BOLD}{label}{RESET}: {value}")

def _warn(label, value):
    print(f"{YELLOW}[!]{RESET} {BOLD}{label}{RESET}: {value}")

def _set(key, value):
    """Write value into jsonOutput. For keys that already exist in the
    default schema, empty values ARE preserved so the output shape stays
    consistent across scans."""
    # For schema keys, always write (even empty) — keeps JSON shape stable.
    if key in jsonOutput:
        jsonOutput[key] = value
        return
    # For ad-hoc keys, keep the old "only meaningful" behaviour.
    if value is None:
        return
    if isinstance(value, str) and not value.strip():
        return
    if isinstance(value, (list, dict)) and not value:
        return
    jsonOutput[key] = value

def _append(key, item):
    """Append to a list-valued key. Creates the list if missing."""
    if item is None:
        return
    if isinstance(item, str) and not item.strip():
        return
    if isinstance(item, dict) and not item:
        return
    jsonOutput.setdefault(key, [])
    if item not in jsonOutput[key]:
        jsonOutput[key].append(item)

def _scan_secrets(text, source):
    if len(text) > MAX_SCAN_BYTES:
        text = text[:MAX_SCAN_BYTES]
    for name, pat in SECRET_PATTERNS.items():
        for m in re.findall(pat, text):
            snippet = (m if isinstance(m, str) else next((x for x in m if x), ''))[:60]
            if not snippet:
                continue
            _warn(f'SECRET({name})', f'{snippet}… — {source}')
            _append('secrets_found', {'type': name, 'snippet': snippet, 'source': source})

# Common false-positive tokens that match social patterns but aren't handles.
# These are generic words, stopwords, or filetypes that frequently appear after
# "@" in READMEs/bios (@domain, @everyone, @media in CSS, etc.).
SOCIAL_STOPWORDS = {
    # Generic English
    'domain', 'everyone', 'here', 'all', 'you', 'me', 'us', 'it',
    'type', 'import', 'export', 'media', 'font', 'keyframes', 'supports',
    'charset', 'the', 'and', 'or', 'not', 'if', 'else', 'for', 'while',
    'return', 'true', 'false', 'null', 'none', 'any', 'param', 'params',
    'example', 'foo', 'bar', 'test', 'demo', 'user', 'username',
    # Common OSINT-context words that end up after @ in tutorials/READMEs
    'osint', 'tactical', 'author', 'credit', 'credits', 'thanks',
    'mention', 'mentions', 'profile', 'account', 'handle', 'social',
    # File/URL fragments
    'com', 'org', 'net', 'io', 'co', 'www', 'http', 'https',
    'github', 'gitlab', 'bitbucket', 'twitter', 'mastodon', 'linkedin',
    'instagram', 'telegram', 'discord', 'reddit', 'keybase',
    # TLD-like
    'dev', 'xyz', 'app', 'page', 'site',
}

def _looks_like_hash_or_id(s):
    """Heuristic: 'de14e947', '1a2b3c', etc. — 6-40 char all-hex strings
    are almost always commit SHAs or IDs, not handles."""
    if len(s) < 6 or len(s) > 40:
        return False
    return bool(re.fullmatch(r'[0-9a-f]+', s.lower())) and any(c.isdigit() for c in s)

def _looks_like_valid_handle(val):
    """Filter out common false positives that look like social handles
    but aren't. Applied to all platforms that use @handle form."""
    if not val:
        return False
    v = val.strip().lower().rstrip('/')
    if len(v) < 3 or len(v) > 40:
        return False
    if v in SOCIAL_STOPWORDS:
        return False
    if _looks_like_hash_or_id(v):
        return False
    # All-digit handles are suspicious for Twitter / IG (both allow but rare in bios)
    if v.isdigit():
        return False
    return True


# Domains that are NOT Mastodon — skip them when matching Mastodon URL pattern
NON_MASTODON_DOMAINS = {
    'twitter.com', 'x.com', 'linkedin.com', 'youtube.com', 'youtu.be',
    'instagram.com', 'threads.net', 'facebook.com', 'fb.com',
    'reddit.com', 'medium.com', 'tiktok.com', 'github.com', 'gitlab.com',
    'bitbucket.org', 'twitch.tv', 'discord.com', 'discord.gg',
    't.me', 'telegram.me', 'keybase.io', 'patreon.com', 'ko-fi.com',
    'bsky.app', 'hashnode.com', 'hashnode.dev', 'dev.to',
    'stackoverflow.com', 'hackthebox.com', 'tryhackme.com',
    'buymeacoffee.com', 'buymeacoff.com',
}


def _extract_social(text):
    found = {}
    # Pass 1: find Mastodon matches first, so we can strip their text from
    # subsequent platform searches (Mastodon handles look like Twitter @handles
    # to the Twitter regex otherwise).
    masto_matches = re.findall(SOCIAL_PATTERNS["Mastodon"], text, re.IGNORECASE)
    masked_text = text
    masto_handles = []
    for m in masto_matches:
        if m[0] and m[1]:
            domain = m[0].lower().lstrip('www.')
            if domain in NON_MASTODON_DOMAINS:
                continue
            masto_handles.append(f"@{m[1]}@{domain}")
            # Remove this fragment from the text so Twitter/Reddit regex
            # don't re-pick `@user` out of a Mastodon URL.
            masked_text = re.sub(
                re.escape(m[0]) + r"/@" + re.escape(m[1]),
                " ", masked_text, flags=re.I
            )
        elif m[2] and m[3]:
            domain = m[3].lower()
            if domain in NON_MASTODON_DOMAINS:
                continue
            masto_handles.append(f"@{m[2]}@{domain}")
            masked_text = re.sub(
                r"@" + re.escape(m[2]) + r"@" + re.escape(m[3]),
                " ", masked_text, flags=re.I
            )
    if masto_handles:
        found["Mastodon"] = list(dict.fromkeys(masto_handles))

    # Pass 2: every other platform (on the masked text)
    for platform, pattern in SOCIAL_PATTERNS.items():
        if platform == "Mastodon":
            continue
        cleaned = []
        for m in re.findall(pattern, masked_text, re.IGNORECASE):
            if platform == "Matrix" and isinstance(m, tuple) and len(m) == 2:
                cleaned.append(f"@{m[0]}:{m[1]}")
                continue
            val = (next((g for g in m if g), None) if isinstance(m, tuple) else m)
            if not val:
                continue
            val = val.strip().rstrip('/')
            if platform in ("Matrix", "XMPP"):
                cleaned.append(val)
                continue
            if not _looks_like_valid_handle(val):
                continue
            cleaned.append(val)
        if cleaned:
            found[platform] = list(dict.fromkeys(cleaned))
    return found

def _add_social(platform, handle):
    if not handle or not handle.strip():
        return
    handle = handle.strip().rstrip('/')
    # Mastodon/Matrix/XMPP handles intentionally contain @ and : — skip
    # the generic handle validator which would reject them.
    if platform not in ("Mastodon", "Matrix", "XMPP"):
        if not _looks_like_valid_handle(handle):
            return
    jsonOutput.setdefault('social_media', {}).setdefault(platform, [])
    if handle not in jsonOutput['social_media'][platform]:
        jsonOutput['social_media'][platform].append(handle)

def _add_email(em):
    if not em:
        return
    em = em.strip().lower()
    if not em or 'noreply' in em or 'example' in em or em.endswith(('.png', '.jpg', '.gif')):
        return
    if em not in email_out:
        email_out.append(em)

# ─────────────────────────────────────────────────────────────
# INPUT NORMALIZER  (URL / @handle / plain / email)
# ─────────────────────────────────────────────────────────────
def normalize_target(raw):
    """
    Accepts:
      emrexyz
      @emrexyz
      github.com/emrexyz
      https://github.com/emrexyz
      https://github.com/emrexyz/  (trailing slash, subpaths ignored)
      me@example.com
    Returns: (value, kind)  where kind in {'username','email'}
    """
    t = raw.strip()
    if not t:
        return '', 'username'

    # URL form (with or without scheme)
    url_match = re.search(
        r'(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9](?:[A-Za-z0-9\-]{0,38}))',
        t, re.IGNORECASE
    )
    if url_match:
        return url_match.group(1), 'username'

    # @handle
    if t.startswith('@'):
        return t.lstrip('@').strip(), 'username'

    # Email (must contain @ and a dot in the domain part)
    if '@' in t:
        left, _, right = t.partition('@')
        if left and '.' in right:
            return t, 'email'

    # Plain username
    return t, 'username'

# ─────────────────────────────────────────────────────────────
# MODULE 1 — GITHUB PROFILE
# ─────────────────────────────────────────────────────────────
def findInfoFromUsername(username):
    _section("GitHub Profile")
    r = _get(f'https://api.github.com/users/{username}')
    if not r or r.status_code != 200:
        return False

    data = r.json()
    fields = ['login','id','avatar_url','name','blog','location',
              'twitter_username','email','company','bio',
              'public_repos','followers','following','created_at','updated_at']

    for key in fields:
        val = data.get(key)
        if val in (None, ''):
            continue
        if key == 'location' and str(val).lower().strip() in SKIP_LOCATIONS:
            continue
        if key == 'email':
            _add_email(val)
        _set(key, val)
        _hit(key, val)

    tw = data.get('twitter_username') or ''
    if tw:
        _add_social('Twitter/X', tw)

    combined = f"{data.get('bio') or ''} {data.get('blog') or ''}".strip()
    if combined:
        social = _extract_social(combined)
        if social:
            _section("Social Media (Bio/Blog)")
            for platform, handles in social.items():
                for h in handles:
                    _hit(platform, h)
                    _add_social(platform, h)
    return True

# ─────────────────────────────────────────────────────────────
# MODULE 1b — SOCIAL ACCOUNTS (GitHub native endpoint, 2022+)
# ─────────────────────────────────────────────────────────────
def findSocialAccounts(username):
    _section("Social Accounts (GitHub native)")
    r = _get(f'https://api.github.com/users/{username}/social_accounts')
    if not r or r.status_code != 200 or not isinstance(r.json(), list):
        return
    accounts = r.json()
    if not accounts:
        return
    for acc in accounts:
        provider = acc.get('provider', 'unknown')
        url = acc.get('url', '')
        if not url:
            continue
        _hit(f'social_{provider}', url)
        _append('social_accounts', {'provider': provider, 'url': url})

# ─────────────────────────────────────────────────────────────
# MODULE 2 — GPG / SSH KEYS
# ─────────────────────────────────────────────────────────────
def findPublicKeys(username):
    _section("Public Keys")
    gpg_r = _get(f'https://github.com/{username}.gpg', gh=False)
    ssh_r = _get(f'https://github.com/{username}.keys', gh=False)
    gpg = gpg_r.text if gpg_r else ''
    ssh = ssh_r.text if ssh_r else ''

    if gpg.strip() and "hasn't uploaded any GPG keys" not in gpg:
        url = f'https://github.com/{username}.gpg'
        _hit('GPG_keys', url)
        _set('GPG_keys', url)
        pat = re.compile(
            r"-----BEGIN [^-]+-----([A-Za-z0-9+\/=\s]+)-----END [^-]+-----",
            re.MULTILINE
        )
        for match in pat.findall(gpg):
            try:
                raw = base64.b64decode(match)
                short_id = binascii.hexlify(raw[-8:]).decode()
                _hit('GPG_short_id', short_id)
                _append('GPG_ids', short_id)
                for em in EMAIL_RE.findall(raw.decode('latin-1', errors='ignore')):
                    _add_email(em)
                    _hit('GPG_email', em)
            except Exception:
                pass

    if ssh.strip():
        count = len(ssh.strip().splitlines())
        url = f'https://github.com/{username}.keys'
        _hit('SSH_keys', f'{url} ({count} key(s))')
        _set('SSH_keys', url)
        _set('SSH_keys_count', count)

# ─────────────────────────────────────────────────────────────
# MODULE 3 — GIST ANALYSIS
# ─────────────────────────────────────────────────────────────
def analyzeGists(username):
    _section("Gist Analysis")
    page, total, gist_secrets = 1, 0, []

    while True:
        r = _get(f'https://api.github.com/users/{username}/gists?per_page=100&page={page}')
        if not r:
            break
        gists = r.json()
        if not gists or not isinstance(gists, list):
            break
        for gist in gists:
            total += 1
            gist_id = gist.get('id', '')
            for fname, fdata in (gist.get('files') or {}).items():
                for s in SENSITIVE_FILENAMES:
                    if s.lower() in fname.lower():
                        _warn('SENSITIVE_GIST_FILE', f'{fname} → https://gist.github.com/{username}/{gist_id}')
                        gist_secrets.append({'file': fname, 'gist': gist_id})
                raw_url = fdata.get('raw_url', '')
                size = fdata.get('size', 0) or 0
                if raw_url and 0 < size < MAX_SCAN_BYTES:
                    try:
                        content = session.get(raw_url, timeout=10).text
                        for em in EMAIL_RE.findall(content):
                            _add_email(em)
                        _scan_secrets(content, f'gist:{gist_id}/{fname}')
                        for platform, handles in _extract_social(content).items():
                            for h in handles:
                                _hit(f'gist_social({platform})', h)
                                _add_social(platform, h)
                    except Exception:
                        pass
        if len(gists) < 100:
            break
        page += 1

    if total > 0:
        _hit('total_gists', total)
        _set('gist_count', total)
    if gist_secrets:
        _set('gist_sensitive_files', gist_secrets)

# ─────────────────────────────────────────────────────────────
# MODULE 4 — PUBLIC EVENTS (commit email leak — highest-value signal)
# ─────────────────────────────────────────────────────────────
def analyzeEvents(username):
    _section("Public Events (commit email leak)")
    emails_found = {}
    for page in range(1, 4):
        r = _get(f'https://api.github.com/users/{username}/events/public?per_page=100&page={page}')
        if not r or r.status_code != 200:
            break
        events = r.json()
        if not isinstance(events, list) or not events:
            break
        for ev in events:
            payload = ev.get('payload', {}) or {}
            repo = (ev.get('repo') or {}).get('name', '?')
            for c in payload.get('commits', []) or []:
                author = (c.get('author') or {})
                em = (author.get('email') or '').strip()
                nm = (author.get('name') or '').strip()
                if not em or 'noreply' in em:
                    continue
                if em not in emails_found:
                    emails_found[em] = {'name': nm, 'repo': repo}
                    _hit('commit_email', f'{em} ({nm}) — {repo}')
                _add_email(em)
        if len(events) < 100:
            break
    # Always write (even empty) to keep JSON shape stable across scans
    _set('public_events_emails', [
        {'email': e, 'name': v['name'], 'repo': v['repo']}
        for e, v in emails_found.items()
    ])

# ─────────────────────────────────────────────────────────────
# MODULE 5 — COMMIT SEARCH (across all public repos)
# ─────────────────────────────────────────────────────────────
def searchCommits(username):
    _section(f"Commit Search (author:{username})")
    hdr = dict(GH_HEADERS)
    hdr['Accept'] = 'application/vnd.github.cloak-preview+json'
    try:
        r = session.get(
            f'https://api.github.com/search/commits?q=author:{username}&per_page=50',
            headers=hdr, timeout=15
        )
    except Exception:
        return
    if r.status_code != 200:
        return
    items = r.json().get('items', []) or []
    seen = {}
    for it in items:
        commit = (it.get('commit') or {})
        repo = ((it.get('repository') or {}).get('full_name')) or '?'
        for role in ('author', 'committer'):
            person = commit.get(role) or {}
            em = (person.get('email') or '').strip()
            nm = (person.get('name') or '').strip()
            if not em or 'noreply' in em:
                continue
            key = (em, role)
            if key not in seen:
                seen[key] = {'email': em, 'name': nm, 'role': role, 'repo': repo}
                _hit(f'search_{role}_email', f'{em} ({nm}) — {repo}')
            _add_email(em)
    # Always write (even empty) to keep JSON shape stable
    _set('commit_search_emails', list(seen.values()))

# ─────────────────────────────────────────────────────────────
# MODULE 6 — FOLLOWING / FOLLOWERS / STARRED
# ─────────────────────────────────────────────────────────────
def analyzeSocial(username):
    _section("Following / Followers / Starred")
    following_count = jsonOutput.get('following', 0)
    followers_count = jsonOutput.get('followers', 0)
    if following_count:
        _hit('following_count', following_count)
    if followers_count:
        _hit('followers_count', followers_count)

    r = _get(f'https://api.github.com/users/{username}/starred?per_page=100')
    if not r or r.status_code != 200 or not isinstance(r.json(), list):
        return
    langs, topics = {}, {}
    for repo in r.json():
        lang = repo.get('language')
        if lang:
            langs[lang] = langs.get(lang, 0) + 1
        for t in repo.get('topics', []) or []:
            topics[t] = topics.get(t, 0) + 1
    if langs:
        top_langs = dict(sorted(langs.items(), key=lambda x: -x[1])[:5])
        top_str   = ', '.join(f'{l}({c})' for l, c in top_langs.items())
        _hit('starred_top_languages', top_str)
        _set('starred_top_languages', top_langs)     # JSON gets dict
    else:
        _set('starred_top_languages', {})
    if topics:
        top_topics = dict(sorted(topics.items(), key=lambda x: -x[1])[:8])
        top_str    = ', '.join(f'{t}({c})' for t, c in top_topics.items())
        _hit('starred_top_topics', top_str)
        _set('starred_top_topics', top_topics)       # JSON gets dict
    else:
        _set('starred_top_topics', {})

# ─────────────────────────────────────────────────────────────
# MODULE 7 — ORGANIZATIONS
# ─────────────────────────────────────────────────────────────
def findOrganizations(username):
    _section("Organizations")
    r = _get(f'https://api.github.com/users/{username}/orgs')
    if not r or r.status_code != 200 or not isinstance(r.json(), list) or not r.json():
        return
    org_data = []
    for org in r.json():
        org_login = org.get('login', '')
        if not org_login:
            continue
        _hit('organization', org_login)
        mr = _get(f'https://api.github.com/orgs/{org_login}/public_members?per_page=100')
        members = []
        if mr and mr.status_code == 200 and isinstance(mr.json(), list):
            members = [m['login'] for m in mr.json() if m.get('login') and m['login'] != username]
        if members:
            _hit(f'  org_members({org_login})', ', '.join(members[:20]) + ('…' if len(members) > 20 else ''))
        org_data.append({'org': org_login, 'members': members})
    if org_data:
        _set('organizations', org_data)

# ─────────────────────────────────────────────────────────────
# MODULE 8 — PROFILE README
# ─────────────────────────────────────────────────────────────
def scanProfileReadme(username):
    _section("Profile README")
    for branch in ['main', 'master']:
        for fname in ['README.md', 'readme.md']:
            try:
                r = session.get(
                    f'https://raw.githubusercontent.com/{username}/{username}/{branch}/{fname}',
                    headers={'User-Agent': UA}, timeout=10
                )
            except Exception:
                continue
            if r.status_code == 200 and r.text.strip():
                _set('profile_readme', f'{branch}/{fname}')
                social = _extract_social(r.text)
                for platform, handles in social.items():
                    for h in handles:
                        _hit(platform, h)
                        _add_social(platform, h)
                _scan_secrets(r.text, f'profile_readme/{fname}')
                for em in EMAIL_RE.findall(r.text):
                    _add_email(em)
                return

# ─────────────────────────────────────────────────────────────
# FULL SCAN
# ─────────────────────────────────────────────────────────────
def fullScan(username):
    # Stamp scan time right away so even a failed scan records when it ran
    _set('scanned_at', datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))

    exists = findInfoFromUsername(username)
    if not exists:
        print(f"{RED}[-]{RESET} Username '{username}' does not exist.")
        return

    findSocialAccounts(username)
    findPublicKeys(username)
    analyzeGists(username)
    analyzeEvents(username)
    searchCommits(username)
    analyzeSocial(username)
    findOrganizations(username)
    scanProfileReadme(username)

    unique_emails = list(dict.fromkeys(
        e for e in email_out if 'noreply' not in e and 'example' not in e
    ))
    # Always write emails_all (even if empty) so platform sees the key
    _set('emails_all', unique_emails)
    if unique_emails:
        _section("All Emails Found")
        for e in unique_emails:
            _hit('email', e)

    out_file = f'{username}.json'
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(jsonOutput, f, sort_keys=True, indent=4, default=str, ensure_ascii=False)
    print(f"\n{GREEN}[+]{RESET} Saved → {out_file}")

# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog='osgint',
        description='GitHub OSINT — username, @username, profile URL, or email'
    )
    parser.add_argument('target', help='GitHub username | @username | github.com/user URL | email')
    parser.add_argument('--json', action='store_true', help='Also print JSON to stdout')
    args = parser.parse_args()

    value, kind = normalize_target(args.target)
    if not value:
        print(f"{RED}[-]{RESET} Invalid input.")
        sys.exit(1)

    if kind == 'email':
        _section("Email Lookup")
        r = _get(f'https://api.github.com/search/users?q={value}')
        users = re.findall(r'"login":"(.*?)"', r.text) if r else []
        if not users:
            print(f"{RED}[-]{RESET} No GitHub user found for: {value}")
            sys.exit(1)
        username = users[0]
        _hit('github_username', username)
        fullScan(username)
    else:
        fullScan(value)

    if args.json:
        print(json.dumps(jsonOutput, sort_keys=True, indent=4, default=str, ensure_ascii=False))
