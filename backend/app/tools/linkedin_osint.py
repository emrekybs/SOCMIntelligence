#!/usr/bin/env python3
"""
LinkedIn OSINT — herkese acik profil sayfasi + Wayback Machine arsiv kopyalari.

Oturum / cerez / sifre KULLANMAZ. Iki kaynak okunur:
  1) linkedin.com/in/<slug> sayfasinin oturumsuz (herkese acik) hali — LinkedIn cogu zaman
     giris duvari (authwall / HTTP 999) dondurur; o durumda sadece durum raporlanir.
  2) Ayni sayfanin Wayback Machine kopyalari — eski unvan / sirket / konum degisimleri buradan cikar.

Iki kaynakta da sayfanin JSON-LD (schema.org Person) blogu ve meta etiketleri ayristirilir.

  python linkedin_osint.py https://www.linkedin.com/in/kullanici
  python linkedin_osint.py kullanici --snapshots 4
"""
from __future__ import annotations

import argparse
import html as htmllib
import json
import re
from urllib.parse import unquote

from bs4 import BeautifulSoup

import _toolkit as tk

CDX = "https://web.archive.org/cdx/search/cdx"
SLUG_RE = re.compile(r"^[A-Za-z0-9\-_%.]{2,100}$")
AUTHWALL_MARKERS = ("authwall", "/login", "/checkpoint", "/uas/login", "signup/cold-join")


# ─── Girdi ────────────────────────────────────────────────────────
def normalize(raw: str) -> str | None:
    t = (raw or "").strip()
    if not t:
        return None
    m = re.search(r"linkedin\.com/(?:mwlite/)?in/([^/?#\s]+)", t, re.I)
    if m:
        t = m.group(1)
    elif "/" in t or " " in t:
        return None
    t = unquote(t).strip().strip("/").lstrip("@")
    return t if SLUG_RE.match(t) else None


# ─── Ayristirma ───────────────────────────────────────────────────
def _first(v):
    if isinstance(v, list):
        return v[0] if v else None
    return v


