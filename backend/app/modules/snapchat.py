"""
Snapchat OSINT modulu - SOCMIntelligence platformu.

Icerik:
  1. Schemas         - account info, analytics, stories, heatmap grid
  2. SnapAdapter     - classify (tek tip: username) + scan
  3. Router          - /scan + /heatmap (PNG download)
  4. GraphConverter

Tool: tools/snap_osint.py
  Input: spez, @spez, snapchat.com/add/spez, https://www.snapchat.com/@spez
  Tum varyantlar username'e normalize edilir.

Heatmap stratejisi:
  Scan'de --no-heatmap ile PNG uretmeyiz (hiz), JSON'daki 'heatmap.grid' ile
  frontend inline SVG cizer. Kullanici isterse /heatmap endpoint'i PNG doner.
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

class SnapAccountInformation(BaseModel):
    page_title: str | None = None
    page_description: str | None = None
    is_public: bool | None = None
    username: str | None = None
    display_name: str | None = None
    badge: str | None = None
    profile_picture: str | None = None
    background_picture: str | None = None
    subscriber_count: int | None = None
    bio: str | None = None
    website: str | None = None
    category: str | None = None
    subcategory: str | None = None
    snapcode_url: str | None = None


class SnapAccountAnalysis(BaseModel):
    account_age: str | None = None
    created_at: str | None = None
    last_updated: str | None = None
    last_active: str | None = None
    most_active_day: str | None = None
    most_active_hour: str | None = None


class SnapRelatedAccount(BaseModel):
    username: str | None = None
    title: str | None = None
    subscribers: int | None = None
    pic: str | None = None


class SnapEntry(BaseModel):
    """Story, highlight veya spotlight icindeki bir snap."""
    id: str | None = None
    url: str | None = None
    type: str | None = None
    upload_date: str | None = None
    duration_s: float | None = None


class SnapStoryCollection(BaseModel):
    count: int = 0
    snaps: list[SnapEntry] = Field(default_factory=list)


class SnapHighlight(BaseModel):
    title: str | None = None
    thumbnail: str | None = None
    snap_count: int = 0
    snaps: list[SnapEntry] = Field(default_factory=list)


class SnapHighlightCollection(BaseModel):
    count: int = 0
    total_snaps: int = 0
    highlights: list[SnapHighlight] = Field(default_factory=list)


class SnapSpotlight(BaseModel):
    name: str | None = None
    thumbnail: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    snaps: list[SnapEntry] = Field(default_factory=list)


class SnapSpotlightCollection(BaseModel):
    count: int = 0
    total_duration_s: float = 0
    spotlights: list[SnapSpotlight] = Field(default_factory=list)


class SnapAnalytics(BaseModel):
    total_snaps: int = 0
    video_count: int = 0
    video_pct: float = 0
    image_count: int = 0
    image_pct: float = 0
    avg_per_day: str | float | None = None        # "10.00 snaps/day" string olarak gelir
    first_snap: str | None = None
    last_snap: str | None = None
    most_active_day: str | None = None
    most_active_hour: str | None = None
    avg_spotlight_duration: str | float | None = None  # "N/A" veya float
    daily_distribution: dict[str, int] = Field(default_factory=dict)
    hourly_distribution: dict[str, int] = Field(default_factory=dict)


class SnapHeatmap(BaseModel):
    description: str | None = None
    days: list[str] = Field(default_factory=list)
    grid: dict[str, dict[str, int]] = Field(default_factory=dict)


class SnapResult(BaseModel):
    """Snap tool cikti shape'i."""
    account_information: SnapAccountInformation | None = None
    account_analysis: SnapAccountAnalysis | None = None
    related_accounts: list[SnapRelatedAccount] = Field(default_factory=list)
    stories: SnapStoryCollection | None = None
    curated_highlights: SnapHighlightCollection | None = None
    spotlights: SnapSpotlightCollection | None = None
    lenses: dict[str, Any] = Field(default_factory=dict)
    snap_analytics: SnapAnalytics | None = None
    heatmap: SnapHeatmap | None = None


# ═════════════════════════════════════════════════════════════════
# 2. ADAPTER
# ═════════════════════════════════════════════════════════════════

