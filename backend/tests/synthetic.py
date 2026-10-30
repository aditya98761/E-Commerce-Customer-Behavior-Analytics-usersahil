"""SYNTHETIC data used ONLY by automated tests. It is not the UCI dataset and is never imported by the app."""
import numpy as np
import pandas as pd


def make_raw(n_customers=120, days=330, seed=7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2010-12-01")
    products = [(f"{85000 + i}", f"SYNTH PRODUCT {i}", round(float(rng.uniform(0.5, 9)), 2)) for i in range(30)]
    rows, inv = [], 10000
    for c in range(n_customers):
        for _ in range(int(rng.integers(1, 9))):
            inv += 1
            d = start + pd.Timedelta(days=int(rng.integers(0, days)), hours=int(rng.integers(8, 17)))
            bundle = [0, 1, 2] if rng.random() < 0.4 else []  # planted co-purchase pattern
            picks = list(dict.fromkeys(bundle + list(rng.integers(0, 30, size=int(rng.integers(1, 5))))))
            for p in picks:
                code, desc, price = products[p]
                rows.append([str(inv), code, desc, int(rng.integers(1, 12)), d, price, 12000 + c, "United Kingdom" if c % 5 else "France"])
    df = pd.DataFrame(rows, columns=["InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate", "UnitPrice", "CustomerID", "Country"])
    # planted data problems
    dirty = [
        df.iloc[0].copy(),                                                      # exact duplicate
        pd.Series(["C99001", "85001", "SYNTH PRODUCT 1", -2, start + pd.Timedelta(days=40), 3.0, 12001, "France"], index=df.columns),  # cancellation
        pd.Series(["99002", "85002", "SYNTH PRODUCT 2", -5, start, 2.0, 12002, "France"], index=df.columns),      # invalid qty
        pd.Series(["99003", "85003", "SYNTH PRODUCT 3", 5, start, 0.0, 12003, "France"], index=df.columns),       # invalid price
        pd.Series(["99004", "POST", "POSTAGE", 1, start, 18.0, 12004, "France"], index=df.columns),                # non-product
        pd.Series(["99005", "85004", "SYNTH PRODUCT 4", 2, start + pd.Timedelta(days=3), 2.5, np.nan, "United Kingdom"], index=df.columns),  # guest
    ]
    return pd.concat([df, pd.DataFrame(dirty)], ignore_index=True)
