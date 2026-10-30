"""Real JVM tests: RUN_SPARK_TESTS=1 python -m pytest tests/test_spark_analytics.py -q."""
import os
from datetime import datetime, timedelta
from decimal import Decimal

import pandas as pd
import pytest

pytestmark = pytest.mark.skipif(os.environ.get("RUN_SPARK_TESTS") != "1", reason="Opt in to real Spark/JVM tests")
pytest.importorskip("pyspark")

from app.services import analytics as pandas_analytics
from app.services import spark_analytics as spark_analytics


@pytest.fixture(scope="module")
def spark():
    # Exercise the same JDBC-enabled startup as the real worker, while never
    # connecting to PostgreSQL. Startup without JDBC missed a Windows failure.
    session = spark_analytics.create_spark(jdbc=True)
    yield session
    session.stop()


def test_jdbc_driver_loads_and_local_tasks_execute(spark):
    driver = spark._jvm.org.postgresql.Driver()
    assert driver.acceptsURL("jdbc:postgresql://localhost/example")
    assert spark.range(3).count() == 3


@pytest.mark.parametrize("customers", [10, 11, 22])
def test_rfm_matches_pandas_with_ties_and_multiple_items(spark, customers):
    rows = []
    for cid in range(1, customers + 1):
        for order in range(1 + cid % 3):
            date = datetime(2018, 1, 1, 12, 30) + timedelta(days=cid % 5 + order)
            for value in (Decimal("10.25"), Decimal("2.50")):
                rows.append((cid, f"{cid}-{order}", date, value))
    # Guest purchases must not move the snapshot or enter scoring.
    rows.append((None, "guest", datetime(2026, 1, 1), Decimal("999.00")))
    schema = "customer_id int, invoice_no string, invoice_date timestamp_ntz, line_total decimal(12,2)"
    frame = spark.createDataFrame(rows, schema).repartition(3)
    actual, snapshot, count = spark_analytics.compute_rfm(frame)
    actual = pd.DataFrame([r.asDict() for r in actual.collect()]).sort_values("customer_id").reset_index(drop=True)
    source = pd.DataFrame(rows, columns=["customer_id", "invoice_no", "invoice_date", "line_total"])
    source["line_total"] = source.line_total.astype(float)
    expected = pandas_analytics.compute_rfm(source)
    for field in ("customer_id", "recency", "frequency", "r_score", "f_score", "m_score", "segment"):
        assert actual[field].tolist() == expected[field].tolist(), field
    assert actual.monetary.astype(float).tolist() == pytest.approx(expected.monetary.tolist())
    assert count == customers and snapshot.year == 2018


def test_olist_unique_customer_join_and_delivery_filter(spark):
    customers = spark.createDataFrame([("c1", "u1"), ("c2", "u1"), ("c3", "u2")],
                                      "customer_id string, customer_unique_id string")
    orders = spark.createDataFrame([
        ("o1", "c1", "delivered", datetime(2018, 1, 1)),
        ("o2", "c2", "delivered", datetime(2018, 1, 2)),
        ("o3", "c3", "canceled", datetime(2026, 1, 1)),
    ], "order_id string, customer_id string, order_status string, order_purchase_timestamp timestamp_ntz")
    items = spark.createDataFrame([("o1", 10.0), ("o1", 10.0), ("o2", 20.0), ("o3", 999.0)], "order_id string, price double")
    mapping = spark.createDataFrame([(1, "u1")], "customer_id int, customer_unique_id string")
    result = spark_analytics.join_olist_items(customers, orders, items, mapping).collect()
    assert len(result) == 3 and {r.customer_id for r in result} == {1}
    assert sum(r.line_total for r in result) == 40
    assert {r.invoice_no for r in result} == {"o1", "o2"}
    with pytest.raises(ValueError, match="mapping is incomplete"):
        spark_analytics.join_olist_items(customers, orders, items, mapping.filter("customer_id = 99"))


def test_empty_rfm_rejected(spark):
    frame = spark.createDataFrame([], "customer_id int, invoice_no string, invoice_date timestamp_ntz, line_total double")
    with pytest.raises(ValueError, match="At least 10"):
        spark_analytics.compute_rfm(frame)


def test_jdbc_url_conversion():
    options = spark_analytics.jdbc_options("postgresql+psycopg2://olist:s%40cret@[::1]:5433/olist?sslmode=require&connect_timeout=5")
    assert options["url"] == "jdbc:postgresql://[::1]:5433/olist?sslmode=require&connectTimeout=5"
    assert options["password"] == "s@cret" and "s@cret" not in options["url"]
    with pytest.raises(ValueError, match="PostgreSQL"):
        spark_analytics.jdbc_options("sqlite:///test.db")
