"""
Case management router.

Endpoints:
  POST   /api/cases                     - Yeni case olustur
  GET    /api/cases                     - Tum case'leri listele (arama opsiyonel)
  GET    /api/cases/{case_id}           - Tek case detay
  PATCH  /api/cases/{case_id}           - Kismi guncelle (auto-save)
  DELETE /api/cases/{case_id}           - Sil

  GET    /api/cases/{case_id}/export    - .socmint (zip) indir
  POST   /api/cases/import              - .socmint (zip) yukle

  GET    /api/entities/find             - Cross-case entity arama
  GET    /api/entities/search           - Autocomplete icin entity listesi

  POST   /api/queries                   - Saved query kaydet
  GET    /api/queries                   - Tum saved query'ler
  DELETE /api/queries/{id}              - Saved query sil
"""
from __future__ import annotations

import io
import json
import zipfile
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core import cases_store

router = APIRouter(prefix="/api", tags=["cases"])


# ── Pydantic models ─────────────────────────────────────────────
class CaseCreate(BaseModel):
    title: str = Field(default="Untitled case", max_length=200)
    target: str = Field(default="", max_length=200)
    analyst: str = Field(default="Analyst", max_length=100)
    confidence: str = Field(default="medium", pattern="^(low|medium|high)$")


class CaseUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    target: str | None = Field(default=None, max_length=200)
    analyst: str | None = Field(default=None, max_length=100)
    confidence: str | None = Field(default=None, pattern="^(low|medium|high)$")
    notes: str | None = None  # markdown, buyuk olabilir
    scan_results: dict[str, Any] | None = None
    graph: dict[str, Any] | None = None
    scan_history: list[dict[str, Any]] | None = None
    platforms: list[str] | None = None


class SavedQuery(BaseModel):
    name: str = Field(..., max_length=100)
    query: dict[str, Any]


# ── Case CRUD ───────────────────────────────────────────────────
@router.post("/cases")
def create_case(req: CaseCreate) -> dict[str, Any]:
    return cases_store.create_case(
        title=req.title, target=req.target,
        analyst=req.analyst, confidence=req.confidence,
    )


@router.get("/cases")
def list_cases(
    search: str = Query(default="", max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    cases = cases_store.list_cases(limit=limit, search=search)
    return {"cases": cases, "count": len(cases)}


@router.get("/cases/{case_id}")
def get_case(case_id: str) -> dict[str, Any]:
    case = cases_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return case


@router.patch("/cases/{case_id}")
def update_case(case_id: str, req: CaseUpdate) -> dict[str, Any]:
    existing = cases_store.get_case(case_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    update_fields: dict[str, Any] = {}
    if req.title is not None:      update_fields["title"] = req.title
    if req.target is not None:     update_fields["target"] = req.target
    if req.analyst is not None:    update_fields["analyst"] = req.analyst
    if req.confidence is not None: update_fields["confidence"] = req.confidence
    if req.notes is not None:      update_fields["notes"] = req.notes
    if req.scan_results is not None:
        update_fields["scan_results_json"] = json.dumps(req.scan_results)
    if req.graph is not None:
        update_fields["graph_json"] = json.dumps(req.graph)
        # Entity index guncelle - cross-case search icin
        cases_store.index_entities_from_graph(case_id, req.graph)
    if req.scan_history is not None:
        update_fields["scan_history_json"] = json.dumps(req.scan_history)
    if req.platforms is not None:
        update_fields["platforms_csv"] = ",".join(sorted(set(req.platforms)))

    updated = cases_store.update_case(case_id, **update_fields)
    return updated or existing


@router.delete("/cases/{case_id}")
def delete_case(case_id: str) -> dict[str, Any]:
    ok = cases_store.delete_case(case_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return {"deleted": True, "case_id": case_id}


# ── Export/Import .socmint ─────────────────────────────────────────
@router.get("/cases/{case_id}/export")
def export_case(case_id: str):
    """.socmint uzantili zip dosyasi olarak indir.
    Icerik: case.json (metadata + scan_results + graph + notes + history)
    """
    case = cases_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("case.json", json.dumps(case, indent=2, ensure_ascii=False))
        zf.writestr("README.txt",
            f"SOCMIntelligence vaka paketi\n"
            f"Case ID: {case['case_id']}\n"
            f"Title:   {case['title']}\n"
            f"Target:  {case['target']}\n"
            f"Exported: {case['updated_at']}\n\n"
            f"Ice aktarmak icin: SOCMIntelligence > Vakalar > Ice aktar\n"
        )
    buf.seek(0)

    filename = f"{case['case_id']}.socmint"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/cases/import")
async def import_case(file: UploadFile = File(...)) -> dict[str, Any]:
    """.socmint (zip) dosyasini yukle - yeni case olarak import et."""
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:  # 50 MB limit
        raise HTTPException(status_code=413, detail="File too large (max 50 MB)")

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            if "case.json" not in zf.namelist():
                raise HTTPException(status_code=400, detail="Invalid .socmint file: no case.json")
            case_json = zf.read("case.json").decode("utf-8")
            imported = json.loads(case_json)
    except (zipfile.BadZipFile, json.JSONDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid .socmint file: {e}")

    # Yeni case_id ata (import cakisma olmasin diye)
    original_id = imported.get("case_id", "imported")
    new_case = cases_store.create_case(
        title=f"[imported] {imported.get('title', 'Untitled')}",
        target=imported.get("target", ""),
        analyst=imported.get("analyst", "Analyst"),
        confidence=imported.get("confidence", "medium"),
    )
    cases_store.update_case(
        new_case["case_id"],
        notes=imported.get("notes", ""),
        scan_results_json=json.dumps(imported.get("scan_results", {})),
        graph_json=json.dumps(imported.get("graph", {"nodes": [], "edges": []})),
        scan_history_json=json.dumps(imported.get("scan_history", [])),
        platforms_csv=",".join(imported.get("platforms", [])),
    )
    # Entity index
    graph = imported.get("graph", {"nodes": [], "edges": []})
    cases_store.index_entities_from_graph(new_case["case_id"], graph)

    return {
        "imported": True,
        "new_case_id": new_case["case_id"],
        "original_case_id": original_id,
    }


# ── Cross-case entity search ────────────────────────────────────
@router.get("/entities/find")
def find_entity(value: str = Query(..., min_length=2, max_length=200)) -> dict[str, Any]:
    """Bir email/username/domain hangi case'lerde geciyor?"""
    results = cases_store.find_entity_across_cases(value)
    return {
        "value": value,
        "matches": results,
        "case_count": len(set(r["case_id"] for r in results)),
    }


@router.get("/entities/search")
def search_entities(
    q: str = Query(default="", max_length=200),
    type: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Entity autocomplete - UI icin."""
    results = cases_store.search_entities(
        query=q, entity_type=type, limit=limit,
    )
    return {"results": results, "count": len(results)}


# ── Saved queries ───────────────────────────────────────────────
@router.post("/queries")
def save_query(req: SavedQuery) -> dict[str, Any]:
    return cases_store.save_query(name=req.name, query=req.query)


@router.get("/queries")
def list_queries() -> dict[str, Any]:
    qs = cases_store.list_saved_queries()
    return {"queries": qs, "count": len(qs)}


@router.delete("/queries/{query_id}")
def delete_query(query_id: int) -> dict[str, Any]:
    ok = cases_store.delete_saved_query(query_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Query {query_id} not found")
    return {"deleted": True, "id": query_id}
