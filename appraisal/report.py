"""One-page business case summary in Markdown, built from the same numbers as the app."""

from __future__ import annotations

import pandas as pd

from .model import Assumptions, Option, appraise, scenarios, tornado, value_for_money


def money(x: float) -> str:
    sign = "-" if x < 0 else ""
    x = abs(x)
    return f"{sign}£{x/1e6:.2f}m" if x >= 1e6 else f"{sign}£{x/1e3:,.0f}k"


def years(x) -> str:
    return "not within period" if x is None or pd.isna(x) else f"{x:.1f} years"


def summary(title: str, options: list[Option], a: Assumptions, preferred: str | None = None) -> str:
    res = pd.DataFrame([appraise(o, a) for o in options])
    real = res[res.pv_costs > 0]
    best = (real.sort_values("npv", ascending=False).iloc[0] if not real.empty else res.iloc[0])
    pick = res.set_index("option").loc[preferred] if preferred else best
    pick_name = preferred or best.option
    opt = next(o for o in options if o.name == pick_name)
    tor = tornado(opt, a).sort_values("range", ascending=False)
    sc = scenarios(opt, a).set_index("scenario")

    lines = [
        f"# Business case: {title}",
        "",
        "## Recommendation",
        f"Proceed with **{pick_name}**. Over {a.years} years it returns a net present value of "
        f"**{money(pick.npv)}**, a benefit-cost ratio of **{pick.bcr:.2f}** "
        f"({value_for_money(pick.bcr).lower()} value for money), and pays back in **{years(pick.payback_years)}**.",
        "",
        f"Benefits could fall by **{pick.benefit_headroom:.0%}** before the option stops paying for itself. "
        f"Even in the pessimistic case (costs +20%, benefits -20%) the NPV is **{money(sc.loc['Pessimistic', 'npv'])}**.",
        "",
        "## Options compared",
        "",
        "| Option | NPV | BCR | Value for money | ROI | IRR | Payback |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in res.itertuples():
        irr = "n/a" if r.irr is None or pd.isna(r.irr) else f"{r.irr:.0%}"
        bcr = "baseline" if r.pv_costs == 0 else f"{r.bcr:.2f}"
        roi = "baseline" if r.pv_costs == 0 else f"{r.roi:.0%}"
        lines.append(f"| {r.option} | {money(r.npv)} | {bcr} | {value_for_money(r.bcr) if r.pv_costs else '-'} | "
                     f"{roi} | {irr} | {years(r.payback_years) if r.pv_costs else '-'} |")
    lines += [
        "",
        "## Assumptions",
        f"- Appraisal period: {a.years} years after year 0; discount rate {a.discount_rate:.1%} "
        "(HM Treasury Green Book social time preference rate).",
        f"- Optimism bias: costs uplifted {a.cost_optimism_bias:.0%}, benefits reduced {a.benefit_haircut:.0%}.",
        f"- Benefits ramp up over {opt.ramp_years} year(s) from year {opt.benefit_start_year}.",
        "- Extra delivery-risk uplift on costs, by option: "
        + ("; ".join(f"{o.name} {o.delivery_risk_uplift:.0%}" for o in options if o.delivery_risk_uplift) or "none")
        + ".",
        "",
        "## What could change the answer",
        f"The NPV is most sensitive to **{tor.iloc[0].driver.lower()}** "
        f"(a ±20% swing moves NPV by {money(tor.iloc[0].range)}), then **{tor.iloc[1].driver.lower()}**. "
        "These are the estimates to firm up before approval.",
        "",
        "| Scenario | NPV | BCR | Payback |",
        "|---|---|---|---|",
    ]
    for name, r in sc.iterrows():
        lines.append(f"| {name} | {money(r.npv)} | {r.bcr:.2f} | {years(r.payback_years)} |")
    return "\n".join(lines) + "\n"