def _str(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        v = ", ".join(str(x) for x in v if x)
    s = htmllib.unescape(str(v)).strip()
    return s or None


def _ld_blocks(soup: BeautifulSoup) -> list[dict]:
    out = []
    for sc in soup.find_all("script", type="application/ld+json"):
        raw = sc.string or sc.get_text() or ""
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if not isinstance(it, dict):
                continue
            if isinstance(it.get("@graph"), list):
                out.extend(x for x in it["@graph"] if isinstance(x, dict))
            else:
                out.append(it)
    return out


def _types(it: dict) -> set[str]:
    t = it.get("@type")
    return set(t) if isinstance(t, list) else {t} if t else set()


def _org(o: dict) -> dict:
    mem = o.get("member") if isinstance(o.get("member"), dict) else {}
    loc = o.get("location")
    if isinstance(loc, dict):
        loc = loc.get("name") or loc.get("addressLocality")
    return {k: v for k, v in {
        "name": _str(o.get("name")),
        "url": _str(o.get("url") or o.get("sameAs")),
        "location": _str(loc),
        "start": _str(mem.get("startDate")),
        "end": _str(mem.get("endDate")),
        "description": _str(mem.get("description") or o.get("description")),
        "role": _str(mem.get("roleName") or mem.get("name")),
    }.items() if v}


def _count(text: str, words: str) -> str | None:
    m = re.search(r"(\d[\d.,]*\+?)\s*(?:" + words + r")", text or "", re.I)
    return m.group(1) if m else None


def parse_profile(html: str) -> dict | None:
    """Profil HTML'inden JSON-LD Person + meta bilgisi. Profil yoksa None."""
    soup = BeautifulSoup(html, "lxml")
    blocks = _ld_blocks(soup)
    person = next((b for b in blocks if "Person" in _types(b)), None)

    def meta(*names):
        for n in names:
            m = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
            if m and m.get("content"):
                return _str(m["content"])
        return None

    og_title = meta("og:title", "twitter:title")
    og_desc = meta("og:description", "description", "twitter:description")
    og_image = meta("og:image", "twitter:image")
    title = _str(soup.title.get_text(" ", strip=True)) if soup.title else None
    if not person and not (og_title and "linkedin" in (title or og_title or "").lower() and " | " in (title or og_title)):
        return None

    p = person or {}
    addr = p.get("address") if isinstance(p.get("address"), dict) else {}
    img = p.get("image")
    img = img.get("contentUrl") if isinstance(img, dict) else img
    works = [_org(o) for o in (p.get("worksFor") or []) if isinstance(o, dict)]
    past_jobs, education = [], []
    for o in p.get("alumniOf") or []:
        if not isinstance(o, dict):
            continue
        (education if "EducationalOrganization" in _types(o) else past_jobs).append(_org(o))
    langs = [_str(x.get("name") if isinstance(x, dict) else x) for x in (p.get("knowsLanguage") or [])]
    followers = None
    stats = p.get("interactionStatistic")
    for st in stats if isinstance(stats, list) else [stats] if stats else []:
        if isinstance(st, dict) and "follow" in str(st.get("name") or st.get("interactionType") or "").lower():
            followers = st.get("userInteractionCount")
    articles = []
    for b in blocks:
        if _types(b) & {"Article", "SocialMediaPosting", "DiscussionForumPosting", "BlogPosting"} and b.get("headline"):
            au = b.get("author")
            au = _first(au)
            articles.append({k: v for k, v in {
                "title": _str(b.get("headline")), "url": _str(b.get("url") or b.get("mainEntityOfPage")),
                "date": _str(b.get("datePublished")), "author": _str(au.get("name") if isinstance(au, dict) else au),
            }.items() if v})

    # og:title: "Ad Soyad - Unvan - Sirket | LinkedIn"
    name_from_title = None
    if og_title:
        name_from_title = re.split(r"\s+[-–|]\s+", og_title)[0].strip() or None

    about = _str(p.get("description"))
    text_blob = " ".join(x for x in (about, og_desc) if x)
    return {
        "name": _str(p.get("name")) or name_from_title,
        "headline": _str(p.get("jobTitle")) or _headline_from_title(og_title),
        "about": about,
        "meta_description": og_desc,
        "location": _str(addr.get("addressLocality")),
        "country": _str(addr.get("addressCountry")),
        "image": _str(img) or og_image,
        "profile_url": _str(p.get("url") or p.get("sameAs")),
        "followers": followers if followers is not None else _count(og_desc, "followers|takipçi"),
        "connections": _count(og_desc, "connections|bağlantı"),
        "current": works,
        "past": past_jobs,
        "education": education,
        "languages": [x for x in langs if x],
        "awards": [_str(a) for a in (p.get("awards") or []) if _str(a)],
        "member_of": [_org(o) for o in (p.get("memberOf") or []) if isinstance(o, dict)],
        "articles": articles[:40],
        "emails": tk.find_emails(text_blob),
        "socials": [s for s in tk.find_socials(text_blob) if s["platform"] != "linkedin"],
        "urls": [u for u in tk.find_urls(text_blob) if "linkedin.com" not in u][:20],
        "title": title or og_title,
        "has_jsonld": bool(person),
    }


def _headline_from_title(t: str | None) -> str | None:
    if not t:
        return None
    t = re.sub(r"\s*\|\s*LinkedIn\s*$", "", t, flags=re.I)
    parts = re.split(r"\s+[-–]\s+", t)
    return " - ".join(parts[1:]) or None if len(parts) > 1 else None


# ─── Kaynaklar ────────────────────────────────────────────────────
def fetch_live(slug: str) -> dict:
    url = f"https://www.linkedin.com/in/{slug}/"
    out = {"source": "live", "url": url}
    try:
        r = tk.get(url, headers={"Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.9"},
                   retries=1, allow=(403, 404, 410, 429, 451, 999))
    except tk.HttpError as e:
        out.update(status="error", detail=str(e))
        return out
    final = r.url or url
    chain = [h.url for h in r.history] + [final]
    out["http"] = r.status_code
    if r.status_code in (404, 410):
        out["status"] = "not_found"
        return out
    if r.status_code in (999, 403, 429, 451) or any(m in u for u in chain for m in AUTHWALL_MARKERS):
        out["status"] = "blocked"
        return out
    try:
        prof = parse_profile(r.text[:3_000_000])
    except Exception as e:  # noqa: BLE001 - beklenmedik sayfa yapisi taramayi durdurmasin
        out.update(status="error", detail=f"parse: {e}")
        return out
    if not prof:
        out["status"] = "blocked" if "authwall" in r.text[:200_000].lower() else "empty"
        return out
    out.update(status="ok", profile=prof)
    return out


def _cdx(**params) -> list[list]:
    params["output"] = "json"
    data = tk.get_json(CDX, params=params) or []
    return data[1:] if data and isinstance(data[0], list) and data[0][:1] == ["timestamp"] else data


def _d(ts: str) -> str:
    return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}" if ts and len(ts) >= 8 else ts


