"""Run with:  pytest -q"""

import io

import numpy as np
import pytest

from appraisal.benefits import benefit_status, load, rag, revalidate
from appraisal.document import build
from appraisal.model import (EXAMPLE_ASSUMPTIONS, EXAMPLE_OPTIONS, Assumptions, Option, appraise, cash_flows, irr,
                             npv, payback_year, scenarios, tornado, value_for_money)
from appraisal.report import summary
from appraisal.simulation import Uncertainty, cdf, simulate, summarise

SIMPLE = Option("Simple", upfront_cost=100, year1_cost=0, annual_run_cost=0, annual_benefit=50,
                ramp_years=1, benefit_start_year=1)
NO_DISCOUNT = Assumptions(years=3, discount_rate=0.0)


# --- Core finance ----------------------------------------------------------
def test_npv_by_hand():
    # -100 now, +50 for 3 years, 10% rate: -100 + 45.45 + 41.32 + 37.57 = 24.34
    assert npv(np.array([-100, 50, 50, 50]), 0.10) == pytest.approx(24.34, abs=0.01)


def test_irr_makes_npv_zero():
    flows = np.array([-100, 50, 50, 50])
    r = irr(flows)
    assert npv(flows, r) == pytest.approx(0, abs=1e-4)
    assert r == pytest.approx(0.2338, abs=1e-3)


def test_irr_none_when_never_pays_back():
    assert irr(np.array([-100, 10, 10])) is None or irr(np.array([-100, 10, 10])) < 0


def test_payback_interpolates():
    cf = cash_flows(SIMPLE, NO_DISCOUNT)  # cumulative: -100, -50, 0, 50
    assert payback_year(cf.cumulative_net) == pytest.approx(2.0)


def test_appraise_simple_case():
    r = appraise(SIMPLE, NO_DISCOUNT)
    assert r["npv"] == pytest.approx(50)
    assert r["bcr"] == pytest.approx(1.5)
    assert r["roi"] == pytest.approx(0.5)


def test_optimism_bias_and_risk_uplift_raise_costs():
    a = Assumptions(years=3, discount_rate=0.0, cost_optimism_bias=0.2)
    risky = Option(**{**SIMPLE.to_dict(), "delivery_risk_uplift": 0.3})
    assert cash_flows(SIMPLE, a).costs.sum() == pytest.approx(120)
    assert cash_flows(risky, a).costs.sum() == pytest.approx(150)


def test_benefit_ramp():
    o = Option("Ramp", 0, 0, 0, 100, ramp_years=2, benefit_start_year=1)
    assert cash_flows(o, Assumptions(years=3, discount_rate=0)).benefits.tolist() == [0, 50, 100, 100]


@pytest.mark.parametrize("bcr,band", [(0.8, "Poor"), (1.2, "Low"), (1.7, "Medium"), (3, "High"), (5, "Very high")])
def test_value_for_money_bands(bcr, band):
    assert value_for_money(bcr) == band


def test_tornado_benefit_is_most_sensitive_in_example():
    saas = EXAMPLE_OPTIONS[1]
    t = tornado(saas, EXAMPLE_ASSUMPTIONS).sort_values("range", ascending=False)
    assert t.iloc[0].driver == "Annual benefit"


def test_scenarios_are_ordered():
    sc = scenarios(EXAMPLE_OPTIONS[1], EXAMPLE_ASSUMPTIONS).set_index("scenario").npv
    assert sc["Pessimistic"] < sc["Base"] < sc["Optimistic"]


def test_risk_uplift_flips_the_recommendation():
    """The worked example's key point: without delivery-risk uplift, in-house looks best."""
    no_uplift = [Option(**{**o.to_dict(), "delivery_risk_uplift": 0}) for o in EXAMPLE_OPTIONS]
    best = lambda opts: max(opts[1:], key=lambda o: appraise(o, EXAMPLE_ASSUMPTIONS)["npv"]).name
    assert best(no_uplift) == "Build in-house dashboard"
    assert best(EXAMPLE_OPTIONS) == "Buy a SaaS PPM tool"


# --- Simulation ------------------------------------------------------------
def test_zero_uncertainty_reproduces_deterministic_npv():
    sims = simulate(EXAMPLE_OPTIONS, EXAMPLE_ASSUMPTIONS, Uncertainty(0, 0, 0, 0, 0), n=50)
    for o in EXAMPLE_OPTIONS:
        assert sims[o.name].iloc[0] == pytest.approx(appraise(o, EXAMPLE_ASSUMPTIONS)["npv"], rel=1e-9)


def test_simulation_is_reproducible_and_probabilities_valid():
    s1 = simulate(EXAMPLE_OPTIONS, EXAMPLE_ASSUMPTIONS, n=2000)
    s2 = simulate(EXAMPLE_OPTIONS, EXAMPLE_ASSUMPTIONS, n=2000)
    assert s1.equals(s2)
    odds = summarise(s1).dropna(subset=["p_best"])
    assert odds.p_best.sum() == pytest.approx(1.0)
    assert ((odds.p_positive >= 0) & (odds.p_positive <= 1)).all()


def test_lopsided_ranges_pull_p50_below_point_estimate():
    saas = EXAMPLE_OPTIONS[1]
    s = simulate([saas], EXAMPLE_ASSUMPTIONS)[saas.name]
    assert s.median() < appraise(saas, EXAMPLE_ASSUMPTIONS)["npv"]


def test_cdf_is_decreasing():
    c = cdf(simulate([EXAMPLE_OPTIONS[1]], EXAMPLE_ASSUMPTIONS, n=3000).iloc[:, 0])
    assert (np.diff(c.p_at_least) <= 1e-12).all()


# --- Benefits realisation --------------------------------------------------
def test_benefit_rag_thresholds():
    assert rag(0.95) == "Green" and rag(0.8) == "Amber" and rag(0.5) == "Red"


def test_example_benefits_tell_the_intended_story():
    register, tracking, costs = load()
    s = benefit_status(register, tracking).set_index("benefit_id")
    assert s.loc["B1", "rag"] == "Green"
    assert s.loc["B3", "rag"] == "Red"
    assert s.loc["B2", "recent_ratio"] > s.loc["B2", "realisation"]  # B2 is recovering
    v = revalidate(tracking, costs, s.reset_index())
    assert v["cost_run_rate"] > 1.0
    assert v["reforecast_npv"] < v["original_npv"]
    assert v["still_justified"]


# --- Outputs ---------------------------------------------------------------
def test_summary_and_word_document_build():
    md = summary("Test", EXAMPLE_OPTIONS, EXAMPLE_ASSUMPTIONS)
    assert "## Recommendation" in md and "Buy a SaaS PPM tool" in md
    docx_bytes = build("Test", EXAMPLE_OPTIONS, EXAMPLE_ASSUMPTIONS, "Buy a SaaS PPM tool")
    from docx import Document
    text = "\n".join(p.text for p in Document(io.BytesIO(docx_bytes)).paragraphs)
    for section in ["Strategic case", "Economic case", "Commercial case", "Financial case", "Management case"]:
        assert section in text
