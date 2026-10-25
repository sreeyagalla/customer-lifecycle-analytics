"""Build the committed sample: real rows only, selected by a deterministic hash rule.

Sampling is by customer (so each sampled customer's full history stays intact and
lifecycle states are computed exactly as on the full data). Lines with no customer
ID are sampled by invoice at the same rate so the data-quality counts keep their
shape. Nothing is generated or altered.
"""

from __future__ import annotations

import hashlib

import pandas as pd

from . import paths

SAMPLE_PERCENT = 25


def keep(key: str, percent: int = SAMPLE_PERCENT) -> bool:
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % 100 < percent


def build_sample(full: pd.DataFrame, percent: int = SAMPLE_PERCENT) -> pd.DataFrame:
    has_customer = full["customer_id"].notna()
    cust_keep = {
        cid: keep(f"customer:{cid}", percent) for cid in full.loc[has_customer, "customer_id"].unique()
    }
    inv_keep = {
        inv: keep(f"invoice:{inv}", percent) for inv in full.loc[~has_customer, "invoice"].unique()
    }
    mask = has_customer & full["customer_id"].map(cust_keep).fillna(False).astype(bool)
    mask |= ~has_customer & full["invoice"].map(inv_keep).fillna(False).astype(bool)
    return full.loc[mask].reset_index(drop=True)


def write_sample(percent: int = SAMPLE_PERCENT) -> pd.DataFrame:
    full = pd.read_parquet(paths.RETAIL_PARQUET)
    sample = build_sample(full, percent)
    paths.SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    sample.to_parquet(paths.RETAIL_SAMPLE, index=False, compression="zstd")
    return sample
