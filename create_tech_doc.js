/**
 * Creates UNIDO_EIP_Technical_Documentation.docx
 * Run: node create_tech_doc.js
 */

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, LevelFormat, PageBreak
} = require('docx');
const fs = require('fs');
const path = require('path');

// ── Colours ──────────────────────────────────────────────────────────────────
const BLUE       = "009EDB";   // UNIDO blue
const DARK_BLUE  = "005A8E";
const DARK_TEXT  = "1A1A2E";
const MID_GREY   = "6B7280";
const LIGHT_BLUE_BG = "E8F4FB";
const HEADER_BG  = "009EDB";
const ALT_ROW    = "F0F8FD";

// ── Helpers ───────────────────────────────────────────────────────────────────
const border = { style: BorderStyle.SINGLE, size: 1, color: "D1D5DB" };
const borders = { top: border, bottom: border, left: border, right: border };
const noBorder = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const noBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder };

function heading1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 400, after: 160 },
    children: [new TextRun({ text, font: "Arial", size: 32, bold: true, color: DARK_BLUE })],
  });
}

function heading2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 120 },
    children: [new TextRun({ text, font: "Arial", size: 26, bold: true, color: BLUE })],
  });
}

function heading3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 200, after: 80 },
    children: [new TextRun({ text, font: "Arial", size: 22, bold: true, color: DARK_TEXT })],
  });
}

function body(text, opts = {}) {
  return new Paragraph({
    spacing: { before: 60, after: 100 },
    children: [new TextRun({ text, font: "Arial", size: 22, color: DARK_TEXT, ...opts })],
  });
}

function bullet(text, indent = 720) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { before: 40, after: 60 },
    indent: { left: indent, hanging: 360 },
    children: [new TextRun({ text, font: "Arial", size: 22, color: DARK_TEXT })],
  });
}

function pageBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}

function spacer() {
  return new Paragraph({ spacing: { before: 80, after: 80 }, children: [new TextRun("  ")] });
}

function blueBox(lines) {
  const rows = lines.map((line, i) =>
    new TableRow({
      children: [new TableCell({
        borders: noBorders,
        shading: { fill: LIGHT_BLUE_BG, type: ShadingType.CLEAR },
        margins: { top: i === 0 ? 140 : 40, bottom: i === lines.length - 1 ? 140 : 40, left: 200, right: 200 },
        children: [new Paragraph({
          children: [new TextRun({ text: line, font: "Courier New", size: 18, color: "005A8E" })],
        })],
      })],
    })
  );
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [9360],
    rows,
  });
}

