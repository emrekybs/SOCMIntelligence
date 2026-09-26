"""
Mastodon OSINT modulu - SOCMIntelligence platformu.

Icerik:
  1. Schemas         - instance, admin account, avatar analysis, status analysis
  2. MastoAdapter    - classify + scan (3 input tipi) + to_graph
  3. Router          - FastAPI endpoints
  4. GraphConverter  - instance + account -> nodes/edges

Tool: tools/masto_osint.py
  Input tipleri:
    username               -> tum instance'larda tara
    instance.com           -> sunucu bilgisi + admin profili
    @user@instance         -> ikisi birden
    https://instance/@user -> ikisi birden
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.celery_app import celery_app
from app.core.adapter import PlatformAdapter
from app.schemas.common import JobCreated


# ═════════════════════════════════════════════════════════════════
# 1. SCHEMAS
# ═════════════════════════════════════════════════════════════════

class MastoCustomField(BaseModel):
    name: str | None = None
    value: str | None = None
    value_html: str | None = None
    verified_at: str | None = None


class MastoAvatarAnalysis(BaseModel):
    url: str | None = None
    path: str | None = None
    size_bytes: int | None = None
    md5: str | None = None
    sha256: str | None = None
    dimensions: list[int] = Field(default_factory=list)
    format: str | None = None
    exif: dict[str, Any] = Field(default_factory=dict)
    phash: str | None = None
    dhash: str | None = None


class MastoStatusAnalysis(BaseModel):
    statuses_analyzed: int = 0
    hour_distribution: dict[str, int] = Field(default_factory=dict)
    day_distribution: dict[str, int] = Field(default_factory=dict)
    languages: dict[str, int] = Field(default_factory=dict)
    top_hashtags: dict[str, int] = Field(default_factory=dict)
    top_mentions: dict[str, int] = Field(default_factory=dict)
    visibility_breakdown: dict[str, int] = Field(default_factory=dict)
    media_post_count: int = 0
    reply_post_count: int = 0
    boost_post_count: int = 0
    total_favourites: int = 0
    total_boosts: int = 0
    total_replies_received: int = 0
    urls_shared: list[str] = Field(default_factory=list)
    posts_per_day_avg: float = 0.0
    top_post: dict[str, Any] | None = None


class MastoPinnedStatus(BaseModel):
    url: str | None = None
    created_at: str | None = None
    text: str | None = None
    favourites: int = 0
    reblogs: int = 0


class MastoAccount(BaseModel):
    """Mastodon kullanici hesabi - hem 'targeted_account' hem 'admin' olarak kullanilir."""
    user_id: str | None = None
    username: str | None = None
    acct: str | None = None
    account: str | None = None
    display_name: str | None = None
    profile_url: str | None = None
    instance: str | None = None
    profile_locked: bool | None = None
    discoverable: bool | None = None
    bot: bool | None = None
    group: bool | None = None
    noindex: bool | None = None
    suspended: bool | None = None
    limited: bool | None = None
    profile_created_at: str | None = None
    last_status_at: str | None = None
    followers_count: int | None = None
    following_count: int | None = None
    statuses_count: int | None = None
    bio: str | None = None
    bio_html: str | None = None
    avatar_link: str | None = None
    header_link: str | None = None
    custom_fields: list[MastoCustomField] = Field(default_factory=list)

    # OSINT extracted
    emails: list[str] = Field(default_factory=list)
    phone_numbers: list[str] = Field(default_factory=list)
    crypto_addresses: dict[str, list[str]] = Field(default_factory=dict)
    urls: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    social_handles: dict[str, list[str]] = Field(default_factory=dict)
    emails_in_bio: list[str] = Field(default_factory=list)
    urls_in_bio: list[str] = Field(default_factory=list)
    hashtags_in_bio: list[str] = Field(default_factory=list)

    status_analysis: MastoStatusAnalysis | None = None
    pinned_statuses: list[MastoPinnedStatus] = Field(default_factory=list)
    avatar_analysis: MastoAvatarAnalysis | None = None


class MastoInstanceInfo(BaseModel):
    """Mastodon sunucu bilgisi + admin."""
    instance: str | None = None
    name: str | None = None
    title: str | None = None
    short_description: str | None = None
    detailed_description: str | None = None
    email: str | None = None
    languages: list[str] = Field(default_factory=list)
    registrations_open: bool | None = None
    registration_approval_required: bool | None = None
    thumbnail_link: str | None = None
    version: str | None = None
    user_count: int | None = None
    status_count: int | None = None
    domain_count: int | None = None
    streaming_url: str | None = None
    admin: MastoAccount | None = None


class MastoUsernameHit(BaseModel):
    """username scan sonucu - her hit bir instance'taki hesap."""
    instance: str | None = None
    username: str | None = None
    display_name: str | None = None
    profile_url: str | None = None
    followers_count: int | None = None
    statuses_count: int | None = None
    bio: str | None = None


