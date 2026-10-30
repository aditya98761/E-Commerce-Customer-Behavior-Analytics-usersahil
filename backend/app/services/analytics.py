"""Pure analytical functions (no DB access) so they are directly unit-testable."""
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, silhouette_score
from sklearn.preprocessing import StandardScaler

SEGMENT_RULES = [  # first match wins; covers every (R, F) combination
    ("Champions", lambda r, f: r >= 4 and f >= 4),
    ("Loyal Customers", lambda r, f: r == 3 and f >= 4),
    ("Can't Lose Them", lambda r, f: r <= 2 and f >= 4),
    ("At Risk", lambda r, f: r <= 2 and f == 3),
    ("New Customers", lambda r, f: r >= 4 and f == 1),
    ("Potential Loyalists", lambda r, f: r >= 4 and f in (2, 3)),
    ("Need Attention", lambda r, f: r == 3 and f in (2, 3)),
    ("About to Sleep", lambda r, f: r == 3 and f == 1),
    ("Hibernating", lambda r, f: r <= 2 and f <= 2),
]


def label_segment(r: int, f: int) -> str:
    for name, rule in SEGMENT_RULES:
        if rule(r, f):
            return name
    return "Other"


def _quintile(s: pd.Series, reverse=False) -> pd.Series:
    labels = [5, 4, 3, 2, 1] if reverse else [1, 2, 3, 4, 5]
    return pd.qcut(s.rank(method="first"), 5, labels=labels).astype(int)


def compute_rfm(df: pd.DataFrame, snapshot: pd.Timestamp | None = None) -> pd.DataFrame:
    """df: non-cancelled rows with customer_id, invoice_no, invoice_date, line_total."""
    df = df.dropna(subset=["customer_id"])
    if df["customer_id"].nunique() < 10:
        raise ValueError("At least 10 identified customers are required for RFM quintile scoring.")
    snapshot = snapshot or (df["invoice_date"].max().normalize() + pd.Timedelta(days=1))
    g = df.groupby("customer_id").agg(last=("invoice_date", "max"), frequency=("invoice_no", "nunique"),
                                      monetary=("line_total", "sum"))
    g["recency"] = (snapshot - g["last"]).dt.days.astype(int)
    g = g.drop(columns="last")
    g = g[g["monetary"] > 0].copy()
    g["r_score"] = _quintile(g["recency"], reverse=True)  # recent = high score
    g["f_score"] = _quintile(g["frequency"])
    g["m_score"] = _quintile(g["monetary"])
    g["segment"] = [label_segment(r, f) for r, f in zip(g["r_score"], g["f_score"])]
    return g.reset_index()


def run_kmeans(rfm: pd.DataFrame, k: int | None = None, k_min=2, k_max=8, seed=42) -> dict:
    X = np.log1p(rfm[["recency", "frequency", "monetary"]].astype(float))  # tame right skew
    Xs = StandardScaler().fit_transform(X)
    k_max = min(k_max, len(rfm) - 1)
    sil = {}
    for kk in range(k_min, k_max + 1):
        lab = KMeans(n_clusters=kk, n_init=10, random_state=seed).fit_predict(Xs)
        sil[kk] = float(silhouette_score(Xs, lab, sample_size=min(len(Xs), 5000), random_state=seed))
    best = k or max(sil, key=sil.get)
    labels = KMeans(n_clusters=best, n_init=10, random_state=seed).fit_predict(Xs)
    prof = (rfm.assign(cluster=labels).groupby("cluster")
            .agg(size=("customer_id", "count"), recency=("recency", "mean"),
                 frequency=("frequency", "mean"), monetary=("monetary", "mean")).round(2).reset_index())
    pca = PCA(n_components=2, random_state=seed).fit(Xs)
    coords = pca.transform(Xs)
    idx = np.random.default_rng(seed).choice(len(Xs), size=min(len(Xs), 1500), replace=False)
    points = [{"x": round(float(coords[i, 0]), 3), "y": round(float(coords[i, 1]), 3), "cluster": int(labels[i])} for i in idx]
    return {"labels": labels, "k": int(best), "silhouette_by_k": {str(a): round(b, 4) for a, b in sil.items()},
            "silhouette": round(sil[best], 4) if best in sil else round(float(silhouette_score(Xs, labels)), 4),
            "profiles": prof.to_dict("records"), "points": points,
            "pca_explained_variance": [round(float(v), 4) for v in pca.explained_variance_ratio_]}