function headerRow(cells, widths) {
  return new TableRow({
    tableHeader: true,
    children: cells.map((text, i) => new TableCell({
      borders,
      width: { size: widths[i], type: WidthType.DXA },
      shading: { fill: HEADER_BG, type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      verticalAlign: VerticalAlign.CENTER,
      children: [new Paragraph({
        alignment: AlignmentType.LEFT,
        children: [new TextRun({ text, font: "Arial", size: 20, bold: true, color: "FFFFFF" })],
      })],
    })),
  });
}

function dataRow(cells, widths, shade = false) {
  return new TableRow({
    children: cells.map((text, i) => new TableCell({
      borders,
      width: { size: widths[i], type: WidthType.DXA },
      shading: { fill: shade ? ALT_ROW : "FFFFFF", type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      children: [new Paragraph({
        children: [new TextRun({ text: String(text), font: "Arial", size: 20, color: DARK_TEXT })],
      })],
    })),
  });
}

// ── Cover Page ────────────────────────────────────────────────────────────────
function makeCoverPage() {
  const metaWidths = [2800, 6560];
  const metaRows = [
    ["Platform", "UNIDO Evaluation Intelligence Platform (EIP)"],
    ["Version", "1.0"],
    ["Date", "July 2026"],
    ["Classification", "Internal — Independent Evaluation Unit"],
    ["Audience", "IEU Evaluation Analysts & Technical Staff"],
    ["Backend", "FastAPI + Qdrant Cloud + Sentence-Transformers"],
    ["Frontend", "Streamlit"],
    ["AI Model", "Claude claude-sonnet-4-20250514 (Anthropic)"],
    ["Embedding Model", "BAAI/bge-base-en-v1.5 (local, 768-dim)"],
    ["Reranker Model", "BAAI/bge-reranker-v2-m3 (local cross-encoder)"],
  ];
  return [
    new Paragraph({ spacing: { before: 1200, after: 200 }, children: [new TextRun({ text: "UNIDO", font: "Arial", size: 80, bold: true, color: BLUE })] }),
    new Paragraph({ spacing: { before: 0, after: 80 }, children: [new TextRun({ text: "Evaluation Intelligence Platform", font: "Arial", size: 44, color: DARK_TEXT })] }),
    new Paragraph({ spacing: { before: 0, after: 600 }, children: [new TextRun({ text: "Technical Documentation", font: "Arial", size: 36, color: MID_GREY })] }),
    new Paragraph({ spacing: { before: 0, after: 40 }, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: BLUE, space: 1 } }, children: [new TextRun("  ")] }),
    spacer(),
    new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: metaWidths,
      rows: metaRows.map(([label, value], i) => dataRow([label, value], metaWidths, i % 2 === 0)),
    }),
    pageBreak(),
  ];
}

// ── Section 1: Executive Summary ──────────────────────────────────────────────
function makeExecutiveSummary() {
  return [
    heading1("1. Executive Summary"),
    body("The UNIDO Evaluation Intelligence Platform (EIP) is a retrieval-augmented search and synthesis system built for the Independent Evaluation Unit (IEU). It ingests all 56 terminal evaluation reports spanning 2021–2025 and makes them fully searchable, synthesisable, and analytically queryable in natural language."),
    spacer(),
    body("The platform addresses a critical operational gap: evaluation analysts previously had to manually read dozens of reports to identify cross-cutting lessons, recurring failure patterns, or evidence on specific themes. The EIP reduces this from days of work to seconds."),
    spacer(),
    heading2("Core Capabilities"),
    bullet("Search & Browse — filter the full portfolio by thematic area, region, SDG, year, and evaluation rating; structured detail view per report"),
    bullet("Cross-Report Synthesis — select any subset of reports and ask natural language questions; the system retrieves relevant passages across all selected reports simultaneously and synthesises an answer using Claude"),
    bullet("OECD-DAC Criteria Browser — evidence from reports organised by Relevance, Effectiveness, Efficiency, Impact, Sustainability, and Coherence"),
    bullet("Portfolio Analytics — live charts showing distribution by theme, region, SDG coverage, and evaluation rating"),
    bullet("AI Content Extraction — executive summaries, lessons learned, recommendations, and SDG mapping with justifications, extracted by Gemini 2.0 Flash"),
    spacer(),
    heading2("Key Technical Choices"),
    bullet("Local embeddings (no API cost) — BAAI/bge-base-en-v1.5 runs on laptop CPU"),
    bullet("Hybrid retrieval — dense semantic vectors + keyword BM25 search merged before reranking"),
    bullet("Cross-encoder reranker — reads query + passage together for precise relevance scoring"),
    bullet("Section-aware indexing — lessons/recommendations chunks scored higher than background text"),
    bullet("Zero cloud infrastructure — runs entirely on a local machine; shareable via ngrok"),
    pageBreak(),
  ];
}

