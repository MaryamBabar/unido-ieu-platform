"""
Groq extraction script — UNIDO evaluation reports.
Sends the last 40% of each PDF directly to Groq — no regex section detection.
Works regardless of how individual reports format their headers.
Scales to 100+ reports.

Usage:
    cd eio-rag
    python scripts/ai_extract_groq.py                        # all reports in REPORTS dict
    python scripts/ai_extract_groq.py --only UNIDO-100321    # single report
    python scripts/ai_extract_groq.py --skip-existing        # skip already done
    python scripts/ai_extract_groq.py --pdf path/to/file.pdf --id UNIDO-XXXXX --title "..."

Add GROQ_API_KEY=gsk_... to eio-rag/.env
Get a free key at: https://console.groq.com
"""

import os, sys, json, time, re, argparse
import pdfplumber
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from groq import Groq

# ── CONFIG ────────────────────────────────────────────────────────────────────

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
MODEL        = "llama-3.3-70b-versatile"
MAX_CHARS    = 14000   # Groq context limit per call

BASE_DIR = Path(__file__).parent.parent
PDF_DIR  = BASE_DIR / "data" / "pdfs"
OUT_DIR  = BASE_DIR / "data" / "ai_extractions"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Add your reports here — or pass --pdf / --id / --title flags for ad-hoc extraction
REPORTS = {
    "UNIDO-100043": {
        "pdf":   "2021/GFSRL-100043_TE_Report_2020_E.pdf.pdf",
        "title": 'Independent Terminal Evaluation: The Project "Bamboo Processing for Sri Lanka"',
    },
    "UNIDO-100321": {
        "pdf":   "2021/EvalRep_AZE-100321_HCFC_Phase_out_TE-2021.pdf",
        "title": "Independent Terminal Evaluation: Initiation of the HCFC Phase Out in the Republic of Azerbaijan",
    },
    "UNIDO-104112": {
        "pdf":   "2021/EvalRep_UKR-104112_RECP_TE-2020.pdf",
        "title": "Independent Terminal Evaluation: Promoting the Adaptation and Adoption of RECP (Resource Efficient and Cleaner Production) Through the Establishment and Operation of a Cleaner Production Centre (CPC) in Ukraine",
    },
    "UNIDO-120323": {
        "pdf":   "2021/GF_ID-4890_GFURU-120323_TE_Report_2020_E.pdf.pdf",
        "title": "Independent Terminal Evaluation: Towards a Green Economy in Uruguay: Stimulating Sustainable Practices and Low-Emission Technologies in Prioritized Sectors",
    },
}

THEMATIC_AREAS = [
    "Energy Efficiency", "Clean / Renewable Energy", "Climate Action",
    "Circular Economy / Waste Management", "Chemicals & POPs",
    "Industrial Policy & Competitiveness", "Trade & Standards",
    "Agro-Industry & Food Systems", "Water & Environment",
    "Gender & Inclusion", "Digital Innovation",
]

# ── PDF EXTRACTION ────────────────────────────────────────────────────────────

def extract_pdf_text(pdf_path: Path) -> tuple[str, str, int]:
    """
    Returns (full_start_text, end_text, n_pages).
    end_text = last 40% of the document (where lessons/recs always appear).
    start_text = first 20% (for context/summary).
    """
    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        n_pages = len(pdf.pages)
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                pages.append(t)

    full = "\n\n".join(pages)
    chars = len(full)

    # First 20% for context
    start_text = full[: int(chars * 0.20)]
    # Last 40% for lessons + recommendations (always at end of UNIDO reports)
    end_text   = full[int(chars * 0.60):]

    return start_text, end_text, n_pages


def find_pdf(rel_path: str) -> Path | None:
    exact = PDF_DIR / rel_path
    if exact.exists():
        return exact
    alt = rel_path.replace(".pdf.pdf", ".pdf")
    if (PDF_DIR / alt).exists():
        return PDF_DIR / alt
    name = Path(rel_path).name
    for p in PDF_DIR.rglob("*"):
        if p.name == name:
            return p
    return None


# ── GROQ CALLS ────────────────────────────────────────────────────────────────

def call_groq(client: Groq, messages: list, attempt: int = 1) -> str:
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.0,
            max_tokens=4096,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        err = str(e)
        m = re.search(r'try again in ([\d.]+)s', err, re.IGNORECASE)
        wait = float(m.group(1)) + 3 if m else 30
        if attempt <= 4:
            print(f"    ⏳ Rate limit — waiting {wait:.0f}s (attempt {attempt+1}/4)...")
            time.sleep(wait)
            return call_groq(client, messages, attempt + 1)
        raise


def parse_json(raw: str) -> dict:
    raw = raw.strip()
    if "```" in raw:
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$',          '', raw, flags=re.MULTILINE)
        raw = raw.strip()
    start = raw.find('{')
    end   = raw.rfind('}')
    if start != -1 and end != -1:
        raw = raw[start:end+1]
    return json.loads(raw)


