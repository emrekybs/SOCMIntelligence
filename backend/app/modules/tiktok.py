"""
TikTok OSINT modulu - SOCMIntelligence platformu.

Tool: tools/tiktok_osint.py
  Input tipleri:
    charlidamelio                          -> username
    @khaby.lame                            -> username
    https://www.tiktok.com/@nadorlily      -> username
  Hepsi tek username'e normalize edilir.

Cikti: tiktok_<username>_<ts>.json (auto-output) + tiktok_<username>_growth.png
Growth chart Snapchat heatmap pattern'inda: scan'de atla, isteyince endpoint'ten al.
"""
from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from app.celery_app import celery_app
from app.core.adapter import PlatformAdapter
from app.core.cache import cache
from app.schemas.common import JobCreated


# ═════════════════════════════════════════════════════════════════
# 1. SCHEMAS
# ═════════════════════════════════════════════════════════════════

class TikTokHashtagAnalysis(BaseModel):
    top_tags: list[dict[str, Any]] = Field(default_factory=list)
    top_niche: str | None = None
    niche_scores: dict[str, Any] = Field(default_factory=dict)
    unique_tags: int = 0
    total_uses: int = 0


class TikTokScheduleAnalysis(BaseModel):
    day_dist: dict[str, int] = Field(default_factory=dict)
    hour_dist: dict[str, int] = Field(default_factory=dict)
    best_day_name: str | None = None
    best_hour_str: str | None = None


class TikTokMentionNetwork(BaseModel):
    total: int = 0
    unique: int = 0
    top: list[dict[str, Any]] = Field(default_factory=list)


class TikTokGrowthPoint(BaseModel):
    date: str | None = None
    followers: int | None = None
    likes: int | None = None
    video_count: int | None = None
    estimated: bool = False


class TikTokProfile(BaseModel):
    """TikTok tool cikti shape'i - tek hesap."""
    username: str
    display_name: str | None = None
    user_id: str | None = None
    bio: str | None = None
    verified: bool | None = None
    private: bool | None = None
    region: str | None = None
    language: str | None = None
    create_time: int | None = None
    profile_image: str | None = None
    profile_url: str | None = None

    # Counts
    followers: int | None = None
    following: int | None = None
    likes: int | None = None
    video_count: int | None = None
    friend_count: int | None = None

    # Derived
    engagement_rate: float | None = None
    account_age_days: int | None = None
    followers_per_day: float | None = None
    fake_score: int | None = None
    fake_label: str | None = None

    # Nested
    videos: list[dict[str, Any]] = Field(default_factory=list)
    viral_videos: list[dict[str, Any]] = Field(default_factory=list)
    hashtag_analysis: TikTokHashtagAnalysis | None = None
    schedule_analysis: TikTokScheduleAnalysis | None = None
    mention_network: TikTokMentionNetwork | None = None
    bio_link: dict[str, Any] = Field(default_factory=dict)
    comment_analysis: dict[str, Any] = Field(default_factory=dict)
    posting_frequency: dict[str, Any] = Field(default_factory=dict)
    growth_history: list[TikTokGrowthPoint] = Field(default_factory=list)
    avatar_path: str | None = None


# ═════════════════════════════════════════════════════════════════
# 2. ADAPTER
# ═════════════════════════════════════════════════════════════════

