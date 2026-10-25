"""Turn the SQL marts into the numbers the dashboard shows: the lifecycle
scorecard vs. the hindsight benchmark, growth accounting, cohorts, email program
lift vs. the randomized holdout, and the hypothesis registry.

Every number in docs/data.js comes from here. Nothing is typed in by hand."""

from __future__ import annotations

import datetime as dt
import json
import math

import numpy as np
import pandas as pd
from scipy import stats as sps

from . import paths, stats, warehouse

SEGMENTS = ("All", "UK", "International")
FOLLOWUP_DAYS = 90


def load_marts() -> dict[str, pd.DataFrame]:
    con = warehouse.marts_connection()
    names = ("fiscal_quarters", "data_window", "customers", "customer_quarter",
             "lifecycle_quarterly", "cohort_monthly", "data_quality", "stg_email", "build_info")
    return {n: con.execute(f"select * from {n}").df() for n in names}


# ---------------------------------------------------------------- lifecycle KPIs

def _seg(df: pd.DataFrame, segment: str) -> pd.DataFrame:
    return df if segment == "All" else df[df["segment"] == segment]


def kpi_inputs(cq: pd.DataFrame, q: int, lookback: int) -> dict[str, pd.DataFrame]:
    """Customer-level rows behind each KPI for quarter q."""
    rows = cq[cq["qidx"] == q]
    gap = rows["quarters_since_last_active"]
    new = rows[rows["is_active"] & (gap.isna() | (gap > lookback))]
    return {
        "new": new,
        "retention_base": rows[rows["active_prev"]],
        "reactivation_base": rows[rows["active_prev2"] & ~rows["active_prev"]],
        "active": rows[rows["is_active"]],
    }


def scorecard(m: dict[str, pd.DataFrame], current_q: int, segment: str) -> list[dict]:
    """FY2011 quarter vs. the same quarter of FY2010 (hindsight benchmark).
    Lookback for 'new' = the history the benchmark quarter has (like-for-like)."""
    fq = m["fiscal_quarters"].set_index("qidx")
    data_end = pd.Timestamp(m["data_window"]["data_end_date"].iloc[0])
    bench_q = current_q - 4
    lookback = bench_q - 1
    cq = _seg(m["customer_quarter"], segment)
    cur, ben = kpi_inputs(cq, current_q, lookback), kpi_inputs(cq, bench_q, lookback)
    followup_ok = pd.Timestamp(fq.loc[current_q, "end_date_excl"]) - pd.Timedelta(days=1) \
        + pd.Timedelta(days=FOLLOWUP_DAYS) <= data_end
    base = {"segment": segment, "current": fq.loc[current_q, "label"],
            "benchmark": fq.loc[bench_q, "label"], "lookback_quarters": lookback}
    out = []

    def add(kpi, stage, label, unit, measurable, why, res=None, extra=None):
        row = {**base, "kpi": kpi, "stage": stage, "label": label, "unit": unit,
               "measurable": bool(measurable), "note": why}
        if measurable and res is not None:
            row.update({k: _clean(v) for k, v in res.items()})
            row["significant"] = bool(res["p_value"] < 0.05)
        row.update(extra or {})
        out.append(row)

    # Acquisition
    if lookback >= 1:
        c_new, b_new = len(cur["new"]), len(ben["new"])
        never_seen = int(cur["new"]["last_active_before"].isna().sum())
        add("new_customers", "Acquisition", "New customers", "count", True,
            f"No order in the prior {lookback} quarter(s), in both years.",
            stats.poisson_exact(c_new, b_new), {"current_never_seen_before": never_seen})
    else:
        add("new_customers", "Acquisition", "New customers", "count", False,
            "FY2010 Q1 is the first quarter of data, so there is no history to tell new from returning.")

    # Activation
    if lookback < 1:
        add("activation_rate", "Activation", "90-day activation rate", "rate", False,
            "No history behind the benchmark quarter to identify new customers.")
    elif not followup_ok:
        add("activation_rate", "Activation", "90-day activation rate", "rate", False,
            "The 90-day follow-up window runs past the end of the data (9 Dec 2011).")
    else:
        a, b = cur["new"], ben["new"]
        add("activation_rate", "Activation", "90-day activation rate", "rate", True,
            "Share of new customers with a second order on a later day within 90 days.",
            stats.two_proportion(int(a["activated_90d"].sum()), len(a), int(b["activated_90d"].sum()), len(b)))

    # Retention
    if bench_q >= 2:
        a, b = cur["retention_base"], ben["retention_base"]
        add("retention_rate", "Retention", "Quarter-over-quarter retention", "rate", True,
            "Share of last quarter's active customers who ordered again this quarter.",
            stats.two_proportion(int(a["is_active"].sum()), len(a), int(b["is_active"].sum()), len(b)))
    else:
        add("retention_rate", "Retention", "Quarter-over-quarter retention", "rate", False,
            "The benchmark quarter has no prior quarter in the data.")

    # Reactivation
    if bench_q >= 3:
        a, b = cur["reactivation_base"], ben["reactivation_base"]
        add("reactivation_rate", "Reactivation", "Win-back rate (lapsed 1 quarter)", "rate", True,
            "Share of customers active two quarters ago, inactive last quarter, who came back.",
            stats.two_proportion(int(a["is_active"].sum()), len(a), int(b["is_active"].sum()), len(b)))
    else:
        add("reactivation_rate", "Reactivation", "Win-back rate (lapsed 1 quarter)", "rate", False,
            "Needs two quarters of history before the benchmark quarter.")

    # Value
    add("revenue_per_active", "Value", "Net revenue per active customer", "gbp", True,
        "Orders minus cancellations in the quarter, per active customer (Welch t-test).",
        stats.welch(cur["active"]["net_value"].to_numpy(), ben["active"]["net_value"].to_numpy()))
    return out


