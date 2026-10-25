import numpy as np
import pytest
from scipy import stats as sps
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import confint_proportions_2indep, proportions_ztest

from cla import stats


@pytest.mark.parametrize("xa,na,xb,nb", [(267, 21307, 122, 21306), (40, 300, 55, 310), (5, 50, 1, 60)])
def test_two_proportion_matches_statsmodels(xa, na, xb, nb):
    r = stats.two_proportion(xa, na, xb, nb)
    _, p = proportions_ztest([xa, xb], [na, nb])
    lo, hi = confint_proportions_2indep(xa, na, xb, nb, method="wald", compare="diff")
    assert r["p_value"] == pytest.approx(p, rel=1e-9)
    assert (r["ci_low"], r["ci_high"]) == pytest.approx((lo, hi), rel=1e-9)
    assert r["diff"] == pytest.approx(xa / na - xb / nb)


def test_welch_matches_scipy():
    rng = np.random.default_rng(7)
    a, b = rng.exponential(3, 400), rng.exponential(2.5, 350)
    r = stats.welch(a, b)
    ref = sps.ttest_ind(a, b, equal_var=False)
    ci = ref.confidence_interval(0.95)
    assert r["p_value"] == pytest.approx(ref.pvalue, rel=1e-9)
    assert (r["ci_low"], r["ci_high"]) == pytest.approx((ci.low, ci.high), rel=1e-9)


def test_poisson_exact_is_conditional_binomial():
    r = stats.poisson_exact(979, 940)
    assert r["p_value"] == pytest.approx(sps.binomtest(979, 1919, 0.5).pvalue, rel=1e-12)
    assert r["rel_ci_low"] < r["rel"] < r["rel_ci_high"]


def test_bh_matches_statsmodels():
    p = [0.001, 0.04, 0.03, 0.5, 0.2, 0.0001, 0.049]
    assert stats.bh_adjust(p) == pytest.approx(multipletests(p, method="fdr_bh")[1].tolist(), rel=1e-12)