class TikTokAdapter(PlatformAdapter):
    platform = "tiktok"
    script = "tiktok_osint.py"
    capabilities = ["scan", "growth_chart_png"]
    cache_ttl = 600  # 10dk

    def classify(self, raw: str) -> tuple[str, str]:
        """
        Tek tip: username. Tum varyantlar (@prefix, URL) tek username'e normalize.
          "charlidamelio"                            -> ("username", "charlidamelio")
          "@khaby.lame"                              -> ("username", "khaby.lame")
          "https://www.tiktok.com/@nadorlily"        -> ("username", "nadorlily")
          "tiktok.com/@user"                         -> ("username", "user")
        """
        t = (raw or "").strip().rstrip("/")
        if not t:
            raise ValueError("Bos input")

        # URL form
        m = re.search(r"tiktok\.com/@([^/?&#\s]+)", t, re.I)
        if m:
            username = m.group(1)
        else:
            # @-prefix strip
            username = t.lstrip("@").strip()

        # TikTok username: 2-24 karakter, alphanumeric + . _
        if not re.match(r"^[A-Za-z0-9._]{2,24}$", username):
            raise ValueError(f"Gecersiz TikTok username: {raw}")

        return ("username", username)

    async def scan(
        self, target_type: str, value: str,
        compare_with: list[str] | None = None,
        video_count: int | None = None,
    ) -> dict[str, Any]:
        if target_type != "username":
            raise ValueError(f"Desteklenmeyen tip: {target_type}")

        vc = max(5, min(35, int(video_count or 20)))  # TikTok tool range: 5-35
        tool_args: list[str] = [value]

        # Compare mode: ek username'leri ekle + --compare
        if compare_with:
            tool_args.extend(compare_with[:4])  # max 5 total (primary + 4)
            tool_args.append("--compare")

        tool_args.extend(["--videos", str(vc)])

        try:
            result = await self._run_tool_auto_output(
                target_type=target_type,
                value=value,
                args=tool_args,
                output_pattern="tiktok_*.json",
                timeout=180 if compare_with else 120,
            )
        except RuntimeError as e:
            msg = str(e).lower()
            # Bot-block / rate-limit -> hesap yok DEGIL; tekrar denenebilir (RATE_LIMITED)
            if ("blocked" in msg or "rate-limit" in msg or "rate limit" in msg
                    or "captcha" in msg or "429" in msg or "bot-block" in msg):
                raise RuntimeError(
                    f"rate_limit: TikTok su an istegi engelledi (bot-block/rate-limit): {value}. "
                    f"Birkac dakika sonra tekrar tarayin."
                )
            # Gercekten olmayan / erisilemeyen hesap
            if ("not found" in msg or "does not exist" in msg or "hesap yok" in msg
                    or "bulunamadi" in msg or "no profiles" in msg):
                raise LookupError(
                    f"TikTok hesabi bulunamadi: {value}. "
                    f"(Yanlis kullanici adi veya kaldirilmis hesap olabilir)"
                )
            raise

        # Compare mode JSON'u array doner (birden fazla profil).
        # Frontend tek obje bekliyor, compare ise 'profiles' array'i ile return.
        if isinstance(result, list):
            if not result:
                raise LookupError(f"TikTok: hicbir profil bulunamadi")
            return {
                "username": result[0].get("username"),
                "compare_mode": True,
                "profiles": result,
                "compared_count": len(result),
            }

        if not result.get("username"):
            raise LookupError(f"TikTok hesabi bulunamadi: {value}")

        try:
            validated = TikTokProfile.model_validate(result)
            return validated.model_dump(mode="json")
        except Exception:
            return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return TikTokGraphConverter.convert(data)


# ═════════════════════════════════════════════════════════════════
# 3. GRAPH CONVERTER
# ═════════════════════════════════════════════════════════════════

