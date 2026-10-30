"""Import + analytics execution. Results are persisted, so dashboards never retrain on request."""
import os
import traceback
from datetime import datetime

import pandas as pd
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from .. import models as m
from ..schemas import PARAM_MODELS
from . import analytics as A
from .cleaning import clean_retail
from .recommendations import recommendation_source
from .spark_jobs import launch_spark_run, resolve_rfm_engine

CHUNK = 20000


def read_upload(path: str) -> pd.DataFrame:
    if path.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(path, dtype={"InvoiceNo": str, "StockCode": str})
    for enc in ("utf-8", "ISO-8859-1"):
        try:
            return pd.read_csv(path, dtype={"InvoiceNo": str, "StockCode": str}, encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode CSV (tried utf-8 and ISO-8859-1)")


def load_clean_into_db(db: Session, df: pd.DataFrame) -> None:
    for model in (m.CustomerSegment, m.AssociationRule, m.Forecast, m.OrderItem, m.Order, m.Product, m.Customer):
        db.execute(delete(model))
    prod = df.drop_duplicates("StockCode")[["StockCode", "Description"]]
    db.execute(insert(m.Product), [{"stock_code": a, "description": b[:255]} for a, b in prod.itertuples(index=False)])

    pos = df[~df["is_cancellation"] & df["CustomerID"].notna()]
    cust = df[df["CustomerID"].notna()].groupby("CustomerID").agg(
        country=("Country", lambda s: s.mode().iat[0]), first=("InvoiceDate", "min"), last=("InvoiceDate", "max"))
    stats = pos.groupby("CustomerID").agg(orders=("InvoiceNo", "nunique"), spent=("line_total", "sum"))
    cust = cust.join(stats).fillna({"orders": 0, "spent": 0})
    db.execute(insert(m.Customer), [dict(customer_id=int(i), country=r.country, first_order_date=r["first"].to_pydatetime(),
               last_order_date=r["last"].to_pydatetime(), order_count=int(r.orders), total_spent=round(float(r.spent), 2))
               for i, r in cust.iterrows()])

    orders = df.groupby("InvoiceNo").agg(cid=("CustomerID", "first"), date=("InvoiceDate", "min"),
                                         country=("Country", "first"), canc=("is_cancellation", "first"),
                                         total=("line_total", "sum")).reset_index()
    rows = [dict(invoice_no=r.InvoiceNo, customer_id=None if pd.isna(r.cid) else int(r.cid), invoice_date=r.date.to_pydatetime(),
                 country=r.country, is_cancellation=bool(r.canc), total_amount=round(float(r.total), 2)) for r in orders.itertuples()]
    for i in range(0, len(rows), CHUNK):
        db.execute(insert(m.Order), rows[i:i + CHUNK])
    items = df[["InvoiceNo", "StockCode", "Quantity", "UnitPrice", "line_total"]]
    for i in range(0, len(items), CHUNK):
        part = items.iloc[i:i + CHUNK]
        db.execute(insert(m.OrderItem), [dict(invoice_no=a, stock_code=b, quantity=int(c), unit_price=float(d), line_total=float(e))
                                         for a, b, c, d, e in part.itertuples(index=False)])
    db.commit()


def _finish(db, run, status, result=None, error=None):
    run.status, run.result, run.error, run.finished_at = status, result, (error or None) and error[:2000], datetime.utcnow()
    db.commit()


def execute_import(session_factory, run_id: int, path: str, source_label: str) -> None:
    db = session_factory()
    run = db.get(m.AnalyticsRun, run_id)
    try:
        run.status, run.started_at = "running", datetime.utcnow()
        db.commit()
        clean, report = clean_retail(read_upload(path))
        report["source_file"] = source_label
        load_clean_into_db(db, clean)
        _finish(db, run, "completed", report)
    except Exception as exc:  # noqa: BLE001 - surfaced to the run history
        db.rollback()
        _finish(db, run, "failed", error=f"{type(exc).__name__}: {exc}")
    finally:
        db.close()
        if os.path.exists(path):
            os.remove(path)


def _items_frame(db: Session) -> pd.DataFrame:
    q = (select(m.Order.invoice_no, m.Order.customer_id, m.Order.invoice_date, m.OrderItem.stock_code,
                m.Product.description, m.OrderItem.line_total)
         .join(m.OrderItem, m.OrderItem.invoice_no == m.Order.invoice_no)
         .join(m.Product, m.Product.stock_code == m.OrderItem.stock_code)
         .where(m.Order.is_cancellation.is_(False)))
    df = pd.read_sql(q, db.connection())
    df["invoice_date"] = pd.to_datetime(df["invoice_date"])
    return df


def _persist_segments(db, run_id, rfm: pd.DataFrame, clusters=None):
    rows = []
    for i, r in enumerate(rfm.itertuples()):
        rows.append(dict(run_id=run_id, customer_id=int(r.customer_id), recency=int(r.recency), frequency=int(r.frequency),
                         monetary=float(r.monetary), r_score=int(r.r_score), f_score=int(r.f_score), m_score=int(r.m_score),
                         segment=None if clusters is not None else r.segment,
                         cluster=None if clusters is None else int(clusters[i])))
    for i in range(0, len(rows), CHUNK):
        db.execute(insert(m.CustomerSegment), rows[i:i + CHUNK])


def execute_run(session_factory, run_id: int) -> None:
    db = session_factory()
    run = db.get(m.AnalyticsRun, run_id)
    try:
        run.status, run.started_at = "running", datetime.utcnow()
        db.commit()
        p = PARAM_MODELS[run.run_type](**run.params)
        if db.query(m.OrderItem.id).first() is None:
            raise ValueError("No data loaded. Import a dataset first.")
        if run.run_type == "rfm":
            engine = resolve_rfm_engine(p.engine, recommendation_source(db))
            run.params = {**run.params, "engine": engine}
            db.commit()
            if engine == "spark":
                try:
                    launch_spark_run(db.get_bind().url.render_as_string(hide_password=False), run.id)
                except Exception:
                    db.refresh(run)
                    # A timeout while the JVM is shutting down must not turn
                    # an already committed successful run into a failure.
                    if run.status not in ("completed", "failed"):
                        raise
                    return
                db.refresh(run)
                if run.status not in ("completed", "failed"):
                    _finish(db, run, "failed", error="Spark worker exited before saving results. Check backend/data/spark-logs and SPARK_SETUP.md.")
                return
        df = _items_frame(db)
        result: dict
        if run.run_type in ("rfm", "clustering"):
            rfm = A.compute_rfm(df[df["customer_id"].notna()])
            if run.run_type == "rfm":
                _persist_segments(db, run.id, rfm)
                seg = rfm.groupby("segment").agg(customers=("customer_id", "count"), avg_recency=("recency", "mean"),
                                                 avg_frequency=("frequency", "mean"), avg_monetary=("monetary", "mean"),
                                                 revenue=("monetary", "sum")).round(2).reset_index()
                result = {"engine": "pandas", "customers_scored": int(len(rfm)), "snapshot_rule": "last invoice date + 1 day",
                          "segments": seg.to_dict("records")}
            else:
                out = A.run_kmeans(rfm, k=p.k, k_min=p.k_min, k_max=p.k_max)
                _persist_segments(db, run.id, rfm, out["labels"])
                result = {kk: v for kk, v in out.items() if kk != "labels"}
                result["customers_scored"] = int(len(rfm))
        elif run.run_type == "basket":
            rules = A.run_basket(df, p.min_support, p.min_confidence, p.min_lift, p.top_n, p.max_len)
            if rules:
                db.execute(insert(m.AssociationRule), [dict(run_id=run.id, antecedents=r["antecedent_names"], consequents=r["consequent_names"],
                                                            support=r["support"], confidence=r["confidence"], lift=r["lift"]) for r in rules[:2000]])
            result = {"rules_found": len(rules), "rules_stored": min(len(rules), 2000), "baskets": int(df["invoice_no"].nunique())}
        else:
            daily = df.groupby(df["invoice_date"].dt.normalize())["line_total"].sum()
            out = A.run_forecast(daily, p.horizon, p.test_days)
            db.execute(insert(m.Forecast), [dict(run_id=run.id, date=r["date"].to_pydatetime(), actual=r["actual"],
                                                 predicted=r["predicted"], baseline=r["baseline"], phase=r["phase"]) for r in out["rows"]])
            result = {k: v for k, v in out.items() if k != "rows"}
            result["model_name"] = "GradientBoostingRegressor (lag>=28 + calendar features)"
            result["baseline_name"] = "Seasonal naive (repeat last observed week)"
        db.commit()
        _finish(db, run, "completed", result)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        _finish(db, run, "failed", error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=2)}")
    finally:
        db.close()