def _clean(v):
    if isinstance(v, (np.floating, float)):
        return None if math.isnan(v) else float(v)
    if isinstance(v, np.integer):
        return int(v)
    return v


# ---------------------------------------------------------------- email programs

def program_lift(email: pd.DataFrame) -> list[dict]:
    hold = email[email["arm"] == "No E-Mail"]
    out = []
    for arm in ("Mens E-Mail", "Womens E-Mail"):
        t = email[email["arm"] == arm]
        for outcome in ("visit", "conversion", "spend"):
            if outcome == "spend":
                r = stats.welch(t["spend"].to_numpy(), hold["spend"].to_numpy())
            else:
                r = stats.two_proportion(int(t[outcome].sum()), len(t), int(hold[outcome].sum()), len(hold))
            r = {k: _clean(v) for k, v in r.items()}
            r.update(arm=arm, outcome=outcome,
                     incremental_total=r["diff"] * len(t),
                     incremental_ci_low=r["ci_low"] * len(t), incremental_ci_high=r["ci_high"] * len(t))
            out.append(r)
    return out


def segment_lift(email: pd.DataFrame, by: str = "lifecycle_stage", outcome: str = "visit") -> list[dict]:
    out = []
    for level, g in email.groupby(by):
        hold = g[g["arm"] == "No E-Mail"]
        for arm in ("Mens E-Mail", "Womens E-Mail"):
            t = g[g["arm"] == arm]
            r = stats.two_proportion(int(t[outcome].sum()), len(t), int(hold[outcome].sum()), len(hold))
            out.append({"segment_by": by, "level": level, "arm": arm, "outcome": outcome,
                        **{k: _clean(v) for k, v in r.items()}})
    return out


def balance(email: pd.DataFrame) -> list[dict]:
    """Standardized mean differences of pre-email covariates vs. the holdout."""
    X = pd.get_dummies(email[["recency", "history", "mens", "womens", "newbie", "zip_code", "channel"]],
                       columns=["zip_code", "channel"], dtype=float)
    hold = X[email["arm"] == "No E-Mail"]
    out = []
    for arm in ("Mens E-Mail", "Womens E-Mail"):
        t = X[email["arm"] == arm]
        for col in X.columns:
            sd = math.sqrt((t[col].var() + hold[col].var()) / 2)
            out.append({"arm": arm, "covariate": col, "treated_mean": float(t[col].mean()),
                        "holdout_mean": float(hold[col].mean()),
                        "smd": float((t[col].mean() - hold[col].mean()) / sd) if sd else 0.0})
    return out


# ---------------------------------------------------------------- hypothesis registry

def retail_cohort(customers: pd.DataFrame) -> pd.DataFrame:
    h = paths.hypotheses()["retail_cohort"]
    d = customers.copy()
    d["first_order_date"] = pd.to_datetime(d["first_order_date"])
    return d[(d["first_order_date"] >= pd.Timestamp(h["first_order_from"]))
             & (d["first_order_date"] < pd.Timestamp(h["first_order_before"]))].copy()


