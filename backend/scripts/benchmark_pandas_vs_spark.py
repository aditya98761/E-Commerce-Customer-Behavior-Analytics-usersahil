"""Optional BDA module: pandas vs PySpark on the same aggregation (revenue per country and per month).

  python -m scripts.benchmark_pandas_vs_spark --file "data/Online Retail.xlsx" --repeat 3
Requires: pip install -r requirements-spark.txt and a Java runtime. Skips Spark cleanly if unavailable.
"""
import argparse
import time

import pandas as pd

from app.services.cleaning import clean_retail
from app.services.runner import read_upload


def timeit(fn, n):
    t = []
    for _ in range(n):
        s = time.perf_counter(); fn(); t.append(time.perf_counter() - s)
    return min(t), sum(t) / len(t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--scale", type=int, default=1, help="replicate data N times to emulate larger volumes")
    a = ap.parse_args()
    df, _ = clean_retail(read_upload(a.file))
    df = pd.concat([df] * a.scale, ignore_index=True)
    df = df[~df.is_cancellation].assign(month=lambda d: d.InvoiceDate.dt.to_period("M").astype(str))
    print(f"rows={len(df):,}")
    pd_fn = lambda: df.groupby(["Country", "month"])["line_total"].sum().reset_index()  # noqa: E731
    print("pandas   best/avg s: %.3f / %.3f" % timeit(pd_fn, a.repeat))
    try:
        from pyspark.sql import SparkSession, functions as F
        spark = SparkSession.builder.master("local[*]").appName("bench").getOrCreate()
        sdf = spark.createDataFrame(df[["Country", "month", "line_total"]]).cache()
        sdf.count()  # materialise the cache so only the aggregation is timed
        sp_fn = lambda: sdf.groupBy("Country", "month").agg(F.sum("line_total")).collect()  # noqa: E731
        sp_fn()  # warm-up (JIT / shuffle setup)
        print("pyspark  best/avg s: %.3f / %.3f" % timeit(sp_fn, a.repeat))
        spark.stop()
    except Exception as exc:  # noqa: BLE001
        print(f"PySpark skipped: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
