"""
GitHub OSINT modulu - SOCMIntelligence platformu.

Icerik:
  1. GithubProfileData   - tool cikti Pydantic model'i
  2. GithubAdapter       - tool runner + classify + scan + to_graph
  3. Router              - FastAPI endpoints (/scan, /capabilities)
  4. GraphConverter      - tarama sonucunu graph nodes/edges'e cevirir

Tool:
  tools/github_osint.py - osgint/C3n7ral051nt4g3ncy inspired, tokensız calisir
  Input formatlari:
    emrexyz
    @emrexyz
    github.com/emrexyz
    https://github.com/emrexyz
    https://github.com/emrexyz/some-repo
    me@example.com   (email arama - username'e cozulur)

Cikti JSON sabit shape:
  login, id, avatar_url, name, blog, location, email, company, bio,
  public_repos, followers, following, created_at, updated_at,
  emails_all[], social_accounts[], social_media{}, organizations[],
  secrets_found[], sensitive_files[], public_events_emails[],
  commit_search_emails[], gist_count, GPG_ids[], GPG_keys,
  starred_top_languages{}, starred_top_topics{}, scanned_at
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.celery_app import celery_app
from app.core.adapter import PlatformAdapter
from app.schemas.common import JobCreated

# ═════════════════════════════════════════════════════════════════
# 1. SCHEMAS — Pydantic models for tool output
# ═════════════════════════════════════════════════════════════════

class GithubSocialAccount(BaseModel):
    provider: str                      # "twitter", "mastodon", "linkedin", "generic"
    url: str


class GithubOrganization(BaseModel):
    org: str
    members: list[str] = []            # public org members (excluding target)


class GithubSecretFinding(BaseModel):
    type: str                          # "AWS Access Key", "GitHub Token", vs
    snippet: str                       # redacted preview (first 60 chars)
    source: str                        # where found (gist/repo/readme)


class GithubCommitEmail(BaseModel):
    email: str
    name: str = ""
    role: str = "author"               # "author" | "committer"
    repo: str = "?"


class GithubProfileData(BaseModel):
    """
    Tool cikti shape'i - sabit (her zaman bu fieldlar doner).
    Bos field'lar None / [] / {} olarak kalir.
    """
    # Scan metadata
    scanned_at: datetime | None = None

    # Core profile
    login: str | None = None
    id: int | None = None
    avatar_url: str | None = None
    name: str | None = None
    blog: str | None = None
    location: str | None = None
    twitter_username: str | None = None
    email: str | None = None
    company: str | None = None
    bio: str | None = None
    public_repos: int | None = None
    followers: int | None = None
    following: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    profile_readme: str | None = None

    # Collections - always present, may be empty
    emails_all: list[str] = Field(default_factory=list)
    social_accounts: list[GithubSocialAccount] = Field(default_factory=list)
    social_media: dict[str, list[str]] = Field(default_factory=dict)
    organizations: list[GithubOrganization] = Field(default_factory=list)
    secrets_found: list[GithubSecretFinding] = Field(default_factory=list)
    sensitive_files: list[dict[str, Any]] = Field(default_factory=list)
    public_events_emails: list[str] = Field(default_factory=list)
    commit_search_emails: list[GithubCommitEmail] = Field(default_factory=list)
    gist_count: int = 0
    GPG_ids: list[str] = Field(default_factory=list)
    GPG_keys: str | None = None
    starred_top_languages: dict[str, int] = Field(default_factory=dict)
    starred_top_topics: dict[str, int] = Field(default_factory=dict)


# ═════════════════════════════════════════════════════════════════
# 2. ADAPTER — tool runner integration
# ═════════════════════════════════════════════════════════════════

class GithubAdapter(PlatformAdapter):
    """GitHub tool wrapper - subprocess + Redis cache + input classify."""

    platform = "github"
    script = "github_osint.py"
    capabilities = ["scan"]
    cache_ttl = 300  # 5dk - tokensız rate limit 60/hr, cache esastir

    # ─── classify: ham input -> (type, value) ───────────────────
    def classify(self, raw: str) -> tuple[str, str]:
        """
        Input tipini algila:
          "emrexyz"                        -> ("username", "emrexyz")
          "@emrexyz"                       -> ("username", "emrexyz")
          "github.com/emrexyz"             -> ("username", "emrexyz")
          "https://github.com/emrexyz"     -> ("username", "emrexyz")
          "me@example.com"                 -> ("email",    "me@example.com")
        """
        t = raw.strip()
        if not t:
            raise ValueError("Bos input")

        # URL - scheme var/yok
        url_match = re.search(
            r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9](?:[A-Za-z0-9\-]{0,38}))",
            t, re.IGNORECASE,
        )
        if url_match:
            return ("username", url_match.group(1))

        # @handle
        if t.startswith("@"):
            return ("username", t.lstrip("@").strip())

        # Email - @ icerir, sag tarafta nokta var
        if "@" in t:
            left, _, right = t.partition("@")
            if left and "." in right:
                return ("email", t)

        # Plain username
        return ("username", t)

    # ─── scan: subprocess calistir ───────────────────────────────
    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        """
        Her iki tip de (username/email) tool'a ayni sekilde gecirilir.
        Script normalize eder, email'i username'e cozer.
        """
        if target_type not in ("username", "email"):
            raise ValueError(f"Desteklenmeyen tip: {target_type}")

        result = await self._run_tool(
            target_type=target_type,
            value=value,
            args=[value, "--json"],
            env_keys=[],  # tokensız
        )

        # Script 404 durumunda JSON dondurur ama login=None olur.
        # Bunu explicit NOT_FOUND'a cevir.
        if not result.get("login"):
            raise LookupError(f"GitHub kullanicisi bulunamadi: {value}")

        # Pydantic validation - schema uymayan field'lar duserse log'a yazar
        try:
            validated = GithubProfileData.model_validate(result)
            return validated.model_dump(mode="json")
        except Exception:
            # Schema uymazsa raw dict don - alt siniftakiler yine calisir
            return result

    # ─── to_graph: scan sonucunu graph node/edge'e cevir ────────
    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        """
        SOCMIntelligence graph DataLayer formatina cevir.
        Node tipleri: person, username, email, domain, breach
        """
        return GithubGraphConverter.convert(data)


# ═════════════════════════════════════════════════════════════════
# 3. GRAPH CONVERTER — result -> SOCMIntelligence graph nodes/edges
# ═════════════════════════════════════════════════════════════════

class GithubGraphConverter:
    """
    GitHub scan sonucunu frontend SOCMIntelligence graph'in bekledigi node/edge
    yapisina cevirir. Unique ID pattern'i: '{type}_{source}_{value}'
    """

    @staticmethod
    def convert(data: dict[str, Any]) -> dict[str, list]:
        login = data.get("login")
        if not login:
            return {"nodes": [], "edges": []}

        nodes: list[dict] = []
        edges: list[dict] = []

        # ─── Person node (kullanici profili) ─────────────────────
        person_id = f"p_gh_{login}"
        nodes.append({
            "id": person_id,
            "type": "person",
            "label": data.get("name") or login,
            "meta": {
                "Login": login,
                "Platform": "GitHub",
                "Bio": data.get("bio") or "—",
                "Location": data.get("location") or "—",
                "Company": data.get("company") or "—",
                "Followers": str(data.get("followers") or 0),
                "Repos": str(data.get("public_repos") or 0),
                "Created": (data.get("created_at") or "")[:10],
            },
        })

        # ─── Username node (GitHub handle) ───────────────────────
        user_id = f"u_gh_{login}"
        nodes.append({
            "id": user_id,
            "type": "username",
            "label": login,
            "meta": {
                "Platforms": "GitHub",
                "Profile": f"https://github.com/{login}",
                "Public_Repos": str(data.get("public_repos") or 0),
            },
        })
        edges.append({
            "id": f"ed_{person_id}_{user_id}",
            "source": person_id,
            "target": user_id,
            "type": "owns",
        })

        # ─── Email nodes ─────────────────────────────────────────
        for email in data.get("emails_all", []):
            em_id = f"e_{_slug(email)}"
            if not _has_node(nodes, em_id):
                nodes.append({
                    "id": em_id,
                    "type": "email",
                    "label": email,
                    "meta": {
                        "Provider": _email_provider(email),
                        "Source": "GitHub commit/profile",
                    },
                })
            edges.append({
                "id": f"ed_{person_id}_{em_id}",
                "source": person_id, "target": em_id,
                "type": "owns",
            })

        # ─── Social account username'leri ────────────────────────
        for platform, handles in (data.get("social_media") or {}).items():
            for h in handles[:5]:  # limit - cok fazla olmasin
                if not h:
                    continue
                sn_id = f"u_{_slug(platform)}_{_slug(h)}"
                if not _has_node(nodes, sn_id):
                    nodes.append({
                        "id": sn_id,
                        "type": "username",
                        "label": h,
                        "meta": {
                            "Platforms": platform,
                            "Source": "GitHub profile/readme",
                        },
                    })
                edges.append({
                    "id": f"ed_{person_id}_{sn_id}",
                    "source": person_id, "target": sn_id,
                    "type": "linked_to",
                })

        # ─── Blog/personal domain ───────────────────────────────
        if data.get("blog"):
            blog = data["blog"].strip()
            if blog and ("http" in blog or "." in blog):
                domain = _extract_domain(blog)
                if domain:
                    d_id = f"d_{_slug(domain)}"
                    if not _has_node(nodes, d_id):
                        nodes.append({
                            "id": d_id,
                            "type": "domain",
                            "label": domain,
                            "meta": {
                                "Source": "GitHub profile blog",
                                "URL": blog,
                            },
                        })
                    edges.append({
                        "id": f"ed_{person_id}_{d_id}",
                        "source": person_id, "target": d_id,
                        "type": "owns",
                    })

        # ─── Organizations ───────────────────────────────────────
        for org in data.get("organizations", []):
            org_name = org.get("org") if isinstance(org, dict) else org
            if not org_name:
                continue
            o_id = f"u_org_{_slug(org_name)}"
            if not _has_node(nodes, o_id):
                nodes.append({
                    "id": o_id,
                    "type": "username",
                    "label": f"@{org_name}",
                    "meta": {
                        "Platforms": "GitHub Org",
                        "Members": str(len((org.get("members") or []))) if isinstance(org, dict) else "?",
                    },
                })
            edges.append({
                "id": f"ed_{person_id}_{o_id}",
                "source": person_id, "target": o_id,
                "type": "registered_to",
            })

        # ─── Secrets found -> breach tipinde gelecek (uyari) ─────
        for secret in data.get("secrets_found", []):
            if not isinstance(secret, dict):
                continue
            s_id = f"br_secret_{_slug(secret.get('type',''))}"
            if not _has_node(nodes, s_id):
                nodes.append({
                    "id": s_id,
                    "type": "breach",
                    "label": f"Leak: {secret.get('type', 'Unknown')}",
                    "meta": {
                        "Type": secret.get("type", ""),
                        "Source": secret.get("source", ""),
                        "Severity": "HIGH",
                    },
                })
            edges.append({
                "id": f"ed_{person_id}_{s_id}",
                "source": person_id, "target": s_id,
                "type": "appears_in",
            })

        # ─── Dedup: ayni ID'li node/edge'leri tekille ───────────
        nodes = _dedup_by_id(nodes)
        edges = _dedup_by_id(edges)

        return {"nodes": nodes, "edges": edges}


# ─── Helper functions ────────────────────────────────────────────

def _slug(s: str) -> str:
    """URL-safe, uniqueness-preserving kisa id."""
    return re.sub(r"[^A-Za-z0-9]+", "_", (s or "").lower()).strip("_")[:40]


def _has_node(nodes: list[dict], node_id: str) -> bool:
    return any(n["id"] == node_id for n in nodes)


def _dedup_by_id(items: list[dict]) -> list[dict]:
    """Ayni ID'li node/edge'leri tekille - ilk karsilasilan kalir."""
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        iid = item.get("id")
        if iid and iid not in seen:
            seen.add(iid)
            out.append(item)
    return out


def _email_provider(email: str) -> str:
    """Email adresinden saglayici ismini tahmin et."""
    if "@" not in email:
        return "Unknown"
    domain = email.split("@", 1)[1].lower()
    providers = {
        "gmail.com": "Gmail", "outlook.com": "Outlook", "hotmail.com": "Hotmail",
        "yahoo.com": "Yahoo", "protonmail.com": "ProtonMail", "proton.me": "Proton",
        "icloud.com": "iCloud", "yandex.com": "Yandex", "tutanota.com": "Tutanota",
    }
    return providers.get(domain, domain)


def _extract_domain(url_or_blog: str) -> str | None:
    """URL'den domain cek."""
    m = re.search(r"(?:https?://)?([A-Za-z0-9][A-Za-z0-9\-.]+\.[A-Za-z]{2,})", url_or_blog)
    return m.group(1).lower().rstrip("/") if m else None


