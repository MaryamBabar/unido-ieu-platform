# UNIDO Evaluation Intelligence Platform — Demo Script
### Technical Demo | Independent Evaluation Unit | July 2026

---

## Before the Demo (5 minutes before)
- Start backend: `cd eio-rag && python backend/main.py`
- Open frontend: `streamlit run frontend/app.py`
- Open a second browser tab with the app ready on the Synthesis tab
- Confirm Qdrant is connected (green dot in sidebar)

---

## Opening (1 minute)
> "This is the UNIDO Evaluation Intelligence Platform — a retrieval system built specifically for the Independent Evaluation Unit. It ingests all 56 terminal evaluation reports from 2021 to 2025 and makes them fully searchable, filterable, and queryable in natural language. Let me show you how it works."

---

## Part 1 — Search & Browse (3 minutes)

### Demo step 1.1 — Show the full portfolio
- Click **Search** tab
- Point out: 56 reports visible, newest first
- Show: year badges, thematic area tags, rating badges (colour-coded)

> "Every report is automatically classified by thematic area, region, SDG coverage, and evaluation rating — all extracted from the PDF text."

### Demo step 1.2 — Filter by thematic area
- In the left sidebar, expand **Thematic Area**
- Select: **Clean / Renewable Energy**
- Watch the list filter instantly

> "The system has pre-classified all reports across 11 UNIDO thematic areas. Right now we can see all clean energy evaluations across Africa, Asia, and Latin America."

### Demo step 1.3 — Add a second filter
- Also select **Africa** under Region
- Point to the filtered list of ~8 reports

> "Now we can see only clean energy projects in Africa — across countries like Nigeria, Madagascar, South Africa, Kenya, Mozambique."

### Demo step 1.4 — Open a report detail
- Click **View Details ↗** on the Nigeria Mini-Grid report (UNIDO-100260)
- Show the 5 tabs: Overview, Lessons Learned, Recommendations, SDG Mapping, Context

> "Every report has a structured detail view with AI-extracted content: executive summary, lessons learned, recommendations, and SDG mapping with justifications."

---

## Part 2 — Cross-Report Synthesis (5 minutes) ← THE MAIN EVENT

> "This is the core capability. Analysts can select multiple reports and ask questions — the system retrieves relevant passages across all of them and synthesises an answer."

### Demo step 2.1 — Select reports for synthesis
- Click **Synthesis** tab
- In the left panel, select ALL reports (click Select All)
- Point out: "56 reports selected"

### Demo step 2.2 — First query: Sustainability
Type exactly:
```
What are the main lessons learned about project sustainability across energy projects?
```
- Wait for results
- Point to: how passages come from multiple reports, each cited by title

> "The system retrieves passages from across all 56 reports simultaneously using a hybrid search — dense semantic vectors plus keyword matching — then reranks the results with a cross-encoder model for precision."

### Demo step 2.3 — Second query: Gender
Type exactly:
```
How have gender considerations been addressed in clean energy and industrial projects?
```
- Point to the cross-report evidence

> "Notice the system can answer questions about cross-cutting themes that aren't tagged in the metadata — it finds the relevant text within the PDF content itself."

### Demo step 2.4 — Third query: Specific failure pattern
Type exactly:
```
What were the main reasons for unsatisfactory project ratings?
```
- This should surface evidence from the rated reports

> "This kind of question would normally require an analyst to read all 56 reports manually. The system surfaces the relevant evidence in seconds."

### Demo step 2.5 — Fourth query: Country-specific
Type exactly:
```
What lessons apply to energy access projects in Sub-Saharan Africa?
```

---

## Part 3 — OECD-DAC Criteria Browser (2 minutes)

- Click **OECD-DAC** tab
- Select 3-4 reports
- Click **Relevance** criterion

> "The system also organises retrieved passages by OECD-DAC evaluation criteria — Relevance, Effectiveness, Efficiency, Impact, Sustainability, Coherence. This maps directly to how evaluation analysts structure their work."

- Show the radar chart
> "This radar chart visualises the evidence coverage for each DAC criterion across the selected reports."

---

## Part 4 — Portfolio Analytics (1 minute)

- Click **Visualise** tab
- Show the charts: thematic distribution, SDG coverage, ratings by year, regional breakdown

> "The platform also gives a live portfolio view — how our evaluation portfolio is distributed across themes, regions, SDGs, and quality ratings."

---

## Technical Architecture (if asked)

**Retrieval pipeline:**
1. PDF ingestion → section-aware chunking (600 tokens, 150 overlap)
2. Embedding: `BAAI/bge-base-en-v1.5` (768-dim, runs locally — no API cost)
3. Storage: Qdrant Cloud vector database
4. Query: Hybrid dense + keyword search (top-30 candidates)
5. Reranking: `BAAI/bge-reranker-v2-m3` cross-encoder (top-10 results)
6. Section boosting: lessons_learned ×1.40, recommendations ×1.35
7. Query expansion: domain vocabulary expansion for evaluation terminology

**What makes this different from a simple keyword search:**
- Semantic search finds conceptually similar content even with different wording
- Cross-encoder reranker reads query + passage together for precise relevance scoring
- Section labels ensure lessons/recommendations score higher than background text
- HyDE-style retrieval uses realistic evaluation templates to anchor the embedding space

---

## Anticipated Questions

**Q: How accurate is the thematic classification?**
> "It uses a combination of keyword patterns and semantic similarity against each thematic area. We validated it on the 4 pilot reports — we can extend validation to the full 56."

**Q: Can it handle Arabic or French reports?**
> "The current embedding model is English-only. Multi-language support would require a multilingual model like `paraphrase-multilingual-mpnet-base-v2` — a straightforward swap."

**Q: How long does ingestion take?**
> "About 2-3 minutes per PDF on a laptop CPU. The 56-report corpus takes roughly 2 hours to ingest once. After that, search is instant."

**Q: Is the data secure?**
> "All PDFs stay on the local machine. Only the text embeddings (numerical vectors) are sent to Qdrant Cloud — no raw text leaves the machine."

**Q: Can we add more reports?**
> "Yes — add the PDF to `data/pdfs/` and one entry to `data/metadata.yaml`, then run `python scripts/ingest.py`. It appears in the platform immediately."

---

## If Something Goes Wrong

| Problem | Fix |
|---|---|
| Backend not responding | `cd eio-rag && python backend/main.py` |
| No results in search | Check Qdrant connection — may need to re-ingest |
| Slow reranker | First query loads the model (~15s), subsequent queries are fast |
| Reports not showing | Click Refresh button top-right of Search tab |

---

*Prepared for the UNIDO IEU Technical Demo — July 2026*
