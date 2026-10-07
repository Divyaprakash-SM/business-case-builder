import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from appraisal.model import appraise, cash_flows, scenarios, tornado, value_for_money
from appraisal.report import money, years
from appraisal.ui import AQUA, BLUE, BLUE_LIGHT, INK, MUTED, ORANGE, assumptions, colours, options, options_editor, style

a = assumptions()

st.title("Business Case Builder")
st.markdown("<p class='note'>Compare investment options the way a finance director or HM Treasury would: "
            "net present value, benefit-cost ratio, payback, and how fragile each answer is.</p>",
            unsafe_allow_html=True)

st.subheader("1 · Define the options")
options_editor()
st.caption("Edit any cell, or add a row. Benefits are measured against doing the minimum, so the do-minimum "
           "row is the baseline at zero. Global assumptions are in the sidebar.")

opts = options()
if not opts:
    st.stop()
colour = colours(opts)
res = pd.DataFrame([appraise(o, a) for o in opts])
real = res[res.pv_costs > 0]
best = real.sort_values("npv", ascending=False).iloc[0] if not real.empty else res.iloc[0]
st.session_state.preferred = best.option

st.subheader("2 · Results")
st.markdown(f"""<div class="rec"><b>Recommended: {best.option}</b><br>
NPV <b>{money(best.npv)}</b> · benefit-cost ratio <b>{best.bcr:.2f}</b> ({value_for_money(best.bcr).lower()} value for money) ·
pays back in <b>{years(best.payback_years)}</b> · benefits could fall <b>{best.benefit_headroom:.0%}</b> before it stops paying for itself.
</div>""", unsafe_allow_html=True)

left, right = st.columns([1, 1.25])
with left:
    r = res.sort_values("npv")
    fig = go.Figure(go.Bar(x=r.npv, y=r.option, orientation="h",
                           marker=dict(color=[colour[o] for o in r.option], cornerradius=4),
                           text=[money(v) for v in r.npv], textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}<br>NPV £%{x:,.0f}<extra></extra>"))
    style(fig, 300, title=dict(text="Net present value by option", font=dict(size=15)))
    fig.update_xaxes(tickprefix="£", tickformat=".2s", range=[min(0, r.npv.min() * 1.3), max(1, r.npv.max() * 1.3)])
    st.plotly_chart(fig, use_container_width=True)
with right:
    show = res[res.pv_costs > 0].assign(vfm=lambda d: d.bcr.map(value_for_money))
    st.dataframe(show[["option", "npv", "bcr", "vfm", "roi", "irr", "payback_years", "discounted_payback_years"]],
                 hide_index=True, use_container_width=True,
                 column_config={"option": "Option", "npv": st.column_config.NumberColumn("NPV", format="£%d"),
                                "bcr": st.column_config.NumberColumn("BCR", format="%.2f"), "vfm": "Value for money",
                                "roi": st.column_config.NumberColumn("ROI", format="percent"),
                                "irr": st.column_config.NumberColumn("IRR", format="percent"),
                                "payback_years": st.column_config.NumberColumn("Payback (yrs)", format="%.1f"),
                                "discounted_payback_years": st.column_config.NumberColumn("Discounted payback", format="%.1f")})
    st.caption("The do-minimum baseline is left out of the table because every figure is measured against it. "
               "NPV: value created, in today's money. BCR: £ of benefit per £1 of cost. IRR: the return the option "
               "earns. Discounted payback: break-even once the time value of money is counted.")

st.subheader("3 · Look inside an option")
choices = list(real.option) or [o.name for o in opts]
pick = st.selectbox("Option", choices, index=choices.index(best.option) if best.option in choices else 0)
opt = next(o for o in opts if o.name == pick)
cf = cash_flows(opt, a)
rr = appraise(opt, a)
tab_cf, tab_sens = st.tabs(["Cash flow & payback", "Sensitivity & scenarios"])

with tab_cf:
    c = st.columns(4)
    c[0].metric("PV of costs", money(rr["pv_costs"]))
    c[1].metric("PV of benefits", money(rr["pv_benefits"]))
    c[2].metric("NPV", money(rr["npv"]))
    c[3].metric("Payback", years(rr["payback_years"]))
    l, r = st.columns(2)
    with l:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=cf.year, y=-cf.costs, name="Costs", marker=dict(color=ORANGE, cornerradius=4),
                             customdata=cf.costs, hovertemplate="Year %{x}<br>Costs £%{customdata:,.0f}<extra></extra>"))
        fig.add_trace(go.Bar(x=cf.year, y=cf.benefits, name="Benefits", marker=dict(color=AQUA, cornerradius=4),
                             hovertemplate="Year %{x}<br>Benefits £%{y:,.0f}<extra></extra>"))
        style(fig, 340, barmode="relative", bargap=.35, title=dict(text="Money out and in, by year", font=dict(size=15)))
        fig.update_yaxes(tickprefix="£", tickformat=".2s"); fig.update_xaxes(dtick=1, title="Year")
        st.plotly_chart(fig, use_container_width=True)
    with r:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=cf.year, y=cf.cumulative_net, name="Cumulative (cash)", mode="lines+markers",
                                 line=dict(color=BLUE, width=2), marker=dict(size=8)))
        fig.add_trace(go.Scatter(x=cf.year, y=cf.cumulative_pv_net, name="Cumulative (discounted)", mode="lines+markers",
                                 line=dict(color=BLUE, width=2, dash="dot"), marker=dict(size=8)))
        if rr["payback_years"]:
            fig.add_vline(x=rr["payback_years"], line=dict(color=MUTED, width=1, dash="dash"),
                          annotation_text=f"Payback {rr['payback_years']:.1f} yrs", annotation_position="top left")
        style(fig, 340, hovermode="x unified", title=dict(text="When does it pay for itself?", font=dict(size=15)))
        fig.update_yaxes(tickprefix="£", tickformat=".2s"); fig.update_xaxes(dtick=1, title="Year")
        st.plotly_chart(fig, use_container_width=True)
    with st.expander("Year-by-year cash flow table"):
        money_cols = ["costs", "benefits", "net", "pv_costs", "pv_benefits", "pv_net", "cumulative_net", "cumulative_pv_net"]
        st.dataframe(cf, hide_index=True, use_container_width=True,
                     column_config={k: st.column_config.NumberColumn(format="£%d") for k in money_cols}
                     | {"discount_factor": st.column_config.NumberColumn(format="%.3f")})

