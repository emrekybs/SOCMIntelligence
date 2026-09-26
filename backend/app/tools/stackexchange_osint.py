#!/usr/bin/env python3
"""
Stack Exchange OSINT — profil, ag genelindeki hesaplar, etiketler, yanit verilen kullanicilar.

  python stackexchange_osint.py https://stackoverflow.com/users/22656/jon-skeet
  python stackexchange_osint.py 22656                 (--site stackoverflow)
  python stackexchange_osint.py superuser:12345
  python stackexchange_osint.py "Jon Skeet"           (ada gore arama, en yuksek itibarli)

STACKEXCHANGE_KEY opsiyonel (gunluk kota 300 -> 10.000).
"""
from __future__ import annotations

import argparse
import os
import re
from collections import Counter

import _toolkit as tk

API = "https://api.stackexchange.com/2.3"
KEY = os.environ.get("STACKEXCHANGE_KEY", "").strip()
SITE_MAP = {"stackoverflow.com": "stackoverflow", "superuser.com": "superuser", "serverfault.com": "serverfault",
            "askubuntu.com": "askubuntu", "mathoverflow.net": "mathoverflow.net", "stackapps.com": "stackapps"}
_quota = {"remaining": None}


def site_from_host(host: str) -> str:
    host = host.lower().replace("www.", "")
    if host in SITE_MAP:
        return SITE_MAP[host]
    if host.endswith(".stackexchange.com"):
        return host.split(".stackexchange.com")[0]
    return host.split(".")[0]


def parse_target(raw: str, default_site: str):
    t = (raw or "").strip()
    m = re.search(r"https?://([A-Za-z0-9.\-]+)/users/(-?\d+)", t)
    if m:
        return site_from_host(m.group(1)), "id", m.group(2)
    m = re.match(r"^([a-z.\-]+):(\d+)$", t, re.I)
    if m:
        return m.group(1).lower(), "id", m.group(2)
    if t.isdigit():
        return default_site, "id", t
    if len(t) >= 2:
        return default_site, "name", t
    return None


def call(path: str, **params):
    params.setdefault("site", None)
    params = {k: v for k, v in params.items() if v is not None}
    if KEY:
        params["key"] = KEY
    r = tk.get(f"{API}{path}", params=params, allow=(400, 404))
    try:
        data = r.json() or {}
    except ValueError:
        data = {}
    if data.get("error_id"):
        name = data.get("error_name") or ""
        if name in ("throttle_violation",) or data.get("error_id") == 502:
            tk.fail("rate_limited", f"Stack Exchange kota/hiz siniri: {data.get('error_message')}")
        if data.get("error_id") in (400,) and "site" in (data.get("error_message") or "").lower():
            tk.fail("not_found", f"Gecersiz site: {data.get('error_message')}")
        raise tk.HttpError(data.get("error_id"), path, data.get("error_message") or name)
    _quota["remaining"] = data.get("quota_remaining", _quota["remaining"])
    if data.get("backoff"):
        import time
        time.sleep(min(int(data["backoff"]), 30))
    return data


