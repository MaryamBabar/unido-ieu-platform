"""
Extract structured sections from UNIDO evaluation PDFs using PyMuPDF heading detection.

Sections extracted: Findings, Results, Lessons Learned, Conclusions, Recommendations

Usage:
    cd eio-rag
    python scripts/extract_sections.py              # process all PDFs
    python scripts/extract_sections.py --report NGA # process one report by report_id

Output: data/extracted_sections/<report_id>.json
"""

import sys
import re
import json
import yaml
from pathlib import Path

import fitz  # PyMuPDF

# ─────────────────────────── CONFIG ─────────────────────────────────────────

PDF_DIR   = Path(__file__).parent.parent / "data" / "pdfs"
META_FILE = Path(__file__).parent.parent / "data" / "metadata.yaml"
OUT_DIR   = Path(__file__).parent.parent / "data" / "extracted_sections"

# Minimum page to start looking (skip executive summary boilerplate)
SKIP_FIRST_N_PAGES = 8

# Max chars per section (trim very long sections for storage)
MAX_SECTION_CHARS = 12_000

# ─────────────────────────── SECTION PATTERNS ───────────────────────────────

# These patterns match candidate section headings (applied to a single line of text)
# Order matters: more specific patterns first
_SECTION_DEFS = [
    # (section_key, compiled regex)
    ("lessons_learned",    re.compile(r'\b(key\s+)?lessons?\s*(learned?|learnt|pratiques?)?\b', re.I)),
    ("findings",           re.compile(r'\b(key\s+)?(eval[a-z]*\s+)?findings?\b', re.I)),
    ("conclusions",        re.compile(r'\bconclusions?\b', re.I)),
    ("recommendations",    re.compile(r'\brecommendations?\b', re.I)),
    ("results",            re.compile(r'\b(project\s+|key\s+)?(achievem[a-z]*\s+of\s+)?results?\b', re.I)),
]

# Heading-level keywords that signal a NEW top-level section (used to stop extraction)
_ANY_SECTION_RE = re.compile(
    r'\b(findings?|conclusions?|lessons?\s+(learned?|learnt)|recommendations?|'
    r'annexe?s?|references?|bibliography|introduction|background|methodology|'
    r'executive\s+summary)\b',
    re.I,
)

# Noise to exclude (these would give false positive headings)
_EXCLUDE_RE = re.compile(
    r'(results\s+framework|results[\-\s]based|monitoring|evaluation\s+criteria|'
    r'performance\s+indicators|log\s*frame|management\s+response|'
    r'annexe?\s+\d|annex\s+[ivxlcdm]+|table\s+of\s+contents)',
    re.I,
)


# ─────────────────────────── EXTRACTION ─────────────────────────────────────

def _get_body_size(doc: fitz.Document) -> float:
    """Estimate the body text font size (most-common non-tiny size)."""
    size_counts: dict[float, int] = {}
    for pno in range(min(10, len(doc))):
        page = doc[pno]
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    s = round(span["size"], 1)
                    if 8 <= s <= 14:
                        size_counts[s] = size_counts.get(s, 0) + len(span["text"])
    if not size_counts:
        return 11.0
    return max(size_counts, key=size_counts.get)


def _classify_line(text: str) -> str | None:
    """Return section key if the line matches a section heading, else None."""
    t = text.strip()
    if not t or len(t) > 160 or _EXCLUDE_RE.search(t):
        return None
    # strip leading section numbers like "4.1", "III.", "A."
    cleaned = re.sub(r'^[\d\.\s]+|^[IVXLCDM]+\.\s*|^[A-Z]\.\s*', '', t).strip()
    for key, pat in _SECTION_DEFS:
        if pat.search(cleaned):
            return key
    return None


def _is_heading_span(text: str, size: float, bold: bool, body_size: float) -> bool:
    """Heuristic: is this a heading-level span?"""
    if not text.strip() or len(text.strip()) > 160:
        return False
    # Must be bold or noticeably larger than body
    return bold or size >= body_size + 1.5


