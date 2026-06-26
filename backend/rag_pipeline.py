"""
RAG query pipeline — no LLM, no API keys needed.
Returns retrieved + reranked passages directly.
Uses local sentence-transformers for everything.
"""

import time
import uuid
import logging
from typing import Optional

from sentence_transformers import SentenceTransformer, CrossEncoder
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Filter, FieldCondition, MatchAny, Range, MatchText,
    TextIndexParams, TokenizerType,
)

from config import config
from models import QueryFilters, SourceCitation

logger = logging.getLogger(__name__)

SECTION_BOOST = {
    "lessons_learned": 1.40,
    "recommendations": 1.35,
    "conclusions": 1.30,
    "findings": 1.25,
    "relevance": 1.10, "effectiveness": 1.10, "sustainability": 1.10,
    "impact": 1.10, "efficiency": 1.05, "coherence": 1.05,
    "executive_summary": 1.05, "body": 1.00,
    "background": 0.90, "methodology": 0.85, "annexes": 0.70,
}

# ─────────────────────────────────────────────────────────────────────────────
# Singleton models
# ─────────────────────────────────────────────────────────────────────────────

_embed_model: Optional[SentenceTransformer] = None
_reranker: Optional[CrossEncoder] = None
_qdrant: Optional[QdrantClient] = None


def get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        logger.info(f"Loading embedding model: {config.EMBEDDING_MODEL}...")
        _embed_model = SentenceTransformer(config.EMBEDDING_MODEL)
        logger.info("Embedding model ready.")
    return _embed_model


def get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        logger.info(f"Loading reranker: {config.RERANKER_MODEL} (~15s first load)...")
        _reranker = CrossEncoder(config.RERANKER_MODEL, max_length=512)
        logger.info("Reranker ready.")
    return _reranker


def get_qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY, timeout=60)
    return _qdrant


