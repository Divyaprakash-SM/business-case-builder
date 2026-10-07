import streamlit as st

from appraisal.document import DEFAULT_NARRATIVE, build
from appraisal.model import appraise
from appraisal.report import summary
from appraisal.ui import assumptions, options

a = assumptions()
opts = options()
real = [o.name for o in opts if appraise(o, a)["pv_costs"] > 0]

st.title("Business case document")
st.markdown("<p class='note'>Generates a board-ready Word document structured on the HM Treasury <b>Five Case Model</b> "
            "(strategic, economic, commercial, financial, management). The numbers come straight from the appraisal "
            "and risk simulation, so the document and the model can never disagree.</p>", unsafe_allow_html=True)

if not real:
    st.info("Add at least one option with costs on the Options appraisal page.")
    st.stop()

pref = st.session_state.get("preferred", real[0])
c = st.columns([1, 1])
chosen = c[0].selectbox("Recommended option", real, index=real.index(pref) if pref in real else 0)
author = c[1].text_input("Prepared by", "")

st.markdown("##### Narrative sections")
st.caption("The economic and financial cases are written for you from the numbers. Edit the parts only a person can write.")
n = {}
l, r = st.columns(2)
n["strategic"] = l.text_area("Strategic case: why change is needed", DEFAULT_NARRATIVE["strategic"], height=150)
n["objectives"] = r.text_area("Objectives (SMART)", DEFAULT_NARRATIVE["objectives"], height=150)
n["commercial"] = l.text_area("Commercial case: how it will be procured", DEFAULT_NARRATIVE["commercial"], height=130)
n["management"] = r.text_area("Management case: governance and delivery", DEFAULT_NARRATIVE["management"], height=130)

title = st.session_state.title
docx_bytes = build(title, opts, a, chosen, n, author=author)
md = summary(title, opts, a, preferred=chosen)

b1, b2, _ = st.columns([1, 1, 2])
b1.download_button("Download Word document", docx_bytes, "business_case.docx", type="primary", use_container_width=True,
                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
b2.download_button("Download one-page summary (Markdown)", md, "business_case_summary.md", "text/markdown",
                   use_container_width=True)

st.markdown("##### One-page summary preview")
with st.container(border=True):
    st.markdown(md.replace("\n## ", "\n#### ").replace("# ", "### ", 1))