// ── Section 2: Architecture ───────────────────────────────────────────────────
function makeArchitecture() {
  const compWidths = [2400, 3500, 3460];
  return [
    heading1("2. System Architecture"),
    body("The platform follows a two-tier architecture: a FastAPI backend handling retrieval, synthesis, and data management, and a Streamlit frontend providing the analyst-facing interface. All AI inference runs locally (embeddings, reranking) or via managed API (Claude for synthesis, Gemini for extraction)."),
    spacer(),
    heading2("Component Overview"),
    new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: compWidths,
      rows: [
        headerRow(["Component", "Technology", "Purpose"], compWidths),
        dataRow(["Frontend", "Streamlit (Python)", "Analyst UI — Search, Synthesis, DAC, Visualise tabs"], compWidths, false),
        dataRow(["Backend API", "FastAPI + Uvicorn", "REST endpoints for search, synthesis, ingestion"], compWidths, true),
        dataRow(["Vector DB", "Qdrant Cloud", "Stores ~18,000 text chunk embeddings (768-dim)"], compWidths, false),
        dataRow(["Embedding Model", "BAAI/bge-base-en-v1.5", "Local sentence transformer — no API cost"], compWidths, true),
        dataRow(["Reranker", "BAAI/bge-reranker-v2-m3", "Cross-encoder reranker for precision scoring"], compWidths, false),
        dataRow(["LLM — Synthesis", "Anthropic Claude claude-sonnet-4-20250514", "Cross-report synthesis and analytical Q&A"], compWidths, true),
        dataRow(["LLM — Extraction", "Gemini 2.0 Flash", "AI extraction of summaries, lessons, SDG mapping"], compWidths, false),
        dataRow(["Observability", "LangSmith", "Query tracing and retrieval monitoring"], compWidths, true),
      ],
    }),
    spacer(),
    heading2("Data Flow"),
    body("1. Analyst submits a natural language question in the Synthesis tab"),
    body("2. Backend expands the query with domain vocabulary (evaluation terminology)"),
    body("3. Expanded query is embedded using BAAI/bge-base-en-v1.5 (local)"),
    body("4. Qdrant performs hybrid search: dense vector similarity + keyword (BM25-style)"),
    body("5. Top-30 candidates are merged, deduplicated, and section-boosted"),
    body("6. BAAI/bge-reranker-v2-m3 cross-encoder reranks to top-10 passages"),
    body("7. Top-10 passages are sent as context to Claude claude-sonnet-4-20250514"),
    body("8. Claude synthesises a response, streamed token-by-token to the frontend"),
    pageBreak(),
  ];
}

