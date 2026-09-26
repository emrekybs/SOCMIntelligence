#!/usr/bin/env python3
"""
Reddit OSINT Tool — SOCMIntelligence
══════════════════════════════
Usage:
  python reddit_osint.py USERNAME
  python reddit_osint.py u/USERNAME
  python reddit_osint.py https://www.reddit.com/user/USERNAME
  python reddit_osint.py USER1 USER2 USER3
  python reddit_osint.py USERNAME --limit 100
  python reddit_osint.py USERNAME --no-color

Requirements:
  pip install requests rich
No auth required — uses public Reddit JSON API.
"""

import sys, re, json, argparse, time
from collections import Counter
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

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

C  = Console() if HAS_RICH else None
UA = "SOCMIntelligence/1.0 (Reddit OSINT Tool)"

# Sentiment lexicons
POS_WORDS = {"great","good","love","amazing","awesome","excellent","nice","best",
             "thanks","thank","helpful","perfect","yes","agree","correct","right",
             "beautiful","wonderful","interesting","cool","fantastic","brilliant"}
NEG_WORDS = {"bad","hate","terrible","awful","worst","wrong","stupid","idiot",
             "disgusting","horrible","trash","garbage","toxic","annoying","false",
             "boring","pathetic","ridiculous","dumb","ugly","lame","cringe"}

# Well-known large subreddits — activity here means "generic user"
GENERIC_SUBS = {"AskReddit","worldnews","news","funny","gaming","pics","videos",
                "todayilearned","science","IAmA","EarthPorn","Music","movies",
                "technology","bestof","explainlikeimfive","LifeProTips","Showerthoughts"}


# ══════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════

def parse_target(raw: str) -> tuple[str, str]:
    """
    Input → (kind, name)
    kind: 'user' | 'subreddit'

    Accepts:
      spez, @spez, u/spez, /u/spez
      r/OSINT, /r/OSINT
      https://www.reddit.com/user/spez[/...]
      https://old.reddit.com/u/spez
      https://np.reddit.com/r/OSINT/
      www.reddit.com/r/OSINT  (no scheme)
    """
    raw = raw.strip().rstrip("/")

    # Subreddit URL (any subdomain: www, old, np, new, i...)
    m = re.search(r"reddit\.com/r/([A-Za-z0-9_]+)", raw, re.I)
    if m: return "subreddit", m.group(1)

    # r/subreddit or /r/subreddit
    m = re.match(r"/?r/([A-Za-z0-9_]+)$", raw, re.I)
    if m: return "subreddit", m.group(1)

    # User URL (user/ or u/)
    m = re.search(r"reddit\.com/(?:user|u)/([A-Za-z0-9_\-]+)", raw, re.I)
    if m: return "user", m.group(1)

    # u/username or /u/username
    m = re.match(r"/?u/([A-Za-z0-9_\-]+)$", raw, re.I)
    if m: return "user", m.group(1)

    # @username
    m = re.match(r"@([A-Za-z0-9_\-]+)$", raw)
    if m: return "user", m.group(1)

    # Plain username (Reddit username: 3-20 chars, alnum + _ -)
    return "user", raw


def rget(url: str, params: dict = None) -> dict | None:
    """Reddit JSON API — respects rate limits."""
    try:
        r = requests.get(
            url, params=params,
            headers={"User-Agent": UA},
            timeout=15
        )
        if r.status_code == 429:
            time.sleep(2)
            r = requests.get(url, params=params,
                             headers={"User-Agent": UA}, timeout=15)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None


def fn(n) -> str:
    try: n = int(n)
    except: return str(n)
    if n >= 1_000_000: return f"{n/1e6:.1f}M"
    if n >= 1_000:     return f"{n/1e3:.1f}K"
    return f"{n:,}"


def fts(ts) -> str:
    if not ts: return "N/A"
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%d.%m.%Y")
    except: return str(ts)


def fage(ts) -> str:
    if not ts: return "N/A"
    try:
        created = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        days    = (datetime.now(tz=timezone.utc) - created).days
        y, m    = days // 365, (days % 365) // 30
        parts   = []
        if y: parts.append(f"{y} year"  + ("s" if y != 1 else ""))
        if m: parts.append(f"{m} month" + ("s" if m != 1 else ""))
        return ", ".join(parts) or f"{days} day" + ("s" if days != 1 else "")
    except: return "N/A"


def ascii_bar(v, mx, w=16) -> str:
    if mx == 0: return ""
    f = max(1, int(v / mx * w))
    return "█" * f + "░" * (w - f)


# ══════════════════════════════════════════════════════
#  DATA FETCH
# ══════════════════════════════════════════════════════

def fetch_profile(username: str) -> dict | None:
    data = rget(f"https://www.reddit.com/user/{username}/about.json")
    if not data: return None
    d = data.get("data", {})
    if d.get("is_suspended") or d.get("is_blocked"):
        return {"error": "Account suspended or blocked.", "username": username}
    return d


