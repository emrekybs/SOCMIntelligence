"""
Iliski grafigi zenginlestirme katmani.

Modullerin kendi `to_graph()` ciktisini TEMEL alir, uzerine arac ciktisinda olup
modul donusturucusunun kullanmadigi iliskileri ekler:

  YouTube   : en cok yorum yapanlar, en cok begenilen yorum sahipleri, About/aciklama
              sosyal linkleri (bio_links), etiketler
  TikTok    : yorumcular -> videolar, bio linki, hashtag'ler
  Reddit    : kullanici -> subreddit agirliklari, subreddit -> moderatorler / yazarlar
  Snapchat  : iliskili hesaplar (abone sayisi), spotlight hashtag'leri
  Mastodon  : en cok bahsedilen hesaplar, hashtag'ler, telefon/kripto adresleri
  GitHub    : organizasyon uyeleri, commit e-postalarinin gectigi repolar, ilgi konulari

Modul dosyalarina dokunulmaz; ayni node ID semasi kullanildigi icin platformlar
arasi kimlik eslestirme (ayni ID = ayni dugum) calismaya devam eder.
"""
from __future__ import annotations

import math
import re
from typing import Any
from urllib.parse import urlparse


# ═════════════════════════════════════════════════════════════════
# Yardimcilar
# ═════════════════════════════════════════════════════════════════

def _slug(s: Any) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(s or "").lower()).strip("_")[:40]


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    u = url if re.match(r"^https?://", url, re.I) else "https://" + url
    try:
        host = urlparse(u).netloc.lower()
    except Exception:
        return None
    host = host.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _trunc(s: Any, n: int) -> str:
    s = str(s or "").replace("\n", " ").replace("\r", " ").strip()
    return s[:n] + "…" if len(s) > n else s


def fill_missing(validated: Any, raw: Any) -> Any:
    """
    Pydantic dogrulamasi semada olmayan alanlari sessizce atar
    (or. YouTube tool'unun `bio_links`, `wayback` alanlari).
    Dogrulanmis veriyi KORUR, sadece eksik anahtarlari ham ciktidan ekler.
    """
    if isinstance(validated, dict) and isinstance(raw, dict):
        out = dict(validated)
        for k, rv in raw.items():
            if k not in out:
                out[k] = rv
            else:
                out[k] = fill_missing(out[k], rv)
        return out
    if isinstance(validated, list) and isinstance(raw, list) and len(validated) == len(raw):
        return [fill_missing(v, r) for v, r in zip(validated, raw)]
    return validated


# Kanonik platform on-ekleri - farkli modullerin ayni hesap icin ayni ID uretmesi icin
_ID_ALIASES = [
    ("u_twitter_x_", "u_twitter_"),
    ("u_x_", "u_twitter_"),
    ("u_github_", "u_gh_"),
    ("u_snapchat_", "u_snap_"),
    ("u_mastodon_", "u_masto_"),
]


def canonical_id(node_id: str) -> str:
    nid = (node_id or "").lower()
    for old, new in _ID_ALIASES:
        if nid.startswith(old):
            return new + nid[len(old):]
    return nid


