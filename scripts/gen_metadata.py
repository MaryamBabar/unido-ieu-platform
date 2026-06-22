"""
Generate data/metadata.yaml from the two Excel files.
Run from the eio-rag root:  python scripts/gen_metadata.py
"""
import pandas as pd
import yaml
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
FIN_XLSX = Path("/sessions/clever-determined-goldberg/mnt/uploads/UNIDO_Financial_Overview_with_Analytics (1).xlsx")
RAT_XLSX = Path("/sessions/clever-determined-goldberg/mnt/uploads/Ratings_Summary.xlsx")
OUT_YAML = BASE / "data" / "metadata.yaml"

# ── Load ───────────────────────────────────────────────────────────────────────
fin = pd.read_excel(FIN_XLSX, sheet_name="2_Full_Budget_Table")
fin = fin[fin["Project Code"].notna() & fin["Project Code"].astype(str).str.startswith("UNIDO")].copy()
fin["Project Code"] = fin["Project Code"].astype(str).str.strip()

rat = pd.read_excel(RAT_XLSX, sheet_name="2_Project_Ratings_Matrix")
rat = rat[rat["Project Code"].notna() & rat["Project Code"].astype(str).str.startswith("UNIDO")].copy()
rat["Project Code"] = rat["Project Code"].astype(str).str.strip()
rat["Project Code"] = rat["Project Code"].replace("UNIDO-30310", "UNIDO-130310")

merged = fin.merge(
    rat[["Project Code","Short Title","Overall",
         "Relevance","Coherence","Effectiveness","Efficiency","Impact","Sustainability"]],
    on="Project Code", how="left"
)

