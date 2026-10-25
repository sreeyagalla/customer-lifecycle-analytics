import pandas as pd
import pytest

from cla import paths, warehouse
from tests import independent

MART_NAMES = ("fiscal_quarters", "data_window", "orders", "customers", "customer_quarter",
              "lifecycle_quarterly", "cohort_monthly", "data_quality", "stg_email", "build_info")


@pytest.fixture(scope="session")
def sample_con(tmp_path_factory):
    if not paths.EMAIL_CSV.exists():
        pytest.skip("email experiment CSV missing: run `cla fetch`")
    db = tmp_path_factory.mktemp("warehouse") / "sample.duckdb"
    con = warehouse.build("sample", db_path=db, export=False)
    yield con
    con.close()


@pytest.fixture(scope="session")
def sample_marts(sample_con):
    return {n: sample_con.execute(f"select * from {n}").df() for n in MART_NAMES}


@pytest.fixture(scope="session")
def sample_raw():
    return pd.read_parquet(paths.RETAIL_SAMPLE)


@pytest.fixture(scope="session")
def sample_ind(sample_raw):
    return independent.pipeline(sample_raw)
