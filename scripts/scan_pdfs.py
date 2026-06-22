"""
Scans data/pdfs/ (including year subfolders) and generates a pre-filled
metadata.yaml — extracts country, thematic area, and SDGs from filenames.

Run from the eio-rag folder:
  python scripts/scan_pdfs.py

Output: data/metadata_generated.yaml
Review it, correct anything marked CHECK, then rename to metadata.yaml.
"""

import re
import sys
from pathlib import Path
import yaml

BASE_DIR = Path(__file__).parent.parent
PDF_DIR  = BASE_DIR / "data" / "pdfs"
OUT_FILE = BASE_DIR / "data" / "metadata_generated.yaml"

# ── Country name → (region, aliases to match in filename) ────────────────────
COUNTRIES = {
    "Azerbaijan":        ("Europe",        ["Azerbaijan", "AZE"]),
    "Ukraine":           ("Europe",        ["Ukraine", "UKR"]),
    "Serbia":            ("Europe",        ["Serbia"]),
    "Russia":            ("Europe",        ["Russia", "Russian"]),
    "Morocco":           ("Africa",        ["Morocco", "Morocc", "Maghreb"]),
    "Egypt":             ("Middle East",   ["Egypt", "Egyptian", "EGY"]),
    "Nigeria":           ("Africa",        ["Nigeria", "Nigerian", "NIG"]),
    "Senegal":           ("Africa",        ["Senegal"]),
    "Cameroon":          ("Africa",        ["Cameroon"]),
    "Kenya":             ("Africa",        ["Kenya", "KEN"]),
    "South Africa":      ("Africa",        ["South Africa"]),
    "Madagascar":        ("Africa",        ["Madagascar"]),
    "Mozambique":        ("Africa",        ["Mozambique", "MOZ"]),
    "Republic of Congo": ("Africa",        ["Republic of Congo", "Congo"]),
    "India":             ("Asia",          [" India", "Indian", "_IND"]),
    "China":             ("Asia",          ["China", "Chinese", "CHN"]),
    "Malaysia":          ("Asia",          ["Malaysia", "Malaysian"]),
    "Pakistan":          ("Asia",          ["Pakistan"]),
    "Thailand":          ("Asia",          ["Thailand", "Thai", "THA"]),
    "Sri Lanka":         ("Asia",          ["Sri Lanka", "SRL"]),
    "Uruguay":           ("Latin America", ["Uruguay", "URU"]),
    "Bolivia":           ("Latin America", ["Bolivia"]),
    "Dominican Republic":("Latin America", ["Domini"]),
    "Caribbean":         ("Latin America", ["Caribbean", "CCREEE"]),
    "Pacific":           ("Global",        ["Pacific", "PCREEE"]),
    "Mediterranean":     ("Global",        ["SwitchMed", "Maghreb"]),
    "Latin America":     ("Latin America", ["LAC countries", "LAC "]),
}

# ── Keyword → thematic area + default SDGs ───────────────────────────────────
THEMATIC_MAP = [
    # (keywords_any_match,          thematic_category,                       sdgs)
    (["HCFC", "PCB", "POPs", "POP", "DDT", "PCPs", "WEEE", "contaminated",
      "Stockholm", "BAT", "BEP", "hazardous waste", "medical waste",
      "open burning", "OHIS"],     "Chemicals & POPs",                      [3, 12, 13]),
    (["energy efficiency", "EE ",
      "industrial energy", "solar thermal", "process heat",
      "RECP", "cleaner production"],
                                   "Energy Efficiency",                      [7, 9, 13]),
    (["renewable energy", "solar energy", "biomass", "hydropower",
      "hydro", "geothermal", "mini-grid", "CCREEE", "PCREEE",
      "energy access", "electrification", "clean energy"],
                                   "Clean / Renewable Energy",               [7, 1, 13]),
    (["waste-to-energy", "waste to energy", "waste to clean energy",
      "organic waste", "municipal waste", "solid waste",
      "circular", "SwitchMed", "scrap metal"],
                                   "Circular Economy / Waste Management",    [12, 11, 13]),
    (["water", "H2O", "leather"],  "Water & Environment",                   [6, 9, 13]),
    (["IoT", "Internet of Things",
      "digital", "technology transfer", "CTCN"],
                                   "Digital Innovation",                     [9, 17]),
    (["sustainable city", "sustainable cities",
      "urban", "green recovery", "industrial capacity",
      "financing", "competitiveness", "SwitchMed"],
                                   "Industrial Policy & Competitiveness",    [9, 11, 13]),
    (["climate", "GHG", "low carbon", "emission",
      "new energy vehicles"],      "Climate Action",                         [13, 9, 11]),
    (["agro", "food", "agriculture"], "Agro-Industry & Food Systems",        [2, 12, 15]),
    (["gender", "women"],          "Gender & Inclusion",                     [5, 10]),
]

# ── Additional SDGs by keyword ────────────────────────────────────────────────
EXTRA_SDGS = {
    17: ["technology transfer", "CTCN", "partnership", "financing", "network",
         "CCREEE", "PCREEE", "capacity"],
    8:  ["MSME", "SME", "enterprise", "employment", "industry"],
    11: ["city", "cities", "urban"],
    3:  ["health", "waste", "hazardous", "PCB", "POPs", "contamin"],
    6:  ["water", "H2O"],
    1:  ["rural", "electrification", "energy access", "productive use"],
    15: ["land", "deforestation"],
    9:  ["industry", "infrastructure", "industrial"],
}


def guess_year(path: Path, folder: str) -> int:
    for src in [folder, path.stem, path.name]:
        for tok in re.findall(r'\b(20\d{2})\b', src):
            if 2000 <= int(tok) <= 2030:
                return int(tok)
    return 9999


