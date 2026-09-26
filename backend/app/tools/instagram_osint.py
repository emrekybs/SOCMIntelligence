#!/usr/bin/env python3
"""
Instagram OSINT — HikerAPI ile herkese acik hesap analizi (SOCMIntelligence).

Osintgram (Datalux) mantiginin SOCMIntelligence'a uyarlanmis hali. Instagram'a
KENDI hesabinla oturum ACMAZ; veriyi HikerAPI saglayicisindan ceker.
Anahtar: HIKERAPI_TOKEN (Ayarlar'dan girilir). Anahtar yoksa acikca "ORNEK VERI" doner.

Kapsam — hedef hesabin KENDI herkese acik verisi:
  profil + "About this account" (ulke, olusturma, kullanici adi degisim sayisi),
  bio linkleri, hesabin KENDI yayinladigi isletme iletisimi (public_email/telefon),
  hashtag'ler, gonderi konumlari (harita), acilis metinleri, begeni/yorum/medya
  istatistikleri, paylasim saatleri isi haritasi, foto alt metinleri,
  en cok yorum yapanlar, etiketleyenler, hedefin etiketledikleri,
  Instagram'in onerdigi iliskili hesaplar, hikaye/one cikan sayilari,
  takipci/takip ozeti.

Bilerek DAHIL EDILMEDI: hedefin takipcilerinin/takip ettiklerinin (ucuncu
sahislarin) e-posta ve telefon numaralarinin toplanmasi. Bu kisi grafigindeki
onayli olmayan insanlarin kisisel iletisim bilgisidir; SOCMIntelligence bunu
toplamaz.

  python instagram_osint.py nasa
  python instagram_osint.py https://www.instagram.com/nasa/ --posts 30
"""
from __future__ import annotations

import argparse
import os
import re
from collections import Counter
from datetime import datetime, timezone

import _toolkit as tk

DEFAULT_POSTS = 30
DEFAULT_COMMENT_POSTS = 12
MEDIA_TYPE = {1: "photo", 2: "video", 8: "carousel"}
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
# Hesabin KENDI yayinladigi isletme iletisimi + profil ustveri alanlari.
EXTRA_FIELDS = ("external_url", "public_email", "contact_phone_number", "public_phone_country_code",
                "public_phone_number", "whatsapp_number", "business_contact_method", "address_street",
                "city_name", "zip", "latitude", "longitude", "instagram_location_id", "category",
                "category_name", "business_category_name", "account_type", "is_memorialized", "fbid_v2",
                "total_clips_count", "total_igtv_videos", "usertags_count", "highlight_reel_count")


def normalize(raw: str) -> str | None:
    t = (raw or "").strip()
    if not t:
        return None
    m = re.search(r"instagram\.com/([^/?#\s]+)", t, re.I)
    if m:
        t = m.group(1)
    t = t.strip("/").lstrip("@").split("?")[0]
    return t if re.match(r"^[A-Za-z0-9._]{1,30}$", t) else None


# ─── HikerAPI istemcisi ───────────────────────────────────────────
def build_client(token: str | None):
    if not token:
        return None
    try:
        from hikerapi import Client  # type: ignore
    except ImportError:
        tk.fail("error", "hikerapi paketi kurulu degil: pip install hikerapi")
    return Client(token=token)


def _resp(result, key):
    """HikerAPI 'g2' cevaplari {response:{<key>:[...]}, next_page_id:...} seklinde."""
    if not isinstance(result, dict):
        return [], None
    return (result.get("response", {}) or {}).get(key, []) or [], result.get("next_page_id")


def _err(data):
    """HikerAPI hata sozlugunu gorunur mesajla exception'a cevir."""
    if isinstance(data, dict):
        msg = data.get("error") or data.get("exception") or data.get("message")
        if msg and not data.get("user") and not data.get("pk"):
            raise tk.HttpError(0, f"hikerapi: {msg}", str(msg))


