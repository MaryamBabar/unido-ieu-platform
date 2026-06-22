"""
Ingestion pipeline — local embeddings, no API key needed.
Uses BAAI/bge-base-en-v1.5 via sentence-transformers (free, runs locally).
"""

import re
import uuid
import time
import logging
import math
import yaml
from pathlib import Path
from typing import Optional
from collections import Counter

import fitz  # PyMuPDF
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, PayloadSchemaType,
)

from config import config

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ─────────────────────────────────────────────────────────────────────────────
# UNIDO section detection
# ─────────────────────────────────────────────────────────────────────────────

SECTION_PATTERNS = [
    ("lessons_learned",   r"\b(lessons?\s+learned|lessons?\s+learnt|key\s+lessons?)\b"),
    ("recommendations",   r"\brecommendations?\b"),
    ("conclusions",       r"\b(conclusions?|overall\s+conclusions?)\b"),
    ("relevance",         r"\b(relevance|criterion\s+1)\b"),
    ("coherence",         r"\b(coherence)\b"),
    ("effectiveness",     r"\b(effectiveness|criterion\s+[23])\b"),
    ("efficiency",        r"\b(efficiency|criterion\s+[34])\b"),
    ("impact",            r"\b(impact|criterion\s+[45])\b"),
    ("sustainability",    r"\b(sustainability|criterion\s+[56])\b"),
    ("executive_summary", r"\b(executive\s+summary|management\s+summary)\b"),
    ("findings",          r"\b(findings?|evaluation\s+findings?|key\s+findings?)\b"),
    ("methodology",       r"\b(methodology|evaluation\s+approach)\b"),
    ("background",        r"\b(background|introduction|project\s+description)\b"),
    ("annexes",           r"\b(annex|appendix)\b"),
]

HIGH_VALUE_SECTIONS = {"lessons_learned", "recommendations", "conclusions", "findings"}
PAGE_MARKER_RE = re.compile(r"^\[PAGE \d+\]$")

# ─────────────────────────────────────────────────────────────────────────────
# Embedding model (loaded once, reused)
# ─────────────────────────────────────────────────────────────────────────────

_embed_model: Optional[SentenceTransformer] = None


