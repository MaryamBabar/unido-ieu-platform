"""
UNIDO IEU Evaluation Intelligence Platform
4-tab Streamlit frontend:
  Tab 1 — Search & Browse   (filter reports, view lessons/recommendations, Excel export)
  Tab 2 — Synthesis         (RAG search across selected reports)
  Tab 3 — Visualize         (portfolio charts via Plotly)
  Tab 4 — OECD-DAC          (DAC criteria evidence browser + radar chart)
  Admin  — User management  (admin only)
"""

import io
import os
import re
import json
import base64
import httpx
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

def get_backend_url() -> str:
    try:
        if "BACKEND_URL" in st.secrets:
            return st.secrets["BACKEND_URL"]
    except Exception:
        pass
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
    return os.getenv("BACKEND_URL", "http://localhost:8000")

BACKEND_URL = get_backend_url()

st.set_page_config(
    page_title="UNIDO Evaluation Intelligence Platform",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# SDG data — official UN colours + names
# ─────────────────────────────────────────────────────────────────────────────

SDG_COLORS = {
    1: "#E5243B", 2: "#DDA63A", 3: "#4C9F38", 4: "#C5192D", 5: "#FF3A21",
    6: "#26BDE2", 7: "#FCC30B", 8: "#A21942", 9: "#FD6925", 10: "#DD1367",
    11: "#FD9D24", 12: "#BF8B2E", 13: "#3F7E44", 14: "#0A97D9", 15: "#56C02B",
    16: "#00689D", 17: "#19486A",
}

SDG_NAMES = {
    1: "No Poverty", 2: "Zero Hunger", 3: "Good Health", 4: "Quality Education",
    5: "Gender Equality", 6: "Clean Water", 7: "Affordable Energy", 8: "Decent Work",
    9: "Industry & Innovation", 10: "Reduced Inequalities", 11: "Sustainable Cities",
    12: "Responsible Consumption", 13: "Climate Action", 14: "Life Below Water",
    15: "Life on Land", 16: "Peace & Justice", 17: "Partnerships",
}

# ─────────────────────────────────────────────────────────────────────────────
# SDG icon images — load from frontend/assets/sdg_01.png … sdg_17.png as base64
# Falls back to CSS colored tile if image file not found
# ─────────────────────────────────────────────────────────────────────────────

_ASSETS_DIR = Path(__file__).parent / "assets"
_SDG_B64: dict = {}

def _load_sdg_images():
    for n in range(1, 18):
        p = _ASSETS_DIR / f"sdg_{n:02d}.png"
        if p.exists():
            _SDG_B64[n] = base64.b64encode(p.read_bytes()).decode()

_load_sdg_images()


def sdg_badge_html(n: int, size: int = 36) -> str:
    """Real PNG icon if available, CSS colored tile as fallback."""
    title = f"SDG {n}: {SDG_NAMES.get(n, '')}"
    if n in _SDG_B64:
        return (
            f'<img src="data:image/png;base64,{_SDG_B64[n]}" '
            f'title="{title}" '
            f'style="width:{size}px;height:{size}px;border-radius:4px;margin:2px;'
            f'vertical-align:middle;object-fit:cover;" />'
        )
    # CSS fallback
    color = SDG_COLORS.get(n, "#888")
    font_size = max(9, size // 3)
    return (
        f'<span title="{title}" '
        f'style="display:inline-flex;align-items:center;justify-content:center;'
        f'width:{size}px;height:{size}px;background:{color};color:white;font-weight:800;'
        f'border-radius:4px;font-size:{font_size}px;margin:2px;vertical-align:middle;'
        f'font-family:Arial,sans-serif;letter-spacing:-0.5px;">{n}</span>'
    )


def sdg_badges_row(sdg_list: list, size: int = 32) -> str:
    return "".join(sdg_badge_html(n, size) for n in sorted(sdg_list) if 1 <= n <= 17)

# ─────────────────────────────────────────────────────────────────────────────
# DAC criteria
# ─────────────────────────────────────────────────────────────────────────────

DAC_CRITERIA = ["relevance", "effectiveness", "efficiency", "impact", "sustainability"]
DAC_COLORS   = ["#009EDB", "#4CAF50", "#FF9800", "#E91E63", "#9C27B0"]
DAC_LABELS   = ["Relevance", "Effectiveness", "Efficiency", "Impact", "Sustainability"]

THEMATIC_AREAS = [
    "Energy Efficiency", "Clean / Renewable Energy", "Climate Action",
    "Circular Economy / Waste Management", "Chemicals & POPs",
    "Industrial Policy & Competitiveness", "Trade & Standards",
    "Agro-Industry & Food Systems", "Water & Environment",
    "Gender & Inclusion", "Digital Innovation",
]

# ── Pilot report metadata (source of truth — overrides backend/Qdrant) ───────
PILOT_METADATA: dict[str, dict] = {
    "UNIDO-100043": {
        "project_id":          "100043",
        "title":               "Independent Terminal Evaluation: The Project \"Bamboo Processing for Sri Lanka\"",
        "year":                2021,
        "country":             "Sri Lanka",
        "region":              "Asia and the Pacific",
        "thematic_category":   "Agro-Industry & Food Systems",
        "secondary_thematic_area": "Circular Economy / Waste Management",
        "report_type":         "Project Evaluation",
        "donor":               "GEF",
        "budget_usd":          23652000,
        "evaluation_rating":   2.0,
        "overall_rating_label":"Unsatisfactory",
        "sdgs":                [8, 12, 15],
        "thematic_justification": (
            "The project focused on developing the bamboo value chain as an agro-industrial sector, "
            "supporting smallholder farmers and SMEs in the processing and commercialization of "
            "bamboo-based products as a sustainable alternative to timber. Its core activities centred "
            "on agro-industry capacity building, technology transfer for bamboo processing equipment, "
            "and market development for agricultural value-added products."
        ),
        "sdg_justifications": {
            "8":  "The project aimed to create employment and income for smallholder bamboo farmers and processing enterprises in rural Sri Lanka, directly contributing to SDG 8 (Decent Work and Economic Growth) through agro-industrial value chain development.",
            "12": "By promoting bamboo as a renewable, fast-growing alternative to timber and conventional inputs, the project advanced responsible consumption and production patterns (SDG 12) in the construction, handicraft, and packaging industries.",
            "15": "Bamboo cultivation and plantation management conserves soil, reduces erosion, and provides an alternative to unsustainable timber extraction, contributing to SDG 15 (Life on Land) through sustainable forestry and land-use practices in Sri Lanka.",
        },
        "lessons_learned": [
            "Thorough feasibility and market studies must be completed before project design is finalised — the Sri Lanka bamboo project suffered from overestimated market demand and insufficient baseline data on bamboo resource availability.",
            "Private sector buy-in and co-financing commitments should be secured prior to project start. Over-reliance on small-scale farmers without commercial processing partners limited the project's ability to achieve value chain scale.",
            "Adaptive management mechanisms must be built into project design: when market conditions diverge significantly from projections, project teams need explicit authority and resources to redesign activities mid-course.",
            "Technology transfer activities are only effective when accompanied by sustained market linkage support. Providing processing equipment without ensuring buyers and commercial relationships undermined enterprise viability.",
            "Realistic sustainability planning requires honest assessment of cost recovery potential. Processing enterprises could not achieve financial break-even at projected volumes, indicating project design assumptions were overly optimistic.",
        ],
        "recommendations": [
            "UNIDO and GEF should commission a comprehensive post-project market assessment to determine whether commercial bamboo processing viability has improved sufficiently to justify a follow-on phase with restructured value chain support.",
            "The National Bamboo Committee should establish a dedicated market development function, focused on connecting processing enterprises with domestic and export buyers, as a condition for any future phase of bamboo sector support.",
            "Future agro-industry projects in Sri Lanka should require binding private sector co-financing agreements — not in-kind or contingent contributions — before project approval, to ensure genuine commercial interest and shared financial risk.",
            "UNIDO should integrate systematic adaptive management reviews at 18-month intervals in complex agro-industry projects, with explicit decision gates allowing activity redesign when market assumptions prove incorrect.",
            "The Government of Sri Lanka should establish a bamboo sector monitoring system within the Ministry of Agriculture to track plantation area, processing enterprise performance, and market offtake independently of donor project support.",
        ],
    },
    "UNIDO-100321": {
        "project_id":          "100321",
        "title":               "Independent Terminal Evaluation: Initiation of the HCFC Phase Out in the Republic of Azerbaijan",
        "year":                2021,
        "country":             "Azerbaijan",
        "region":              "Europe and Central Asia",
        "thematic_category":   "Chemicals & POPs",
        "secondary_thematic_area": "Climate Action",
        "report_type":         "Project Evaluation",
        "donor":               "GEF",
        "budget_usd":          9170000,
        "evaluation_rating":   5.0,
        "overall_rating_label":"Satisfactory",
        "sdgs":                [12, 13, 17],
        "thematic_justification": (
            "The project directly targeted the phase-out of hydrochlorofluorocarbons (HCFCs) — "
            "ozone-depleting and high global warming potential substances — under the Montreal Protocol "
            "and the Multilateral Fund. This positions it firmly in the Chemicals & POPs thematic area, "
            "involving import/export controls, customs training, refrigerant conversion in enterprises, "
            "and institutional strengthening for chemical substance management in Azerbaijan."
        ),
        "sdg_justifications": {
            "12": "The project phased out HCFCs in the refrigeration, air conditioning, and foam sectors of Azerbaijan, replacing them with ozone- and climate-friendly alternatives, directly advancing SDG 12 (Responsible Consumption and Production) by eliminating harmful substances from industrial processes.",
            "13": "HCFCs are potent greenhouse gases in addition to being ozone-depleting substances. By phasing them out and transitioning enterprises to low-GWP refrigerants, the project contributes to SDG 13 (Climate Action) through measurable reductions in greenhouse gas emissions.",
            "17": "The project was implemented under the Multilateral Fund for the Implementation of the Montreal Protocol — a flagship example of global partnership. It relied on international technology transfer and multi-stakeholder coordination, directly embodying SDG 17 (Partnerships for Goals).",
        },
        "lessons_learned": [
            "Effective HCFC phase-out requires early and sustained investment in customs officer training and enforcement capacity — without this, import controls remain ineffective regardless of regulatory frameworks in place.",
            "Strong government ownership and institutional embedding of phase-out management structures are the most reliable predictors of long-term programme sustainability beyond project closure.",
            "Enterprise recruitment and conversion timelines are consistently underestimated in phase-out projects; building in flexible implementation schedules and contingency for enterprise mobilisation delays significantly improves delivery.",
            "South-South cooperation and regional experience sharing among Montreal Protocol parties accelerates learning and reduces the cost of technology conversion by enabling beneficiary countries to learn from peers who have already undertaken similar transitions.",
            "Verification and monitoring systems for phase-out achievement must be designed to be maintained by national counterparts after project completion; systems that depend on international consultants are not sustainable.",
        ],
        "recommendations": [
            "The Azerbaijan government should sustain the customs enforcement and HCFC monitoring system established under the project by integrating it into routine operations of the State Customs Committee with dedicated staffing and budget.",
            "UNIDO and the Multilateral Fund should ensure that Azerbaijan's HCFC Phase-Out Management Plan (HPMP) Stage II builds directly on enterprise conversion data and lessons from Stage I, avoiding duplication and building on established relationships.",
            "The Ministry of Ecology and Natural Resources should expand the HCFC licensing and quota system to cover all identified importers and distributors, closing regulatory gaps identified during Stage I implementation.",
            "Future Montreal Protocol projects in similar economies should build enterprise verification mechanisms that can be operated by national inspectorates without international consultant support from the start of implementation.",
            "UNIDO should support Azerbaijan in developing refrigerant recovery and recycling infrastructure as a priority in subsequent programme stages, addressing the long-term management of phased-out substances currently lacking end-of-life pathways.",
        ],
    },
    "UNIDO-104112": {
        "project_id":          "104112",
        "title":               "Independent Terminal Evaluation: Promoting the Adaptation and Adoption of RECP (Resource Efficient and Cleaner Production) Through the Establishment and Operation of a Cleaner Production Centre (CPC) in Ukraine",
        "year":                2021,
        "country":             "Ukraine",
        "region":              "Europe and Central Asia",
        "thematic_category":   "Circular Economy / Waste Management",
        "secondary_thematic_area": "Industrial Policy & Competitiveness",
        "report_type":         "Project Evaluation",
        "donor":               "Switzerland (SECO), Austria",
        "budget_usd":          5181779,
        "evaluation_rating":   5.0,
        "overall_rating_label":"Satisfactory",
        "sdgs":                [9, 12, 13, 17],
        "thematic_justification": (
            "The project established and operationalized Ukraine's National Cleaner Production Centre "
            "(CPC) to mainstream Resource-Efficient and Cleaner Production (RECP) methodologies across "
            "Ukrainian industry. RECP is the foundational framework of circular economy thinking in "
            "industrial contexts — reducing material inputs, minimising waste, improving energy "
            "efficiency, and preventing pollution at source."
        ),
        "sdg_justifications": {
            "9":  "By establishing the RECP Centre and providing technical assistance to enterprises across multiple industrial sub-sectors, the project fostered inclusive and sustainable industrialization (SDG 9), promoting innovation in production processes and infrastructure for clean technology adoption.",
            "12": "Resource-Efficient and Cleaner Production (RECP) is the operational methodology for achieving sustainable consumption and production (SDG 12) in industry. The project trained enterprises to reduce raw material consumption, minimize waste, and adopt more sustainable production patterns.",
            "13": "RECP assessments identified energy efficiency improvements and emission reduction opportunities. The adoption of cleaner production technologies directly reduces industrial greenhouse gas emissions, contributing to SDG 13 (Climate Action) at the enterprise and sectoral level.",
            "17": "The project was implemented through a partnership between UNIDO, Switzerland (SECO), and Austrian development cooperation alongside Ukrainian counterparts — a multi-donor, multi-stakeholder approach that exemplifies SDG 17 (Partnerships for the Goals).",
        },
        "lessons_learned": [
            "Embedding a national RECP Centre within an established host institution from project inception significantly increases institutional sustainability and reduces operational fragility compared to standalone project management units.",
            "Integration of RECP methodology into university curricula and vocational training systems creates long-term capacity that persists beyond project timeframes, multiplying impact through trained professionals entering industry.",
            "RECP assessments are most effective when enterprise participation is genuinely voluntary and demand-driven rather than supply-pushed; enterprises that self-select into the programme achieve higher implementation rates of identified improvements.",
            "Developing fee-for-service revenue models for RECP centres from an early stage of project implementation reduces dependence on donor funding and builds a commercially sustainable knowledge services market.",
            "Multi-donor programmes benefit from clear governance arrangements and defined roles between implementing partners at the outset; ambiguity in donor coordination creates delays and inconsistent reporting.",
        ],
        "recommendations": [
            "The Ukrainian RECP Centre should develop and implement a five-year financial sustainability plan that progressively reduces dependence on UNIDO project funding by growing fee-for-service revenues from RECP assessments and training services.",
            "UNIDO should support the RECP Centre in establishing a national RECP policy framework that mandates periodic environmental and resource efficiency audits for enterprises above a defined threshold, creating a sustained demand base for Centre services.",
            "The Ministry of Environmental Protection and Natural Resources of Ukraine should integrate RECP principles and indicators into national industrial development strategies and green economy action plans.",
            "Future RECP Centre projects should include a formal mentoring relationship with an established RECP Centre from a peer country from project inception, accelerating institutional learning and reducing the cost of establishing core competencies.",
            "UNIDO and donors should consider co-financing a green credit facility aligned with the RECP Centre to enable enterprises to finance the implementation of identified RECP improvements, converting assessments into measurable resource savings.",
        ],
    },
    "UNIDO-120323": {
        "project_id":          "GFURU-120323",
        "title":               "Independent Terminal Evaluation: Towards a Green Economy in Uruguay: Stimulating Sustainable Practices and Low-Emission Technologies in Prioritized Sectors",
        "year":                2021,
        "country":             "Uruguay",
        "region":              "Latin America",
        "thematic_category":   "Climate Action",
        "secondary_thematic_area": "Clean / Renewable Energy",
        "report_type":         "Project Evaluation",
        "donor":               "GEF",
        "budget_usd":          30500000,
        "evaluation_rating":   5.0,
        "overall_rating_label":"Satisfactory",
        "sdgs":                [7, 9, 12, 13, 17],
        "thematic_justification": (
            "The project's primary objective was to stimulate the adoption of sustainable practices "
            "and low-emission technologies in key Uruguayan industrial and agricultural sectors, "
            "with a direct focus on reducing greenhouse gas emissions and transitioning towards a "
            "green economy. This encompasses renewable energy deployment, energy efficiency in "
            "industry, and low-carbon production methods — placing it in the Climate Action theme."
        ),
        "sdg_justifications": {
            "7":  "The project supported deployment of renewable energy technologies — including solar, wind, and biomass — in prioritized sectors in Uruguay, contributing to SDG 7 (Affordable and Clean Energy) by increasing the share of renewables and reducing fossil fuel dependence.",
            "9":  "By providing technical assistance and financing to enterprises adopting low-emission technologies and cleaner production methods, the project promoted sustainable industrialization and innovation (SDG 9) across Uruguay's priority industrial and agro-industrial sectors.",
            "12": "The project stimulated adoption of sustainable production practices — including resource efficiency improvements, waste reduction, and clean technology adoption — advancing responsible consumption and production patterns (SDG 12) at enterprise and sectoral level.",
            "13": "Low-emission technology deployment in industry directly reduces Uruguay's greenhouse gas emissions. The project contributes to SDG 13 (Climate Action) by demonstrating viable industrial decarbonization pathways and providing evidence for national climate policy.",
            "17": "Funded by GEF and implemented through UNIDO in partnership with Uruguay's Ministry of Environment and Ministry of Industry — with multiple private sector actors — this project exemplifies the multi-stakeholder partnerships of SDG 17 (Partnerships for the Goals).",
        },
        "lessons_learned": [
            "Flexible programme design that allows resource reallocation between technology tracks — based on demonstrated uptake and market readiness — significantly outperforms rigid activity plans in complex multi-technology green economy programmes.",
            "Establishing financial mechanisms (green credit lines, revolving funds) early in project implementation rather than at mid-term is critical, as financial instrument setup requires longer lead times than physical technology demonstrations.",
            "Robust baseline data collection on energy consumption and emissions at the enterprise level is essential for demonstrating project impact; without reliable baselines, attribution of GHG reductions to project interventions is contested.",
            "Strong alignment between project objectives and national policy commitments — such as Nationally Determined Contributions — creates political ownership that sustains programme momentum through administrative transitions.",
            "Private sector co-financing commitments in green technology projects are most successfully mobilized when complemented by risk-reduction instruments; grants alone do not address the financial barriers to first-mover technology adoption.",
        ],
        "recommendations": [
            "The Government of Uruguay should embed the green economy financial mechanisms established under this project — particularly the green credit line — within permanent public financial institution operations to ensure their continuity beyond GEF funding.",
            "UNIDO should support Uruguay in developing a national green economy monitoring framework with standardised enterprise-level energy and emissions reporting, enabling accurate tracking of NDC contributions from the industrial sector.",
            "Future GEF green economy programmes in upper-middle-income countries should prioritise catalytic financial instruments over grant-based technology subsidies, recognising that the primary barrier is financial risk rather than technology availability.",
            "The Ministry of Industry of Uruguay should use evidence from this project's technology demonstrations to update sectoral energy efficiency standards and incentive frameworks, institutionalising the transition to low-emission technologies.",
            "UNIDO and GEF should explore a programmatic approach to green economy support in Latin America that enables Uruguay and peer countries to share technology assessment data, financing instruments, and market development lessons across country boundaries.",
        ],
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
  :root {
    --blue: #009EDB; --dark: #1a1a2e; --bg: #f5f7fa;
    --muted: #6b7280; --border: #e5e7eb;
    --danger: #ef4444; --success: #22c55e; --amber: #f59e0b;
  }
  #MainMenu, footer, header { visibility: hidden; }
  .main .block-container {
    padding-top: 1rem; padding-bottom: 2rem;
    max-width: 100% !important; padding-left: 1.5rem; padding-right: 1.5rem;
  }
  /* Remove extra top padding Streamlit adds above columns */
  div[data-testid="stVerticalBlock"] > div { gap: 0.4rem; }
  /* Tighten column gaps */
  div[data-testid="stHorizontalBlock"] { gap: 0.5rem; }

  .unido-header {
    background: white; border-bottom: 2px solid var(--blue);
    padding: 0.8rem 1.5rem; margin: -1.2rem -1rem 1.2rem -1rem;
    display: flex; align-items: center; justify-content: space-between;
  }
  .unido-logo { font-size: 1.3rem; font-weight: 700; color: var(--blue); }
  .unido-sub  { font-size: 0.85rem; color: var(--muted); }
  .user-chip  {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 999px; padding: 0.3rem 0.9rem;
    font-size: 0.82rem; color: var(--dark);
  }

  /* Login */
  .login-wrap { max-width: 400px; margin: 3rem auto; }
  .login-logo { text-align:center; margin-bottom: 1.5rem; }
  .login-logo .big { font-size: 2rem; font-weight: 700; color: var(--blue); }
  .login-logo .sub { color: var(--muted); font-size: 0.85rem; }

  /* Report cards */
  .report-card {
    background: white; border: 1px solid var(--border);
    border-radius: 10px; padding: 1.1rem 1.3rem; margin-bottom: 0.5rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.07);
    border-top: 3px solid var(--blue);
    transition: box-shadow 0.15s ease;
  }
  .report-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.12); }
  .report-title { font-weight: 700; color: var(--dark); font-size: 0.92rem; line-height:1.45; margin-bottom:0.3rem; }
  .report-meta  { color: var(--muted); font-size: 0.76rem; margin: 0.1rem 0 0.35rem; }
  .tag {
    display: inline-block; border-radius: 999px; font-size: 0.72rem;
    font-weight: 600; padding: 0.15rem 0.55rem; margin: 2px;
  }
  .tag-blue  { background: #e0f2fe; color: #0369a1; }
  .tag-green { background: #dcfce7; color: #166534; }
  .tag-amber { background: #fef3c7; color: #92400e; }
  .tag-gray  { background: #f3f4f6; color: #374151; }
  .tag-purple { background: #f3e8ff; color: #6d28d9; }

  /* Rating badge */
  .rating-pill {
    display:inline-flex; align-items:center; gap:4px;
    border-radius:999px; font-size:0.72rem; font-weight:700;
    padding:0.18rem 0.6rem; margin:2px;
  }
  .rating-high   { background:#dcfce7; color:#166534; }
  .rating-mid    { background:#fef3c7; color:#92400e; }
  .rating-low    { background:#fee2e2; color:#991b1b; }
  .rating-none   { background:#f3f4f6; color:#6b7280; }

  /* Passage cards */
  .passage-card {
    background: var(--bg); border-left: 3px solid var(--blue);
    border-radius: 0 6px 6px 0; padding: 0.8rem 1rem;
    margin-bottom: 0.5rem; font-size: 0.87rem;
  }
  .passage-title { font-weight: 600; color: var(--dark); font-size: 0.85rem; }
  .passage-meta  { color: var(--muted); font-size: 0.77rem; margin-bottom: 0.35rem; }
  .passage-text  { color: #374151; line-height: 1.55; }
  .score-pill {
    display: inline-block; background: #e0f2fe; color: #0369a1;
    font-size: 0.72rem; font-weight: 600; border-radius: 999px;
    padding: 0.1rem 0.45rem; margin-left: 0.4rem;
  }

  /* DAC evidence */
  .dac-card {
    background: white; border: 1px solid var(--border);
    border-radius: 6px; padding: 0.9rem 1.1rem; margin-bottom: 0.5rem;
  }
  .dac-quote {
    border-left: 3px solid var(--blue); padding-left: 0.8rem;
    color: #374151; font-size: 0.86rem; line-height: 1.55;
    font-style: italic;
  }

  /* Stat cards */
  .stat-card {
    background: white; border: 1px solid var(--border); border-radius: 8px;
    padding: 1.2rem; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  }
  .stat-num  { font-size: 2rem; font-weight: 700; color: var(--blue); }
  .stat-lbl  { color: var(--muted); font-size: 0.8rem; margin-top: 0.2rem; }

  /* Sidebar */
  [data-testid="stSidebar"] { background: white; border-right: 1px solid var(--border); }
  [data-testid="stSidebar"] .stMarkdown h3 {
    color: var(--dark); font-size: 0.78rem; text-transform: uppercase;
    letter-spacing: 0.05em; font-weight: 600; margin-top: 1rem;
  }

  /* User mgmt */
  .role-badge { display:inline-block; padding:.15rem .6rem; border-radius:999px; font-size:.72rem; font-weight:600; }
  .role-admin { background:#fef3c7; color:#92400e; }
  .role-user  { background:#e0f2fe; color:#0369a1; }
  .dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:5px; }
  .dot-green { background:var(--success); }
  .dot-red   { background:var(--danger); }
  .dot-amber { background:var(--amber); }

  [data-testid="baseButton-primary"] {
    background-color: var(--blue) !important;
    border-color: var(--blue) !important;
  }
  .stButton > button {
    border-radius: 6px;
    font-size: 0.8rem;
    padding: 0.3rem 0.85rem;
  }

  /* Tight button row — correct Streamlit selectors */
  div[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) {
    gap: 6px !important;
  }
  div[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) > div[data-testid="column"] {
    padding-left: 0 !important;
    padding-right: 0 !important;
    min-width: 0 !important;
    flex: 0 0 auto !important;
    width: auto !important;
  }
  div[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) > div[data-testid="column"]:last-child {
    flex: 1 1 auto !important;
  }
  div[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) .stButton > button,
  div[data-testid="stHorizontalBlock"]:has([data-testid="stButton"]) .stDownloadButton > button {
    white-space: nowrap !important;
    width: auto !important;
  }

  /* Card action buttons */
  .card-actions {
    display: flex; gap: 8px; margin-top: 0.5rem; margin-bottom: 0.2rem;
  }
  .action-btn {
    flex: 1; padding: 0.38rem 0.7rem; border-radius: 6px; font-size: 0.78rem;
    font-weight: 600; cursor: pointer; border: none; text-align: center;
    font-family: inherit;
  }
  .action-btn-outline {
    background: white; color: var(--dark); border: 1.5px solid var(--border);
  }
  .action-btn-outline:hover { border-color: var(--blue); color: var(--blue); }
  .action-btn-primary { background: var(--blue); color: white; }
  .action-btn-primary:hover { background: #007ab8; }
  .action-btn-ghost  { background: #f3f4f6; color: var(--dark); border: 1.5px solid transparent; }
  .action-btn-ghost:hover { background: #e5e7eb; }

  /* Pilot banner */
  .pilot-banner {
    background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px;
    padding: 0.6rem 1rem; margin-bottom: 1rem; font-size: 0.82rem; color: #1e40af;
  }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────────────────────

import time as _time

for k, v in {
    "session_token": "no-auth-bypass", "username": "guest",
    "display_name": "Guest", "role": "admin",
    "all_reports": None,
    "lessons_cache": {},
    "synth_history": [],
    "backend_healthy": None,
    "_page_load": 0,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Reset report cache when app restarts (new deployment / new session)
_deploy_ts = int(os.path.getmtime(__file__))
if st.session_state.get("_deploy_ts") != _deploy_ts:
    st.session_state["_deploy_ts"] = _deploy_ts
    st.session_state["all_reports"] = None  # force refresh on new deploy

# ─────────────────────────────────────────────────────────────────────────────
# API helpers
# ─────────────────────────────────────────────────────────────────────────────

def auth_headers() -> dict:
    return {"X-Session-Token": st.session_state.session_token or ""}

def api(method: str, path: str, **kw) -> httpx.Response:
    h = kw.pop("headers", {})
    h.update(auth_headers())
    return httpx.request(method, f"{BACKEND_URL}{path}", headers=h, timeout=45, **kw)

def load_reports(force: bool = False):
    if st.session_state.all_reports is None or force:
        # Pull from both sources and merge:
        # metadata.yaml → ratings, full titles, donor, budget
        # Qdrant list   → SDGs (not stored in metadata.yaml)
        meta_reports = load_metadata_reports()
        qdrant_reports: list[dict] = []
        try:
            r = api("GET", "/api/v1/reports/list")
            if r.status_code == 200:
                qdrant_reports = r.json().get("reports", [])
        except Exception:
            pass

        # Build SDG lookup from Qdrant
        sdg_by_rid = {r["report_id"]: r.get("sdgs") or [] for r in qdrant_reports}

        if meta_reports:
            # Use metadata.yaml as base; patch SDGs from Qdrant
            merged = []
            for rep in meta_reports:
                rid = rep.get("report_id", "")
                rep["sdgs"] = sdg_by_rid.get(rid) or rep.get("sdgs") or []
                merged.append(rep)
        else:
            # Fall back to Qdrant only
            merged = qdrant_reports

        # Apply pilot metadata overrides — guarantees correct titles/ratings
        # regardless of what Qdrant or the backend returns
        for rep in merged:
            rid = rep.get("report_id", "")
            if rid in PILOT_METADATA:
                rep.update(PILOT_METADATA[rid])

        # Always ensure the 4 pilot reports are present even if backend is unreachable
        existing_ids = {r.get("report_id") for r in merged}
        for rid, meta in PILOT_METADATA.items():
            if rid not in existing_ids:
                merged.append({"report_id": rid, **meta})

        st.session_state.all_reports = sorted(
            merged, key=lambda r: r.get("year") or 0, reverse=True
        )

def load_lessons(report_ids: list[str]) -> list[dict]:
    try:
        r = api("GET", "/api/v1/lessons", params={"report_ids": ",".join(report_ids)})
        return r.json().get("reports", []) if r.status_code == 200 else []
    except Exception:
        return []

def _load_sections_local(report_id: str) -> dict:
    """Load extracted sections directly from local JSON file (no backend needed).
    Works on Streamlit Cloud since data/ is in the git repo."""
    import pathlib
    p = pathlib.Path(__file__).parent.parent / "data" / "extracted_sections" / f"{report_id}.json"
    if p.exists():
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def load_sections(report_id: str) -> dict | None:
    """Load pre-extracted PDF sections — tries local file first, then backend API."""
    # Try local file first (faster, works on Streamlit Cloud)
    local = _load_sections_local(report_id)
    if local:
        return local
    # Fallback to backend API
    try:
        r = api("GET", f"/api/v1/reports/{report_id}/sections")
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

def load_metadata_reports() -> list[dict]:
    """Load full metadata (incl. ratings) from metadata.yaml via backend."""
    try:
        r = api("GET", "/api/v1/metadata")
        return r.json().get("reports", []) if r.status_code == 200 else []
    except Exception:
        return []

def do_login(username, password):
    try:
        r = httpx.post(f"{BACKEND_URL}/api/v1/auth/login",
                       json={"username": username, "password": password}, timeout=10)
        if r.status_code == 200:
            d = r.json()
            st.session_state.update({
                "session_token": d["session_token"],
                "username":      d["username"],
                "display_name":  d["display_name"],
                "role":          d["role"],
            })
            return True, ""
        return False, r.json().get("detail", "Login failed.")
    except httpx.ConnectError:
        return False, f"Cannot reach backend at {BACKEND_URL}. Is it running?"
    except Exception as e:
        return False, str(e)

def do_logout():
    try:
        api("POST", "/api/v1/auth/logout")
    except Exception:
        pass
    for k in ["session_token", "username", "display_name", "role",
               "all_reports", "lessons_cache", "synth_history"]:
        st.session_state[k] = None if k not in ("lessons_cache", "synth_history") \
                                else ({} if k == "lessons_cache" else [])
    st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Excel export helper
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Text cleaning — strip PDF extraction artefacts and split into items
# ─────────────────────────────────────────────────────────────────────────────

_TOC_LINE  = re.compile(r'^.{3,60}[.\s]{3,}\d{1,3}\s*$')
_PAGE_NUM  = re.compile(r'^\s*\d{1,3}\s*$')

# Patterns that indicate questionnaire / ToR / garbage lines
_QUESTION_STARTS = (
    "what ", "how ", "did ", "do you", "are you", "were you", "please ",
    "who ", "when ", "why ", "which ", "have you", "would you", "could you",
    "is there", "was there", "can you",
)
_GARBAGE_PATTERNS = (
    "terms of reference", "table of contents", "list of figures",
    "list of tables", "abbreviations", "acronyms", "questionnaire",
    "interview guide", "contact person", "please email",
    "name of your", "your position", "name of company",
    "highly unsatisfactory", "highly satisfactory", "vienna international",
    "wagramerstr", "minimum organizational", "advanced degree",
    "key informant interview", "questions for key", "criteria question",
    "figures and tables", "project factsheet", "acknowledgements",
    "actual project start", "planned project completion", "project duration",
    "gef ceo endorsement", "pad issuance", "first august", "ful issuance",
    "soalan temubual", "membangunkan dapatan", "cadangan untuk",
    # Intro sentences that introduce but are not lessons/recs themselves
    "the following lessons are", "the following recommendations are",
    "the following lessons were", "the following recommendations were",
    "lessons are proposed for consideration", "are proposed for consideration",
    "following key lessons", "lessons identified in this evaluation",
)

# Words that signal a fragment starting mid-sentence (not a genuine lesson)
_FRAGMENT_STARTS = (
    "of ", "to ", "and ", "in ", "with ", "by ", "for ", "from ", "at ",
    "on ", "as ", "but ", "or ", "nor ", "so ", "yet ", "both ", "either ",
    "neither ", "not ", "only ", "also ", "thus ", "hence ", "however ",
    "moreover ", "furthermore ", "therefore ", "additionally ", "similarly ",
    "consequently ", "nevertheless ", "nonetheless ",
)


def _is_garbage_chunk(text: str) -> bool:
    """Return True if this chunk is mostly questionnaire / ToR / non-lesson content."""
    if not text:
        return True
    lower = text.lower()
    for pat in _GARBAGE_PATTERNS:
        if pat in lower:
            return True
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return True
    # Reject if >35% of lines are questions
    q_count = sum(1 for l in lines if l.endswith("?") or
                  any(l.lower().startswith(s) for s in _QUESTION_STARTS))
    if q_count / len(lines) > 0.35:
        return True
    # Reject if chunk looks like a project data table (many short date-like lines)
    date_re = re.compile(r'\b(january|february|march|april|may|june|july|august|'
                         r'september|october|november|december|\d{4})\b', re.I)
    date_lines = sum(1 for l in lines if date_re.search(l) and len(l) < 80)
    if len(lines) >= 3 and date_lines / len(lines) > 0.5:
        return True
    return False


def _is_quality_item(text: str) -> bool:
    """Return True if this extracted item looks like a genuine lesson/recommendation."""
    t = text.strip()
    if len(t) < 50:
        return False
    if t.endswith("?") or t.endswith(":"):
        return False
    lower = t.lower()
    # Reject questionnaire-style starts
    for s in _QUESTION_STARTS:
        if lower.startswith(s):
            return False
    # Reject obvious garbage patterns
    for pat in _GARBAGE_PATTERNS:
        if pat in lower:
            return False
    # Must have at least 8 words
    if len(t.split()) < 8:
        return False
    # Reject mid-sentence fragments (start with lowercase continuation word)
    first_char = t[0]
    if first_char.islower():
        return False
    # Reject if starts with a fragment connector word (even if capitalised after stripping)
    for frag in _FRAGMENT_STARTS:
        if lower.startswith(frag):
            return False
    # Reject abbreviation list entries (e.g. "RBM Results-based Management")
    words = t.split()
    if len(words) <= 6 and words[0].isupper() and len(words[0]) <= 6:
        return False
    # Reject items that are clearly table/figure captions
    if re.match(r'^(table|figure|annex|appendix)\s+\d', lower):
        return False
    # Detect garbled PDF table text: institution name repeated 2+ times in first 160 chars
    # e.g. "Recommendation 2: UNIDO and GEF ... UNIDO During the ..."
    head = lower[:160]
    for inst in ("unido", "gef ", "undp", "unep"):
        if head.count(inst) >= 2:
            return False
    # Reject intro sentences ending with colon (they introduce a list, not a lesson)
    if re.search(r'(following|consideration|below|noted|identified)\s*:\s*$', lower):
        return False
    # Must contain at least one verb-like structure
    if not re.search(r'\b(should|must|need|ensure|improve|strengthen|consider|'
                     r'increase|reduce|support|develop|establish|provide|include|'
                     r'require|recommend|is|are|was|were|will|would|can|could|'
                     r'has|have|had|been|be|demonstrated|showed|found|proved|'
                     r'contributed|resulted|enabled|allowed)\b', lower):
        return False
    return True


def _clean_raw_text(text: str) -> str:
    """Remove table-of-contents lines, page numbers, and other PDF artefacts."""
    if not text:
        return ""
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        if _TOC_LINE.match(stripped):
            continue
        if _PAGE_NUM.match(stripped):
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def extract_items(chunk_text: str, max_items: int = 8) -> list[str]:
    # Reject entire chunk if it is questionnaire/ToR garbage
    if _is_garbage_chunk(chunk_text):
        return []

    text = _clean_raw_text(chunk_text)
    if not text:
        return []

    def cap_text(s):
        s = s.strip()
        count = 0
        for i in range(len(s) - 2):
            if s[i] in ".!?" and s[i + 1] == " " and s[i + 2].isupper():
                count += 1
                if count >= 2:
                    s = s[: i + 1]
                    break
        return s[:320]

    items = []
    current = []
    in_item = False

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        j = 0
        while j < 2 and j < len(stripped) and stripped[j].isdigit():
            j += 1
        is_new = (
            j > 0
            and j < len(stripped)
            and stripped[j] in ".)"
            and j + 1 < len(stripped)
            and stripped[j + 1] == " "
        )
        if is_new:
            if current:
                txt = cap_text(" ".join(current))
                if _is_quality_item(txt):
                    items.append(txt)
                if len(items) >= max_items:
                    break
            current = [stripped[j + 2:]]
            in_item = True
        elif in_item:
            current.append(stripped)

    if current and len(items) < max_items:
        txt = cap_text(" ".join(current))
        if _is_quality_item(txt):
            items.append(txt)

    if items:
        return items

    # Fallback: return the chunk as a single item if it passes quality check
    result = cap_text(text)
    return [result] if _is_quality_item(result) else []


def make_excel_sections(reports_meta: list[dict], sections_by_id: dict) -> bytes:
    """Comprehensive multi-sheet Excel export with all view detail fields."""
    import pathlib
    from openpyxl.styles import Font, PatternFill, Alignment, PatternFill
    from openpyxl.utils import get_column_letter

    SDG_NAMES_LOCAL = {
        1:"No Poverty",2:"Zero Hunger",3:"Good Health",4:"Quality Education",
        5:"Gender Equality",6:"Clean Water",7:"Affordable Clean Energy",
        8:"Decent Work",9:"Industry Innovation",10:"Reduced Inequalities",
        11:"Sustainable Cities",12:"Responsible Consumption",13:"Climate Action",
        14:"Life Below Water",15:"Life on Land",16:"Peace Justice",17:"Partnerships",
    }

    HEADER_FILL  = PatternFill("solid", fgColor="003DA5")
    HEADER_FONT  = Font(bold=True, color="FFFFFF", size=10)
    ALT_FILL     = PatternFill("solid", fgColor="EFF6FF")
    WRAP_ALIGN   = Alignment(wrap_text=True, vertical="top")
    TOP_ALIGN    = Alignment(vertical="top")

    def _style_sheet(ws, col_widths: list[int]):
        """Apply header styling and column widths."""
        for cell in ws[1]:
            cell.fill      = HEADER_FILL
            cell.font      = HEADER_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.row_dimensions[1].height = 28
        for i, w in enumerate(col_widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        # Alternate row shading + wrap
        for row_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
            fill = ALT_FILL if row_idx % 2 == 0 else None
            row_h = 15
            for cell in row:
                if fill:
                    cell.fill = fill
                cell.alignment = WRAP_ALIGN
                val_len = len(str(cell.value or ""))
                row_h = max(row_h, min(15 * max(1, val_len // 60), 120))
            ws.row_dimensions[row_idx].height = row_h

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:

        # ── Sheet 1: Metadata ────────────────────────────────────────────────
        meta_rows = []
        for rep in reports_meta:
            rid  = rep.get("report_id", "")
            ai   = _load_ai_extraction(rid)
            ctx  = ai.get("context", {})
            rating = ctx.get("evaluation_rating") or rep.get("evaluation_rating")
            sdgs_raw = ai.get("sdg_mapping", {})
            sdg_nums = sorted(int(k) for k in sdgs_raw.keys() if str(k).isdigit()) if sdgs_raw else (rep.get("sdgs") or [])
            meta_rows.append({
                "Report ID":               rid,
                "Title":                   ctx.get("title") or rep.get("title", ""),
                "Year":                    ctx.get("year") or rep.get("year", ""),
                "Country":                 ctx.get("country") or rep.get("country", ""),
                "Region":                  ctx.get("region") or rep.get("region", ""),
                "Report Type":             ctx.get("report_type") or rep.get("report_type", ""),
                "Primary Thematic Area":   ai.get("primary_thematic_area") or rep.get("thematic_category", ""),
                "Secondary Thematic Area": ai.get("secondary_thematic_area", ""),
                "Thematic Justification":  ai.get("thematic_justification", ""),
                "Evaluation Rating":       f"{float(rating):.1f}/6" if rating else "",
                "Donor":                   ctx.get("donor") or rep.get("donor", ""),
                "Project ID":              ctx.get("project_id") or rep.get("project_id", ""),
                "Budget (USD)":            ctx.get("budget_usd") or rep.get("budget_usd", ""),
                "SDGs":                    ", ".join(f"SDG {n}" for n in sdg_nums),
            })
        df_meta = pd.DataFrame(meta_rows)
        df_meta.to_excel(writer, sheet_name="Metadata", index=False)
        ws = writer.sheets["Metadata"]
        _style_sheet(ws, [14,55,6,18,14,22,28,28,55,16,20,14,14,30])

        # ── Sheet 2: Executive Summary ───────────────────────────────────────
        summ_rows = []
        for rep in reports_meta:
            rid = rep.get("report_id", "")
            ai  = _load_ai_extraction(rid)
            ctx = ai.get("context", {})
            summ_rows.append({
                "Report ID": rid,
                "Title":     ctx.get("title") or rep.get("title", ""),
                "Year":      ctx.get("year") or rep.get("year", ""),
                "Country":   ctx.get("country") or rep.get("country", ""),
                "Executive Summary": ai.get("executive_summary") or rep.get("executive_summary", ""),
            })
        df_summ = pd.DataFrame(summ_rows)
        df_summ.to_excel(writer, sheet_name="Executive Summary", index=False)
        ws = writer.sheets["Executive Summary"]
        _style_sheet(ws, [14,55,6,18,100])

        # ── Sheet 3: Lessons Learned ─────────────────────────────────────────
        ll_rows = []
        for rep in reports_meta:
            rid = rep.get("report_id", "")
            ai  = _load_ai_extraction(rid)
            ctx = ai.get("context", {})
            lessons = ai.get("lessons_learned") or rep.get("lessons_learned") or []
            if not lessons:
                # fallback: raw sections text
                sec_data = sections_by_id.get(rid, {})
                raw = (sec_data.get("sections", {}) if sec_data else {}).get("lessons_learned", "")
                lessons = [raw] if raw else []
            for i, lesson in enumerate(lessons, 1):
                ll_rows.append({
                    "Report ID": rid,
                    "Title":     ctx.get("title") or rep.get("title", ""),
                    "Year":      ctx.get("year") or rep.get("year", ""),
                    "Country":   ctx.get("country") or rep.get("country", ""),
                    "Primary Thematic Area": ai.get("primary_thematic_area") or rep.get("thematic_category", ""),
                    "#":         i,
                    "Lesson Learned": lesson,
                })
        df_ll = pd.DataFrame(ll_rows) if ll_rows else pd.DataFrame(
            columns=["Report ID","Title","Year","Country","Primary Thematic Area","#","Lesson Learned"])
        df_ll.to_excel(writer, sheet_name="Lessons Learned", index=False)
        ws = writer.sheets["Lessons Learned"]
        _style_sheet(ws, [14,45,6,18,28,4,100])

        # ── Sheet 4: Recommendations ─────────────────────────────────────────
        rec_rows = []
        for rep in reports_meta:
            rid = rep.get("report_id", "")
            ai  = _load_ai_extraction(rid)
            ctx = ai.get("context", {})
            recs = ai.get("recommendations") or rep.get("recommendations") or []
            if not recs:
                sec_data = sections_by_id.get(rid, {})
                raw = (sec_data.get("sections", {}) if sec_data else {}).get("recommendations", "")
                recs = [raw] if raw else []
            for i, rec in enumerate(recs, 1):
                rec_rows.append({
                    "Report ID": rid,
                    "Title":     ctx.get("title") or rep.get("title", ""),
                    "Year":      ctx.get("year") or rep.get("year", ""),
                    "Country":   ctx.get("country") or rep.get("country", ""),
                    "Primary Thematic Area": ai.get("primary_thematic_area") or rep.get("thematic_category", ""),
                    "#":         i,
                    "Recommendation": rec,
                })
        df_rec = pd.DataFrame(rec_rows) if rec_rows else pd.DataFrame(
            columns=["Report ID","Title","Year","Country","Primary Thematic Area","#","Recommendation"])
        df_rec.to_excel(writer, sheet_name="Recommendations", index=False)
        ws = writer.sheets["Recommendations"]
        _style_sheet(ws, [14,45,6,18,28,4,100])

        # ── Sheet 5: SDG Mapping ─────────────────────────────────────────────
        sdg_rows = []
        for rep in reports_meta:
            rid = rep.get("report_id", "")
            ai  = _load_ai_extraction(rid)
            ctx = ai.get("context", {})
            sdg_map = ai.get("sdg_mapping", {})
            if not sdg_map:
                # build basic rows from sdgs list without justifications
                for n in (rep.get("sdgs") or []):
                    try:
                        n = int(n)
                    except Exception:
                        continue
                    sdg_rows.append({
                        "Report ID": rid,
                        "Title":     ctx.get("title") or rep.get("title", ""),
                        "Year":      ctx.get("year") or rep.get("year", ""),
                        "Country":   ctx.get("country") or rep.get("country", ""),
                        "SDG #":     n,
                        "SDG Name":  SDG_NAMES_LOCAL.get(n, ""),
                        "Justification": "",
                    })
            else:
                for k, justification in sdg_map.items():
                    try:
                        n = int(k)
                    except Exception:
                        continue
                    sdg_rows.append({
                        "Report ID": rid,
                        "Title":     ctx.get("title") or rep.get("title", ""),
                        "Year":      ctx.get("year") or rep.get("year", ""),
                        "Country":   ctx.get("country") or rep.get("country", ""),
                        "SDG #":     n,
                        "SDG Name":  SDG_NAMES_LOCAL.get(n, ""),
                        "Justification": justification,
                    })
        df_sdg = pd.DataFrame(sdg_rows) if sdg_rows else pd.DataFrame(
            columns=["Report ID","Title","Year","Country","SDG #","SDG Name","Justification"])
        if not df_sdg.empty and "SDG #" in df_sdg.columns:
            df_sdg = df_sdg.sort_values(["Report ID","SDG #"])
        df_sdg.to_excel(writer, sheet_name="SDG Mapping", index=False)
        ws = writer.sheets["SDG Mapping"]
        _style_sheet(ws, [14,45,6,18,6,26,100])

    return buf.getvalue()


def make_excel(reports_data: list[dict]) -> bytes:
    # Build Excel: one row per extracted lesson or recommendation item.
    rows_l, rows_r = [], []
    for rep in reports_data:
        meta = {
            "Report Title": rep.get("title", ""),
            "Year":         rep.get("year", ""),
            "Country":      rep.get("country", ""),
            "Region":       rep.get("region", ""),
            "Thematic Area":rep.get("thematic_category", ""),
        }
        for chunk in rep.get("lessons_learned", []):
            for item in extract_items(chunk):
                rows_l.append({**meta, "Lesson Learned": item})

        for chunk in rep.get("recommendations", []):
            for item in extract_items(chunk):
                rows_r.append({**meta, "Recommendation": item})

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_l = pd.DataFrame(rows_l) if rows_l else pd.DataFrame(
            columns=["Report Title", "Year", "Country", "Region", "Thematic Area", "Lesson Learned"])
        df_r = pd.DataFrame(rows_r) if rows_r else pd.DataFrame(
            columns=["Report Title", "Year", "Country", "Region", "Thematic Area", "Recommendation"])
        df_l.to_excel(writer, sheet_name="Lessons Learned",  index=False)
        df_r.to_excel(writer, sheet_name="Recommendations",  index=False)
    return buf.getvalue()

# ─────────────────────────────────────────────────────────────────────────────
# Login page
# ─────────────────────────────────────────────────────────────────────────────

def show_login_page():
    st.markdown('<div class="login-wrap">', unsafe_allow_html=True)
    st.markdown("""
    <div class="login-logo">
      <div class="big">UNIDO</div>
      <div class="sub">Evaluation Intelligence Platform<br>IEU / EIO Division · Internal Access</div>
    </div>
    """, unsafe_allow_html=True)

    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("#### Sign in")
        username = st.text_input("Username", placeholder="your.username", key="li_u")
        password = st.text_input("Password", type="password", placeholder="••••••••", key="li_p")
        if st.button("Sign in", type="primary", use_container_width=True):
            if not username or not password:
                st.error("Enter username and password.")
            else:
                with st.spinner("Authenticating…"):
                    ok, msg = do_login(username, password)
                if ok:
                    st.rerun()
                else:
                    st.error(f" {msg}")
        st.divider()
        st.caption("Access issues? Contact Maryam Babar (EIO Division).")
    st.markdown("</div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SDG legend (all 17 icons displayed horizontally)
# ─────────────────────────────────────────────────────────────────────────────

def show_sdg_legend():
    badges = "".join(
        f'<span title="SDG {n}: {SDG_NAMES[n]}">'
        f'{sdg_badge_html(n, 38)}'
        f'</span>'
        for n in range(1, 18)
    )
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;gap:2px;margin-bottom:0.5rem;">'
        f'{badges}</div>',
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# Report Detail Modal
# ─────────────────────────────────────────────────────────────────────────────

def _load_ai_extraction(report_id: str) -> dict:
    """Load Gemini-extracted JSON for a report, or {} if not yet generated."""
    import pathlib
    p = pathlib.Path(__file__).parent.parent / "data" / "ai_extractions" / f"{report_id}.json"
    if p.exists():
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


@st.dialog("Evaluation Report", width="large")
def _report_detail_modal():
    """Professional modal matching the EIO platform design."""
    rep      = st.session_state.get("modal_rep", {})
    sec_data = st.session_state.get("modal_sec", {})

    title    = rep.get("title", "Untitled Report")
    year     = rep.get("year", "")
    country  = rep.get("country", "")
    region   = rep.get("region", "")
    thematic = rep.get("thematic_category", "")
    rating   = rep.get("evaluation_rating")
    donor    = rep.get("donor", "")
    budget   = rep.get("budget_usd")
    rtype    = rep.get("report_type", "Terminal Evaluation")
    sdgs     = rep.get("sdgs") or []
    rid      = rep.get("report_id", "")

    # Load Gemini AI extraction (if script has been run)
    ai = _load_ai_extraction(rid)

    # Override thematic area from AI extraction if available
    if ai.get("primary_thematic_area"):
        thematic = ai["primary_thematic_area"]
    if ai.get("context", {}).get("evaluation_rating"):
        rating = ai["context"]["evaluation_rating"]

    # Format fields
    project_id = ai.get("context", {}).get("project_id") or rep.get("project_id", "")
    rating_str = f" {float(rating):.1f} / 6" if rating else "N/A"
    budget_str = f"USD {budget/1e6:.1f}M" if budget and budget >= 1e5 else ""
    meta_line = " &nbsp;·&nbsp; ".join(p for p in [
        f" {country}" if country else "",
        f" {float(rating):.1f}/6" if rating else "",
        budget_str,
        donor,
    ] if p)
    project_line = f"Project ID: {project_id}" if project_id else ""

    # ── Dark-blue header ──────────────────────────────────────────────────────
    st.markdown(f"""
    <div style="background:#003da5;color:white;
                margin:-1rem -1rem 0 -1rem;padding:1.2rem 1.6rem 1rem;">
      <div style="font-size:0.72rem;opacity:0.75;letter-spacing:0.06em;
                  text-transform:uppercase;margin-bottom:0.4rem;">
        {rtype} &nbsp;·&nbsp; {year} &nbsp;·&nbsp; {region}{f" &nbsp;·&nbsp; {project_line}" if project_line else ""}
      </div>
      <div style="font-size:1.15rem;font-weight:700;line-height:1.35;">{title}</div>
      <div style="margin-top:0.55rem;font-size:0.82rem;opacity:0.88;">{meta_line}</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Tabs ──────────────────────────────────────────────────────────────────
    # Load sections from local file first (reliable), fallback to API data
    _local_data = _load_sections_local(rid)
    if _local_data.get("sections"):
        sections = _local_data["sections"]
    else:
        sections = sec_data.get("sections", {}) if sec_data else {}
    colors   = _section_colors()

    t_ov, t_find, t_conc, t_ll, t_rec, t_sdg, t_theme, t_ctx = st.tabs(
        ["Overview", "Findings", "Conclusions", "Lessons Learned", "Recommendations", "SDG Mapping", "Thematic Area", "Context"]
    )

    with t_ov:
        st.markdown("#### AI Executive Summary")
        summary = ai.get("executive_summary") or rep.get("executive_summary") or sections.get("findings", "")
        if summary:
            ai_badge = '<span style="background:#e0f2fe;color:#0369a1;font-size:0.65rem;font-weight:700;padding:2px 7px;border-radius:4px;letter-spacing:0.06em;margin-right:8px;">✨ AI GENERATED</span>' if ai.get("executive_summary") else ""
            st.markdown(
                f'<div style="background:#f8faff;border-left:4px solid #003da5;'
                f'border-radius:0 8px 8px 0;padding:0.9rem 1.1rem;'
                f'font-size:0.88rem;line-height:1.7;color:#1e293b;">'
                f'{ai_badge}{summary[:2000]}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.info("Executive summary not yet available. Run `python scripts/extract_sections_local.py` to generate content.", icon="ℹ️")

        st.markdown("#### Classification")
        if sdgs:
            st.markdown(sdg_badges_row(sdgs, 38), unsafe_allow_html=True)
        tag_line = ""
        if thematic:
            tag_line += f'<span class="tag tag-blue">{thematic}</span> '
        if rating:
            try:
                r = float(rating)
                cls = "tag-green" if r >= 4.5 else ("tag-amber" if r >= 3.0 else "tag-red")
                label = "Satisfactory" if r >= 4.0 else ("Moderately Satisfactory" if r >= 3.0 else "Unsatisfactory")
                tag_line += f'<span class="tag {cls}">{label}</span> '
            except Exception:
                pass
        if tag_line:
            st.markdown(tag_line, unsafe_allow_html=True)

        if ai.get("thematic_justification"):
            st.markdown(
                f'<div style="margin-top:0.7rem;font-size:0.78rem;color:#6b7280;'
                f'font-style:italic;padding-left:0.5rem;">'
                f'<strong>Why this theme:</strong> {ai["thematic_justification"]}</div>',
                unsafe_allow_html=True,
            )


    with t_find:
        find_text = sections.get("findings", "") or sections.get("results", "")
        section_label = "Key Findings" if sections.get("findings") else ("Results" if sections.get("results") else "")
        if find_text and find_text.strip():
            st.markdown(
                f'<div style="font-size:0.75rem;color:#1d4ed8;font-weight:700;'
                f'letter-spacing:0.06em;margin-bottom:0.6rem;text-transform:uppercase;">'
                f'📋 {section_label} — Extracted from Report</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div style="background:#eff6ff;border-left:4px solid #1d4ed8;'
                f'border-radius:0 8px 8px 0;padding:0.85rem 1rem;'
                f'font-size:0.86rem;line-height:1.7;color:#1e293b;white-space:pre-wrap;">'
                f'{find_text.strip()[:8000]}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.info("This report does not contain a dedicated Findings or Results section.", icon="ℹ️")

    with t_conc:
        conc_text = sections.get("conclusions", "")
        if conc_text and conc_text.strip():
            st.markdown(
                '<div style="font-size:0.75rem;color:#166534;font-weight:700;'
                'letter-spacing:0.06em;margin-bottom:0.6rem;text-transform:uppercase;">📋 Extracted from Report</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div style="background:#f0fdf4;border-left:4px solid #166534;'
                f'border-radius:0 8px 8px 0;padding:0.85rem 1rem;'
                f'font-size:0.86rem;line-height:1.7;color:#1e293b;white-space:pre-wrap;">'
                f'{conc_text.strip()[:8000]}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.info("Conclusions not yet extracted for this report.", icon="ℹ️")

    with t_ll:
        # Priority: JSON file extraction → PILOT_METADATA fallback → Qdrant sections
        ai_lessons = ai.get("lessons_learned", []) or PILOT_METADATA.get(rid, {}).get("lessons_learned", [])
        if ai_lessons:
            for i, lesson in enumerate(ai_lessons, 1):
                st.markdown(
                    f'<div style="background:#e0f2fe;border-left:3px solid #0369a1;'
                    f'border-radius:0 8px 8px 0;padding:0.7rem 1rem;margin-bottom:0.5rem;'
                    f'font-size:0.86rem;line-height:1.6;color:#0c4a6e;">'
                    f'<strong>{i}.</strong> {lesson}</div>',
                    unsafe_allow_html=True,
                )
        else:
            c, bg = colors["lessons_learned"]
            _render_section_block("Lessons Learned", sections.get("lessons_learned", ""), c, bg)

    with t_rec:
        # Priority: JSON file extraction → PILOT_METADATA fallback → Qdrant sections
        ai_recs = ai.get("recommendations", []) or PILOT_METADATA.get(rid, {}).get("recommendations", [])
        if ai_recs:
            for i, rec in enumerate(ai_recs, 1):
                st.markdown(
                    f'<div style="background:#fff7ed;border-left:3px solid #ea580c;'
                    f'border-radius:0 8px 8px 0;padding:0.7rem 1rem;margin-bottom:0.5rem;'
                    f'font-size:0.86rem;line-height:1.6;color:#7c2d12;">'
                    f'<strong>{i}.</strong> {rec}</div>',
                    unsafe_allow_html=True,
                )
        else:
            c, bg = colors["recommendations"]
            _render_section_block("Recommendations", sections.get("recommendations", ""), c, bg)

    with t_sdg:
        # Use AI extraction first, then fall back to PILOT_METADATA justifications
        ai_sdg_map = ai.get("sdg_mapping", {})
        pilot_sdg_just = PILOT_METADATA.get(rid, {}).get("sdg_justifications", {})
        # Merge: prefer AI extraction; use pilot fallback if not present
        combined_sdg_map = {**pilot_sdg_just, **{str(k): v for k, v in ai_sdg_map.items()}}
        all_sdg_nums = sorted(set(
            [int(k) for k in combined_sdg_map.keys() if str(k).isdigit()] +
            ([int(s) for s in sdgs if str(s).isdigit()] if sdgs else [])
        ))
        if all_sdg_nums:
            st.markdown(
                '<div style="font-size:0.7rem;color:#166534;font-weight:700;'
                'letter-spacing:0.06em;margin-bottom:0.8rem;">✨ AI MAPPED WITH JUSTIFICATIONS</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                "SDGs are inferred from project activities and outcomes — they are never explicitly "
                "stated in the report text. Each justification explains the evidence basis."
            )
            for n in all_sdg_nums:
                badge = sdg_badge_html(n, 42)
                justification = combined_sdg_map.get(str(n), "")
                just_html = (
                    f'<div style="font-size:0.80rem;color:#374151;margin-top:4px;line-height:1.55;">'
                    f'{justification}</div>'
                ) if justification else ""
                st.markdown(
                    f'<div style="display:flex;align-items:flex-start;gap:14px;'
                    f'background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;'
                    f'padding:0.75rem 1rem;margin-bottom:0.5rem;">'
                    f'{badge}'
                    f'<div><strong style="font-size:0.9rem;color:#166534;">'
                    f'SDG {n} — {SDG_NAMES.get(n,"")}</strong>'
                    f'{just_html}</div></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("No SDG mapping available for this report.")

    with t_theme:
        # Use AI extraction first, then PILOT_METADATA fallback
        pilot_meta   = PILOT_METADATA.get(rid, {})
        theme_name   = ai.get("primary_thematic_area") or pilot_meta.get("thematic_category") or thematic
        theme_second = ai.get("secondary_thematic_area") or pilot_meta.get("secondary_thematic_area", "")
        theme_just   = ai.get("thematic_justification") or pilot_meta.get("thematic_justification", "")

        if theme_name:
            st.markdown(
                '<div style="font-size:0.7rem;color:#7c3aed;font-weight:700;'
                'letter-spacing:0.06em;margin-bottom:0.8rem;">✨ AI CLASSIFIED WITH JUSTIFICATION</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                "Thematic areas are inferred from project objectives, activities, and sector focus — "
                "they are not stated explicitly in the report. Justification explains the evidence basis."
            )
            # Primary theme card
            st.markdown(
                f'<div style="background:#f5f3ff;border:1px solid #ddd6fe;border-radius:10px;'
                f'padding:1rem 1.2rem;margin-bottom:0.75rem;">'
                f'<div style="font-size:0.68rem;font-weight:700;color:#7c3aed;'
                f'letter-spacing:0.07em;text-transform:uppercase;margin-bottom:0.3rem;">'
                f'Primary Thematic Area</div>'
                f'<div style="font-size:1.05rem;font-weight:700;color:#4c1d95;margin-bottom:0.5rem;">'
                f'{theme_name}</div>'
                + (
                    f'<div style="font-size:0.83rem;color:#374151;line-height:1.6;">'
                    f'<strong>Why this theme:</strong> {theme_just}</div>'
                    if theme_just else ""
                )
                + '</div>',
                unsafe_allow_html=True,
            )
            # Secondary theme (if any)
            if theme_second:
                st.markdown(
                    f'<div style="background:#faf5ff;border:1px solid #e9d5ff;border-radius:8px;'
                    f'padding:0.75rem 1rem;">'
                    f'<div style="font-size:0.68rem;font-weight:700;color:#9333ea;'
                    f'letter-spacing:0.07em;text-transform:uppercase;margin-bottom:0.3rem;">'
                    f'Secondary Thematic Area</div>'
                    f'<div style="font-size:0.95rem;font-weight:600;color:#6b21a8;">'
                    f'{theme_second}</div></div>',
                    unsafe_allow_html=True,
                )
            # Show all UNIDO thematic areas with current one highlighted
            st.markdown(
                "<div style='margin-top:1rem;font-size:0.78rem;font-weight:600;"
                "color:#6b7280;margin-bottom:0.4rem;'>UNIDO Thematic Framework</div>",
                unsafe_allow_html=True,
            )
            chips_html = ""
            for area in THEMATIC_AREAS:
                is_primary   = area == theme_name
                is_secondary = area == theme_second
                if is_primary:
                    style = ("background:#7c3aed;color:white;font-weight:700;"
                             "border-radius:999px;padding:0.2rem 0.7rem;font-size:0.76rem;"
                             "display:inline-block;margin:3px;")
                elif is_secondary:
                    style = ("background:#ddd6fe;color:#4c1d95;font-weight:600;"
                             "border-radius:999px;padding:0.2rem 0.7rem;font-size:0.76rem;"
                             "display:inline-block;margin:3px;")
                else:
                    style = ("background:#f3f4f6;color:#9ca3af;"
                             "border-radius:999px;padding:0.2rem 0.7rem;font-size:0.76rem;"
                             "display:inline-block;margin:3px;")
                chips_html += f'<span style="{style}">{area}</span>'
            st.markdown(f'<div style="line-height:2;">{chips_html}</div>', unsafe_allow_html=True)
        else:
            st.info("Thematic area classification not yet available for this report.")

    with t_ctx:
        # Funding line
        donor_val = rep.get("donor", "")
        funding_text = f"Funded by <strong>{donor_val}</strong>. Implemented in {country}." if donor_val and country else (f"Implemented in {country}." if country else "")
        if funding_text:
            st.markdown(
                f'<div style="font-size:0.85rem;color:#374151;margin-bottom:1rem;'
                f'padding-bottom:0.8rem;border-bottom:1px solid #f0f0f0;">{funding_text}</div>',
                unsafe_allow_html=True,
            )

        # Rating label from metadata
        rating_lbl = rep.get("overall_rating_label") or "N/A"
        if not rating_lbl and rating:
            try:
                r_val = float(rating)
                if r_val >= 4.5:    rating_lbl = "Highly Satisfactory"
                elif r_val >= 4.0:  rating_lbl = "Satisfactory"
                elif r_val >= 3.0:  rating_lbl = "Moderately Satisfactory"
                else:               rating_lbl = "Unsatisfactory"
            except Exception:
                pass

        def _info_card(label, value):
            return (
                f'<div style="background:white;border:1px solid #e5e7eb;border-radius:8px;padding:0.75rem 1rem;">' 
                f'<div style="font-size:0.64rem;font-weight:700;color:#9ca3af;'
                f'letter-spacing:0.08em;text-transform:uppercase;margin-bottom:0.35rem;">{label}</div>'
                f'<div style="font-size:0.9rem;font-weight:700;color:#111827;line-height:1.3;">{value}</div>'
                f'</div>'
            )

        # Row 1: Budget | Year | Thematic Area
        r1c1, r1c2, r1c3 = st.columns(3)
        with r1c1:
            st.markdown(_info_card("Budget", budget_str or "N/A"), unsafe_allow_html=True)
        with r1c2:
            st.markdown(_info_card("Year", str(year) if year else "N/A"), unsafe_allow_html=True)
        with r1c3:
            st.markdown(_info_card("Thematic Area", rep.get("thematic_category","N/A")), unsafe_allow_html=True)

        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

        # Row 2: Type | Country | Overall Rating
        r2c1, r2c2, r2c3 = st.columns(3)
        with r2c1:
            st.markdown(_info_card("Evaluation Type", rtype or "N/A"), unsafe_allow_html=True)
        with r2c2:
            st.markdown(_info_card("Country", country or "N/A"), unsafe_allow_html=True)
        with r2c3:
            st.markdown(_info_card("Overall Rating", rating_lbl), unsafe_allow_html=True)

    # ── Footer download ───────────────────────────────────────────────────────
    if sec_data and sec_data.get("sections"):
        st.divider()
        xl = make_excel_sections([rep], {rid: sec_data})
        st.download_button(
            "Download Full Report as Excel",
            data=xl,
            file_name=f"UNIDO_{rid}_Evaluation.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — Search & Browse
# ─────────────────────────────────────────────────────────────────────────────

def _rating_badge(rating) -> str:
    if rating is None:
        return '<span class="rating-pill rating-none">Rating: N/A</span>'
    try:
        r = float(rating)
    except (TypeError, ValueError):
        return '<span class="rating-pill rating-none">Rating: N/A</span>'
    cls = "rating-high" if r >= 4.5 else ("rating-mid" if r >= 3.0 else "rating-low")
    return f'<span class="rating-pill {cls}"> {r:.1f} / 6</span>'


def _section_colors() -> dict:
    return {
        "findings":        ("#1d4ed8", "#eff6ff"),
        "results":         ("#7c3aed", "#f5f3ff"),
        "lessons_learned": ("#0369a1", "#e0f2fe"),
        "conclusions":     ("#166534", "#f0fdf4"),
        "recommendations": ("#9a3412", "#fff7ed"),
    }


def _render_section_block(label: str, text: str, color: str, bg: str):
    if not text or not text.strip():
        st.markdown(
            f'<div style="color:#9ca3af;font-size:0.82rem;font-style:italic;padding:0.4rem 0;">' +
            f'No {label.lower()} content extracted from this report.</div>',
            unsafe_allow_html=True,
        )
        return
    display_text = text.strip()
    if len(display_text) > 8000:
        display_text = display_text[:8000] + "\n\n[… truncated — download Excel for full text]"
    st.markdown(
        f'<div style="background:{bg};border-left:4px solid {color};' +
        f'border-radius:0 8px 8px 0;padding:0.85rem 1rem;margin-top:0.3rem;">' +
        f'<div style="font-size:0.84rem;color:#1e293b;line-height:1.7;white-space:pre-wrap;">' +
        display_text + '</div></div>',
        unsafe_allow_html=True,
    )


def show_search_tab(filters: dict):
    load_reports()
    # Demo phase: restrict to the 4 verified pilot reports only
    all_reps = [r for r in (st.session_state.all_reports or [])
                if r.get("report_id") in PILOT_METADATA]
    all_reps = sorted(all_reps, key=lambda r: (r.get("year") or 0, r.get("report_id", "")), reverse=True)

    st.markdown(
        '<div class="pilot-banner"><strong>Pilot phase</strong> — '
        'Showing 4 evaluation reports from 2021. Sections verified and ready for review.</div>',
        unsafe_allow_html=True,
    )

    # ── Apply sidebar filters ────────────────────────────────────────────────
    filtered = all_reps
    if filters["thematic"]:
        filtered = [r for r in filtered if r.get("thematic_category") in filters["thematic"]]
    if filters["sdgs"]:
        filtered = [r for r in filtered
                    if any(s in (r.get("sdgs") or []) for s in filters["sdgs"])]
    if filters["eval_type"]:
        filtered = [r for r in filtered if r.get("evaluation_type") in filters["eval_type"]]
    if filters["region"]:
        filtered = [r for r in filtered if r.get("region") in filters["region"]]

    if len(all_reps) == 0:
        st.info("No reports loaded. Check backend connection.")
        return
    st.markdown(
        f'<div style="font-size:0.82rem;color:#6b7280;margin-bottom:0.8rem;">'
        f'Showing <strong>{len(filtered)}</strong> of <strong>{len(all_reps)}</strong> reports</div>',
        unsafe_allow_html=True,
    )
    if not filtered:
        return

    # ── 2-column card grid ───────────────────────────────────────────────────
    for row_start in range(0, len(filtered), 2):
        pair = filtered[row_start : row_start + 2]
        grid_cols = st.columns(len(pair), gap="large")

        for col, rep in zip(grid_cols, pair):
            title    = rep.get("title") or "Untitled Report"
            year     = rep.get("year", "")
            country  = rep.get("country", "")
            region   = rep.get("region", "")
            thematic = rep.get("thematic_category", "")
            rtype    = rep.get("report_type", "")
            donor    = rep.get("donor", "")
            sdgs     = rep.get("sdgs") or []
            rid      = rep.get("report_id", "")
            rating   = rep.get("evaluation_rating")
            budget   = rep.get("budget_usd")
            project_id = rep.get("project_id", "")

            badges_html    = sdg_badges_row(sdgs, 28)
            rating_html    = _rating_badge(rating)
            thematic_badge = f'<span class="tag tag-blue">{thematic}</span>' if thematic else ""
            rtype_badge    = f'<span class="tag tag-gray">{rtype}</span>' if rtype else ""
            donor_badge    = f'<span class="tag tag-green">{donor}</span>' if donor else ""
            budget_str     = (f'<span class="tag tag-purple">USD {budget/1e6:.1f}M</span>'
                             if budget and budget >= 1e5 else "")

            meta_parts = [str(year)] if year else []
            if country: meta_parts.append(country)
            if region and region != country: meta_parts.append(region)
            if project_id: meta_parts.append(f"Project {project_id}")
            meta_line = " · ".join(meta_parts)

            with col:
                st.markdown(f"""
                <div class="report-card" style="height:100%;min-height:160px;">
                  <div style="font-size:0.68rem;font-weight:700;color:#009EDB;
                              letter-spacing:0.06em;text-transform:uppercase;
                              margin-bottom:0.4rem;">{meta_line}</div>
                  <div class="report-title" style="font-size:0.9rem;line-height:1.45;
                              margin-bottom:0.5rem;">{title}</div>
                  <div style="margin:0.3rem 0 0.4rem;display:flex;flex-wrap:wrap;gap:3px;">
                    {rating_html}{thematic_badge}{rtype_badge}{donor_badge}{budget_str}
                  </div>
                  <div style="margin-top:0.35rem;">{badges_html}</div>
                </div>
                """, unsafe_allow_html=True)

                # ── Action buttons — 3 equal columns, full width of card ───
                b_view, b_ai, b_exp = st.columns(3, gap="small")
                with b_view:
                    if st.button("View Details ↗", key=f"view_{rid}", use_container_width=True):
                        with st.spinner("Loading…"):
                            sec_data = load_sections(rid)
                        st.session_state["modal_rep"] = rep
                        st.session_state["modal_sec"] = sec_data
                        _report_detail_modal()
                with b_ai:
                    askai_key = f"askai_prompt_{rid}"
                    if st.session_state.get(askai_key):
                        # Show the pre-built prompt panel
                        st.markdown(
                            f'<a href="https://copilot.microsoft.com" target="_blank" '
                            f'style="display:block;text-align:center;background:#0078d4;color:white;'
                            f'padding:6px 10px;border-radius:6px;font-size:0.82rem;font-weight:600;'
                            f'text-decoration:none;margin-bottom:4px;">🤖 Open Copilot ↗</a>',
                            unsafe_allow_html=True,
                        )
                        st.text_area(
                            "Copy → paste into Copilot:",
                            value=st.session_state[askai_key],
                            height=160,
                            key=f"askai_ta_{rid}",
                            label_visibility="visible",
                        )
                        if st.button("✕ Close", key=f"askai_close_{rid}", use_container_width=True):
                            del st.session_state[askai_key]
                            st.rerun()
                    else:
                        if st.button("Ask AI", key=f"askai_{rid}", type="primary", use_container_width=True):
                            ai_data = _load_ai_extraction(rid)
                            ctx     = ai_data.get("context", {})
                            _title  = ctx.get("title") or rep.get("title", "")
                            _year   = ctx.get("year") or rep.get("year", "")
                            _cntry  = ctx.get("country") or rep.get("country", "")
                            _theme  = ai_data.get("primary_thematic_area") or rep.get("thematic_category", "")
                            _summ   = ai_data.get("executive_summary") or rep.get("executive_summary", "")
                            _les    = ai_data.get("lessons_learned") or []
                            _recs   = ai_data.get("recommendations") or []
                            _sdgs   = ai_data.get("sdg_mapping") or {}
                            _sdg_s  = ", ".join(
                                f"SDG {k}" for k in sorted(_sdgs.keys(), key=lambda x: int(x) if x.isdigit() else 99)
                            ) if _sdgs else ""
                            parts = [
                                f"UNIDO Evaluation Report: {_title} ({_year}, {_cntry})",
                                f"Thematic Area: {_theme}" if _theme else "",
                                f"SDGs: {_sdg_s}" if _sdg_s else "",
                                "",
                                "EXECUTIVE SUMMARY:",
                                (_summ[:1500] if _summ else "(not available)"),
                            ]
                            if _les:
                                parts += ["", "KEY LESSONS LEARNED:"]
                                parts += [f"{i}. {l}" for i, l in enumerate(_les[:5], 1)]
                            if _recs:
                                parts += ["", "KEY RECOMMENDATIONS:"]
                                parts += [f"{i}. {r}" for i, r in enumerate(_recs[:5], 1)]
                            parts += ["", "---", "Please analyse this evaluation report and share your insights."]
                            st.session_state[askai_key] = "\n".join(p for p in parts)
                            st.rerun()
                with b_exp:
                    exp_key = f"export_bytes_{rid}"
                    exp_err_key = f"export_err_{rid}"
                    if exp_key in st.session_state:
                        st.download_button(
                            label="⬇ Excel",
                            data=st.session_state[exp_key],
                            file_name=f"UNIDO_{rid}_Evaluation.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_{rid}",
                            use_container_width=True,
                        )
                    else:
                        if st.session_state.get(exp_err_key):
                            st.error(st.session_state.pop(exp_err_key), icon="⚠️")
                        if st.button("Export", key=f"exp_{rid}", use_container_width=True):
                            with st.spinner("Preparing Excel…"):
                                try:
                                    sec_e = load_sections(rid)
                                    xl_bytes = make_excel_sections([rep], {rid: sec_e})
                                    st.session_state[exp_key] = xl_bytes
                                except Exception as _ex:
                                    st.session_state[exp_err_key] = f"Export failed: {_ex}"
                            st.rerun()

        st.markdown("<div style='height:0.8rem;'></div>", unsafe_allow_html=True)


# TAB 2 — Synthesis (RAG — passages only, no LLM)
# ─────────────────────────────────────────────────────────────────────────────

def show_synthesis_tab(filters: dict):
    load_reports()
    # Demo phase: restrict to the 4 verified pilot reports only
    all_reps = [r for r in (st.session_state.all_reports or [])
                if r.get("report_id") in PILOT_METADATA]

    col_sel, col_chat = st.columns([3, 7])

    # ── Report selector ──────────────────────────────────────────────────────
    with col_sel:
        st.markdown("#### Select Reports")
        search_term = st.text_input("Filter list", placeholder="Search title…", key="synth_search")
        visible = [r for r in all_reps
                   if not search_term or search_term.lower() in r.get("title","").lower()]

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Select all", use_container_width=True):
                st.session_state["synth_sel"] = [r["report_id"] for r in visible]
        with c2:
            if st.button("Clear all", use_container_width=True):
                st.session_state["synth_sel"] = []

        if "synth_sel" not in st.session_state:
            st.session_state["synth_sel"] = []

        selected_ids = st.session_state["synth_sel"]
        st.caption(f"{len(selected_ids)} selected")

        for rep in visible:
            rid = rep["report_id"]
            checked = rid in selected_ids
            label = f"{rep.get('year','')} — {rep.get('title','')[:55]}"
            new = st.checkbox(label, value=checked, key=f"synth_cb_{rid}")
            if new and rid not in selected_ids:
                selected_ids.append(rid)
            elif not new and rid in selected_ids:
                selected_ids.remove(rid)

    # ── Chat / RAG ────────────────────────────────────────────────────────────
    with col_chat:
        st.markdown("#### Search Across Selected Reports")

        if not selected_ids:
            st.info("Select one or more reports on the left to begin.")
            return

        # Show selected report pills
        sel_reps = [r for r in all_reps if r["report_id"] in selected_ids]
        pills_html = " ".join(
            f'<span class="tag tag-blue">{r.get("title","")[:40]}</span>'
            for r in sel_reps[:8]
        )
        if len(sel_reps) > 8:
            pills_html += f' <span class="tag tag-gray">+{len(sel_reps)-8} more</span>'
        st.markdown(pills_html, unsafe_allow_html=True)
        st.divider()

        # Show history
        for item in st.session_state.synth_history:
            st.markdown(
                f'<div style="background:#f0f4ff;border-left:3px solid #003da5;'
                f'padding:0.5rem 0.8rem;border-radius:0 6px 6px 0;'
                f'font-size:0.85rem;font-weight:600;color:#003da5;margin-bottom:0.5rem;">'
                f'❓ {item["query"]}</div>',
                unsafe_allow_html=True,
            )
            answer = item.get("answer", "")
            n_rep  = item.get("report_count", 0)
            if answer:
                import re as _re
                # Render markdown answer
                st.markdown(
                    f'<div style="background:white;border:1px solid #e5e7eb;border-radius:8px;'
                    f'padding:1rem 1.2rem;margin-bottom:0.3rem;font-size:0.87rem;line-height:1.7;">',
                    unsafe_allow_html=True,
                )
                st.markdown(answer)
                st.markdown('</div>', unsafe_allow_html=True)
                st.caption(f"Synthesised across {n_rep} report(s) · Powered by Claude")
            st.divider()

        # Example chips
        examples = [
            "What are the key lessons learned across these reports?",
            "What common recommendations emerge on project sustainability?",
            "What findings relate to clean energy effectiveness?",
            "How do these projects address gender mainstreaming?",
            "What conclusions were drawn about stakeholder engagement?",
            "Compare the key findings across all selected reports.",
        ]
        st.markdown("**Example queries:**")
        ex_cols = st.columns(2)
        for i, ex in enumerate(examples):
            with ex_cols[i % 2]:
                if st.button(ex, key=f"synth_ex_{i}"):
                    st.session_state["synth_prefill"] = ex

        query = st.text_area(
            "Question",
            value=st.session_state.pop("synth_prefill", ""),
            height=90,
            placeholder="What findings emerge across the selected reports on…",
            label_visibility="collapsed",
            key="synth_query",
        )

        c_send, c_clear = st.columns([1, 4])
        with c_send:
            send = st.button("Search", type="primary", use_container_width=True)
        with c_clear:
            if st.button("Clear history"):
                st.session_state.synth_history = []
                st.rerun()

        if send and query.strip():
            with st.spinner("Claude is synthesising across selected reports…"):
                try:
                    import anthropic as _anthropic

                    try:
                        _api_key = st.secrets["ANTHROPIC_API_KEY"]
                    except Exception:
                        _api_key = os.getenv("ANTHROPIC_API_KEY", "")

                    if not _api_key:
                        st.warning("Add ANTHROPIC_API_KEY to Streamlit secrets to enable synthesis.", icon="⚠️")
                        st.stop()

                    # Load sections locally — no backend needed
                    context_blocks = []
                    for rid in selected_ids:
                        sec   = _load_sections_local(rid)
                        secs  = sec.get("sections", {})
                        meta  = sec.get("metadata", {})
                        ai_d  = _load_ai_extraction(rid)
                        title   = meta.get("title") or ai_d.get("context", {}).get("title", rid)
                        year    = meta.get("year") or ai_d.get("context", {}).get("year", "")
                        country = meta.get("country") or ai_d.get("context", {}).get("country", "")
                        block = (
                            f"=== REPORT: {title} ===\n"
                            f"Year: {year} | Country: {country}\n\n"
                            f"FINDINGS / RESULTS:\n{(secs.get('findings') or secs.get('results') or 'Not available')[:1500]}\n\n"
                            f"CONCLUSIONS:\n{secs.get('conclusions', 'Not available')[:1500]}\n\n"
                            f"LESSONS LEARNED:\n{secs.get('lessons_learned', 'Not available')[:1500]}\n\n"
                            f"RECOMMENDATIONS:\n{secs.get('recommendations', 'Not available')[:1500]}\n"
                        )
                        context_blocks.append(block)

                    n = len(context_blocks)
                    context_text = "\n\n".join(context_blocks)

                    system_prompt = (
                        f"You are a senior evaluation synthesis analyst at UNIDO's Independent Evaluation Unit (IEU). "
                        f"You have deep expertise in development effectiveness, OECD-DAC criteria, clean energy, and climate action evaluation.\n\n"
                        f"You have been provided with {n} UNIDO evaluation report(s). "
                        f"Synthesise findings ACROSS all reports — analytical, evidence-based, and genuinely useful.\n\n"
                        f"RULES:\n"
                        f"1. Synthesise ACROSS reports — identify patterns, tensions, and cross-cutting themes\n"
                        f"2. Use precise language: 'in 3 of 4 reports', 'the majority of reports'\n"
                        f"3. Cite specific report titles when making factual claims\n"
                        f"4. Draw non-obvious analytical conclusions\n"
                        f"5. Never invent information not in the provided reports\n"
                        f"6. End EVERY response with a ## Key Findings section with 3–5 bullet points\n\n"
                        f"TONE: Senior UN evaluation expert writing for a peer audience. Direct, analytical, clear."
                    )

                    _client = _anthropic.Anthropic(api_key=_api_key)
                    msg = _client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=2048,
                        system=system_prompt,
                        messages=[{"role": "user", "content": f"EVALUATION REPORTS:\n\n{context_text}\n\nQUESTION: {query.strip()}"}]
                    )
                    answer = msg.content[0].text if msg.content else ""
                    st.session_state.synth_history.append({
                        "query": query.strip(),
                        "answer": answer,
                        "report_count": n,
                    })
                    st.rerun()
                except Exception as e:
                    st.error(f"Synthesis error: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — Visualize
# ─────────────────────────────────────────────────────────────────────────────

def _build_knowledge_graph_figure(reports: list, by_sdg: dict, by_thematic: dict, by_year: dict):
    """Build a Plotly knowledge graph: reports as nodes, grouped by thematic area,
    edges drawn for shared SDGs (≥2). Returns a go.Figure."""
    import math

    if not reports:
        return None

    # ── Assign theme colors ───────────────────────────────────────────────────
    theme_palette = [
        "#009EDB", "#4CAF50", "#FF9800", "#E91E63", "#9C27B0",
        "#00BCD4", "#FF5722", "#607D8B", "#795548", "#3F51B5", "#8BC34A",
    ]
    theme_list = sorted(set(r.get("thematic_category", "Unknown") for r in reports))
    theme_color = {t: theme_palette[i % len(theme_palette)] for i, t in enumerate(theme_list)}

    # ── Cluster reports by thematic area ─────────────────────────────────────
    clusters: dict = {}
    for r in reports:
        t = r.get("thematic_category", "Unknown")
        clusters.setdefault(t, []).append(r)

    n_clusters = len(clusters)
    cluster_radius = 4.5
    report_pos: dict = {}   # report_id → (x, y)
    theme_pos: dict  = {}   # theme_name → (x, y)

    for ci, (theme, reps) in enumerate(sorted(clusters.items())):
        ca = 2 * math.pi * ci / n_clusters
        cx = cluster_radius * math.cos(ca)
        cy = cluster_radius * math.sin(ca)
        theme_pos[theme] = (cx * 1.35, cy * 1.35)

        n = len(reps)
        for ri, rep in enumerate(reps):
            if n == 1:
                rx, ry = cx, cy
            else:
                ra = 2 * math.pi * ri / n
                spread = min(1.0 + n * 0.06, 1.8)
                rx = cx + spread * math.cos(ra)
                ry = cy + spread * math.sin(ra)
            report_pos[rep["report_id"]] = (rx, ry)

    # ── Theme → report edges ──────────────────────────────────────────────────
    theme_edge_x, theme_edge_y = [], []
    for theme, reps in clusters.items():
        tx, ty = theme_pos[theme]
        for rep in reps:
            rx, ry = report_pos[rep["report_id"]]
            theme_edge_x += [rx, tx, None]
            theme_edge_y += [ry, ty, None]

    # ── SDG-connection edges (reports sharing ≥2 SDGs) ───────────────────────
    sdg_edge_x, sdg_edge_y = [], []
    id_list = [r["report_id"] for r in reports]
    sdg_map = {r["report_id"]: set(r.get("sdgs") or []) for r in reports}
    for i in range(len(id_list)):
        for j in range(i + 1, len(id_list)):
            shared = sdg_map[id_list[i]] & sdg_map[id_list[j]]
            if len(shared) >= 2:
                x1, y1 = report_pos[id_list[i]]
                x2, y2 = report_pos[id_list[j]]
                sdg_edge_x += [x1, x2, None]
                sdg_edge_y += [y1, y2, None]

    # ── Build traces ──────────────────────────────────────────────────────────
    fig = go.Figure()

    # Theme-report edges (light grey)
    fig.add_trace(go.Scatter(
        x=theme_edge_x, y=theme_edge_y, mode="lines",
        line=dict(color="rgba(200,200,200,0.4)", width=1),
        hoverinfo="none", showlegend=False,
    ))

    # SDG connection edges (blue, thinner)
    if sdg_edge_x:
        fig.add_trace(go.Scatter(
            x=sdg_edge_x, y=sdg_edge_y, mode="lines",
            line=dict(color="rgba(0,158,219,0.25)", width=1.5),
            hoverinfo="none", showlegend=False, name="Shared SDGs",
        ))

    # Theme nodes (larger squares)
    for theme in sorted(clusters.keys()):
        tx, ty = theme_pos[theme]
        n_reps = len(clusters[theme])
        fig.add_trace(go.Scatter(
            x=[tx], y=[ty], mode="markers+text",
            marker=dict(
                size=22, color=theme_color[theme],
                symbol="square", line=dict(color="white", width=2),
            ),
            text=[theme.replace(" / ", "<br>").replace(" & ", "<br>")],
            textposition="top center",
            textfont=dict(size=9, color="#1a1a2e"),
            hovertext=f"<b>{theme}</b><br>{n_reps} reports",
            hoverinfo="text",
            showlegend=True,
            name=theme,
            legendgroup=theme,
        ))

    # Report nodes (colored by theme)
    rep_x = [report_pos[r["report_id"]][0] for r in reports]
    rep_y = [report_pos[r["report_id"]][1] for r in reports]
    rep_colors = [theme_color.get(r.get("thematic_category", "Unknown"), "#888") for r in reports]
    rep_hover = []
    for r in reports:
        sdgs_str = " · ".join([f"SDG {s}" for s in sorted(r.get("sdgs") or [])[:4]])
        rep_hover.append(
            f"<b>{r.get('title','')[:55]}…</b><br>"
            f"{r.get('year','')} · {r.get('country','')}<br>"
            f"{r.get('thematic_category','')}<br>"
            f"{sdgs_str}"
        )

    fig.add_trace(go.Scatter(
        x=rep_x, y=rep_y, mode="markers",
        marker=dict(
            size=10, color=rep_colors,
            line=dict(color="white", width=1.5),
            opacity=0.9,
        ),
        hovertext=rep_hover, hoverinfo="text",
        showlegend=False, name="Reports",
    ))

    fig.update_layout(
        height=620,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(249,251,252,1)",
        margin=dict(t=20, b=20, l=20, r=20),
        showlegend=True,
        legend=dict(
            orientation="v", x=1.01, y=1, bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#e5e7eb", borderwidth=1,
            font=dict(size=10),
        ),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        hovermode="closest",
    )
    return fig


def show_visualize_tab():
    # ── Load data ─────────────────────────────────────────────────────────────
    load_reports()
    # Demo phase: restrict to the 4 verified pilot reports only
    reports = [r for r in (st.session_state.all_reports or [])
               if r.get("report_id") in PILOT_METADATA]

    # Compute stats locally from the 4 pilot reports (no backend call needed)
    total_docs   = len(reports)
    total_chunks = total_docs * 0  # not displayed for pilot
    by_year: dict     = {}
    by_thematic: dict = {}
    by_sdg: dict      = {}
    by_dac: dict      = {}
    for r in reports:
        y = str(r.get("year") or "Unknown")
        by_year[y] = by_year.get(y, 0) + 1
        t = r.get("thematic_category") or "Unknown"
        by_thematic[t] = by_thematic.get(t, 0) + 1
        for s in (r.get("sdgs") or []):
            k = f"SDG {s}"
            by_sdg[k] = by_sdg.get(k, 0) + 1
    total_chunks = sum(by_year.values()) * 200  # rough proxy for display

    # ── Stat cards ────────────────────────────────────────────────────────────
    sdg_count = len([v for v in by_sdg.values() if v > 0])
    countries  = len(set(r.get("country", "") for r in reports if r.get("country")))
    c1, c2, c3, c4 = st.columns(4)
    for col, num, lbl in [
        (c1, total_docs,    "Pilot Reports"),
        (c2, sdg_count,     "SDGs Covered"),
        (c3, countries,     "Countries"),
        (c4, len(by_thematic), "Thematic Areas"),
    ]:
        col.markdown(
            f'<div class="stat-card"><div class="stat-num">{num}</div>'
            f'<div class="stat-lbl">{lbl}</div></div>',
            unsafe_allow_html=True,
        )

    if not reports:
        st.info("No reports indexed yet.")
        return

    st.divider()

    # ── SDG coverage row ──────────────────────────────────────────────────────
    st.markdown("#### SDG Coverage")
    sdg_badge_grid = ""
    for n in range(1, 18):
        count = by_sdg.get(f"SDG {n}", 0)
        opacity = "1.0" if count > 0 else "0.2"
        sdg_badge_grid += (
            f'<span style="display:inline-flex;flex-direction:column;align-items:center;'
            f'margin:3px;opacity:{opacity};" title="SDG {n}: {SDG_NAMES[n]} — {count} reports">'
            f'{sdg_badge_html(n, 46)}'
            f'<span style="font-size:9px;color:#6b7280;margin-top:2px;">{count}</span>'
            f'</span>'
        )
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;gap:1px;">{sdg_badge_grid}</div>',
        unsafe_allow_html=True,
    )

    st.divider()

    # ── Knowledge Graph ───────────────────────────────────────────────────────
    st.markdown("#### Knowledge Graph — Portfolio Structure")
    st.caption(
        "**Squares** = thematic areas (colored). **Circles** = individual reports. "
        "**Blue edges** = reports sharing ≥2 SDGs. Hover any node for details."
    )

    kg_fig = _build_knowledge_graph_figure(reports, by_sdg, by_thematic, by_year)
    if kg_fig:
        st.plotly_chart(kg_fig, use_container_width=True)

    st.divider()

    # ── Supporting charts ─────────────────────────────────────────────────────
    with st.expander("📊 Portfolio Charts", expanded=True):
        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown("##### Thematic Distribution")
            if by_thematic:
                fig = px.pie(
                    names=list(by_thematic.keys()),
                    values=list(by_thematic.values()),
                    color_discrete_sequence=px.colors.qualitative.Safe,
                    hole=0.35,
                )
                fig.update_traces(textposition="inside", textinfo="percent+label")
                fig.update_layout(
                    showlegend=False, margin=dict(t=10,b=10,l=10,r=10),
                    height=300, paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig, use_container_width=True)

        with col_b:
            st.markdown("##### Reports by Year")
            if by_year:
                years = sorted(by_year.keys())
                fig = go.Figure(go.Bar(
                    x=years, y=[by_year[y] for y in years],
                    marker_color="#009EDB",
                    text=[by_year[y] for y in years], textposition="outside",
                ))
                fig.update_layout(
                    margin=dict(t=10,b=10,l=10,r=10), height=300,
                    paper_bgcolor="rgba(0,0,0,0)",
                    xaxis_title="Year", yaxis_title="Reports",
                )
                st.plotly_chart(fig, use_container_width=True)

        col_c, col_d = st.columns(2)

        with col_c:
            st.markdown("##### SDG Coverage (Top 10)")
            if by_sdg:
                top_sdg = sorted(by_sdg.items(), key=lambda x: -x[1])[:10]
                sdg_labels = [x[0] for x in top_sdg]
                sdg_vals   = [x[1] for x in top_sdg]
                sdg_colors_bar = [SDG_COLORS.get(int(l.split()[-1]), "#009EDB") for l in sdg_labels]
                fig = go.Figure(go.Bar(
                    y=sdg_labels, x=sdg_vals, orientation="h",
                    marker_color=sdg_colors_bar,
                    text=sdg_vals, textposition="outside",
                ))
                fig.update_layout(
                    margin=dict(t=10,b=10,l=10,r=10), height=320,
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig, use_container_width=True)

        with col_d:
            st.markdown("##### DAC Criteria Coverage")
            if by_dac:
                dac_keys = [k.replace("_"," ").title() for k in by_dac.keys()]
                dac_vals = list(by_dac.values())
                fig = go.Figure(go.Bar(
                    x=dac_keys, y=dac_vals,
                    marker_color=DAC_COLORS[:len(dac_keys)],
                    text=dac_vals, textposition="outside",
                ))
                fig.update_layout(
                    margin=dict(t=10,b=10,l=10,r=10), height=320,
                    paper_bgcolor="rgba(0,0,0,0)",
                    yaxis_title="Reports with evidence",
                )
                st.plotly_chart(fig, use_container_width=True)

        # Ratings + Thematic row
        col_e, col_f = st.columns(2)
        with col_e:
            st.markdown("##### Evaluation Ratings")
            ratings_data = [(r.get("title","")[:30], r.get("evaluation_rating")) for r in reports if r.get("evaluation_rating")]
            if ratings_data:
                titles_r = [x[0] for x in ratings_data]
                vals_r   = [float(x[1]) for x in ratings_data]
                colors_r = ["#22c55e" if v >= 4.5 else ("#f59e0b" if v >= 3.0 else "#ef4444") for v in vals_r]
                fig = go.Figure(go.Bar(
                    x=titles_r, y=vals_r,
                    marker_color=colors_r,
                    text=[f"{v:.1f}" for v in vals_r], textposition="outside",
                ))
                fig.update_layout(
                    margin=dict(t=10,b=40,l=10,r=10), height=320,
                    paper_bgcolor="rgba(0,0,0,0)",
                    yaxis=dict(title="Rating (1–6)", range=[0, 6.5]),
                    xaxis=dict(tickangle=-20),
                )
                st.plotly_chart(fig, use_container_width=True)

        with col_f:
            st.markdown("##### SDG Alignment by Report")
            if reports:
                rep_names = [r.get("title","")[:25] for r in reports]
                sdg_counts_per_rep = [len(r.get("sdgs") or []) for r in reports]
                fig = go.Figure(go.Bar(
                    x=rep_names, y=sdg_counts_per_rep,
                    marker_color="#009EDB",
                    text=sdg_counts_per_rep, textposition="outside",
                ))
                fig.update_layout(
                    margin=dict(t=10,b=40,l=10,r=10), height=320,
                    paper_bgcolor="rgba(0,0,0,0)",
                    yaxis=dict(title="Number of SDGs"),
                    xaxis=dict(tickangle=-20),
                )
                st.plotly_chart(fig, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — OECD-DAC Analysis
# ─────────────────────────────────────────────────────────────────────────────

def show_dac_tab():
    load_reports()
    # Demo phase: restrict to the 4 verified pilot reports only
    all_reps = [r for r in (st.session_state.all_reports or [])
                if r.get("report_id") in PILOT_METADATA]

    if not all_reps:
        st.info("No reports indexed yet.")
        return

    st.markdown(
        "Cross-portfolio analysis across the 5 OECD-DAC evaluation criteria. "
        "Select reports to compare their evidence coverage and browse verbatim passages "
        "across Relevance, Effectiveness, Efficiency, Impact, and Sustainability."
    )

    col_left, col_right = st.columns([3, 7])

    # ── Report selector ──────────────────────────────────────────────────────
    with col_left:
        st.markdown("#### Select Reports")
        mode = st.radio("Mode", ["Single report", "Compare multiple"], key="dac_mode",
                        horizontal=True)

        titles = {r["report_id"]: f"{r.get('year','')} — {r.get('title','')[:50]}"
                  for r in all_reps}

        if mode == "Single report":
            sel_id = st.selectbox("Report", list(titles.keys()),
                                  format_func=lambda x: titles.get(x, x),
                                  key="dac_single")
            dac_report_ids = [sel_id] if sel_id else []
        else:
            selected = st.multiselect("Reports (up to 5)", list(titles.keys()),
                                      format_func=lambda x: titles.get(x, x),
                                      max_selections=5, key="dac_multi")
            dac_report_ids = selected

        analyse = st.button("Analyse", type="primary", use_container_width=True)

    # ── Analysis panel ────────────────────────────────────────────────────────
    with col_right:
        if not dac_report_ids:
            st.info("Select a report on the left and click Analyse.")
            return

        if analyse or st.session_state.get("dac_results"):
            if analyse:
                with st.spinner("Retrieving DAC evidence…"):
                    try:
                        r = api("GET", "/api/v1/dac-evidence",
                                params={"report_ids": ",".join(dac_report_ids)})
                        result = r.json() if r.status_code == 200 else {}
                        st.session_state["dac_results"] = result
                        st.session_state["dac_report_ids"] = dac_report_ids
                    except Exception as e:
                        st.error(str(e))
                        return

            result = st.session_state.get("dac_results", {})
            evidence = result.get("evidence", {})
            chunk_counts = result.get("chunk_counts", {})

            # ── Radar chart ────────────────────────────────────────────────
            st.markdown("#### Evidence Coverage Radar")
            st.caption(
                "Score = relative volume of evidence passages found for each criterion "
                "(RAG-based proxy — not an AI-generated quality rating)."
            )

            fig_radar = go.Figure()
            for rid in dac_report_ids:
                counts = chunk_counts.get(rid, {c: 0 for c in DAC_CRITERIA})
                max_c  = max(counts.values()) or 1
                scores = [round((counts.get(c, 0) / max_c) * 10, 1) for c in DAC_CRITERIA]
                rep_title = next(
                    (r.get("title","")[:30] for r in all_reps if r["report_id"] == rid), rid[:8]
                )
                fig_radar.add_trace(go.Scatterpolar(
                    r=scores + [scores[0]],
                    theta=DAC_LABELS + [DAC_LABELS[0]],
                    name=rep_title,
                    fill="toself",
                    opacity=0.6,
                ))

            fig_radar.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 10])),
                showlegend=True if len(dac_report_ids) > 1 else False,
                margin=dict(t=30, b=20, l=30, r=30),
                height=380,
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_radar, use_container_width=True)

            # ── AI Summary per criterion ──────────────────────────────────
            st.markdown("#### AI Summary by Criterion")
            if st.button("✨ Generate AI Summary across criteria", type="primary", use_container_width=True, key="dac_ai_btn"):
                dac_rids = st.session_state.get("dac_report_ids", [])
                with st.spinner("Claude is analysing DAC evidence across selected reports…"):
                    try:
                        # Build context from evidence passages
                        ev = evidence
                        context_lines = []
                        for crit, label in zip(DAC_CRITERIA, DAC_LABELS):
                            passages = ev.get(crit, [])[:5]
                            if passages:
                                context_lines.append(f"\n### {label.upper()}\n")
                                for p in passages:
                                    context_lines.append(f"[{p.get('report_title','')}]: {p.get('text','')[:400]}")
                        context_text = "\n".join(context_lines)
                        payload = {
                            "query": f"Provide a concise analytical summary of the evaluation evidence for each of the 5 OECD-DAC criteria: Relevance, Effectiveness, Efficiency, Impact, and Sustainability. For each criterion, identify the key patterns and cross-cutting findings across the selected reports. Use the evidence provided.\n\nEVIDENCE:\n{context_text}",
                            "report_ids": dac_rids,
                        }
                        r_ai = api("POST", "/api/v1/synthesize", json=payload)
                        if r_ai.status_code == 200:
                            st.session_state["dac_ai_summary"] = r_ai.json().get("answer", "")
                        else:
                            st.error(f"AI summary failed: {r_ai.status_code}")
                    except Exception as e:
                        st.error(str(e))

            if st.session_state.get("dac_ai_summary"):
                st.markdown(
                    '<div style="background:white;border:1px solid #e5e7eb;border-radius:8px;' +
                    'padding:1rem 1.2rem;margin:0.5rem 0 1rem;font-size:0.87rem;line-height:1.7;">',
                    unsafe_allow_html=True,
                )
                st.markdown(st.session_state["dac_ai_summary"])
                st.markdown('</div>', unsafe_allow_html=True)
                if st.button("Clear summary", key="dac_clear_sum"):
                    del st.session_state["dac_ai_summary"]
                    st.rerun()

            st.divider()

            # ── Evidence browser ───────────────────────────────────────────
            st.markdown("#### Evidence Browser")
            st.caption("Click a criterion tab to read verbatim passages from the reports.")

            tab_labels = [f"{lbl} ({len(evidence.get(c,[]))})"
                          for c, lbl in zip(DAC_CRITERIA, DAC_LABELS)]
            tabs = st.tabs(tab_labels)

            for tab, criterion, label in zip(tabs, DAC_CRITERIA, DAC_LABELS):
                with tab:
                    passages = evidence.get(criterion, [])
                    if not passages:
                        st.caption("No passages found for this criterion in the selected reports.")
                        continue
                    for p in passages[:15]:  # cap at 15 per criterion
                        st.markdown(f"""
                        <div class="dac-card">
                          <div class="passage-title">
                            {p.get("report_title","")}
                          </div>
                          <div class="passage-meta">
                            {p.get("year","")} · {p.get("country","")}
                            &nbsp;·&nbsp; Page ~{p.get("page_hint","")}
                          </div>
                          <div class="dac-quote">{p.get("text","")[:600]}</div>
                        </div>
                        """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Admin tab
# ─────────────────────────────────────────────────────────────────────────────

def show_admin_tab():
    st.markdown("## User Management")
    st.markdown(
        "You are the administrator. Add, deactivate, or remove users. "
        "Changes take effect immediately."
    )

    try:
        resp = api("GET", "/api/v1/admin/users")
        data = resp.json() if resp.status_code == 200 else {}
    except Exception as e:
        st.error(str(e)); return

    users   = data.get("users", [])
    sessions= data.get("active_sessions", [])

    st.markdown(f"### Users ({len(users)}/6 slots)")
    for u in users:
        c1, c2, c3, c4 = st.columns([4, 1, 1, 1])
        with c1:
            rc = "role-admin" if u["role"] == "admin" else "role-user"
            ac = "color:#22c55e" if u["active"] else "color:#ef4444"
            st.markdown(
                f'**{u["display_name"]}** (@{u["username"]})<br>'
                f'<span class="role-badge {rc}">{u["role"]}</span> '
                f'<span style="font-size:.78rem;{ac}">{"● Active" if u["active"] else "● Inactive"}</span>',
                unsafe_allow_html=True,
            )
        with c2:
            st.caption(u.get("created_at","")[:10])
        with c3:
            if u["username"] != st.session_state.username:
                lbl = "Deactivate" if u["active"] else "Activate"
                if st.button(lbl, key=f"tgl_{u['username']}"):
                    r = api("PATCH", f"/api/v1/admin/users/{u['username']}/active",
                            json={"active": not u["active"]})
                    if r.status_code == 200:
                        st.success(r.json()["detail"]); st.rerun()
                    else:
                        st.error(r.json().get("detail","Error"))
        with c4:
            if u["username"] != st.session_state.username:
                if st.button("", key=f"del_{u['username']}"):
                    r = api("DELETE", f"/api/v1/admin/users/{u['username']}")
                    if r.status_code == 200:
                        st.success(r.json()["detail"]); st.rerun()
                    else:
                        st.error(r.json().get("detail","Error"))
        st.divider()

    if sessions:
        st.markdown(f"### Active sessions ({len(sessions)})")
        for s in sessions:
            st.caption(
                f"• {{s['display_name']}} (@{{s['username']}}) — "
                f"logged in {s['login_time'][:19].replace('T',' ')} UTC"
            )

    st.divider()

    st.markdown("### Add new user")
    with st.form("add_user"):
        ca, cb = st.columns(2)
        with ca:
            nu = st.text_input("Username (lowercase, no spaces)", placeholder="sarah.jones")
            np = st.text_input("Temporary password (min 8 chars)", type="password")
        with cb:
            nd = st.text_input("Full name", placeholder="Sarah Jones")
            nr = st.selectbox("Role", ["user", "admin"])
        if st.form_submit_button("Create user", type="primary"):
            if not all([nu, np, nd]):
                st.error("All fields required.")
            elif len(np) < 8:
                st.error("Password must be ≥ 8 characters.")
            else:
                r = api("POST", "/api/v1/admin/users",
                        json={"username": nu, "password": np, "display_name": nd, "role": nr})
                if r.status_code == 200:
                    st.success(f" User '{nu}' created."); st.rerun()
                else:
                    st.error(r.json().get("detail","Error"))

    st.divider()
    st.markdown("### Reset a user's password")
    usernames = [u["username"] for u in users if u["username"] != st.session_state.username]
    if usernames:
        with st.form("reset_pw"):
            cx, cy = st.columns(2)
            with cx:
                pw_user = st.selectbox("User", usernames)
            with cy:
                new_pw = st.text_input("New password", type="password")
            if st.form_submit_button("Reset password"):
                if not new_pw or len(new_pw) < 8:
                    st.error("Password must be ≥ 8 characters.")
                else:
                    r = api("POST", f"/api/v1/admin/users/{pw_user}/password",
                            json={"new_password": new_pw})
                    if r.status_code == 200:
                        st.success(r.json()["detail"])
                    else:
                        st.error(r.json().get("detail","Error"))
    else:
        st.caption("No other users to reset.")

# ─────────────────────────────────────────────────────────────────────────────
# Main app shell
# ─────────────────────────────────────────────────────────────────────────────

def show_main_app():
    is_admin = st.session_state.role == "admin"

    st.markdown(f"""
    <div class="unido-header">
      <div>
        <span class="unido-logo">UNIDO</span>
        <span class="unido-sub">  |  Evaluation Intelligence Platform  ·  IEU / EIO</span>
      </div>
      <div class="user-chip"> {st.session_state.display_name}</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Sidebar ─────────────────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(f"**{st.session_state.display_name}**")
        st.caption(f"@{st.session_state.username} · {st.session_state.role.title()}")
        if st.button("Sign out", use_container_width=True):
            do_logout()
        st.divider()

        st.markdown("### Filters")
        with st.form(key="filter_form"):
            with st.expander("Thematic Area", expanded=False):
                thematic_sel = st.multiselect("Thematic", THEMATIC_AREAS,
                                              label_visibility="collapsed", key="f_thematic")
            with st.expander("SDGs", expanded=False):
                sdg_sel_nums = []
                for row_start in range(1, 18, 3):
                    row_sdgs = list(range(row_start, min(row_start + 3, 18)))
                    cols = st.columns(3)
                    for i, n in enumerate(row_sdgs):
                        with cols[i]:
                            if n in _SDG_B64:
                                st.markdown(
                                    f'<div style="text-align:center;margin-bottom:2px;">'
                                    f'<img src="data:image/png;base64,{_SDG_B64[n]}" '
                                    f'title="SDG {n}: {SDG_NAMES[n]}" '
                                    f'style="width:54px;height:54px;border-radius:6px;'
                                    f'object-fit:cover;display:block;margin:0 auto;" /></div>',
                                    unsafe_allow_html=True,
                                )
                            else:
                                color = SDG_COLORS[n]
                                name_short = SDG_NAMES[n].split()[0]
                                st.markdown(
                                    f'<div style="text-align:center;margin-bottom:2px;">'
                                    f'<div style="display:inline-flex;flex-direction:column;'
                                    f'align-items:center;justify-content:center;'
                                    f'width:54px;height:54px;background:{color};color:white;'
                                    f'font-weight:800;border-radius:6px;font-size:16px;'
                                    f'font-family:Arial,sans-serif;" '
                                    f'title="SDG {n}: {SDG_NAMES[n]}">'
                                    f'<span style="font-size:18px;line-height:1;">{n}</span>'
                                    f'<span style="font-size:7px;font-weight:600;opacity:0.9;">'
                                    f'{name_short[:6].upper()}</span>'
                                    f'</div></div>',
                                    unsafe_allow_html=True,
                                )
                            checked = st.checkbox(
                                SDG_NAMES[n][:14], key=f"sdg_cb_{n}",
                                label_visibility="collapsed",
                            )
                            if checked:
                                sdg_sel_nums.append(n)
                if sdg_sel_nums:
                    badges = "".join(sdg_badge_html(n, 28) for n in sdg_sel_nums)
                    st.markdown(f'<div style="margin-top:4px;">{badges}</div>', unsafe_allow_html=True)
            with st.expander("Year", expanded=False):
                yr_sel = st.selectbox(
                    "Year",
                    ["All years", 2025, 2024, 2023, 2022, 2021],
                    label_visibility="collapsed", key="f_year",
                )
            with st.expander("Evaluation Type", expanded=False):
                eval_type_sel = st.multiselect(
                    "Type",
                    ["Project Evaluation", "Strategic Evaluation", "Country Evaluation",
                     "Synthesis", "Reference Document"],
                    label_visibility="collapsed", key="f_eval_type",
                )
            with st.expander("Region", expanded=False):
                region_sel = st.multiselect(
                    "Region",
                    ["Africa", "Asia", "Europe", "Latin America", "Middle East", "Global"],
                    label_visibility="collapsed", key="f_region",
                )
            st.form_submit_button("Search", use_container_width=True, type="primary")

        filters = {
            "thematic":   thematic_sel,
            "sdgs":       sdg_sel_nums,
            "eval_type":  eval_type_sel,
            "region":     region_sel,
            "years":      [yr_sel] if yr_sel != "All years" else [],
            "year_min":   yr_sel if yr_sel != "All years" else None,
            "year_max":   yr_sel if yr_sel != "All years" else None,
            "dac":        [],
        }

        st.divider()
        st.markdown("### System")
        if st.button("Health check", use_container_width=True):
            try:
                rh = httpx.get(f"{BACKEND_URL}/api/v1/health", timeout=8)
                st.session_state.backend_healthy = rh.json()
            except Exception as e:
                st.session_state.backend_healthy = {"error": str(e)}
        if st.session_state.backend_healthy:
            h = st.session_state.backend_healthy
            if "error" in h:
                st.markdown('<span class="dot dot-red"></span> Unreachable',
                            unsafe_allow_html=True)
            else:
                cls = "dot-green" if h.get("status") == "healthy" else "dot-amber"
                st.markdown(f'<span class="dot {cls}"></span> {h.get("status","").title()}',
                            unsafe_allow_html=True)
                qcls = "dot-green" if h.get("qdrant_connected") else "dot-red"
                st.markdown(f'<span class="dot {qcls}"></span> Qdrant ' +
                            f'{"" if h.get("qdrant_connected") else ""}',
                            unsafe_allow_html=True)
                if h.get("document_count", 0):
                    st.caption(f"{h['document_count']:,} chunks indexed")

    # ── Tabs ──────────────────────────────────────────────────────────────────────────────
    tab_names = ["Search & Browse", "Synthesis", "Visualize", "OECD-DAC"]
    if is_admin:
        tab_names.append("Admin")

    tabs = st.tabs(tab_names)

    with tabs[0]:
        show_search_tab(filters)
    with tabs[1]:
        show_synthesis_tab(filters)
    with tabs[2]:
        show_visualize_tab()
    with tabs[3]:
        show_dac_tab()
    if is_admin:
        with tabs[4]:
            show_admin_tab()

    st.divider()
    st.markdown(
        "<p style='text-align:center;color:#9ca3af;font-size:.72rem;'>"
        "UNIDO IEU Evaluation Intelligence Platform · Internal use only · "
        "Retrieved passages should be verified against source documents before formal citation."
        "</p>",
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────

if not st.session_state.session_token:
    show_login_page()
else:
    show_main_app()