def run_basket(df: pd.DataFrame, min_support=0.02, min_confidence=0.3, min_lift=1.0, top_n=150, max_len=3) -> list[dict]:
    """df: non-cancelled rows with invoice_no, stock_code, description. Restricted to top_n products (memory)."""
    from mlxtend.frequent_patterns import apriori, association_rules
    top = df.groupby("stock_code")["invoice_no"].nunique().nlargest(top_n).index
    sub = df[df["stock_code"].isin(top)].drop_duplicates(["invoice_no", "stock_code"])
    basket = pd.crosstab(sub["invoice_no"], sub["stock_code"]).gt(0)
    basket = basket[basket.sum(axis=1) >= 2]  # single-item baskets carry no co-purchase signal
    if basket.empty:
        return []
    freq = apriori(basket, min_support=min_support, use_colnames=True, max_len=max_len)
    if freq.empty:
        return []
    rules = association_rules(freq, num_itemsets=len(basket), metric="confidence", min_threshold=min_confidence)
    rules = rules[rules["lift"] >= min_lift].sort_values("lift", ascending=False)
    names = df.drop_duplicates("stock_code").set_index("stock_code")["description"].to_dict()
    return [{"antecedents": sorted(r.antecedents), "consequents": sorted(r.consequents),
             "antecedent_names": [names.get(c, c) for c in sorted(r.antecedents)],
             "consequent_names": [names.get(c, c) for c in sorted(r.consequents)],
             "support": float(r.support), "confidence": float(r.confidence), "lift": float(r.lift)}
            for r in rules.itertuples()]


LAGS = (28, 35, 42)  # all >= max horizon, so every feature is known at forecast time (no recursion, no leakage)
MAX_HORIZON = 28


def _features(y: pd.Series) -> pd.DataFrame:
    f = pd.DataFrame(index=y.index)
    f["dow"], f["dom"], f["month"] = y.index.dayofweek, y.index.day, y.index.month
    for l in LAGS:
        f[f"lag_{l}"] = y.shift(l)
    f["roll7_lag28"] = y.shift(28).rolling(7).mean()
    return f


def run_forecast(daily: pd.Series, horizon=28, test_days=28, seed=42) -> dict:
    """daily: revenue indexed by date. Chronological split; the scored model sees only the train window."""
    if not 1 <= horizon <= MAX_HORIZON:
        raise ValueError(f"horizon must be between 1 and {MAX_HORIZON}")
    y = daily.asfreq("D").fillna(0.0)  # days with no trading are real zeros
    if len(y) < 120 + test_days:
        raise ValueError("Not enough history: need at least 120 days plus the test window.")
    train, test = y.iloc[:-test_days], y.iloc[-test_days:]
    future_idx = pd.date_range(y.index[-1] + pd.Timedelta(days=1), periods=horizon)
    ext = pd.concat([y, pd.Series(np.nan, index=future_idx)])
    X = _features(ext)

    def fit(idx):
        Xt = X.loc[idx].dropna()
        m = GradientBoostingRegressor(random_state=seed, n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.8)
        return m.fit(Xt, ext.loc[Xt.index])

    m1 = fit(train.index)  # trained strictly on the train window
    pred_test = np.clip(m1.predict(X.loc[test.index].fillna(0)), 0, None)
    last_week = {d.dayofweek: v for d, v in zip(train.index[-7:], train.iloc[-7:])}  # seasonal-naive baseline
    base_test = np.array([last_week[d.dayofweek] for d in test.index])

    def metrics(p):
        return {"mae": round(float(mean_absolute_error(test, p)), 2),
                "rmse": round(float(np.sqrt(mean_squared_error(test, p))), 2)}
    m_model, m_base = metrics(pred_test), metrics(base_test)

    m2 = fit(y.index)  # refit on all history only to produce the genuine future forecast
    pred_future = np.clip(m2.predict(X.loc[future_idx].fillna(0)), 0, None)
    rows = [{"date": d, "actual": float(v), "predicted": None, "baseline": None, "phase": "train"} for d, v in train.items()]
    rows += [{"date": d, "actual": float(a), "predicted": float(p), "baseline": float(b), "phase": "test"}
             for d, a, p, b in zip(test.index, test, pred_test, base_test)]
    rows += [{"date": d, "actual": None, "predicted": float(p), "baseline": None, "phase": "future"}
             for d, p in zip(future_idx, pred_future)]
    return {"model": m_model, "baseline": m_base, "train_end": str(train.index[-1].date()),
            "test_start": str(test.index[0].date()), "rows": rows,
            "beats_baseline": m_model["rmse"] < m_base["rmse"],
            "rmse_improvement_pct": round(100 * (m_base["rmse"] - m_model["rmse"]) / max(m_base["rmse"], 1e-9), 2)}
