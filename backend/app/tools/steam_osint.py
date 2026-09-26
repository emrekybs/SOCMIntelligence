#!/usr/bin/env python3
"""
Steam OSINT — profil, eski kullanici adlari, gruplar, arkadas listesi, oyunlar.

STEAM_API_KEY varsa resmi Web API kullanilir (arkadas listesi + oyunlar + banlar + seviye).
Yoksa herkese acik XML profil + ad gecmisi + arkadas sayfasi okunur.

  python steam_osint.py gabelogannewell
  python steam_osint.py 76561197960287930
  python steam_osint.py https://steamcommunity.com/id/gabelogannewell
"""
from __future__ import annotations

import argparse
import os
import re
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

import _toolkit as tk

API = "https://api.steampowered.com"
COMM = "https://steamcommunity.com"
KEY = os.environ.get("STEAM_API_KEY", "").strip()
PERSONA = {0: "Çevrimdışı", 1: "Çevrimiçi", 2: "Meşgul", 3: "Uzakta", 4: "Uykuda", 5: "Takas arıyor", 6: "Oyun arıyor"}
VIS = {1: "Gizli", 2: "Yalnızca arkadaşlar", 3: "Herkese açık"}


def parse_target(raw: str) -> tuple[str, str] | None:
    t = (raw or "").strip().rstrip("/")
    m = re.search(r"steamcommunity\.com/profiles/(\d{17})", t)
    if m:
        return "id64", m.group(1)
    m = re.search(r"steamcommunity\.com/id/([A-Za-z0-9_\-]{2,64})", t)
    if m:
        return "vanity", m.group(1)
    if re.match(r"^7656119\d{10}$", t):
        return "id64", t
    t = t.lstrip("@")
    if re.match(r"^[A-Za-z0-9_\-]{2,64}$", t):
        return "vanity", t
    return None


def api(path: str, **params):
    params["key"] = KEY
    return tk.get_json(f"{API}/{path}", params=params, allow=(401, 403))


def xml_text(root, tag):
    el = root.find(tag)
    return el.text.strip() if el is not None and el.text else None


def public_profile(kind: str, value: str) -> dict | None:
    url = f"{COMM}/profiles/{value}/?xml=1" if kind == "id64" else f"{COMM}/id/{value}/?xml=1"
    r = tk.get(url, allow=(404,))
    if r.status_code != 200:
        return None
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        return None
    if root.tag != "profile" or root.find("steamID64") is None:
        return None
    groups = []
    for g in root.findall("./groups/group"):
        groups.append({
            "id": xml_text(g, "groupID64"), "name": xml_text(g, "groupName"), "url": xml_text(g, "groupURL"),
            "members": int(xml_text(g, "memberCount") or 0) or None, "primary": g.get("isPrimary") == "1",
        })
    games = []
    for g in root.findall("./mostPlayedGames/mostPlayedGame"):
        games.append({"name": xml_text(g, "gameName"), "hours_2w": _f(xml_text(g, "hoursPlayed")),
                      "hours": _f(xml_text(g, "hoursOnRecord")), "url": xml_text(g, "gameLink")})
    summary_html = xml_text(root, "summary") or ""
    return {
        "steamid": xml_text(root, "steamID64"),
        "persona": xml_text(root, "steamID"),
        "custom_url": xml_text(root, "customURL"),
        "online_state": xml_text(root, "onlineState"),
        "state_message": tk.html_to_text(xml_text(root, "stateMessage") or ""),
        "privacy": xml_text(root, "privacyState"),
        "avatar": xml_text(root, "avatarFull"),
        "vac_banned": xml_text(root, "vacBanned") == "1",
        "trade_ban": xml_text(root, "tradeBanState"),
        "limited": xml_text(root, "isLimitedAccount") == "1",
        "member_since": xml_text(root, "memberSince"),
        "location": xml_text(root, "location"),
        "real_name": xml_text(root, "realname"),
        "summary": tk.html_to_text(summary_html),
        "summary_links": tk.links_from_html(summary_html),
        "hours_2w": _f(xml_text(root, "hoursPlayed2Wk")),
        "groups": groups,
        "most_played": games,
    }