def run_hypotheses(m: dict[str, pd.DataFrame]) -> list[dict]:
    reg = paths.hypotheses()
    coh = retail_cohort(m["customers"])
    email = m["stg_email"]
    labels = m["fiscal_quarters"].set_index("qidx")["label"]
    out = []
    for h in reg["hypotheses"]:
        row = {"id": h["id"], "family": h["family"], "question": h["question"], "test": h["test"]}
        if h["test"] == "two_proportion" and "group" in h:
            col, (ga, gb) = h["group"], h["groups"]
            vals = coh[col] if col != "early_cancel" else coh["early_cancel_30d"].map(
                {True: ga, False: gb})
            a, b = coh[vals == ga], coh[vals == gb]
            r = stats.two_proportion(int(a[h["outcome"]].sum()), len(a), int(b[h["outcome"]].sum()), len(b))
            row.update(r, effect=f"Activation rate, {ga} minus {gb}", unit="pp", n=len(a) + len(b))
        elif h["test"] == "spearman":
            rho, p = sps.spearmanr(coh[h["x"]], coh[h["y"]])
            row.update(diff=float(rho), p_value=float(p), effect="Spearman rank correlation",
                       unit="rho", n=len(coh))
        elif h["test"] == "chi_square":
            tab = pd.crosstab(coh["first_qidx"].map(labels), coh[h["outcome"]])
            chi2, p, dof, _ = sps.chi2_contingency(tab, correction=False)
            rates = (tab[True] / tab.sum(axis=1)).round(4).to_dict()
            row.update(diff=float(chi2), p_value=float(p), effect=f"Chi-square ({dof} df)",
                       unit="chi2", n=int(tab.to_numpy().sum()), group_rates=rates)
        elif "arms" in h:
            ta, tb = h["arms"]
            a, b = email[email["arm"] == ta], email[email["arm"] == tb]
            if h["test"] == "welch_t":
                r = stats.welch(a[h["outcome"]].to_numpy(), b[h["outcome"]].to_numpy())
                unit = "usd"
            else:
                r = stats.two_proportion(int(a[h["outcome"]].sum()), len(a),
                                         int(b[h["outcome"]].sum()), len(b))
                unit = "pp"
            row.update(r, effect=f"{h['outcome'].title()}: {ta} minus {tb}", unit=unit, n=len(a) + len(b))
        out.append({k: _clean(v) for k, v in row.items()})
    q = stats.bh_adjust([r["p_value"] for r in out])
    for r, qv in zip(out, q):
        r["q_value"] = qv
        r["significant_bh"] = bool(qv < reg["alpha"])
    return out


# ---------------------------------------------------------------- site payload

def records(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime("%Y-%m-%d")
        elif df[c].dtype == object:
            df[c] = df[c].map(lambda v: v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v)
    return json.loads(df.to_json(orient="records"))


def build_payload() -> dict:
    m = load_marts()
    cq = m["customer_quarter"]
    score = [row for seg in SEGMENTS for q in (5, 6, 7, 8) for row in scorecard(m, q, seg)]
    coh = m["cohort_monthly"]
    coh = coh[(coh["segment"] == "All") & (coh["lookback_months"] >= 12)
               & (pd.to_datetime(coh["cohort_month"]) < pd.Timestamp(m["data_window"]["data_end_date"].iloc[0]).to_period("M").to_timestamp())]
    email = m["stg_email"]
    arms = (email.groupby("arm").agg(customers=("row_id", "size"), visit_rate=("visit", "mean"),
                                     conversion_rate=("conversion", "mean"),
                                     spend_per_customer=("spend", "mean")).reset_index())
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": m["build_info"]["source"].iloc[0],
        "data_quality": records(m["data_quality"]),
        "data_window": records(m["data_window"])[0],
        "counts": {"customers": int(len(m["customers"])), "customer_quarters": int(len(cq)),
                   "email_customers": int(len(email))},
        "scorecard": score,
        "quarterly": records(m["lifecycle_quarterly"]),
        "cohorts": records(coh[["cohort_month", "months_since", "cohort_size", "active_share", "partial_month"]]),
        "programs": {"arms": records(arms), "lift": program_lift(email),
                     "segment_lift": segment_lift(email), "balance": balance(email)},
        "hypotheses": run_hypotheses(m),
    }


def write_site_data(payload: dict | None = None) -> dict:
    payload = payload or build_payload()
    out = paths.ROOT / "docs" / "data.js"
    out.parent.mkdir(exist_ok=True)
    text = json.dumps(payload, indent=1, default=str)
    out.write_text(f"// Generated by `cla site` from the SQL marts. Do not edit.\nwindow.DATA = {text};\n",
                   encoding="utf-8")
    return payload