class IG:
    def __init__(self, api, username: str):
        self.api = api
        self.username = username
        try:
            data = api.user_by_username_v2(username)
        except Exception as e:  # noqa: BLE001 - istemci hatasini gorunur yap
            raise tk.HttpError(0, f"hikerapi cagri hatasi: {e}", str(e))
        _err(data)
        if isinstance(data, dict) and data.get("detail") and not data.get("user"):
            tk.fail("not_found", f"@{username} bulunamadi: {data['detail']}")
        # bazi surumler user'i {"user": {...}} sarar, bazilari duz doner
        self.user = (data or {}).get("user") or (data if isinstance(data, dict) and data.get("pk") else {})
        if not self.user.get("pk"):
            hint = (data.get("error") or data.get("detail") or "") if isinstance(data, dict) else ""
            tk.fail("not_found", f"Instagram hesabi bulunamadi: {username}" + (f" ({hint})" if hint else ""))
        self.pk = self.user["pk"]
        self.private = bool(self.user.get("is_private"))

    # -- sayfalama --
    def _pages(self, method, key, limit, cursor="page_id"):
        out, nxt = [], None
        while len(out) < (limit or 1_000_000):
            try:
                res = method(self.pk, **({cursor: nxt} if nxt else {}))
            except Exception as e:  # noqa: BLE001 - butce/hata bitince eldekiyle don
                break
            items, nxt = _resp(res, key)
            out.extend(items)
            if not nxt or not items:
                break
        return out[:limit] if limit else out

    def feed(self, limit):
        return self._pages(self.api.user_medias_g2, "items", limit, cursor="next_page_id")

    def comments(self, media_id, limit=200):
        out, nxt = [], ""
        while len(out) < limit:
            try:
                res = self.api.media_comments_v2(media_id, page_id=nxt)
            except Exception as e:  # noqa: BLE001
                if "Entries not found" in str(e):
                    break
                break
            out.extend((res.get("response", {}) or {}).get("comments", []) or [])
            nxt = res.get("next_page_id")
            if not nxt:
                break
        return out[:limit]

    # -- profil --
    def profile(self):
        d = self.user
        info = {
            "id": d["pk"], "username": self.username, "full_name": d.get("full_name"),
            "biography": d.get("biography"), "follower_count": d.get("follower_count"),
            "following_count": d.get("following_count"), "media_count": d.get("media_count"),
            "is_private": d.get("is_private"), "is_business": d.get("is_business"),
            "is_verified": d.get("is_verified"),
            "profile_pic_url": (d.get("hd_profile_pic_url_info") or {}).get("url") or d.get("profile_pic_url"),
        }
        for k in EXTRA_FIELDS:
            if d.get(k) not in (None, "", [], {}):
                info[k] = d[k]
        info["bio_links"] = [{"title": l.get("title") or None, "url": l.get("url") or l.get("lynx_url")}
                             for l in (d.get("bio_links") or []) if isinstance(l, dict) and (l.get("url") or l.get("lynx_url"))]
        pr = [p for p in (d.get("pronouns") or []) if p]
        if pr:
            info["pronouns"] = "/".join(pr)
        return info

    def about(self):
        try:
            data = self.api.user_about_gql(str(self.pk))
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(data, dict) or not data:
            return None
        former = str(data.get("former_usernames") or "").strip()
        return {"country": data.get("country") or None, "date_joined": data.get("date") or None,
                "former_usernames_count": int(former) if former.isdigit() else (len(re.split(r"[,\n]", former)) if former else 0)}

    # -- icerik --
    @staticmethod
    def _play(p):
        return p.get("play_count") or p.get("ig_play_count") or p.get("view_count")

    @staticmethod
    def _coauthors(p):
        return [u.get("username") for u in p.get("coauthor_producers") or [] if u.get("username")]

    def _preview(self, p):
        code = p.get("code")
        path = "reel" if p.get("product_type") == "clips" else "p"
        cand = (p.get("image_versions2") or {}).get("candidates") or []
        return {"id": p.get("id"), "media_type": MEDIA_TYPE.get(p.get("media_type"), "other"),
                "thumbnail_url": cand[0]["url"] if cand else None,
                "permalink": f"https://www.instagram.com/{path}/{code}/" if code else None,
                "like_count": p.get("like_count"), "comment_count": p.get("comment_count"),
                "play_count": self._play(p), "taken_at": p.get("taken_at"),
                "caption": ((p.get("caption") or {}).get("text") or "")[:120],
                "author": (p.get("user") or {}).get("username")}

    # -- takipci / takip / medya (herkese acik) --
    @staticmethod
    def _sum_user(u):
        return {"id": u.get("pk"), "username": u.get("username"), "full_name": u.get("full_name"),
                "is_private": u.get("is_private"), "is_verified": u.get("is_verified")}

    def followers(self, limit):
        return [self._sum_user(u) for u in self._pages(self.api.user_followers_g2, "users", limit)]

    def followings(self, limit):
        return [self._sum_user(u) for u in self._pages(self.api.user_following_g2, "users", limit)]

    def stories(self):
        try:
            data = self.api.user_stories_v2(self.pk)
        except Exception:  # noqa: BLE001
            return []
        out = []
        for it in ((data or {}).get("reel") or {}).get("items", []) or []:
            cand = (it.get("image_versions2") or {}).get("candidates") or []
            img = cand[0]["url"] if cand else None
            if it.get("media_type") == 2 and it.get("video_versions"):
                out.append({"id": it.get("id"), "media_type": "video", "url": it["video_versions"][0]["url"],
                            "thumbnail_url": img, "taken_at": it.get("taken_at")})
            elif img:
                out.append({"id": it.get("id"), "media_type": "photo", "url": img, "taken_at": it.get("taken_at")})
        return out

    def highlights(self):
        try:
            data = self.api.user_highlights_v2(self.pk)
        except Exception:  # noqa: BLE001
            return []
        tray = (data.get("response", {}) or {}).get("tray") or [] if isinstance(data, dict) else []
        out = []
        for it in tray:
            cover = it.get("cover_media") or {}
            img = cover.get("cropped_image_version") or cover.get("full_image_version") or {}
            out.append({"id": (it.get("id") or "").split(":")[-1] or None, "title": it.get("title"),
                        "media_count": it.get("media_count"), "thumbnail_url": img.get("url"),
                        "created_at": it.get("created_at")})
        return out

    def photos(self, feed, limit):
        out = []
        for p in feed:
            link = self._preview(p)["permalink"]
            for m in (p.get("carousel_media") or [p]):
                if m.get("media_type") != 1:
                    continue
                cand = (m.get("image_versions2") or {}).get("candidates") or []
                if cand:
                    out.append({"id": m.get("id"), "url": cand[0]["url"],
                                "taken_at": m.get("taken_at") or p.get("taken_at"), "permalink": link})
                if len(out) >= limit:
                    return out
        return out