def _f(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def aliases(id64: str) -> list[dict]:
    try:
        data = tk.get_json(f"{COMM}/profiles/{id64}/ajaxaliases/", allow=(404,))
    except tk.HttpError:
        return []
    return [{"name": a.get("newname"), "changed": a.get("timechanged")} for a in (data or []) if isinstance(a, dict) and a.get("newname")]


def friends_public(id64: str) -> list[dict]:
    try:
        r = tk.get(f"{COMM}/profiles/{id64}/friends/", allow=(403, 404))
    except tk.HttpError:
        return []
    if r.status_code != 200:
        return []
    soup = BeautifulSoup(r.text, "lxml")
    out = []
    for b in soup.select("[data-steamid]"):
        sid = b.get("data-steamid")
        if not sid or sid == id64 or any(f["steamid"] == sid for f in out):
            continue
        content = b.select_one(".friend_block_content")
        name = content.contents[0].strip() if content and content.contents and isinstance(content.contents[0], str) else (content.get_text(" ", strip=True).split("\n")[0] if content else None)
        img = b.select_one("img")
        out.append({"steamid": sid, "name": name, "profile_url": f"{COMM}/profiles/{sid}", "avatar": img.get("src") if img else None})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Steam OSINT")
    ap.add_argument("target")
    args = ap.parse_args()
    parsed = parse_target(args.target)
    if not parsed:
        tk.fail("not_found", f"Gecersiz Steam hedefi: {args.target}")
    kind, value = parsed

    try:
        id64 = value if kind == "id64" else None
        if KEY and not id64:
            res = (api("ISteamUser/ResolveVanityURL/v0001/", vanityurl=value) or {}).get("response") or {}
            if res.get("success") == 1:
                id64 = res.get("steamid")
        pub = public_profile("id64" if id64 else kind, id64 or value)
        if pub and not id64:
            id64 = pub["steamid"]
        if not id64:
            tk.fail("not_found", f"Steam profili bulunamadi: {value}")

        out = {"steamid": id64, "profile_url": f"{COMM}/profiles/{id64}", "source": "api" if KEY else "public", **(pub or {})}
        out["steamid"] = id64

        if KEY:
            ps = ((api("ISteamUser/GetPlayerSummaries/v0002/", steamids=id64) or {}).get("response") or {}).get("players") or []
            if ps:
                p = ps[0]
                out.update({
                    "persona": p.get("personaname") or out.get("persona"),
                    "profile_url": p.get("profileurl") or out["profile_url"],
                    "avatar": p.get("avatarfull") or out.get("avatar"),
                    "real_name": p.get("realname") or out.get("real_name"),
                    "country": p.get("loccountrycode"), "state_code": p.get("locstatecode"),
                    "time_created": tk.iso(p.get("timecreated")), "last_logoff": tk.iso(p.get("lastlogoff")),
                    "persona_state": PERSONA.get(p.get("personastate")), "visibility": VIS.get(p.get("communityvisibilitystate")),
                    "playing": p.get("gameextrainfo"), "primary_clan": p.get("primaryclanid"),
                })
            bans = ((api("ISteamUser/GetPlayerBans/v1/", steamids=id64) or {}).get("players") or [{}])[0]
            if bans:
                out["bans"] = {"vac": bans.get("NumberOfVACBans"), "game": bans.get("NumberOfGameBans"), "community": bans.get("CommunityBanned"),
                               "economy": bans.get("EconomyBan"), "days_since_last": bans.get("DaysSinceLastBan")}
            lvl = ((api("IPlayerService/GetSteamLevel/v1/", steamid=id64) or {}).get("response") or {}).get("player_level")
            out["level"] = lvl
            fl = ((api("ISteamUser/GetFriendList/v0001/", steamid=id64, relationship="friend") or {}).get("friendslist") or {}).get("friends") or []
            friends = [{"steamid": f.get("steamid"), "since": tk.iso(f.get("friend_since")), "profile_url": f"{COMM}/profiles/{f.get('steamid')}"} for f in fl]
            ids = [f["steamid"] for f in friends][:300]
            names = {}
            for i in range(0, len(ids), 100):
                for p in ((api("ISteamUser/GetPlayerSummaries/v0002/", steamids=",".join(ids[i:i + 100])) or {}).get("response") or {}).get("players") or []:
                    names[p.get("steamid")] = p
            for f in friends:
                p = names.get(f["steamid"]) or {}
                f["name"], f["avatar"], f["country"] = p.get("personaname"), p.get("avatarmedium"), p.get("loccountrycode")
            out["friends"] = friends
            og = (api("IPlayerService/GetOwnedGames/v0001/", steamid=id64, include_appinfo=1, include_played_free_games=1) or {}).get("response") or {}
            games = sorted(og.get("games") or [], key=lambda g: -(g.get("playtime_forever") or 0))
            out["games"] = {"count": og.get("game_count"), "top": [{"appid": g.get("appid"), "name": g.get("name"),
                            "hours": round((g.get("playtime_forever") or 0) / 60, 1), "hours_2w": round((g.get("playtime_2weeks") or 0) / 60, 1)} for g in games[:25]]}
        else:
            out["friends"] = friends_public(id64)

        out["aliases"] = aliases(id64)
        text = (out.get("summary") or "") + " " + " ".join(out.get("summary_links") or [])
        out["summary_emails"] = tk.find_emails(text)
        out["summary_socials"] = tk.find_socials(text)
        if not pub and not KEY:
            tk.fail("not_found", f"Steam profili okunamadi: {value}")
    except tk.HttpError as e:
        tk.fail("rate_limited" if e.status == 429 else "error", f"Steam: {e}")
    tk.emit(out)


if __name__ == "__main__":
    main()