# ── PDF filename map ───────────────────────────────────────────────────────────
FILE_MAP = {
    "UNIDO-100321": "2021/EvalRep_AZE-100321_HCFC_Phase_out_TE-2021.pdf",
    "UNIDO-104112": "2021/EvalRep_UKR-104112_RECP_TE-2020.pdf",
    "UNIDO-100043": "2021/GFSRL-100043_TE_Report_2020_E.pdf.pdf",
    "UNIDO-120323": "2021/GF_ID-4890_GFURU-120323_TE_Report_2020_E.pdf.pdf",
    "UNIDO-140307": "2022/EvalRep_GLO-140307-5832_CTCN_TE-2020.pdf",
    "UNIDO-100260": "2022/Evaluation report on Mini-grid based renewable energy (biomass) sources to augment rural electrification in Nigeria (2022).pdf",
    "UNIDO-130149": "2022/Evaluation report on Promoting business models for increasing penetration and scaling-up of solar energy in India (2022).pdf",
    "UNIDO-190036": "2022/Evaluation report on Strengthening capacity for operation and maintenance with Internet of Things technologies in Kenya (2022).pdf",
    "UNIDO-150033": "2022/Evaluation report on the Demonstration of BAT and BEP in open burning activities in response to the Stockholm Convention on POPs.pdf",
    "UNIDO-120601": "2022/Evaluation report on the Low Carbon Low Emission Clean Energy Technology Transfer Programme (2022).pdf",
    "UNIDO-150049": "2023/Evaluation report on Development and Implementation of a Sustainable Management Mechanism for POPs in the Caribbean (UNIDO project No. 150049).pdf",
    "UNIDO-140019": "2023/Evaluation report on Environmentally Sound Management and Final Disposal of PCBs at the Russian Railways network and other PCB owners (Phase I).pdf",
    "UNIDO-104044": "2023/Evaluation report on Environmentally Sound Management and Final Disposal of PCBs in India.pdf",
    "UNIDO-100313": "2023/Evaluation report on Environmentally Sound Management and Final Disposal of PCBs in Serbia.pdf",
    "UNIDO-140160": "2023/Evaluation report on Environmentally Sound Management and Final Disposal of PCBs in the Republic of Congo.pdf",
    "UNIDO-140298": "2023/Evaluation report on Environmentally sound management and disposal of PCB-containing equipment and disposal of DDT wastes, upgrade of techn. expertise.pdf",
    "UNIDO-140296": "2023/Evaluation report on Environmentally sound management of PCB-containing equipment and wastes and upgrade of technical expertise in Bolivia.pdf",
    "UNIDO-104160": "2023/Evaluation report on Environmentally sound management of medical wastes in India (2023).pdf",
    "UNIDO-100114": "2023/Evaluation report on Environmentally sound management of municipal and hazardous solid saste to reduce emissions of unintentional POPs in Senegal.pdf",
    "UNIDO-140276": "2023/Evaluation report on First operational phase of the Pacific Centre for Renewable Energy and Energy Efficiency.pdf",
    "UNIDO-120264": "2023/Evaluation report on GHG emissions reductions in targeted industrial sub-sectors through EE and application of solar thermal systems in Malaysia.pdf",
    "UNIDO-150346": "2023/Evaluation report on Hosting and Managing Private Financing Advisory Network.pdf",
    "UNIDO-120094": "2023/Evaluation report on Increased energy access for productive use through small hydropower development in rural areas in Madagascar.pdf",
    "UNIDO-120487": "2023/Evaluation report on Industrial energy efficiency improvement in South Africa.pdf",
    "UNIDO-170117": "2023/Evaluation report on Making polychlorinated biphenyls management and elimination sustainable in Morocco.pdf",
    "UNIDO-140157": "2023/Evaluation report on PCB Management and Disposal at the Energy Sector.pdf",
    "UNIDO-103029": "2023/Evaluation report on Promoting energy efficiency and renewable energy in selected micro, small and medium enterprise (MSME) clusters in India.pdf",
    "UNIDO-120335": "2023/Evaluation report on Promoting integrated biomass and small hydro solutions for productive uses in Cameroon.pdf",
    "UNIDO-130310": "2023/Evaluation report on Promoting organic waste-to-energy and other low-carbon technologies in SMMEs_Accelerating biogas market dev. in South Africa.pdf",
    "UNIDO-100122": "2023/Evaluation report on Removal of technical and economic barriers to initiating the clean-up activities for contaminated sites at OHIS.pdf",
    "UNIDO-130200": "2023/Evaluation report on Start-up and first operational phase of the Caribbean Centre for Renewable Energy and Energy Efficiency (CCREEE).pdf",
    "UNIDO-100288": "2023/Evaluation report on Stimulating industrial competitiveness through biomass-based, grid connected electricity generation in the Domini.pdf",
    "UNIDO-100045": "2023/Evaluation report on Sustainable Energy Initiative for Industries in Pakistan.pdf",
    "UNIDO-150270": "2023/Evaluation report on Sustainable cities management initiative for Senegal.pdf",
    "UNIDO-120568": "2023/Evaluation report on Sustainable conversion of waste to clean energy for Greenhouse Gas (GHG) emission reduction.pdf",
    "UNIDO-120073": "2023/Evaluation report on Utilizing solar energy for industrial process heat in Egyptian industry.pdf",
    "UNIDO-150259": "2023/Evaluation report on the H2O Maghreb in Morocco (2023).pdf",
    "UNIDO-150157": "2023/Evaluation report on the Integrated adoption of new energy vehicles in China (2023).pdf",
    "UNIDO-190106": "2023/Evaluation report on the Renewable Energy (PARE) project (2023).pdf",
    "UNIDO-PCB-CLUSTER-001": "2023/Final report on the independent terminal evaluation of a cluster of UNIDO polychlorinated biphenyls (PCPs) projects.pdf",
    "UNIDO-150050": "2024/Evaluation report on Environmentally sound management of PCB wastes and PCB-contaminated equipment in Sri Lanka.pdf",
    "UNIDO-170046": "2024/Evaluation report on Generating energy capacity from geothermal power generation and its related technologies for sustainable development.pdf",
    "UNIDO-230030": "2024/Evaluation report on Industrial capacity-building, policy advice and diagnostics for the green recovery of Ukraine.pdf",
    "UNIDO-130249": "2024/Evaluation report on Introduction of an environmentally sound management and disposal system for PCB wastes and PCB decontaminated equipmentpdf.pdf",
    "UNIDO-150052": "2024/Evaluation report on Mainstreaming climate change adaptation through water resource management in leather industrial zone development in Pakistan.pdf",
    "UNIDO-180228": "2024/Evaluation report on SwitchMed II (UNIDO project No 180228).pdf",
    "UNIDO-150263": "2024/Evaluation report on Towards sustainable energy for all in Mozambique.pdf",
    "UNIDO-140196": "2024/Evaluation report on Upgrading of China small hydropower (SHP) capacity.pdf",
    "UNIDO-140297": "2025/Evaluation report on Strengthening national initiatives and enhancement of reg. coop. for environmentally sound management of POPs in WEEE in LAC countries_F-250612.pdf",
    "UNIDO-150046": "2025/Evaluation report on Sustainable-city development in Malaysia.pdf",
    "UNIDO-150186": "2025/Evaluation_report_on_Greening_of_scrap_metal_value_chain_through_the_promotion_of_BAT-BEP_to_reduce_U-POPs_releases_from_recycling_facilities_in_Thailand.pdf",
}

