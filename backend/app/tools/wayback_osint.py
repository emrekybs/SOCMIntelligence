#!/usr/bin/env python3
"""
Wayback Machine OSINT — bir URL / alan adi / profil sayfasinin arsiv gecmisi.
Ilk, orta ve son arsiv kopyasindan e-posta, sosyal hesap ve dis baglantilar cikarilir
(silinmis profiller ve degismis bio'lar icin).

  python wayback_osint.py example.com
  python wayback_osint.py https://twitter.com/jack
"""
from __future__ import annotations

import argparse
import re
from collections import Counter

from bs4 import BeautifulSoup

import _toolkit as tk

CDX = "https://web.archive.org/cdx/search/cdx"


def normalize(raw: str) -> tuple[str, bool] | None:
    t = (raw or "").strip()
    if not t or " " in t:
        return None
    t = re.sub(r"^https?://", "", t, flags=re.I).rstrip("/")
    if not re.match(r"^[A-Za-z0-9.\-]+\.[A-Za-z]{2,}(?::\d+)?(/.*)?$", t):
        return None
    is_domain = "/" not in t
    return t, is_domain


def cdx(**params) -> list[list]:
    params["output"] = "json"
    data = tk.get_json(CDX, params=params) or []
    return data[1:] if data and isinstance(data[0], list) and data[0] and data[0][0] in ("timestamp", "original", "urlkey") else data


def snapshot_info(ts: str, original: str) -> dict:
    url = f"https://web.archive.org/web/{ts}id_/{original}"
    out = {"timestamp": ts, "date": _d(ts), "archive_url": f"https://web.archive.org/web/{ts}/{original}"}
    try:
        r = tk.get(url, allow=(404, 403))
    except tk.HttpError as e:
        out["error"] = str(e)
        return out
    if r.status_code != 200 or "html" not in (r.headers.get("content-type") or "html"):
        out["error"] = f"HTTP {r.status_code}"
        return out
    html = r.text[:2_000_000]
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else None
    desc = None
    for sel in ('meta[name="description"]', 'meta[property="og:description"]'):
        m = soup.select_one(sel)
        if m and m.get("content"):
            desc = m["content"].strip()
            break
    text = soup.get_text(" ", strip=True)
    links = []
    for a in soup.find_all("a", href=True):
        h = re.sub(r"^https?://web\.archive\.org/web/\d+[a-z_]*/", "", a["href"].strip())
        if h.startswith("http") and h not in links:
            links.append(h)
    mailto = [a["href"][7:].split("?")[0].lower() for a in soup.find_all("a", href=True) if a["href"].lower().startswith("mailto:")]
    own = tk.domain_of(original)
    doms = Counter(d for d in (tk.domain_of(l) for l in links) if d and d != own and "archive.org" not in d)
    out.update({
        "title": title, "description": desc,
        "emails": list(dict.fromkeys(mailto + tk.find_emails(text)))[:30],
        "socials": tk.find_socials(" ".join(links))[:40],
        "domains": dict(doms.most_common(20)),
    })
    return out


def _d(ts: str) -> str:
    return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}" if ts and len(ts) >= 8 else ts


def main() -> None:
    ap = argparse.ArgumentParser(description="Wayback Machine OSINT")
    ap.add_argument("target")
    ap.add_argument("--snapshots", type=int, default=3, help="Icerigi okunacak arsiv kopyasi sayisi (ilk/orta/son)")
    args = ap.parse_args()
    n = normalize(args.target)
    if not n:
        tk.fail("not_found", f"Gecersiz URL / alan adi: {args.target}")
    target, is_domain = n

    try:
        rows = cdx(url=target, fl="timestamp,original,statuscode,mimetype,digest", collapse="timestamp:8", limit=5000)
        urls = []
        if is_domain:
            urls = cdx(url=f"{target}/*", fl="original,timestamp,statuscode", collapse="urlkey", limit=400)
    except tk.HttpError as e:
        tk.fail("rate_limited" if e.status in (429, 503) else "error", f"Wayback CDX: {e}")

    if not rows and not urls:
        tk.fail("not_found", f"Wayback Machine'de arsiv kaydi yok: {target}")

    years, status, mimes, digests = Counter(), Counter(), Counter(), set()
    for r in rows:
        ts, orig, st, mt, dg = (r + [None] * 5)[:5]
        years[ts[:4]] += 1
        status[st or "-"] += 1
        mimes[mt or "-"] += 1
        if dg:
            digests.add(dg)
    ok_html = [r for r in rows if (r[2] or "").startswith("2") and "html" in (r[3] or "")]
    picks = []
    if ok_html:
        idx = sorted({0, len(ok_html) // 2, len(ok_html) - 1})[: max(1, args.snapshots)]
        picks = [ok_html[i] for i in idx]
    snaps = [snapshot_info(p[0], p[1]) for p in picks]

    emails, socials, seen = [], [], set()
    for s in snaps:
        for e in s.get("emails") or []:
            if e not in emails:
                emails.append(e)
        for so in s.get("socials") or []:
            k = (so["platform"], so["handle"].lower())
            if k not in seen:
                seen.add(k)
                socials.append({**so, "first_seen": s["date"]})

    tk.emit({
        "input": args.target, "target": target, "is_domain": is_domain,
        "total_captures": len(rows), "unique_versions": len(digests),
        "first_capture": _d(rows[0][0]) if rows else None, "last_capture": _d(rows[-1][0]) if rows else None,
        "first_capture_url": f"https://web.archive.org/web/{rows[0][0]}/{rows[0][1]}" if rows else None,
        "last_capture_url": f"https://web.archive.org/web/{rows[-1][0]}/{rows[-1][1]}" if rows else None,
        "last_status": rows[-1][2] if rows else None,
        "years": dict(sorted(years.items())), "status_codes": dict(status.most_common()), "mime_types": dict(mimes.most_common(8)),
        "captures": [{"timestamp": r[0], "date": _d(r[0]), "status": r[2], "mime": r[3],
                      "archive_url": f"https://web.archive.org/web/{r[0]}/{r[1]}"} for r in rows[-60:]][::-1],
        "urls": [{"url": u[0], "first": _d(u[1]) if len(u) > 1 else None, "status": u[2] if len(u) > 2 else None} for u in urls],
        "snapshots": snaps, "emails": emails, "socials": socials,
    })


if __name__ == "__main__":
    main()