// ── Section 3: Retrieval Pipeline ─────────────────────────────────────────────
function makeRetrievalPipeline() {
  const paramWidths = [2800, 2200, 2000, 2360];
  const boostWidths = [3000, 2000, 4360];
  const expWidths = [2800, 6560];
  return [
    heading1("3. Retrieval Pipeline"),
    body("The retrieval pipeline is the technical core of the platform. It implements a six-stage process designed to maximise recall (finding all relevant content) and precision (ranking the most relevant content highest)."),
    spacer(),

    heading2("3.1 Chunking"),
    body("PDFs are split into overlapping text chunks before ingestion. Each chunk receives a section label (lessons_learned, recommendations, conclusions, body, annexes) determined by proximity to section headers."),
    spacer(),
    new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: paramWidths,
      rows: [
        headerRow(["Parameter", "Value", "Previous Value", "Rationale"], paramWidths),
        dataRow(["CHUNK_SIZE", "600 tokens", "400 tokens", "More context per passage; captures full lesson statements"], paramWidths, false),
        dataRow(["CHUNK_OVERLAP", "150 tokens", "80 tokens", "Prevents key content falling at chunk boundaries"], paramWidths, true),
        dataRow(["RETRIEVAL_TOP_K", "30 candidates", "20 candidates", "Higher recall before reranking filter"], paramWidths, false),
        dataRow(["RERANK_TOP_N", "10 passages", "6 passages", "Broader context for Claude synthesis"], paramWidths, true),
      ],
    }),
    spacer(),

    heading2("3.2 Embedding"),
    body("Text chunks are encoded using BAAI/bge-base-en-v1.5, a 768-dimensional sentence transformer model that runs entirely on the local CPU. The model is downloaded once (~440MB) and cached locally — no API calls or costs are incurred for embedding."),
    spacer(),
    body("All vectors are L2-normalised before storage, enabling cosine similarity search in Qdrant."),
    spacer(),

    heading2("3.3 Hybrid Search"),
    body("Every query triggers two parallel searches in Qdrant:"),
    bullet("Dense search — semantic similarity between query embedding and chunk embeddings (captures conceptual meaning even with different wording)"),
    bullet("Keyword search — BM25-style word matching via Qdrant's full-text index on chunk_text (captures exact terminology matches)"),
    spacer(),
    body("Results from both searches are merged and deduplicated. A candidate that appears in both dense and keyword results receives a combined score boost."),
    spacer(),

    heading2("3.4 Section Boosting"),
    body("After merging, each candidate's retrieval score is multiplied by a section-specific boost factor:"),
    spacer(),
    new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: boostWidths,
      rows: [
        headerRow(["Section Label", "Boost Factor", "Rationale"], boostWidths),
        dataRow(["lessons_learned", "×1.40", "Highest priority — generalizable findings most sought by analysts"], boostWidths, false),
        dataRow(["recommendations", "×1.35", "Actionable outputs — high value for evidence synthesis"], boostWidths, true),
        dataRow(["conclusions", "×1.30", "Evaluative judgements on project performance"], boostWidths, false),
        dataRow(["body (general text)", "×1.00", "Baseline — project descriptions and background"], boostWidths, true),
        dataRow(["annexes", "×0.70", "Supporting data — lower priority for synthesis queries"], boostWidths, false),
      ],
    }),
    spacer(),

    heading2("3.5 Query Expansion"),
    body("Before embedding, queries are expanded with domain-specific vocabulary using a trigger-word map. If a query contains a trigger term, additional semantically related terms are appended to the query string. This improves recall for evaluation terminology that may appear differently in report text."),
    spacer(),
    new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: expWidths,
      rows: [
        headerRow(["Trigger Term", "Expansion Added"], expWidths),
        dataRow(["lessons", "lessons learned key findings evaluation evidence"], expWidths, false),
        dataRow(["sustainability", "sustainability long-term impact ownership exit strategy financial"], expWidths, true),
        dataRow(["gender", "gender equality women inclusion social equity"], expWidths, false),
        dataRow(["clean energy", "clean energy renewable solar wind geothermal biomass electrification"], expWidths, true),
        dataRow(["climate", "climate change mitigation adaptation GHG emissions reduction carbon"], expWidths, false),
        dataRow(["chemicals", "chemicals POPs PCB hazardous waste stockholm convention"], expWidths, true),
        dataRow(["industrial", "industrial policy competitiveness manufacturing value chain SME"], expWidths, false),
      ],
    }),
    spacer(),

    heading2("3.6 Cross-Encoder Reranking"),
    body("The final reranking step uses BAAI/bge-reranker-v2-m3, a cross-encoder model that reads the query and each candidate passage together (rather than separately) to produce a precise relevance score. This is computationally more expensive than vector similarity but dramatically improves precision."),
    spacer(),
    body("The top-30 candidates from hybrid search are reranked; the top-10 are passed to Claude as context. The first query in a session takes ~15 seconds to load the reranker model; subsequent queries are fast."),
    spacer(),

    heading2("3.7 HyDE (Hypothetical Document Embeddings)"),
    body("For lessons learned and recommendations queries, the system also embeds pre-written evaluation-style template sentences (e.g., 'A key lesson from this evaluation is that...') and uses them as additional search vectors. This anchors the embedding space toward the style and vocabulary of actual evaluation findings, improving retrieval of relevant content."),
    pageBreak(),
  ];
}