def extract_sections(pdf_path: Path) -> dict[str, str]:
    """
    Return dict with keys: findings, results, lessons_learned, conclusions, recommendations.
    Values are extracted text (may be empty string if section not found).
    """
    doc = fitz.open(str(pdf_path))
    body_size = _get_body_size(doc)
    n_pages   = len(doc)

    # ── Pass 1: collect all heading events ──────────────────────────────────
    # Each event: (page_idx, block_idx, line_idx, section_key, heading_text, char_offset)
    events: list[dict] = []
    char_offset = 0  # running character position across the whole doc

    all_text_segments: list[tuple[int, str]] = []  # (char_offset, text)

    for pno in range(n_pages):
        page = doc[pno]
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        for bidx, block in enumerate(blocks):
            if block.get("type") != 0:
                continue
            for lidx, line in enumerate(block.get("lines", [])):
                spans = line.get("spans", [])
                if not spans:
                    continue

                line_text  = " ".join(s["text"] for s in spans).strip()
                line_size  = round(spans[0]["size"], 1)
                line_bold  = any(bool(s["flags"] & 16) for s in spans)

                all_text_segments.append((char_offset, line_text + "\n"))

                # Only look for headings after SKIP_FIRST_N_PAGES
                if pno >= SKIP_FIRST_N_PAGES and _is_heading_span(line_text, line_size, line_bold, body_size):
                    section_key = _classify_line(line_text)
                    if section_key:
                        events.append({
                            "page":         pno,
                            "offset":       char_offset,
                            "section_key":  section_key,
                            "heading_text": line_text,
                        })

                char_offset += len(line_text) + 1

    doc.close()

    if not events:
        return {k: "" for k, _ in _SECTION_DEFS}

    # ── Pass 2: build flat doc text ──────────────────────────────────────────
    full_text = "".join(text for _, text in all_text_segments)

    # ── Pass 3: for each section key, pick the BEST heading ─────────────────
    # Strategy: prefer headings that appear in the second half of the doc;
    # among ties, pick the one with the most text following it.

    # Count how many distinct section keywords appear in a heading text.
    # Prefer specific headings (1 keyword) over combined ones (2+ keywords).
    _ALL_SEC_RES = [pat for _, pat in _SECTION_DEFS]

    def _heading_keyword_count(text: str) -> int:
        cleaned = re.sub(r'^[\d\.\s]+|^[IVXLCDM]+\.\s*|^[A-Z]\.\s*', '', text).strip()
        return sum(1 for pat in _ALL_SEC_RES if pat.search(cleaned))

    best_events: dict[str, dict] = {}
    for ev in events:
        key = ev["section_key"]
        if key not in best_events:
            best_events[key] = ev
        else:
            existing = best_events[key]
            cur_specificity  = _heading_keyword_count(ev["heading_text"])
            prev_specificity = _heading_keyword_count(existing["heading_text"])
            # Prefer more specific headings (fewer combined keywords)
            if cur_specificity < prev_specificity:
                best_events[key] = ev
            # If same specificity, prefer later-occurring headings
            elif cur_specificity == prev_specificity and ev["page"] > existing["page"] * 1.5:
                best_events[key] = ev

    # ── Pass 4: extract text between headings ────────────────────────────────
    # Sort chosen events by offset, find the next event boundary
    chosen = sorted(best_events.values(), key=lambda e: e["offset"])
    offset_to_next: dict[int, int] = {}
    for i, ev in enumerate(chosen):
        if i + 1 < len(chosen):
            offset_to_next[ev["offset"]] = chosen[i + 1]["offset"]
        else:
            offset_to_next[ev["offset"]] = len(full_text)

    result: dict[str, str] = {}
    for key, _ in _SECTION_DEFS:
        if key not in best_events:
            result[key] = ""
            continue

        ev       = best_events[key]
        start    = ev["offset"]
        end      = offset_to_next.get(start, len(full_text))
        raw      = full_text[start:end].strip()

        # Clean up: remove the heading line itself, collapse whitespace
        lines = raw.split("\n")
        # skip the first line (the heading itself)
        body_lines = lines[1:] if lines else []
        body = "\n".join(l for l in body_lines if l.strip())
        # Collapse excessive blank lines
        body = re.sub(r'\n{3,}', '\n\n', body)

        result[key] = body[:MAX_SECTION_CHARS]

    return result


# ─────────────────────────── PIPELINE ───────────────────────────────────────

def load_metadata() -> list[dict]:
    with open(META_FILE) as f:
        raw = yaml.safe_load(f) or {}
    # Support both top-level list and {'reports': [...]} structure
    if isinstance(raw, dict):
        return raw.get("reports", [])
    return raw


def find_pdf(filename: str) -> Path | None:
    """Find PDF by filename. filename may include year subfolder like '2021/foo.pdf'."""
    # Direct path relative to PDF_DIR
    direct = PDF_DIR / filename
    if direct.exists():
        return direct
    # Just the basename
    basename = Path(filename).name
    for pdf in PDF_DIR.rglob("*.pdf"):
        if pdf.name == basename:
            return pdf
    return None


def process_report(meta: dict) -> dict:
    filename = meta.get("filename", "")
    pdf_path = find_pdf(filename)
    if not pdf_path:
        return {"report_id": meta["report_id"], "error": f"PDF not found: {filename}"}

    sections = extract_sections(pdf_path)
    found    = [k for k, v in sections.items() if v]

    return {
        "report_id": meta["report_id"],
        "title":     meta.get("title", ""),
        "filename":  filename,
        "sections":  sections,
        "found":     found,
    }


def run_all(filter_id: str | None = None):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    metadata = load_metadata()

    if filter_id:
        metadata = [m for m in metadata if filter_id.lower() in m.get("report_id", "").lower()]
        if not metadata:
            print(f"No reports matching '{filter_id}'")
            return

    total = len(metadata)
    succeeded = 0
    failed = 0

    print(f"\n{'='*60}")
    print(f"PDF Section Extractor — {total} reports")
    print(f"Output: {OUT_DIR}")
    print(f"{'='*60}\n")

    for i, meta in enumerate(metadata, 1):
        rid = meta.get("report_id", "?")
        print(f"[{i:2d}/{total}] {rid} ...", end=" ", flush=True)

        result = process_report(meta)

        if "error" in result:
            print(f"❌ {result['error']}")
            failed += 1
            continue

        found = result["found"]
        out_path = OUT_DIR / f"{rid}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        label = ", ".join(found) if found else "NONE"
        print(f"✅ [{label}]")
        succeeded += 1

    print(f"\n{'='*60}")
    print(f"Done. {succeeded} succeeded, {failed} failed.")
    print(f"JSON files in: {OUT_DIR}")


# ─────────