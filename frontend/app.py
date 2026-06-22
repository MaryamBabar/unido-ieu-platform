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
import json
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
    page_icon="🔍",
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

SDG_ICON_URL = "https://sdgs.un.org/sites/default/files/goals/E-WEB-Goal-{n:02d}.png"

def sdg_badge_html(n: int, size: int = 36) -> str:
    """Returns HTML for an SDG badge — official icon with colour fallback."""
    color = SDG_COLORS.get(n, "#888")
    url = SDG_ICON_URL.format(n=n)
    return (
        f'<img src="{url}" title="SDG {n}: {SDG_NAMES.get(n,"")}" '
        f'width="{size}" height="{size}" style="border-radius:4px;margin:2px;vertical-align:middle;" '
        f'onerror="this.outerHTML=\'<span title=&quot;SDG {n}: {SDG_NAMES.get(n,"")}&quot; '
        f'style=&quot;display:inline-flex;align-items:center;justify-content:center;'
        f'width:{size}px;height:{size}px;background:{color};color:white;font-weight:700;'
        f'border-radius:4px;font-size:{max(9,size//3)}px;margin:2px;&quot;>{n}</span>\'">'
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
  .main .block-container { padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1280px; }

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
    border-radius: 8px; padding: 1rem 1.2rem; margin-bottom: 0.7rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  }
  .report-title { font-weight: 600; color: var(--dark); font-size: 0.97rem; }
  .report-meta  { color: var(--muted); font-size: 0.8rem; margin: 0.2rem 0 0.4rem; }
  .tag {
    display: inline-block; border-radius: 999px; font-size: 0.72rem;
    font-weight: 600; padding: 0.15rem 0.55rem; margin: 2px;
  }
  .tag-blue  { background: #e0f2fe; color: #0369a1; }
  .tag-green { background: #dcfce7; color: #166534; }
  .tag-amber { background: #fef3c7; color: #92400e; }
  .tag-gray  { background: #f3f4f6; color: #374151; }

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
  .stButton > button { border-radius: 6px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────────────────────

for k, v in {
    "session_token": None, "username": None,
    "display_name": None, "role": None,
    "all_reports": None,          # cached report list
    "lessons_cache": {},          # report_id -> {lessons, recommendations}
    "synth_history": [],          # synthesis chat history
    "backend_healthy": None,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

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
        try:
            r = api("GET", "/api/v1/reports/list")
            if r.status_code == 200:
                st.session_state.all_reports = r.json().get("reports", [])
            else:
                st.session_state.all_reports = []
        except Exception:
            st.session_state.all_reports = []

def load_lessons(report_ids: list[str]) -> list[dict]:
    try:
        r = api("GET", "/api/v1/lessons", params={"report_ids": ",".join(report_ids)})
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

def make_excel(reports_data: list[dict]) -> bytes:
    rows_l, rows_r = [], []
    for rep in reports_data:
        meta = {
            "Report Title":    rep.get("title", ""),
            "Year":            rep.get("year", ""),
            "Country":         rep.get("country", ""),
            "Region":          rep.get("region", ""),
            "Thematic Area":   rep.get("thematic_category", ""),
        }
        for lesson in rep.get("lessons_learned", []):
            rows_l.append({**meta, "Lesson Learned": lesson})
        for rec in rep.get("recommendations", []):
            rows_r.append({**meta, "Recommendation": rec})

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_l = pd.DataFrame(rows_l) if rows_l else pd.DataFrame(
            columns=["Report Title","Year","Country","Region","Thematic Area","Lesson Learned"])
        df_r = pd.DataFrame(rows_r) if rows_r else pd.DataFrame(
            columns=["Report Title","Year","Country","Region","Thematic Area","Recommendation"])
        df_l.to_excel(writer, sheet_name="Lessons Learned",    index=False)
        df_r.to_excel(writer, sheet_name="Recommendations",    index=False)
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
                    st.error(f"❌ {msg}")
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
# TAB 1 — Search & Browse
# ─────────────────────────────────────────────────────────────────────────────

def show_search_tab(filters: dict):
    load_reports()
    all_reps = st.session_state.all_reports or []

    # ── Apply filters ────────────────────────────────────────────────────────
    filtered = all_reps
    if filters["thematic"]:
        filtered = [r for r in filtered if r.get("thematic_category") in filters["thematic"]]
    if filters["sdgs"]:
        filtered = [r for r in filtered
                    if any(s in (r.get("sdgs") or []) for s in filters["sdgs"])]
    if filters["year_min"] or filters["year_max"]:
        ymin = filters["year_min"] or 0
        ymax = filters["year_max"] or 9999
        filtered = [r for r in filtered
                    if ymin <= (r.get("year") or 0) <= ymax]
    if filters["eval_type"]:
        filtered = [r for r in filtered if r.get("evaluation_type") in filters["eval_type"]]
    if filters["region"]:
        filtered = [r for r in filtered if r.get("region") in filters["region"]]

    # ── SDG all-17 legend ────────────────────────────────────────────────────
    st.markdown("#### SDG Reference Icons")
    show_sdg_legend()
    st.divider()

    # ── Controls row ─────────────────────────────────────────────────────────
    col_count, col_refresh, col_export = st.columns([3, 1, 1])
    with col_count:
        n_total = len(all_reps)
        n_shown = len(filtered)
        if n_total == 0:
            st.info("No reports indexed yet. Add PDFs and run the ingestion script.")
        else:
            st.markdown(f"**{n_shown}** of **{n_total}** reports")
    with col_refresh:
        if st.button("🔄 Refresh", use_container_width=True):
            load_reports(force=True)
            st.rerun()
    with col_export:
        if filtered:
            if st.button("📥 Export to Excel", type="primary", use_container_width=True):
                with st.spinner("Fetching lessons & recommendations…"):
                    rid_list = [r["report_id"] for r in filtered]
                    lessons_data = load_lessons(rid_list)
                if lessons_data:
                    excel_bytes = make_excel(lessons_data)
                    st.download_button(
                        label="⬇ Download Excel",
                        data=excel_bytes,
                        file_name="UNIDO_Lessons_Recommendations.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
                else:
                    st.warning("No lessons or recommendations found for the selected reports.")

    if not filtered:
        return

    # ── Report cards ─────────────────────────────────────────────────────────
    for rep in filtered:
        title    = rep.get("title", "Unknown")
        year     = rep.get("year", "")
        country  = rep.get("country", "")
        region   = rep.get("region", "")
        thematic = rep.get("thematic_category", "")
        etype    = rep.get("evaluation_type", "")
        donor    = rep.get("donor", "")
        sdgs     = rep.get("sdgs") or []
        rid      = rep.get("report_id", "")

        badges_html = sdg_badges_row(sdgs, 28)
        thematic_badge = f'<span class="tag tag-blue">{thematic}</span>' if thematic else ""
        etype_badge    = f'<span class="tag tag-gray">{etype}</span>'    if etype    else ""
        donor_badge    = f'<span class="tag tag-green">{donor}</span>'    if donor    else ""

        st.markdown(f"""
        <div class="report-card">
          <div class="report-title">{title}</div>
          <div class="report-meta">
            {year} &nbsp;·&nbsp; {country}
            {"&nbsp;·&nbsp; " + region if region else ""}
          </div>
          <div style="margin:0.3rem 0;">
            {thematic_badge}{etype_badge}{donor_badge}
          </div>
          <div style="margin-top:0.4rem;">{badges_html}</div>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("📋 Lessons Learned & Recommendations"):
            with st.spinner("Loading…"):
                data = load_lessons([rid])
            if data:
                rep_data = data[0]
                col_l, col_r = st.columns(2)
                with col_l:
                    st.markdown("**Lessons Learned**")
                    lessons = rep_data.get("lessons_learned", [])
                    if lessons:
                        for i, lesson in enumerate(lessons, 1):
                            st.markdown(f"**{i}.** {lesson}")
                    else:
                        st.caption("No lessons extracted from this section.")
                with col_r:
                    st.markdown("**Recommendations**")
                    recs = rep_data.get("recommendations", [])
                    if recs:
                        for i, rec in enumerate(recs, 1):
                            st.markdown(f"**{i}.** {rec}")
                    else:
                        st.caption("No recommendations extracted from this section.")
            else:
                st.caption("No structured data found for this report yet.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — Synthesis (RAG — passages only, no LLM)
# ─────────────────────────────────────────────────────────────────────────────

def show_synthesis_tab(filters: dict):
    load_reports()
    all_reps = st.session_state.all_reports or []

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
            st.markdown(f"**Q:** *{item['query']}*")
            for p in item.get("passages", []):
                score = p.get("reranker_score", 0)
                st.markdown(f"""
                <div class="passage-card">
                  <div class="passage-title">
                    {p.get("report_title","")}
                    <span class="score-pill">relevance {score:.2f}</span>
                  </div>
                  <div class="passage-meta">
                    {p.get("year","")} · {p.get("country","")}
                    &nbsp;·&nbsp; Section: {p.get("section_type","").replace("_"," ").title()}
                  </div>
                  <div class="passage-text">{p.get("chunk_text","")[:500]}…</div>
                </div>
                """, unsafe_allow_html=True)
            st.divider()

        # Example chips
        examples = [
            "What lessons emerge on stakeholder engagement?",
            "What sustainability challenges were identified?",
            "How is gender mainstreaming assessed?",
            "What recommendations relate to project design?",
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
            # Build thematic filter if set
            payload = {
                "query": query.strip(),
                "filters": {
                    "dac_criteria":       filters.get("dac", []),
                    "sdgs":               filters.get("sdgs", []),
                    "thematic_categories": filters.get("thematic", []),
                    "year_min":            filters.get("year_min"),
                    "year_max":            filters.get("year_max"),
                },
            }
            with st.spinner("Searching portfolio…"):
                try:
                    r = api("POST", "/api/v1/query", json=payload)
                    if r.status_code == 200:
                        data = r.json()
                        passages = data.get("passages", [])
                        st.session_state.synth_history.append({
                            "query":   query.strip(),
                            "passages": passages,
                        })
                        st.rerun()
                    else:
                        st.error(f"Backend error {r.status_code}")
                except httpx.ConnectError:
                    st.error(f"Cannot reach backend at {BACKEND_URL}.")
                except Exception as e:
                    st.error(str(e))

        st.info(
            "💡 **AI Synthesis** (generates a written answer across reports) can be enabled "
            "by adding your Anthropic API key to `.env`. Currently showing raw retrieved passages.",
            icon="ℹ️",
        )

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — Visualize
# ─────────────────────────────────────────────────────────────────────────────

def show_visualize_tab():
    try:
        r = api("GET", "/api/v1/stats")
        if r.status_code != 200:
            st.error("Could not load portfolio stats.")
            return
        stats = r.json()
    except Exception as e:
        st.error(f"Backend error: {e}")
        return

    total_docs  = stats.get("total_documents", 0)
    total_chunks= stats.get("total_chunks", 0)
    by_year     = stats.get("documents_by_year", {})
    by_thematic = stats.get("documents_by_thematic", {})
    by_sdg      = stats.get("documents_by_sdg", {})
    by_dac      = stats.get("documents_by_dac", {})

    # ── Stat cards ────────────────────────────────────────────────────────────
    sdg_count     = len([v for v in by_sdg.values() if v > 0])
    thematic_count= len(by_thematic)

    c1, c2, c3, c4 = st.columns(4)
    for col, num, lbl in [
        (c1, total_docs,   "Total Reports"),
        (c2, total_chunks, "Total Chunks Indexed"),
        (c3, sdg_count,    "SDGs Covered"),
        (c4, thematic_count,"Thematic Areas"),
    ]:
        col.markdown(
            f'<div class="stat-card"><div class="stat-num">{num}</div>'
            f'<div class="stat-lbl">{lbl}</div></div>',
            unsafe_allow_html=True,
        )

    if total_docs == 0:
        st.info("No reports indexed yet — ingest PDFs to see charts.")
        return

    st.divider()

    # ── SDG icon grid ─────────────────────────────────────────────────────────
    st.markdown("#### SDG Coverage")
    sdg_badge_grid = ""
    for n in range(1, 18):
        count = by_sdg.get(f"SDG {n}", 0)
        opacity = "1.0" if count > 0 else "0.25"
        sdg_badge_grid += (
            f'<span style="display:inline-flex;flex-direction:column;align-items:center;'
            f'margin:4px;opacity:{opacity};" title="SDG {n}: {SDG_NAMES[n]} — {count} reports">'
            f'{sdg_badge_html(n, 48)}'
            f'<span style="font-size:10px;color:#6b7280;margin-top:2px;">{count}</span>'
            f'</span>'
        )
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;gap:2px;">{sdg_badge_grid}</div>',
        unsafe_allow_html=True,
    )

    st.divider()

    # ── Charts row 1 ──────────────────────────────────────────────────────────
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("#### Thematic Area Distribution")
        if by_thematic:
            fig = px.pie(
                names=list(by_thematic.keys()),
                values=list(by_thematic.values()),
                color_discrete_sequence=px.colors.qualitative.Safe,
                hole=0.35,
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(
                showlegend=False, margin=dict(t=10, b=10, l=10, r=10),
                height=320, paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.markdown("#### Reports by Year")
        if by_year:
            years = sorted(by_year.keys())
            fig = go.Figure(go.Bar(
                x=years, y=[by_year[y] for y in years],
                marker_color="#009EDB",
                text=[by_year[y] for y in years],
                textposition="outside",
            ))
            fig.update_layout(
                margin=dict(t=10, b=10, l=10, r=10),
                height=320, paper_bgcolor="rgba(0,0,0,0)",
                xaxis_title="Year", yaxis_title="Reports",
            )
            st.plotly_chart(fig, use_container_width=True)

    # ── Charts row 2 ──────────────────────────────────────────────────────────
    col_c, col_d = st.columns(2)

    with col_c:
        st.markdown("#### SDG Coverage (Top 10)")
        if by_sdg:
            top_sdg = sorted(by_sdg.items(), key=lambda x: -x[1])[:10]
            sdg_labels = [x[0] for x in top_sdg]
            sdg_vals   = [x[1] for x in top_sdg]
            sdg_colors = [SDG_COLORS.get(int(l.split()[-1]), "#009EDB") for l in sdg_labels]
            fig = go.Figure(go.Bar(
                y=sdg_labels, x=sdg_vals,
                orientation="h",
                marker_color=sdg_colors,
                text=sdg_vals, textposition="outside",
            ))
            fig.update_layout(
                margin=dict(t=10, b=10, l=10, r=10),
                height=340, paper_bgcolor="rgba(0,0,0,0)",
                xaxis_title="Reports",
            )
            st.plotly_chart(fig, use_container_width=True)

    with col_d:
        st.markdown("#### DAC Criteria Coverage")
        if by_dac:
            dac_keys = [k.replace("_"," ").title() for k in by_dac.keys()]
            dac_vals = list(by_dac.values())
            fig = go.Figure(go.Bar(
                x=dac_keys, y=dac_vals,
                marker_color=DAC_COLORS[:len(dac_keys)],
                text=dac_vals, textposition="outside",
            ))
            fig.update_layout(
                margin=dict(t=10, b=10, l=10, r=10),
                height=340, paper_bgcolor="rgba(0,0,0,0)",
                yaxis_title="Reports with evidence",
            )
            st.plotly_chart(fig, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — OECD-DAC Analysis
# ─────────────────────────────────────────────────────────────────────────────

def show_dac_tab():
    load_reports()
    all_reps = st.session_state.all_reports or []

    if not all_reps:
        st.info("No reports indexed yet.")
        return

    st.markdown(
        "Cross-portfolio analysis across the 5 OECD-DAC criteria — "
        "Relevance, Effectiveness, Efficiency, Impact, Sustainability. "
        "Click any criterion to browse verbatim evidence passages from the underlying reports."
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
                if st.button("🗑", key=f"del_{u['username']}"):
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
                f"• {s['display_name']} (@{s['username']}) — "
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
                    st.success(f"✅ User '{nu}' created."); st.rerun()
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
        <span class="unido-sub"> &nbsp;|&nbsp; Evaluation Intelligence Platform &nbsp;·&nbsp; IEU / EIO</span>
      </div>
      <div class="user-chip">👤 {st.session_state.display_name}</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(f"**{st.session_state.display_name}**")
        st.caption(f"@{st.session_state.username} · {st.session_state.role.title()}")
        if st.button("Sign out", use_container_width=True):
            do_logout()
        st.divider()

        st.markdown("### Filters")
        with st.expander("Thematic Area", expanded=False):
            thematic_sel = st.multiselect("Thematic", THEMATIC_AREAS,
                                          label_visibility="collapsed", key="f_thematic")
        with st.expander("SDGs", expanded=False):
            sdg_sel_nums = []
            # 3-column icon grid — click icon to toggle
            for row_start in range(1, 18, 3):
                row_sdgs = list(range(row_start, min(row_start + 3, 18)))
                cols = st.columns(3)
                for i, n in enumerate(row_sdgs):
                    with cols[i]:
                        color = SDG_COLORS[n]
                        url   = SDG_ICON_URL.format(n=n)
                        # Show the official UN SDG icon
                        st.markdown(
                            f'<a title="SDG {n}: {SDG_NAMES[n]}">'
                            f'<img src="{url}" width="52" style="border-radius:5px;display:block;margin:auto;" '
                            f'onerror="this.outerHTML=\'<div style=&quot;width:52px;height:52px;background:{color};'
                            f'color:white;font-weight:700;border-radius:5px;display:flex;align-items:center;'
                            f'justify-content:center;font-size:14px;margin:auto;&quot;>{n}</div>\'">'
                            f'</a>',
                            unsafe_allow_html=True,
                        )
                        checked = st.checkbox(
                            f"{n}", key=f"sdg_cb_{n}",
                            label_visibility="visible",
                        )
                        if checked:
                            sdg_sel_nums.append(n)
            if sdg_sel_nums:
                st.caption(f"Selected: {', '.join(f'SDG {n}' for n in sdg_sel_nums)}")
            if st.button("Clear SDGs", key="clear_sdgs", use_container_width=True):
                for n in range(1, 18):
                    st.session_state[f"sdg_cb_{n}"] = False
                st.rerun()
        with st.expander("Evaluation Type", expanded=False):
            eval_type_sel = st.multiselect(
                "Type",
                ["Project Evaluation", "Thematic Evaluation", "Country Evaluation",
                 "Synthesis", "Reference Document"],
                label_visibility="collapsed", key="f_eval_type",
            )
        with st.expander("Region", expanded=False):
            region_sel = st.multiselect(
                "Region",
                ["Africa", "Asia", "Europe", "Latin America", "Middle East", "Global"],
                label_visibility="collapsed", key="f_region",
            )
        with st.expander("Year Range", expanded=False):
            yr = st.slider("Year", 2000, 2025, (2010, 2025), key="f_year")

        with st.expander("DAC Criteria (synthesis filter)", expanded=False):
            dac_sel = st.multiselect(
                "DAC",
                ["Relevance", "Coherence", "Effectiveness", "Efficiency",
                 "Impact", "Sustainability"],
                label_visibility="collapsed", key="f_dac",
            )

        filters = {
            "thematic":   thematic_sel,
            "sdgs":       sdg_sel_nums,
            "eval_type":  eval_type_sel,
            "region":     region_sel,
            "year_min":   yr[0] if yr[0] > 2000 else None,
            "year_max":   yr[1] if yr[1] < 2025 else None,
            "dac":        dac_sel,
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
                st.markdown(f'<span class="dot {qcls}"></span> Qdrant '
                            f'{"✓" if h.get("qdrant_connected") else "✗"}',
                            unsafe_allow_html=True)
                if h.get("document_count", 0):
                    st.caption(f"{h['document_count']:,} chunks indexed")

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_names = ["🔍 Search & Browse", "🤝 Synthesis", "📊 Visualize", "🎯 OECD-DAC"]
    if is_admin:
        tab_names.append("⚙️ Admin")

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