class MastoResult(BaseModel):
    """Tool'un ana cikti shape'i - kind degerine gore farkli alanlar dolar."""
    input: str
    kind: str                    # "qualified" | "username" | "instance" | "invalid"
    scanned_at: datetime | None = None
    targeted_account: MastoAccount | None = None
    instance_info: MastoInstanceInfo | None = None
    username_scan: list[dict[str, Any]] = Field(default_factory=list)


# ═════════════════════════════════════════════════════════════════
# 2. ADAPTER
# ═════════════════════════════════════════════════════════════════

class MastoAdapter(PlatformAdapter):
    platform = "mastodon"
    script = "masto_osint.py"
    capabilities = ["scan"]
    cache_ttl = 600  # 10dk - username scan agir is, cache onemli

    # ─── classify: ham input -> (type, value) ───────────────────
    def classify(self, raw: str) -> tuple[str, str]:
        """
        Input tipleri:
          "gargron"                          -> ("username", "gargron")
          "mastodon.social"                  -> ("instance", "mastodon.social")
          "@gargron@mastodon.social"         -> ("qualified", "gargron@mastodon.social")
          "https://mastodon.social/@gargron" -> ("qualified", "gargron@mastodon.social")
        """
        t = (raw or "").strip().rstrip("/").strip("<>\"'")
        if not t:
            raise ValueError("Bos input")

        # URL form: https://instance/@user
        m = re.match(
            r"(?:https?://)?(?:www\.)?([A-Za-z0-9][A-Za-z0-9\-.]+\.[A-Za-z]{2,})/@([A-Za-z0-9_]+)/?$",
            t
        )
        if m:
            return ("qualified", f"{m.group(2)}@{m.group(1).lower()}")

        # Qualified: @user@instance veya user@instance
        m = re.match(r"^@?([A-Za-z0-9_]{1,30})@([A-Za-z0-9\-.]+\.[A-Za-z]{2,})$", t)
        if m:
            return ("qualified", f"{m.group(1)}@{m.group(2).lower()}")

        # Instance: nokta var, @ yok
        if "." in t and not t.startswith("@"):
            host = re.sub(r"^https?://", "", t, flags=re.I).split("/", 1)[0].split("@")[-1]
            if re.match(r"^[A-Za-z0-9][A-Za-z0-9\-.]+\.[A-Za-z]{2,}$", host):
                return ("instance", host.lower())

        # Username: sade metin
        u = t.lstrip("@").strip()
        if re.match(r"^[A-Za-z0-9_]{1,30}$", u):
            return ("username", u)

        raise ValueError(f"Gecersiz Mastodon input: {raw}")

    # ─── scan: subprocess calistir (tool -o ile dosyaya yazar) ───
    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        if target_type not in ("username", "instance", "qualified"):
            raise ValueError(f"Desteklenmeyen tip: {target_type}")

        # Tool input'u "user@instance" sekline almiyor, ham input'u ister.
        # Bize classify sonrasi normalize value geldi, onu tool'un istedigi sekle cevir:
        if target_type == "qualified":
            raw_for_tool = f"@{value}"  # "@gargron@mastodon.social"
        else:
            raw_for_tool = value

        # Tool -o ile dosyaya yazar, biz okur oluruz
        # Username modunda --max kucuk tutalim hız icin (default 500 fazla)
        max_instances = 100 if target_type == "username" else 500

        result = await self._run_tool_file_output(
            target_type=target_type,
            value=value,
            args_builder=lambda out: [
                raw_for_tool,
                "-o", out,
                *(["--max", str(max_instances)] if target_type == "username" else []),
                *(["--as-user"] if target_type == "username" else []),
                *(["--as-instance"] if target_type == "instance" else []),
            ],
            timeout=180,  # username scan yavas olabilir
        )

        # kind=invalid durumu
        if result.get("kind") == "invalid":
            raise LookupError(f"Mastodon input tanınamadi: {value}")

        # Instance scan sonucu bos mu?
        if target_type == "instance" and not result.get("instance_info"):
            raise LookupError(f"Instance bulunamadi: {value}")

        # Qualified scan - targeted_account yok ama username_scan var mi?
        if (target_type == "qualified"
                and not result.get("targeted_account")
                and not result.get("username_scan")):
            raise LookupError(f"Hesap bulunamadi: {value}")

        # Username scan - hic hit yoksa
        if target_type == "username" and not result.get("username_scan"):
            raise LookupError(f"Kullanici hicbir instance'ta bulunamadi: {value}")

        # Pydantic validation - schema uymazsa raw don
        try:
            validated = MastoResult.model_validate(result)
            return validated.model_dump(mode="json")
        except Exception:
            return result

    # ─── to_graph ────────────────────────────────────────────────
    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return MastoGraphConverter.convert(data)