class GraphBuilder:
    """Node/edge ekleme, (source,target,type) bazinda tekillestirme, agirlik."""

    def __init__(self, base: dict[str, list] | None = None, platform: str = ""):
        self.platform = platform
        self.nodes: dict[str, dict] = {}
        self.edges: dict[tuple, dict] = {}
        base = base or {"nodes": [], "edges": []}
        for n in base.get("nodes", []):
            n = dict(n)
            n["id"] = canonical_id(n["id"])
            n["meta"] = dict(n.get("meta") or {})
            self.nodes.setdefault(n["id"], n)
        for e in base.get("edges", []):
            self.edge(canonical_id(e["source"]), canonical_id(e["target"]), e.get("type", "linked_to"),
                      weight=e.get("weight"))

    def has(self, nid: str) -> bool:
        return canonical_id(nid) in self.nodes

    def node(self, nid: str, ntype: str, label: str, meta: dict | None = None) -> str:
        nid = canonical_id(nid)
        meta = {k: v for k, v in (meta or {}).items() if v not in (None, "", [], {})}
        if nid in self.nodes:
            cur = self.nodes[nid]["meta"]
            for k, v in meta.items():
                cur.setdefault(k, v)
        else:
            self.nodes[nid] = {"id": nid, "type": ntype, "label": str(label), "meta": meta}
        return nid

    def edge(self, src: str, tgt: str, etype: str, weight: float | int | None = None) -> None:
        src, tgt = canonical_id(src), canonical_id(tgt)
        if not src or not tgt or src == tgt:
            return
        key = (src, tgt, etype)
        if key in self.edges:
            if weight is not None:
                old = self.edges[key].get("weight") or 0
                self.edges[key]["weight"] = max(old, weight)
            return
        e = {"id": f"ed_{src}__{tgt}__{etype}", "source": src, "target": tgt, "type": etype}
        if weight is not None:
            e["weight"] = weight
        self.edges[key] = e

    def bump(self, src: str, tgt: str, etype: str, by: int = 1) -> None:
        src, tgt = canonical_id(src), canonical_id(tgt)
        key = (src, tgt, etype)
        if key in self.edges:
            self.edges[key]["weight"] = (self.edges[key].get("weight") or 0) + by
        else:
            self.edge(src, tgt, etype, weight=by)

    def drop(self, src: str, tgt: str, etype: str) -> None:
        self.edges.pop((canonical_id(src), canonical_id(tgt), etype), None)

    def retype(self, prefix: str, new_type: str, meta: dict | None = None) -> None:
        for nid, n in self.nodes.items():
            if nid.startswith(prefix):
                n["type"] = new_type
                for k, v in (meta or {}).items():
                    n["meta"].setdefault(k, v)

    def export(self) -> dict[str, list]:
        # Kenarlarin iki ucu da mevcut olmali
        edges = [e for e in self.edges.values() if e["source"] in self.nodes and e["target"] in self.nodes]
        nodes = list(self.nodes.values())
        for n in nodes:
            srcs = n.setdefault("sources", [])
            if self.platform and self.platform not in srcs:
                srcs.append(self.platform)
        return {"nodes": nodes, "edges": edges}


