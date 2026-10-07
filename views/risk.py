import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from appraisal.model import appraise
from appraisal.report import money
from appraisal.simulation import Uncertainty, cdf, simulate, summarise
from appraisal.ui import INK, MUTED, assumptions, colours, options, style

a = assumptions()
opts = options()
real = [o for o in opts if appraise(o, a)["pv_costs"] > 0]

st.title("Risk simulation")
st.markdown("<p class='note'>A single NPV pretends we know the future. Here every estimate becomes a range and the "
            "business case is replayed 10,000 times. The question changes from <i>\"what is the NPV?\"</i> to "
            "<i>\"how likely is this to pay off, and which option wins most often?\"</i></p>", unsafe_allow_html=True)

with st.expander("Uncertainty ranges (applied on top of optimism bias)", expanded=False):
    c = st.columns(5)
    cost_low = c[0].slider("Costs: best case", -0.5, 0.0, -0.10, 0.05, format="%.2f")
    cost_high = c[1].slider("Costs: worst case", 0.0, 1.5, 0.30, 0.05, format="%.2f")
    ben_low = c[2].slider("Benefits: worst case", -0.9, 0.0, -0.30, 0.05, format="%.2f")
    ben_high = c[3].slider("Benefits: best case", 0.0, 0.8, 0.10, 0.05, format="%.2f")
    delay = c[4].slider("Chance benefits start a year late", 0.0, 1.0, 0.20, 0.05, format="%.2f")
    st.caption("Ranges are deliberately lopsided: real projects overrun far more often than they underrun.")
unc = Uncertainty(cost_low, cost_high, ben_low, ben_high, delay)

if not real:
    st.info("Add at least one option with costs on the Options appraisal page.")
    st.stop()


@st.cache_data(show_spinner="Running 10,000 simulations…")
def run(opts_key, a_key, unc_key):
    return simulate(real, a, unc)


sims = run(tuple(o.to_dict().values() for o in real).__repr__(), repr(a), repr(unc))
odds = summarise(sims)
colour = colours(opts)
best = odds.sort_values("p_best", ascending=False).iloc[0]
det = {o.name: appraise(o, a)["npv"] for o in real}

st.markdown(f"""<div class="rec"><b>{best.option}</b> is the best option in <b>{best.p_best:.0%}</b> of simulated futures
and pays for itself <b>{best.p_positive:.0%}</b> of the time. The middle outcome (P50) is <b>{money(best.p50)}</b>,
against a single-point estimate of {money(det[best.option])}.</div>""", unsafe_allow_html=True)

c = st.columns(len(real))
for col, o in zip(c, real):
    r = odds.set_index("option").loc[o.name]
    col.metric(o.name, f"{r.p_positive:.0%} chance NPV > 0", f"P10 {money(r.p10)} · P90 {money(r.p90)}", delta_color="off",
               delta_arrow="off")

left, right = st.columns([1.4, 1])
with left:
    fig = go.Figure()
    for o in real:
        cu = cdf(sims[o.name])
        fig.add_trace(go.Scatter(x=cu.npv, y=cu.p_at_least, name=o.name, mode="lines",
                                 line=dict(color=colour[o.name], width=2.5),
                                 hovertemplate=f"{o.name}<br>%{{y:.0%}} chance NPV ≥ £%{{x:,.0f}}<extra></extra>"))
    fig.add_vline(x=0, line=dict(color=INK, width=1))
    fig.add_hline(y=0.8, line=dict(color=MUTED, width=1, dash="dot"),
                  annotation_text="80% confidence", annotation_position="top right")
    style(fig, 400, title=dict(text="How confident can we be in at least this NPV?", font=dict(size=15)))
    fig.update_xaxes(tickprefix="£", tickformat=".2s", title="NPV")
    fig.update_yaxes(tickformat=".0%", range=[0, 1.02], zeroline=False)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Read across from 80% on the left: that's the NPV you can promise with 80% confidence (the P20 value). "
               "The further right a curve sits, the better the option.")
with right:
    fig = go.Figure()
    for o in real:
        s = sims[o.name]
        fig.add_trace(go.Violin(y=s, name=o.name, line_color=colour[o.name], fillcolor=colour[o.name], opacity=.35,
                                box_visible=True, meanline_visible=False, points=False, hoverinfo="skip"))
    fig.add_hline(y=0, line=dict(color=INK, width=1))
    style(fig, 400, showlegend=False, title=dict(text="Spread of outcomes", font=dict(size=15)))
    fig.update_yaxes(tickprefix="£", tickformat=".2s", title="NPV")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Odds table")
st.dataframe(odds.assign(deterministic=odds.option.map(det))[
    ["option", "deterministic", "p10", "p50", "p90", "p_positive", "p_best"]], hide_index=True, use_container_width=True,
    column_config={"option": "Option", "deterministic": st.column_config.NumberColumn("Single-point NPV", format="£%d"),
                   "p10": st.column_config.NumberColumn("P10 (bad case)", format="£%d"),
                   "p50": st.column_config.NumberColumn("P50 (middle)", format="£%d"),
                   "p90": st.column_config.NumberColumn("P90 (good case)", format="£%d"),
                   "p_positive": st.column_config.NumberColumn("Chance NPV > 0", format="percent"),
                   "p_best": st.column_config.NumberColumn("Chance it's the best option", format="percent")})
st.caption("Why is P50 below the single-point NPV? Because the ranges are lopsided: overruns and benefit shortfalls "
           "are bigger and more frequent than the upside. A single-point estimate quietly assumes everything goes to plan.")
