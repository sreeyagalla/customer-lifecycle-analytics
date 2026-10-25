"""Every scorecard number vs. a recomputation from the KPI definitions."""
import pytest

from cla import analysis
from tests import independent


@pytest.mark.parametrize("segment", ["All", "UK", "International"])
@pytest.mark.parametrize("q", [5, 6, 7, 8])
def test_scorecard_matches_independent(sample_marts, sample_ind, q, segment):
    rows = analysis.scorecard(sample_marts, q, segment)
    lookback = q - 4 - 1
    cur = independent.kpis(sample_ind["cq"], q, lookback, segment)
    ben = independent.kpis(sample_ind["cq"], q - 4, lookback, segment)
    for r in rows:
        if not r["measurable"]:
            continue
        (va, na), (vb, nb) = cur[r["kpi"]], ben[r["kpi"]]
        assert r["a"] == pytest.approx(va, rel=1e-9), r["kpi"]
        assert r["b"] == pytest.approx(vb, rel=1e-9), r["kpi"]
        if r["kpi"] != "new_customers":
            assert (r["n_a"], r["n_b"]) == (na, nb)


def test_measurability_rules(sample_marts):
    by = {(r["current"], r["kpi"]): r for q in (5, 8) for r in analysis.scorecard(sample_marts, q, "All")}
    assert not by[("FY2011 Q1", "new_customers")]["measurable"]      # no history behind FY2010 Q1
    assert not by[("FY2011 Q1", "retention_rate")]["measurable"]
    assert not by[("FY2011 Q4", "activation_rate")]["measurable"]    # 90-day window runs past 9 Dec 2011
    assert by[("FY2011 Q4", "retention_rate")]["measurable"]
    assert by[("FY2011 Q4", "new_customers")]["lookback_quarters"] == 3