def guess_country_region(text: str):
    text_lower = text.lower()
    # Prioritise longer / more specific matches first
    for country, (region, aliases) in sorted(
            COUNTRIES.items(), key=lambda x: -max(len(a) for a in x[1][1])):
        for alias in aliases:
            if alias.lower() in text_lower:
                return country, region
    return "CHECK — not detected", "CHECK"


def guess_thematic_sdgs(text: str):
    text_lower = text.lower()
    for keywords, thematic, base_sdgs in THEMATIC_MAP:
        if any(kw.lower() in text_lower for kw in keywords):
            sdgs = list(base_sdgs)
            for sdg, kw_list in EXTRA_SDGS.items():
                if sdg not in sdgs and any(kw.lower() in text_lower for kw in kw_list):
                    sdgs.append(sdg)
            return thematic, sorted(set(sdgs))
    return "CHECK — not detected", [17]


def guess_donor(text: str) -> str:
    t = text.lower()
    if re.search(r'\bGF[A-Z]{2,}\b', text) or text.startswith("GF"):
        return "GEF"
    if "gef" in t:       return "GEF"
    if "eu " in t or "_eu_" in t or "european" in t: return "EU"
    if "sida" in t:      return "SIDA"
    if "japan" in t:     return "Government of Japan"
    if "unep" in t:      return "UNEP"
    return "CHECK"


def guess_eval_type(text: str) -> str:
    t = text.lower()
    if "thematic" in t:        return "Thematic Evaluation"
    if "country" in t:         return "Country Evaluation"
    if "synthesis" in t:       return "Synthesis"
    if "cluster" in t:         return "Synthesis"
    return "Project Evaluation"


def main():
    if not PDF_DIR.exists():
        print(f"❌ PDF directory not found: {PDF_DIR}"); sys.exit(1)

    pdfs = []
    for item in sorted(PDF_DIR.iterdir()):
        if item.is_file() and item.suffix.lower() == ".pdf":
            pdfs.append((item, ""))
        elif item.is_dir():
            for pdf in sorted(item.glob("*.pdf")):
                pdfs.append((pdf, item.name))

    if not pdfs:
        print("No PDFs found."); sys.exit(0)

    print(f"\nFound {len(pdfs)} PDFs — analysing filenames...\n")

    entries = []
    needs_check = 0

    for i, (pdf_path, folder) in enumerate(pdfs, 1):
        filename_in_yaml = f"{folder}/{pdf_path.name}" if folder else pdf_path.name
        # Use full filename (without .pdf extension) as the text to analyse
        full_text = pdf_path.stem.replace("_", " ").replace("-", " ")

        year                   = guess_year(pdf_path, folder)
        country, region        = guess_country_region(full_text)
        thematic, sdgs         = guess_thematic_sdgs(full_text)
        donor                  = guess_donor(pdf_path.name)
        eval_type              = guess_eval_type(full_text)

        # Use the stem as a starter title (nicer than FILL IN)
        # Strip common prefixes like "Evaluation report on "
        title_guess = re.sub(
            r'^(evaluation\s+report\s+on\s+|evalrep[_\s]+|final\s+report\s+on\s+the\s+'
            r'independent\s+terminal\s+evaluation\s+of\s+)',
            '', full_text, flags=re.IGNORECASE
        ).strip().capitalize()
        # Add "CHECK — " if country not detected
        if "CHECK" in country:
            needs_check += 1

        flag = "CHECK — " if "CHECK" in country or "CHECK" in thematic else ""

        entry = {
            "report_id":         f"unido-{i:03d}",
            "title":             f"{flag}{title_guess}",
            "filename":          filename_in_yaml,
            "year":              year,
            "country":           country,
            "region":            region,
            "thematic_category": thematic,
            "dac_criteria":      ["Relevance", "Effectiveness", "Efficiency",
                                  "Impact", "Sustainability"],
            "sdgs":              sdgs,
            "evaluation_type":   eval_type,
            "donor":             donor,
            "project_id":        "",
        }
        entries.append(entry)
        status = "✅" if "CHECK" not in country and "CHECK" not in thematic else "⚠ "
        print(f"  {status} [{i:02d}] {country:25s} | {thematic[:35]:35s} | SDGs {sdgs}")

    header = """\
# ═══════════════════════════════════════════════════════════════════════════════
# AUTO-GENERATED by scripts/scan_pdfs.py  (smarter version)
#
# Fields marked "CHECK —" need your attention before ingestion.
# Everything else has been auto-detected from the filename.
#
# To review: search for "CHECK" in this file (Ctrl+F in VS Code).
#
# thematic_category — valid values:
#   Energy Efficiency | Clean / Renewable Energy | Climate Action |
#   Circular Economy / Waste Management | Chemicals & POPs |
#   Industrial Policy & Competitiveness | Trade & Standards |
#   Agro-Industry & Food Systems | Water & Environment |
#   Gender & Inclusion | Digital Innovation
#
# region — valid values:
#   Africa | Asia | Europe | Latin America | Middle East | Global
# ═══════════════════════════════════════════════════════════════════════════════

"""

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(header)
        yaml.dump({"reports": entries}, f,
                  default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"\n{'='*60}")
    print(f"✅  Generated: {OUT_FILE}")
    print(f"⚠   Entries needing manual check: {needs_check}")
    print(f"\nNext steps:")
    print(f"  1. Open data/metadata_generated.yaml in VS Code")
    print(f"  2. Press Ctrl+F and search for 'CHECK'")
    print(f"  3. Fix those entries (country, thematic, title)")
    print(f"  4. Also update the 'title' fields with official report titles")
    print(f"  5. Rename file to data/metadata.yaml")
    print(f"  6. Run: python scripts/ingest.py")


if __name__ == "__main__":
    main()
