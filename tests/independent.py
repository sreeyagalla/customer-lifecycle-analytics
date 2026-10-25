"""An independent, pure-pandas re-implementation of the pipeline, written
separately from the SQL. Tests compare the two: if the SQL (or the dashboard
payload built on it) drifts from these definitions, the tests fail."""

from __future__ import annotations

import numpy as np
import pandas as pd

from cla import paths

KEY_COLS = ["invoice", "stock_code", "description", "quantity", "invoice_ts", "unit_price", "customer_id", "country"]


def quarter_of(ts: pd.Series) -> pd.Series:
    ts = pd.to_datetime(ts)
    return ((ts.dt.year - 2009) * 12 + ts.dt.month - 12) // 3 + 1


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    c = paths.spec()["cleaning"]
    r = raw[~((raw["source_sheet"] == c["overlap_sheet"]) & (raw["invoice_ts"] >= pd.Timestamp(c["overlap_from"])))]
    r = r.drop_duplicates(subset=KEY_COLS).copy()
    code = r["stock_code"].astype(str)
    non_merch = code.isin(c["non_merchandise_codes"]) | code.str.startswith(tuple(c["non_merchandise_prefixes"]))
    r["is_merch"] = ~non_merch
    r["inv"] = r["invoice"].astype(str)
    r["line_value"] = r["quantity"] * r["unit_price"]
    return r


def orders(lines: pd.DataFrame) -> pd.DataFrame:
    ok = (lines["customer_id"].notna() & ~lines["inv"].str.startswith("C") & ~lines["inv"].str.startswith("A")
          & lines["is_merch"] & (lines["unit_price"] > 0) & (lines["quantity"] > 0))
    o = (lines[ok].groupby("invoice")
         .agg(customer_id=("customer_id", "first"), order_ts=("invoice_ts", "min"),
              country=("country", "min"), merch_value=("line_value", "sum"))
         .reset_index())
    o = o[o["merch_value"] > 0].copy()
    o["order_date"] = o["order_ts"].dt.normalize()
    o["qidx"] = quarter_of(o["order_ts"])
    return o


def cancellations(lines: pd.DataFrame) -> pd.DataFrame:
    ok = lines["customer_id"].notna() & lines["inv"].str.startswith("C") & lines["is_merch"]
    c = lines[ok].groupby("invoice").agg(customer_id=("customer_id", "first"), ts=("invoice_ts", "min"),
                                         value=("line_value", "sum")).reset_index()
    c["qidx"] = quarter_of(c["ts"])
    return c


def customers(o: pd.DataFrame) -> pd.DataFrame:
    first = o.sort_values(["order_ts", "invoice"]).groupby("customer_id").head(1).set_index("customer_id")
    home = paths.spec()["cleaning"]["home_country"]
    return pd.DataFrame({
        "first_order_date": first["order_date"],
        "first_qidx": first["qidx"],
        "segment": np.where(first["country"] == home, "UK", "International"),
    })


def customer_quarter(o: pd.DataFrame, cancels: pd.DataFrame, cust: pd.DataFrame) -> pd.DataFrame:
    """Customer x quarter (1..8) from first active quarter, with lifecycle flags."""
    act = o[o["qidx"] <= 8].groupby(["customer_id", "qidx"]).agg(
        gross=("merch_value", "sum"), first_date=("order_date", "min")).reset_index()
    canc = cancels.groupby(["customer_id", "qidx"])["value"].sum()
    rows = []
    active_sets = act.groupby("customer_id")["qidx"].apply(set).to_dict()
    for cid, info in cust.iterrows():
        A = active_sets.get(cid, set())
        for q in range(int(info["first_qidx"]), 9):
            before = [a for a in A if a < q]
            rows.append((cid, info["segment"], q, q in A, max(before) if before else np.nan,
                         (q - 1) in A, (q - 2) in A))
    cq = pd.DataFrame(rows, columns=["customer_id", "segment", "qidx", "is_active", "last_before",
                                     "active_prev", "active_prev2"])
    cq = cq.merge(act, on=["customer_id", "qidx"], how="left")
    cq["gross"] = cq["gross"].fillna(0.0)
    cq["cancel"] = [canc.get((c, q), 0.0) for c, q in zip(cq["customer_id"], cq["qidx"])]
    cq["net"] = cq["gross"] + cq["cancel"]
    # second order on a later calendar day within 90 days of the first order of the quarter
    dates = o.groupby("customer_id")["order_date"].apply(lambda s: np.sort(s.unique())).to_dict()
    nxt = []
    for cid, fd in zip(cq["customer_id"], cq["first_date"]):
        if pd.isna(fd):
            nxt.append(pd.NaT)
            continue
        later = dates[cid][dates[cid] > np.datetime64(fd)]
        nxt.append(pd.Timestamp(later[0]) if len(later) else pd.NaT)
    cq["next_date"] = nxt
    cq["activated"] = (cq["next_date"] - cq["first_date"]).dt.days.le(90).fillna(False).astype(bool)
    cq["status"] = np.select(
        [cq["is_active"] & cq["last_before"].isna(), cq["is_active"] & cq["active_prev"], cq["is_active"],
         cq["active_prev"]],
        ["new", "retained", "reactivated", "lapsed"], "dormant")
    return cq


def pipeline(raw: pd.DataFrame) -> dict[str, pd.DataFrame]:
    lines = clean(raw)
    o = orders(lines)
    c = cancellations(lines)
    cust = customers(o)
    return {"lines": lines, "orders": o, "customers": cust, "cq": customer_quarter(o, c, cust)}


def kpis(cq: pd.DataFrame, q: int, lookback: int, segment: str = "All") -> dict:
    """The five scorecard KPIs for one quarter, straight from the definitions."""
    d = cq if segment == "All" else cq[cq["segment"] == segment]
    d = d[d["qidx"] == q]
    new = d[d["is_active"] & (d["last_before"].isna() | (q - d["last_before"] > lookback))]
    ret = d[d["active_prev"]]
    rea = d[d["active_prev2"] & ~d["active_prev"]]
    act = d[d["is_active"]]
    return {
        "new_customers": (len(new), len(new)),
        "activation_rate": (new["activated"].mean() if len(new) else np.nan, len(new)),
        "retention_rate": (ret["is_active"].mean() if len(ret) else np.nan, len(ret)),
        "reactivation_rate": (rea["is_active"].mean() if len(rea) else np.nan, len(rea)),
        "revenue_per_active": (act["net"].mean(), len(act)),
    }