def fetch_items(username: str, kind: str, limit: int = 100) -> list:
    """kind: 'comments' | 'submitted'"""
    items  = []
    after  = None
    per_pg = min(limit, 100)

    while len(items) < limit:
        params = {"limit": per_pg, "raw_json": 1}
        if after: params["after"] = after
        data = rget(f"https://www.reddit.com/user/{username}/{kind}.json", params)
        if not data: break
        children = data.get("data", {}).get("children", [])
        if not children: break
        for c in children:
            items.append(c.get("data", {}))
        after = data.get("data", {}).get("after")
        if not after: break
        time.sleep(0.6)   # rate limit

    return items[:limit]


def fetch_pushshift(username: str) -> dict:
    """
    Pushshift API — scan for deleted comments.
    Results may be partial (Pushshift is not always up to date).
    """
    result = {"available": False, "deleted_count": 0, "samples": []}
    try:
        r = requests.get(
            "https://api.pushshift.io/reddit/search/comment/",
            params={"author": username, "size": 10, "fields": "body,subreddit,created_utc"},
            headers={"User-Agent": UA},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json().get("data", [])
            result["available"]     = True
            result["deleted_count"] = len(data)
            result["samples"]       = [
                {"text": d.get("body","")[:100],
                 "subreddit": d.get("subreddit",""),
                 "date": fts(d.get("created_utc"))}
                for d in data if d.get("body","") not in ("[deleted]","[removed]","")
            ]
    except Exception:
        pass
    return result


# ══════════════════════════════════════════════════════
#  ANALYSES
# ══════════════════════════════════════════════════════

def analyze_subreddits(comments: list, posts: list) -> dict:
    sub_counter = Counter()
    for item in comments + posts:
        s = item.get("subreddit")
        if s: sub_counter[s] += 1

    top = sub_counter.most_common(15)
    niche_subs = [(s, c) for s, c in top if s not in GENERIC_SUBS]
    interests  = [s for s, _ in niche_subs[:8]]

    return {
        "top_subreddits": [{"sub": s, "count": c} for s, c in top],
        "niche_subs":     [{"sub": s, "count": c} for s, c in niche_subs[:8]],
        "interests":      interests,
        "unique_subs":    len(sub_counter),
    }


def analyze_activity(comments: list, posts: list) -> dict:
    hour_c  = Counter()
    day_c   = Counter()
    all_ts  = []

    for item in comments + posts:
        ts = item.get("created_utc")
        if not ts: continue
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        hour_c[dt.hour]    += 1
        day_c[dt.weekday()] += 1
        all_ts.append(dt)

    if not all_ts:
        return {}

    all_ts.sort()
    best_hour = hour_c.most_common(1)[0][0] if hour_c else None
    best_day  = day_c.most_common(1)[0][0]  if day_c  else None
    days_en   = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

    # Timezone estimate — from peak activity hour
    # (person most likely active between 08-23)
    tz_est = None
    if best_hour is not None:
        # UTC offset estimate, assuming local afternoon (14:00) is peak
        offset = (14 - best_hour) % 24
        if offset > 12: offset -= 24
        if -12 <= offset <= 14:
            tz_est = f"UTC{'+' if offset >= 0 else ''}{offset} (estimated)"

    # Activity score
    now      = datetime.now(tz=timezone.utc)
    last_30d = sum(1 for t in all_ts if (now - t).days <= 30)
    last_90d = sum(1 for t in all_ts if (now - t).days <= 90)
    score    = min(100, last_30d * 4 + last_90d)

    return {
        "hour_distribution":  dict(sorted(hour_c.items())),
        "day_distribution":   dict(sorted(day_c.items())),
        "best_hour":          f"{best_hour:02d}:00" if best_hour is not None else "N/A",
        "best_day":           days_en[best_day] if best_day is not None else "N/A",
        "timezone_est":       tz_est,
        "last_30d_posts":     last_30d,
        "last_90d_posts":     last_90d,
        "activity_score":     score,
        "first_activity":     fts(all_ts[0].timestamp())  if all_ts else "N/A",
        "last_activity":      fts(all_ts[-1].timestamp()) if all_ts else "N/A",
    }


def analyze_content(comments: list, posts: list) -> dict:
    # Karma breakdown
    comment_karma = sum(c.get("score", 0) for c in comments)
    post_karma    = sum(p.get("score", 0) for p in posts)
    top_comments  = sorted(comments, key=lambda x: x.get("score", 0), reverse=True)[:5]
    top_posts     = sorted(posts,    key=lambda x: x.get("score", 0), reverse=True)[:5]

    # Sentiment analysis
    pos = neg = neu = 0
    for item in comments:
        body = (item.get("body") or "").lower()
        p    = sum(1 for w in POS_WORDS if w in body)
        n    = sum(1 for w in NEG_WORDS if w in body)
        if p > n:   pos  += 1
        elif n > p: neg  += 1
        else:       neu  += 1
    total_s  = pos + neg + neu
    pos_pct  = round(pos  / total_s * 100, 1) if total_s else 0
    neg_pct  = round(neg  / total_s * 100, 1) if total_s else 0

    # Average comment length
    lengths  = [len(c.get("body","")) for c in comments if c.get("body")]
    avg_len  = round(sum(lengths) / len(lengths)) if lengths else 0

    # Deleted / removed content
    deleted  = sum(1 for c in comments if c.get("body") in ("[deleted]","[removed]"))

    return {
        "comment_karma":   comment_karma,
        "post_karma":      post_karma,
        "avg_comment_len": avg_len,
        "deleted_comments":deleted,
        "top_comments": [
            {"text": c.get("body","")[:120], "score": c.get("score",0),
             "subreddit": c.get("subreddit",""), "date": fts(c.get("created_utc"))}
            for c in top_comments
        ],
        "top_posts": [
            {"title": p.get("title","")[:100], "score": p.get("score",0),
             "subreddit": p.get("subreddit",""), "url": p.get("url",""),
             "date": fts(p.get("created_utc"))}
            for p in top_posts
        ],
        "sentiment": {
            "positive": pos, "negative": neg, "neutral": neu,
            "pos_pct": pos_pct, "neg_pct": neg_pct,
        },
    }


def analyze_bot_score(profile: dict, comments: list, posts: list,
                      activity: dict) -> dict:
    """
    Heuristic bot / suspicious-behavior score (0-100).
    """
    score  = 0
    flags  = []

    # Account very young but very active
    age_days = 0
    ct = profile.get("created_utc")
    if ct:
        age_days = (datetime.now(tz=timezone.utc) -
                    datetime.fromtimestamp(int(ct), tz=timezone.utc)).days
    if age_days > 0 and age_days < 30 and len(comments) + len(posts) > 50:
        score += 25
        flags.append("Very young account, extremely active")

    # Very low karma but many posts
    total_karma = (profile.get("link_karma",0) or 0) + (profile.get("comment_karma",0) or 0)
    total_items = len(comments) + len(posts)
    if total_items > 20 and total_karma < 10:
        score += 20
        flags.append("Very low karma, high activity")

    # All comments in the same subreddit
    if comments:
        sub_c  = Counter(c.get("subreddit","") for c in comments)
        top_pct= sub_c.most_common(1)[0][1] / len(comments) if sub_c else 0
        if top_pct > 0.85:
            score += 15
            flags.append(f"{int(top_pct*100)}% of comments in a single subreddit")

    # Always active at the same hour
    hd = activity.get("hour_distribution", {})
    if hd:
        mx_hour_pct = max(hd.values()) / sum(hd.values()) if sum(hd.values()) else 0
        if mx_hour_pct > 0.5:
            score += 15
            flags.append("Activity clustered in a very narrow time window")

    # High rate of deleted comments
    deleted = sum(1 for c in comments if c.get("body") in ("[deleted]","[removed]"))
    if len(comments) > 10 and deleted / len(comments) > 0.3:
        score += 15
        flags.append(f"{int(deleted/len(comments)*100)}% of comments are deleted")

    # No avatar + not suspended + old account
    if not profile.get("icon_img") and age_days > 365:
        score += 10
        flags.append("Old account with no avatar")

    label = ("HIGH RISK" if score >= 60 else
             "MEDIUM RISK" if score >= 35 else
             "LOW RISK"    if score >= 15 else "CLEAN")

    return {"score": min(score, 100), "label": label, "flags": flags}


# ══════════════════════════════════════════════════════
#  FULL ANALYSIS
# ══════════════════════════════════════════════════════

def full_analyze(username: str, limit: int = 100) -> dict:
    result = {
        "username":   username,
        "profile_url":f"https://www.reddit.com/u/{username}",
        "scanned_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }

    # Profil
    profile = fetch_profile(username)
    if not profile:
        result["error"] = "User not found or access blocked."
        return result
    if profile.get("error"):
        result["error"] = profile["error"]
        return result

    result["profile"] = {
        "display_name":  profile.get("name"),
        "id":            profile.get("id"),
        "created_utc":   profile.get("created_utc"),
        "created_date":  fts(profile.get("created_utc")),
        "account_age":   fage(profile.get("created_utc")),
        "total_karma":   (profile.get("link_karma",0) or 0) +
                         (profile.get("comment_karma",0) or 0),
        "post_karma":    profile.get("link_karma", 0),
        "comment_karma": profile.get("comment_karma", 0),
        "verified":      profile.get("verified", False),
        "employee":      profile.get("is_employee", False),
        "nsfw":          profile.get("over_18", False),
        "has_avatar":    bool(profile.get("icon_img") and
                              "styles" not in str(profile.get("icon_img",""))),
        "avatar_url":    profile.get("icon_img") or profile.get("snoovatar_img") or "",
        "description":   (profile.get("subreddit",{}) or {}).get("public_description",""),
        "is_suspended":  profile.get("is_suspended", False),
    }

    # Comments and posts
    comments = fetch_items(username, "comments",  limit)
    posts    = fetch_items(username, "submitted", limit // 2)

    result["stats"] = {
        "comments_fetched": len(comments),
        "posts_fetched":    len(posts),
    }

    # Analizler
    sub_analysis  = analyze_subreddits(comments, posts)
    act_analysis  = analyze_activity(comments, posts)
    cont_analysis = analyze_content(comments, posts)
    bot_analysis  = analyze_bot_score(profile, comments, posts, act_analysis)

    result["subreddit_analysis"] = sub_analysis
    result["activity_analysis"]  = act_analysis
    result["content_analysis"]   = cont_analysis
    result["bot_score"]          = bot_analysis

    return result


# ══════════════════════════════════════════════════════
#  PRINT
# ══════════════════════════════════════════════════════

def print_profile(r: dict):
    c   = C
    p   = r.get("profile", {})
    sub = r.get("subreddit_analysis", {})
    act = r.get("activity_analysis",  {})
    con = r.get("content_analysis",   {})
    bot = r.get("bot_score",          {})

    c.print()
    c.print(Rule(f"[bold cyan]u/{r['username']}[/bold cyan]", style="cyan"))

    # ── Profile header
    flags = []
    if p.get("verified"):   flags.append("[green]✦ Verified[/green]")
    if p.get("employee"):   flags.append("[bright_cyan]Reddit Employee[/bright_cyan]")
    if p.get("nsfw"):       flags.append("[yellow]NSFW[/yellow]")
    if p.get("is_suspended"): flags.append("[red]SUSPENDED[/red]")

    hdr = Text()
    hdr.append(f"\n  u/{p.get('display_name', r['username'])}\n", style="bold white")
    if flags:
        hdr.append(f"  {'  '.join(flags)}\n")
    if p.get("description"):
        hdr.append(f"\n  {p['description'][:180]}\n", style="italic dim")
    hdr.append(f"\n  {r['profile_url']}", style="dim underline")
    c.print(Panel(hdr, title="[bold]Profile[/bold]",
                  border_style="cyan", padding=(0,2)))

    # ── Basic stats
    st = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
               border_style="dim", min_width=60, padding=(0,2))
    st.add_column("Field",  style="dim", width=22)
    st.add_column("Value",  style="bold white", justify="right")
    st.add_column("",       style="dim", width=20)
    st.add_row("Total Karma",     fn(p.get("total_karma",0)),    "")
    st.add_row("Post Karma",      fn(p.get("post_karma",0)),     "")
    st.add_row("Comment Karma",   fn(p.get("comment_karma",0)),  "")
    st.add_row("Created",         p.get("created_date","N/A"),   p.get("account_age",""))
    st.add_row("Avatar",          "Yes" if p.get("has_avatar") else "No", "")
    st.add_row("Comments Fetched",fn(r.get("stats",{}).get("comments_fetched",0)), "")
    st.add_row("Posts Fetched",   fn(r.get("stats",{}).get("posts_fetched",0)),    "")
    c.print(Panel(st, title="[bold]Statistics[/bold]", border_style="magenta"))

    # ── Subreddit analysis
    tops = sub.get("top_subreddits", [])
    if tops:
        mx = tops[0]["count"] if tops else 1
        tbl = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                    border_style="dim", padding=(0,1))
        tbl.add_column("Subreddit",  style="cyan",   width=26)
        tbl.add_column("Activity",   justify="right", width=8)
        tbl.add_column("",           min_width=18)
        for item in tops[:12]:
            tbl.add_row(
                f"r/{item['sub']}",
                str(item["count"]),
                f"[cyan]{ascii_bar(item['count'], mx)}[/cyan]"
            )
        interest_str = "  ".join(sub.get("interests", [])[:6])
        summary = (f"  Unique subreddits:  [bold]{sub.get('unique_subs',0)}[/bold]\n"
                   f"  Niche interests:    [cyan]{interest_str}[/cyan]")
        c.print(Panel(Text.from_markup(summary),
                      title="[bold]Subreddit Summary[/bold]", border_style="dim"))
        c.print(Panel(tbl, title="[bold]Most Active Subreddits[/bold]",
                      border_style="green"))

    # ── Activity analysis
    if act:
        hd   = act.get("hour_distribution", {})
        dd   = act.get("day_distribution",  {})
        days_en = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
        mx_h = max(hd.values(), default=1)
        mx_d = max(dd.values(), default=1)

        hour_lines = [
            f"  {k:02d}:00  {ascii_bar(v, mx_h, 14)}  {v}"
            for k, v in sorted(hd.items())
        ]
        day_lines = [
            f"  {days_en[k]:<4}  {ascii_bar(v, mx_d, 14)}  {v}"
            for k, v in sorted(dd.items())
        ]
        act_score = act.get("activity_score", 0)
        act_color = ("bright_green" if act_score >= 75 else
                     "green"        if act_score >= 45 else
                     "yellow"       if act_score >= 20 else "red")

        summary = (
            f"  Activity Score   [{act_color}]{act_score}/100[/{act_color}]\n"
            f"  Peak Hour        [bold]{act.get('best_hour','?')}[/bold]\n"
            f"  Peak Day         [bold]{act.get('best_day','?')}[/bold]\n"
            f"  Timezone (est.)  [yellow]{act.get('timezone_est','?')}[/yellow]\n"
            f"  Last 30 days     {act.get('last_30d_posts',0)} actions\n"
            f"  Last activity    {act.get('last_activity','?')}\n"
            f"  First activity   {act.get('first_activity','?')}\n\n"
            "[dim]── Hour Distribution ──[/dim]\n" +
            "\n".join(hour_lines) +
            "\n\n[dim]── Day Distribution ──[/dim]\n" +
            "\n".join(day_lines)
        )
        c.print(Panel(Text.from_markup(summary),
                      title="[bold]Activity Analysis[/bold]", border_style="blue"))

    # ── Content analysis
    if con:
        sent     = con.get("sentiment", {})
        total_s  = sent.get("positive",0) + sent.get("negative",0) + sent.get("neutral",0)
        if total_s:
            pb = ascii_bar(sent["positive"], total_s, 16)
            nb = ascii_bar(sent["negative"], total_s, 16)
            ob = ascii_bar(sent["neutral"],  total_s, 16)
            sent_text = (
                f"  [green]Positive[/green]  [green]{pb}[/green]  "
                f"{sent['positive']} ({sent['pos_pct']}%)\n"
                f"  [red]Negative[/red]  [red]{nb}[/red]  "
                f"{sent['negative']} ({sent['neg_pct']}%)\n"
                f"  [dim]Neutral [/dim]  [dim]{ob}[/dim]  {sent['neutral']}"
            )
            c.print(Panel(
                Text.from_markup(
                    f"  Avg. comment length: {con.get('avg_comment_len',0)} chars\n"
                    f"  Deleted comments:    {con.get('deleted_comments',0)}\n\n" +
                    sent_text
                ),
                title="[bold]Content Analysis[/bold]", border_style="yellow"
            ))

        # Top comments
        top_c = con.get("top_comments", [])
        if top_c:
            ct = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                       border_style="dim", padding=(0,1))
            ct.add_column("Score",     justify="right", width=7)
            ct.add_column("Subreddit", style="cyan",    width=20)
            ct.add_column("Date",      style="dim",     width=12)
            ct.add_column("Comment",   min_width=28,    no_wrap=True)
            for item in top_c:
                ct.add_row(
                    str(item["score"]),
                    f"r/{item['subreddit']}",
                    item["date"],
                    item["text"][:60].replace("\n"," "),
                )
            c.print(Panel(ct, title="[bold]Top Comments[/bold]",
                          border_style="green"))

        # Top posts
        top_p = con.get("top_posts", [])
        if top_p:
            pt = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                       border_style="dim", padding=(0,1))
            pt.add_column("Score",     justify="right", width=7)
            pt.add_column("Subreddit", style="cyan",    width=20)
            pt.add_column("Date",      style="dim",     width=12)
            pt.add_column("Title",     min_width=28,    no_wrap=True)
            for item in top_p:
                pt.add_row(
                    str(item["score"]),
                    f"r/{item['subreddit']}",
                    item["date"],
                    item["title"][:55],
                )
            c.print(Panel(pt, title="[bold]Top Posts[/bold]",
                          border_style="bright_magenta"))

    # ── Bot score
    if bot:
        bs     = bot.get("score", 0)
        bl     = bot.get("label", "")
        bflags = bot.get("flags", [])
        bc     = ("red" if bs >= 60 else "orange1" if bs >= 35
                  else "yellow" if bs >= 15 else "green")
        lines  = [
            f"  Score  [{bc}]{bs}/100[/{bc}]  [{bc}]{bl}[/{bc}]"
        ]
        for f in bflags:
            lines.append(f"  [dim]•[/dim] {f}")
        c.print(Panel(Text.from_markup("\n".join(lines)),
                      title="[bold]Bot / Suspicion Score[/bold]", border_style=bc))

    c.print(Rule(style="dim"))
    c.print()


