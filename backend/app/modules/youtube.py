"""
YouTube OSINT modulu - SOCMIntelligence platformu.

Tool: tools/youtube_osint.py
  Input tipleri (hepsi @handle'a normalize):
    @MrBeast                               -> ("handle", "@MrBeast")
    MrBeast                                -> ("handle", "@MrBeast")
    https://youtube.com/@MrBeast           -> ("handle", "@MrBeast")
    UCX6OQ3DkcsbYNE6H8uQQuVA               -> ("channel_id", "UCX6...")
    https://youtube.com/channel/UC...      -> ("channel_id", "UC...")

Key feature: brandingSettings'dan gelen social_accounts graph'a **cross-platform**
olarak baglanir (Instagram, Twitter, TikTok, Patreon, etc).
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.celery_app import celery_app
from app.core.adapter import PlatformAdapter
from app.schemas.common import JobCreated


# ═════════════════════════════════════════════════════════════════
# 1. SCHEMAS
# ═════════════════════════════════════════════════════════════════

class YouTubeChannel(BaseModel):
    title: str | None = None
    handle: str | None = None
    description: str | None = None
    channel_url: str | None = None
    country: str | None = None
    created_date: str | None = None
    account_age: str | None = None
    account_age_days: int | None = None
    subscribers: int | None = None
    total_views: int | None = None
    video_count: int | None = None
    avg_views_per_video: int | None = None
    subs_per_day: float | None = None
    views_per_day: int | None = None
    verified: bool | None = None
    made_for_kids: bool | None = None
    keywords: str | None = None


class YouTubeVideo(BaseModel):
    title: str | None = None
    video_id: str | None = None
    url: str | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    date: str | None = None
    duration: str | None = None
    category: str | None = None


class YouTubeVideoAnalysis(BaseModel):
    total: int = 0
    avg_views: int | None = None
    avg_likes: int | None = None
    avg_engagement_pct: float | None = None
    median_views: int | None = None
    total_duration_h: float | None = None
    duration_buckets: dict[str, int] = Field(default_factory=dict)
    best_upload_hour: str | None = None
    best_upload_day: str | None = None
    timezone_est: str | None = None
    hour_distribution: dict[str, int] = Field(default_factory=dict)
    day_distribution: dict[str, int] = Field(default_factory=dict)
    top_tags: list[dict[str, Any]] = Field(default_factory=list)
    top_categories: list[dict[str, Any]] = Field(default_factory=list)
    viral_videos: list[YouTubeVideo] = Field(default_factory=list)
    top_by_views: list[YouTubeVideo] = Field(default_factory=list)
    top_by_likes: list[YouTubeVideo] = Field(default_factory=list)
    latest_videos: list[YouTubeVideo] = Field(default_factory=list)


class YouTubeSocialAccount(BaseModel):
    """bio_data.social_accounts + branding.channel.links'ten extract edilen."""
    platform: str | None = None
    title: str | None = None
    url: str | None = None
    handle: str | None = None


class YouTubeBioData(BaseModel):
    urls: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    social_accounts: list[YouTubeSocialAccount] = Field(default_factory=list)


class YouTubeCommentAnalysis(BaseModel):
    total_comments: int = 0
    videos_scanned: int = 0
    top_commenters: list[dict[str, Any]] = Field(default_factory=list)
    top_liked_comments: list[dict[str, Any]] = Field(default_factory=list)
    sentiment: dict[str, Any] = Field(default_factory=dict)


class YouTubePlaylist(BaseModel):
    title: str | None = None
    video_count: int | None = None
    url: str | None = None


class YouTubeResult(BaseModel):
    target: str
    scanned_at: str | None = None
    channel_id: str | None = None
    channel_url: str | None = None
    channel: YouTubeChannel | None = None
    bio_data: YouTubeBioData | None = None
    playlists: list[YouTubePlaylist] = Field(default_factory=list)
    video_analysis: YouTubeVideoAnalysis | None = None
    fake_score: dict[str, Any] = Field(default_factory=dict)
    comment_analysis: YouTubeCommentAnalysis | None = None
    error: str | None = None


# ═════════════════════════════════════════════════════════════════
# 2. ADAPTER
# ═════════════════════════════════════════════════════════════════

