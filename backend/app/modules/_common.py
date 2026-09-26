"""
Yeni moduller icin ortak parcalar: router fabrikasi, graph yardimcilari,
sosyal hesap -> kanonik node ID esleme (platformlar arasi kimlik birlestirme).
"""

import re
from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from pydantic import Field, create_model

from app.celery_app import celery_app
from app.schemas.common import JobCreated


def slug(s: Any) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(s or "").lower()).strip("_")[:40]


def domain_of(url: str | None) -> str | None:
    if not url:
        return None
    m = re.search(r"(?:https?://)?(?:www\.)?([A-Za-z0-9][A-Za-z0-9\-.]*\.[A-Za-z]{2,})", url)
    return m.group(1).lower() if m else None


# Diger modullerle ayni ID on-ekleri (enrich.canonical_id ile uyumlu)
SOCIAL_PREFIX = {
    "twitter": "twitter", "x": "twitter", "twitter/x": "twitter", "instagram": "instagram", "tiktok": "tiktok",
    "youtube": "youtube", "github": "gh", "gitlab": "gitlab", "telegram": "telegram", "reddit": "reddit",
    "linkedin": "linkedin", "facebook": "facebook", "snapchat": "snap", "keybase": "keybase", "steam": "steam",
    "twitch": "twitch", "hackernews": "hackernews", "mastodon": "masto", "bluesky": "bluesky", "instagram": "instagram", "kick": "kick", "discord": "discord",
}
SOCIAL_LABEL = {
    "twitter": "Twitter/X", "instagram": "Instagram", "tiktok": "TikTok", "youtube": "YouTube", "gh": "GitHub", "gitlab": "GitLab",
    "telegram": "Telegram", "reddit": "Reddit", "linkedin": "LinkedIn", "facebook": "Facebook", "snap": "Snapchat", "keybase": "Keybase",
    "steam": "Steam", "twitch": "Twitch", "hackernews": "Hacker News", "masto": "Mastodon", "bluesky": "Bluesky", "instagram": "Instagram", "kick": "Kick", "discord": "Discord",
}


class G:
    """Kucuk graph kurucu: (source,target,type) tekillestirme + agirlik."""

    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: dict[tuple, dict] = {}

    def node(self, nid: str, ntype: str, label: str, meta: dict | None = None) -> str:
        meta = {k: v for k, v in (meta or {}).items() if v not in (None, "", [], {})}
        if nid in self.nodes:
            for k, v in meta.items():
                self.nodes[nid]["meta"].setdefault(k, v)
        else:
            self.nodes[nid] = {"id": nid, "type": ntype, "label": str(label), "meta": meta}
        return nid

    def edge(self, s: str, t: str, etype: str, weight: float | int | None = None) -> None:
        if not s or not t or s == t:
            return
        k = (s, t, etype)
        if k in self.edges:
            if weight is not None:
                self.edges[k]["weight"] = max(self.edges[k].get("weight") or 0, weight)
            return
        e = {"id": f"ed_{s}__{t}__{etype}", "source": s, "target": t, "type": etype}
        if weight is not None:
            e["weight"] = weight
        self.edges[k] = e

    def social(self, anchor: str, platform: str, handle: str, url: str | None = None,
               etype: str = "linked_to", source: str = "", extra: dict | None = None) -> str | None:
        """Sosyal hesabi kanonik ID ile ekle. Mastodon handle'i 'kullanici@sunucu' bicimindedir."""
        if not handle:
            return None
        key = SOCIAL_PREFIX.get((platform or "").lower(), slug(platform))
        h = handle.lstrip("@")
        if key == "masto" and "@" in h:
            user, inst = h.split("@", 1)
            nid, label = f"u_masto_{slug(user)}_{slug(inst)}", f"@{user}@{inst}"
        else:
            nid, label = f"u_{key}_{slug(h)}", f"@{h}" if key not in ("linkedin", "facebook") else h
        self.node(nid, "username", label, {"Platforms": SOCIAL_LABEL.get(key, platform), "URL": url, "Source": source, **(extra or {})})
        self.edge(anchor, nid, etype)
        return nid

    def email(self, anchor: str, email: str, source: str, etype: str = "owns", extra: dict | None = None) -> str:
        nid = self.node(f"e_{slug(email)}", "email", email, {"Source": source, **(extra or {})})
        self.edge(anchor, nid, etype)
        return nid

    def domain(self, anchor: str, url_or_domain: str, source: str, etype: str = "linked_to", weight=None) -> str | None:
        d = domain_of(url_or_domain)
        if not d:
            return None
        nid = self.node(f"d_ext_{slug(d)}", "domain", d, {"Source": source, "URL": url_or_domain if "/" in (url_or_domain or "") else None})
        self.edge(anchor, nid, etype, weight)
        return nid

    def hashtag(self, anchor: str, tag: str, platform: str, weight=None, etype: str = "tagged") -> str | None:
        tag = (tag or "").lstrip("#").strip()
        if not tag:
            return None
        nid = self.node(f"h_{slug(tag)}", "hashtag", f"#{tag}", {"Platform": platform})
        self.edge(anchor, nid, etype, weight)
        return nid

    def export(self) -> dict[str, list]:
        edges = [e for e in self.edges.values() if e["source"] in self.nodes and e["target"] in self.nodes]
        return {"nodes": list(self.nodes.values()), "edges": edges}


def raise_tool_error(result: dict, platform: str) -> None:
    """Aracin {"error": ..., "message": ...} ciktisini exception'a cevir."""
    if not isinstance(result, dict) or not result.get("error"):
        return
    kind, msg = str(result.get("error")), result.get("message") or str(result.get("error"))
    if kind == "not_found":
        raise LookupError(msg)
    if kind == "private":
        raise PermissionError(msg)
    if kind == "rate_limited":
        raise RuntimeError(f"rate_limit: {msg}")
    raise RuntimeError(f"{platform}: {msg}")


def make_router(platform: str, adapter_factory: Callable, examples: list[str], max_targets: int = 10,
                input_types: list[str] | None = None, requires_env: list[str] | None = None) -> APIRouter:
    router = APIRouter(prefix=f"/api/socmint/{platform}", tags=[platform])
    name = "".join(p.title() for p in platform.split("_"))
    Target = create_model(f"{name}Target", raw=(str, Field(..., min_length=1, max_length=300)))
    ScanReq = create_model(f"{name}ScanRequest", targets=(list[Target], Field(..., min_length=1, max_length=max_targets)))

    @router.get("/capabilities")
    def capabilities() -> dict[str, Any]:
        return {"platform": platform, "capabilities": ["scan"], "input_types": input_types or [],
                "input_examples": examples, "requires_env": requires_env or []}

    @router.post("/scan", response_model=JobCreated)
    def scan(req: ScanReq) -> JobCreated:  # type: ignore[valid-type]
        adapter = adapter_factory()
        classified = []
        for t in req.targets:
            try:
                tt, v = adapter.classify(t.raw)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Gecersiz input '{t.raw}': {e}")
            classified.append({"raw": t.raw, "type": tt, "value": v})
        task = celery_app.send_task("scan_platform_targets", args=[platform, classified])
        from app.routers.jobs import register_job
        register_job(task.id, platform, len(classified))
        return JobCreated(job_id=task.id, platform=platform, target_count=len(classified))

    @router.post("/classify")
    def classify(req: Target) -> dict[str, str]:  # type: ignore[valid-type]
        try:
            tt, v = adapter_factory().classify(req.raw)
            return {"type": tt, "value": v, "raw": req.raw}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return router