# ═════════════════════════════════════════════════════════════════
# 4. ROUTER — FastAPI endpoints
# ═════════════════════════════════════════════════════════════════

router = APIRouter(prefix="/api/socmint/github", tags=["github"])


class GithubTarget(BaseModel):
    """Tek hedef - frontend'den gelen ham input."""
    raw: str = Field(..., min_length=1, max_length=200, description="Username, URL veya email")


class GithubScanRequest(BaseModel):
    """Coklu hedef taramasi icin request body."""
    targets: list[GithubTarget] = Field(..., min_length=1, max_length=10)


@router.get("/capabilities")
def github_capabilities() -> dict[str, Any]:
    """Platform'un destekledigi ozellikler - frontend buton render icin."""
    return {
        "platform": "github",
        "capabilities": GithubAdapter.capabilities,
        "input_types": ["username", "email"],
        "input_examples": [
            "torvalds",
            "@torvalds",
            "github.com/torvalds",
            "https://github.com/torvalds",
            "me@example.com",
        ],
    }


@router.post("/scan", response_model=JobCreated)
def github_scan(req: GithubScanRequest) -> JobCreated:
    """
    Coklu hedef scan'i Celery kuyruguna at, job_id don.
    Frontend GET /api/socmint/jobs/{job_id} ile poll eder.
    """
    adapter = GithubAdapter()
    classified: list[dict[str, str]] = []

    for t in req.targets:
        try:
            target_type, value = adapter.classify(t.raw)
            classified.append({"raw": t.raw, "type": target_type, "value": value})
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Gecersiz input '{t.raw}': {e}")

    # Celery dispatch - generic task
    task = celery_app.send_task(
        "scan_platform_targets",
        args=["github", classified],
    )

    # Job map'e kaydet - /jobs/{id} polling icin
    from app.routers.jobs import register_job
    register_job(task.id, "github", len(classified))

    return JobCreated(
        job_id=task.id,
        platform="github",
        target_count=len(classified),
    )


@router.post("/classify")
def github_classify(req: GithubTarget) -> dict[str, str]:
    """
    Chip input icin hizli classification - frontend yazildikca cagirir.
    Backend'e round trip gerektirir ama tutarlilik icin tek yerde.
    Alternatif: frontend'te ayni logic'i JS ile tekrarla (hiz icin onerilir).
    """
    try:
        adapter = GithubAdapter()
        target_type, value = adapter.classify(req.raw)
        return {"type": target_type, "value": value, "raw": req.raw}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
