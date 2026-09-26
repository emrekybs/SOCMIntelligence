"""
Case persistence - SQLite ile investigation save/load/list.

Schema:
  cases(id PK, case_id, title, target, analyst, confidence, notes,
        scan_results_json, graph_json, scan_history_json,
        created_at, updated_at, platforms_csv)
  case_entities(case_id FK, entity_type, entity_value, platform, node_id)
    -- indexed for cross-case search: "bu email hangi case'lerde var"

Tek dosya /data/cases.db. Worker ve API aynı dosyaya erişir.
"""
from __future__ import annotations

import json
import os
import time
import sqlite3
import secrets
from pathlib import Path
from typing import Any
from datetime import datetime, timezone


DB_PATH = Path(os.getenv("CASES_DB_PATH", str(Path(__file__).resolve().parents[3] / "data" / "cases.db")))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _conn() -> sqlite3.Connection:
    """Sync SQLite connection - WAL mode for concurrent read/write."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Schema init - idempotent, her startup'ta cagrilir."""
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS cases (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id        TEXT UNIQUE NOT NULL,
            title          TEXT NOT NULL DEFAULT 'Untitled case',
            target         TEXT,
            analyst        TEXT DEFAULT 'Analyst',
            confidence     TEXT DEFAULT 'medium',
            notes          TEXT DEFAULT '',
            scan_results_json   TEXT DEFAULT '{}',
            graph_json          TEXT DEFAULT '{"nodes":[],"edges":[]}',
            scan_history_json   TEXT DEFAULT '[]',
            platforms_csv  TEXT DEFAULT '',
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cases_case_id    ON cases(case_id);
        CREATE INDEX IF NOT EXISTS idx_cases_target     ON cases(target);
        CREATE INDEX IF NOT EXISTS idx_cases_updated_at ON cases(updated_at DESC);

        -- Cross-case search: entities (emails, usernames, domains, urls)
        -- Her case scan edildiğinde graph node'lari buraya da yazilir.
        CREATE TABLE IF NOT EXISTS case_entities (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id      TEXT NOT NULL,
            entity_type  TEXT NOT NULL,  -- email, username, domain, url, person
            entity_value TEXT NOT NULL,  -- normalize edilmis deger
            platform     TEXT,
            node_id      TEXT,
            FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_entity_value ON case_entities(entity_value);
        CREATE INDEX IF NOT EXISTS idx_entity_type  ON case_entities(entity_type);
        CREATE INDEX IF NOT EXISTS idx_entity_case  ON case_entities(case_id);

        -- Saved queries (filter builder)
        CREATE TABLE IF NOT EXISTS saved_queries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            query_json  TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );
        """)


def generate_case_id() -> str:
    """Format: SMI-YYYYMMDD-XXXX (random 4 char)"""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    rand = secrets.token_hex(2).upper()
    return f"SMI-{today}-{rand}"


# ═════════════════════════════════════════════════════════════════
# CRUD
# ═════════════════════════════════════════════════════════════════

def create_case(
    *, title: str = "Untitled case", target: str = "",
    analyst: str = "Analyst", confidence: str = "medium",
) -> dict[str, Any]:
    case_id = generate_case_id()
    now = _now_iso()
    with _conn() as c:
        c.execute("""
            INSERT INTO cases (case_id, title, target, analyst, confidence, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (case_id, title, target, analyst, confidence, now, now))
    return get_case(case_id)


def get_case(case_id: str) -> dict[str, Any] | None:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        if not row:
            return None
        return _row_to_dict(row)


def list_cases(limit: int = 50, search: str = "") -> list[dict[str, Any]]:
    with _conn() as c:
        if search:
            q = f"%{search}%"
            rows = c.execute("""
                SELECT case_id, title, target, analyst, confidence,
                       platforms_csv, created_at, updated_at
                FROM cases
                WHERE case_id LIKE ? OR title LIKE ? OR target LIKE ? OR analyst LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
            """, (q, q, q, q, limit)).fetchall()
        else:
            rows = c.execute("""
                SELECT case_id, title, target, analyst, confidence,
                       platforms_csv, created_at, updated_at
                FROM cases
                ORDER BY updated_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def update_case(case_id: str, **fields: Any) -> dict[str, Any] | None:
    """Kismi guncelleme - title/notes/analyst/confidence/scan_results_json/graph_json/scan_history_json."""
    allowed = {
        "title", "target", "analyst", "confidence", "notes",
        "scan_results_json", "graph_json", "scan_history_json", "platforms_csv",
    }
    to_set = {k: v for k, v in fields.items() if k in allowed}
    if not to_set:
        return get_case(case_id)
    to_set["updated_at"] = _now_iso()

    set_clause = ", ".join(f"{k} = ?" for k in to_set)
    values = list(to_set.values()) + [case_id]
    with _conn() as c:
        c.execute(f"UPDATE cases SET {set_clause} WHERE case_id = ?", values)
    return get_case(case_id)


def delete_case(case_id: str) -> bool:
    with _conn() as c:
        cur = c.execute("DELETE FROM cases WHERE case_id = ?", (case_id,))
        return cur.rowcount > 0


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    # JSON field'lari parse et
    for k in ("scan_results_json", "graph_json", "scan_history_json"):
        if k in d and isinstance(d[k], str):
            try:
                d[k.replace("_json", "")] = json.loads(d[k])
            except (json.JSONDecodeError, TypeError):
                d[k.replace("_json", "")] = {} if "results" in k else []
            del d[k]
    d["platforms"] = [p for p in (d.pop("platforms_csv", "") or "").split(",") if p]
    return d


# ═════════════════════════════════════════════════════════════════
# ENTITIES (cross-case search)
# ═════════════════════════════════════════════════════════════════

def index_entities_from_graph(case_id: str, graph: dict[str, Any]) -> None:
    """Graph node'lari case_entities'a yaz - cross-case search icin."""
    with _conn() as c:
        # Eski entity'leri sil
        c.execute("DELETE FROM case_entities WHERE case_id = ?", (case_id,))
        for node in graph.get("nodes", []):
            node_id = node.get("id", "")
            node_type = node.get("type", "")
            label = node.get("label", "")
            platform = (node.get("meta", {}) or {}).get("Platform", "") \
                     or (node.get("meta", {}) or {}).get("platform", "")
            # Normalize: emailler lower-case, username'ler lower-case
            value = (label or "").strip().lower()
            if not value:
                continue
            c.execute("""
                INSERT INTO case_entities (case_id, entity_type, entity_value, platform, node_id)
                VALUES (?, ?, ?, ?, ?)
            """, (case_id, node_type, value, platform, node_id))


def find_entity_across_cases(entity_value: str) -> list[dict[str, Any]]:
    """Bir entity (email, username vs) hangi case'lerde gecmis — cross-case arama."""
    value = entity_value.strip().lower()
    with _conn() as c:
        rows = c.execute("""
            SELECT DISTINCT e.case_id, e.entity_type, e.platform, e.node_id,
                   c.title, c.target, c.updated_at
            FROM case_entities e
            JOIN cases c ON c.case_id = e.case_id
            WHERE e.entity_value = ?
            ORDER BY c.updated_at DESC
        """, (value,)).fetchall()
    return [dict(r) for r in rows]


def search_entities(
    query: str = "", entity_type: str | None = None, limit: int = 100,
) -> list[dict[str, Any]]:
    """Entity search with optional type filter - UI autocomplete icin."""
    with _conn() as c:
        if entity_type:
            rows = c.execute("""
                SELECT DISTINCT entity_value, entity_type,
                       COUNT(DISTINCT case_id) AS case_count
                FROM case_entities
                WHERE entity_type = ? AND entity_value LIKE ?
                GROUP BY entity_value
                ORDER BY case_count DESC, entity_value
                LIMIT ?
            """, (entity_type, f"%{query.lower()}%", limit)).fetchall()
        else:
            rows = c.execute("""
                SELECT DISTINCT entity_value, entity_type,
                       COUNT(DISTINCT case_id) AS case_count
                FROM case_entities
                WHERE entity_value LIKE ?
                GROUP BY entity_value, entity_type
                ORDER BY case_count DESC, entity_value
                LIMIT ?
            """, (f"%{query.lower()}%", limit)).fetchall()
    return [dict(r) for r in rows]


# ═════════════════════════════════════════════════════════════════
# SAVED QUERIES (filter builder)
# ═════════════════════════════════════════════════════════════════

def save_query(name: str, query: dict[str, Any]) -> dict[str, Any]:
    now = _now_iso()
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO saved_queries (name, query_json, created_at) VALUES (?, ?, ?)",
            (name, json.dumps(query), now),
        )
        row_id = cur.lastrowid
    return {"id": row_id, "name": name, "query": query, "created_at": now}


def list_saved_queries() -> list[dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, name, query_json, created_at FROM saved_queries ORDER BY created_at DESC"
        ).fetchall()
    return [
        {"id": r["id"], "name": r["name"],
         "query": json.loads(r["query_json"]), "created_at": r["created_at"]}
        for r in rows
    ]


def delete_saved_query(query_id: int) -> bool:
    with _conn() as c:
        cur = c.execute("DELETE FROM saved_queries WHERE id = ?", (query_id,))
        return cur.rowcount > 0