def analyze(ig: IG, posts: int, comment_posts: int, follow_limit: int = 150, photo_limit: int = 100) -> dict:
    prof = ig.profile()
    out = {"username": ig.username, "profile": prof, "about": ig.about(),
           "is_private": ig.private, "backend": "HikerAPI"}
    # Isletme adresi (hesabin kendi yayinladigi)
    if prof.get("latitude") and prof.get("longitude"):
        out["business_address"] = {"street": prof.get("address_street"), "city": prof.get("city_name"),
                                    "zip": prof.get("zip"), "lat": prof.get("latitude"), "lng": prof.get("longitude")}
    if ig.private:
        out["note"] = "Hesap gizli — yalnizca profil bilgileri okunabildi."
        return out

    feed = ig.feed(posts)
    out["scanned_posts"] = len(feed)

    # hashtag'ler + acilis metinleri
    htag = Counter()
    captions = []
    for p in feed:
        cap = (p.get("caption") or {}).get("text") or ""
        if cap:
            captions.append(cap[:400])
        for w in cap.split():
            if w.startswith("#") and len(w) > 1:
                htag[w] += 1
    out["hashtags"] = [{"hashtag": h, "count": c} for h, c in htag.most_common(40)]
    out["captions_sample"] = captions[:20]

    # medya + etkilesim istatistikleri
    likes = [int(p.get("like_count") or 0) for p in feed]
    coms = [int(p.get("comment_count") or 0) for p in feed]
    plays = [n for n in (ig._play(p) for p in feed if p.get("media_type") == 2) if n]
    n = len(feed)
    out["stats"] = {
        "posts": n,
        "photos": sum(1 for p in feed if p.get("media_type") == 1),
        "videos": sum(1 for p in feed if p.get("media_type") == 2),
        "carousels": sum(1 for p in feed if p.get("media_type") == 8),
        "likes_total": sum(likes), "likes_avg": sum(likes) // n if n else 0, "likes_max": max(likes) if likes else 0,
        "comments_total": sum(coms), "comments_avg": sum(coms) // n if n else 0, "comments_max": max(coms) if coms else 0,
        "video_plays_total": sum(plays), "video_plays_avg": sum(plays) // len(plays) if plays else 0,
        "engagement_rate": round((sum(likes) + sum(coms)) / n / max(prof.get("follower_count") or 1, 1) * 100, 3) if n else 0,
        "collaborations": sum(1 for p in feed if ig._coauthors(p)),
        "paid_partnerships": sum(1 for p in feed if p.get("is_paid_partnership")),
    }
    out["posts_preview"] = [ig._preview(p) for p in feed[:24]]

    # paylasim saatleri (UTC)
    times = sorted(p["taken_at"] for p in feed if p.get("taken_at"))
    by_wd = dict.fromkeys(WEEKDAYS, 0)
    by_h = {f"{h:02d}": 0 for h in range(24)}
    for tsec in times:
        w = datetime.fromtimestamp(tsec, tz=timezone.utc)
        by_wd[WEEKDAYS[w.weekday()]] += 1
        by_h[f"{w.hour:02d}"] += 1
    gaps = [(b - a) / 86400 for a, b in zip(times, times[1:])]
    out["posting_times"] = {
        "posts": len(times), "timezone": "UTC", "by_weekday": by_wd, "by_hour": by_h,
        "most_active_day": max(by_wd, key=by_wd.get) if times else None,
        "most_active_hour": f"{int(max(by_h, key=by_h.get)):02d}:00" if times else None,
        "first_post": datetime.fromtimestamp(times[0], tz=timezone.utc).strftime("%Y-%m-%d") if times else None,
        "last_post": datetime.fromtimestamp(times[-1], tz=timezone.utc).strftime("%Y-%m-%d") if times else None,
        "avg_days_between_posts": round(sum(gaps) / len(gaps), 1) if gaps else None,
    }

    # gonderi konumlari (harita)
    locs = {}
    for p in feed:
        loc = p.get("location") or {}
        if loc.get("lat") is not None and loc.get("lng") is not None:
            key = f"{loc['lat']},{loc['lng']}"
            if key not in locs or (p.get("taken_at") or 0) > (locs[key].get("taken_at") or 0):
                locs[key] = {"name": loc.get("name"), "lat": loc["lat"], "lng": loc["lng"],
                             "taken_at": p.get("taken_at"),
                             "time": datetime.fromtimestamp(p["taken_at"], tz=timezone.utc).strftime("%Y-%m-%d") if p.get("taken_at") else None}
    out["locations"] = sorted(locs.values(), key=lambda a: a.get("time") or "", reverse=True)

    # foto alt metinleri
    alt = []
    for p in feed:
        for m in (p.get("carousel_media") or [p]):
            if m.get("media_type") == 1 and m.get("accessibility_caption"):
                alt.append(m["accessibility_caption"])
    out["photo_alt_text"] = alt[:30]

    # yorum yapanlar + ham yorum dokumu (iliski grafigi)
    commenters = {}
    comments_raw = []
    for p in feed[:comment_posts]:
        link = ig._preview(p)["permalink"]
        for c in ig.comments(p.get("id"), limit=100):
            u = c.get("user") or {}
            pk = u.get("pk")
            if pk is None:
                continue
            e = commenters.setdefault(pk, {"id": pk, "username": u.get("username"), "full_name": u.get("full_name"), "count": 0})
            e["count"] += 1
            if len(comments_raw) < 500:
                comments_raw.append({"username": u.get("username"), "text": c.get("text"),
                                     "created_at": c.get("created_at"), "likes": c.get("comment_like_count"), "post_url": link})
    out["top_commenters"] = sorted(commenters.values(), key=lambda u: u["count"], reverse=True)[:40]
    out["comments"] = comments_raw

    # etiketleyenler
    taggers = {}
    for p in ig._pages(ig.api.user_tag_medias_v2, "items", 60):
        u = p.get("user") or {}
        pk = u.get("pk")
        if pk is None:
            continue
        e = taggers.setdefault(pk, {"id": pk, "username": u.get("username"), "full_name": u.get("full_name"), "count": 0})
        e["count"] += 1
    out["tagged_by"] = sorted(taggers.values(), key=lambda u: u["count"], reverse=True)[:40]

    # hedefin etiketledigi kisiler
    tagged = {}
    for p in feed:
        ut = p.get("usertags") or []
        if isinstance(ut, dict):
            ut = ut.get("in") or []
        for tg in ut:
            u = tg.get("user") or {}
            pk = u.get("pk")
            if pk is None:
                continue
            e = tagged.setdefault(pk, {"id": pk, "username": u.get("username"), "full_name": u.get("full_name"), "count": 0})
            e["count"] += 1
    out["tagged_users"] = sorted(tagged.values(), key=lambda u: u["count"], reverse=True)[:40]

    # Instagram'in onerdigi iliskili hesaplar
    try:
        sug = ig.api.user_suggested_profiles_v2(ig.pk)
        users = (sug.get("users") if isinstance(sug, dict) else None) or []
        out["suggested_profiles"] = [{"id": u.get("pk"), "username": u.get("username"),
                                      "full_name": u.get("full_name"), "is_verified": u.get("is_verified")}
                                     for u in users][:30]
    except Exception:  # noqa: BLE001
        out["suggested_profiles"] = []

    # hikaye + one cikan (medya URL'leri ile — indirmeye hazir)
    stories = ig.stories()
    out["active_stories"] = len(stories)
    out["stories"] = stories
    out["highlights"] = ig.highlights()

    # herkese acik fotograf listesi (toplu URL)
    out["photos"] = ig.photos(feed, photo_limit)
    out["profile_pic_hd"] = prof.get("profile_pic_url")

    # takipci / takip listeleri (herkese acik hesap icin)
    if follow_limit > 0:
        out["followers"] = ig.followers(follow_limit)
        out["followings"] = ig.followings(follow_limit)
    else:
        out["followers"] = []
        out["followings"] = []

    return out