def print_plain(r: dict):
    p   = r.get("profile", {})
    sub = r.get("subreddit_analysis", {})
    act = r.get("activity_analysis",  {})
    con = r.get("content_analysis",   {})
    bot = r.get("bot_score",          {})
    SEP = "=" * 58
    print(SEP)
    print(f"  u/{r['username']}")
    print(SEP)
    print(f"  Total Karma     : {fn(p.get('total_karma',0))}")
    print(f"  Created         : {p.get('created_date','?')}  ({p.get('account_age','')})")
    print(f"  Verified        : {'Yes' if p.get('verified') else 'No'}")
    if sub.get("interests"):
        print(f"  Interests       : {', '.join(sub['interests'][:5])}")
    if act:
        print(f"  Peak Hour       : {act.get('best_hour','?')}")
        print(f"  Peak Day        : {act.get('best_day','?')}")
        print(f"  Timezone (est.) : {act.get('timezone_est','?')}")
    if bot:
        print(f"  Bot Score       : {bot.get('score',0)}/100  {bot.get('label','')}")
    if con.get("sentiment"):
        s = con["sentiment"]
        print(f"  Sentiment       : +{s['pos_pct']}% / -{s['neg_pct']}%")
    print(SEP)


# ══════════════════════════════════════════════════════
#  SAVE JSON
# ══════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════
#  JSON OUTPUT — platform-friendly normalization
# ══════════════════════════════════════════════════════

