import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from appraisal.benefits import AT_RISK, ON_TRACK, benefit_status, load, quarterly, revalidate
from appraisal.model import appraise
from appraisal.report import money
from appraisal.ui import AQUA, BLUE, BLUE_LIGHT, INK, MUTED, ORANGE, RAG, RAG_ICON, assumptions, options, style

st.title("Benefits realisation")
st.markdown("<p class='note'>Most business cases are approved and never looked at again. PRINCE2's first principle, "
            "<b>continued business justification</b>, says a project should be stopped if its case no longer "
            "stacks up. This page checks promised benefits against what has actually landed, and re-forecasts the NPV.</p>",
            unsafe_allow_html=True)

register, tracking, costs = load()
with st.expander("Use your own tracking data"):
    st.caption("Upload CSVs with the same columns as the files in /data. Otherwise the worked example is shown: "
               "the SaaS PPM tool approved in January 2025, reviewed in October 2026.")
    c = st.columns(3)
    f1 = c[0].file_uploader("benefits_register.csv", type="csv")
    f2 = c[1].file_uploader("benefits_tracking.csv", type="csv")
    f3 = c[2].file_uploader("cost_tracking.csv", type="csv")
    if f1 and f2 and f3:
        register, tracking, costs = pd.read_csv(f1), pd.read_csv(f2), pd.read_csv(f3)

status = benefit_status(register, tracking)
q = quarterly(tracking, costs)
v = revalidate(tracking, costs, status, assumptions().discount_rate)
reported = q.benefit_actual.notna().sum()
last_q = q.quarter[q.benefit_actual.notna()].iloc[-1] if reported else "-"

# Risk-adjusted NPV the board approved (from the appraisal page, if the chosen option exists there).
approved = next((appraise(o, assumptions())["npv"] for o in options() if "SaaS" in o.name), None)

realised = status.actual.sum() / status.planned.sum()
verdict = "still justified" if v["still_justified"] else "NO LONGER justified: return to the board"
st.markdown(f"""<div class="rec"><b>Business case {verdict}.</b> {v['quarters_reported']} of {v['quarters_total']} quarters
reported (to {last_q}). Benefits realised: <b>{realised:.0%}</b> of plan. Costs running at <b>{v['cost_run_rate']:.0%}</b> of plan.
Re-forecast NPV <b>{money(v['reforecast_npv'])}</b> against <b>{money(v['original_npv'])}</b> in the delivery plan
{f"and {money(approved)} in the risk-adjusted case the board approved" if approved is not None else ""}.</div>""",
            unsafe_allow_html=True)

c = st.columns(4)
c[0].metric("Benefits realised to date", money(status.actual.sum()), f"{money(status.actual.sum() - status.planned.sum())} vs plan")
c[1].metric("Costs to date", money(q.cost_actual.sum()), f"{money(q.cost_actual.sum() - q.cost_planned[q.cost_actual.notna()].sum())} vs plan",
            delta_color="inverse")
c[2].metric("Forecast lifetime benefit", money(status.forecast_total.sum()), f"{money(status.forecast_gap.sum())} vs plan")
c[3].metric("Re-forecast NPV", money(v["reforecast_npv"]), f"{money(v['reforecast_npv'] - v['original_npv'])} vs plan")

