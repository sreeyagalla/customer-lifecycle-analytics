"""Build the DuckDB warehouse: load the landed data, run the SQL models in order,
and export the marts the dashboard and analyses read as parquet."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import duckdb
import pandas as pd

from . import ingest, paths

MARTS = (
    "fiscal_quarters",
    "data_window",
    "orders",
    "customers",
    "customer_quarter",
    "lifecycle_quarterly",
    "cohort_monthly",
    "data_quality",
    "stg_email",
    "email_arm_summary",
)


def sql_vars() -> dict[str, str]:
    s = paths.spec()
    cal, cln = s["calendar"], s["cleaning"]
    return {
        "data_start": str(cal["data_start"]),
        "first_fiscal_year": str(cal["first_fiscal_year"]),
        "reporting_quarters": str(cal["reporting_quarters"]),
        "overlap_sheet": cln["overlap_sheet"],
        "overlap_from": str(cln["overlap_from"]),
        "home_country": cln["home_country"],
        "activation_window_days": str(s["activation"]["window_days"]),
        "holdout_arm": s["programs"]["holdout_arm"],
    }


def render(sql: str, variables: dict[str, str]) -> str:
    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in variables:
            raise KeyError(f"SQL references unknown variable {{{{{key}}}}}")
        return variables[key]

    return re.sub(r"\{\{\s*(\w+)\s*\}\}", sub, sql)


def sql_files() -> list[Path]:
    return sorted((paths.SQL_DIR / "retail").glob("*.sql")) + sorted((paths.SQL_DIR / "email").glob("*.sql"))


def load_config_tables(con: duckdb.DuckDBPyConnection) -> None:
    cln = paths.spec()["cleaning"]
    con.execute("create or replace table cfg_non_merch_codes (code varchar)")
    con.executemany("insert into cfg_non_merch_codes values (?)", [[c] for c in cln["non_merchandise_codes"]])
    con.execute("create or replace table cfg_non_merch_prefixes (prefix varchar)")
    con.executemany("insert into cfg_non_merch_prefixes values (?)", [[p] for p in cln["non_merchandise_prefixes"]])


def build(source: str = "full", db_path: Path = paths.WAREHOUSE, export: bool = True) -> duckdb.DuckDBPyConnection:
    """source='full' reads data/raw (run `cla fetch` + `cla land` first);
    source='sample' reads the committed 25% customer sample."""
    retail_path = paths.RETAIL_PARQUET if source == "full" else paths.RETAIL_SAMPLE
    if not retail_path.exists():
        hint = "run `cla fetch` and `cla land`" if source == "full" else "run `cla sample` on full data"
        raise FileNotFoundError(f"{retail_path} not found: {hint}")
    if not paths.EMAIL_CSV.exists():
        raise FileNotFoundError(f"{paths.EMAIL_CSV} not found: run `cla fetch`")

    paths.ensure_dirs()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))

    retail = pd.read_parquet(retail_path)
    email = ingest.read_email()
    email.insert(0, "row_id", range(1, len(email) + 1))
    con.register("retail_df", retail)
    con.register("email_df", email)
    con.execute("create table raw_lines as select * from retail_df")
    con.execute("create table raw_email as select * from email_df")
    con.unregister("retail_df")
    con.unregister("email_df")
    load_config_tables(con)

    variables = sql_vars()
    for f in sql_files():
        con.execute(render(f.read_text(encoding="utf-8"), variables))

    con.execute(
        "create or replace table build_info as select ? as source, ? as retail_file, ? as built_at, "
        "(select count(*) from raw_lines) as raw_retail_lines, (select count(*) from raw_email) as raw_email_rows",
        [source, retail_path.name, dt.datetime.now().isoformat(timespec="seconds")],
    )
    if export:
        export_marts(con)
    return con


def export_marts(con: duckdb.DuckDBPyConnection, out_dir: Path = paths.MARTS_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for table in MARTS + ("build_info",):
        con.execute(f"copy {table} to '{(out_dir / f'{table}.parquet').as_posix()}' (format parquet)")


def marts_connection(marts_dir: Path = paths.MARTS_DIR) -> duckdb.DuckDBPyConnection:
    """In-memory connection with a view per exported mart. Never locks the
    warehouse file, so the dashboard can run while `cla build` rewrites it."""
    con = duckdb.connect()
    for table in MARTS + ("build_info",):
        p = marts_dir / f"{table}.parquet"
        if p.exists():
            con.execute(f"create view {table} as select * from read_parquet('{p.as_posix()}')")
    return con
