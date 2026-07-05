"""
Extraction script: reads ALL UNIDO PDFs across 2021–2025, calls Gemini 2.0 Flash,
saves structured JSON to data/ai_extractions/<report_id>.json

Usage:
    cd eio-rag
    pip install google-genai pdfplumber python-dotenv
    # Add GEMINI_API_KEY=your-key to eio-rag/.env
    python scripts/ai_extract_gemini.py

    # To re-run only missing reports (skip already extracted):
    python scripts/ai_extract_gemini.py --skip-existing

    # To run a single report:
    python scripts/ai_extract_gemini.py --only UNIDO-100043

Get a free key at: https://aistudio.google.com/apikey
"""

import os
import sys
import json
import time
import yaml
import pdfplumber
from google import genai
from google.genai import types

# Load .env from the eio-rag/ root
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    load_dotenv(_env_path)
except ImportError:
    pass

# ── CONFIG ────────────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL_NAME     = "gemini-2.0-flash"
MAX_WORDS      = 35000

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_BASE  = os.path.join(BASE_DIR, "data", "pdfs")
OUT_DIR   = os.path.join(BASE_DIR, "data", "ai_extractions")
META_FILE = os.path.join(BASE_DIR, "data", "metadata.yaml")

THEMATIC_AREAS = [
    "Energy Efficiency", "Clean / Renewable Energy", "Climate Action",
    "Circular Economy / Waste Management", "Chemicals & POPs",
    "Industrial Policy & Competitiveness", "Trade & Standards",
    "Agro-Industry & Food Systems", "Water & Environment",
    "Gender & Inclusion", "Digital Innovation",
]

EXTRACTION_PROMPT = """You are a senior evaluation analyst at UNIDO's Independent Evaluation Unit.
Carefully read the evaluation report text below and extract structured information.

Return ONLY a valid JSON object — no markdown fences, no explanation, nothing before or after the JSON.

RULES:
1. Set any field to null if you cannot determine it with confidence — never invent data.
2. Thematic areas are NEVER explicitly stated — infer from project objectives, activities, and outcomes.
3. SDGs are NEVER explicitly stated — infer which SDGs genuinely apply. Only include SDGs with clear evidence.
4. Lessons learned must be GENERALIZABLE principles, not project-specific observations.
5. Recommendations must have a clear ACTOR (who) and ACTION (what they should do).
6. Write the executive_summary yourself in 200–300 words — do not copy sentences from the document.
7. For evaluation_rating: look for an overall rating score. UNIDO uses a 1–6 scale (6 = highest). Return null if not found.

VALID THEMATIC AREAS (pick the single best primary, optionally one secondary):
{thematic_areas}

RETURN THIS EXACT JSON STRUCTURE:
{{
  "report_id": "{report_id}",
  "executive_summary": "200–300 word synthesis written by you, not copied",
  "lessons_learned": [
    "Generalizable lesson as a complete sentence.",
    "Another generalizable lesson."
  ],
  "recommendations": [
    "Actor should/must do specific action.",
    "Another actor should do something."
  ],
  "sdg_mapping": {{
    "7": "One sentence explaining why SDG 7 applies based on specific report content.",
    "13": "One sentence explaining why SDG 13 applies."
  }},
  "primary_thematic_area": "Exact name from the valid list above",
  "secondary_thematic_area": "Exact name from the valid list, or null",
  "thematic_justification": "One sentence citing specific project activities that justify this classification.",
  "context": {{
    "title": "Full official report title",
    "year": null,
    "country": "Country name(s)",
    "region": "Africa | Asia | Europe | Latin America | Middle East | Global",
    "report_type": "Project Evaluation",
    "evaluation_rating": null,
    "donor": "Main donor name or null",
    "project_id": "UNIDO project ID code or null",
    "budget_usd": null
  }}
}}

REPORT TEXT:
{text}"""

# ── HELPERS ───────────────────────────────────────────────────────────────────

