"""
extract_lr.py — Extract Lessons Learned & Recommendations from UNIDO evaluation PDFs.
Saves to data/lessons_recommendations.yaml

Run from project root:  python extract_lr.py
"""

import re, os, yaml, fitz
from pathlib import Path

# ─── Section heading patterns ─────────────────────────────────────────────────

LESSONS_RE = re.compile(
    r'^(key\s+)?(lessons?\s+learned(\s+and\s+(good\s+practices?|key\s+practices?))?'
    r'|lessons?\s+learnt'
    r'|good\s+practices?\s+and\s+lessons?\s+learned)$', re.I)

RECS_RE = re.compile(
    r'^((conclusions?\s+(and|/)\s+)?recommendations?'
    r'|recommendations?\s+(and\s+conclusions?|and\s+way\s+forward))$', re.I)

# Headings that signal we've entered an annex / appendix
ANNEX_RE = re.compile(r'^\s*(annex|appendix|annexure)\s*[a-z0-9:\s]*$', re.I)

# Headings that end a lessons or recs section
SECTION_END_RE = re.compile(
    r'^(annex|appendix|bibliography|references?|acronyms?|abbreviations?|'
    r'management\s+response|conclusions?\s+and\s+recommendations?|conclusions?|'
    r'findings?|executive\s+summary|methodology|background|introduction|'
    r'summary\s+of\s+ratings?|rating\s+summary|recommendations?\s+matrix|'
    r'evaluation\s+matrix|logframe|log\s+frame|project\s+results\s+framework)$',
    re.I)


def _is_heading(s: str) -> bool:
    s = s.strip()
    if not s or len(s) > 85:
        return False
    if s[-1] in '.,:;?!':
        return False
    if re.search(r'\b(was|were|is|are|has|have|had|will|would|should|must|can|could)\b', s) and len(s) > 55:
        return False
    return True


def _get_pages(pdf_path: str) -> list[tuple[int, str, list[str]]]:
    doc = fitz.open(pdf_path)
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text("text", sort=True)
        lines = [l for l in text.split('\n')]
        pages.append((i + 1, text, lines))
    doc.close()
    return pages


def _find_annex_start(pages) -> int:
    """Return page number where annexes begin (or total_pages if no annex found)."""
    total = len(pages)
    for pg_num, text, lines in pages:
        if pg_num < total * 0.6:
            continue
        for line in lines:
            s = line.strip()
            if _is_heading(s) and ANNEX_RE.match(s):
                return pg_num
    return total + 1


def _find_section_page(pages, pattern: re.Pattern, annex_start: int,
                       total_pages: int) -> int | None:
    """Find the best page for a section heading — in main body, not annexes/ToC."""
    candidates = []
    for pg_num, text, lines in pages:
        if pg_num >= annex_start:
            break
        if pg_num < total_pages * 0.25:  # skip first 25% (intro/ToC)
            continue
        for line in lines:
            s = line.strip()
            if _is_heading(s) and pattern.match(s):
                candidates.append(pg_num)
                break  # one match per page
    return candidates[-1] if candidates else None


def _extract_from_page(pages, start_page: int, stop_on: list[re.Pattern]) -> str:
    """Collect text starting from start_page until a stop heading is found."""
    result = []
    in_section = False

    for pg_num, text, lines in pages:
        if pg_num < start_page:
            continue

        for line in lines:
            s = line.strip()

            if not in_section:
                if pg_num == start_page and _is_heading(s) and any(p.match(s) for p in stop_on):
                    in_section = True
                continue

            # Stop conditions
            if s and _is_heading(s) and len(s) < 85:
                if SECTION_END_RE.match(s):
                    return '\n'.join(result).strip()
                for p in stop_on:
                    # Stop if we hit another primary section of the same type (different page)
                    if pg_num > start_page and p.match(s):
                        return '\n'.join(result).strip()

            result.append(line)

    return '\n'.join(result).strip()


