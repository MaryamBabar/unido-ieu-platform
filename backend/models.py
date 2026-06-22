"""
Pydantic models for API request/response validation.
These are the contracts between Streamlit frontend and FastAPI backend.
"""

from pydantic import BaseModel, Field
from typing import Optional


# ── DAC Criteria ─────────────────────────────────────────────────────────────
DAC_CRITERIA = [
    "Relevance",
    "Coherence",
    "Effectiveness",
    "Efficiency",
    "Impact",
    "Sustainability",
]

# ── Thematic Categories ───────────────────────────────────────────────────────
THEMATIC_CATEGORIES = [
    "Energy Efficiency",
    "Clean / Renewable Energy",
    "Climate Action",
    "Circular Economy / Waste Management",
    "Chemicals & POPs",
    "Industrial Policy & Competitiveness",
    "Trade & Standards",
    "Agro-Industry & Food Systems",
    "Water & Environment",
    "Gender & Inclusion",
    "Digital Innovation",
]

# ── SDG list ──────────────────────────────────────────────────────────────────
SDG_LIST = [f"SDG {i}" for i in range(1, 18)]


# ─────────────────────────────────────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────────────────────────────────────

class QueryFilters(BaseModel):
    """Optional metadata filters applied before ANN search in Qdrant."""
    dac_criteria: list[str] = Field(default=[], description="DAC criteria to filter by")
    sdgs: list[int] = Field(default=[], description="SDG numbers (1-17) to filter by")
    thematic_categories: list[str] = Field(default=[], description="Thematic areas to filter by")
    year_min: Optional[int] = Field(default=None, description="Earliest publication year")
    year_max: Optional[int] = Field(default=None, description="Latest publication year")


class QueryRequest(BaseModel):
    """Body for POST /api/v1/query"""
    query: str = Field(..., min_length=5, max_length=2000, description="Natural language question")
    filters: QueryFilters = Field(default_factory=QueryFilters)
    stream: bool = Field(default=True, description="Stream the response token by token")


# ─────────────────────────────────────────────────────────────────────────────
# Response models
# ─────────────────────────────────────────────────────────────────────────────

class SourceCitation(BaseModel):
    """A single passage citation returned with the answer."""
    report_title: str
    year: Optional[int]
    country: Optional[str]
    chunk_text: str           # the actual passage text
    similarity_score: float   # Qdrant ANN score
    reranker_score: float     # cross-encoder score
    chunk_index: int          # position in document


class QueryResponse(BaseModel):
    """Body for non-streaming /api/v1/query response."""
    answer: str
    citations: list[SourceCitation]
    query_id: str             # LangSmith trace ID
    retrieval_count: int      # how many candidates Qdrant returned
    reranked_count: int       # how many passed to LLM


class HealthResponse(BaseModel):
    status: str
    qdrant_connected: bool
    collection_exists: bool
    document_count: int
    missing_credentials: list[str]


class StatsResponse(BaseModel):
    total_chunks: int
    total_documents: int
    documents_by_year: dict[str, int]
    documents_by_thematic: dict[str, int]
    documents_by_sdg: dict[str, int]
    documents_by_dac: dict[str, int]