# ── Lookup tables ──────────────────────────────────────────────────────────────
THEME_MAP = {
    "Circular Economy":               "Circular Economy / Waste Management",
    "Chemicals & POPs":               "Chemicals & POPs",
    "Climate Action / Mitigation":    "Climate Action",
    "Climate Adaptation":             "Climate Action",
    "Clean Energy / Renewable Energy":"Clean / Renewable Energy",
    "Energy Efficiency":              "Energy Efficiency",
    "Waste Management":               "Circular Economy / Waste Management",
    "Cross-cutting":                  "Industrial Policy & Competitiveness",
}

REGION_MAP = {
    "Europe & CIS":                       "Europe",
    "Asia-Pacific":                       "Asia",
    "Sub-Saharan Africa":                 "Africa",
    "Sub-Saharan Africa / North Africa":  "Africa",
    "Latin America & Caribbean":          "Latin America",
    "Arab States / MENA":                 "Middle East",
    "Global / Multi-region":              "Global",
}

RATING_MAP = {"HS": 6.0, "S": 5.0, "MS": 4.0, "MU": 3.0, "U": 2.0, "HU": 1.0}

THEME_SDGS = {
    "Chemicals & POPs":                    [3, 12, 13],
    "Energy Efficiency":                   [7, 9, 13],
    "Clean / Renewable Energy":            [1, 7, 13],
    "Climate Action":                      [9, 11, 13],
    "Circular Economy / Waste Management": [11, 12, 13],
    "Water & Environment":                 [6, 9, 13],
    "Digital Innovation":                  [9, 17],
    "Industrial Policy & Competitiveness": [9, 11, 13],
}

EVAL_TYPE_MAP = {"UNIDO-PCB-CLUSTER-001": "Synthesis"}


def clean_donor(d):
    if pd.isna(d): return "GEF"
    d = str(d)
    if "GEF" in d or "Global Environment Facility" in d: return "GEF"
    if "Japan" in d: return "Government of Japan"
    if "European Union" in d or d.strip() == "EU": return "EU"
    if "USAID" in d: return "USAID"
    if "Germany" in d or "BMZ" in d: return "Germany BMZ"
    if "SECO" in d or "Switzerland" in d: return "SECO"
    if "," in d or "Multiple" in d.lower() or "Austrian" in d: return "Multi-donor"
    return d.split("(")[0].strip()


def get_dac(row):
    cols = ["Relevance","Coherence","Effectiveness","Efficiency","Impact","Sustainability"]
    out = [c for c in cols if pd.notna(row.get(c)) and str(row.get(c,"")).strip() not in ("","nan")]
    return out if out else ["Relevance","Effectiveness","Efficiency","Impact","Sustainability"]