# ─── ORNEK VERI (anahtar yoksa) ────────────────────────────────────
def mock(username: str) -> dict:
    return {
        "username": username, "mock": True, "backend": "HikerAPI (örnek veri)",
        "profile": {"id": "0", "username": username, "full_name": "Örnek Hesap", "biography": "Bu örnek veridir. Gerçek veri için Ayarlar'dan HIKERAPI_TOKEN girin.",
                    "follower_count": 12345, "following_count": 321, "media_count": 210, "is_verified": True, "is_business": True,
                    "public_email": "info@ornek.com", "category_name": "Software", "external_url": "https://ornek.com",
                    "bio_links": [{"title": "Site", "url": "https://ornek.com"}]},
        "about": {"country": "Türkiye", "date_joined": "2015", "former_usernames_count": 1},
        "is_private": False, "scanned_posts": 3,
        "hashtags": [{"hashtag": "#osint", "count": 3}, {"hashtag": "#siber", "count": 2}],
        "stats": {"posts": 3, "photos": 2, "videos": 1, "carousels": 0, "likes_total": 900, "likes_avg": 300,
                  "likes_max": 500, "comments_total": 45, "comments_avg": 15, "comments_max": 20,
                  "video_plays_total": 4000, "video_plays_avg": 4000, "engagement_rate": 7.65, "collaborations": 0, "paid_partnerships": 1},
        "posting_times": {"posts": 3, "timezone": "UTC", "by_weekday": dict.fromkeys(WEEKDAYS, 0) | {"Mon": 2, "Fri": 1},
                          "by_hour": {f"{h:02d}": (2 if h == 9 else 0) for h in range(24)},
                          "most_active_day": "Mon", "most_active_hour": "09:00", "first_post": "2024-01-01", "last_post": "2024-06-01", "avg_days_between_posts": 60.0},
        "locations": [{"name": "İstanbul", "lat": 41.0082, "lng": 28.9784, "time": "2024-06-01"}],
        "top_commenters": [{"id": "1", "username": "yorumcu1", "full_name": "Yorumcu", "count": 4}],
        "tagged_by": [], "tagged_users": [{"id": "2", "username": "arkadas", "full_name": None, "count": 1}],
        "suggested_profiles": [{"id": "3", "username": "benzer_hesap", "full_name": "Benzer", "is_verified": False}],
        "active_stories": 2, "highlights": [{"title": "Öne çıkan", "media_count": 5}],
        "photo_alt_text": [], "captions_sample": ["Örnek gönderi #osint"], "posts_preview": [],
    }