class TikTokGraphConverter:
    """
    TikTok -> graph:
      person (central) + username + bio_link (if URL) -> domain
      mention_network.top -> username[] (linked_to, weak signal)
      hashtag top_niche -> meta only (not node)
    """

    @staticmethod
    def convert(data: dict[str, Any]) -> dict[str, list]:
        nodes: list[dict] = []
        edges: list[dict] = []

        username = data.get("username")
        if not username:
            return {"nodes": nodes, "edges": edges}

        # Person node
        person_id = f"p_tiktok_{_slug(username)}"
        nodes.append({
            "id": person_id,
            "type": "person",
            "label": data.get("display_name") or username,
            "meta": {
                "Platform": "TikTok",
                "Username": username,
                "Bio": _trunc(data.get("bio") or "—", 100),
                "Followers": str(data.get("followers") or 0),
                "Following": str(data.get("following") or 0),
                "Videos": str(data.get("video_count") or 0),
                "Verified": "Yes" if data.get("verified") else "No",
                "Private": "Yes" if data.get("private") else "No",
                "Region": data.get("region") or "—",
                "Fake_Score": f"{data.get('fake_score', '?')} ({data.get('fake_label', '—')})",
            },
        })

        # Username node
        u_id = f"u_tiktok_{_slug(username)}"
        nodes.append({
            "id": u_id,
            "type": "username",
            "label": f"@{username}",
            "meta": {
                "Platforms": "TikTok",
                "Profile": data.get("profile_url") or f"https://www.tiktok.com/@{username}",
                "Followers": str(data.get("followers") or 0),
            },
        })
        edges.append({
            "id": f"ed_{person_id}_{u_id}",
            "source": person_id, "target": u_id, "type": "owns",
        })

        # Bio link (if URL) -> domain
        bio_link = data.get("bio_link") or {}
        bio_url = bio_link.get("url") if isinstance(bio_link, dict) else None
        if bio_url:
            dom = _extract_domain(bio_url)
            if dom:
                d_id = f"d_ext_{_slug(dom)}"
                if not _has_node(nodes, d_id):
                    nodes.append({
                        "id": d_id,
                        "type": "domain",
                        "label": dom,
                        "meta": {
                            "Source": "TikTok bio link",
                            "URL": bio_url,
                            "Platform": bio_link.get("platform") or "Link",
                        },
                    })
                edges.append({
                    "id": f"ed_{person_id}_{d_id}",
                    "source": person_id, "target": d_id, "type": "owns",
                })

        # Mention network top -> username nodes (linked_to, weak)
        mn = data.get("mention_network") or {}
        for m in (mn.get("top") or [])[:8]:
            if not isinstance(m, dict):
                continue
            mentioned = m.get("account")
            if not mentioned or mentioned == username:
                continue
            m_id = f"u_tiktok_{_slug(mentioned)}"
            if not _has_node(nodes, m_id):
                nodes.append({
                    "id": m_id,
                    "type": "username",
                    "label": f"@{mentioned}",
                    "meta": {
                        "Platforms": "TikTok",
                        "Source": f"Mentioned by @{username}",
                        "Mention_count": str(m.get("count") or 0),
                    },
                })
            edges.append({
                "id": f"ed_{person_id}_{m_id}_mention",
                "source": person_id, "target": m_id, "type": "linked_to",
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


# ═════════════════════════════════════════════════════════════════
# 4. ROUTER — scan + growth chart PNG
# ═════════════════════════════════════════════════════════════════

router = APIRouter(prefix="/api/socmint/tiktok", tags=["tiktok"])


class TikTokTarget(BaseModel):
    raw: str = Field(..., min_length=1, max_length=200)
    compare_with: list[str] | None = Field(default=None, max_length=4)
    video_count: int | None = Field(default=None, ge=5, le=35)


class TikTokScanRequest(BaseModel):
    targets: list[TikTokTarget] = Field(..., min_length=1, max_length=5)


@router.get("/capabilities")
def tiktok_capabilities() -> dict[str, Any]:
    return {
        "platform": "tiktok",
        "capabilities": TikTokAdapter.capabilities,
        "input_types": ["username"],
        "input_examples": [
            "charlidamelio",
            "@khaby.lame",
            "https://www.tiktok.com/@nadorlily",
            "charlidamelio @khaby.lame @zachking  (space-separated = compare mode)",
        ],
        "extras": {
            "compare_with": "list[str] up to 4 other usernames for comparison",
            "video_count": "int 5-35 (default 20)",
        },
    }


@router.post("/scan", response_model=JobCreated)
def tiktok_scan(req: TikTokScanRequest) -> JobCreated:
    adapter = TikTokAdapter()
    classified: list[dict[str, Any]] = []
    for t in req.targets:
        try:
            target_type, value = adapter.classify(t.raw)
            item: dict[str, Any] = {"raw": t.raw, "type": target_type, "value": value}
            if t.compare_with:
                item["compare_with"] = t.compare_with
            if t.video_count is not None:
                item["video_count"] = t.video_count
            classified.append(item)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Gecersiz input '{t.raw}': {e}")

    task = celery_app.send_task("scan_platform_targets", args=["tiktok", classified])

    from app.routers.jobs import register_job
    register_job(task.id, "tiktok", len(classified))

    return JobCreated(
        job_id=task.id, platform="tiktok", target_count=len(classified),
    )


@router.post("/classify")
def tiktok_classify(req: TikTokTarget) -> dict[str, str]:
    try:
        adapter = TikTokAdapter()
        t, v = adapter.classify(req.raw)
        return {"type": t, "value": v, "raw": req.raw}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/growth/{username}")
async def tiktok_growth_png(username: str):
    """
    Growth chart PNG — Snapchat heatmap pattern'i.
    Scan sirasinda tool PNG uretiyor ama cwd temp'te oluyor, alip cacheliyoruz.
    """
    adapter = TikTokAdapter()
    try:
        _, clean = adapter.classify(username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    cache_key = f"growth:tiktok:{clean}"
    cached = await cache.get(cache_key)
    if cached and isinstance(cached, dict) and cached.get("png_base64"):
        png_bytes = base64.b64decode(cached["png_base64"])
        return Response(
            content=png_bytes, media_type="image/png",
            headers={"Content-Disposition": f'inline; filename="growth_{clean}.png"'},
        )

    # Generate - tool'u calistir, cwd'deki .png'yi yakala
    import tempfile, asyncio, os
    from app.core.tool_runner import TOOLS_DIR

    with tempfile.TemporaryDirectory(prefix="tiktok_gw_") as tmpdir:
        tmpdir_path = Path(tmpdir)
        script_path = TOOLS_DIR / "tiktok_osint.py"
        if not script_path.exists():
            raise HTTPException(status_code=500, detail="TikTok tool bulunamadi")

        proc = await asyncio.create_subprocess_exec(
            "python3", "-u", str(script_path), clean, "--videos", "5",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(tmpdir_path),
            env={**os.environ},
        )
        try:
            _, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=90)
        except asyncio.TimeoutError:
            proc.kill(); await proc.wait()
            raise HTTPException(status_code=504, detail="Growth chart timeout")

        # PNG dosyasini bul
        pngs = sorted(tmpdir_path.glob("tiktok_*_growth.png"))
        if not pngs:
            raise HTTPException(status_code=404, detail="Growth PNG olusturulamadi")
        png_bytes = pngs[0].read_bytes()

        await cache.set(
            cache_key,
            {"png_base64": base64.b64encode(png_bytes).decode("ascii")},
            ttl=86400,
        )

        return Response(
            content=png_bytes, media_type="image/png",
            headers={"Content-Disposition": f'inline; filename="growth_{clean}.png"'},
        )