def _pairs(obj: Any, key_names=("tag", "name", "account", "sub", "user", "author", "username"),
           count_names=("count", "posts", "total_comments")) -> list[tuple[str, int]]:
    """{"a":3} / [["a",3]] / [{"tag":"a","count":3}] -> [("a",3)]"""
    out: list[tuple[str, int]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            try:
                out.append((str(k), int(v)))
            except (TypeError, ValueError):
                continue
    elif isinstance(obj, list):
        for it in obj:
            if isinstance(it, (list, tuple)) and len(it) >= 2:
                out.append((str(it[0]), int(it[1] or 0)))
            elif isinstance(it, dict):
                k = next((it[n] for n in key_names if it.get(n)), None)
                c = next((it[n] for n in count_names if it.get(n) is not None), 0)
                if k:
                    try:
                        out.append((str(k), int(c)))
                    except (TypeError, ValueError):
                        out.append((str(k), 0))
    return out


def _hashtags(g: GraphBuilder, anchor: str, pairs: list[tuple[str, int]], limit: int, platform: str) -> None:
    for tag, cnt in pairs[:limit]:
        tag = tag.lstrip("#").strip()
        if not tag:
            continue
        hid = g.node(f"h_{_slug(tag)}", "hashtag", f"#{tag}", {"Platform": platform})
        g.edge(anchor, hid, "tagged", weight=cnt or None)


# ═════════════════════════════════════════════════════════════════
# Platform zenginlestiricileri
# ═════════════════════════════════════════════════════════════════

def _enrich_github(g: GraphBuilder, d: dict) -> None:
    login = d.get("login")
    if not login:
        return
    pid = f"p_gh_{login}"
    g.retype("u_org_", "community", {"Tür": "GitHub organizasyonu"})

    for org in d.get("organizations") or []:
        if not isinstance(org, dict) or not org.get("org"):
            continue
        oid = f"u_org_{_slug(org['org'])}"
        g.node(oid, "community", f"@{org['org']}", {"Platforms": "GitHub Org",
                                                   "Profile": f"https://github.com/{org['org']}"})
        g.drop(pid, oid, "registered_to")
        g.edge(pid, oid, "member_of")
        for m in (org.get("members") or [])[:20]:
            if not m or str(m).lower() == str(login).lower():
                continue
            mid = g.node(f"u_gh_{_slug(m)}", "username", m, {
                "Platforms": "GitHub", "Profile": f"https://github.com/{m}",
                "Source": f"{org['org']} organizasyon üyesi",
            })
            g.edge(mid, oid, "member_of")

    if d.get("twitter_username"):
        tw = d["twitter_username"]
        tid = g.node(f"u_twitter_{_slug(tw)}", "username", f"@{tw}", {
            "Platforms": "Twitter/X", "URL": f"https://x.com/{tw}", "Source": "GitHub profili"})
        g.edge(pid, tid, "linked_to")

    for c in (d.get("commit_search_emails") or [])[:15]:
        if not isinstance(c, dict) or not c.get("email"):
            continue
        eid = g.node(f"e_{_slug(c['email'])}", "email", c["email"], {"Source": "Commit meta verisi",
                                                                     "Commit_adı": c.get("name")})
        g.edge(pid, eid, "owns")
        repo = c.get("repo")
        if repo and repo != "?":
            rid = g.node(f"c_gh_repo_{_slug(repo)}", "content", repo, {
                "Tür": "Repo", "URL": f"https://github.com/{repo}"})
            g.edge(eid, rid, "appears_in")

    for topic, cnt in _pairs(d.get("starred_top_topics") or {})[:6]:
        hid = g.node(f"h_{_slug(topic)}", "hashtag", f"#{topic}", {"Platform": "GitHub (yıldızlı repo konusu)"})
        g.edge(pid, hid, "interest", weight=cnt)

    for s in (d.get("secrets_found") or []):
        if isinstance(s, dict):
            sid = f"br_secret_{_slug(s.get('type', ''))}"
            if g.has(sid):
                g.nodes[canonical_id(sid)]["meta"].setdefault("Snippet", s.get("snippet"))


def _masto_account(g: GraphBuilder, acc: dict, fallback_instance: str | None = None) -> None:
    username = acc.get("username") or acc.get("acct")
    instance = acc.get("instance") or fallback_instance
    if not username or not instance:
        return
    uid = f"u_masto_{_slug(username)}_{_slug(instance)}"
    pid = f"p_masto_{_slug(username)}_{_slug(instance)}"
    anchor = pid if g.has(pid) else g.node(uid, "username", f"@{username}@{instance}",
                                          {"Platforms": "Mastodon", "Instance": instance,
                                           "Profile": acc.get("profile_url")})
    sa = acc.get("status_analysis") or {}
    for acct, cnt in _pairs(sa.get("top_mentions") or {})[:12]:
        a = acct.lstrip("@")
        if "@" in a:
            mu, mi = a.split("@", 1)
        else:
            mu, mi = a, instance
        if not mu:
            continue
        mid = g.node(f"u_masto_{_slug(mu)}_{_slug(mi)}", "username", f"@{mu}@{mi}", {
            "Platforms": "Mastodon", "Instance": mi, "Profile": f"https://{mi}/@{mu}",
            "Source": f"@{username} tarafından bahsedildi"})
        g.edge(anchor, mid, "mentioned", weight=cnt)
    _hashtags(g, anchor, _pairs(sa.get("top_hashtags") or {}), 10, "Mastodon")

    for ph in (acc.get("phone_numbers") or [])[:5]:
        aid = g.node(f"a_phone_{_slug(ph)}", "artifact", ph, {"Tür": "Telefon", "Source": "Mastodon bio"})
        g.edge(anchor, aid, "owns")
    for chain, addrs in (acc.get("crypto_addresses") or {}).items():
        for ad in (addrs or [])[:3]:
            aid = g.node(f"a_crypto_{_slug(ad)}", "artifact", _trunc(ad, 18),
                         {"Tür": f"Kripto ({chain.upper()})", "Adres": ad, "Source": "Mastodon bio"})
            g.edge(anchor, aid, "owns")


def _enrich_mastodon(g: GraphBuilder, d: dict) -> None:
    if d.get("targeted_account"):
        _masto_account(g, d["targeted_account"])
    inst = d.get("instance_info") or {}
    if inst.get("admin"):
        _masto_account(g, inst["admin"], inst.get("instance"))
    for hit in (d.get("username_scan") or []):
        if isinstance(hit, dict) and (hit.get("status_analysis") or hit.get("phone_numbers")
                                      or hit.get("crypto_addresses")):
            _masto_account(g, hit)


def _enrich_reddit(g: GraphBuilder, d: dict) -> None:
    if d.get("type") == "subreddit":
        name = d.get("name") or ""
        sub_id = f"d_reddit_sub_{_slug(name)}"
        pa = d.get("post_analysis") or {}
        for a in pa.get("top_authors") or []:
            if not isinstance(a, dict) or not a.get("user") or str(a["user"]).startswith("["):
                continue
            uid = g.node(f"u_reddit_{_slug(a['user'])}", "username", f"u/{a['user']}", {
                "Platforms": "Reddit", "Profile": f"https://www.reddit.com/user/{a['user']}"})
            g.edge(uid, sub_id, "appears_in", weight=a.get("posts"))
        for m in d.get("moderators") or []:
            if not isinstance(m, dict):
                continue
            user = m.get("username") or m.get("name") or m.get("user")
            if not user:
                continue
            uid = g.node(f"u_reddit_{_slug(user)}", "username", f"u/{user}", {
                "Platforms": "Reddit", "Role": "Moderatör", "Mod_since": m.get("mod_since"),
                "Profile": f"https://www.reddit.com/user/{user}"})
            g.edge(uid, sub_id, "moderates")
    else:
        username = d.get("username") or ""
        pid = f"p_reddit_{_slug(username)}"
        sa = d.get("subreddit_analysis") or {}
        for sub, cnt in _pairs(sa.get("top_subreddits") or [])[:12]:
            sid = g.node(f"d_reddit_sub_{_slug(sub)}", "community", f"r/{sub}", {
                "Platform": "Reddit subreddit", "URL": f"https://www.reddit.com/r/{sub}"})
            g.edge(pid, sid, "appears_in", weight=cnt)
    g.retype("d_reddit_sub_", "community")


def _enrich_snapchat(g: GraphBuilder, d: dict) -> None:
    info = d.get("account_information") or {}
    username = info.get("username")
    if not username:
        return
    pid = f"p_snap_{_slug(username)}"
    if g.has(pid):
        badge = info.get("badge")
        # Tool rozet yoksa "None" string'i yaziyor -> dogru deger
        g.nodes[canonical_id(pid)]["meta"]["Verified"] = "Yes" if badge not in (None, "", "None", "null") else "No"
    for rel in (d.get("related_accounts") or [])[:12]:
        if not isinstance(rel, dict) or not rel.get("username") or rel["username"] == username:
            continue
        rid = g.node(f"u_snap_{_slug(rel['username'])}", "username", f"@{rel['username']}", {
            "Platforms": "Snapchat", "Display_Name": rel.get("title"),
            "Subscribers": rel.get("subscribers"),
            "Profile": f"https://www.snapchat.com/add/{rel['username']}",
            "Source": "Snapchat 'ilişkili hesaplar'"})
        g.drop(pid, rid, "linked_to")
        g.edge(pid, rid, "related")
    tags: dict[str, int] = {}
    for sp in ((d.get("spotlights") or {}).get("spotlights") or []):
        for t in (sp.get("hashtags") or []) if isinstance(sp, dict) else []:
            t = str(t).lstrip("#")
            if t:
                tags[t] = tags.get(t, 0) + 1
    _hashtags(g, pid, sorted(tags.items(), key=lambda x: -x[1]), 10, "Snapchat")


def _enrich_tiktok(g: GraphBuilder, d: dict) -> None:
    username = d.get("username")
    if not username:
        return
    pid = f"p_tiktok_{_slug(username)}"

    bl = d.get("bio_link") or {}
    url = bl.get("final_url") or bl.get("original_url") or bl.get("url")
    dom = bl.get("domain") or _domain(url)
    if url and dom:
        did = g.node(f"d_ext_{_slug(dom)}", "domain", dom, {"Source": "TikTok bio linki", "URL": url,
                                                            "HTTP": bl.get("http_code")})
        g.edge(pid, did, "owns")

    _hashtags(g, pid, _pairs((d.get("hashtag_analysis") or {}).get("top_tags") or []), 10, "TikTok")

    videos = {str(v.get("id")): v for v in (d.get("videos") or []) if isinstance(v, dict)}
    ca = d.get("comment_analysis") or {}
    for c in (ca.get("top_commenters") or [])[:15]:
        u = c.get("username") if isinstance(c, dict) else None
        if not u or u == username:
            continue
        cid = g.node(f"u_tiktok_{_slug(u)}", "username", f"@{u}", {
            "Platforms": "TikTok", "Role": "Yorumcu", "Profile": f"https://www.tiktok.com/@{u}",
            "Yorum_sayısı": c.get("total_comments"), "Video_sayısı": c.get("video_count")})
        g.edge(cid, pid, "commented", weight=c.get("total_comments"))
    for c in (ca.get("top_liked") or [])[:10]:
        if not isinstance(c, dict) or not c.get("author") or not c.get("video_id"):
            continue
        vid = str(c["video_id"])
        v = videos.get(vid, {})
        vnode = g.node(f"c_tiktok_{_slug(vid)}", "content", _trunc(v.get("title") or vid, 28), {
            "Tür": "Video", "URL": v.get("url") or f"https://www.tiktok.com/@{username}/video/{vid}",
            "İzlenme": v.get("views"), "Beğeni": v.get("likes")})
        g.edge(pid, vnode, "posted")
        a = c["author"]
        cid = g.node(f"u_tiktok_{_slug(a)}", "username", f"@{a}", {
            "Platforms": "TikTok", "Role": "Yorumcu", "Profile": f"https://www.tiktok.com/@{a}"})
        g.bump(cid, vnode, "commented")


def _enrich_youtube(g: GraphBuilder, d: dict) -> None:
    from app.modules.youtube import YouTubeGraphConverter, _extract_handle_from_url  # modul yardimcilari

    channel = d.get("channel") or {}
    title = channel.get("title") or d.get("target") or "unknown"
    handle = channel.get("handle") or d.get("target") or ""
    handle_clean = handle.lstrip("@") if handle else _slug(title)
    pid = f"p_youtube_{_slug(handle_clean)}"
    if not g.has(pid):
        return
    # Tool'daki "verified" aslinda status.longUploadsStatus == allowed (dogrulama rozeti DEGIL)
    pm = g.nodes[canonical_id(pid)]["meta"]
    if "Verified" in pm:
        pm["Uzun_video_izni"] = "Var" if pm.pop("Verified") == "Yes" else "Yok"

    # Tool ciktisi `bio_links` (modul semasi `bio_data` bekliyor) -> sosyal hesaplar
    bl = d.get("bio_links") or {}
    for acc in (bl.get("social_accounts") or [])[:20]:
        if not isinstance(acc, dict):
            continue
        url = acc.get("url") or ""
        plat_raw = (acc.get("platform") or "").lower().strip()
        if not plat_raw:
            continue
        key = YouTubeGraphConverter.PLATFORM_MAP.get(plat_raw, _slug(plat_raw))
        h = _extract_handle_from_url(url, key) if url else None
        h = h or acc.get("handle")
        if not h:
            continue
        sid = g.node(f"u_{key}_{_slug(h.lstrip('@'))}", "username", h if h.startswith("@") else f"@{h}", {
            "Platforms": acc.get("platform"), "URL": url,
            "Source": "YouTube Hakkında linkleri" if acc.get("verified") else "YouTube kanal açıklaması"})
        g.edge(pid, sid, "linked_to")
    for ln in (bl.get("links") or [])[:10]:
        if not isinstance(ln, dict):
            continue
        dom = ln.get("domain") or _domain(ln.get("final") or ln.get("original"))
        if not dom or "youtube.com" in dom or "youtu.be" in dom:
            continue
        did = g.node(f"d_ext_{_slug(dom)}", "domain", dom, {
            "Source": "YouTube açıklaması", "URL": ln.get("final") or ln.get("original"),
            "HTTP": ln.get("http_code")})
        g.edge(pid, did, "linked_to")

    ca = d.get("comment_analysis") or {}
    for c in (ca.get("top_commenters") or [])[:15]:
        if not isinstance(c, dict) or not c.get("author"):
            continue
        a = c["author"]
        cid = g.node(f"u_ytname_{_slug(a)}", "username", a, {
            "Platforms": "YouTube", "Role": "Yorumcu (görünen ad)", "Yorum_sayısı": c.get("count")})
        g.edge(cid, pid, "commented", weight=c.get("count"))
    for c in (ca.get("top_liked_comments") or [])[:8]:
        if not isinstance(c, dict) or not c.get("author"):
            continue
        a = c["author"]
        cid = g.node(f"u_ytname_{_slug(a)}", "username", a, {
            "Platforms": "YouTube", "Role": "Yorumcu (görünen ad)",
            "En_beğenilen_yorum": _trunc(c.get("text"), 80), "Beğeni": c.get("likes")})
        g.edge(cid, pid, "commented")

    _hashtags(g, pid, _pairs((d.get("video_analysis") or {}).get("top_tags") or []), 10, "YouTube")


_ENRICHERS = {
    "github": _enrich_github,
    "mastodon": _enrich_mastodon,
    "reddit": _enrich_reddit,
    "snapchat": _enrich_snapchat,
    "tiktok": _enrich_tiktok,
    "youtube": _enrich_youtube,
}


def _single(adapter, d: dict) -> dict[str, list]:
    g = GraphBuilder(adapter.to_graph(d), platform=adapter.platform)
    fn = _ENRICHERS.get(adapter.platform)
    if fn:
        fn(g, d)
    return g.export()


def merge_graphs(graphs: list[dict[str, list]]) -> dict[str, list]:
    nodes: dict[str, dict] = {}
    edges: dict[tuple, dict] = {}
    for gr in graphs:
        for n in gr.get("nodes", []):
            if n["id"] in nodes:
                cur = nodes[n["id"]]
                for k, v in (n.get("meta") or {}).items():
                    cur["meta"].setdefault(k, v)
                for s in n.get("sources", []):
                    if s not in cur["sources"]:
                        cur["sources"].append(s)
            else:
                nodes[n["id"]] = {**n, "meta": dict(n.get("meta") or {}), "sources": list(n.get("sources", []))}
        for e in gr.get("edges", []):
            key = (e["source"], e["target"], e["type"])
            if key in edges:
                if e.get("weight") is not None:
                    edges[key]["weight"] = max(edges[key].get("weight") or 0, e["weight"])
            else:
                edges[key] = dict(e)
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


def build_graph(adapter, data: dict) -> dict[str, list]:
    """Tek hedefin iliski grafigi. Karsilastirma modunda her profil ayri islenip birlestirilir."""
    if isinstance(data, dict) and data.get("compare_mode") and isinstance(data.get("profiles"), list):
        return merge_graphs([_single(adapter, p) for p in data["profiles"] if isinstance(p, dict)])
    return _single(adapter, data)


def edge_width(weight: float | None) -> float:  # frontend ile ayni formul (dokumantasyon)
    return 1.2 + (math.log2(weight) if weight and weight > 1 else 0)
