"""
Builds the worked-example tracking data (fictional) in /data.

Scenario: the board approved "Buy a SaaS PPM tool" in January 2025.
It is now October 2026: 7 of 20 quarters have been reported.

  B1 PMO reporting time saved   - landing slightly ahead of plan
  B2 Contractor spend removed   - started 3 quarters late (contract notice period)
  B3 Late change requests down  - stuck at about half of plan (adoption problem)
  Costs                         - running about 8% over plan

Run:  python -m appraisal.example_data
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .benefits import DATA_DIR

QUARTERS = [f"{y}-Q{q}" for y in range(2025, 2030) for q in range(1, 5)]
REPORTED = 7  # 2025-Q1 .. 2026-Q3

REGISTER = [
    # id, benefit, type, owner, measure, annual_target_gbp
    ("B1", "PMO reporting time saved", "Non-cashable (efficiency)", "Head of PMO",
     "Analyst days per month spent compiling reports", 95_000),
    ("B2", "Contractor report production removed", "Cashable", "Finance Business Partner",
     "Contractor invoices for reporting support", 40_000),
    ("B3", "Fewer late change requests", "Cost avoidance", "Programme Director",
     "Change requests raised after stage gate, x average cost", 30_000),
]


def main() -> None:
    rng = np.random.default_rng(11)
    DATA_DIR.mkdir(exist_ok=True)
    pd.DataFrame(REGISTER, columns=["benefit_id", "benefit", "type", "owner", "measure", "annual_target_gbp"]) \
        .to_csv(DATA_DIR / "benefits_register.csv", index=False)

    rows = []
    for bid, _, _, _, _, annual in REGISTER:
        for i, q in enumerate(QUARTERS):
            year = i // 4  # 0-based year of operation
            planned = annual / 4 * (0.5 if year == 0 else 1.0)
            actual = np.nan
            if i < REPORTED:
                if bid == "B1":
                    ratio = rng.uniform(0.98, 1.10)
                elif bid == "B2":
                    ratio = 0 if i < 3 else rng.uniform(0.85, 1.0)
                else:
                    ratio = rng.uniform(0.40, 0.55)
                actual = round(planned * ratio)
            rows.append({"benefit_id": bid, "quarter": q, "planned": round(planned), "actual": actual})
    pd.DataFrame(rows).to_csv(DATA_DIR / "benefits_tracking.csv", index=False)

    cost_rows = []
    for i, q in enumerate(QUARTERS):
        planned = 48_000 / 4 + (25_000 if i == 0 else 0) + (60_000 / 4 if i < 4 else 0)
        actual = round(planned * rng.uniform(1.04, 1.12)) if i < REPORTED else np.nan
        cost_rows.append({"quarter": q, "planned": round(planned), "actual": actual})
    pd.DataFrame(cost_rows).to_csv(DATA_DIR / "cost_tracking.csv", index=False)
    print("wrote benefits_register.csv, benefits_tracking.csv, cost_tracking.csv")


if __name__ == "__main__":
    main()