class SnapAdapter(PlatformAdapter):
    platform = "snapchat"
    script = "snap_osint.py"
    capabilities = ["scan", "heatmap_png"]
    cache_ttl = 600  # 10dk - Snapchat sayfalari sık degismez

    def classify(self, raw: str) -> tuple[str, str]:
        """
        Tek input tipi var: username. Tum varyantlar tek username'e normalize.
          "spez"                             -> ("username", "spez")
          "@spez"                            -> ("username", "spez")
          "snapchat.com/add/spez"            -> ("username", "spez")
          "https://www.snapchat.com/@spez"   -> ("username", "spez")
          "https://story.snapchat.com/@spez" -> ("username", "spez")
        """
        t = (raw or "").strip().rstrip("/")
        if not t:
            raise ValueError("Bos input")

        # URL /add/username
        m = re.search(r"snapchat\.com/add/([A-Za-z0-9._\-]+)", t, re.I)
        if m:
            return ("username", m.group(1))

        # URL /@username
        m = re.search(r"snapchat\.com/@([A-Za-z0-9._\-]+)", t, re.I)
        if m:
            return ("username", m.group(1))

        # @-prefix strip
        while t.startswith("@"):
            t = t[1:]
        t = t.strip()

        if not re.match(r"^[A-Za-z0-9._\-]{3,32}$", t):
            raise ValueError(f"Gecersiz Snapchat username: {raw}")

        return ("username", t)

    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        """
        Tool heatmap PNG'yi kendi dizinine yazar - --no-heatmap ile onu atla.
        JSON'u tempfile'a yazdir (--save-json /tmp/...) ve oku.
        """
        if target_type != "username":
            raise ValueError(f"Desteklenmeyen tip: {target_type}")

        result = await self._run_tool_file_output(
            target_type=target_type,
            value=value,
            args_builder=lambda out: [
                value,
                "--no-heatmap",      # scan sirasinda PNG olusturma
                "--save-json", out,  # JSON temp'e yaz
            ],
            timeout=90,
        )

        # Tool is_public=false veya account_information boş ise not-found
        acc_info = result.get("account_information") or {}
        if not acc_info.get("username"):
            raise LookupError(f"Snapchat hesabi bulunamadi: {value}")
        if acc_info.get("is_public") is False:
            # Private hesaplar icin de info doner ama icerik sinirli
            # Schema'yi tutarli tutmak icin exception atmayiz, data ile devam
            pass

        try:
            validated = SnapResult.model_validate(result)
            return validated.model_dump(mode="json")
        except Exception:
            return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return SnapGraphConverter.convert(data)


# ═════════════════════════════════════════════════════════════════
# 3. GRAPH CONVERTER
# ═════════════════════════════════════════════════════════════════

class SnapGraphConverter:
    """
    Snap scan sonucunu graph'e cevirir.
    Central: person + username. Related accounts -> diger username'ler.
    Website (varsa) -> domain. Hashtag'ler spotlight'tan -> opsiyonel.
    """

    @staticmethod
    def convert(data: dict[str, Any]) -> dict[str, list]:
        nodes: list[dict] = []
        edges: list[dict] = []

        info = data.get("account_information") or {}
        username = info.get("username")
        if not username:
            return {"nodes": nodes, "edges": edges}

        # Person node
        person_id = f"p_snap_{_slug(username)}"
        nodes.append({
            "id": person_id,
            "type": "person",
            "label": info.get("display_name") or username,
            "meta": {
                "Platform": "Snapchat",
                "Username": username,
                "Bio": info.get("bio") or "—",
                "Subscribers": str(info.get("subscriber_count") or 0),
                "Verified": "Yes" if info.get("badge") else "No",
                "Public": "Yes" if info.get("is_public") else "No",
                "Category": (info.get("subcategory") or info.get("category") or "—").replace("public-profile-", "").replace("-v3", ""),
            },
        })

        # Username node
        u_id = f"u_snap_{_slug(username)}"
        nodes.append({
            "id": u_id,
            "type": "username",
            "label": f"@{username}",
            "meta": {
                "Platforms": "Snapchat",
                "Profile": f"https://www.snapchat.com/add/{username}",
                "Subscribers": str(info.get("subscriber_count") or 0),
            },
        })
        edges.append({
            "id": f"ed_{person_id}_{u_id}",
            "source": person_id, "target": u_id, "type": "owns",
        })

        # Website -> domain node
        website = info.get("website")
        if website and website not in (None, "None", "", "null"):
            dom = _extract_domain(website)
            if dom:
                d_id = f"d_ext_{_slug(dom)}"
                if not _has_node(nodes, d_id):
                    nodes.append({
                        "id": d_id,
                        "type": "domain",
                        "label": dom,
                        "meta": {"Source": "Snapchat bio link", "URL": website},
                    })
                edges.append({
                    "id": f"ed_{person_id}_{d_id}",
                    "source": person_id, "target": d_id, "type": "owns",
                })

        # Related accounts - weak signals, username nodes
        for rel in (data.get("related_accounts") or [])[:8]:
            if not isinstance(rel, dict):
                continue
            rel_name = rel.get("username")
            if not rel_name or rel_name == username:
                continue
            rel_id = f"u_snap_{_slug(rel_name)}"
            if not _has_node(nodes, rel_id):
                nodes.append({
                    "id": rel_id,
                    "type": "username",
                    "label": f"@{rel_name}",
                    "meta": {
                        "Platforms": "Snapchat",
                        "Display_Name": rel.get("title") or rel_name,
                        "Source": "Related to target",
                    },
                })
            edges.append({
                "id": f"ed_{person_id}_{rel_id}_rel",
                "source": person_id, "target": rel_id, "type": "linked_to",
            })

        # Spotlight hashtags - informational
        for sp in (data.get("spotlights", {}).get("spotlights") or [])[:5]:
            if not isinstance(sp, dict):
                continue
            for tag in (sp.get("hashtags") or [])[:3]:
                if not tag:
                    continue
                # Hashtag'i ayri node olarak eklemeyelim - graph kirli olur.
                # Meta'ya ekleriz. Simdilik atla.
                pass

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