with tab_sens:
    l, r = st.columns([1.3, 1])
    with l:
        t = tornado(opt, a)
        base = t.base_npv.iloc[0]
        fig = go.Figure()
        fig.add_trace(go.Bar(y=t.driver, x=t.npv_low_input - base, base=base, orientation="h", name="Input −20%",
                             marker=dict(color=BLUE_LIGHT, cornerradius=4), customdata=t.npv_low_input,
                             hovertemplate="%{y} −20%<br>NPV £%{customdata:,.0f}<extra></extra>"))
        fig.add_trace(go.Bar(y=t.driver, x=t.npv_high_input - base, base=base, orientation="h", name="Input +20%",
                             marker=dict(color=BLUE, cornerradius=4), customdata=t.npv_high_input,
                             hovertemplate="%{y} +20%<br>NPV £%{customdata:,.0f}<extra></extra>"))
        fig.add_vline(x=base, line=dict(color=INK, width=1))
        style(fig, 340, barmode="overlay", title=dict(text="Which estimate matters most? (±20% each)", font=dict(size=15)))
        fig.update_xaxes(tickprefix="£", tickformat=".2s", title="NPV")
        st.plotly_chart(fig, use_container_width=True)
        top = t.sort_values("range", ascending=False).iloc[0]
        st.caption(f"The widest bar is **{top.driver.lower()}**: a ±20% error there moves NPV by {money(top.range)}. "
                   "That is the number to validate before asking for approval.")
    with r:
        sc = scenarios(opt, a)
        st.markdown("##### Scenarios")
        st.dataframe(sc[["scenario", "npv", "bcr", "payback_years"]], hide_index=True, use_container_width=True,
                     column_config={"scenario": "Scenario", "npv": st.column_config.NumberColumn("NPV", format="£%d"),
                                    "bcr": st.column_config.NumberColumn("BCR", format="%.2f"),
                                    "payback_years": st.column_config.NumberColumn("Payback (yrs)", format="%.1f")})
        st.caption("Pessimistic adds 20 points of cost uplift and benefit haircut; optimistic removes 10.")
        st.markdown("##### Break-even")
        st.markdown(f"Benefits can fall **{rr['benefit_headroom']:.0%}** below estimate before NPV hits zero.")