def extract_lessons_and_recs(client: Groq, title: str, end_text: str) -> dict:
    """
    Send the last 40% of the PDF to Groq.
    Ask it to find lessons and recommendations regardless of header format.
    """
    system = (
        "You are a UNIDO evaluation expert extracting structured data from evaluation reports. "
        "Return ONLY valid JSON. No markdown fences, no explanation, nothing before or after the JSON."
    )

    user = f"""Report title: {title}

Below is text from the latter portion of a UNIDO evaluation report.
This section contains the lessons learned and recommendations.
They may be labelled in various ways: "Lessons Learned", "Lessons Learnt", "Lesson #1",
"Lessons and good practices", "C. Lessons", numbered bullet points, lettered sections, etc.
Recommendations may appear as "Recommendation 1", "Recommendation #1", "B. Recommendations",
"Conclusion X / Recommendation X" pairs, or bullet points.

RULES:
1. Copy the EXACT wording of each lesson and each recommendation as written in the text.
2. Do NOT paraphrase, summarize, or rewrite. Verbatim only.
3. Include ALL lessons and ALL recommendations you find — do not truncate.
4. Each item must be a complete sentence or paragraph.
5. If a recommendation has sub-parts (e.g. 1a, 1b), include the full text of each sub-part as a separate item, or combined if they read as one.
6. Return empty lists if genuinely not found.

REPORT TEXT:
{end_text[:MAX_CHARS]}

Return this exact JSON:
{{
  "lessons_learned": [
    "Exact verbatim lesson 1.",
    "Exact verbatim lesson 2."
  ],
  "recommendations": [
    "Exact verbatim recommendation 1.",
    "Exact verbatim recommendation 2."
  ]
}}"""

    raw = call_groq(client, [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ])
    try:
        return parse_json(raw)
    except Exception as e:
        print(f"    ⚠️  JSON parse error on call 1: {e}")
        return {"lessons_learned": [], "recommendations": []}


def extract_metadata(client: Groq, title: str, start_text: str) -> dict:
    """
    Send the first 20% of the PDF to Groq.
    Extract SDGs, thematic area, executive summary, and context fields.
    """
    system = (
        "You are a senior UNIDO evaluation analyst. "
        "Return ONLY valid JSON. No markdown, no explanation."
    )

    thematic_list = "\n".join(f"  - {t}" for t in THEMATIC_AREAS)

    user = f"""Report title: {title}

REPORT CONTEXT (opening section of the evaluation):
{start_text[:MAX_CHARS]}

Return this exact JSON:
{{
  "executive_summary": "Write a 200-250 word synthesis of this project in your own words. Do not copy sentences.",
  "primary_thematic_area": "Exact name from the valid list below",
  "secondary_thematic_area": "Exact name from the valid list or null",
  "thematic_justification": "One sentence citing specific project activities justifying this classification.",
  "sdg_mapping": {{
    "13": "One sentence explaining why SDG 13 applies based on specific evidence from the report."
  }},
  "context": {{
    "title": "{title}",
    "year": null,
    "country": "Country name(s)",
    "region": "Africa | Asia | Europe | Latin America | Middle East | Global",
    "report_type": "Project Evaluation | Thematic Evaluation | Country Evaluation | Synthesis",
    "evaluation_rating": null,
    "donor": "Main donor name or null",
    "project_id": "UNIDO project ID code or null",
    "budget_usd": null
  }}
}}

VALID THEMATIC AREAS (pick single best primary, optionally one secondary):
{thematic_list}

RULES:
- SDGs are NEVER explicitly stated — infer which apply from what the project actually does.
- Include only SDGs with clear direct evidence. Add as many as apply.
- Thematic area is never stated explicitly — infer from project objectives.
- evaluation_rating: look for an overall numeric rating on a 1-6 scale. null if absent.
- Set fields to null if you cannot determine them confidently."""

    raw = call_groq(client, [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ])
    try:
        return parse_json(raw)
    except Exception as e:
        print(f"    ⚠️  JSON parse error on call 2: {e}")
        return {}


# ── PROCESS ONE REPORT ────────────────────────────────────────────────────────