# ═════════════════════════════════════════════════════════════════
# 4. ROUTER — scan + heatmap PNG download
# ═════════════════════════════════════════════════════════════════

router = APIRouter(prefix="/api/socmint/snapchat", tags=["snapchat"])


class SnapTarget(BaseModel):
    raw: str = Field(..., min_length=1, max_length=200)


class SnapScanRequest(BaseModel):
    targets: list[SnapTarget] = Field(..., min_length=1, max_length=10)


@router.get("/capabilities")
def snap_capabilities() -> dict[str, Any]:
    return {
        "platform": "snapchat",
        "capabilities": SnapAdapter.capabilities,
        "input_types": ["username"],
        "input_examples": [
            "djkhaled305",
            "@djkhaled305",
            "https://www.snapchat.com/add/djkhaled305",
            "https://www.snapchat.com/@djkhaled305",
            "snapchat.com/add/djkhaled305",
        ],
    }


@router.post("/scan", response_model=JobCreated)
def snap_scan(req: SnapScanRequest) -> JobCreated:
    adapter = SnapAdapter()
    classified: list[dict[str, str]] = []
    for t in req.targets:
        try:
            target_type, value = adapter.classify(t.raw)
            classified.append({"raw": t.raw, "type": target_type, "value": value})
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Gecersiz input '{t.raw}': {e}")

    task = celery_app.send_task("scan_platform_targets", args=["snapchat", classified])

    from app.routers.jobs import register_job
    register_job(task.id, "snapchat", len(classified))

    return JobCreated(
        job_id=task.id, platform="snapchat", target_count=len(classified),
    )


@router.post("/classify")
def snap_classify(req: SnapTarget) -> dict[str, str]:
    try:
        adapter = SnapAdapter()
        t, v = adapter.classify(req.raw)
        return {"type": t, "value": v, "raw": req.raw}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/heatmap/{username}")
async def snap_heatmap_png(username: str):
    """
    Heatmap PNG uretip dondurur - kullanici 'Download heatmap' butonuna bastiginda.
    Scan sirasinda PNG uretilmiyor (--no-heatmap), bu endpoint talep uzerine yapar.
    Cache'te heatmap varsa oradan da alinabilir (ayri key).
    """
    # Input validation
    adapter = SnapAdapter()
    try:
        _, clean_username = adapter.classify(username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Cache kontrol - once PNG cache'inde var mi
    cache_key = f"heatmap:snapchat:{clean_username}"
    cached = await cache.get(cache_key)
    if cached and isinstance(cached, dict) and cached.get("png_base64"):
        png_bytes = base64.b64decode(cached["png_base64"])
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={"Content-Disposition": f'inline; filename="heatmap_{clean_username}.png"'},
        )

    # PNG uret - tool'u --output ile cagir, temp dir'e yazdir
    import tempfile
    from app.core.tool_runner import TOOLS_DIR
    import asyncio
    import os

    with tempfile.TemporaryDirectory(prefix="snap_hm_") as tmpdir:
        tmpdir_path = Path(tmpdir)
        png_path = tmpdir_path / f"heatmap_{clean_username}.png"
        json_path = tmpdir_path / f"scan_{clean_username}.json"

        script_path = TOOLS_DIR / "snap_osint.py"
        if not script_path.exists():
            raise HTTPException(status_code=500, detail="Snap tool bulunamadi")

        proc = await asyncio.create_subprocess_exec(
            "python3", "-u", str(script_path),
            clean_username,
            "--output", str(png_path),
            "--save-json", str(json_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(tmpdir_path),
        )
        try:
            _, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise HTTPException(status_code=504, detail="Heatmap timeout")

        if proc.returncode != 0:
            err = stderr_b.decode("utf-8", errors="replace")[:200]
            raise HTTPException(status_code=500, detail=f"Heatmap uretilemedi: {err}")

        if not png_path.exists():
            raise HTTPException(status_code=404, detail="Heatmap PNG olusturulamadi (muhtemelen hesap boş / upload yok)")

        png_bytes = png_path.read_bytes()

        # Cache'e yaz (24h)
        await cache.set(
            cache_key,
            {"png_base64": base64.b64encode(png_bytes).decode("ascii")},
            ttl=86400,
        )

        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={"Content-Disposition": f'inline; filename="heatmap_{clean_username}.png"'},
        )
