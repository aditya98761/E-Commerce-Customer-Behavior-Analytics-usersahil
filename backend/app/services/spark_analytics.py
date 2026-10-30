"""Olist RFM computed in Spark; only aggregated results leave Spark.

Imported by the worker, never during normal API startup. JDBC reads are limited
to one connection per source table; joins and RFM aggregations execute in Spark.
"""
from datetime import datetime, time, timedelta
from pathlib import Path
import os
import re
import sys
import tempfile
from urllib.parse import quote, urlencode
from urllib.request import urlopen
from zipfile import ZipFile, BadZipFile

import pyspark
from pyspark.sql import SparkSession, Window, functions as F
from sqlalchemy.engine import make_url

from ..config import settings


def jdbc_options(database_url: str) -> dict:
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql" or not url.host or not url.database:
        raise ValueError("Spark requires a PostgreSQL DATABASE_URL with a host and database name.")
    host = f"[{url.host}]" if ":" in url.host else url.host
    # libpq and pgJDBC spell these connection options differently.
    names = {"connect_timeout": "connectTimeout", "application_name": "ApplicationName"}
    query = {names.get(k, k): v for k, v in url.query.items()}
    if any(isinstance(v, tuple) for v in query.values()):
        raise ValueError("Repeated DATABASE_URL query options are not supported by the Spark job.")
    jdbc_url = f"jdbc:postgresql://{host}:{url.port or 5432}/{quote(url.database, safe='')}"
    if query:
        jdbc_url += "?" + urlencode(query)
    return {"url": jdbc_url, "user": url.username or "", "password": url.password or "",
            "driver": "org.postgresql.Driver", "fetchsize": "10000",
            "preferTimestampNTZ": "true", "pushDownAggregate": "false"}


def _validate_jdbc_jar(path: Path) -> Path:
    try:
        with ZipFile(path) as jar:
            if "org/postgresql/Driver.class" not in jar.namelist() or jar.testzip() is not None:
                raise ValueError("PostgreSQL JDBC JAR is invalid or incomplete.")
    except (OSError, BadZipFile) as exc:
        raise ValueError(f"Cannot read PostgreSQL JDBC JAR: {path}") from exc
    return path.resolve()


def local_jdbc_jar(data_dir: Path) -> Path:
    """Resolve a local driver without Spark's Windows file-copy/chmod path."""
    if settings.spark_jdbc_jar:
        return _validate_jdbc_jar(Path(settings.spark_jdbc_jar))
    match = re.fullmatch(r"org\.postgresql:postgresql:(\d+\.\d+\.\d+)", settings.spark_jdbc_package)
    if not match:
        raise ValueError("For local Windows Spark, use org.postgresql:postgresql:<version> or set SPARK_JDBC_JAR.")
    version = match.group(1)
    cached = data_dir / "ivy" / "jars" / f"org.postgresql_postgresql-{version}.jar"
    if cached.is_file():
        return _validate_jdbc_jar(cached)
    target = data_dir / "jdbc" / f"postgresql-{version}.jar"
    if target.is_file():
        return _validate_jdbc_jar(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        # Download from the driver's publisher over HTTPS, then validate and
        # publish atomically so interrupted/concurrent starts cannot leave a
        # partial driver at the cache path.
        with urlopen(f"https://jdbc.postgresql.org/download/postgresql-{version}.jar", timeout=60) as response:
            with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".jar", delete=False) as output:
                temporary = Path(output.name)
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
        _validate_jdbc_jar(temporary)
        temporary.replace(target)
        return target.resolve()
    except Exception as exc:
        raise RuntimeError("Could not prepare the PostgreSQL JDBC driver. Set SPARK_JDBC_JAR to a valid local driver JAR; see SPARK_SETUP.md.") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def create_spark(*, jdbc: bool = True):
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)
    # Spark's Windows launcher otherwise mis-detects Python paths with spaces.
    os.environ.setdefault("SPARK_HOME", str(Path(pyspark.__file__).resolve().parent))
    data_dir = Path(__file__).resolve().parents[2] / "data" / "spark"
    data_dir.mkdir(parents=True, exist_ok=True)
    builder = (SparkSession.builder.appName("Olist RFM analytics")
               .master(settings.spark_master)
               .config("spark.sql.session.timeZone", "UTC")
               .config("spark.sql.shuffle.partitions", str(settings.spark_shuffle_partitions))
               .config("spark.sql.warehouse.dir", (data_dir / "warehouse").as_uri())
               .config("spark.jars.ivy", str(data_dir / "ivy"))
               .config("spark.local.dir", str(data_dir / "tmp")))
    if jdbc:
        if os.name == "nt" and (settings.spark_master == "local" or settings.spark_master.startswith("local[")):
            # The worker owns a fresh JVM, so these settings reach spark-submit
            # before JVM launch. Local executors share that JVM. Do not use
            # spark.jars/packages here: their fetchFile -> chmod calls require
            # winutils.exe even though the JDBC workload needs no Hadoop I/O.
            jar = local_jdbc_jar(data_dir)
            builder = (builder.config("spark.driver.extraClassPath", str(jar))
                       .config("spark.executor.extraClassPath", str(jar)))
        elif settings.spark_jdbc_jar:
            builder = builder.config("spark.jars", _validate_jdbc_jar(Path(settings.spark_jdbc_jar)).as_uri())
        else:
            builder = builder.config("spark.jars.packages", settings.spark_jdbc_package)
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark


def join_olist_items(customers, orders, items, mapping):
    """Collapse order-specific customer IDs to the project's stable customer ID."""
    purchases = (orders.filter(F.col("order_status") == "delivered")
                 .join(customers, "customer_id")
                 .join(items, "order_id"))
    if purchases.join(mapping, "customer_unique_id", "left_anti").limit(1).count():
        raise ValueError("Olist customer mapping is incomplete. Re-run Databas_Olist/03_enable_project_analytics.sql.")
    # The source customer_id is an Olist per-order ID; map IDs are integers used
    # by customer_segments and the existing dashboard.
    return (purchases.drop("customer_id").join(mapping, "customer_unique_id")
            .select("customer_id", F.col("order_id").alias("invoice_no"),
                    F.col("order_purchase_timestamp").alias("invoice_date"),
                    F.col("price").alias("line_total")))


def read_olist_items(spark, database_url: str):
    options = jdbc_options(database_url)

    def read(table, columns):
        return spark.read.format("jdbc").options(**options).option("dbtable", f"public.{table}").load().select(*columns)

    return join_olist_items(
        read("olist_customers", ["customer_id", "customer_unique_id"]),
        read("olist_orders", ["order_id", "customer_id", "order_status", "order_purchase_timestamp"]),
        read("olist_order_items", ["order_id", "price"]),
        read("analytics_customer_map", ["customer_id", "customer_unique_id"]),
    )


def compute_rfm(items):
    """Match Pandas' elapsed-day recency and rank(method='first') qcut scores."""
    items = items.filter(F.col("customer_id").isNotNull())
    stats = items.agg(F.countDistinct("customer_id").alias("customers"),
                      F.max("invoice_date").alias("last")).first()
    if stats.customers < 10:
        raise ValueError("At least 10 identified customers are required for RFM quintile scoring.")
    snapshot = datetime.combine(stats.last.date() + timedelta(days=1), time.min)
    rfm = (items.groupBy("customer_id")
           .agg(F.max("invoice_date").alias("last"), F.countDistinct("invoice_no").alias("frequency"),
                F.sum("line_total").alias("monetary"))
           .filter(F.col("monetary") > 0)
           .withColumn("recency", F.floor((F.unix_timestamp(F.lit(snapshot)) - F.unix_timestamp("last")) / 86400).cast("int"))
           .drop("last"))
    count = rfm.count()
    if count < 10:
        raise ValueError("At least 10 customers with positive spending are required for RFM quintile scoring.")
    # qcut on ranks has edges 1 + (n-1)*q. ntile(5) differs for uneven
    # populations. Tie-break by customer_id, as in Pandas' sorted groupby.
    for metric, score in (("recency", "r_score"), ("frequency", "f_score"), ("monetary", "m_score")):
        rank = F.row_number().over(Window.orderBy(metric, "customer_id"))
        quintile = F.greatest(F.lit(1), F.ceil((rank - 1) * 5 / (count - 1))).cast("int")
        rfm = rfm.withColumn(score, 6 - quintile if metric == "recency" else quintile)
    r, f = F.col("r_score"), F.col("f_score")
    segment = (F.when((r >= 4) & (f >= 4), "Champions")
               .when((r == 3) & (f >= 4), "Loyal Customers")
               .when((r <= 2) & (f >= 4), "Can't Lose Them")
               .when((r <= 2) & (f == 3), "At Risk")
               .when((r >= 4) & (f == 1), "New Customers")
               .when((r >= 4) & f.isin(2, 3), "Potential Loyalists")
               .when((r == 3) & f.isin(2, 3), "Need Attention")
               .when((r == 3) & (f == 1), "About to Sleep")
               .otherwise("Hibernating"))
    return rfm.withColumn("segment", segment), snapshot, count


def segment_summary(rfm):
    summary = rfm.groupBy("segment").agg(
        F.count("customer_id").alias("customers"),
        F.bround(F.avg("recency"), 2).alias("avg_recency"),
        F.bround(F.avg("frequency"), 2).alias("avg_frequency"),
        F.bround(F.avg("monetary"), 2).cast("double").alias("avg_monetary"),
        F.bround(F.sum("monetary"), 2).cast("double").alias("revenue"),
    )
    return [row.asDict() for row in summary.orderBy("segment").collect()]