def normalize(obj):
    """
    Lossless JSON normalization. Keeps every field intact — does NOT drop
    empty/null/[] values. The consuming frontend always sees the same schema.

    - tuple → list (JSON-safe)
    - datetime / Peer / MTProto-ish objects → str
    - "N/A" → null (real null instead of placeholder text)
    - None / False / 0 / "" / [] / {} stay as-is
    """
    if obj is None:
        return None
    if isinstance(obj, str):
        return None if obj == "N/A" else obj
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int, float)):
        return obj
    if isinstance(obj, dict):
        return {k: normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [normalize(i) for i in obj]
    try:
        return str(obj)
    except Exception:
        return None


def save_json(results: list) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    def result_name(r):
        if r.get("type") == "subreddit":
            return r.get("name", "sub")
        return r.get("username", "user")

    name = "_".join(result_name(r) for r in results)[:50]
    path = f"reddit_{name}_{ts}.json"

    # No more strip_empty — frontend sees every field, even when empty
    normalized = [normalize(r) for r in results]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(normalized if len(normalized) > 1 else normalized[0],
                  f, ensure_ascii=False, indent=2, default=str)
    return path


# ══════════════════════════════════════════════════════
#  SUBREDDIT ANALYSIS
# ══════════════════════════════════════════════════════

def fetch_subreddit(name: str) -> dict | None:
    data = rget(f"https://www.reddit.com/r/{name}/about.json")
    if not data: return None
    return data.get("data", {})


def fetch_subreddit_posts(name: str, sort: str = "hot", limit: int = 50) -> list:
    data = rget(f"https://www.reddit.com/r/{name}/{sort}.json",
                params={"limit": limit, "raw_json": 1})
    if not data: return []
    return [c.get("data", {}) for c in data.get("data", {}).get("children", [])]


def fetch_subreddit_mods(name: str) -> list:
    data = rget(f"https://www.reddit.com/r/{name}/about/moderators.json")
    if not data: return []
    return [
        {"username": m.get("name"), "mod_since": fts(m.get("date")),
         "permissions": m.get("mod_permissions", [])}
        for m in data.get("data", {}).get("children", [])
    ]


def analyze_subreddit_posts(posts: list) -> dict:
    if not posts: return {}

    authors    = Counter()
    flairs     = Counter()
    hour_c     = Counter()
    day_c      = Counter()
    days_en    = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    total_score= 0
    total_comm = 0
    domain_c   = Counter()

    for p in posts:
        if p.get("author") not in ("[deleted]", None):
            authors[p["author"]] += 1
        if p.get("link_flair_text"):
            flairs[p["link_flair_text"]] += 1
        ts = p.get("created_utc")
        if ts:
            dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            hour_c[dt.hour]     += 1
            day_c[dt.weekday()] += 1
        total_score += p.get("score", 0)
        total_comm  += p.get("num_comments", 0)
        domain = p.get("domain", "")
        if domain and not domain.startswith("self."):
            domain_c[domain] += 1

    best_hour = hour_c.most_common(1)[0][0] if hour_c else None
    best_day  = day_c.most_common(1)[0][0]  if day_c  else None

    top_posts = sorted(posts, key=lambda x: x.get("score", 0), reverse=True)[:5]

    return {
        "total_analyzed":    len(posts),
        "avg_score":         round(total_score / len(posts)) if posts else 0,
        "avg_comments":      round(total_comm  / len(posts)) if posts else 0,
        "top_authors":       [{"user": u, "posts": c}
                               for u, c in authors.most_common(10)],
        "top_flairs":        [{"flair": f, "count": c}
                               for f, c in flairs.most_common(8)],
        "top_domains":       [{"domain": d, "count": c}
                               for d, c in domain_c.most_common(8)],
        "hour_distribution": dict(sorted(hour_c.items())),
        "day_distribution":  dict(sorted(day_c.items())),
        "best_hour":         f"{best_hour:02d}:00" if best_hour is not None else "N/A",
        "best_day":          days_en[best_day] if best_day is not None else "N/A",
        "top_posts": [
            {"title":       p.get("title","")[:100],
             "author":      p.get("author",""),
             "score":       p.get("score", 0),
             "comments":    p.get("num_comments", 0),
             "flair":       p.get("link_flair_text",""),
             "url":         f"https://reddit.com{p.get('permalink','')}",
             "date":        fts(p.get("created_utc"))}
            for p in top_posts
        ],
    }


def full_analyze_subreddit(name: str, limit: int = 50) -> dict:
    result = {
        "type":        "subreddit",
        "name":        name,
        "url":         f"https://www.reddit.com/r/{name}",
        "scanned_at":  datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }

    about = fetch_subreddit(name)
    if not about:
        result["error"] = f"r/{name} not found or access blocked."
        return result

    result["about"] = {
        "display_name":      about.get("display_name"),
        "title":             about.get("title",""),
        "description":       (about.get("public_description") or "")[:300],
        "subscribers":       about.get("subscribers", 0),
        "active_users":      about.get("active_user_count", 0),
        "created_date":      fts(about.get("created_utc")),
        "age":               fage(about.get("created_utc")),
        "nsfw":              about.get("over18", False),
        "verified":          about.get("community_icon", "") != "",
        "type":              about.get("subreddit_type",""),
        "lang":              about.get("lang",""),
        "allow_images":      about.get("allow_images", True),
        "allow_videos":      about.get("allow_videos", True),
    }

    # Posts (hot + top)
    hot_posts = fetch_subreddit_posts(name, "hot",  limit)
    top_posts = fetch_subreddit_posts(name, "top",  min(limit, 25))
    new_posts = fetch_subreddit_posts(name, "new",  min(limit, 25))

    result["post_analysis"] = analyze_subreddit_posts(hot_posts + top_posts)

    # Moderators
    mods = fetch_subreddit_mods(name)
    if mods:
        result["moderators"] = mods

    # Engagement estimate
    subs   = result["about"]["subscribers"] or 0
    active = result["about"]["active_users"] or 0
    if subs > 0:
        ratio = round(active / subs * 100, 2)
        result["engagement"] = {
            "active_ratio_pct": ratio,
            "label": ("Very Active" if ratio > 1 else
                      "Active"      if ratio > 0.3 else
                      "Low Activity"),
        }

    return result


def print_subreddit(r: dict):
    c   = C
    ab  = r.get("about", {})
    pa  = r.get("post_analysis", {})
    mods= r.get("moderators", [])
    eng = r.get("engagement", {})

    c.print()
    c.print(Rule(f"[bold cyan]r/{r['name']}[/bold cyan]", style="cyan"))

    # Header
    hdr = Text()
    hdr.append(f"\n  r/{ab.get('display_name', r['name'])}\n", style="bold white")
    hdr.append(f"  {ab.get('title','')}\n", style="dim")
    if ab.get("description"):
        hdr.append(f"\n  {ab['description'][:200]}\n", style="italic dim")
    hdr.append(f"\n  {r['url']}", style="dim underline")
    flags = []
    if ab.get("nsfw"):             flags.append("[yellow]NSFW[/yellow]")
    if ab.get("type") == "private":flags.append("[red]Private[/red]")
    if flags: hdr.append(f"\n  {'  '.join(flags)}")
    c.print(Panel(hdr, title="[bold]Subreddit[/bold]",
                  border_style="cyan", padding=(0,2)))

    # Statistics
    st = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
               border_style="dim", min_width=60, padding=(0,2))
    st.add_column("Field", style="dim", width=22)
    st.add_column("Value", style="bold white", justify="right")
    st.add_column("",      style="dim", width=18)
    st.add_row("Subscribers",    fn(ab.get("subscribers",0)),   "")
    st.add_row("Active Now",     fn(ab.get("active_users",0)),  "")
    if eng:
        st.add_row("Active Ratio",   f"{eng['active_ratio_pct']}%",
                   eng.get("label",""))
    st.add_row("Created",        ab.get("created_date","?"),    ab.get("age",""))
    st.add_row("Language",       ab.get("lang","?"),            "")
    st.add_row("Type",           ab.get("type","?"),            "")
    st.add_row("Moderators",     str(len(mods)),                "")
    c.print(Panel(st, title="[bold]Statistics[/bold]", border_style="magenta"))

    # Post analysis
    if pa:
        c.print(Panel(
            Text.from_markup(
                f"  Posts analyzed      : [bold]{pa['total_analyzed']}[/bold]\n"
                f"  Average score       : [bold]{pa['avg_score']}[/bold]\n"
                f"  Average comments    : [bold]{pa['avg_comments']}[/bold]\n"
                f"  Peak hour           : [bold]{pa['best_hour']}[/bold]\n"
                f"  Peak day            : [bold]{pa['best_day']}[/bold]"
            ),
            title="[bold]Post Analysis[/bold]", border_style="yellow"
        ))

        # Top authors
        if pa.get("top_authors"):
            mx = pa["top_authors"][0]["posts"]
            at = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                       border_style="dim", padding=(0,1))
            at.add_column("User",      style="cyan", width=22)
            at.add_column("Posts",     justify="right", width=6)
            at.add_column("",          min_width=16)
            for a in pa["top_authors"][:10]:
                at.add_row(f"u/{a['user']}", str(a["posts"]),
                           f"[cyan]{ascii_bar(a['posts'], mx)}[/cyan]")
            c.print(Panel(at, title="[bold]Top Authors[/bold]",
                          border_style="green"))

        # Top flairs
        if pa.get("top_flairs"):
            ft = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                       border_style="dim", padding=(0,1))
            ft.add_column("Flair",  min_width=24)
            ft.add_column("Count",  justify="right", width=6)
            for fl in pa["top_flairs"]:
                ft.add_row(fl["flair"], str(fl["count"]))
            c.print(Panel(ft, title="[bold]Popular Flairs[/bold]",
                          border_style="blue"))

        # Top domains
        if pa.get("top_domains"):
            dt = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                       border_style="dim", padding=(0,1))
            dt.add_column("Domain", style="cyan", min_width=24)
            dt.add_column("Count",  justify="right", width=6)
            for d in pa["top_domains"]:
                dt.add_row(d["domain"], str(d["count"]))
            c.print(Panel(dt, title="[bold]Most Shared Domains[/bold]",
                          border_style="bright_cyan"))

        # Top posts
        if pa.get("top_posts"):
            tt = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                       border_style="dim", padding=(0,1))
            tt.add_column("Score",  justify="right", width=7)
            tt.add_column("Comm.",  justify="right", width=7)
            tt.add_column("Author", style="cyan",    width=16)
            tt.add_column("Date",   style="dim",     width=12)
            tt.add_column("Title",  min_width=28,    no_wrap=True)
            for p in pa["top_posts"]:
                tt.add_row(str(p["score"]), str(p["comments"]),
                           f"u/{p['author']}", p["date"],
                           p["title"][:50])
            c.print(Panel(tt, title="[bold]Top Posts[/bold]",
                          border_style="bright_magenta"))

    # Moderators
    if mods:
        mt = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
                   border_style="dim", padding=(0,1))
        mt.add_column("Moderator",    style="cyan", width=22)
        mt.add_column("Mod Since",    style="dim",  width=14)
        mt.add_column("Permissions",  style="dim")
        for m in mods[:10]:
            perms = ", ".join(m.get("permissions") or ["all"])
            mt.add_row(f"u/{m['username']}", m.get("mod_since","?"), perms)
        c.print(Panel(mt, title=f"[bold]Moderators ({len(mods)})[/bold]",
                      border_style="red"))

    c.print(Rule(style="dim"))
    c.print()


