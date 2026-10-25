"""Filesystem layout and config loading. Override the data root with CLA_DATA_DIR."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
SQL_DIR = ROOT / "sql"
DATA_DIR = Path(os.environ.get("CLA_DATA_DIR", ROOT / "data"))

RAW_DIR = DATA_DIR / "raw"
SAMPLE_DIR = ROOT / "data" / "sample"
MARTS_DIR = DATA_DIR / "marts"
RESULTS_DIR = DATA_DIR / "results"
R_INPUT_DIR = DATA_DIR / "r_inputs"
WAREHOUSE = DATA_DIR / "warehouse.duckdb"
REPORTS_DIR = ROOT / "reports"

RETAIL_ZIP = RAW_DIR / "online_retail_ii.zip"
RETAIL_PARQUET = RAW_DIR / "online_retail_ii.parquet"
RETAIL_SAMPLE = SAMPLE_DIR / "online_retail_ii_sample.parquet"
EMAIL_CSV = RAW_DIR / "hillstrom_email.csv"


@lru_cache(maxsize=None)
def load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def spec() -> dict:
    return load_yaml("measurement_spec.yaml")


def hypotheses() -> dict:
    return load_yaml("hypotheses.yaml")


def ensure_dirs() -> None:
    for d in (RAW_DIR, MARTS_DIR, RESULTS_DIR, R_INPUT_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
