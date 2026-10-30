"""Spark RFM worker. Run from backend: python -m scripts.spark_rfm

The API supplies --run-id for an already created run. Without it this command
creates a new run. No source tables or previous successful results are replaced.
"""
import argparse
from datetime import datetime
import re
from urllib.parse import quote

from sqlalchemy import insert
from sqlalchemy.engine import make_url

from app import models as m
from app.config import settings
from app.database import SessionLocal


def safe_error(exc):
    detail = str(exc)
    causes = re.findall(r"Caused by:\s*([^\r\n]+)", detail)
    if causes:
        detail = causes[-1]
    elif "Py4J" in type(exc).__name__:
        # Some JVM errors have no nested cause; their meaningful message follows
        # Py4J's generic "An error occurred while calling ..." wrapper.
        java_lines = [line.strip().removeprefix(": ") for line in detail.splitlines()
                      if line.strip().startswith(": ")]
        if java_lines:
            detail = java_lines[0]
    message = f"{type(exc).__name__}: {detail}"
    url = make_url(settings.database_url)
    # Driver errors can include connection strings. Do not publish credentials
    # through run-history responses.
    message = message.replace(settings.database_url, "[DATABASE_URL]")
    if url.password:
        for secret in (quote(url.password, safe=""), url.password):
            message = message.replace(secret, "[redacted]")
    return message[:1800]


def persist_scores(db, run_id, rfm):
    batch = []
    # Stream customer-level results, never the entire transaction dataset.
    for row in rfm.toLocalIterator():
        batch.append(dict(run_id=run_id, customer_id=int(row.customer_id), recency=int(row.recency),
                          frequency=int(row.frequency), monetary=float(row.monetary),
                          r_score=int(row.r_score), f_score=int(row.f_score), m_score=int(row.m_score),
                          segment=row.segment, cluster=None))
        if len(batch) == 1000:
            db.execute(insert(m.CustomerSegment), batch)
            batch.clear()
    if batch:
        db.execute(insert(m.CustomerSegment), batch)


def execute_spark_run(session_factory, run_id):
    spark = None
    with session_factory() as db:
        run = db.get(m.AnalyticsRun, run_id)
        if run is None or run.run_type != "rfm" or run.status not in ("pending", "running"):
            raise ValueError("Expected a pending/running RFM run. Completed runs cannot be overwritten.")
        try:
            run.status, run.started_at = "running", run.started_at or datetime.utcnow()
            run.params = {**run.params, "engine": "spark"}
            db.commit()
            if db.get_bind().dialect.name != "postgresql":
                raise ValueError("Spark RFM requires PostgreSQL and the loaded Olist tables.")
            try:
                from app.services.spark_analytics import create_spark, read_olist_items, compute_rfm, segment_summary
            except ImportError:
                raise RuntimeError("Install Spark in the backend environment: python -m pip install -r requirements-spark.txt") from None
            spark = create_spark()
            items = read_olist_items(spark, db.get_bind().url.render_as_string(hide_password=False)).cache()
            rfm, snapshot, count = compute_rfm(items)
            rfm = rfm.cache()
            summary = segment_summary(rfm)
            persist_scores(db, run.id, rfm)
            run.result = {"engine": "spark", "spark_version": spark.version, "spark_master": settings.spark_master,
                          "source": "olist", "customers_scored": count, "snapshot_rule": "last invoice date + 1 day",
                          "snapshot_date": snapshot.date().isoformat(), "segments": summary}
            run.status, run.finished_at, run.error = "completed", datetime.utcnow(), None
            db.commit()  # scores and completed status become visible together
            return True
        except Exception as exc:
            db.rollback()  # discard every score in a failed run
            run = db.get(m.AnalyticsRun, run_id)
            run.status, run.finished_at, run.error = "failed", datetime.utcnow(), safe_error(exc)
            db.commit()
            return False
        finally:
            if spark is not None:
                try:
                    spark.stop()
                except Exception:
                    pass  # completed DB transaction remains authoritative


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int, help="Existing pending/running RFM run (used by the API)")
    args = parser.parse_args()
    run_id = args.run_id
    if run_id is None:
        with SessionLocal() as db:
            run = m.AnalyticsRun(run_type="rfm", params={"engine": "spark"}, status="pending")
            db.add(run)
            db.commit()
            run_id = run.id
    print(f"Starting Spark RFM run {run_id}", flush=True)
    success = execute_spark_run(SessionLocal, run_id)
    with SessionLocal() as db:
        run = db.get(m.AnalyticsRun, run_id)
        print(f"Run {run_id}: {run.status}", flush=True)
        print(run.result if success else run.error, flush=True)
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
