"""
Monte Carlo risk analysis for a business case.

A single NPV hides how uncertain it is. Here every estimate becomes a range:
costs tend to overrun more than they underrun, benefits tend to disappoint more
than they surprise, and benefits sometimes start a year late. We replay the
business case thousands of times with random draws from those ranges and read
off the odds:

  P(NPV > 0)   the chance the option pays for itself
  P10/P50/P90  pessimistic / middle / optimistic outcomes
  P(best)      how often each option beats the others in the same draw

The same random draws are shared across options ("common random numbers") so
the comparison is like-for-like: in a bad year for estimates, every option has
a bad year.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .model import Assumptions, Option


@dataclass
class Uncertainty:
    cost_low: float = -0.10       # costs could come in 10% under...
    cost_high: float = 0.30       # ...or 30% over
    benefit_low: float = -0.30    # benefits could fall 30% short...
    benefit_high: float = 0.10    # ...or beat plan by 10%
    delay_probability: float = 0.20  # chance benefits start a year late


def _triangular(u: np.ndarray, low: float, mode: float, high: float) -> np.ndarray:
    """Inverse CDF of a triangular distribution, so we can feed shared uniforms."""
    if high == low:
        return np.full_like(u, mode)
    c = (mode - low) / (high - low)
    return np.where(u < c, low + np.sqrt(u * (high - low) * (mode - low)),
                    high - np.sqrt((1 - u) * (high - low) * (high - mode)))


def _benefit_annuity(opt: Option, a: Assumptions, delay: int) -> float:
    """Present value of £1/yr of full benefit, given the ramp and a start delay."""
    t = np.arange(a.years + 1)
    since = t - (opt.benefit_start_year + delay) + 1
    profile = np.clip(since / max(opt.ramp_years, 1), 0, 1)
    return float(np.sum(profile / (1 + a.discount_rate) ** t))


def simulate(options: list[Option], a: Assumptions, unc: Uncertainty = Uncertainty(),
             n: int = 10_000, seed: int = 7) -> pd.DataFrame:
    """Return an n x options DataFrame of simulated NPVs."""
    rng = np.random.default_rng(seed)
    u_up, u_y1, u_run, u_ben = (rng.random(n) for _ in range(4))
    delayed = rng.random(n) < unc.delay_probability
    f = 1 / (1 + a.discount_rate) ** np.arange(a.years + 1)
    run_annuity = f[1:].sum()
    out = {}
    for o in options:
        cost_mult = 1 + a.cost_optimism_bias + o.delivery_risk_uplift
        up = o.upfront_cost * (1 + _triangular(u_up, unc.cost_low, 0, unc.cost_high))
        y1 = o.year1_cost * (1 + _triangular(u_y1, unc.cost_low, 0, unc.cost_high))
        run = o.annual_run_cost * (1 + _triangular(u_run, unc.cost_low, 0, unc.cost_high))
        pv_costs = (up + y1 * f[1] + run * run_annuity) * cost_mult
        ben = o.annual_benefit * (1 + _triangular(u_ben, unc.benefit_low, 0, unc.benefit_high)) * (1 - a.benefit_haircut)
        annuity = np.where(delayed, _benefit_annuity(o, a, 1), _benefit_annuity(o, a, 0))
        out[o.name] = ben * annuity - pv_costs
    return pd.DataFrame(out)


def summarise(sims: pd.DataFrame, baseline: str | None = None) -> pd.DataFrame:
    """Odds table per option. Options with no cost (the do-minimum baseline) are excluded from P(best)."""
    cols = [c for c in sims.columns if c != baseline and sims[c].abs().sum() > 0]
    winner = sims[cols].idxmax(axis=1) if cols else pd.Series(dtype=str)
    rows = []
    for c in sims.columns:
        s = sims[c]
        rows.append({"option": c, "p10": s.quantile(0.10), "p50": s.quantile(0.50), "p90": s.quantile(0.90),
                     "mean": s.mean(), "p_positive": (s > 0).mean(),
                     "p_best": (winner == c).mean() if c in cols else np.nan})
    return pd.DataFrame(rows)


def cdf(series: pd.Series, points: int = 200) -> pd.DataFrame:
    """'Probability NPV is at least X' curve: the classic risk S-curve, read right to left."""
    x = np.linspace(series.quantile(0.005), series.quantile(0.995), points)
    s = np.sort(series.to_numpy())
    p_at_least = 1 - np.searchsorted(s, x, side="left") / len(s)
    return pd.DataFrame({"npv": x, "p_at_least": p_at_least})