def create_text_index() -> None:
    """Create a full-text index on chunk_text for hybrid keyword search.
    Idempotent — safe to call on every startup."""
    try:
        get_qdrant().create_payload_index(
            collection_name=config.QDRANT_COLLECTION,
            field_name="chunk_text",
            field_schema=TextIndexParams(
                type="text",
                tokenizer=TokenizerType.WORD,
                min_token_len=3,
                max_token_len=20,
                lowercase=True,
            ),
        )
        logger.info("✅ Full-text index on chunk_text created / confirmed.")
    except Exception as e:
        logger.warning(f"Text index skipped (may already exist): {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Search
# ─────────────────────────────────────────────────────────────────────────────

def embed_query(query: str) -> list[float]:
    model = get_embed_model()
    vector = model.encode(query, normalize_embeddings=True)
    return vector.tolist()


def build_filter(filters: QueryFilters) -> Optional[Filter]:
    conditions = []
    if filters.dac_criteria:
        conditions.append(FieldCondition(key="dac_criteria", match=MatchAny(any=filters.dac_criteria)))
    if filters.sdgs:
        conditions.append(FieldCondition(key="sdgs", match=MatchAny(any=filters.sdgs)))
    if filters.thematic_categories:
        conditions.append(FieldCondition(key="thematic_category", match=MatchAny(any=filters.thematic_categories)))
    if filters.year_min is not None or filters.year_max is not None:
        conditions.append(FieldCondition(key="year", range=Range(gte=filters.year_min, lte=filters.year_max)))
    return Filter(must=conditions) if conditions else None


def _payload_to_candidate(p: dict, score: float) -> dict:
    section = p.get("section_type", "body")
    boost = SECTION_BOOST.get(section, 1.0)
    return {
        "chunk_text":       p.get("chunk_text", ""),
        "title":            p.get("title", "Unknown"),
        "year":             p.get("year"),
        "country":          p.get("country", ""),
        "thematic_category":p.get("thematic_category", ""),
        "dac_criteria":     p.get("dac_criteria", []),
        "sdgs":             p.get("sdgs", []),
        "section_type":     section,
        "is_high_value":    p.get("is_high_value", False),
        "chunk_index":      p.get("chunk_index", 0),
        "page_hint":        p.get("page_hint", 1),
        "similarity_score": score * boost,
        "raw_score":        score,
    }


def search(query: str, filters: QueryFilters) -> list[dict]:
    """Dense vector search."""
    vector = embed_query(query)
    qdrant_filter = build_filter(filters)

    results = get_qdrant().search(
        collection_name=config.QDRANT_COLLECTION,
        query_vector=vector,
        query_filter=qdrant_filter,
        limit=config.RETRIEVAL_TOP_K,
        with_payload=True,
    )
    return [_payload_to_candidate(hit.payload or {}, float(hit.score)) for hit in results]


def keyword_search(query: str, filters: QueryFilters, limit: int = 20) -> list[dict]:
    """Keyword (full-text) search using the Qdrant text index on chunk_text.
    Requires create_text_index() to have been called at least once."""
    words = [w.strip() for w in query.split() if len(w.strip()) >= 3]
    if not words:
        return []

    try:
        base_filter = build_filter(filters)
        text_conditions = [
            FieldCondition(key="chunk_text", match=MatchText(text=w))
            for w in words[:4]   # use up to 4 keywords
        ]
        must_conditions = (base_filter.must if base_filter else []) + text_conditions
        kw_filter = Filter(must=must_conditions)

        results, _ = get_qdrant().scroll(
            collection_name=config.QDRANT_COLLECTION,
            scroll_filter=kw_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [_payload_to_candidate(hit.payload or {}, 0.65) for hit in results]
    except Exception as e:
        logger.warning(f"Keyword search failed (index may not exist yet): {e}")
        return []


def rerank(query: str, candidates: list[dict]) -> list[dict]:
    if not candidates:
        return []
    reranker = get_reranker()
    pairs = [(query, c["chunk_text"]) for c in candidates]
    scores = reranker.predict(pairs, show_progress_bar=False)
    for c, s in zip(candidates, scores):
        c["reranker_score"] = float(s)
    return sorted(candidates, key=lambda x: x["reranker_score"], reverse=True)[:config.RERANK_TOP_N]


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline entry point (no LLM — returns passages only)
# ─────────────────────────────────────────────────────────────────────────────

def run_query(query: str, filters: QueryFilters) -> tuple[list[SourceCitation], dict]:
    """
    Hybrid retrieval: dense vector search + keyword (full-text) search.
    Results are merged, deduplicated, then reranked.
    No LLM. Runs entirely locally + Qdrant.
    """
    query_id = str(uuid.uuid4())
    t0 = time.time()

    # Vector search
    vector_candidates = search(query, filters)

    # Keyword search (may return empty if text index not yet created)
    keyword_candidates = keyword_search(query, filters, limit=config.RETRIEVAL_TOP_K)

    # Merge: deduplicate by first 120 chars of chunk text, prefer higher score
    seen: dict[str, dict] = {}
    for c in vector_candidates + keyword_candidates:
        key = c["chunk_text"][:120]
        if key not in seen or c["similarity_score"] > seen[key]["similarity_score"]:
            seen[key] = c
    candidates = list(seen.values())

    t_search = round((time.time() - t0) * 1000)

    t1 = time.time()
    top_passages = rerank(query, candidates)
    t_rerank = round((time.time() - t1) * 1000)

    logger.info(
        f"[{query_id[:8]}] Vector:{len(vector_candidates)} + Keyword:{len(keyword_candidates)} "
        f"→ merged:{len(candidates)} → reranked:{len(top_passages)} | "
        f"Search:{t_search}ms | Rerank:{t_rerank}ms"
    )

    citations = [
        SourceCitation(
            report_title=p["title"],
            year=p.get("year"),
            country=p.get("country"),
            chunk_text=p["chunk_text"],
            similarity_score=p["similarity_score"],
            reranker_score=p["reranker_score"],
            chunk_index=p["chunk_index"],
        )
        for p in top_passages
    ]

    metadata = {
        "query_id": query_id,
        "retrieval_count": len(candidates),
        "reranked_count": len(top_passages),
        "search_ms": t_search,
        "rerank_ms": t_rerank,
    }

    return citations, metadata


# ─────────────────────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────────────────────

def check_qdrant_health() -> dict:
    try:
        client = get_qdrant()
        collections = [c.name for c in client.get_collections().collections]
        exists = config.QDRANT_COLLECTION in collections
        count = 0
        if exists:
            info = client.get_collection(config.QDRANT_COLLECTION)
            count = info.points_count or 0
        return {"qdrant_connected": True, "collection_exists": exists, "document_count": count}
    except Exception as e:
        logger.error(f"Qdrant health check failed: {e}")
        return {"qdrant_connected": False, "collection_exists": False, "document_count": 0}


# ─────────────────────────────────────────────────────────────────────────────
# L&R retrieval: 2-stage HyDE semantic search (no LLM required)
# ─────────────────────────────────────────────────────────────────────────────

# Realistic evaluation-style texts used as semantic anchors (HyDE without LLM).
# Embedding similarity to these templates scores genuine L&R text highly and
# questionnaire / ToR / table garbage text poorly.

_LESSON_HYDE_TEMPLATES = [
    (
        "A key lesson from this evaluation is that project sustainability requires strong national "
        "ownership and capacity building from the outset of implementation. The evaluation found "
        "that embedding expertise in national institutions leads to lasting impact."
    ),
    (
        "The evaluation demonstrated that early and continuous stakeholder engagement, particularly "
        "with beneficiary communities, contributed significantly to project effectiveness and "
        "ownership. Lessons learned include the importance of participatory approaches in design."
    ),
    (
        "An important lesson learned is that integrating gender considerations and social inclusion "
        "into project design and monitoring frameworks from the start leads to more equitable "
        "outcomes. Evidence shows that projects neglecting gender dimensions achieved lower ratings."
    ),
    (
        "Experience shows that adequate financing mechanisms and cost-effectiveness analysis should "
        "be built into project design. A critical lesson is that over-reliance on a single donor "
        "creates fragility in long-term programme sustainability."
    ),
    (
        "The evaluation found that technical assistance is most effective when complemented by "
        "institutional capacity building and knowledge transfer to national counterparts. "
        "Critical success factors include strong government commitment and clear exit strategies."
    ),
]

_REC_HYDE_TEMPLATES = [
    (
        "UNIDO should strengthen the monitoring and evaluation framework to enable adaptive "
        "management throughout project implementation. A results-based management system must "
        "be established with clear indicators, baselines, and regular progress reviews."
    ),
    (
        "The project management unit must ensure adequate resources are allocated for capacity "
        "development and knowledge transfer activities. UNIDO should provide targeted technical "
        "assistance to national counterparts to build long-term institutional capabilities."
    ),
    (
        "Future projects should incorporate gender-responsive indicators from the design phase "
        "to ensure equitable participation and benefit distribution. UNIDO must mainstream "
        "gender and social inclusion across all project components and reporting mechanisms."
    ),
    (
        "UNIDO and the government counterpart should establish a clear exit strategy and "
        "sustainability plan well before project closure. It is recommended that the project "
        "develop financial sustainability mechanisms to ensure continuity after UNIDO support ends."
    ),
    (
        "The evaluation recommends that UNIDO strengthen coordination mechanisms with other "
        "UN agencies and development partners to avoid duplication and enhance synergies. "
        "UNIDO should take a more proactive role in convening multi-stakeholder platforms."
    ),
]

_LR_LESSON_KW = frozenset([
    "lesson", "learned", "learning", "experience show", "experience suggest",
    "demonstrated", "evidence show", "evaluation found", "evaluation show",
    "evaluation demonstrate", "proved to be", "key finding", "important finding",
    "critical success", "success factor", "it was found", "the evaluation",
    "contribut", "important to note", "it is important", "resulted in",
    "enabled", "allowed", "good practice",
])
_LR_REC_KW = frozenset([
    "recommend", "should ", "must ", "advised", "proposed", "suggest",
    "action needed", "need to ", "needs to ", "ought to", "it is essential",
    "it is important to", "should be", "must be", "will need",
    "it is recommended", "the project should", "unido should",
])


def _lr_keyword_score(text: str, mode: str) -> float:
    """Return 0.0–1.0 keyword density score for the given mode."""
    lower = text.lower()
    keywords = _LR_LESSON_KW if mode == "lessons" else _LR_REC_KW
    hits = sum(1 for kw in keywords if kw in lower)
    return min(hits / 3.0, 1.0)


def search_lr_semantic(
    mode: str,                           # "lessons" or "recommendations"
    report_ids: Optional[list[str]] = None,
    top_per_template: int = 15,
    top_final: int = 6,
) -> tuple[dict, dict]:
    """
    2-stage HyDE-style semantic retrieval for lessons learned / recommendations.

    Stage 1 — Multi-template dense search:
        Embed each of several realistic evaluation text templates and search
        Qdrant. This is HyDE (Hypothetical Document Embeddings) without an LLM —
        hand-crafted realistic examples replace LLM-generated hypothetical answers.
        Multiple templates improve recall across different phrasing styles.

    Stage 2 — Hybrid scoring + deduplication:
        final_score = semantic_similarity × 0.65
                    + keyword_density    × 0.25
                    + section_label_bonus× 0.10
        Best N chunks per report are returned.

    Returns:
        texts_by_report_id: {rid: [chunk_text, ...]}
        meta_by_report_id:  {rid: {title, year, country, region, thematic_category, report_id}}
    """
    embed = get_embed_model()
    client = get_qdrant()

    templates = _LESSON_HYDE_TEMPLATES if mode == "lessons" else _REC_HYDE_TEMPLATES
    target_label = "lessons_learned" if mode == "lessons" else "recommendations"

    qdrant_filter: Optional[Filter] = None
    if report_ids:
        qdrant_filter = Filter(
            must=[FieldCondition(key="report_id", match=MatchAny(any=report_ids))]
        )

    # Stage 1 — collect unique candidates (dedup by point id, keep best score)
    best_by_id: dict = {}  # point_id -> {text, report_id, section_type, sem_score, meta}

    for template in templates:
        vec = embed.encode(template, normalize_embeddings=True).tolist()
        try:
            hits = client.search(
                collection_name=config.QDRANT_COLLECTION,
                query_vector=vec,
                query_filter=qdrant_filter,
                limit=top_per_template,
                with_payload=True,
                score_threshold=0.30,
            )
        except Exception as e:
            logger.warning(f"search_lr_semantic [{mode}] template search failed: {e}")
            continue

        for hit in hits:
            pid = str(hit.id)
            p = hit.payload or {}
            if pid not in best_by_id or float(hit.score) > best_by_id[pid]["sem_score"]:
                best_by_id[pid] = {
                    "text":         p.get("chunk_text", "").strip(),
                    "report_id":    p.get("report_id", ""),
                    "section_type": p.get("section_type", "body"),
                    "sem_score":    float(hit.score),
                    "meta": {
                        "title":            p.get("title", ""),
                        "year":             p.get("year"),
                        "country":          p.get("country", ""),
                        "region":           p.get("region", ""),
                        "thematic_category": p.get("thematic_category", ""),
                    },
                }

    if not best_by_id:
        return {}, {}

    # Stage 2 — score, group by report, take top N
    report_candidates: dict = {}  # rid -> [(final_score, text)]
    report_meta: dict = {}

    for cdata in best_by_id.values():
        text = cdata["text"]
        if not text or len(text) < 80:
            continue

        sem       = cdata["sem_score"]
        kw        = _lr_keyword_score(text, mode)
        label_bon = 0.10 if cdata["section_type"] == target_label else 0.0
        final     = sem * 0.65 + kw * 0.25 + label_bon

        rid = cdata["report_id"]
        if not rid:
            continue

        report_candidates.setdefault(rid, []).append((final, text))
        if rid not in report_meta:
            report_meta[rid] = {**cdata["meta"], "report_id": rid}

    texts_by_report: dict = {}
    for rid, scored in report_candidates.items():
        scored.sort(key=lambda x: x[0], reverse=True)
        texts_by_report[rid] = [t for _, t in scored[:top_final]]

    logger.info(
        f"search_lr_semantic [{mode}]: {len(best_by_id)} candidates → "
        f"{sum(len(v) for v in texts_by_report.values())} chunks across "
        f"{len(texts_by_report)} reports"
    )
    return texts_by_report, report_meta