# ═════════════════════════════════════════════════════════════════
# 3. GRAPH CONVERTER
# ═════════════════════════════════════════════════════════════════

class MastoGraphConverter:
    """
    Mastodon scan sonucunu graph node/edge'e cevirir.
    Node tipleri: person, username, email, domain, ip (instance=domain)
    """

    @staticmethod
    def convert(data: dict[str, Any]) -> dict[str, list]:
        nodes: list[dict] = []
        edges: list[dict] = []
        kind = data.get("kind", "invalid")

        # ─── Instance mode: domain node + admin account ─────────
        if data.get("instance_info"):
            inst = data["instance_info"]
            inst_name = inst.get("instance") or "unknown"
            d_id = f"d_masto_{_slug(inst_name)}"
            nodes.append({
                "id": d_id,
                "type": "domain",
                "label": inst_name,
                "meta": {
                    "Title": inst.get("title") or "—",
                    "Version": inst.get("version") or "—",
                    "Users": str(inst.get("user_count") or 0),
                    "Statuses": str(inst.get("status_count") or 0),
                    "Admin_Email": inst.get("email") or "—",
                    "Open_Registration": "Yes" if inst.get("registrations_open") else "No",
                },
            })

            # Instance email (admin contact)
            if inst.get("email"):
                e_id = f"e_{_slug(inst['email'])}"
                nodes.append({
                    "id": e_id,
                    "type": "email",
                    "label": inst["email"],
                    "meta": {"Role": "Instance admin contact", "Source": "Mastodon"},
                })
                edges.append({
                    "id": f"ed_{d_id}_{e_id}",
                    "source": d_id, "target": e_id, "type": "registered_to",
                })

            # Admin account
            if inst.get("admin"):
                MastoGraphConverter._add_account_subgraph(
                    nodes, edges, inst["admin"], d_id, role_hint="admin"
                )

        # ─── Qualified / username mode: targeted account ────────
        if data.get("targeted_account"):
            MastoGraphConverter._add_account_subgraph(
                nodes, edges, data["targeted_account"], anchor_id=None
            )

        # ─── Username scan: her hit icin hafif node ─────────────
        for hit in (data.get("username_scan") or []):
            if not isinstance(hit, dict):
                continue
            username = hit.get("username") or hit.get("acct")
            instance = hit.get("instance")
            if not username or not instance:
                continue
            u_id = f"u_masto_{_slug(username)}_{_slug(instance)}"
            if _has_node(nodes, u_id):
                continue
            nodes.append({
                "id": u_id,
                "type": "username",
                "label": f"@{username}@{instance}",
                "meta": {
                    "Platforms": "Mastodon",
                    "Instance": instance,
                    "Followers": str(hit.get("followers_count") or 0),
                    "Posts": str(hit.get("statuses_count") or 0),
                    "Profile": hit.get("profile_url") or "",
                },
            })

            # Link to instance domain node (if exists)
            d_id = f"d_masto_{_slug(instance)}"
            if not _has_node(nodes, d_id):
                nodes.append({
                    "id": d_id,
                    "type": "domain",
                    "label": instance,
                    "meta": {"Platform": "Mastodon instance"},
                })
            edges.append({
                "id": f"ed_{u_id}_{d_id}",
                "source": u_id, "target": d_id, "type": "registered_to",
            })

        return _dedup_graph({"nodes": nodes, "edges": edges})

    @staticmethod
    def _add_account_subgraph(
        nodes: list[dict],
        edges: list[dict],
        acc: dict[str, Any],
        anchor_id: str | None,
        role_hint: str | None = None,
    ) -> None:
        """Bir hesabi (targeted veya admin) graph'e ekle - emailler, URLs, social handles."""
        username = acc.get("username") or acc.get("acct") or "unknown"
        instance = acc.get("instance") or "unknown"

        # Person node (hesap sahibi)
        person_id = f"p_masto_{_slug(username)}_{_slug(instance)}"
        if _has_node(nodes, person_id):
            return
        nodes.append({
            "id": person_id,
            "type": "person",
            "label": acc.get("display_name") or username,
            "meta": {
                "Handle": acc.get("account") or f"@{username}@{instance}",
                "Role": "Admin" if role_hint == "admin" else "User",
                "Followers": str(acc.get("followers_count") or 0),
                "Following": str(acc.get("following_count") or 0),
                "Statuses": str(acc.get("statuses_count") or 0),
                "Created": (acc.get("profile_created_at") or "")[:10],
                "Bio": _truncate(acc.get("bio") or "—", 100),
            },
        })

        # Username node
        u_id = f"u_masto_{_slug(username)}_{_slug(instance)}"
        if not _has_node(nodes, u_id):
            nodes.append({
                "id": u_id,
                "type": "username",
                "label": f"@{username}@{instance}",
                "meta": {
                    "Platforms": "Mastodon",
                    "Instance": instance,
                    "Profile": acc.get("profile_url") or "",
                },
            })
            edges.append({
                "id": f"ed_{person_id}_{u_id}",
                "source": person_id, "target": u_id, "type": "owns",
            })

        # Instance domain
        d_id = f"d_masto_{_slug(instance)}"
        if not _has_node(nodes, d_id):
            nodes.append({
                "id": d_id,
                "type": "domain",
                "label": instance,
                "meta": {"Platform": "Mastodon instance"},
            })
        edges.append({
            "id": f"ed_{u_id}_{d_id}",
            "source": u_id, "target": d_id, "type": "registered_to",
        })

        # Anchor - eger instance mode'daysak admin'i instance'a bagla
        if anchor_id:
            edges.append({
                "id": f"ed_{anchor_id}_{person_id}_admin",
                "source": anchor_id, "target": person_id, "type": "registered_to",
            })

        # Emails
        for em in acc.get("emails", []) or acc.get("emails_in_bio", []):
            if not em or "@" not in em:
                continue
            e_id = f"e_{_slug(em)}"
            if not _has_node(nodes, e_id):
                nodes.append({
                    "id": e_id,
                    "type": "email",
                    "label": em,
                    "meta": {
                        "Provider": _email_provider(em),
                        "Source": "Mastodon bio",
                    },
                })
            edges.append({
                "id": f"ed_{person_id}_{e_id}",
                "source": person_id, "target": e_id, "type": "owns",
            })

        # URLs -> external domain nodes (bio'daki linkler)
        for url in (acc.get("urls") or acc.get("urls_in_bio") or [])[:6]:
            dom = _extract_domain(url)
            if not dom or dom == instance:
                continue
            ext_id = f"d_ext_{_slug(dom)}"
            if not _has_node(nodes, ext_id):
                nodes.append({
                    "id": ext_id,
                    "type": "domain",
                    "label": dom,
                    "meta": {"Source": "Mastodon bio link", "URL": url},
                })
            edges.append({
                "id": f"ed_{person_id}_{ext_id}",
                "source": person_id, "target": ext_id, "type": "linked_to",
            })

        # Social handles (Twitter, Keybase, Patreon vs)
        for platform, handles in (acc.get("social_handles") or {}).items():
            for h in (handles or [])[:3]:
                if not h:
                    continue
                sn_id = f"u_{_slug(platform)}_{_slug(h)}"
                if not _has_node(nodes, sn_id):
                    nodes.append({
                        "id": sn_id,
                        "type": "username",
                        "label": h,
                        "meta": {
                            "Platforms": platform.title(),
                            "Source": "Mastodon bio",
                        },
                    })
                edges.append({
                    "id": f"ed_{person_id}_{sn_id}",
                    "source": person_id, "target": sn_id, "type": "linked_to",
                })

        # Custom fields'ta email/URL olabilir
        for cf in acc.get("custom_fields", []) or []:
            if not isinstance(cf, dict):
                continue
            val = (cf.get("value") or "").strip()
            name = (cf.get("name") or "").strip()
            if not val:
                continue
            # Email gibi gorunuyorsa
            if re.match(r"^[A-Za-z0-9_.+\-]+@[A-Za-z0-9\-.]+\.[A-Za-z]{2,}$", val):
                e_id = f"e_{_slug(val)}"
                if not _has_node(nodes, e_id):
                    nodes.append({
                        "id": e_id,
                        "type": "email",
                        "label": val,
                        "meta": {"Label": name, "Source": "Mastodon custom field"},
                    })
                edges.append({
                    "id": f"ed_{person_id}_{e_id}_cf",
                    "source": person_id, "target": e_id, "type": "owns",
                })


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


