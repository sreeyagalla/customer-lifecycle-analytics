"""SQL marts vs. the independent pandas implementation, on the committed real sample."""
import numpy as np
import pandas as pd


def test_sheet_overlap_is_an_exact_copy(sample_raw):
    a = sample_raw[(sample_raw["source_sheet"] == "Year 2009-2010") & (sample_raw["invoice_ts"] >= "2010-12-01")]
    b = sample_raw[(sample_raw["source_sheet"] == "Year 2010-2011") & (sample_raw["invoice_ts"] < "2010-12-10")]
    assert len(a) > 0
    assert set(a["invoice"]) == set(b["invoice"])


def test_orders_match(sample_marts, sample_ind):
    sql = sample_marts["orders"].set_index("invoice").sort_index()
    ind = sample_ind["orders"].set_index("invoice").sort_index()
    assert list(sql.index) == list(ind.index)
    assert np.allclose(sql["merch_value"], ind["merch_value"])
    assert (sql["customer_id"].astype(int) == ind["customer_id"].astype(int)).all()
    assert (sql["qidx"] == ind["qidx"]).all()


def test_customers_match(sample_marts, sample_ind):
    sql = sample_marts["customers"].set_index("customer_id").sort_index()
    ind = sample_ind["customers"].sort_index()
    assert list(sql.index.astype(int)) == list(ind.index.astype(int))
    assert (pd.to_datetime(sql["first_order_date"]).values == pd.to_datetime(ind["first_order_date"]).values).all()
    assert (sql["segment"].values == ind["segment"].values).all()


def test_customer_quarter_status_and_values_match(sample_marts, sample_ind):
    key = ["customer_id", "qidx"]
    sql = sample_marts["customer_quarter"].sort_values(key).reset_index(drop=True)
    ind = sample_ind["cq"].sort_values(key).reset_index(drop=True)
    assert len(sql) == len(ind)
    assert (sql["status"].values == ind["status"].values).all()
    assert np.allclose(sql["net_value"], ind["net"])
    assert (sql["activated_90d"].values == ind["activated"].values).all()


def test_growth_accounting_identity(sample_marts):
    lq = sample_marts["lifecycle_quarterly"].sort_values(["segment", "qidx"])
    assert (lq["active_customers"] == lq["new_customers"] + lq["retained_customers"] + lq["reactivated_customers"]).all()
    prev = lq.groupby("segment")["active_customers"].shift()
    ok = prev.notna()
    assert (lq.loc[ok, "lapsed_customers"] == prev[ok] - lq.loc[ok, "retained_customers"]).all()


def test_data_quality_counts(sample_marts, sample_raw, sample_ind):
    dq = sample_marts["data_quality"].set_index("step")["n"]
    assert dq[1] == len(sample_raw)
    assert dq[4] == len(sample_ind["lines"])
    assert dq[8] == len(sample_ind["orders"])
    assert dq[9] == len(sample_ind["customers"])