// ── Section 4: Data Pipeline ──────────────────────────────────────────────────
function makeDataPipeline() {
  return [
    heading1("4. Data Pipeline"),
    heading2("4.1 PDF Ingestion"),
    body("PDFs are ingested via scripts/ingest.py. The script:"),
    bullet("Reads all reports listed in data/metadata.yaml"),
    bullet("Extracts text from each PDF using pdfplumber"),
    bullet("Detects section boundaries (Lessons Learned, Recommendations, Conclusions, Annexes)"),
    bullet("Splits text into overlapping chunks of 600 tokens with 150-token overlap"),
    bullet("Assigns section labels to each chunk based on proximity to section headers"),
    bullet("Embeds each chunk using BAAI/bge-base-en-v1.5"),
    bullet("Upserts vectors into Qdrant with payload metadata (report_id, section, page_num, report_title, year, country, thematic_area)"),
    spacer(),
    body("Total corpus: 56 reports → approximately 18,000 chunks in Qdrant."),
    spacer(),

    heading2("4.2 AI Extraction (Gemini 2.0 Flash)"),
    body("For each report, a one-time AI extraction step produces structured JSON containing:"),
    bullet("executive_summary — 200–300 word synthesis written by the model"),
    bullet("lessons_learned — list of generalizable principles (not project-specific observations)"),
    bullet("recommendations — list of actionable items with clear actor and action"),
    bullet("sdg_mapping — dictionary mapping SDG numbers to one-sentence justifications"),
    bullet("primary_thematic_area / secondary_thematic_area — inferred from project content"),
    bullet("thematic_justification — one sentence citing the specific activities that justify classification"),
    bullet("context — title, year, country, region, report type, evaluation rating, donor, budget"),
    spacer(),
    body("Extracted JSON is saved to data/ai_extractions/<report_id>.json. The frontend loads this at runtime to populate the report detail modal tabs."),
    spacer(),

    heading2("4.3 Metadata"),
    body("data/metadata.yaml contains baseline metadata for all 56 reports: report_id, title, filename (path to PDF), year, country, region, donor, and report_type. This file is the single source of truth for the report list."),
    pageBreak(),
  ];
}

// ── Section 5: Frontend Tabs ──────────────────────────────────────────────────
function makeFrontend() {
  const tabWidths = [2200, 3000, 4160];
  return [
    heading1("5. Frontend Interface"),
    body("The frontend is built with Streamlit (Python) and opens at http://localhost:8501 when the app is running. It requires no separate installation — all dependencies are listed in requirements.txt."),
    spacer(),
    new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: tabWidths,
      rows: [
        headerRow(["Tab", "Primary Feature", "Description"], tabWidths),
        dataRow(["🔍 Search", "Portfolio browser", "Filter by thematic area, region, SDG, year, rating; view structured report detail modal"], tabWidths, false),
        dataRow(["💬 Synthesis", "Cross-report Q&A", "Select reports, ask natural language questions, receive synthesised answers from Claude"], tabWidths, true),
        dataRow(["⚖️ OECD-DAC", "DAC criteria browser", "Retrieved passages organised by Relevance, Effectiveness, Efficiency, Impact, Sustainability, Coherence"], tabWidths, false),
        dataRow(["📊 Visualise", "Portfolio analytics", "Static charts: thematic distribution, SDG coverage, rating distribution, regional breakdown"], tabWidths, true),
        dataRow(["⚙️ Admin", "Ingestion status", "View ingestion logs, chunk counts, Qdrant connection status"], tabWidths, false),
      ],
    }),
    spacer(),

    heading2("Report Detail Modal"),
    body("Clicking 'View Details' on any report opens a 5-tab modal:"),
    bullet("Overview — AI-generated executive summary (with 'AI GENERATED' badge), thematic classification and justification, metadata"),
    bullet("Lessons Learned — numbered cards showing AI-extracted generalizable lessons"),
    bullet("Recommendations — numbered cards showing AI-extracted actionable recommendations with actors"),
    bullet("SDG Mapping — per-SDG cards showing which SDGs apply and why, with evidence from the report"),
    bullet("Context — raw metadata: year, country, region, donor, budget, project ID, evaluation rating"),
    pageBreak(),
  ];
}

