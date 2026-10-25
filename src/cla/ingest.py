"""Download the two public datasets, verify checksums, and land them as columnar files.

Sources (both public, no authentication):
  * UCI Online Retail II (CC BY 4.0) - every line of every invoice of a UK online
    gift-ware retailer, 1 Dec 2009 - 9 Dec 2011.
  * MineThatData E-Mail Analytics challenge (Kevin Hillstrom, 2008) - 64,000
    customers of an apparel retailer randomly assigned to a Mens email, a Womens
    email, or no email, with visit / conversion / spend in the following two weeks.
"""

from __future__ import annotations

import hashlib
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import paths


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    path: Path
    sha256: str
    licence: str


RETAIL = Source(
    name="UCI Online Retail II",
    url="https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip",
    path=paths.RETAIL_ZIP,
    sha256="572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb",
    licence="CC BY 4.0",
)
EMAIL = Source(
    name="MineThatData E-Mail Analytics (Hillstrom)",
    url="http://www.minethatdata.com/Kevin_Hillstrom_MineThatData_E-MailAnalytics_DataMiningChallenge_2008.03.20.csv",
    path=paths.EMAIL_CSV,
    sha256="0e5893329d8b93cefecc571777672028290ab69865718020c78c7284f291aece",
    licence="Publicly released by the author for analysis; not redistributed in this repo",
)
SOURCES = (RETAIL, EMAIL)

RETAIL_COLUMNS = {
    "Invoice": "invoice",
    "StockCode": "stock_code",
    "Description": "description",
    "Quantity": "quantity",
    "InvoiceDate": "invoice_ts",
    "Price": "unit_price",
    "Customer ID": "customer_id",
    "Country": "country",
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(source: Source, force: bool = False) -> Path:
    """Download a source if missing and verify its checksum."""
    source.path.parent.mkdir(parents=True, exist_ok=True)
    if force or not source.path.exists():
        print(f"downloading {source.name} ...")
        tmp = source.path.with_suffix(source.path.suffix + ".part")
        urllib.request.urlretrieve(source.url, tmp)
        tmp.replace(source.path)
    digest = sha256_of(source.path)
    if digest != source.sha256:
        raise RuntimeError(
            f"{source.name}: sha256 {digest} does not match the pinned {source.sha256}. "
            "The upstream file changed; inspect it before updating the pin."
        )
    return source.path


def land_retail(zip_path: Path = paths.RETAIL_ZIP, out: Path = paths.RETAIL_PARQUET) -> pd.DataFrame:
    """Read both workbook sheets (about 3 minutes) and write one parquet file.

    The sheets are kept exactly as published (including their overlap) and tagged
    with source_sheet; de-duplication is a documented SQL step, not a silent one.
    """
    with zipfile.ZipFile(zip_path) as zf:
        member = next(n for n in zf.namelist() if n.lower().endswith(".xlsx"))
        with zf.open(member) as fh:
            sheets = pd.read_excel(
                fh,
                sheet_name=None,
                dtype={"Invoice": str, "StockCode": str, "Description": str, "Country": str},
                engine="openpyxl",
            )
    frames = []
    for sheet_name, df in sheets.items():
        df = df.rename(columns=RETAIL_COLUMNS)[list(RETAIL_COLUMNS.values())]
        df["source_sheet"] = sheet_name
        frames.append(df)
    lines = pd.concat(frames, ignore_index=True)
    lines["customer_id"] = lines["customer_id"].astype("Int64")
    lines["quantity"] = lines["quantity"].astype("int64")
    lines["unit_price"] = lines["unit_price"].astype("float64")
    lines["invoice_ts"] = pd.to_datetime(lines["invoice_ts"])
    out.parent.mkdir(parents=True, exist_ok=True)
    lines.to_parquet(out, index=False)
    return lines


def read_email(path: Path = paths.EMAIL_CSV) -> pd.DataFrame:
    df = pd.read_csv(path)
    # The published file spells the suburban zip code class "Surburban".
    df["zip_code"] = df["zip_code"].replace({"Surburban": "Suburban"})
    return df