def main() -> None:
    ap = argparse.ArgumentParser(description="Stack Exchange OSINT")
    ap.add_argument("target")
    ap.add_argument("--site", default="stackoverflow")
    args = ap.parse_args()
    parsed = parse_target(args.target, args.site)
    if not parsed:
        tk.fail("not_found", f"Gecersiz hedef: {args.target}")
    site, kind, value = parsed

    try:
        flt = (call("/filters/create", include="user.about_me;user.website_url;user.location", base="default", unsafe="false").get("items") or [{}])[0].get("filter")
        candidates = []
        if kind == "name":
            res = call("/users", site=site, inname=value, sort="reputation", order="desc", pagesize=10).get("items") or []
            if not res:
                tk.fail("not_found", f"{site} sitesinde '{value}' adli kullanici bulunamadi")
            candidates = [{"user_id": x.get("user_id"), "display_name": x.get("display_name"), "reputation": x.get("reputation"), "link": x.get("link")} for x in res]
            value = str(res[0]["user_id"])
        items = call(f"/users/{value}", site=site, filter=flt).get("items") or []
        if not items:
            tk.fail("not_found", f"Stack Exchange kullanicisi bulunamadi: {site}/{value}")
        u = items[0]
        network = []
        if u.get("account_id"):
            network = call(f"/users/{u['account_id']}/associated", pagesize=100).get("items") or []
        tags = call(f"/users/{value}/top-tags", site=site, pagesize=20).get("items") or []
        answers = call(f"/users/{value}/answers", site=site, pagesize=60, sort="activity", order="desc").get("items") or []
        questions = call(f"/users/{value}/questions", site=site, pagesize=40, sort="activity", order="desc").get("items") or []
        qids = list(dict.fromkeys(str(a["question_id"]) for a in answers if a.get("question_id")))[:100]
        qs = call(f"/questions/{';'.join(qids)}", site=site, pagesize=100).get("items") or [] if qids else []
    except tk.HttpError as e:
        tk.fail("rate_limited" if e.status == 429 else "error", f"Stack Exchange: {e}")

    qmap = {q.get("question_id"): q for q in qs}
    answered = {}
    for a in answers:
        q = qmap.get(a.get("question_id")) or {}
        o = q.get("owner") or {}
        if not o.get("user_id") or o.get("user_id") == u.get("user_id"):
            continue
        k = str(o["user_id"])
        e = answered.setdefault(k, {"user_id": o["user_id"], "name": tk.html_to_text(o.get("display_name") or ""), "link": o.get("link"), "count": 0})
        e["count"] += 1
    about_html = u.get("about_me") or ""
    about = tk.html_to_text(about_html)
    txt = about + " " + about_html + " " + (u.get("website_url") or "")
    dist = tk.distributions([x.get("creation_date") for x in answers + questions])
    tag_counts = Counter()
    for q in questions:
        tag_counts.update(q.get("tags") or [])

    tk.emit({
        "site": site, "user_id": u.get("user_id"), "account_id": u.get("account_id"),
        "display_name": tk.html_to_text(u.get("display_name") or ""), "reputation": u.get("reputation"),
        "badges": u.get("badge_counts") or {}, "created": tk.iso(u.get("creation_date")), "last_access": tk.iso(u.get("last_access_date")),
        "location": tk.html_to_text(u.get("location") or "") or None, "website": u.get("website_url") or None, "link": u.get("link"),
        "profile_image": u.get("profile_image"), "user_type": u.get("user_type"), "is_employee": u.get("is_employee"),
        "about": about, "about_links": list(dict.fromkeys(tk.links_from_html(about_html))), "about_emails": tk.find_emails(about),
        "socials": tk.find_socials(txt),
        "candidates": candidates,
        "network": [{"site": n.get("site_name"), "site_url": n.get("site_url"), "user_id": n.get("user_id"), "reputation": n.get("reputation"),
                     "answers": n.get("answer_count"), "questions": n.get("question_count"), "created": tk.iso(n.get("creation_date")),
                     "link": f"{n.get('site_url')}/users/{n.get('user_id')}" if n.get("site_url") else None} for n in network],
        "top_tags": [{"tag": t.get("tag_name"), "answers": t.get("answer_count"), "answer_score": t.get("answer_score"),
                      "questions": t.get("question_count")} for t in tags],
        "answers": [{"question_id": a.get("question_id"), "title": tk.html_to_text((qmap.get(a.get("question_id")) or {}).get("title") or ""),
                     "score": a.get("score"), "accepted": a.get("is_accepted"), "date": tk.iso(a.get("creation_date")),
                     "link": (qmap.get(a.get("question_id")) or {}).get("link")} for a in answers],
        "questions": [{"title": tk.html_to_text(q.get("title") or ""), "score": q.get("score"), "answered": q.get("is_answered"),
                       "tags": q.get("tags"), "date": tk.iso(q.get("creation_date")), "link": q.get("link")} for q in questions],
        "question_tags": dict(tag_counts.most_common(15)),
        "answered_users": sorted(answered.values(), key=lambda x: -x["count"])[:30],
        "activity": {"first": dist["first"], "last": dist["last"], "hour_distribution": dist["hour_distribution"], "day_distribution": dist["day_distribution"]},
        "quota_remaining": _quota["remaining"],
    })


if __name__ == "__main__":
    main()
