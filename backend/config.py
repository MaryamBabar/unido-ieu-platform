"""
Configuration — runs with Qdrant + LangSmith only.
No OpenAI, no LLM required.
Local sentence-transformers handle all embeddings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    # ── Local Embeddings (no API key needed) ─────────────────────────────────
    # Downloads ~440MB once on first run, then cached locally
    EMBEDDING_MODEL: str = "BAAI/bge-base-en-v1.5"
    EMBEDDING_DIM: int = 768

    # ── Qdrant Cloud ──────────────────────────────────────────────────────────
    QDRANT_URL: str = os.getenv("QDRANT_URL", "")
    QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY", "")
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "unido_evaluations")

    # ── LangSmith (optional — system works without it) ────────────────────────
    LANGSMITH_API_KEY: str = os.getenv("LANGSMITH_API_KEY", "")
    LANGSMITH_PROJECT: str = os.getenv("LANGSMITH_PROJECT", "unido-ieu")
    LANGCHAIN_TRACING_V2: str = os.getenv("LANGCHAIN_TRACING_V2", "true")

    # ── RAG parameters ────────────────────────────────────────────────────────
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "400"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "80"))
    RETRIEVAL_TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", "20"))
    RERANK_TOP_N: int = int(os.getenv("RERANK_TOP_N", "6"))
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"

    # ── FastAPI ───────────────────────────────────────────────────────────────
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")

    # ── Paths ─────────────────────────────────────────────────────────────────
    PDF_DIR: Path = BASE_DIR / "data" / "pdfs"
    METADATA_FILE: Path = BASE_DIR / "data" / "metadata.yaml"

    def validate(self) -> list[str]:
        missing = []
        if not self.QDRANT_URL:
            missing.append("QDRANT_URL")
        if not self.QDRANT_API_KEY:
            missing.append("QDRANT_API_KEY")
        return missing


config = Config()
