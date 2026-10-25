"""The few statistical tests the scorecard needs, written out explicitly so each
can be checked against scipy / statsmodels in the tests."""

from __future__ import annotations

import numpy as np
from scipy import stats


def two_proportion(x_a: int, n_a: int, x_b: int, n_b: int, alpha: float = 0.05) -> dict:
    """Difference p_a - p_b: pooled z-test p-value, unpooled Wald CI."""
    p_a, p_b = x_a / n_a, x_b / n_b
    pooled = (x_a + x_b) / (n_a + n_b)
    se_pooled = np.sqrt(pooled * (1 - pooled) * (1 / n_a + 1 / n_b))
    z = (p_a - p_b) / se_pooled
    se = np.sqrt(p_a * (1 - p_a) / n_a + p_b * (1 - p_b) / n_b)
    zc = stats.norm.ppf(1 - alpha / 2)
    diff = p_a - p_b
    return {
        "a": p_a, "b": p_b, "n_a": n_a, "n_b": n_b,
        "diff": diff, "ci_low": diff - zc * se, "ci_high": diff + zc * se,
        "rel": p_a / p_b - 1 if p_b else None,
        "p_value": float(2 * stats.norm.sf(abs(z))),
    }


def welch(a: np.ndarray, b: np.ndarray, alpha: float = 0.05) -> dict:
    """Difference of means with Welch's t-test and CI."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    va, vb = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
    diff = a.mean() - b.mean()
    se = np.sqrt(va + vb)
    df = (va + vb) ** 2 / (va**2 / (len(a) - 1) + vb**2 / (len(b) - 1))
    tc = stats.t.ppf(1 - alpha / 2, df)
    return {
        "a": a.mean(), "b": b.mean(), "n_a": len(a), "n_b": len(b),
        "diff": diff, "ci_low": diff - tc * se, "ci_high": diff + tc * se,
        "rel": a.mean() / b.mean() - 1,
        "p_value": float(2 * stats.t.sf(abs(diff / se), df)),
    }


def poisson_exact(c_a: int, c_b: int, alpha: float = 0.05) -> dict:
    """Compare two counts over equal exposure: exact conditional binomial test.
    The CI is for the relative change (rate ratio - 1)."""
    res = stats.binomtest(c_a, c_a + c_b, 0.5)
    lo, hi = res.proportion_ci(1 - alpha, method="exact")
    return {
        "a": c_a, "b": c_b, "n_a": c_a, "n_b": c_b,
        "diff": c_a - c_b,
        "rel": c_a / c_b - 1,
        "rel_ci_low": lo / (1 - lo) - 1, "rel_ci_high": hi / (1 - hi) - 1,
        "p_value": float(res.pvalue),
    }


def bh_adjust(p_values: list[float]) -> list[float]:
    """Benjamini-Hochberg q-values."""
    p = np.asarray(p_values, float)
    n = len(p)
    order = np.argsort(p)
    ranked = p[order] * n / np.arange(1, n + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.minimum(q, 1.0)
    return out.tolist()