def get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        logger.info(f"Loading embedding model: {config.EMBEDDING_MODEL} (first load ~30s)...")
        _embed_model = SentenceTransformer(config.EMBEDDING_MODEL)
        logger.info("Embedding model loaded.")
    return _embed_model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts locally. No API call, no cost."""
    model = get_embed_model()
    # batch_size=32 works well on CPU
    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=len(texts) > 50,
        normalize_embeddings=True,  # cosine similarity requires normalised vectors
    )
    return embeddings.tolist()


# ─────────────────────────────────────────────────────────────────────────────
# PDF extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_pdf_text(pdf_path: Path) -> tuple[str, int, int]:
    doc = fitz.open(str(pdf_path))
    pages_text = []
    for i, page in enumerate(doc):
        text = page.get_text("text", sort=True)
        if text.strip():
            pages_text.append(f"[PAGE {i+1}]\n{text}")
    doc.close()

    full_text = "\n".join(pages_text)
    words = full_text.split()
    word_count = len(words)

    if word_count > 60_000:
        logger.warning(f"  Capping at 50,000 words (was {word_count:,})")
        full_text = " ".join(words[:50_000])
        word_count = 50_000

    logger.info(f"  {len(pages_text)} pages, {word_count:,} words")
    return full_text, len(pages_text), word_count


# ─────────────────────────────────────────────────────────────────────────────
# Section-aware chunking
# ─────────────────────────────────────────────────────────────────────────────

def detect_section(text: str) -> str:
    text_lower = text.lower().strip()
    for name, pattern in SECTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return name
    return "body"


def chunk_document(full_text: str) -> list[dict]:
    lines = full_text.split("\n")
    chunk_size_chars = config.CHUNK_SIZE * 4
    overlap_chars = config.CHUNK_OVERLAP * 4

    sections = []
    current_section = "body"
    current_lines = []
    current_page = 1

    for line in lines:
        if PAGE_MARKER_RE.match(line.strip()):
            try:
                current_page = int(line.strip()[6:-1])
            except ValueError:
                pass
            continue

        stripped = line.strip()
        if stripped and len(stripped) < 100 and detect_section(stripped) != "body":
            if current_lines:
                sections.append({
                    "section_type": current_section,
                    "text": "\n".join(current_lines).strip(),
                    "start_page": current_page,
                })
            current_section = detect_section(stripped)
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append({
            "section_type": current_section,
            "text": "\n".join(current_lines).strip(),
            "start_page": current_page,
        })

    # Chunk each section
    all_chunks = []
    for section in sections:
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", section["text"]) if p.strip()]
        current = ""
        for para in paragraphs:
            if len(current) + len(para) > chunk_size_chars and current:
                all_chunks.append({
                    "text": current.strip(),
                    "section_type": section["section_type"],
                    "page_hint": section["start_page"],
                    "chunk_index": len(all_chunks),
                    "is_high_value": section["section_type"] in HIGH_VALUE_SECTIONS,
                })
                current = current[-overlap_chars:] + "\n\n" + para
            else:
                current = current + "\n\n" + para if current else para
        if current.strip():
            all_chunks.append({
                "text": current.strip(),
                "section_type": section["section_type"],
                "page_hint": section["start_page"],
                "chunk_index": len(all_chunks),
                "is_high_value": section["section_type"] in HIGH_VALUE_SECTIONS,
            })

    high_value = sum(1 for c in all_chunks if c["is_high_value"])
    logger.info(f"  {len(all_chunks)} chunks ({high_value} from high-value sections)")
    return all_chunks


# ─────────────────────────────────────────────────────────────────────────────
# Qdrant collection setup
# ─────────────────────────────────────────────────────────────────────────────

def ensure_collection(client: QdrantClient) -> None:
    existing = [c.name for c in client.get_collections().collections]
    if config.QDRANT_COLLECTION in existing:
        logger.info(f"Collection '{config.QDRANT_COLLECTION}' exists.")
        return

    logger.info(f"Creating collection '{config.QDRANT_COLLECTION}'...")
    client.create_collection(
        collection_name=config.QDRANT_COLLECTION,
        vectors_config=VectorParams(size=config.EMBEDDING_DIM, distance=Distance.COSINE),
    )
    for field, schema in [
        ("year", PayloadSchemaType.INTEGER),
        ("thematic_category", PayloadSchemaType.KEYWORD),
        ("section_type", PayloadSchemaType.KEYWORD),
        ("report_id", PayloadSchemaType.KEYWORD),
    ]:
        client.create_payload_index(
            collection_name=config.QDRANT_COLLECTION,
            field_name=field,
            field_schema=schema,
        )
    logger.info("Collection created.")


# ─────────────────────────────────────────────────────────────────────────────
# Ingest one report
# ─────────────────────────────────────────────────────────────────────────────

def ingest_report(pdf_path: Path, report_metadata: dict, qdrant_client: QdrantClient) -> dict:
    start = time.time()
    report_id = report_metadata.get("report_id") or str(uuid.uuid4())
    title = report_metadata.get("title", pdf_path.name)

    logger.info(f"\n{'='*60}\nIngesting: {title}")

    full_text, page_count, word_count = extract_pdf_text(pdf_path)
    chunks = chunk_document(full_text)

    logger.info(f"  Embedding {len(chunks)} chunks locally...")
    embeddings = embed_texts([c["text"] for c in chunks])

    points = []
    for chunk, vector in zip(chunks, embeddings):
        points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={
                "report_id": report_id,
                "title": title,
                "year": report_metadata.get("year"),
                "country": report_metadata.get("country", ""),
                "region": report_metadata.get("region", ""),
                "thematic_category": report_metadata.get("thematic_category", ""),
                "dac_criteria": report_metadata.get("dac_criteria", []),
                "sdgs": report_metadata.get("sdgs", []),
                "evaluation_type": report_metadata.get("evaluation_type", ""),
                "donor": report_metadata.get("donor", ""),
                "chunk_text": chunk["text"],
                "section_type": chunk["section_type"],
                "is_high_value": chunk["is_high_value"],
                "chunk_index": chunk["chunk_index"],
                "page_hint": chunk["page_hint"],
            },
        ))

    # Upsert in batches
    for i in range(0, len(points), 50):
        qdrant_client.upsert(collection_name=config.QDRANT_COLLECTION, points=points[i:i+50])

    elapsed = round(time.time() - start, 1)
    logger.info(f"  Done in {elapsed}s")
    return {
        "report_id": report_id, "title": title,
        "chunk_count": len(chunks), "elapsed_seconds": elapsed, "status": "success",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Batch ingest
# ─────────────────────────────────────────────────────────────────────────────

def ingest_all(pdf_dir: Path, metadata_file: Path) -> list[dict]:
    with open(metadata_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    reports = data.get("reports", [])
    qdrant_client = QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY, timeout=300)
    ensure_collection(qdrant_client)

    results = []
    for i, meta in enumerate(reports, 1):
        pdf_path = pdf_dir / meta.get("filename", "")
        if not pdf_path.exists():
            logger.error(f"[{i}/{len(reports)}] Not found: {pdf_path.name} — skipping")
            results.append({"title": meta.get("title", "?"), "status": "error", "error": "PDF not found"})
            continue
        logger.info(f"\n[{i}/{len(reports)}]")
        try:
            result = ingest_report(pdf_path, meta, qdrant_client)
            results.append(result)
        except Exception as e:
            logger.error(f"  FAILED: {e}")
            results.append({"title": meta.get("title", "?"), "status": "error", "error": str(e)})

    success = sum(1 for r in results if r.get("status") == "success")
    logger.info(f"\nDone: {success}/{len(reports)} ingested successfully.")
    return results
