"""
One-time extraction script: reads 4 UNIDO pilot PDFs, calls Gemini 1.5 Flash,
saves structured JSON to data/ai_extractions/<report_id>.json

Usage:
    cd eio-rag
    pip install google-generativeai pdfplumber
    export GEMINI_API_KEY="your-key-here"
    python scripts/ai_extract_gemini.py

Get a free key at: https://aistudio.google.com/apikey
Free tier: 1,500 requests/day, 1M tokens/min — more than enough for 4 reports.
"""

import os
import json
import time
import pdfplumber
import google.generativeai as genai

# ── CONFIG ────────────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL_NAME = "gemini-1.5-flash"
MAX_WORDS = 40000          # truncate very long PDFs to save tokens
RETRY_DELAY = 10           # seconds to wait if rate-limited

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR  = os.path.join(BASE_DIR, "data", "pdfs", "2021")
OUT_DIR  = os.path.join(BASE_DIR, "data", "ai_extractions")

# Report ID → PDF filename mapping
REPORTS = {
    "UNIDO-100043": "GFSRL-100043_TE_Report_2020_E.pdf.pdf",
    "UNIDO-100321": "EvalRep_AZE-100321_HCFC_Phase_out_TE-2021.pdf",
    "UNIDO-104112": "EvalRep_UKR-104112_RECP_TE-2020.pdf",
    "UNIDO-120323": "GF_ID-4890_GFURU-120323_TE_Report_2020_E.pdf.pdf",
}

THEMATIC_AREAS = [
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

EXTRACTION_PROMPT = """
You are a senior evaluation analyst at UNIDO's Independent Evaluation Unit.
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
    "year": 2021,
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
{text}
"""

# ── HELPERS ───────────────────────────────────────────────────────────────────

def extract_text(pdf_path: str) -> tuple[str, int, int]:
    """Extract text from PDF, return (text, pages, words)."""
    pages = 0
    all_text = []
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


def call_gemini(model, prompt: str, report_id: str, attempt: int = 1) -> dict:
    """Call Gemini and return parsed JSON. Retries once on failure."""
    print(f"  🤖 Calling Gemini (attempt {attempt})...")
    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.0,
            max_output_tokens=4096,
        ),
    )
    raw = response.text.strip()

    # Strip markdown fences if Gemini added them anyway
    if raw.startswith("```"):
        raw = raw.split("```", 2)[-1]  # take content after opening fence
        if raw.startswith("json"):
            raw = raw[4:]
        # remove closing fence if present
        if "```" in raw:
            raw = raw[:raw.rfind("```")]
        raw = raw.strip()

    try:
        data = json.loads(raw)
        return data
    except json.JSONDecodeError as e:
        if attempt == 1:
            print(f"  ⚠️  JSON parse failed ({e}), retrying with stricter prompt...")
            stricter = prompt + "\n\nIMPORTANT: Your previous response could not be parsed as JSON. Return ONLY raw JSON, starting with {{ and ending with }}. No other text."
            time.sleep(3)
            return call_gemini(model, stricter, report_id, attempt=2)
        raise ValueError(f"Gemini returned unparseable JSON after 2 attempts.\nRaw output:\n{raw[:500]}")


def process_report(model, report_id: str, pdf_filename: str) -> dict:
    pdf_path = os.path.join(PDF_DIR, pdf_filename)
    out_path = os.path.join(OUT_DIR, f"{report_id}.json")

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    print(f"\n{'='*60}")
    print(f"Processing {report_id}")
    print(f"PDF: {pdf_filename}")

    # Extract text
    print("  📄 Extracting PDF text...")
    text, pages, words = extract_text(pdf_path)
    print(f"  ✅ {pages} pages, {words:,} words extracted")

    # Build prompt
    prompt = EXTRACTION_PROMPT.format(
        thematic_areas="\n".join(f"  - {t}" for t in THEMATIC_AREAS),
        report_id=report_id,
        text=text,
    )

    # Call Gemini
    data = call_gemini(model, prompt, report_id)

    # Add extraction metadata
    data["_extraction_meta"] = {
        "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": MODEL_NAME,
        "pdf_pages": pages,
        "pdf_words_processed": min(words, MAX_WORDS),
    }

    # Save
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"  ✅ Saved → {out_path}")
    return data


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY is not set.")
        print("   Get a free key at: https://aistudio.google.com/apikey")
        print("   Then run:  export GEMINI_API_KEY='your-key-here'")
        return

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    print(f"✅ Gemini configured ({MODEL_NAME})")
    print(f"📂 PDFs from: {PDF_DIR}")
    print(f"📂 Output to: {OUT_DIR}")

    results = {}
    errors  = {}

    for i, (report_id, pdf_filename) in enumerate(REPORTS.items()):
        try:
            data = process_report(model, report_id, pdf_filename)
            results[report_id] = "✅ OK"

            # Print a quick preview
            summary = data.get("executive_summary", "")
            print(f"  📝 Summary preview: {summary[:150]}...")
            lessons = data.get("lessons_learned", [])
            print(f"  📚 {len(lessons)} lessons learned")
            recs = data.get("recommendations", [])
            print(f"  📋 {len(recs)} recommendations")
            sdgs = list(data.get("sdg_mapping", {}).keys())
            print(f"  🎯 SDGs: {', '.join(sdgs) if sdgs else 'none'}")
            print(f"  🏷️  Theme: {data.get('primary_thematic_area', 'unknown')}")

        except Exception as e:
            errors[report_id] = str(e)
            print(f"  ❌ FAILED: {e}")

        # Polite pause between requests (avoid rate limits)
        if i < len(REPORTS) - 1:
            print(f"  ⏳ Waiting 5 seconds before next report...")
            time.sleep(5)

    # Summary
    print(f"\n{'='*60}")
    print("EXTRACTION COMPLETE")
    print(f"{'='*60}")
    for rid, status in results.items():
        print(f"  {status}  {rid}")
    for rid, err in errors.items():
        print(f"  ❌ FAILED  {rid}: {err}")

    if errors:
        print(f"\n⚠️  {len(errors)} report(s) failed. Fix errors above and re-run.")
    else:
        print(f"\n🎉 All {len(results)} reports extracted successfully!")
        print(f"   JSON files are in: {OUT_DIR}")
        print(f"   Reload the Streamlit app to see the updated View Details content.")


if __name__ == "__main__":
    main()
