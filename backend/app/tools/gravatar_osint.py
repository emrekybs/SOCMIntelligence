#!/usr/bin/env python3
"""
Gravatar OSINT — e-posta / hash / kullanici adindan profil, avatar ve bagli hesaplar.

  python gravatar_osint.py kisi@ornek.com
  python gravatar_osint.py 205e460b479e2e5b48aec07710c08d50
  python gravatar_osint.py beau

GRAVATAR_API_KEY varsa v3 API daha fazla alan dondurur (opsiyonel).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re

import _toolkit as tk

KEY = os.environ.get("GRAVATAR_API_KEY", "").strip()


def classify(raw: str) -> tuple[str, str]:
    t = (raw or "").strip()
    m = re.search(r"gravatar\.com/([A-Za-z0-9._\-]+)", t, re.I)
    if m and m.group(1).lower() not in ("avatar", "profile"):
        t = m.group(1)
    if "@" in t and "." in t.split("@")[-1]:
        return "email", t.lower()
    if re.fullmatch(r"[a-fA-F0-9]{32}", t):
        return "md5", t.lower()
    if re.fullmatch(r"[a-fA-F0-9]{64}", t):
        return "sha256", t.lower()
    return "username", t.lstrip("@")


def v3_profile(ident: str) -> dict | None:
    headers = {"Authorization": f"Bearer {KEY}"} if KEY else None
    r = tk.get(f"https://api.gravatar.com/v3/profiles/{ident}", headers=headers, allow=(404, 401, 403))
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def legacy_profile(ident: str) -> dict | None:
    r = tk.get(f"https://gravatar.com/{ident}.json", allow=(404, 403))
    if r.status_code != 200:
        return None
    try:
        entry = (r.json().get("entry") or [None])[0]
    except (ValueError, AttributeError):
        return None
    return entry


def main() -> None:
    ap = argparse.ArgumentParser(description="Gravatar OSINT")
    ap.add_argument("target")
    args = ap.parse_args()
    kind, value = classify(args.target)
    md5 = sha256 = None
    if kind == "email":
        md5 = hashlib.md5(value.encode()).hexdigest()
        sha256 = hashlib.sha256(value.encode()).hexdigest()
    elif kind == "md5":
        md5 = value
    elif kind == "sha256":
        sha256 = value

    try:
        has_avatar = None
        avatar_hash = md5 or sha256
        if avatar_hash:
            r = tk.get(f"https://gravatar.com/avatar/{avatar_hash}", params={"d": "404", "s": "400"}, allow=(404,))
            has_avatar = r.status_code == 200

        prof, source = None, None
        for ident in [x for x in (sha256, md5, value if kind == "username" else None) if x]:
            prof = v3_profile(ident)
            if prof:
                source = "v3"
                break
        legacy = None
        for ident in [x for x in (md5, value if kind == "username" else None, sha256) if x]:
            legacy = legacy_profile(ident)
            if legacy:
                source = source or "legacy"
                break
    except tk.HttpError as e:
        tk.fail("rate_limited" if e.status == 429 else "error", f"Gravatar: {e}")

    if not prof and not legacy and not has_avatar:
        tk.fail("not_found", f"Gravatar kaydi bulunamadi: {value}")

    p, l = prof or {}, legacy or {}
    accounts = []
    for a in (p.get("verified_accounts") or []):
        if a.get("is_hidden"):
            continue
        accounts.append({"service": a.get("service_label") or a.get("service_type"), "type": a.get("service_type"), "url": a.get("url"),
                         "username": _handle_from_url(a.get("url")), "verified": True})
    for a in (l.get("accounts") or []):
        if any(x["url"] == a.get("url") for x in accounts):
            continue
        accounts.append({"service": a.get("name") or a.get("shortname") or a.get("domain"), "type": a.get("shortname"), "url": a.get("url"),
                         "username": a.get("username") or a.get("display"), "verified": a.get("verified") in (True, "true")})
    links = [{"title": x.get("label"), "url": x.get("url")} for x in (p.get("links") or [])]
    links += [{"title": x.get("title"), "url": x.get("value")} for x in (l.get("urls") or []) if not any(y["url"] == x.get("value") for y in links)]
    crypto = [{"label": w.get("label"), "address": w.get("address")} for w in ((p.get("payments") or {}).get("crypto_wallets") or [])]
    crypto += [{"label": c.get("type"), "address": c.get("value")} for c in (l.get("currency") or [])]
    contact = p.get("contact_info") or {}
    phones = [x.get("value") for x in (l.get("phoneNumbers") or []) if x.get("value")]
    phones += [contact.get(k) for k in ("home_phone", "work_phone", "cell_phone") if contact.get(k)]
    emails = [x.get("value") for x in (l.get("emails") or []) if x.get("value")]
    if contact.get("email"):
        emails.append(contact["email"])
    about = p.get("description") or l.get("aboutMe") or ""
    for e in tk.find_emails(about):
        if e not in emails:
            emails.append(e)

    tk.emit({
        "input": value, "input_type": kind, "email": value if kind == "email" else None,
        "md5": md5 or l.get("hash"), "sha256": sha256 or p.get("hash"),
        "has_avatar": has_avatar,
        "avatar_url": p.get("avatar_url") or l.get("thumbnailUrl") or (f"https://gravatar.com/avatar/{avatar_hash}?s=400" if has_avatar else None),
        "profile_found": bool(prof or legacy), "source": source or "avatar",
        "profile_url": p.get("profile_url") or l.get("profileUrl"),
        "username": l.get("preferredUsername") or (value if kind == "username" else None),
        "display_name": p.get("display_name") or l.get("displayName"),
        "name": " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x) or ((l.get("name") or {}).get("formatted") if isinstance(l.get("name"), dict) else None),
        "about": about,
        "location": p.get("location") or l.get("currentLocation"),
        "job_title": p.get("job_title"), "company": p.get("company"),
        "pronouns": p.get("pronouns"), "timezone": p.get("timezone"),
        "registration_date": p.get("registration_date"), "last_profile_edit": p.get("last_profile_edit"),
        "accounts": accounts, "links": links, "crypto": crypto, "phones": phones, "emails": emails,
        "socials": tk.find_socials(" ".join([about] + [a.get("url") or "" for a in accounts] + [x["url"] or "" for x in links])),
    })


def _handle_from_url(url: str | None) -> str | None:
    if not url:
        return None
    s = tk.find_socials(url)
    return s[0]["handle"] if s else url.rstrip("/").rsplit("/", 1)[-1]


if __name__ == "__main__":
    main()
