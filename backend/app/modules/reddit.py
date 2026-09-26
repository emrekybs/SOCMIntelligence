"""
Reddit OSINT modulu - SOCMIntelligence platformu.

Icerik:
  1. Schemas         - user profile + subreddit (discriminated by 'type' field)
  2. RedditAdapter   - classify (user|subreddit) + scan + to_graph
  3. Router
  4. GraphConverter

Tool: tools/reddit_osint.py
  Input tipleri:
    spez, @spez, u/spez         -> user
    r/OSINT                     -> subreddit
    URL (reddit.com/user/...)   -> user
    URL (reddit.com/r/...)      -> subreddit
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

# --- User ---

class RedditUserProfile(BaseModel):
    display_name: str | None = None
    id: str | None = None
    created_utc: float | None = None
    created_date: str | None = None
    account_age: str | None = None
    total_karma: int | None = None
    post_karma: int | None = None
    comment_karma: int | None = None
    verified: bool | None = None
    employee: bool | None = None
    nsfw: bool | None = None
    has_avatar: bool | None = None
    avatar_url: str | None = None
    description: str | None = None
    is_suspended: bool | None = None


class RedditUserStats(BaseModel):
    comments_fetched: int = 0
    posts_fetched: int = 0


class RedditSubredditActivity(BaseModel):
    """En aktif olunan subreddit'ler."""
    name: str | None = None
    comments: int = 0
    posts: int = 0


class RedditUserData(BaseModel):
    """type=user icin ana payload."""
    username: str
    profile_url: str | None = None
    scanned_at: str | None = None
    profile: RedditUserProfile | None = None
    stats: RedditUserStats | None = None
    subreddit_analysis: dict[str, Any] | None = None
    activity_analysis: dict[str, Any] | None = None
    content_analysis: dict[str, Any] | None = None
    bot_score: dict[str, Any] | None = None
    error: str | None = None


# --- Subreddit ---

class RedditSubredditAbout(BaseModel):
    display_name: str | None = None
    title: str | None = None
    description: str | None = None
    subscribers: int | None = None
    active_users: int | None = None
    created_date: str | None = None
    age: str | None = None
    nsfw: bool | None = None
    verified: bool | None = None
    type: str | None = None
    lang: str | None = None
    allow_images: bool | None = None
    allow_videos: bool | None = None


class RedditPostAnalysis(BaseModel):
    total_analyzed: int = 0
    avg_score: int | None = None
    avg_comments: int | None = None
    top_authors: list[dict[str, Any]] = Field(default_factory=list)
    top_flairs: list[dict[str, Any]] = Field(default_factory=list)
    top_domains: list[dict[str, Any]] = Field(default_factory=list)
    hour_distribution: dict[str, int] = Field(default_factory=dict)
    day_distribution: dict[str, int] = Field(default_factory=dict)
    best_hour: str | None = None
    best_day: str | None = None
    top_posts: list[dict[str, Any]] = Field(default_factory=list)


class RedditEngagement(BaseModel):
    active_ratio_pct: float | None = None
    label: str | None = None


class RedditSubredditData(BaseModel):
    """type=subreddit icin ana payload."""
    type: str = "subreddit"
    name: str
    url: str | None = None
    scanned_at: str | None = None
    about: RedditSubredditAbout | None = None
    post_analysis: RedditPostAnalysis | None = None
    moderators: list[dict[str, Any]] = Field(default_factory=list)
    engagement: RedditEngagement | None = None
    error: str | None = None


# ═════════════════════════════════════════════════════════════════
# 2. ADAPTER
# ═════════════════════════════════════════════════════════════════

