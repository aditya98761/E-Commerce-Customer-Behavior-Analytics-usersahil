"""Validation + cleaning of the UCI Online Retail dataset. Every decision is counted in the report."""
import re
import pandas as pd

REQUIRED = ["InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate", "UnitPrice", "CustomerID", "Country"]
# Non-merchandise stock codes in the dataset (postage, fees, manual adjustments, samples...)
NON_PRODUCT = {"POST", "D", "DOT", "M", "BANK CHARGES", "AMAZONFEE", "S", "B", "CRUK", "PADS", "C2"}


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    lookup = {re.sub(r"[\s_]", "", str(c)).lower(): c for c in df.columns}
    mapping = {}
    for col in REQUIRED:
        if col.lower() not in lookup:
            raise ValueError(f"Missing required column '{col}'. Found: {list(df.columns)}")
        mapping[lookup[col.lower()]] = col
    return df.rename(columns=mapping)[REQUIRED].copy()


def clean_retail(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = normalise_columns(raw)
    rep: dict = {"currency": "GBP", "rows_raw": int(len(df)),
                 "missing_before": {c: int(df[c].isna().sum()) for c in REQUIRED}}

    df["InvoiceNo"] = df["InvoiceNo"].astype(str).str.strip()
    df["StockCode"] = df["StockCode"].astype(str).str.strip().str.upper()
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"], errors="coerce")
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce")
    df["UnitPrice"] = pd.to_numeric(df["UnitPrice"], errors="coerce")

    bad = df[["InvoiceDate", "Quantity", "UnitPrice"]].isna().any(axis=1) | df["InvoiceNo"].str.upper().isin(["NAN", ""])
    rep["unparseable_rows_removed"] = int(bad.sum())
    df = df[~bad]

    before = len(df)
    df = df.drop_duplicates()
    rep["exact_duplicates_removed"] = int(before - len(df))

    df["is_cancellation"] = df["InvoiceNo"].str.upper().str.startswith("C")
    can = df["is_cancellation"]
    bad_qty = (~can & (df["Quantity"] <= 0)) | (can & (df["Quantity"] >= 0))
    rep["invalid_quantity_removed"] = int(bad_qty.sum())
    df = df[~bad_qty]

    bad_price = df["UnitPrice"] <= 0
    rep["invalid_price_removed"] = int(bad_price.sum())
    df = df[~bad_price]

    non_prod = df["StockCode"].isin(NON_PRODUCT)
    rep["non_product_rows_removed"] = int(non_prod.sum())
    df = df[~non_prod].copy()

    # Descriptions: fill from the most common description of the same stock code, else UNKNOWN
    df["Description"] = df["Description"].astype("string").str.strip().replace("", pd.NA)
    rep["missing_description_filled"] = int(df["Description"].isna().sum())
    canon = df.dropna(subset=["Description"]).groupby("StockCode")["Description"].agg(lambda s: s.mode().iat[0])
    df["Description"] = df["StockCode"].map(canon).fillna("UNKNOWN").astype(str)  # one description per code

    # Missing CustomerID: rows KEPT for sales analytics, excluded from customer-level analytics
    df["CustomerID"] = pd.to_numeric(df["CustomerID"], errors="coerce").astype("Int64")
    rep["missing_customer_id_rows_kept_as_guest"] = int(df["CustomerID"].isna().sum())

    df["Country"] = df["Country"].astype(str).str.strip()
    df["line_total"] = (df["Quantity"] * df["UnitPrice"]).round(2)
    df = df.reset_index(drop=True)

    rep.update({
        "rows_clean": int(len(df)),
        "cancellation_rows_kept_flagged": int(df["is_cancellation"].sum()),
        "unique_invoices": int(df["InvoiceNo"].nunique()),
        "unique_customers": int(df["CustomerID"].nunique()),
        "unique_products": int(df["StockCode"].nunique()),
        "date_min": str(df["InvoiceDate"].min()), "date_max": str(df["InvoiceDate"].max()),
        "retention_pct": round(100 * len(df) / max(rep["rows_raw"], 1), 2),
    })
    return df, rep