def archive_rows(slug: str) -> list[list]:
    rows, seen = [], set()
    for host in ("linkedin.com", "tr.linkedin.com"):
        try:
            got = _cdx(url=f"{host}/in/{slug}", fl="timestamp,original,statuscode,digest",
                       filter="statuscode:200", collapse="digest", limit=2000)
        except tk.HttpError as e:
            if e.status in (429, 503):
                raise
            if e.status == 0 and host == "linkedin.com":
                raise
            continue
        for r in got:
            if r[0] not in seen:
                seen.add(r[0])
                rows.append(r)
    return sorted(rows, key=lambda r: r[0])


def fetch_snapshot(ts: str, original: str) -> dict:
    out = {"source": "wayback", "timestamp": ts, "date": _d(ts),
           "archive_url": f"https://web.archive.org/web/{ts}/{original}"}
    try:
        r = tk.get(f"https://web.archive.org/web/{ts}id_/{original}", allow=(403, 404))
    except tk.HttpError as e:
        out.update(status="error", detail=str(e))
        return out
    if r.status_code != 200:
        out.update(status="error", detail=f"HTTP {r.status_code}")
        return out
    try:
        prof = parse_profile(r.text[:3_000_000])
    except Exception as e:  # noqa: BLE001 - bozuk / beklenmedik arsiv HTML'i taramayi durdurmasin
        out.update(status="error", detail=f"parse: {e}")
        return out
    if prof:
        out.update(status="ok", profile=prof)
    else:
        out["status"] = "empty"
    return out


def pick(rows: list[list], n: int) -> list[list]:
    """En yeni kopyalar once, en eski kopya da dahil (degisim takibi icin)."""
    if not rows:
        return []
    idx = list(range(len(rows) - 1, -1, -1))
    chosen = idx[: max(1, n - 1)]
    if 0 not in chosen:
        chosen.append(0)
    return [rows[i] for i in sorted(set(chosen))]


# ─── Birlestirme ──────────────────────────────────────────────────
def _company(p: dict) -> str | None:
    cur = p.get("current") or []
    return ", ".join(c["name"] for c in cur if c.get("name")) or None


def history_of(sources: list[dict]) -> tuple[list[dict], list[dict]]:
    hist, changes = [], []
    fields = (("headline", "Unvan"), ("company", "Şirket"), ("location", "Konum"), ("name", "Ad"))
    prev = None
    for s in sources:
        p = s.get("profile") or {}
        row = {"date": s.get("date") or "canlı", "source": s["source"], "url": s.get("archive_url") or s.get("url"),
               "name": p.get("name"), "headline": p.get("headline"), "company": _company(p),
               "location": p.get("location"), "followers": p.get("followers")}
        hist.append(row)
        if prev:
            for key, label in fields:
                a, b = prev.get(key), row.get(key)
                if a and b and a != b:
                    changes.append({"field": label, "from": a, "to": b, "from_date": prev["date"], "to_date": row["date"]})
        prev = row
    return hist, changes


