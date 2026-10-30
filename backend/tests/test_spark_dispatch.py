from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import models as m
from app.database import Base
from app.services import runner
from app.services.spark_jobs import resolve_rfm_engine
from scripts.spark_rfm import execute_spark_run, persist_scores, safe_error


@pytest.fixture
def factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db:
        db.add(m.Customer(customer_id=1, country="SP", first_order_date=datetime(2018, 1, 1),
                          last_order_date=datetime(2018, 1, 1), order_count=1, total_spent=10))
        db.add(m.Product(stock_code="p1", description="Product"))
        db.add(m.Order(invoice_no="o1", customer_id=1, invoice_date=datetime(2018, 1, 1),
                       country="SP", is_cancellation=False, total_amount=10))
        db.add(m.OrderItem(invoice_no="o1", stock_code="p1", quantity=1, unit_price=10, line_total=10))
        db.commit()
    yield session_factory
    engine.dispose()


def new_run(factory):
    with factory() as db:
        run = m.AnalyticsRun(run_type="rfm", params={"engine": "spark"}, status="pending")
        db.add(run)
        db.commit()
        return run.id


def test_engine_selection_and_unsupported_source():
    assert resolve_rfm_engine("auto", "olist") == "spark"
    assert resolve_rfm_engine("auto", "legacy") == "pandas"
    assert resolve_rfm_engine("pandas", "olist") == "pandas"
    with pytest.raises(ValueError, match="Olist"):
        resolve_rfm_engine("spark", "legacy")


@pytest.mark.parametrize("worker_status", ["completed", "failed", "running"])
@pytest.mark.parametrize("shutdown_error", [False, True])
def test_worker_dispatch_does_not_load_pandas(factory, monkeypatch, worker_status, shutdown_error):
    run_id = new_run(factory)
    monkeypatch.setattr(runner, "recommendation_source", lambda db: "olist")
    monkeypatch.setattr(runner, "_items_frame", lambda db: pytest.fail("Spark must read through JDBC"))

    def worker(url, received_id):
        assert received_id == run_id
        with factory() as db:
            run = db.get(m.AnalyticsRun, run_id)
            assert run.status == "running" and run.params["engine"] == "spark"
            run.status = worker_status
            if worker_status == "failed":
                run.error = "Useful worker error"
            if worker_status == "completed":
                run.result = {"engine": "spark", "customers_scored": 10}
            db.commit()
        if shutdown_error:
            raise RuntimeError("Worker shutdown failed")

    monkeypatch.setattr(runner, "launch_spark_run", worker)
    runner.execute_run(factory, run_id)
    with factory() as db:
        run = db.get(m.AnalyticsRun, run_id)
        assert run.status == ("failed" if worker_status == "running" else worker_status)
        if worker_status == "failed":
            assert run.error == "Useful worker error"
        if worker_status == "running":
            assert ("shutdown failed" if shutdown_error else "exited") in run.error


def test_worker_failure_is_recorded(factory):
    run_id = new_run(factory)
    assert execute_spark_run(factory, run_id) is False
    with factory() as db:
        run = db.get(m.AnalyticsRun, run_id)
        assert run.status == "failed" and "PostgreSQL" in run.error
        assert not db.scalars(select(m.CustomerSegment)).all()
    with pytest.raises(ValueError, match="cannot be overwritten"):
        execute_spark_run(factory, run_id)


def test_streamed_scores_roll_back_on_failure(factory):
    from types import SimpleNamespace
    run_id = new_run(factory)

    class BrokenFrame:
        def toLocalIterator(self):
            for customer in range(1000):
                yield SimpleNamespace(customer_id=customer, recency=1, frequency=1, monetary=10,
                                      r_score=5, f_score=1, m_score=1, segment="New Customers")
            raise RuntimeError("Interrupted result stream")

    with factory() as db:
        with pytest.raises(RuntimeError, match="Interrupted"):
            persist_scores(db, run_id, BrokenFrame())
        db.rollback()
        assert not db.scalars(select(m.CustomerSegment)).all()


def test_error_redacts_database_credentials(monkeypatch):
    from scripts import spark_rfm
    monkeypatch.setattr(spark_rfm.settings, "database_url", "postgresql://user:s%40cret@localhost/olist")
    message = safe_error(ValueError("connection failed: s@cret or s%40cret"))
    assert "s@cret" not in message and "s%40cret" not in message


def test_java_root_cause_visible_and_redacted(monkeypatch):
    from scripts import spark_rfm
    monkeypatch.setattr(spark_rfm.settings, "database_url", "postgresql://user:s%40cret@localhost/olist")
    message = safe_error(RuntimeError("An error occurred while calling JavaSparkContext.\n"
                                     "Caused by: java.lang.RuntimeException: startup\n"
                                     "Caused by: java.io.FileNotFoundException: HADOOP_HOME is unset; s@cret\n"))
    assert "HADOOP_HOME is unset" in message.splitlines()[0]
    assert "s@cret" not in message and "JavaSparkContext" not in message


def test_api_rejects_invalid_or_unsupported_engine(client):
    assert client.post("/api/runs", json={"run_type": "rfm", "params": {"engine": "unknown"}}).status_code == 422
    response = client.post("/api/runs", json={"run_type": "rfm", "params": {"engine": "spark"}})
    assert response.status_code == 422 and "Olist" in response.json()["detail"]
