"""
Business case engine: options appraisal in the style of HM Treasury's Green Book.

Plain-English glossary
----------------------
NPV  Net Present Value. All future benefits minus all costs, with each year's
     money shrunk to what it is worth *today*. £100 in 5 years is worth less than
     £100 now. Positive NPV = the option creates value.
BCR  Benefit-Cost Ratio. Present value of benefits / present value of costs.
     2.0 means every £1 spent returns £2. The Green Book calls 2+ "high value for money".
ROI  Return on Investment, undiscounted: (total benefits - total costs) / total costs.
IRR  Internal Rate of Return: the discount rate at which NPV is exactly zero.
     If IRR beats your cost of capital, the option pays for itself.
Payback  The year in which cumulative cash flow turns positive.
Optimism bias  Projects systematically under-estimate cost and over-estimate benefit.
     The Green Book tells appraisers to uplift costs and haircut benefits up front.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

GREEN_BOOK_RATE = 0.035  # HM Treasury social time preference rate, years 0-30


@dataclass
class Option:
    name: str
    upfront_cost: float          # year 0 (build / purchase)
    year1_cost: float            # implementation spend in year 1
    annual_run_cost: float       # licences, support, staff - every year from year 1
    annual_benefit: float        # steady-state annual benefit once fully realised
    ramp_years: int = 2          # years to reach full benefit (linear ramp)
    benefit_start_year: int = 1  # first year any benefit lands
    delivery_risk_uplift: float = 0.0  # extra cost uplift for riskier options (e.g. bespoke builds)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Assumptions:
    years: int = 5                     # appraisal period after year 0
    discount_rate: float = GREEN_BOOK_RATE
    cost_optimism_bias: float = 0.0    # e.g. 0.20 => costs uplifted 20%
    benefit_haircut: float = 0.0       # e.g. 0.15 => benefits reduced 15%


def benefit_profile(opt: Option, years: int) -> np.ndarray:
    """Share of full annual benefit realised in each year 0..years."""
    t = np.arange(years + 1)
    since_start = t - opt.benefit_start_year + 1
    ramp = max(opt.ramp_years, 1)
    return np.clip(since_start / ramp, 0, 1)


def cash_flows(opt: Option, a: Assumptions) -> pd.DataFrame:
    t = np.arange(a.years + 1)
    costs = np.zeros(a.years + 1)
    costs[0] += opt.upfront_cost
    if a.years >= 1:
        costs[1] += opt.year1_cost
    costs[1:] += opt.annual_run_cost
    costs *= 1 + a.cost_optimism_bias + opt.delivery_risk_uplift
    benefits = opt.annual_benefit * benefit_profile(opt, a.years) * (1 - a.benefit_haircut)
    factor = 1 / (1 + a.discount_rate) ** t
    df = pd.DataFrame({"year": t, "costs": costs, "benefits": benefits, "discount_factor": factor})
    df["net"] = df.benefits - df.costs
    df["pv_costs"] = df.costs * factor
    df["pv_benefits"] = df.benefits * factor
    df["pv_net"] = df.net * factor
    df["cumulative_net"] = df.net.cumsum()
    df["cumulative_pv_net"] = df.pv_net.cumsum()
    return df


def npv(net: np.ndarray, rate: float) -> float:
    t = np.arange(len(net))
    return float(np.sum(net / (1 + rate) ** t))


def irr(net: np.ndarray, lo: float = -0.99, hi: float = 10.0, tol: float = 1e-7) -> float | None:
    """Bisection: no external finance library needed. None if NPV never crosses zero."""
    f_lo, f_hi = npv(net, lo), npv(net, hi)
    if np.sign(f_lo) == np.sign(f_hi):
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(net, mid)
        if abs(f_mid) < tol:
            break
        if np.sign(f_mid) == np.sign(f_lo):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return mid


def payback_year(cumulative: pd.Series) -> float | None:
    """First point where cumulative cash flow reaches zero, interpolated within the year."""
    c = cumulative.to_numpy()
    for i in range(1, len(c)):
        if c[i - 1] < 0 <= c[i]:
            return (i - 1) + (-c[i - 1]) / (c[i] - c[i - 1])
    return 0.0 if len(c) and c[0] >= 0 else None


def appraise(opt: Option, a: Assumptions) -> dict:
    cf = cash_flows(opt, a)
    pv_c, pv_b = cf.pv_costs.sum(), cf.pv_benefits.sum()
    total_c, total_b = cf.costs.sum(), cf.benefits.sum()
    return {
        "option": opt.name,
        "npv": pv_b - pv_c,
        "bcr": pv_b / pv_c if pv_c else np.nan,
        "roi": (total_b - total_c) / total_c if total_c else np.nan,
        "irr": irr(cf.net.to_numpy()),
        "payback_years": payback_year(cf.cumulative_net),
        "discounted_payback_years": payback_year(cf.cumulative_pv_net),
        "pv_costs": pv_c,
        "pv_benefits": pv_b,
        # How far benefits could fall before NPV hits zero.
        "benefit_headroom": (pv_b - pv_c) / pv_b if pv_b else np.nan,
    }


def value_for_money(bcr: float) -> str:
    """Department for Transport's value-for-money bands, widely used across UK government."""
    if pd.isna(bcr):
        return "n/a"
    if bcr < 1:
        return "Poor"
    if bcr < 1.5:
        return "Low"
    if bcr < 2:
        return "Medium"
    if bcr < 4:
        return "High"
    return "Very high"