def merge_list(sources: list[dict], key: str, ident=lambda x: (x.get("name") or "").lower()) -> list[dict]:
    out, seen = [], {}
    for s in reversed(sources):  # en yeni once
        for it in (s.get("profile") or {}).get(key) or []:
            k = ident(it) if isinstance(it, dict) else str(it).lower()
            if not k:
                continue
            if k in seen:
                continue
            seen[k] = True
            item = dict(it) if isinstance(it, dict) else it
            if isinstance(item, dict):
                item["seen"] = s.get("date") or "canlı"
            out.append(item)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="LinkedIn OSINT (oturumsuz: herkese acik sayfa + Wayback)")
    ap.add_argument("target")
    ap.add_argument("--snapshots", type=int, default=4, help="Okunacak arsiv kopyasi sayisi")
    ap.add_argument("--no-live", action="store_true", help="linkedin.com'a hic istek atma, sadece arsiv")
    args = ap.parse_args()

    slug = normalize(args.target)
    if not slug:
        tk.fail("error", f"Gecersiz LinkedIn profil adresi: {args.target}")
    url = f"https://www.linkedin.com/in/{slug}"

    live = {"source": "live", "status": "skipped", "url": url} if args.no_live else fetch_live(slug)

    rows, arch_err = [], None
    try:
        rows = archive_rows(slug)
    except tk.HttpError as e:
        arch_err = f"Wayback CDX: {e}"
    snaps = [fetch_snapshot(r[0], r[1]) for r in pick(rows, args.snapshots)]
    ok_snaps = [s for s in snaps if s.get("status") == "ok"]

    ordered = ok_snaps + ([live] if live.get("status") == "ok" else [])
    if not ordered:
        if live.get("status") == "not_found" and not rows:
            tk.fail("not_found", f"LinkedIn profili bulunamadi: {slug}")
        if live.get("status") == "error" and arch_err:
            tk.fail("error", "LinkedIn ve Wayback Machine'e erisilemedi (ag / proxy)")
        if arch_err and "HTTP 0" not in arch_err:
            tk.fail("rate_limited", arch_err)
        if live.get("status") == "error":
            tk.fail("error", "LinkedIn'e erisilemedi ve Wayback Machine'de okunabilir kopya yok")
        tk.fail("private", "LinkedIn giris duvari dondurdu ve Wayback Machine'de okunabilir kopya yok"
                if live.get("status") in ("blocked", "empty") else
                f"LinkedIn profili icin okunabilir kaynak yok: {slug}")

    best = ordered[-1]
    bp = best["profile"]
    hist, changes = history_of(ordered)

    emails, socials, urls, seen_s = [], [], [], set()
    for s in ordered:
        p = s["profile"]
        for e in p.get("emails") or []:
            if e not in emails:
                emails.append(e)
        for so in p.get("socials") or []:
            k = (so["platform"], so["handle"].lower())
            if k not in seen_s:
                seen_s.add(k)
                socials.append({**so, "first_seen": s.get("date") or "canlı"})
        for u in p.get("urls") or []:
            if u not in urls:
                urls.append(u)

    tk.emit({
        "input": args.target, "slug": slug, "url": url,
        "source_used": "live" if best is live else "wayback",
        "source_date": best.get("date") or "canlı",
        "live_status": live.get("status"), "live_http": live.get("http"),
        "name": bp.get("name"), "headline": bp.get("headline"), "about": bp.get("about"),
        "location": bp.get("location"), "country": bp.get("country"), "image": bp.get("image"),
        "followers": bp.get("followers"), "connections": bp.get("connections"),
        "current": bp.get("current") or [],
        "experience": merge_list(ordered, "past"),
        "education": merge_list(ordered, "education"),
        "languages": list(dict.fromkeys(l for s in ordered for l in (s["profile"].get("languages") or []))),
        "awards": list(dict.fromkeys(a for s in ordered for a in (s["profile"].get("awards") or []))),
        "member_of": merge_list(ordered, "member_of"),
        "articles": merge_list(ordered, "articles", ident=lambda x: (x.get("url") or x.get("title") or "").lower())[:40],
        "emails": emails, "socials": socials, "urls": urls,
        "history": hist, "changes": changes,
        "archive": {
            "total_versions": len(rows),
            "first": _d(rows[0][0]) if rows else None, "last": _d(rows[-1][0]) if rows else None,
            "error": arch_err,
            "years": {y: sum(1 for r in rows if r[0][:4] == y) for y in sorted({r[0][:4] for r in rows})},
            "snapshots": [{k: v for k, v in s.items() if k != "profile"} | {"parsed": s.get("status") == "ok"} for s in snaps],
        },
    })


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except tk.HttpError as e:
        tk.fail("rate_limited" if e.status in (429, 503) else "error", f"LinkedIn: {e}")
    except Exception as e:  # noqa: BLE001 - araç asla traceback'le çökmesin; adapter JSON bekliyor
        tk.fail("error", f"LinkedIn aracı beklenmedik hata: {e}")