class RedditAdapter(PlatformAdapter):
    platform = "reddit"
    script = "reddit_osint.py"
    capabilities = ["scan"]
    cache_ttl = 600  # 10dk

    def classify(self, raw: str) -> tuple[str, str]:
        """
        Input tipleri (tool'un parse_target mantigi birebir):
          "spez"                                  -> ("user", "spez")
          "@spez"                                 -> ("user", "spez")
          "u/spez", "/u/spez"                     -> ("user", "spez")
          "r/OSINT", "/r/OSINT"                   -> ("subreddit", "OSINT")
          "reddit.com/user/spez"                  -> ("user", "spez")
          "reddit.com/r/OSINT/..."                -> ("subreddit", "OSINT")
        """
        t = (raw or "").strip().rstrip("/")
        if not t:
            raise ValueError("Bos input")

        # Subreddit URL (herhangi subdomain)
        m = re.search(r"reddit\.com/r/([A-Za-z0-9_]+)", t, re.I)
        if m:
            return ("subreddit", m.group(1))

        # r/X or /r/X
        m = re.match(r"^/?r/([A-Za-z0-9_]+)$", t, re.I)
        if m:
            return ("subreddit", m.group(1))

        # User URL
        m = re.search(r"reddit\.com/(?:user|u)/([A-Za-z0-9_\-]+)", t, re.I)
        if m:
            return ("user", m.group(1))

        # u/X or /u/X
        m = re.match(r"^/?u/([A-Za-z0-9_\-]+)$", t, re.I)
        if m:
            return ("user", m.group(1))

        # @username
        m = re.match(r"^@([A-Za-z0-9_\-]+)$", t)
        if m:
            return ("user", m.group(1))

        # Plain username
        if re.match(r"^[A-Za-z0-9_\-]{3,20}$", t):
            return ("user", t)

        raise ValueError(f"Gecersiz Reddit input: {raw}")

    async def scan(self, target_type: str, value: str) -> dict[str, Any]:
        if target_type not in ("user", "subreddit"):
            raise ValueError(f"Desteklenmeyen tip: {target_type}")

        # Tool input'u format olarak u/X veya r/X tercih eder
        prefix = "r/" if target_type == "subreddit" else "u/"
        tool_arg = f"{prefix}{value}"

        result = await self._run_tool_auto_output(
            target_type=target_type,
            value=value,
            args=[tool_arg, "--no-color", "--limit", "100"],
            output_pattern="reddit_*.json",
            timeout=120,
        )

        # Tool error field'i dondurur
        if result.get("error"):
            raise LookupError(result["error"])

        # User output'ta 'type' field'i yok; backend-side ekle
        if target_type == "user" and "type" not in result:
            result["type"] = "user"

        # Pydantic validation - discriminated by 'type'
        try:
            if result.get("type") == "subreddit":
                validated = RedditSubredditData.model_validate(result)
            else:
                validated = RedditUserData.model_validate(result)
            return validated.model_dump(mode="json")
        except Exception:
            return result

    def to_graph(self, data: dict[str, Any]) -> dict[str, list]:
        return RedditGraphConverter.convert(data)


# ═════════════════════════════════════════════════════════════════
# 3. GRAPH CONVERTER
# ═════════════════════════════════════════════════════════════════

class RedditGraphConverter:
    """
    Reddit scan sonucunu graph'e cevirir - discriminated:
      type=subreddit -> domain node (subreddit) + top_authors = username[]
      type=user      -> person node + top subreddits = domain[]
    """

    @staticmethod
    def convert(data: dict[str, Any]) -> dict[str, list]:
        if data.get("type") == "subreddit":
            return RedditGraphConverter._convert_subreddit(data)
        return RedditGraphConverter._convert_user(data)

    @staticmethod
    def _convert_subreddit(data: dict[str, Any]) -> dict[str, list]:
        nodes: list[dict] = []
        edges: list[dict] = []
        name = data.get("name") or "unknown"
        about = data.get("about") or {}
        post_anl = data.get("post_analysis") or {}

        # Subreddit kendisi domain node'u
        sub_id = f"d_reddit_sub_{_slug(name)}"
        nodes.append({
            "id": sub_id,
            "type": "domain",
            "label": f"r/{name}",
            "meta": {
                "Platform": "Reddit",
                "Title": about.get("title") or "—",
                "Subscribers": str(about.get("subscribers") or 0),
                "Active": str(about.get("active_users") or 0),
                "Created": about.get("created_date") or "—",
                "Age": about.get("age") or "—",
                "NSFW": "Yes" if about.get("nsfw") else "No",
                "Type": about.get("type") or "—",
                "URL": data.get("url") or "",
            },
        })

        # Top authors -> username nodes
        for author in (post_anl.get("top_authors") or [])[:10]:
            if not isinstance(author, dict):
                continue
            user = author.get("user")
            if not user or user.startswith("["):  # "[deleted]" gibileri
                continue
            u_id = f"u_reddit_{_slug(user)}"
            if _has_node(nodes, u_id):
                continue
            nodes.append({
                "id": u_id,
                "type": "username",
                "label": f"u/{user}",
                "meta": {
                    "Platforms": "Reddit",
                    "Profile": f"https://www.reddit.com/user/{user}",
                    "Posts_in_sub": str(author.get("posts") or 0),
                },
            })
            edges.append({
                "id": f"ed_{u_id}_{sub_id}",
                "source": u_id,
                "target": sub_id,
                "type": "appears_in",
            })

        # Moderators
        for mod in (data.get("moderators") or [])[:10]:
            if not isinstance(mod, dict):
                continue
            user = mod.get("name") or mod.get("user")
            if not user:
                continue
            u_id = f"u_reddit_{_slug(user)}"
            if not _has_node(nodes, u_id):
                nodes.append({
                    "id": u_id,
                    "type": "username",
                    "label": f"u/{user}",
                    "meta": {
                        "Platforms": "Reddit",
                        "Role": "Moderator",
                        "Profile": f"https://www.reddit.com/user/{user}",
                    },
                })
            edges.append({
                "id": f"ed_mod_{u_id}_{sub_id}",
                "source": u_id,
                "target": sub_id,
                "type": "registered_to",
            })

        # Top domains - external sites linked
        for dom_info in (post_anl.get("top_domains") or [])[:5]:
            if not isinstance(dom_info, dict):
                continue
            dom = dom_info.get("domain")
            if not dom or dom in ("i.redd.it", "v.redd.it", "reddit.com", "self." + name):
                continue
            d_id = f"d_ext_{_slug(dom)}"
            if not _has_node(nodes, d_id):
                nodes.append({
                    "id": d_id,
                    "type": "domain",
                    "label": dom,
                    "meta": {
                        "Source": f"Linked from r/{name}",
                        "Count": str(dom_info.get("count") or 0),
                    },
                })
            edges.append({
                "id": f"ed_{sub_id}_{d_id}",
                "source": sub_id,
                "target": d_id,
                "type": "linked_to",
            })

        return _dedup_graph({"nodes": nodes, "edges": edges})

    @staticmethod
    def _convert_user(data: dict[str, Any]) -> dict[str, list]:
        nodes: list[dict] = []
        edges: list[dict] = []
        username = data.get("username") or "unknown"
        profile = data.get("profile") or {}
        sub_anl = data.get("subreddit_analysis") or {}

        # Person node
        person_id = f"p_reddit_{_slug(username)}"
        nodes.append({
            "id": person_id,
            "type": "person",
            "label": profile.get("display_name") or username,
            "meta": {
                "Platform": "Reddit",
                "Username": username,
                "Total_Karma": str(profile.get("total_karma") or 0),
                "Post_Karma": str(profile.get("post_karma") or 0),
                "Comment_Karma": str(profile.get("comment_karma") or 0),
                "Age": profile.get("account_age") or "—",
                "Created": profile.get("created_date") or "—",
                "Verified": "Yes" if profile.get("verified") else "No",
                "Suspended": "Yes" if profile.get("is_suspended") else "No",
            },
        })

        # Username node
        u_id = f"u_reddit_{_slug(username)}"
        nodes.append({
            "id": u_id,
            "type": "username",
            "label": f"u/{username}",
            "meta": {
                "Platforms": "Reddit",
                "Profile": data.get("profile_url") or f"https://www.reddit.com/user/{username}",
            },
        })
        edges.append({
            "id": f"ed_{person_id}_{u_id}",
            "source": person_id,
            "target": u_id,
            "type": "owns",
        })

        # Top subreddits - appears_in edges
        top_subs = sub_anl.get("top_subreddits") or sub_anl.get("most_active") or []
        # Schema'ya gore isim farkli olabilir - ikisini de dene
        if isinstance(top_subs, dict):
            # {"OSINT": 45, "netsec": 22} formati
            top_subs = [{"name": k, "count": v} for k, v in top_subs.items()]
        for sub in (top_subs or [])[:8]:
            if not isinstance(sub, dict):
                continue
            sub_name = sub.get("name") or sub.get("subreddit")
            if not sub_name:
                continue
            sub_id = f"d_reddit_sub_{_slug(sub_name)}"
            if not _has_node(nodes, sub_id):
                nodes.append({
                    "id": sub_id,
                    "type": "domain",
                    "label": f"r/{sub_name}",
                    "meta": {
                        "Platform": "Reddit subreddit",
                        "User_activity": str(sub.get("count") or sub.get("posts") or 0),
                    },
                })
            edges.append({
                "id": f"ed_{person_id}_{sub_id}",
                "source": person_id,
                "target": sub_id,
                "type": "appears_in",
            })

        return _dedup_graph({"nodes": nodes, "edges": edges})


