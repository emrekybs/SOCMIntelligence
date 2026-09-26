#!/usr/bin/env python3
"""
Keybase OSINT — kriptografik olarak dogrulanmis hesap baglantilari (API anahtari gerekmez).

  python keybase_osint.py chris
  python keybase_osint.py github:torvalds      (twitter: reddit: hackernews: domain: da olur)
  python keybase_osint.py https://keybase.io/chris
"""
from __future__ import annotations

import argparse
import re

import _toolkit as tk

API = "https://keybase.io/_/api/1.0"
LOOKUP_FIELDS = ("usernames", "github", "twitter", "reddit", "hackernews", "domain", "facebook")


def parse_target(raw: str) -> tuple[str, str] | None:
    t = (raw or "").strip().rstrip("/")
    m = re.search(r"keybase\.io/([A-Za-z0-9_]{2,16})", t, re.I)
    if m:
        return "usernames", m.group(1)
    m = re.match(r"^(github|twitter|reddit|hackernews|domain|facebook)\s*:\s*(\S+)$", t, re.I)
    if m:
        return m.group(1).lower(), m.group(2).lstrip("@")
    t = t.lstrip("@")
    if re.match(r"^[A-Za-z0-9_]{2,16}$", t):
        return "usernames", t
    return None


def pick_users(obj) -> list[dict]:
    """list_followers/following yanitindan kullanici listesini cikar (sema toleransli)."""
    if isinstance(obj, dict):
        for k in ("them", "users", "followers", "following", "list"):
            v = obj.get(k)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    return []


def main() -> None:
    ap = argparse.ArgumentParser(description="Keybase OSINT")
    ap.add_argument("target")
    args = ap.parse_args()
    parsed = parse_target(args.target)
    if not parsed:
        tk.fail("not_found", f"Gecersiz Keybase hedefi: {args.target}")
    field, value = parsed

    try:
        data = tk.get_json(f"{API}/user/lookup.json", params={field: value}, allow=(404,))
    except tk.HttpError as e:
        tk.fail("rate_limited" if e.status == 429 else "error", f"Keybase API: {e}")
    them = [u for u in ((data or {}).get("them") or []) if u]
    st = (data or {}).get("status") or {}
    if not them:
        tk.fail("not_found", f"Keybase kullanicisi bulunamadi ({field}={value}): {st.get('desc') or st.get('name') or ''}".strip())
    u = them[0]

    basics = u.get("basics") or {}
    profile = u.get("profile") or {}
    username = basics.get("username") or value
    uid = u.get("id")

    proofs = []
    for p in ((u.get("proofs_summary") or {}).get("all") or []):
        proofs.append({
            "type": p.get("proof_type"),
            "nametag": p.get("nametag"),
            "state": p.get("state"),
            "service_url": p.get("service_url"),
            "proof_url": p.get("proof_url"),
            "human_url": p.get("human_url"),
            "group": p.get("presentation_group"),
        })

    keys = []
    pk = u.get("public_keys") or {}
    prim = pk.get("primary") or {}
    if prim.get("key_fingerprint"):
        keys.append({"fingerprint": prim.get("key_fingerprint"), "kid": prim.get("kid"), "ctime": tk.iso(prim.get("ctime")),
                     "bits": prim.get("nbits"), "algo": prim.get("key_algo"), "primary": True})
    fps = pk.get("pgp_public_key_fingerprints") or []
    fps += [k.get("key_fingerprint") for k in (pk.get("all_bundles") or []) if isinstance(k, dict)]
    for fp in fps:
        if fp and all(x["fingerprint"] != fp for x in keys):
            keys.append({"fingerprint": fp, "primary": False})

    crypto = {}
    for coin, entries in (u.get("cryptocurrency_addresses") or {}).items():
        addrs = [e.get("address") for e in (entries or []) if isinstance(e, dict) and e.get("address")]
        if addrs:
            crypto[coin] = addrs
    stellar = (u.get("stellar") or {}).get("primary") or {}
    if stellar.get("account_id"):
        crypto.setdefault("stellar", []).append(stellar["account_id"])

    devices = []
    for did, d in (u.get("devices") or {}).items():
        if isinstance(d, dict):
            devices.append({"name": d.get("name"), "type": d.get("type"), "ctime": tk.iso(d.get("ctime")), "status": d.get("status")})

    pic = ((u.get("pictures") or {}).get("primary") or {}).get("url")

    followers, following = [], []
    if uid:
        for kind, target in (("followers", followers), ("following", following)):
            try:
                resp = tk.get_json(f"{API}/user/list_{kind}_for_display.json", params={"uid": uid, "num_wanted": 200}, allow=(404,))
                for f in pick_users(resp)[:200]:
                    if f.get("username"):
                        target.append({"username": f.get("username"), "full_name": f.get("full_name"), "uid": f.get("uid")})
            except tk.HttpError as e:
                tk.log(f"{kind} alinamadi: {e}")

    bio = profile.get("bio") or ""
    tk.emit({
        "username": username,
        "uid": uid,
        "profile_url": f"https://keybase.io/{username}",
        "full_name": profile.get("full_name"),
        "location": profile.get("location"),
        "bio": bio,
        "bio_emails": tk.find_emails(bio),
        "bio_socials": tk.find_socials(bio),
        "picture": pic,
        "created": tk.iso(basics.get("ctime")),
        "modified": tk.iso(basics.get("mtime")),
        "lookup": {"field": field, "value": value},
        "proofs": proofs,
        "pgp_keys": keys,
        "crypto": crypto,
        "devices": devices,
        "followers": followers,
        "following": following,
    })


if __name__ == "__main__":
    main()
