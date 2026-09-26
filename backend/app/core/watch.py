"""
Degisiklik takibi (izleme): belirli araliklarla bir hedefi yeniden tarar, onceki tarama ile farki kaydeder.

Tablolar (cases.db icinde):
  watches(id, platform, raw, type, value, interval_hours, enabled, created_at, last_run, next_run, last_status, last_error, change_count)
  watch_snapshots(id, watch_id, at, status, sha256, flat_json, nodes_json, diff_json, error)
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core import cases_store

logger = logging.getLogger(__name__)
VOLATILE = {"scanned_at", "scanned", "duration_ms", "quota_remaining", "local_time", "online_state", "state_message",
            "persona_state", "last_logoff", "timestamp", "avatar_path", "posts_per_day",
            # her taramada imzasi degisen CDN URL'leri (gercek degisiklik degil) — izlemede gurultu yapmasin
            "profile_pic_url", "profile_pic_hd", "profile_pic", "thumbnail_url", "media_url", "banner",
            "avatar_url", "avatar", "photo", "image", "hd_profile_pic_url"}
_run_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def init_db() -> None:
    with cases_store._conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS watches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL, raw TEXT NOT NULL, type TEXT, value TEXT,
            interval_hours REAL NOT NULL DEFAULT 24, enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, last_run TEXT, next_run TEXT, last_status TEXT, last_error TEXT,
            change_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS watch_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watch_id INTEGER NOT NULL, at TEXT NOT NULL, status TEXT, sha256 TEXT,
            flat_json TEXT, nodes_json TEXT, diff_json TEXT, error TEXT,
            FOREIGN KEY (watch_id) REFERENCES watches(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_ws_watch ON watch_snapshots(watch_id, at DESC);
        """)


def flatten(obj: Any, prefix: str = "", depth: int = 0, out: dict | None = None) -> dict[str, Any]:
    """Karsilastirma icin duzlestir: skalerler yol->deger; listeler icin eleman sayisi."""
    out = {} if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in VOLATILE:
                continue
            flatten(v, f"{prefix}.{k}" if prefix else str(k), depth + 1, out)
    elif isinstance(obj, list):
        out[f"{prefix}[#]"] = len(obj)
        if depth < 3 and obj and all(isinstance(x, (str, int, float)) for x in obj) and len(obj) <= 50:
            out[prefix] = sorted(str(x) for x in obj)
    elif depth <= 5:
        if isinstance(obj, str) and len(obj) > 500:
            obj = obj[:500]
        out[prefix] = obj
    return out


def diff(old: dict, new: dict, old_nodes: list, new_nodes: list) -> dict[str, Any]:
    changes = []
    for k in sorted(set(old) | set(new)):
        a, b = old.get(k), new.get(k)
        if a != b:
            changes.append({"path": k, "old": a, "new": b})
    on, nn = {n["id"]: n["label"] for n in old_nodes}, {n["id"]: n["label"] for n in new_nodes}
    return {
        "changes": changes[:300], "change_total": len(changes),
        "nodes_added": [nn[i] for i in nn.keys() - on.keys()][:100],
        "nodes_removed": [on[i] for i in on.keys() - nn.keys()][:100],
    }


def _row(r) -> dict[str, Any]:
    d = dict(r)
    d["enabled"] = bool(d.get("enabled"))
    return d


def list_watches() -> list[dict]:
    with cases_store._conn() as c:
        return [_row(r) for r in c.execute("SELECT * FROM watches ORDER BY id DESC").fetchall()]


def get_watch(wid: int) -> dict | None:
    with cases_store._conn() as c:
        r = c.execute("SELECT * FROM watches WHERE id = ?", (wid,)).fetchone()
        return _row(r) if r else None