def _email_provider(email: str) -> str:
    if "@" not in email:
        return "Unknown"
    domain = email.split("@", 1)[1].lower()
    providers = {
        "gmail.com": "Gmail", "outlook.com": "Outlook", "hotmail.com": "Hotmail",
        "yahoo.com": "Yahoo", "protonmail.com": "ProtonMail", "proton.me": "Proton",
        "icloud.com": "iCloud",
    }
    return providers.get(domain, domain)


def _extract_domain(url: str) -> str | None:
    if not url:
        return None
    m = re.search(r"(?:https?://)?([A-Za-z0-9][A-Za-z0-9\-.]+\.[A-Za-z]{2,})", url)
    return m.group(1).lower().rstrip("/") if m else None


def _truncate(s: str, n: int) -> str:
    s = (s or "").strip().replace("\n", " ").replace("\r", " ")
    return s[:n] + "…" if len(s) > n else s


# ═════════════════════════════════════════════════════════════════
# 4. ROUTER
# ═════════════════════════════════════════════════════════════════

router = APIRouter(prefix="/api/socmint/mastodon", tags=["mastodon"])


class MastoTarget(BaseModel):
    raw: str = Field(..., min_length=1, max_length=200)


class MastoScanRequest(BaseModel):
    targets: list[MastoTarget] = Field(..., min_length=1, max_length=5)