class YouTubeAdapter(PlatformAdapter):
    platform = "youtube"
    script = "youtube_osint.py"
    capabilities = ["scan"]
    cache_ttl = 600
    env_keys = ["YOUTUBE_API_KEY"]  # Tool API key'e ihtiyac duyar

    def classify(self, raw: str) -> tuple[str, str]:
        """
        @handle veya channel_id tipleri:
          "@MrBeast" -> ("handle", "@MrBeast")
          "MrBeast"  -> ("handle", "@MrBeast")
          "UCX6OQ3DkcsbYNE6H8uQQuVA" -> ("channel_id", "UCX6OQ3DkcsbYNE6H8uQQuVA")
          "https://youtube.com/@MrBeast" -> ("handle", "@MrBeast")
          "https://youtube.com/channel/UC..." -> ("channel_id", "UC...")
        """
        t = (raw or "").strip().rstrip("/")
        if not t:
            raise ValueError("Bos input")

        # Channel ID (UC...)
        if re.match(r"^UC[A-Za-z0-9_\-]{22}$", t):
            return ("channel_id", t)

        # URL /channel/UCxxx
        m = re.search(r"youtube\.com/channel/(UC[A-Za-z0-9_\-]{22})", t, re.I)
        if m:
            return ("channel_id", m.group(1))

        # URL /@handle
        m = re.search(r"youtube\.com/@([A-Za-z0-9_.\-]+)", t, re.I)
        if m:
            return ("handle", "@" + m.group(1))

        # URL /user/xxx or /c/xxx
        m = re.search(r"youtube\.com/(?:user|c)/([A-Za-z0-9_.\-]+)", t, re.I)
        if m:
            return ("handle", "@" + m.group(1))

        # @handle or bare name
        clean = t.lstrip("@").strip()
        if not re.match(r"^[A-Za-z0-9_.\-]{2,30}$", clean):
            raise ValueError(f"Gecersiz YouTube hedefi: {raw}")
        return ("handle", "@" + clean)

    async def scan(
        self, target_type: str, value: str,
        compare_with: list[str] | None = None,
        video_count: int | None = None,
    ) -> dict[str, Any]:
        if target_type not in ("handle", "channel_id"):
            raise ValueError(f"Desteklenmeyen tip: {target_type}")

        vc = max(5, min(50, int(video_count or 20)))
        tool_args: list[str] = [value]

        if compare_with:
            tool_args.extend(compare_with[:4])
            tool_args.append("--compare")

        tool_args.extend(["--no-color", "--videos", str(vc)])

        try:
            result = await self._run_tool_auto_output(
                target_type=target_type,
                value=value,
                args=tool_args,
                output_pattern="youtube_*.json",
                env_keys=self.env_keys,
                timeout=240 if compare_with else 150,
            )
        except RuntimeError as e:
            msg = str(e).lower()
            if "api key" in msg or "403" in msg or "quota" in msg:
                raise RuntimeError(
                    f"YouTube API key hatasi: .env'de YOUTUBE_API_KEY dolu mu? "
                    f"Quota asildi olabilir. Detay: {e}"
                )
            if "channel not found" in msg or "not found" in msg:
                raise LookupError(f"YouTube kanali bulunamadi: {value}")
            raise

        # Compare mode array doner
        if isinstance(result, list):
            if not result:
                raise LookupError(f"YouTube: hicbir kanal bulunamadi")
            return {
                "target": result[0].get("target", value),
                "channel_id": result[0].get("channel_id"),
                "channel": result[0].get("channel"),
                "compare_mode": True,
                "profiles": result,
                "compared_count": len(result),
            }

        if result.get("error"):
            err_msg = result["error"].lower()
            if "not found" in err_msg:
                raise LookupError(result["error"])
            raise RuntimeError(result["error"])

        if not result.get("channel_id"):
            raise LookupError(f"YouTube kanali bulunamadi: {value}")

        try:
            validated = YouTubeResult.model_validate(result)
            return validated.model_dump(mode="json")
        except Exception:
            return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return YouTubeGraphConverter.convert(data)


# ═════════════════════════════════════════════════════════════════
# 3. GRAPH CONVERTER — cross-platform edges burada cikar
# ═════════════════════════════════════════════════════════════════

