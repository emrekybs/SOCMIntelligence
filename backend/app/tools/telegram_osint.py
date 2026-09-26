#!/usr/bin/env python3
"""
Telegram OSINT — herkese acik kanal / grup / kullanici sayfalari (API anahtari gerekmez).

Kaynaklar:
  https://t.me/<ad>        profil karti (baslik, aciklama, abone/uye sayisi, foto)
  https://t.me/s/<ad>      herkese acik kanal onizlemesi (son gonderiler)

Kullanim:
  python telegram_osint.py durov
  python telegram_osint.py https://t.me/s/telegram --pages 5
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from urllib.parse import unquote

from bs4 import BeautifulSoup

import _toolkit as tk

USER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")


def parse_target(raw: str) -> str | None:
    t = (raw or "").strip().rstrip("/")
    m = re.search(r"(?:t\.me|telegram\.me|telegram\.dog)/(?:s/)?([A-Za-z0-9_]{4,32})", t, re.I)
    if m:
        return m.group(1)
    t = t.lstrip("@")
    return t if USER_RE.match(t) else None


def num(txt: str | None) -> int | None:
    """'12.3K' / '1 234' / '1,2M' -> int"""
    if not txt:
        return None
    s = txt.strip().upper().replace(" ", " ")
    m = re.match(r"^([\d.,\s]+)\s*([KMB])?", s)
    if not m:
        return None
    n, suf = m.group(1).replace(" ", ""), m.group(2)
    if suf:
        n = n.replace(",", ".")
        try:
            return int(float(n) * {"K": 1e3, "M": 1e6, "B": 1e9}[suf])
        except ValueError:
            return None
    n = n.replace(",", "").replace(".", "")
    return int(n) if n.isdigit() else None


def text_of(el) -> str:
    return el.get_text(" ", strip=True) if el else ""


def parse_card(html: str, username: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    title_el = soup.select_one(".tgme_page_title")
    if not title_el:
        return None
    extra = text_of(soup.select_one(".tgme_page_extra"))
    desc_el = soup.select_one(".tgme_page_description")
    photo = soup.select_one(".tgme_page_photo_image")
    kind = "user"
    low = extra.lower()
    if re.search(r"subscriber|abone", low):
        kind = "channel"
    elif re.search(r"member|üye|online", low):
        kind = "group"
    elif username.lower().endswith("bot"):
        kind = "bot"
    members = None
    m = re.search(r"([\d][\d\s.,]*[KMB]?)\s*(subscribers?|members?)", extra, re.I)
    if m:
        members = num(m.group(1))
    online = None
    m = re.search(r"([\d][\d\s.,]*)\s*online", extra, re.I)
    if m:
        online = num(m.group(1))
    desc_html = str(desc_el) if desc_el else ""
    return {
        "title": text_of(title_el),
        "extra": extra,
        "kind": kind,
        "members": members,
        "online": online,
        "description": desc_el.get_text("\n", strip=True) if desc_el else "",
        "description_links": tk.links_from_html(desc_html),
        "photo": photo.get("src") if photo and photo.name == "img" else (photo.select_one("img").get("src") if photo and photo.select_one("img") else None),
        "verified": bool(soup.select_one(".tgme_page_title .verified-icon")),
        "has_preview": bool(soup.select_one(f'a[href="/s/{username}"]')) or kind == "channel",
    }


def parse_posts(html: str, username: str) -> tuple[list[dict], dict]:
    soup = BeautifulSoup(html, "lxml")
    counters = {}
    for c in soup.select(".tgme_channel_info_counter"):
        val, typ = text_of(c.select_one(".counter_value")), text_of(c.select_one(".counter_type"))
        if typ:
            counters[typ.lower()] = num(val)
    posts = []
    for msg in soup.select(".tgme_widget_message[data-post]"):
        data_post = msg.get("data-post", "")
        try:
            pid = int(data_post.split("/")[-1])
        except ValueError:
            continue
        text_el = msg.select_one(".tgme_widget_message_text")
        text = text_el.get_text("\n", strip=True) if text_el else ""
        t_el = msg.select_one(".tgme_widget_message_date time[datetime]")
        fwd_el = msg.select_one(".tgme_widget_message_forwarded_from_name")
        fwd = None
        if fwd_el:
            href = fwd_el.get("href") or ""
            m = re.search(r"t\.me/([A-Za-z0-9_]{4,32})", href)
            fwd = {"name": text_of(fwd_el), "url": href or None, "username": m.group(1) if m else None}
        links, hashtags, mentions = [], [], []
        if text_el:
            for a in text_el.find_all("a", href=True):
                h = a["href"]
                if h.startswith("?q=%23") or h.startswith("?q=#"):
                    tag = unquote(h.split("q=", 1)[1]).lstrip("#")
                    if tag:
                        hashtags.append(tag)
                elif h.startswith("http"):
                    m = re.match(r"https?://(?:t\.me|telegram\.me)/(?!s/|joinchat|\+)([A-Za-z0-9_]{4,32})/?$", h)
                    if m:
                        mentions.append(m.group(1))
                    else:
                        links.append(h)
        for m in re.finditer(r"(?<![\w@])@([A-Za-z][A-Za-z0-9_]{3,31})\b", text):
            mentions.append(m.group(1))
        media = []
        if msg.select_one(".tgme_widget_message_photo_wrap"):
            media.append("photo")
        if msg.select_one(".tgme_widget_message_video_player, .tgme_widget_message_roundvideo_player"):
            media.append("video")
        if msg.select_one(".tgme_widget_message_document"):
            media.append("document")
        if msg.select_one(".tgme_widget_message_poll"):
            media.append("poll")
        posts.append({
            "id": pid,
            "url": f"https://t.me/{data_post}",
            "date": t_el.get("datetime") if t_el else None,
            "text": text[:600],
            "views": num(text_of(msg.select_one(".tgme_widget_message_views"))),
            "author": text_of(msg.select_one(".tgme_widget_message_from_author")) or None,
            "forwarded_from": fwd,
            "links": list(dict.fromkeys(links)),
            "hashtags": list(dict.fromkeys(hashtags)),
            "mentions": [x for x in dict.fromkeys(mentions) if x.lower() != username.lower()],
            "media": media,
        })
    return posts, counters


def analyze(posts: list[dict]) -> dict:
    if not posts:
        return {"posts_analyzed": 0}
    dist = tk.distributions([p["date"] for p in posts])
    views = [p["views"] for p in posts if p.get("views") is not None]
    tags, ments, fwd, doms, authors, media = Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
    for p in posts:
        tags.update(t.lower() for t in p["hashtags"])
        ments.update(p["mentions"])
        if p.get("forwarded_from"):
            f = p["forwarded_from"]
            fwd[f.get("username") or f.get("name") or "?"] += 1
        for l in p["links"]:
            d = tk.domain_of(l)
            if d:
                doms[d] += 1
        if p.get("author"):
            authors[p["author"]] += 1
        media.update(p["media"] or ["text"])
    span_days = None
    f, l = tk.to_dt(dist["first"]), tk.to_dt(dist["last"])
    if f and l:
        span_days = max((l - f).total_seconds() / 86400, 1)
    return {
        "posts_analyzed": len(posts),
        "first_post": dist["first"], "last_post": dist["last"],
        "hour_distribution": dist["hour_distribution"], "day_distribution": dist["day_distribution"],
        "posts_per_day": round(len(posts) / span_days, 2) if span_days else None,
        "avg_views": round(sum(views) / len(views)) if views else None,
        "max_views": max(views) if views else None,
        "top_hashtags": dict(tags.most_common(20)),
        "top_mentions": dict(ments.most_common(20)),
        "top_forward_sources": dict(fwd.most_common(15)),
        "top_domains": dict(doms.most_common(15)),
        "signed_authors": dict(authors.most_common(10)),
        "media": dict(media),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Telegram OSINT")
    ap.add_argument("target")
    ap.add_argument("--pages", type=int, default=3, help="Kanal onizlemesinden kac sayfa (sayfa ~20 gonderi)")
    args = ap.parse_args()

    username = parse_target(args.target)
    if not username:
        tk.fail("not_found", f"Gecersiz Telegram kullanici adi: {args.target}")

    try:
        r = tk.get(f"https://t.me/{username}", allow=(404,))
    except tk.HttpError as e:
        tk.fail("rate_limited" if e.status == 429 else "error", f"t.me erisilemedi: {e}")
    card = parse_card(r.text, username) if r.status_code == 200 else None
    if not card:
        tk.fail("not_found", f"Telegram hesabi bulunamadi: @{username}")

    posts, counters = [], {}
    if card["kind"] in ("channel", "group") or card["has_preview"]:
        before = None
        for _ in range(max(1, min(args.pages, 15))):
            try:
                rr = tk.get(f"https://t.me/s/{username}", params={"before": before} if before else None, allow=(302, 404))
            except tk.HttpError as e:
                tk.log(f"onizleme alinamadi: {e}")
                break
            if rr.status_code != 200 or "tgme_channel_history" not in rr.text:
                break
            page, cnt = parse_posts(rr.text, username)
            counters = counters or cnt
            new = [p for p in page if p["id"] not in {x["id"] for x in posts}]
            if not new:
                break
            posts.extend(new)
            before = min(p["id"] for p in new)
            if before <= 1:
                break
    posts.sort(key=lambda p: p["id"], reverse=True)

    desc = card["description"]
    tk.emit({
        "username": username,
        "url": f"https://t.me/{username}",
        "kind": card["kind"],
        "title": card["title"],
        "description": desc,
        "photo": card["photo"],
        "verified": card["verified"],
        "extra": card["extra"],
        "subscribers": card["members"] if card["members"] is not None else counters.get("subscribers"),
        "online": card["online"],
        "counters": counters,
        "description_links": card["description_links"],
        "description_emails": tk.find_emails(desc),
        "description_socials": tk.find_socials(desc + " " + " ".join(card["description_links"])),
        "description_mentions": [m for m in re.findall(r"@([A-Za-z][A-Za-z0-9_]{3,31})", desc) if m.lower() != username.lower()],
        "public_preview": bool(posts),
        "posts": posts,
        "analysis": analyze(posts),
    })


if __name__ == "__main__":
    main()
