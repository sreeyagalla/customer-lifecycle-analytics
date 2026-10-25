"""The live demo page: every number it shows must come from docs/data.js, and
data.js must equal an independent recomputation from the raw public files."""
import json
import re

import pandas as pd
import pytest
from scipy import stats as sps

from cla import ingest, paths
from tests import independent

DOCS = paths.ROOT / "docs"


@pytest.fixture(scope="module")
def payload():
    text = (DOCS / "data.js").read_text(encoding="utf-8")
    return json.loads(text[text.index("{"): text.rindex("}") + 1])


def test_page_has_no_hardcoded_figures():
    html = (DOCS / "index.html").read_text(encoding="utf-8")
    visible = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S)
    visible = re.sub(r"<[^>]+>", " ", visible)
    allowed = [r"FY20\d\d", r"\b(19|20)\d\d\b", r"\b95%", r"\bQ[1-4]\b", r"\b\d ·", r"\b12\+ months",
               r"CC BY 4\.0", r"\b1 Dec\b", r"\b1-9\b"]
    for pat in allowed:
        visible = re.sub(pat, " ", visible)
    leftovers = re.findall(r"\d[\d,.]*%?", visible)
    assert leftovers == [], f"hardcoded numbers in page text: {leftovers}"


def test_payload_is_from_full_data(payload):
    assert payload["source"] == "full"
    assert {"scorecard", "quarterly", "cohorts", "programs", "hypotheses", "data_quality"} <= payload.keys()


@pytest.fixture(scope="module")
def full_ind():
    if not paths.RETAIL_PARQUET.exists():
        pytest.skip("full retail data not landed (run `cla fetch` and `cla land`)")
    return independent.pipeline(pd.read_parquet(paths.RETAIL_PARQUET))


def test_published_line_count(payload):
    assert payload["data_quality"][0]["n"] == 1_067_371


def test_every_scorecard_number_matches_raw_recomputation(payload, full_ind):
    for r in payload["scorecard"]:
        if not r["measurable"]:
            continue
        q = int(r["current"][-1]) + 4
        cur = independent.kpis(full_ind["cq"], q, r["lookback_quarters"], r["segment"])[r["kpi"]]
        ben = independent.kpis(full_ind["cq"], q - 4, r["lookback_quarters"], r["segment"])[r["kpi"]]
        assert r["a"] == pytest.approx(cur[0], rel=1e-9), (r["current"], r["segment"], r["kpi"])
        assert r["b"] == pytest.approx(ben[0], rel=1e-9), (r["current"], r["segment"], r["kpi"])


def test_growth_chart_matches_raw_recomputation(payload, full_ind):
    cq = full_ind["cq"]
    counts = cq.groupby(["qidx", "status"]).size().unstack(fill_value=0)
    for r in (x for x in payload["quarterly"] if x["segment"] == "All"):
        assert r["new_customers"] == counts.loc[r["qidx"], "new"]
        assert r["retained_customers"] == counts.loc[r["qidx"], "retained"]
        assert r["reactivated_customers"] == counts.loc[r["qidx"], "reactivated"]


def test_program_numbers_match_raw_csv(payload):
    email = ingest.read_email()
    hold = email[email["segment"] == "No E-Mail"]
    for r in payload["programs"]["lift"]:
        t = email[email["segment"] == r["arm"]]
        assert r["a"] == pytest.approx(t[r["outcome"]].mean(), rel=1e-12)
        assert r["b"] == pytest.approx(hold[r["outcome"]].mean(), rel=1e-12)
        if r["outcome"] == "spend":
            assert r["p_value"] == pytest.approx(sps.ttest_ind(t["spend"], hold["spend"], equal_var=False).pvalue, rel=1e-9)