# ─── Helpers (same as other modules) ──────────────────────────────

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


# ═════════════════════════════════════════════════════════════════
# 4. ROUTER
# ═════════════════════════════════════════════════════════════════

router = APIRouter(prefix="/api/socmint/reddit", tags=["reddit"])


class RedditTarget(BaseModel):
    raw: str = Field(..., min_length=1, max_length=200)


class RedditScanRequest(BaseModel):
    targets: list[RedditTarget] = Field(..., min_length=1, max_length=10)


@router.get("/capabilities")
def reddit_capabilities() -> dict[str, Any]:
    return {
        "platform": "reddit",
        "capabilities": RedditAdapter.capabilities,
        "input_types": ["user", "subreddit"],
        "input_examples": [
            "spez",
            "u/spez",
            "@spez",
            "https://reddit.com/user/spez",
            "r/OSINT",
            "https://reddit.com/r/OSINT",
        ],
    }


@router.post("/scan", response_model=JobCreated)
def reddit_scan(req: RedditScanRequest) -> JobCreated:
    adapter = RedditAdapter()
    classified: list[dict[str, str]] = []
    for t in req.targets:
        try:
            target_type, value = adapter.classify(t.raw)
            classified.append({"raw": t.raw, "type": target_type, "value": value})
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Gecersiz input '{t.raw}': {e}")

    task = celery_app.send_task("scan_platform_targets", args=["reddit", classified])

    from app.routers.jobs import register_job
    register_job(task.id, "reddit", len(classified))

    return JobCreated(
        job_id=task.id, platform="reddit", target_count=len(classified),
    )


@router.post("/classify")
def reddit_classify(req: RedditTarget) -> dict[str, str]:
    try:
        adapter = RedditAdapter()
        t, v = adapter.classify(req.raw)
        return {"type": t, "value": v, "raw": req.raw}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