left, right = st.columns([1.4, 1])
with left:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=q.quarter, y=q.cum_benefit_planned, name="Benefits: plan", mode="lines",
                             line=dict(color=AQUA, width=2, dash="dot")))
    fig.add_trace(go.Scatter(x=q.quarter, y=q.cum_benefit_actual, name="Benefits: actual", mode="lines+markers",
                             line=dict(color=AQUA, width=2.5), marker=dict(size=7)))
    fig.add_trace(go.Scatter(x=q.quarter, y=q.cum_cost_planned, name="Costs: plan", mode="lines",
                             line=dict(color=ORANGE, width=2, dash="dot")))
    fig.add_trace(go.Scatter(x=q.quarter, y=q.cum_cost_actual, name="Costs: actual", mode="lines+markers",
                             line=dict(color=ORANGE, width=2.5), marker=dict(size=7)))
    if reported:
        fig.add_vline(x=reported - 1, line=dict(color=MUTED, width=1, dash="dash"))
        fig.add_annotation(x=reported - 1, y=1, yref="paper", text="Today", showarrow=False, xanchor="left",
                           font=dict(color=MUTED, size=11))
    style(fig, 400, hovermode="x unified", title=dict(text="Cumulative benefits and costs: plan vs actual", font=dict(size=15)))
    fig.update_yaxes(tickprefix="£", tickformat=".2s")
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Where the solid benefit line crosses the solid cost line is the real payback point.")
with right:
    s = status.sort_values("realisation")
    fig = go.Figure(go.Bar(
        x=s.realisation, y=s.benefit, orientation="h",
        marker=dict(color=[RAG[r] for r in s.rag], cornerradius=4),
        text=[f"{RAG_ICON[r]} {x:.0%}" for r, x in zip(s.rag, s.realisation)], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}<br>%{x:.0%} of planned benefit realised<extra></extra>"))
    fig.add_vline(x=1, line=dict(color=INK, width=1))
    style(fig, 400, title=dict(text="Realised to date, % of plan", font=dict(size=15)))
    fig.update_xaxes(tickformat=".0%", range=[0, max(1.45, s.realisation.max() * 1.35)])
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"🟢 ≥ {ON_TRACK:.0%} of plan · 🟠 {AT_RISK:.0%}–{ON_TRACK:.0%} · 🔴 below {AT_RISK:.0%}")

st.subheader("Benefits register")
st.dataframe(status.assign(RAG=status.rag.map(lambda r: f"{RAG_ICON[r]} {r}"))[
    ["benefit_id", "benefit", "type", "owner", "RAG", "planned", "actual", "realisation", "recent_ratio",
     "planned_total", "forecast_total", "forecast_gap"]], hide_index=True, use_container_width=True,
    column_config={"benefit_id": "ID", "benefit": "Benefit", "type": "Type", "owner": "Owner",
                   "planned": st.column_config.NumberColumn("Planned to date", format="£%d"),
                   "actual": st.column_config.NumberColumn("Actual to date", format="£%d"),
                   "realisation": st.column_config.NumberColumn("Realised", format="percent"),
                   "recent_ratio": st.column_config.NumberColumn("Last 2 quarters", format="percent"),
                   "planned_total": st.column_config.NumberColumn("Lifetime plan", format="£%d"),
                   "forecast_total": st.column_config.NumberColumn("Lifetime forecast", format="£%d"),
                   "forecast_gap": st.column_config.NumberColumn("Forecast gap", format="£%d")})

st.subheader("Actions for the benefits review")
for r in status.sort_values("realisation").itertuples():
    if r.rag == "Red":
        st.markdown(f"- 🔴 **{r.benefit}** ({r.owner}): only {r.realisation:.0%} realised, last two quarters at "
                    f"{r.recent_ratio:.0%}. Forecast shortfall {money(-r.forecast_gap)}. Needs a recovery plan or a "
                    "formal reduction in the benefits baseline.")
    elif r.rag == "Amber":
        trend = "recovering" if r.recent_ratio and r.recent_ratio >= ON_TRACK else "not yet recovering"
        st.markdown(f"- 🟠 **{r.benefit}** ({r.owner}): {r.realisation:.0%} realised, {trend} "
                    f"(last two quarters {r.recent_ratio:.0%}). Confirm the root cause and a date for full run-rate.")
    else:
        st.markdown(f"- 🟢 **{r.benefit}** ({r.owner}): on track at {r.realisation:.0%}.")
if v["cost_run_rate"] > 1.05:
    st.markdown(f"- 🟠 **Costs** are running at {v['cost_run_rate']:.0%} of plan. If that holds, lifetime cost rises by "
                f"{money((v['cost_run_rate'] - 1) * q.cost_planned[q.cost_actual.isna()].sum())}.")
