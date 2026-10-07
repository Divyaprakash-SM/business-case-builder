"""Shared Streamlit helpers: styling, chart theme and the options/assumptions held in session state."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .model import EXAMPLE_ASSUMPTIONS, EXAMPLE_OPTIONS, EXAMPLE_TITLE, Assumptions, Option

BLUE, BLUE_LIGHT, ORANGE, AQUA = "#2a78d6", "#b7d3f6", "#eb6834", "#1baf7a"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e0"
SERIES = ["#9a9993", BLUE, ORANGE, AQUA, "#4a3aa7", "#e87ba4"]  # fixed order; do-minimum grey
RAG = {"Green": "#0ca30c", "Amber": "#fab219", "Red": "#d03b3b", "Not started": "#9a9993"}
RAG_ICON = {"Green": "🟢", "Amber": "🟠", "Red": "🔴", "Not started": "⚪"}

COLS = {"name": "Option", "upfront_cost": "Upfront cost (£)", "year1_cost": "Year-1 implementation (£)",
        "annual_run_cost": "Annual running cost (£)", "annual_benefit": "Annual benefit at full run-rate (£)",
        "ramp_years": "Years to full benefit", "benefit_start_year": "Benefits start (year)",
        "delivery_risk_uplift": "Delivery-risk cost uplift"}

CSS = """
<style>
  .block-container {padding-top: 2rem; max-width: 1400px;}
  [data-testid="stMetricValue"] {font-size: 1.7rem; font-weight: 650;}
  [data-testid="stMetricLabel"] p {font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: #52514e;}
  .note {font-size:.92rem; color:#52514e;}
  .rec {border-left: 4px solid #1c5cab; background:#f3f2ee; padding: 14px 18px; border-radius: 6px; margin: 4px 0 18px;}
  h1 {font-weight: 700; letter-spacing: -.02em;}
</style>
"""


def style(fig: go.Figure, height: int = 360, **kw) -> go.Figure:
    top = 40
    if "title" in kw:  # title on its own line above the legend, never overlapping it
        kw["title"] = {**kw["title"], "x": 0.01, "xanchor": "left", "y": 0.985, "yanchor": "top"}
        top = 78
    fig.update_layout(template="plotly_white", height=height, margin=dict(l=10, r=10, t=top, b=10),
                      font=dict(family="Inter, Segoe UI, sans-serif", size=13, color=INK),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
                      hoverlabel=dict(bgcolor="white", font_size=12), **kw)
    fig.update_xaxes(showgrid=False, linecolor=GRID, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor=GRID, zeroline=True, zerolinecolor="#bdbcb6", tickfont=dict(color=MUTED))
    return fig


def init_state() -> None:
    ss = st.session_state
    ss.setdefault("title", EXAMPLE_TITLE)
    ss.setdefault("options_df", pd.DataFrame([o.to_dict() for o in EXAMPLE_OPTIONS]))
    for k, v in EXAMPLE_ASSUMPTIONS.__dict__.items():
        ss.setdefault(f"a_{k}", v)


def assumptions() -> Assumptions:
    ss = st.session_state
    return Assumptions(years=ss.a_years, discount_rate=ss.a_discount_rate,
                       cost_optimism_bias=ss.a_cost_optimism_bias, benefit_haircut=ss.a_benefit_haircut)


def options() -> list[Option]:
    df = st.session_state.options_df.dropna(subset=["name"]).fillna(0)
    out = []
    for r in df.to_dict("records"):
        r["ramp_years"], r["benefit_start_year"] = int(r["ramp_years"]), int(r["benefit_start_year"])
        out.append(Option(**r))
    return out


def colours(opts: list[Option]) -> dict[str, str]:
    return {o.name: SERIES[i % len(SERIES)] for i, o in enumerate(opts)}


def options_editor() -> None:
    """Editable options table that survives page changes (edits are committed to session state)."""
    ss = st.session_state
    ss.setdefault("editor_version", 0)
    key = f"opts_editor_{ss.editor_version}"

    def commit():
        delta = ss[key]
        df = ss.options_df.copy()
        inv = {v: k for k, v in COLS.items()}
        for idx, change in delta["edited_rows"].items():
            for col, val in change.items():
                df.loc[df.index[int(idx)], inv.get(col, col)] = val
        if delta["deleted_rows"]:
            df = df.drop(df.index[delta["deleted_rows"]])
        for row in delta["added_rows"]:
            new = {"name": "New option", "upfront_cost": 0, "year1_cost": 0, "annual_run_cost": 0, "annual_benefit": 0,
                   "ramp_years": 2, "benefit_start_year": 1, "delivery_risk_uplift": 0.0}
            new.update({inv.get(c, c): v for c, v in row.items()})
            df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
        ss.options_df = df.reset_index(drop=True)
        ss.editor_version += 1

    st.data_editor(
        ss.options_df.rename(columns=COLS), num_rows="dynamic", use_container_width=True, hide_index=True,
        key=key, on_change=commit,
        column_config={
            COLS["upfront_cost"]: st.column_config.NumberColumn(format="£%d", min_value=0),
            COLS["year1_cost"]: st.column_config.NumberColumn(format="£%d", min_value=0),
            COLS["annual_run_cost"]: st.column_config.NumberColumn(format="£%d", min_value=0),
            COLS["annual_benefit"]: st.column_config.NumberColumn(format="£%d", min_value=0),
            COLS["ramp_years"]: st.column_config.NumberColumn(min_value=1, max_value=10, step=1),
            COLS["benefit_start_year"]: st.column_config.NumberColumn(min_value=0, max_value=10, step=1),
            COLS["delivery_risk_uplift"]: st.column_config.NumberColumn(
                min_value=0.0, max_value=2.0, step=0.05, format="%.2f",
                help="Extra cost uplift for riskier options, e.g. 0.40 for a bespoke build")})