# ── Build entries ─────────────────────────────────────────────────────────────
entries = []
for _, row in merged.iterrows():
    code = str(row["Project Code"]).strip()
    fn = FILE_MAP.get(code)
    if not fn:
        print(f"  WARN: no filename for {code}", file=sys.stderr)
        continue

    raw_theme = str(row.get("Theme","") or "").strip()
    thematic  = THEME_MAP.get(raw_theme, "Industrial Policy & Competitiveness")
    sdgs      = list(THEME_SDGS.get(thematic, [9, 17]))

    country = str(row.get("Country","") or "").strip()
    # Multi-country/global projects get SDG 17 (partnerships)
    if any(k in country for k in [",","Global","Caribbean","Pacific","Latin America"]):
        if 17 not in sdgs:
            sdgs.append(17)

    raw_region = str(row.get("Region","") or "").strip()
    region = REGION_MAP.get(raw_region, "Global")

    overall = str(row.get("Overall","") or "").strip()
    rating  = RATING_MAP.get(overall, None)

    year_raw = row.get("Eval Year")
    year = int(year_raw) if pd.notna(year_raw) else None

    budget_raw = row.get("TOTAL PROJECT COST $")
    budget = round(float(budget_raw)) if pd.notna(budget_raw) else None

    entry = {
        "report_id":         code,
        "title":             str(row.get("Project Title","") or "").strip(),
        "filename":          fn,
        "year":              year,
        "country":           country,
        "region":            region,
        "thematic_category": thematic,
        "dac_criteria":      get_dac(row),
        "sdgs":              sorted(set(sdgs)),
        "evaluation_type":   EVAL_TYPE_MAP.get(code, "Project Evaluation"),
        "donor":             clean_donor(row.get("Donor")),
        "project_id":        code,
        "evaluation_rating": rating,
        "budget_usd":        budget,
    }
    entries.append(entry)

print(f"Built {len(entries)} entries", file=sys.stderr)

# ── Reference documents (keep at top) ─────────────────────────────────────────
ref_docs = [
    {
        "report_id": "ref-uneg-synthesis-guidelines",
        "title": "UNEG Guidance on Evaluation Synthesis",
        "filename": "UNEG_Synthesis_Guidelines.pdf",
        "year": 2016,
        "country": "Global",
        "region": "Global",
        "thematic_category": "Digital Innovation",
        "dac_criteria": ["Relevance","Effectiveness","Impact"],
        "sdgs": [17],
        "evaluation_type": "Reference Document",
        "donor": "UNEG",
        "project_id": "",
        "evaluation_rating": None,
        "budget_usd": None,
    },
    {
        "report_id": "ref-ai-ethics-un-evaluation",
        "title": "Ethical Principles for Using AI in UN Evaluation",
        "filename": "AI_Ethics_UN_Evaluation.pdf",
        "year": 2023,
        "country": "Global",
        "region": "Global",
        "thematic_category": "Digital Innovation",
        "dac_criteria": [],
        "sdgs": [16, 17],
        "evaluation_type": "Reference Document",
        "donor": "UNEG",
        "project_id": "",
        "evaluation_rating": None,
        "budget_usd": None,
    },
]

all_entries = ref_docs + entries

# ── Write YAML ─────────────────────────────────────────────────────────────────
header = """\
# ═══════════════════════════════════════════════════════════════════════════════
# UNIDO IEU Evaluation Reports — Metadata Configuration
# Generated from: UNIDO_Financial_Overview_with_Analytics.xlsx + Ratings_Summary.xlsx
# 51 evaluation reports + 2 reference documents = 53 total
#
# Thematic categories:
#   Energy Efficiency | Clean / Renewable Energy | Climate Action |
#   Circular Economy / Waste Management | Chemicals & POPs |
#   Industrial Policy & Competitiveness | Trade & Standards |
#   Agro-Industry & Food Systems | Water & Environment |
#   Gender & Inclusion | Digital Innovation
#
# Region: Africa | Asia | Europe | Latin America | Middle East | Global
# evaluation_type: Project Evaluation | Synthesis | Reference Document
# evaluation_rating: 6=HS 5=S 4=MS 3=MU 2=U 1=HU  (null = not rated)
# ═══════════════════════════════════════════════════════════════════════════════

"""

OUT_YAML.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_YAML, "w", encoding="utf-8") as f:
    f.write(header)
    yaml.dump({"reports": all_entries}, f,
              default_flow_style=False, allow_unicode=True,
              sort_keys=False)

print(f"Written: {OUT_YAML}", file=sys.stderr)