class YouTubeGraphConverter:
    """
    YouTube -> graph:
      person + @handle -> owns
      bio_data.social_accounts[] -> cross-platform username nodes
      (Instagram, Twitter, TikTok, Patreon, etc.)
      Bu SOCMIntelligence'in gucu: YT'den @khaby.lame TikTok'ta da varsa,
      ayni `u_tiktok_khaby_lame` node'una baglanir.
    """

    # Platform isimlerini bizim node ID prefix'lerimize map et
    PLATFORM_MAP = {
        "instagram": "instagram",
        "twitter/x": "twitter",
        "twitter": "twitter",
        "x": "twitter",
        "tiktok": "tiktok",
        "facebook": "facebook",
        "twitch": "twitch",
        "discord": "discord",
        "telegram": "telegram",
        "spotify": "spotify",
        "patreon": "patreon",
        "github": "github",
        "kick": "kick",
        "snapchat": "snapchat",
        "linkedin": "linkedin",
        "reddit": "reddit",
    }

    @staticmethod
    def convert(data: dict[str, Any]) -> dict[str, list]:
        nodes: list[dict] = []
        edges: list[dict] = []

        channel = data.get("channel") or {}
        channel_id = data.get("channel_id")
        title = channel.get("title") or data.get("target") or "unknown"
        handle = channel.get("handle") or data.get("target") or ""
        handle_clean = handle.lstrip("@") if handle else _slug(title)

        # Person node
        person_id = f"p_youtube_{_slug(handle_clean)}"
        nodes.append({
            "id": person_id,
            "type": "person",
            "label": title,
            "meta": {
                "Platform": "YouTube",
                "Channel_ID": channel_id or "—",
                "Handle": handle or "—",
                "Country": channel.get("country") or "—",
                "Description": _trunc(channel.get("description") or "—", 120),
                "Created": channel.get("created_date") or "—",
                "Age": channel.get("account_age") or "—",
                "Subscribers": str(channel.get("subscribers") or 0),
                "Total_views": str(channel.get("total_views") or 0),
                "Videos": str(channel.get("video_count") or 0),
                "Verified": "Yes" if channel.get("verified") else "No",
            },
        })

        # YouTube-specific username node
        u_id = f"u_youtube_{_slug(handle_clean)}"
        nodes.append({
            "id": u_id,
            "type": "username",
            "label": handle or f"@{handle_clean}",
            "meta": {
                "Platforms": "YouTube",
                "Profile": channel.get("channel_url") or data.get("channel_url") or "",
                "Channel_ID": channel_id or "—",
                "Subscribers": str(channel.get("subscribers") or 0),
            },
        })
        edges.append({
            "id": f"ed_{person_id}_{u_id}",
            "source": person_id, "target": u_id, "type": "owns",
        })

        # ─── CROSS-PLATFORM — bio_data.social_accounts ─────────────
        bio = data.get("bio_data") or {}
        for acc in (bio.get("social_accounts") or [])[:15]:
            if not isinstance(acc, dict):
                continue
            url = acc.get("url") or ""
            platform_raw = (acc.get("platform") or "").lower().strip()
            if not url or not platform_raw:
                continue

            platform_key = YouTubeGraphConverter.PLATFORM_MAP.get(
                platform_raw, _slug(platform_raw)
            )
            # URL'den handle extract et
            ext_handle = _extract_handle_from_url(url, platform_key)
            if not ext_handle:
                continue

            # Node ID - diger modullerle cross-module merge olabilir
            # Orn. u_tiktok_khaby_lame
            sn_id = f"u_{platform_key}_{_slug(ext_handle)}"
            if not _has_node(nodes, sn_id):
                nodes.append({
                    "id": sn_id,
                    "type": "username",
                    "label": f"@{ext_handle}" if not ext_handle.startswith("@") else ext_handle,
                    "meta": {
                        "Platforms": acc.get("platform") or platform_raw.title(),
                        "Source": "YouTube About links",
                        "URL": url,
                        "Title": acc.get("title") or "—",
                    },
                })
            edges.append({
                "id": f"ed_{person_id}_{sn_id}_social",
                "source": person_id, "target": sn_id, "type": "linked_to",
            })

        # Bio emails
        for em in (bio.get("emails") or [])[:5]:
            if not em or "@" not in em:
                continue
            e_id = f"e_{_slug(em)}"
            if not _has_node(nodes, e_id):
                nodes.append({
                    "id": e_id,
                    "type": "email",
                    "label": em,
                    "meta": {"Source": "YouTube description"},
                })
            edges.append({
                "id": f"ed_{person_id}_{e_id}",
                "source": person_id, "target": e_id, "type": "owns",
            })

        # Bio URLs -> external domains
        for url in (bio.get("urls") or [])[:5]:
            dom = _extract_domain(url)
            if not dom or "youtube.com" in dom:
                continue
            d_id = f"d_ext_{_slug(dom)}"
            if not _has_node(nodes, d_id):
                nodes.append({
                    "id": d_id,
                    "type": "domain",
                    "label": dom,
                    "meta": {"Source": "YouTube description", "URL": url},
                })
            edges.append({
                "id": f"ed_{person_id}_{d_id}",
                "source": person_id, "target": d_id, "type": "linked_to",
            })

        return _dedup_graph({"nodes": nodes, "edges": edges})


# ─── Helpers ─────────────────────────────────────────────────────

def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", (s or "").lower()).strip("_")[:40]


def _has_node(nodes: list[dict], node_id: str) -> bool:
    return any(n["id"] == node_id for n in nodes)