def load_all_reports() -> list[dict]:
    """Load all reports from metadata.yaml."""
    with open(META_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("reports", [])


def find_pdf(filename: str) -> str | None:
    """Resolve a relative filename from metadata.yaml to an absolute path."""
    path = os.path.join(PDF_BASE, filename)
    if os.path.exists(path):
        return path
    # Try without the year subfolder
    basename = os.path.basename(filename)
    for root, _, files in os.walk(PDF_BASE):
        if basename in files:
            return os.path.join(root, basename)
    return None


def extract_text(pdf_path: str) -> tuple[str, int, int]:
    pages, all_text = 0, []
    with pdfplumber.open(pdf_path) as pdf:
        pages = len(pdf.pages)
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                all_text.append(t)
    full_text = "\n\n".join(all_text)
    words = full_text.split()
    if len(words) > MAX_WORDS:
        print(f"  ⚠️  Truncating to {MAX_WORDS:,} words (was {len(words):,})")
        full_text = " ".join(words[:MAX_WORDS])
    return full_text, pages, len(words)


def call_gemini(client, prompt: str, attempt: int = 1) -> dict:
    import re as _re
    print(f"  🤖 Calling Gemini (attempt {attempt})...")
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=4096,
            ),
        )
        raw = response.text.strip()
    except Exception as e:
        err_str = str(e)
        delay_match = _re.search(r'retry in (\d+)', err_str, _re.IGNORECASE)
        if delay_match and attempt <= 5:
            wait = int(delay_match.group(1)) + 5
            print(f"  ⏳ Rate limited — waiting {wait}s then retrying...")
            time.sleep(wait)
            return call_gemini(client, prompt, attempt + 1)
        raise

    if raw.startswith("```"):
        raw = raw.split("```", 2)[-1]
        if raw.startswith("json"):
            raw = raw[4:]
        if "```" in raw:
            raw = raw[:raw.rfind("```")]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        if attempt <= 2:
            print(f"  ⚠️  JSON parse failed, retrying...")
            time.sleep(3)
            return call_gemini(client, prompt + "\n\nReturn ONLY raw JSON starting with { and ending with }.", attempt + 1)
        raise ValueError(f"Could not parse JSON.\nRaw:\n{raw[:500]}")


def process_report(client, report_meta: dict) -> dict:
    rid      = report_meta["report_id"]
    filename = report_meta.get("filename", "")
    out_path = os.path.join(OUT_DIR, f"{rid}.json")

    pdf_path = find_pdf(filename)
    if not pdf_path:
        raise FileNotFoundError(f"PDF not found: {filename}")

    print("  📄 Extracting PDF text...")
    text, pages, words = extract_text(pdf_path)
    print(f"  ✅ {pages} pages, {words:,} words extracted")

    prompt = EXTRACTION_PROMPT.format(
        thematic_areas="\n".join(f"  - {t}" for t in THEMATIC_AREAS),
        report_id=rid,
        text=text,
    )

    data = call_gemini(client, prompt)
    data["_extraction_meta"] = {
        "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": MODEL_NAME,
        "pdf_pages": pages,
        "pdf_words_processed": min(words, MAX_WORDS),
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"  ✅ Saved → {out_path}")
    return data


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    skip_existing = "--skip-existing" in sys.argv
    only_id = None
    if "--only" in sys.argv:
        idx = sys.argv.index("--only")
        only_id = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None

    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY not set. Add it to eio-rag/.env")
        return

    client  = genai.Client(api_key=GEMINI_API_KEY)
    reports = load_all_reports()

    if only_id:
        reports = [r for r in reports if r["report_id"] == only_id]
        if not reports:
            print(f"❌ Report ID '{only_id}' not found in metadata.yaml")
            return

    if skip_existing:
        before = len(reports)
        reports = [r for r in reports
                   if not os.path.exists(os.path.join(OUT_DIR, f"{r['report_id']}.json"))]
        print(f"⏭️  Skipping {before - len(reports)} already-extracted reports")

    print(f"✅ Gemini configured ({MODEL_NAME})")
    print(f"📂 PDFs: {PDF_BASE}")
    print(f"📂 Output: {OUT_DIR}")
    print(f"📋 Reports to process: {len(reports)}")

    results, errors = {}, {}

    for i, rep_meta in enumerate(reports):
        rid = rep_meta["report_id"]
        title = rep_meta.get("short_title") or rep_meta.get("title", "")[:50]
        print(f"\n{'='*60}")
        print(f"[{i+1}/{len(reports)}] {rid} — {title}")

        try:
            data = process_report(client, rep_meta)
            results[rid] = "✅ OK"
            print(f"  📚 {len(data.get('lessons_learned', []))} lessons  |  "
                  f"📋 {len(data.get('recommendations', []))} recs  |  "
                  f"🎯 SDGs: {', '.join(data.get('sdg_mapping', {}).keys())}  |  "
                  f"🏷️  {data.get('primary_thematic_area', '?')}")
        except Exception as e:
            errors[rid] = str(e)
            print(f"  ❌ FAILED: {e}")

        if i < len(reports) - 1:
            print("  ⏳ Waiting 5s...")
            time.sleep(5)

    print(f"\n{'='*60}")
    print(f"DONE  ✅ {len(results)} succeeded  ❌ {len(errors)} failed")
    for rid, err in errors.items():
        print(f"  ❌ {rid}: {err[:100]}")
    if not errors:
        print("🎉 All reports extracted! Refresh the app to see AI content.")


if __name__ == "__main__":
    main()
