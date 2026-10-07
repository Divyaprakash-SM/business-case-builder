"""
Benefits realisation: is the business case still valid after approval?

PRINCE2's first principle is *continued business justification*: a project
should stop if its business case no longer stacks up. Most organisations approve
a business case and never look at it again. This module compares what was
promised with what has actually landed, quarter by quarter, and re-forecasts
the NPV using the real numbers.

Inputs (CSV):
  benefits_register.csv  one row per benefit: owner, type, measure, annual target
  benefits_tracking.csv  per benefit per quarter: planned and actual (£)
  cost_tracking.csv      per quarter: planned and actual cost (£)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ON_TRACK = 0.90   # >= 90% of planned benefit realised to date => Green
AT_RISK = 0.70    # 70-90% => Amber; below => Red


def load(data_dir: Path = DATA_DIR) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (pd.read_csv(data_dir / "benefits_register.csv"),
            pd.read_csv(data_dir / "benefits_tracking.csv"),
            pd.read_csv(data_dir / "cost_tracking.csv"))


def rag(ratio: float) -> str:
    if pd.isna(ratio):
        return "Not started"
    return "Green" if ratio >= ON_TRACK else "Amber" if ratio >= AT_RISK else "Red"


def benefit_status(register: pd.DataFrame, tracking: pd.DataFrame) -> pd.DataFrame:
    """Per benefit: planned vs actual to date, realisation %, RAG and full-life forecast."""
    done = tracking.dropna(subset=["actual"])
    to_date = done.groupby("benefit_id")[["planned", "actual"]].sum()
    total_plan = tracking.groupby("benefit_id").planned.sum().rename("planned_total")
    remaining = tracking[tracking.actual.isna()].groupby("benefit_id").planned.sum().rename("planned_remaining")
    # Recent run-rate matters more than the start: weight the last 2 reported quarters.
    last2 = done.sort_values("quarter").groupby("benefit_id").tail(2).groupby("benefit_id")[["planned", "actual"]].sum()
    recent = (last2.actual / last2.planned.replace(0, np.nan)).rename("recent_ratio")
    df = (register.set_index("benefit_id").join(to_date).join(total_plan).join(remaining).join(recent)
          .fillna({"planned": 0, "actual": 0, "planned_remaining": 0}))
    df["realisation"] = df.actual / df.planned.replace(0, np.nan)
    df["rag"] = df.realisation.map(rag)
    df["forecast_total"] = df.actual + df.planned_remaining * df.recent_ratio.fillna(df.realisation).fillna(1).clip(0, 1.5)
    df["forecast_gap"] = df.forecast_total - df.planned_total
    return df.reset_index()


def quarterly(tracking: pd.DataFrame, costs: pd.DataFrame) -> pd.DataFrame:
    b = tracking.groupby("quarter")[["planned", "actual"]].sum(min_count=1).add_prefix("benefit_")
    c = costs.set_index("quarter")[["planned", "actual"]].add_prefix("cost_")
    q = b.join(c, how="outer").reset_index()
    q["cum_benefit_planned"] = q.benefit_planned.cumsum()
    q["cum_benefit_actual"] = q.benefit_actual.cumsum()
    q["cum_cost_planned"] = q.cost_planned.cumsum()
    q["cum_cost_actual"] = q.cost_actual.cumsum()
    return q


def revalidate(tracking: pd.DataFrame, costs: pd.DataFrame, status: pd.DataFrame,
               annual_rate: float = 0.035) -> dict:
    """Original NPV vs re-forecast NPV from actuals to date plus a run-rate forecast for the rest."""
    q = quarterly(tracking, costs)
    qr = (1 + annual_rate) ** 0.25 - 1
    f = 1 / (1 + qr) ** np.arange(len(q))

    ratio_by_benefit = status.set_index("benefit_id").recent_ratio.fillna(status.set_index("benefit_id").realisation).fillna(1)
    t = tracking.copy()
    t["forecast"] = np.where(t.actual.notna(), t.actual,
                             t.planned * t.benefit_id.map(ratio_by_benefit).clip(0, 1.5))
    ben_fc = t.groupby("quarter").forecast.sum().reindex(q.quarter).to_numpy()

    reported = costs.actual.notna()
    overrun = costs.loc[reported, "actual"].sum() / costs.loc[reported, "planned"].sum() if reported.any() else 1.0
    cost_fc = np.where(costs.actual.notna(), costs.actual, costs.planned * overrun)

    original = float(np.sum((q.benefit_planned.to_numpy() - q.cost_planned.to_numpy()) * f))
    reforecast = float(np.sum((ben_fc - cost_fc) * f))
    return {"original_npv": original, "reforecast_npv": reforecast, "cost_run_rate": overrun,
            "quarters_reported": int(reported.sum()), "quarters_total": len(q),
            "still_justified": reforecast > 0}