def process_report(client: Groq, report_id: str, pdf_path: Path, title: str) -> dict:
    print(f"\n{'='*60}")
    print(f"  {report_id}")
    print(f"  {title[:70]}...")
    print(f"  📄 {pdf_path.name}")

    start_text, end_text, n_pages = extract_pdf_text(pdf_path)
    print(f"  ✅ {n_pages} pages extracted")

    # Call 1: verbatim lessons + recommendations from end of document
    print("  🤖 Groq call 1/2 — extracting lessons & recommendations...")
    lr = extract_lessons_and_recs(client, title, end_text)
    n_ll  = len(lr.get("lessons_learned", []))
    n_rec = len(lr.get("recommendations", []))
    print(f"  ✅ {n_ll} lessons  |  {n_rec} recommendations")

    if n_ll == 0 and n_rec == 0:
        print("  ⚠️  Nothing found in last 40% — retrying with last 60%...")
        _, end_text2, _ = extract_pdf_text(pdf_path)
        # Use more of the document
        import pdfplumber as _pb
        pages = []
        with _pb.open(str(pdf_path)) as pdf:
            chars_all = []
            for p in pdf.pages:
                t = p.extract_text()
                if t: chars_all.append(t)
        full2 = "\n\n".join(chars_all)
        end_text2 = full2[int(len(full2) * 0.40):]
        lr = extract_lessons_and_recs(client, title, end_text2)
        n_ll  = len(lr.get("lessons_learned", []))
        n_rec = len(lr.get("recommendations", []))
        print(f"  ✅ Retry: {n_ll} lessons  |  {n_rec} recommendations")

    time.sleep(5)  # stay within free-tier rate limits

    # Call 2: metadata from start of document
    print("  🤖 Groq call 2/2 — SDG mapping, thematic area, summary...")
    meta = extract_metadata(client, title, start_text)
    sdgs  = list(meta.get("sdg_mapping", {}).keys())
    theme = meta.get("primary_thematic_area", "?")
    print(f"  ✅ SDGs: {', '.join(sdgs) or 'none'}  |  Theme: {theme}")

    result = {
        "report_id": report_id,
        **lr,
        **meta,
        "_extraction_meta": {
            "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model":        MODEL,
            "pdf_pages":    n_pages,
            "method":       "groq-end-section",
        },
    }

    out_path = OUT_DIR / f"{report_id}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"  💾 Saved → {out_path.name}")
    return result


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Extract UNIDO evaluation report data via Groq")
    parser.add_argument("--only",          help="Process only this report ID")
    parser.add_argument("--skip-existing", action="store_true", help="Skip already-extracted reports")
    parser.add_argument("--pdf",           help="Path to a single PDF (relative to PDF_DIR or absolute)")
    parser.add_argument("--id",            help="Report ID for ad-hoc PDF (e.g. UNIDO-999999)")
    parser.add_argument("--title",         help="Report title for ad-hoc PDF")
    args = parser.parse_args()

    if not GROQ_API_KEY:
        print("\n❌  GROQ_API_KEY not set.")
        print("    Add to eio-rag/.env:  GROQ_API_KEY=gsk_your-key-here")
        print("    Get a free key at:    https://console.groq.com")
        sys.exit(1)

    client = Groq(api_key=GROQ_API_KEY)
    print(f"✅  Groq ready ({MODEL})")

    # Ad-hoc single PDF mode
    if args.pdf:
        if not args.id or not args.title:
            print("❌  --pdf requires --id and --title")
            sys.exit(1)
        pdf_path = Path(args.pdf)
        if not pdf_path.is_absolute():
            pdf_path = PDF_DIR / args.pdf
        if not pdf_path.exists():
            print(f"❌  PDF not found: {pdf_path}")
            sys.exit(1)
        process_report(client, args.id, pdf_path, args.title)
        return

    # Batch mode
    reports = dict(REPORTS)

    if args.only:
        if args.only not in reports:
            print(f"❌  Unknown ID '{args.only}'. Valid: {', '.join(reports)}")
            sys.exit(1)
        reports = {args.only: reports[args.only]}

    if args.skip_existing:
        before  = len(reports)
        reports = {rid: m for rid, m in reports.items()
                   if not (OUT_DIR / f"{rid}.json").exists()}
        print(f"⏭️   Skipping {before - len(reports)} already extracted")

    print(f"📋  Reports to process: {len(reports)}")

    results, errors = {}, {}

    for i, (rid, meta) in enumerate(reports.items()):
        pdf_path = find_pdf(meta["pdf"])
        if not pdf_path:
            errors[rid] = f"PDF not found: {meta['pdf']}"
            print(f"  ❌ {rid}: PDF not found")
            continue

        try:
            process_report(client, rid, pdf_path, meta["title"])
            results[rid] = "✅"
        except Exception as e:
            errors[rid] = str(e)
            print(f"  ❌ FAILED: {e}")

        if i < len(reports) - 1:
            print("  ⏳ Waiting 10s before next report...")
            time.sleep(10)

    print(f"\n{'='*60}")
    print(f"DONE — ✅ {len(results)} succeeded  ❌ {len(errors)} failed")
    if errors:
        for rid, err in errors.items():
            print(f"  ❌ {rid}: {err[:120]}")
    else:
        print("\n🎉  All reports extracted!")
        print("    git add data/ai_extractions/")
        print('    git commit -m "AI-extracted lessons, recs, SDGs"')
        print("    git push origin master")


if __name__ == "__main__":
    main()
