"""
Business Case Builder: entry point.

Run locally:  streamlit run app.py
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from appraisal.model import GREEN_BOOK_RATE
from appraisal.ui import CSS, init_state

st.set_page_config(page_title="Business Case Builder", page_icon="💷", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
init_state()

def load_case() -> None:
    """Runs as a callback, before any widget is drawn, so the sidebar sliders can be updated."""
    up = st.session_state.get("case_upload")
    if up is None:
        return
    data = json.load(up)
    st.session_state.title = data["title"]
    for k, v in data["assumptions"].items():
        st.session_state[f"a_{k}"] = v
    st.session_state.options_df = pd.DataFrame(data["options"])
    st.session_state.editor_version = st.session_state.get("editor_version", 0) + 1


pages = st.navigation([
    st.Page("views/appraisal.py", title="Options appraisal", icon="⚖️", default=True),
    st.Page("views/risk.py", title="Risk simulation", icon="🎲"),
    st.Page("views/benefits.py", title="Benefits realisation", icon="📈"),
    st.Page("views/document.py", title="Business case document", icon="📄"),
])

with st.sidebar:
    st.header("Assumptions")
    st.text_input("Decision being appraised", key="title")
    st.slider("Appraisal period (years)", 3, 15, key="a_years")
    st.slider("Discount rate", 0.0, 0.15, step=0.005, format="%.3f", key="a_discount_rate",
              help=f"{GREEN_BOOK_RATE:.1%} is HM Treasury's Green Book rate. Private firms often use their cost of capital (8-12%).")
    st.slider("Optimism bias: cost uplift", 0.0, 1.0, step=0.05, format="%.2f", key="a_cost_optimism_bias",
              help="Projects almost always cost more than estimated. Every option's costs are uplifted by this much.")
    st.slider("Optimism bias: benefit haircut", 0.0, 0.6, step=0.05, format="%.2f", key="a_benefit_haircut",
              help="Benefits are almost always over-estimated. Every option's benefits are reduced by this much.")
    st.divider()
    st.caption("Value for money (benefit-cost ratio): Poor < 1 · Low 1–1.5 · Medium 1.5–2 · High 2–4 · Very high 4+")

    with st.expander("Save or load a case"):
        case = {"title": st.session_state.title,
                "assumptions": {k[2:]: st.session_state[k] for k in st.session_state if k.startswith("a_")},
                "options": st.session_state.options_df.to_dict("records")}
        st.download_button("Download case (JSON)", json.dumps(case, indent=2, default=float), "business_case.json",
                           "application/json", use_container_width=True)
        st.file_uploader("Load a saved case (also accepts exports from the Process Improvement Lab)", type="json",
                         key="case_upload", on_change=load_case)

pages.run()