@router.get("/capabilities")
def masto_capabilities() -> dict[str, Any]:
    return {
        "platform": "mastodon",
        "capabilities": MastoAdapter.capabilities,
        "input_types": ["username", "instance", "qualified"],
        "input_examples": [
            "gargron",
            "mastodon.social",
            "@gargron@mastodon.social",
            "https://mastodon.social/@gargron",
        ],
    }


@router.post("/scan", response_model=JobCreated)
def masto_scan(req: MastoScanRequest) -> JobCreated:
    adapter = MastoAdapter()
    classified: list[dict[str, str]] = []
    for t in req.targets:
        try:
            target_type, value = adapter.classify(t.raw)
            classified.append({"raw": t.raw, "type": target_type, "value": value})
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Gecersiz input '{t.raw}': {e}")

    task = celery_app.send_task("scan_platform_targets", args=["mastodon", classified])

    from app.routers.jobs import register_job
    register_job(task.id, "mastodon", len(classified))

    return JobCreated(
        job_id=task.id, platform="mastodon", target_count=len(classified),
    )


@router.post("/classify")
def masto_classify(req: MastoTarget) -> dict[str, str]:
    try:
        adapter = MastoAdapter()
        t, v = adapter.classify(req.raw)
        return {"type": t, "value": v, "raw": req.raw}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