DRIVERS = {
    "upfront_cost": "Upfront cost",
    "year1_cost": "Year-1 implementation cost",
    "annual_run_cost": "Annual running cost",
    "annual_benefit": "Annual benefit",
}


def tornado(opt: Option, a: Assumptions, swing: float = 0.20) -> pd.DataFrame:
    """NPV when each driver moves +/- swing, one at a time. Widest bar = what to scrutinise."""
    base = appraise(opt, a)["npv"]
    rows = []
    for key, label in DRIVERS.items():
        out = {}
        for sign, tag in [(-1, "low"), (1, "high")]:
            o = Option(**{**opt.to_dict(), key: getattr(opt, key) * (1 + sign * swing)})
            out[tag] = appraise(o, a)["npv"]
        rows.append({"driver": label, "npv_low_input": out["low"], "npv_high_input": out["high"],
                     "range": abs(out["high"] - out["low"])})
    rate_rows = {}
    for tag, r in [("low", a.discount_rate * (1 - swing)), ("high", a.discount_rate * (1 + swing))]:
        rate_rows[tag] = appraise(opt, Assumptions(**{**asdict(a), "discount_rate": r}))["npv"]
    rows.append({"driver": "Discount rate", "npv_low_input": rate_rows["low"], "npv_high_input": rate_rows["high"],
                 "range": abs(rate_rows["high"] - rate_rows["low"])})
    df = pd.DataFrame(rows).sort_values("range")
    df["base_npv"] = base
    return df


def scenarios(opt: Option, a: Assumptions) -> pd.DataFrame:
    """Pessimistic / base / optimistic, the way a board usually asks for it."""
    cases = {
        "Pessimistic": dict(cost_optimism_bias=a.cost_optimism_bias + 0.20, benefit_haircut=a.benefit_haircut + 0.20),
        "Base": {},
        "Optimistic": dict(cost_optimism_bias=max(a.cost_optimism_bias - 0.10, -0.5),
                           benefit_haircut=max(a.benefit_haircut - 0.10, -0.5)),
    }
    rows = []
    for name, change in cases.items():
        r = appraise(opt, Assumptions(**{**asdict(a), **change}))
        rows.append({"scenario": name, **r})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Worked example: should the PMO automate its reporting?
# ---------------------------------------------------------------------------
EXAMPLE_TITLE = "Automating monthly PMO reporting across a 40-project portfolio"
EXAMPLE_OPTIONS = [
    Option("Do minimum (keep manual)", 0, 0, 0, 0, 1, 1, 0.0),
    Option("Buy a SaaS PPM tool", 25_000, 60_000, 48_000, 165_000, 2, 1, 0.05),
    Option("Build in-house dashboard", 15_000, 90_000, 22_000, 140_000, 2, 1, 0.40),
]
EXAMPLE_ASSUMPTIONS = Assumptions(years=5, discount_rate=GREEN_BOOK_RATE, cost_optimism_bias=0.15, benefit_haircut=0.10)