# ══════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description="Reddit OSINT Tool — SOCMIntelligence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python reddit_osint.py spez
  python reddit_osint.py @spez
  python reddit_osint.py u/spez
  python reddit_osint.py https://www.reddit.com/user/spez
  python reddit_osint.py r/OSINT
  python reddit_osint.py https://www.reddit.com/r/OSINT/
  python reddit_osint.py spez r/OSINT user2 r/netsec
  python reddit_osint.py spez --limit 200
  python reddit_osint.py spez --no-color
        """
    )
    ap.add_argument("targets",    nargs="+",
                    help="username, @username, u/username, r/subreddit, or full URL")
    ap.add_argument("--limit",    type=int, default=100, metavar="N",
                    help="Max items to fetch (default: 100)")
    ap.add_argument("--no-color", action="store_true", help="Disable colored output")
    args = ap.parse_args()

    use_rich = HAS_RICH and not args.no_color
    parsed   = list(dict.fromkeys(parse_target(t) for t in args.targets))
    limit    = min(max(args.limit, 10), 500)

    if use_rich:
        C.print()
        C.print(Rule("[bold cyan]Reddit OSINT — SOCMIntelligence[/bold cyan]", style="cyan"))
        C.print()
        for typ, name in parsed:
            prefix = "r/" if typ == "subreddit" else "u/"
            C.print(f"  [dim]Target >[/dim] [cyan]{prefix}{name}[/cyan]")
        C.print()

    results = []

    def run_one(typ_name):
        typ, name = typ_name
        prefix = "r/" if typ == "subreddit" else "u/"
        if use_rich:
            C.print(f"  [dim]Scanning >[/dim] [cyan]{prefix}{name}[/cyan]")
        if typ == "subreddit":
            return full_analyze_subreddit(name, limit)
        else:
            return full_analyze(name, limit)

    with ThreadPoolExecutor(max_workers=min(len(parsed), 2)) as ex:
        futs = {ex.submit(run_one, t): t for t in parsed}
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as e:
                typ, name = futs[fut]
                prefix = "r/" if typ == "subreddit" else "u/"
                if use_rich: C.print(f"  [red][!] {prefix}{name}: {e}[/red]")
                else:        print(f"[!] {prefix}{name}: {e}")

    order = {(t, n): i for i, (t, n) in enumerate(parsed)}
    def sort_key(r):
        if r.get("type") == "subreddit":
            return order.get(("subreddit", r.get("name","")), 99)
        return order.get(("user", r.get("username","")), 99)
    results.sort(key=sort_key)

    if not results:
        sys.exit("[!] No results retrieved.")

    if use_rich: C.print()

    for r in results:
        if r.get("error"):
            label = f"r/{r.get('name','?')}" if r.get("type") == "subreddit" \
                    else f"u/{r.get('username','?')}"
            if use_rich:
                C.print(Panel(f"  [red]{r['error']}[/red]",
                              title=f"[bold]{label}[/bold]",
                              border_style="red"))
            else:
                print(f"[!] {label}: {r['error']}")
            continue

        if r.get("type") == "subreddit":
            if use_rich: print_subreddit(r)
            else:
                s = r.get("about",{})
                print(f"r/{r['name']}  —  {fn(s.get('subscribers',0))} subs  "
                      f"{fn(s.get('active_users',0))} active")
        else:
            if use_rich: print_profile(r)
            else:        print_plain(r)

    fname = save_json(results)
    if use_rich:
        C.print(Padding(f"[green]✔ JSON saved:[/green] [bold]{fname}[/bold]",
                        pad=(0,0,1,2)))
    else:
        print(f"\n[✔] JSON saved: {fname}")


if __name__ == "__main__":
    main()