// ── Section 6: Performance ────────────────────────────────────────────────────
function makePerformance() {
  const perfWidths = [3500, 2430, 3430];
  return [
    heading1("6. Performance Characteristics"),
    new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: perfWidths,
      rows: [
        headerRow(["Operation", "Typical Time", "Notes"], perfWidths),
        dataRow(["First synthesis query (session start)", "~15–20 seconds", "Reranker model loads into RAM on first query only"], perfWidths, false),
        dataRow(["Subsequent synthesis queries", "3–8 seconds", "Embedding + Qdrant search + Claude response"], perfWidths, true),
        dataRow(["PDF ingestion (single report)", "2–3 minutes", "Text extraction, chunking, embedding, Qdrant upsert"], perfWidths, false),
        dataRow(["Full corpus ingestion (56 reports)", "~2 hours", "Run once; subsequent re-ingestion takes same time"], perfWidths, true),
        dataRow(["AI extraction (single report)", "~15 seconds", "Gemini 2.0 Flash API call; rate limit: 5s between calls"], perfWidths, false),
        dataRow(["AI extraction (56 reports)", "~20 minutes", "Sequential with 5s delay between each report"], perfWidths, true),
        dataRow(["Frontend load time", "< 2 seconds", "Qdrant stats fetched on sidebar render"], perfWidths, false),
        dataRow(["Filter/search update", "< 1 second", "Metadata filter in Qdrant, no re-embedding needed"], perfWidths, true),
      ],
    }),
    spacer(),
    body("All embedding and reranking runs on CPU. A machine with 16GB RAM is sufficient. GPU is not required but would approximately halve embedding time during ingestion."),
    pageBreak(),
  ];
}

// ── Section 7: Running the Platform ──────────────────────────────────────────
function makeRunning() {
  return [
    heading1("7. Running the Platform"),
    heading2("7.1 First-Time Setup"),
    blueBox([
      "cd eio-rag",
      "python -m venv venv",
      "source venv/bin/activate   # Windows: venv\\Scripts\\activate",
      "pip install -r requirements.txt",
      "",
      "# Copy and fill in your credentials",
      "cp .env.example .env",
      "# Edit .env — add ANTHROPIC_API_KEY, QDRANT_URL, QDRANT_API_KEY",
    ]),
    spacer(),

    heading2("7.2 Ingest Reports"),
    blueBox([
      "# Run once to index all 56 PDFs into Qdrant",
      "python scripts/ingest.py",
      "",
      "# To rebuild the index from scratch (after chunk size changes):",
      "python scripts/ingest.py --clean",
    ]),
    spacer(),

    heading2("7.3 Run AI Extraction (optional)"),
    blueBox([
      "# Requires GEMINI_API_KEY in .env",
      "python scripts/ai_extract_gemini.py --skip-existing",
      "",
      "# Extract a single report:",
      "python scripts/ai_extract_gemini.py --only UNIDO-100260",
    ]),
    spacer(),

    heading2("7.4 Start Backend and Frontend"),
    blueBox([
      "# Terminal 1 — start the FastAPI backend",
      "cd eio-rag",
      "source venv/bin/activate",
      "python backend/main.py",
      "# Backend runs at http://localhost:8000",
      "",
      "# Terminal 2 — start the Streamlit frontend",
      "cd eio-rag",
      "source venv/bin/activate",
      "streamlit run frontend/app.py",
      "# Frontend opens at http://localhost:8501",
    ]),
    spacer(),

    heading2("7.5 Share with the Team via ngrok"),
    blueBox([
      "# Install ngrok (free) at https://ngrok.com",
      "ngrok http 8501",
      "# Share the generated URL (e.g. https://abc123.ngrok.io) with team members",
    ]),
    spacer(),

    heading2("7.6 Environment Variables (.env)"),
    blueBox([
      "ANTHROPIC_API_KEY=sk-ant-...        # Required: Claude synthesis",
      "QDRANT_URL=https://...qdrant.io     # Required: Qdrant Cloud cluster URL",
      "QDRANT_API_KEY=...                  # Required: Qdrant API key",
      "QDRANT_COLLECTION=unido_evaluations # Optional: defaults to unido_evaluations",
      "GEMINI_API_KEY=AIza...              # Optional: AI extraction only",
      "LANGSMITH_API_KEY=ls__...           # Optional: query tracing",
    ]),
    pageBreak(),
  ];
}