def _dedup_graph(g: dict[str, list]) -> dict[str, list]:
    seenN, seenE = set(), set()
    nodes, edges = [], []
    for n in g["nodes"]:
        if n["id"] not in seenN:
            seenN.add(n["id"])
            nodes.append(n)
    for e in g["edges"]:
        if e["id"] not in seenE:
            seenE.add(e["id"])
            edges.append(e)
    return {"nodes": nodes, "edges": edges}


def _extract_domain(url: str) -> str | None:
    m = re.search(r"(?:https?://)?([A-Za-z0-9][A-Za-z0-9\-.]+\.[A-Za-z]{2,})", url or "")
    return m.group(1).lower().rstrip("/") if m else None


def _trunc(s: str, n: int) -> str:
    s = (s or "").replace("\n", " ").replace("\r", " ")
    return s[:n] + "…" if len(s) > n else s


def _extract_handle_from_url(url: str, platform: str) -> str | None:
    """URL'den platform-specific handle cikart."""
    if not url:
        return None
    patterns = {
        "instagram": r"instagram\.com/([A-Za-z0-9_.]+)",
        "twitter":   r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)",
        "tiktok":    r"tiktok\.com/@([A-Za-z0-9_.]+)",
        "facebook":  r"facebook\.com/([A-Za-z0-9_.\-]+)",
        "twitch":    r"twitch\.tv/([A-Za-z0-9_]+)",
        "telegram":  r"t\.me/([A-Za-z0-9_]+)",
        "spotify":   r"spotify\.com/(?:artist|user)/([A-Za-z0-9]+)",
        "patreon":   r"patreon\.com/([A-Za-z0-9_\-]+)",
        "github":    r"github\.com/([A-Za-z0-9\-]+)",
        "snapchat":  r"snapchat\.com/(?:add/|@)([A-Za-z0-9_.\-]+)",
        "reddit":    r"reddit\.com/(?:user|u)/([A-Za-z0-9_\-]+)",
        "linkedin":  r"linkedin\.com/in/([A-Za-z0-9\-]+)",
    }
    pattern = patterns.get(platform)
    if pattern:
        m = re.search(pattern, url, re.I)
        if m:
            return m.group(1)
    # Fallback: URL'nin son segmenti
    m = re.search(r"/([A-Za-z0-9_.\-@]+)/?$", url)
    return m.group(1) if m else None


# ═════════════════════════════════════════════════════════════════
# 4. ROUTER
# ═════════════════════════════════════════════════════════════════

router = APIRouter(prefix="/api/socmint/youtube", tags=["youtube"])


class YouTubeTarget(BaseModel):
    raw: str = Field(..., min_length=1, max_length=200)
    compare_with: list[str] | None = Field(default=None, max_length=4)
    video_count: int | None = Field(default=None, ge=5, le=50)


class YouTubeScanRequest(BaseModel):
    targets: list[YouTubeTarget] = Field(..., min_length=1, max_length=5)


@router.get("/capabilities")
def yt_capabilities() -> dict[str, Any]:
    return {
        "platform": "youtube",
        "capabilities": YouTubeAdapter.capabilities,
        "input_types": ["handle", "channel_id"],
        "input_examples": [
            "@MrBeast",
            "MrBeast",
            "https://youtube.com/@MrBeast",
            "UCX6OQ3DkcsbYNE6H8uQQuVA",
            "https://youtube.com/channel/UCX6OQ3DkcsbYNE6H8uQQuVA",
            "@MrBeast @PewDiePie @Veritasium  (space-separated = compare mode)",
        ],
        "extras": {
            "compare_with": "list[str] up to 4 other handles/channel IDs",
            "video_count": "int 5-50 (default 20)",
        },
        "requires_env": ["YOUTUBE_API_KEY"],
    }


@router.post("/scan", response_model=JobCreated)
def yt_scan(req: YouTubeScanRequest) -> JobCreated:
    adapter = YouTubeAdapter()
    classified: list[dict[str, Any]] = []
    for t in req.targets:
        try:
            tt, v = adapter.classify(t.raw)
            item: dict[str, Any] = {"raw": t.raw, "type": tt, "value": v}
            if t.compare_with:
                item["compare_with"] = t.compare_with
            if t.video_count is not None:
                item["video_count"] = t.video_count
            classified.append(item)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Gecersiz input '{t.raw}': {e}")

    task = celery_app.send_task("scan_platform_targets", args=["youtube", classified])

    from app.routers.jobs import register_job
    register_job(task.id, "youtube", len(classified))

    return JobCreated(
        job_id=task.id, platform="youtube", target_count=len(classified),
    )


@router.post("/classify")
def yt_classify(req: YouTubeTarget) -> dict[str, str]:
    try:
        adapter = YouTubeAdapter()
        t, v = adapter.classify(req.raw)
        return {"type": t, "value": v, "raw": req.raw}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
