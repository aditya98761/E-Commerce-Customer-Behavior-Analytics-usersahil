import numpy as np
import pandas as pd
import pytest

from app.services import analytics as A
from app.services.cleaning import clean_retail
from tests.synthetic import make_raw


@pytest.fixture(scope="module")
def cleaned():
    return clean_retail(make_raw())


def test_cleaning_report_counts(cleaned):
    df, rep = cleaned
    assert rep["exact_duplicates_removed"] == 1
    assert rep["invalid_quantity_removed"] == 1
    assert rep["invalid_price_removed"] == 1
    assert rep["non_product_rows_removed"] == 1
    assert rep["cancellation_rows_kept_flagged"] == 1
    assert rep["missing_customer_id_rows_kept_as_guest"] == 1
    assert rep["currency"] == "GBP"
    assert (df.loc[~df.is_cancellation, "Quantity"] > 0).all() and (df.UnitPrice > 0).all()


def test_cleaning_rejects_missing_columns():
    with pytest.raises(ValueError, match="Missing required column"):
        clean_retail(pd.DataFrame({"a": [1]}))


def _items(cleaned):
    df, _ = cleaned
    d = df[~df.is_cancellation].rename(columns={"InvoiceNo": "invoice_no", "CustomerID": "customer_id", "InvoiceDate": "invoice_date",
                                                "StockCode": "stock_code", "Description": "description"})
    d["customer_id"] = d["customer_id"].astype(float)
    return d


def test_rfm_scores_and_segments(cleaned):
    rfm = A.compute_rfm(_items(cleaned))
    assert rfm[["r_score", "f_score", "m_score"]].stack().between(1, 5).all()
    assert rfm["segment"].notna().all() and (rfm["segment"] != "Other").all()
    top = rfm.sort_values("recency").iloc[0]  # most recent buyer must score the highest R
    assert top.r_score == 5
    assert rfm["monetary"].gt(0).all()


def test_rfm_segment_rules_cover_all_combinations():
    for r in range(1, 6):
        for f in range(1, 6):
            assert A.label_segment(r, f) != "Other"


def test_rfm_needs_enough_customers():
    with pytest.raises(ValueError):
        A.compute_rfm(pd.DataFrame({"customer_id": [1.0], "invoice_no": ["1"], "invoice_date": [pd.Timestamp("2011-01-01")], "line_total": [5.0]}))


def test_kmeans_silhouette_and_profiles(cleaned):
    rfm = A.compute_rfm(_items(cleaned))
    out = A.run_kmeans(rfm, k_min=2, k_max=5)
    assert 2 <= out["k"] <= 5 and len(out["labels"]) == len(rfm)
    assert -1 <= out["silhouette"] <= 1
    assert sum(p["size"] for p in out["profiles"]) == len(rfm)
    assert out["silhouette"] == max(out["silhouette_by_k"].values())  # auto-k picks the best silhouette


def test_basket_finds_planted_pattern(cleaned):
    rules = A.run_basket(_items(cleaned), min_support=0.1, min_confidence=0.5, top_n=30)
    assert rules and all(r["lift"] >= 1 and 0 < r["confidence"] <= 1 for r in rules)
    planted = {"85000", "85001", "85002"}
    assert any(set(r["antecedents"]) | set(r["consequents"]) <= planted for r in rules)


def test_forecast_no_leakage_and_metrics():
    idx = pd.date_range("2011-01-01", periods=300)
    rng = np.random.default_rng(1)
    y = pd.Series(1000 + 300 * (idx.dayofweek < 5) + rng.normal(0, 40, 300), index=idx)
    out = A.run_forecast(y, horizon=14, test_days=28)
    test = [r for r in out["rows"] if r["phase"] == "test"]
    train = [r for r in out["rows"] if r["phase"] == "train"]
    assert max(r["date"] for r in train) < min(r["date"] for r in test)       # strict chronological split
    assert out["model"]["rmse"] >= out["model"]["mae"] >= 0
    assert len([r for r in out["rows"] if r["phase"] == "future"]) == 14
    # leakage guard: corrupting the TEST actuals must not change the test predictions
    y2 = y.copy(); y2.iloc[-28:] *= 5
    out2 = A.run_forecast(y2, horizon=14, test_days=28)
    p1 = [r["predicted"] for r in out["rows"] if r["phase"] == "test"]
    p2 = [r["predicted"] for r in out2["rows"] if r["phase"] == "test"]
    assert np.allclose(p1, p2)


def test_forecast_horizon_validation():
    with pytest.raises(ValueError):
        A.run_forecast(pd.Series(1.0, index=pd.date_range("2011-01-01", periods=300)), horizon=60)