def draw_card(data: dict, path: str) -> None:
    """Profil kanit karti PNG'si — dis araca (tarayici) gerek yok, matplotlib ile cizilir.
    Zaman damgasi + profil JSON'unun SHA-256'si delil butunlugu icin gomulur."""
    import hashlib
    import json as _json
    import textwrap
    from datetime import datetime, timezone

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    p = data.get("profile") or {}
    about = data.get("about") or {}
    user = p.get("username") or data.get("username") or ""
    digest = hashlib.sha256(_json.dumps(p, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    fig = plt.figure(figsize=(7.4, 4.7), dpi=150)
    fig.patch.set_facecolor("#111823")
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off(); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.add_patch(plt.Rectangle((0, 0.9), 1, 0.1, color="#5f8ac2"))
    ax.text(0.03, 0.947, "SOCMIntelligence — Profil Kanıtı", color="#0b1017", fontsize=12, fontweight="bold", va="center")
    if data.get("mock"):
        ax.text(0.97, 0.947, "ÖRNEK VERİ", color="#0b1017", fontsize=9, fontweight="bold", va="center", ha="right")
    ax.text(0.03, 0.815, (p.get("full_name") or user)[:40], color="#e2e8f0", fontsize=15, fontweight="bold", va="center")
    vb = "  ✓" if p.get("is_verified") else ""
    ax.text(0.03, 0.745, "@" + user + vb, color="#9aa7b6", fontsize=11, family="monospace", va="center")
    stats = [("Takipçi", p.get("follower_count")), ("Takip", p.get("following_count")), ("Gönderi", p.get("media_count")),
             ("Doğrulanmış", "Evet" if p.get("is_verified") else "Hayır"),
             ("Kategori", p.get("category_name") or p.get("category") or "—"),
             ("İş e-posta", p.get("public_email") or "—"), ("Ülke", about.get("country") or "—"),
             ("Oluşturma", about.get("date_joined") or "—")]
    y = 0.64
    for k, v in stats:
        ax.text(0.03, y, k, color="#6b7889", fontsize=9.5, va="center")
        ax.text(0.28, y, str(v if v not in (None, "") else "—")[:28], color="#e2e8f0", fontsize=10, va="center")
        y -= 0.062
    bio = "\n".join(textwrap.wrap((p.get("biography") or "")[:260], 42))[:360]
    ax.text(0.56, 0.66, bio, color="#9aa7b6", fontsize=9, va="top", family="sans-serif")
    ax.add_patch(plt.Rectangle((0, 0), 1, 0.12, color="#0c121a"))
    ax.plot([0, 1], [0.12, 0.12], color="#202a37", lw=1)
    ax.text(0.03, 0.082, "Yakalama: " + ts, color="#9aa7b6", fontsize=8.5, va="center", family="monospace")
    ax.text(0.03, 0.038, "SHA-256: " + digest, color="#6b7889", fontsize=6.6, va="center", family="monospace")
    ax.text(0.97, 0.06, "instagram.com/" + user, color="#5f8ac2", fontsize=8.5, va="center", ha="right", family="monospace")
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description="Instagram OSINT (HikerAPI, oturumsuz)")
    ap.add_argument("target")
    ap.add_argument("--posts", type=int, default=DEFAULT_POSTS, help="Taranacak gonderi sayisi")
    ap.add_argument("--comment-posts", type=int, default=DEFAULT_COMMENT_POSTS, help="Yorumlari okunacak gonderi sayisi")
    ap.add_argument("--follow-limit", type=int, default=150, help="Cekilecek takipci/takip sayisi (0 = kapali)")
    ap.add_argument("--photo-limit", type=int, default=100, help="Toplu fotograf URL sayisi")
    ap.add_argument("--card", help="Profil kanit karti PNG yolu (cizilip cikilir, tarama yapilmaz)")
    args = ap.parse_args()

    username = normalize(args.target)
    if not username:
        tk.fail("error", f"Gecersiz Instagram kullanici adi / URL: {args.target}")

    token = os.environ.get("HIKERAPI_TOKEN") or os.environ.get("HIKER_API_KEY")
    if not token:
        if args.card:
            draw_card(mock(username), args.card)
            tk.emit({"card": args.card, "username": username, "mock": True})
            return
        tk.emit(mock(username))
        return

    api = build_client(token)
    try:
        ig = IG(api, username)
        if args.card:  # sadece profil + about (ucuz) — kart cizilir
            draw_card({"username": ig.username, "profile": ig.profile(), "about": ig.about()}, args.card)
            tk.emit({"card": args.card, "username": ig.username})
            return
        result = analyze(ig, max(1, min(args.posts, 60)), max(0, min(args.comment_posts, 24)),
                         follow_limit=max(0, min(args.follow_limit, 500)), photo_limit=max(0, min(args.photo_limit, 300)))
    except tk.HttpError as e:
        msg = e.body or str(e)
        low = msg.lower()
        if "not found" in low or "does not exist" in low or "not exist" in low:
            tk.fail("not_found", f"Instagram hesabi bulunamadi: {username}")
        if "limit" in low or "429" in low or "quota" in low or "402" in low or "credit" in low or "balance" in low:
            tk.fail("rate_limited", f"HikerAPI kota/kredi/hiz siniri: {msg}")
        if "401" in low or "403" in low or "token" in low or "auth" in low or "unauthor" in low or "forbidden" in low:
            tk.fail("error", f"HikerAPI anahtari gecersiz/yetkisiz: {msg}")
        tk.fail("error", f"HikerAPI hatasi: {msg}")
    tk.emit(result)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 - araç asla traceback'le çökmesin
        tk.fail("error", f"Instagram aracı beklenmedik hata: {e}")