// ── Section 8: Future Enhancements ────────────────────────────────────────────
function makeFuture() {
  return [
    heading1("8. Planned Enhancements"),
    heading2("Near-Term"),
    bullet("Multilingual support — swap embedding model to paraphrase-multilingual-mpnet-base-v2 for Arabic and French reports"),
    bullet("Re-ingest with new chunk parameters — rebuild Qdrant index with 600-token chunks and 150-token overlap for improved retrieval quality"),
    bullet("Complete AI extraction — run Gemini extraction on all 56 reports; requires resolving API quota issue on organisational Google accounts"),
    bullet("Report upload UI — Admin tab drag-and-drop for adding new PDFs without command line"),
    spacer(),
    heading2("Medium-Term"),
    bullet("Citation export — download synthesis responses as formatted Word documents with full citations"),
    bullet("Evaluation calendar — track when evaluations are due, upcoming reports, portfolio gaps"),
    bullet("Comparative rating analysis — interactive heatmap of rating trends by country, theme, and donor"),
    bullet("Feedback loop — thumbs up/down on synthesis results to fine-tune retrieval ranking"),
    spacer(),
    heading2("Long-Term"),
    bullet("Automated ingestion — watch a folder for new PDFs and auto-ingest them"),
    bullet("Portfolio gap analysis — AI identifies which themes, regions, or SDGs are under-evaluated"),
    bullet("Evaluation quality scoring — automated OECD-DAC criteria coverage scoring per report"),
  ];
}

// ── Build Document ─────────────────────────────────────────────────────────────
const doc = new Document({
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0,
        format: LevelFormat.BULLET,
        text: "•",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } },
      }],
    }],
  },
  styles: {
    default: {
      document: { run: { font: "Arial", size: 22 } },
    },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: DARK_BLUE },
        paragraph: { spacing: { before: 400, after: 160 }, outlineLevel: 0 },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: BLUE },
        paragraph: { spacing: { before: 280, after: 120 }, outlineLevel: 1 },
      },
      {
        id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, font: "Arial", color: DARK_TEXT },
        paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 2 },
      },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: BLUE, space: 1 } },
          alignment: AlignmentType.RIGHT,
          children: [
            new TextRun({ text: "UNIDO Evaluation Intelligence Platform  |  Technical Documentation  |  July 2026", font: "Arial", size: 16, color: MID_GREY }),
          ],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          border: { top: { style: BorderStyle.SINGLE, size: 2, color: "D1D5DB", space: 1 } },
          children: [
            new TextRun({ text: "Independent Evaluation Unit — UNIDO     ", font: "Arial", size: 16, color: MID_GREY }),
            new TextRun({ text: "Page ", font: "Arial", size: 16, color: MID_GREY }),
            new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 16, color: MID_GREY }),
          ],
        })],
      }),
    },
    children: [
      ...makeCoverPage(),
      ...makeExecutiveSummary(),
      ...makeArchitecture(),
      ...makeRetrievalPipeline(),
      ...makeDataPipeline(),
      ...makeFrontend(),
      ...makePerformance(),
      ...makeRunning(),
      ...makeFuture(),
    ],
  }],
});

const outPath = path.join(__dirname, "UNIDO_EIP_Technical_Documentation.docx");
Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync(outPath, buffer);
  console.log("✅ Written to: " + outPath);
}).catch(err => {
  console.error("❌ Error:", err.message);
  process.exit(1);
});