def create_watch(platform: str, raw: str, ttype: str, value: str, interval_hours: float) -> dict:
    now = _now()
    with cases_store._conn() as c:
        cur = c.execute("""INSERT INTO watches (platform, raw, type, value, interval_hours, enabled, created_at, next_run)
                           VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
                        (platform, raw, ttype, value, interval_hours, now.isoformat(), now.isoformat()))
        wid = cur.lastrowid
    return get_watch(wid)


def update_watch(wid: int, **fields) -> dict | None:
    allowed = {k: v for k, v in fields.items() if k in ("enabled", "interval_hours") and v is not None}
    if "enabled" in allowed:
        allowed["enabled"] = 1 if allowed["enabled"] else 0
    if allowed:
        sets = ", ".join(f"{k} = ?" for k in allowed)
        with cases_store._conn() as c:
            c.execute(f"UPDATE watches SET {sets} WHERE id = ?", (*allowed.values(), wid))
    return get_watch(wid)


def delete_watch(wid: int) -> bool:
    with cases_store._conn() as c:
        c.execute("DELETE FROM watch_snapshots WHERE watch_id = ?", (wid,))
        return c.execute("DELETE FROM watches WHERE id = ?", (wid,)).rowcount > 0


def snapshots(wid: int, limit: int = 50) -> list[dict]:
    with cases_store._conn() as c:
        rows = c.execute("SELECT id, watch_id, at, status, sha256, diff_json, error FROM watch_snapshots WHERE watch_id = ? ORDER BY id DESC LIMIT ?",
                         (wid, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["diff"] = json.loads(d.pop("diff_json") or "null")
        out.append(d)
    return out


def run_watch(wid: int) -> dict | None:
    """Senkron calisir (thread'de). Cache'i atlayarak hedefi yeniden tarar, farki kaydeder."""
    w = get_watch(wid)
    if not w:
        return None
    from app.core.cache import cache
    from app.tasks.scan_tasks import _get_adapter, _scan_one, sha256_of

    adapter = _get_adapter(w["platform"])

    async def go():
        await cache.invalidate_tool(w["platform"], w["type"], w["value"])
        return await _scan_one(adapter, {"raw": w["raw"], "type": w["type"], "value": w["value"]})

    with _run_lock:
        res = asyncio.run(go())
    now = _now()
    status, data = res.get("status"), res.get("data")
    with cases_store._conn() as c:
        prev = c.execute("SELECT flat_json, nodes_json FROM watch_snapshots WHERE watch_id = ? AND status = 'ok' ORDER BY id DESC LIMIT 1",
                         (wid,)).fetchone()
        flat = flatten(data) if data else None
        nodes = [{"id": n["id"], "label": n["label"]} for n in ((res.get("graph") or {}).get("nodes") or [])]
        d = None
        if status == "ok" and prev:
            d = diff(json.loads(prev["flat_json"] or "{}"), flat or {}, json.loads(prev["nodes_json"] or "[]"), nodes)
        elif status != "ok" and prev:
            d = {"changes": [{"path": "(durum)", "old": "ok", "new": status}], "change_total": 1, "nodes_added": [], "nodes_removed": []}
        changed = bool(d and (d["change_total"] or d["nodes_added"] or d["nodes_removed"]))
        c.execute("""INSERT INTO watch_snapshots (watch_id, at, status, sha256, flat_json, nodes_json, diff_json, error)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                  (wid, now.isoformat(timespec="seconds"), status, sha256_of(data) if data else None,
                   json.dumps(flat, ensure_ascii=False, default=str) if flat else None,
                   json.dumps(nodes, ensure_ascii=False), json.dumps(d, ensure_ascii=False, default=str) if d else None, res.get("error")))
        nxt = now + timedelta(hours=float(w["interval_hours"]))
        c.execute("""UPDATE watches SET last_run = ?, next_run = ?, last_status = ?, last_error = ?, change_count = change_count + ?
                     WHERE id = ?""", (now.isoformat(timespec="seconds"), nxt.isoformat(timespec="seconds"), status, res.get("error"),
                                      1 if changed else 0, wid))
    return get_watch(wid)


async def scheduler_loop(stop: asyncio.Event) -> None:
    """Her dakika vadesi gelen izlemeleri calistirir."""
    while not stop.is_set():
        try:
            now = _now().isoformat()
            with cases_store._conn() as c:
                due = [r["id"] for r in c.execute("SELECT id FROM watches WHERE enabled = 1 AND (next_run IS NULL OR next_run <= ?)", (now,)).fetchall()]
            for wid in due:
                logger.info(f"[izleme] #{wid} calisiyor")
                try:
                    await asyncio.to_thread(run_watch, wid)
                except Exception as e:  # noqa: BLE001
                    logger.exception(f"[izleme] #{wid} hata: {e}")
        except Exception as e:  # noqa: BLE001
            logger.error(f"[izleme] zamanlayici hatasi: {e}")
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass
