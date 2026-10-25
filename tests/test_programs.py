import pandas as pd
import pytest
from statsmodels.stats.proportion import proportions_ztest

from cla import analysis, ingest, paths


@pytest.fixture(scope="module")
def email():
    return ingest.read_email()


def test_published_arm_sizes(email):
    assert email["segment"].value_counts().to_dict() == {"Womens E-Mail": 21387, "Mens E-Mail": 21307, "No E-Mail": 21306}


def test_lift_matches_group_means(sample_marts, email):
    lift = analysis.program_lift(sample_marts["stg_email"])
    means = email.groupby("segment")[["visit", "conversion", "spend"]].mean()
    counts = email.groupby("segment")[["visit", "conversion"]].sum()
    n = email["segment"].value_counts()
    for r in lift:
        assert r["a"] == pytest.approx(means.loc[r["arm"], r["outcome"]], rel=1e-12)
        assert r["b"] == pytest.approx(means.loc["No E-Mail", r["outcome"]], rel=1e-12)
        if r["outcome"] != "spend":
            _, p = proportions_ztest([counts.loc[r["arm"], r["outcome"]], counts.loc["No E-Mail", r["outcome"]]],
                                     [n[r["arm"]], n["No E-Mail"]])
            assert r["p_value"] == pytest.approx(p, rel=1e-9)
        assert r["incremental_total"] == pytest.approx(r["diff"] * n[r["arm"]])


def test_randomization_balance(sample_marts):
    assert max(abs(b["smd"]) for b in analysis.balance(sample_marts["stg_email"])) < 0.1


def test_segment_lift_partitions_population(sample_marts):
    seg = pd.DataFrame(analysis.segment_lift(sample_marts["stg_email"]))
    assert seg.groupby("arm")["n_a"].sum().to_dict() == {"Mens E-Mail": 21307, "Womens E-Mail": 21387}


def test_hypothesis_registry_reports_every_declared_test(sample_marts):
    out = analysis.run_hypotheses(sample_marts)
    assert [h["id"] for h in out] == [h["id"] for h in paths.hypotheses()["hypotheses"]]
    assert all(h["q_value"] >= h["p_value"] - 1e-15 for h in out)