def _clean(text: str) -> str:
    lines = text.split('\n')
    out = []
    for line in lines:
        s = line.strip()
        if re.match(r'^\d{1,3}$', s):
            continue
        if s.isupper() and len(s.split()) <= 3 and len(s) < 30:
            continue
        out.append(line)
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(out)).strip()


def _split_items(text: str) -> list[str]:
    if not text:
        return []
    item_re = re.compile(
        r'(?:^|\n)[ \t]*(?:'
        r'(?:recommendation|lesson|finding|good\s+practice)\s*\d+\s*[:.][ \t]*|'
        r'\d{1,2}[ \t]*[.):][ \t]+(?=[A-Z])'
        r')',
        re.I | re.MULTILINE
    )
    positions = [m.start() for m in item_re.finditer('\n' + text)]
    if len(positions) < 2:
        return [text.strip()] if len(text.strip()) > 60 else []

    items = []
    padded = '\n' + text
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(padded)
        raw = padded[pos:end].strip()
        if len(raw) > 40:
            items.append(raw)
    return items


def extract_from_pdf(pdf_path: str) -> dict:
    pages = _get_pages(pdf_path)
    total = len(pages)
    annex_start = _find_annex_start(pages)

    lesson_page = _find_section_page(pages, LESSONS_RE, annex_start, total)
    rec_page    = _find_section_page(pages, RECS_RE,    annex_start, total)

    lessons_text = ""
    recs_text    = ""

    if lesson_page:
        raw = _extract_from_page(pages, lesson_page, [LESSONS_RE, RECS_RE])
        lessons_text = _clean(raw)

    if rec_page:
        raw = _extract_from_page(pages, rec_page, [RECS_RE])
        recs_text = _clean(raw)

    return {
        "lessons_text":  lessons_text,
        "lessons_items": _split_items(lessons_text),
        "recs_text":     recs_text,
        "recs_items":    _split_items(recs_text),
        "lesson_pages":  [lesson_page] if lesson_page else [],
        "rec_pages":     [rec_page]    if rec_page    else [],
        "annex_start":   annex_start,
        "total_pages":   total,
    }


def run_extraction():
    root      = Path(__file__).parent
    pdf_root  = root / "data" / "pdfs"
    meta_file = root / "data" / "metadata.yaml"
    out_file  = root / "data" / "lessons_recommendations.yaml"

    with open(meta_file, encoding="utf-8") as f:
        meta = yaml.safe_load(f)

    reports = meta.get("reports", [])
    results, errors = {}, []

    print(f"Processing {len(reports)} reports...\n")

    for i, rep in enumerate(reports, 1):
        rid      = rep.get("report_id", "")
        title    = rep.get("title", "")[:55]
        filename = rep.get("filename", "")
        pdf_path = pdf_root / filename

        print(f"[{i:2d}/{len(reports)}] {title}")

        if not pdf_path.exists():
            print(f"          ⚠  Not found: {filename}")
            errors.append(rid); continue

        try:
            r = extract_from_pdf(str(pdf_path))
            nl, nr = len(r["lessons_items"]), len(r["recs_items"])
            ok = "✓" if (nl + nr) > 0 else "⚠  no items"
            print(f"          {ok}  lessons: {nl}  recs: {nr}  "
                  f"(L-p{r['lesson_pages']} R-p{r['rec_pages']} annex@{r['annex_start']})")
            results[rid] = {
                "report_id":          rid,
                "title":              rep.get("title", ""),
                "lessons_learned":    r["lessons_text"],
                "lessons_items":      r["lessons_items"],
                "recommendations":    r["recs_text"],
                "recommendations_items": r["recs_items"],
            }
        except Exception as e:
            print(f"          ✗  ERROR: {e}")
            errors.append(rid)

    with open(out_file, "w", encoding="utf-8") as f:
        yaml.dump({"extractions": list(results.values())},
                  f, allow_unicode=True, default_flow_style=False, width=120)

    print(f"\n✅  Saved → {out_file}")
    print(f"    {len(results)} succeeded · {len(errors)} failed")


if __name__ == "__main__":
    run_extraction()
