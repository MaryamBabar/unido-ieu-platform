"""
FastAPI backend — no LLM, runs with Qdrant + LangSmith only.
"""

import json
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import config
from models import QueryRequest, HealthResponse, StatsResponse
from rag_pipeline import run_query, check_qdrant_health, get_qdrant, create_text_index
from auth import authenticate, validate_session, logout, create_user, set_user_active, change_password, delete_user, list_users, get_active_sessions

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

missing = config.validate()
if missing:
    logger.warning(f"⚠️  Missing credentials: {', '.join(missing)} — check your .env file")
else:
    logger.info("✅ Credentials loaded. Starting backend...")

app = FastAPI(title="UNIDO IEU Evaluation Intelligence Platform", version="1.0.0")


@app.on_event("startup")
async def startup_event():
    """Create Qdrant text index for hybrid search on first startup."""
    if not config.validate():  # only if credentials are present
        create_text_index()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# Auth models + dependency
# ─────────────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class CreateUserRequest(BaseModel):
    username: str
    password: str
    display_name: str
    role: str = "user"

class ChangePasswordRequest(BaseModel):
    new_password: str

class SetActiveRequest(BaseModel):
    active: bool


_BYPASS_TOKEN = "no-auth-bypass"

def require_auth(x_session_token: Optional[str] = Header(default=None)) -> dict:
    # Temporary bypass — remove once users.yaml is stable on Railway
    if x_session_token == _BYPASS_TOKEN:
        return {"username": "guest", "display_name": "Guest", "role": "admin",
                "login_time": "bypass"}
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    session = validate_session(x_session_token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    return session


def require_admin(session: dict = Depends(require_auth)) -> dict:
    if session.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return session


# ─────────────────────────────────────────────────────────────────────────────
# Auth endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/auth/login")
async def login(request: LoginRequest):
    token = authenticate(request.username, request.password)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    session = validate_session(token)
    return {"session_token": token, **session}


@app.post("/api/v1/auth/logout")
async def api_logout(session: dict = Depends(require_auth),
                     x_session_token: Optional[str] = Header(default=None)):
    logout(x_session_token)
    return {"detail": "Logged out."}


@app.get("/api/v1/auth/me")
async def me(session: dict = Depends(require_auth)):
    return session


# ─────────────────────────────────────────────────────────────────────────────
# Admin endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/admin/users")
async def admin_list_users(session: dict = Depends(require_admin)):
    return {"users": list_users(), "active_sessions": get_active_sessions()}


@app.post("/api/v1/admin/users")
async def admin_create_user(request: CreateUserRequest, session: dict = Depends(require_admin)):
    try:
        user = create_user(request.username, request.password, request.display_name, request.role, session["username"])
        return {"detail": f"User '{request.username}' created.", "user": user}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/api/v1/admin/users/{username}/active")
async def admin_set_active(username: str, request: SetActiveRequest, session: dict = Depends(require_admin)):
    try:
        set_user_active(username, request.active, session["username"])
        return {"detail": f"User '{username}' {'activated' if request.active else 'deactivated'}."}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/v1/admin/users/{username}/password")
async def admin_change_password(username: str, request: ChangePasswordRequest, session: dict = Depends(require_admin)):
    try:
        change_password(username, request.new_password, session["username"])
        return {"detail": f"Password changed for '{username}'."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/v1/admin/users/{username}")
async def admin_delete_user(username: str, session: dict = Depends(require_admin)):
    if username == session["username"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account.")
    try:
        delete_user(username, session["username"])
        return {"detail": f"User '{username}' deleted."}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Core endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/health", response_model=HealthResponse)
async def health():
    qdrant_status = check_qdrant_health()
    missing_creds = config.validate()
    return HealthResponse(
        status="healthy" if not missing_creds and qdrant_status["qdrant_connected"] else "degraded",
        qdrant_connected=qdrant_status["qdrant_connected"],
        collection_exists=qdrant_status["collection_exists"],
        document_count=qdrant_status["document_count"],
        missing_credentials=missing_creds,
    )


@app.post("/api/v1/query")
async def query(request: QueryRequest, session: dict = Depends(require_auth)):
    """
    Retrieval-only query. Returns ranked passages — no LLM.
    Add LLM later by plugging into the returned passages.
    """
    missing_creds = config.validate()
    if missing_creds:
        raise HTTPException(status_code=503, detail=f"Missing credentials: {missing_creds}")

    citations, metadata = run_query(query=request.query, filters=request.filters)

    return {
        "passages": [c.model_dump() for c in citations],
        "query_id": metadata["query_id"],
        "retrieval_count": metadata["retrieval_count"],
        "reranked_count": metadata["reranked_count"],
        "search_ms": metadata["search_ms"],
        "rerank_ms": metadata["rerank_ms"],
    }


@app.get("/api/v1/stats", response_model=StatsResponse)
async def stats():
    try:
        client = get_qdrant()
        info = client.get_collection(config.QDRANT_COLLECTION)
        total_chunks = info.points_count or 0

        all_payloads = []
        offset = None
        while True:
            results, next_offset = client.scroll(
                collection_name=config.QDRANT_COLLECTION,
                limit=500, offset=offset,
                with_payload=["report_id", "year", "thematic_category", "sdgs", "dac_criteria"],
            )
            all_payloads.extend(r.payload for r in results)
            if next_offset is None:
                break
            offset = next_offset

        seen = set()
        unique = []
        for p in all_payloads:
            rid = p.get("report_id")
            if rid and rid not in seen:
                seen.add(rid)
                unique.append(p)

        by_year, by_thematic, by_sdg, by_dac = {}, {}, {}, {}
        for p in unique:
            y = str(p.get("year") or "Unknown")
            by_year[y] = by_year.get(y, 0) + 1
            t = p.get("thematic_category") or "Unknown"
            by_thematic[t] = by_thematic.get(t, 0) + 1
            for s in (p.get("sdgs") or []):
                k = f"SDG {s}"
                by_sdg[k] = by_sdg.get(k, 0) + 1
            for d in (p.get("dac_criteria") or []):
                by_dac[d] = by_dac.get(d, 0) + 1

        return StatsResponse(
            total_chunks=total_chunks, total_documents=len(unique),
            documents_by_year=dict(sorted(by_year.items())),
            documents_by_thematic=dict(sorted(by_thematic.items(), key=lambda x: -x[1])),
            documents_by_sdg=dict(sorted(by_sdg.items())),
            documents_by_dac=dict(sorted(by_dac.items())),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/reports/list")
async def list_reports(session: dict = Depends(require_auth)):
    """Return all unique reports indexed in Qdrant with their metadata."""
    try:
        client = get_qdrant()
        seen: dict = {}
        offset = None
        while True:
            results, next_offset = client.scroll(
                collection_name=config.QDRANT_COLLECTION,
                limit=500, offset=offset,
                with_payload=True,
            )
            for point in results:
                p = point.payload or {}
                rid = p.get("report_id")
                if rid and rid not in seen:
                    seen[rid] = {
                        "report_id": rid,
                        "title": p.get("title", "Unknown"),
                        "year": p.get("year"),
                        "country": p.get("country", ""),
                        "region": p.get("region", ""),
                        "thematic_category": p.get("thematic_category", ""),
                        "dac_criteria": p.get("dac_criteria", []),
                        "sdgs": p.get("sdgs", []),
                        "evaluation_type": p.get("evaluation_type", ""),
                        "donor": p.get("donor", ""),
                    }
            if next_offset is None:
                break
            offset = next_offset
        reports = sorted(seen.values(), key=lambda r: r.get("year") or 0, reverse=True)
        return {"reports": reports, "total": len(reports)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/lessons")
async def get_lessons(
    report_ids: str = Query(default=""),
    session: dict = Depends(require_auth),
):
    """Get lessons learned and recommendations grouped by report."""
    try:
        client = get_qdrant()
        rid_set = set(r.strip() for r in report_ids.split(",") if r.strip()) if report_ids else set()
        results_by_report: dict = {}
        offset = None
        while True:
            results, next_offset = client.scroll(
                collection_name=config.QDRANT_COLLECTION,
                limit=500, offset=offset,
                with_payload=True,
            )
            for point in results:
                p = point.payload or {}
                rid = p.get("report_id", "")
                if rid_set and rid not in rid_set:
                    continue
                section = p.get("section_type", "")
                if section not in ("lessons_learned", "recommendations"):
                    continue
                if rid not in results_by_report:
                    results_by_report[rid] = {
                        "report_id": rid,
                        "title": p.get("title", ""),
                        "year": p.get("year"),
                        "country": p.get("country", ""),
                        "region": p.get("region", ""),
                        "thematic_category": p.get("thematic_category", ""),
                        "lessons_learned": [],
                        "recommendations": [],
                    }
                text = p.get("chunk_text", "").strip()
                if text:
                    if section == "lessons_learned":
                        results_by_report[rid]["lessons_learned"].append(text)
                    else:
                        results_by_report[rid]["recommendations"].append(text)
            if next_offset is None:
                break
            offset = next_offset
        return {"reports": list(results_by_report.values())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


DAC_SECTIONS = ["relevance", "effectiveness", "efficiency", "impact", "sustainability"]


@app.get("/api/v1/dac-evidence")
async def get_dac_evidence(
    report_ids: str = Query(default=""),
    session: dict = Depends(require_auth),
):
    """Get DAC criterion evidence passages grouped by criterion."""
    try:
        client = get_qdrant()
        rid_set = set(r.strip() for r in report_ids.split(",") if r.strip()) if report_ids else set()
        evidence: dict = {c: [] for c in DAC_SECTIONS}
        report_chunk_counts: dict = {}  # report_id -> {criterion: count}
        offset = None
        while True:
            results, next_offset = client.scroll(
                collection_name=config.QDRANT_COLLECTION,
                limit=500, offset=offset,
                with_payload=True,
            )
            for point in results:
                p = point.payload or {}
                rid = p.get("report_id", "")
                if rid_set and rid not in rid_set:
                    continue
                section = p.get("section_type", "")
                if section not in DAC_SECTIONS:
                    continue
                text = p.get("chunk_text", "").strip()
                if text:
                    evidence[section].append({
                        "report_id": rid,
                        "report_title": p.get("title", ""),
                        "year": p.get("year"),
                        "country": p.get("country", ""),
                        "text": text,
                        "page_hint": p.get("page_hint", 1),
                    })
                    # Track chunk counts per report per criterion for radar
                    if rid not in report_chunk_counts:
                        report_chunk_counts[rid] = {c: 0 for c in DAC_SECTIONS}
                    report_chunk_counts[rid][section] += 1
            if next_offset is None:
                break
            offset = next_offset
        return {
            "evidence": evidence,
            "chunk_counts": report_chunk_counts,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    return {"service": "UNIDO IEU RAG Platform", "version": "1.0.0", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    import os
    # Use 0.0.0.0 on Railway/Render (PORT env var set by platform), 127.0.0.1 locally
    host = "0.0.0.0" if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RENDER") else "127.0.0.1"
    port = int(os.getenv("PORT", config.API_PORT))
    uvicorn.run("main:app", host=host, port=port, reload=False)
