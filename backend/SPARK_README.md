# Apache Spark Integration

This project uses **PySpark** to run scalable RFM (Recency, Frequency, Monetary)
analysis on the Olist PostgreSQL dataset. Spark is integrated as a separate
analytics worker so that the FastAPI process remains responsible for API
requests, run tracking, and result delivery.

## What Apache Spark does

Apache Spark is a distributed data-processing engine. It divides data into
partitions and executes transformations such as filters, joins, grouping, and
sorting in parallel. Spark uses lazy evaluation: transformations build an
execution plan, and actions such as `count()` or `collect()` trigger execution.

PySpark is Spark's Python API. This project runs Spark locally by default, but
the processing design can be adapted to a multi-machine Spark cluster for
larger workloads.

## Spark's role in this project

Spark is used specifically for **Olist RFM analysis**:

1. Read the required Olist PostgreSQL tables through JDBC.
2. Keep delivered orders only.
3. Join customers, orders, order items, and the project customer mapping.
4. Aggregate purchase history per customer.
5. Calculate recency, frequency, and monetary values.
6. Assign deterministic scores from 1 to 5.
7. Assign business segments such as `Champions`, `At Risk`, and
   `Potential Loyalists`.
8. Produce segment-level summary metrics.
9. Stream customer-level results back to Python in batches.
10. Save the results in the existing PostgreSQL analytics tables.

The source tables are read-only from Spark and are never replaced.

## Processing architecture

```text
React Customers & RFM page
             |
             v
FastAPI creates an analytics run
             |
             v
Separate Python/JVM Spark worker
             |
             v
PostgreSQL tables <- JDBC -> Spark DataFrames
                              |
                              v
                 Joins, filtering, RFM, scoring
                              |
                              v
              Customer-level rows streamed in batches
                              |
                              v
              customer_segments and analytics_runs
```

Relevant implementation files:

- `app/services/spark_analytics.py` - Spark session, JDBC reads, joins, RFM
  calculations, and segment summaries.
- `app/services/spark_jobs.py` - Separate-process Spark job launcher and engine
  selection.
- `scripts/spark_rfm.py` - Spark worker entry point and result persistence.
- `scripts/benchmark_pandas_vs_spark.py` - Optional performance comparison.
- `tests/test_spark_analytics.py` - Real Spark/JVM tests.
- `tests/test_spark_dispatch.py` - Worker dispatch and failure-handling tests.

## RFM calculation

### Recency

The snapshot is midnight on the day after the latest identified purchase.
Recency is the number of whole elapsed days between the snapshot and each
customer's latest delivered order.

### Frequency

Frequency is the number of distinct delivered orders for a customer. It counts
orders rather than individual order items.

### Monetary value

Monetary value is the sum of item prices in BRL. Freight and payment records are
not included because joining them can duplicate order-item amounts.

Customers with positive monetary value are ranked into five groups. Recency
scores are reversed because a lower number of elapsed days is better. Frequency
and monetary scores increase with the customer's rank. Customer ID is used as a
deterministic tie-breaker.

## Supported data sources and engines

| Data source | Automatic engine | Spark support |
|---|---|---|
| Olist PostgreSQL dataset | PySpark | Yes |
| UCI Online Retail dataset | Pandas | No |

Spark RFM requires the Olist PostgreSQL schema and the
`analytics_customer_map` mapping created by
`Databas_Olist/03_enable_project_analytics.sql`.

The other analytics retain their current implementations:

- K-Means clustering: existing analytics service
- Apriori market-basket analysis: existing analytics service
- Forecasting: existing analytics service
- Recommendations: existing analytics service

## Requirements

- Python 3.11
- Java 17
- PostgreSQL 15 or newer
- PySpark 4.0.1
- A loaded Olist database

Install the optional Spark dependency from the `backend` directory:

```powershell
python -m pip install -r requirements.txt -r requirements-spark.txt
```

On Windows, use the project's Python 3.11 environment. The older root
`myenv` environment uses Python 3.9 and is not the supported environment for
the Spark integration.

Verify Java:

```powershell
java -version
```

Set `JAVA_HOME` if Java is not already available to the terminal.

## Configuration

Spark settings are read from `backend/.env`:

```env
SPARK_MASTER=local[2]
SPARK_SHUFFLE_PARTITIONS=4
SPARK_JDBC_PACKAGE=org.postgresql:postgresql:42.7.14
SPARK_JDBC_JAR=
SPARK_JOB_TIMEOUT_SECONDS=1800
```

The defaults are suitable for a local development machine:

- `local[2]` runs Spark with two local worker threads.
- `SPARK_SHUFFLE_PARTITIONS` controls the default number of shuffle
  partitions.
- `SPARK_JDBC_PACKAGE` identifies the PostgreSQL JDBC driver.
- `SPARK_JDBC_JAR` can point to a local driver JAR when downloading is blocked.
- `SPARK_JOB_TIMEOUT_SECONDS` prevents a worker from running indefinitely.

The database password is read from `DATABASE_URL`. It is passed to the worker
through the environment and is not included in command-line arguments.

## Database preparation

Before running Olist Spark RFM:

1. Import all required Olist CSV files into PostgreSQL.
2. Run `Databas_Olist/03_enable_project_analytics.sql`.
3. Set `DATABASE_URL` in `backend/.env`.
4. Start the backend using the same Python environment that contains PySpark.

## Running Spark RFM

Start the backend from the `backend` directory:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Then open **Customers & RFM** in the frontend:

1. Leave **Automatic (Spark for Olist)** selected, or select
   **Apache Spark (Olist)**.
2. Click **Run RFM analysis**.
3. Allow the page to poll the analytics run.
4. View the saved RFM scores and segment summaries.

The API can also start a Spark run directly:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/runs `
  -ContentType 'application/json' `
  -Body '{"run_type":"rfm","params":{"engine":"spark"}}'
```

For a standalone worker run:

```powershell
.\.venv\Scripts\python.exe -m scripts.spark_rfm
```

Spark logs are written to:

```text
backend/data/spark-logs/
```

## Result persistence and failure safety

The Spark worker streams only customer-level RFM rows to Python using
`toLocalIterator()`. It does not collect the complete transaction dataset into
driver memory.

Rows are inserted in batches of 1,000. Database transactions ensure that:

- A successful run publishes its scores and completed status together.
- A failed run rolls back partial score inserts.
- The previous successful run remains available if a new run fails.
- Sanitized errors are recorded in run history.
- Database credentials are removed from error messages.

The worker also stops Spark when the job finishes and terminates the worker if
it exceeds the configured timeout.

## Optional Pandas versus PySpark benchmark

The project includes a benchmark that compares both engines on the same
aggregation: revenue grouped by country and month.

```powershell
python -m scripts.benchmark_pandas_vs_spark `
  --file "data\Online Retail.xlsx" `
  --scale 10 `
  --repeat 3
```

Arguments:

- `--file` - Input Online Retail workbook.
- `--scale` - Replicate the cleaned rows to emulate a larger dataset.
- `--repeat` - Number of timing repetitions.

Spark may be slower than Pandas for approximately 500,000 rows on one laptop
because starting the JVM and preparing the Spark plan adds overhead. Spark's
main advantage appears when data is too large for one machine's memory or when
the workload is distributed across multiple machines.

## Testing

Normal tests do not require a live PostgreSQL server or a Spark JVM:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Real Spark tests are opt-in because they start a JVM:

```powershell
$env:RUN_SPARK_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest tests/test_spark_analytics.py -q
Remove-Item Env:RUN_SPARK_TESTS
```

The tests verify:

- JDBC driver loading and Spark startup.
- RFM parity with the Pandas implementation.
- Ties and uneven customer populations.
- Delivered-order filtering.
- Multiple items and repeat orders.
- Incomplete customer mappings.
- Empty or insufficient data.
- Safe rollback after partial streaming failures.
- Engine selection and unsupported data-source handling.
- Credential redaction in errors.

## Limitations

- The default configuration uses local Spark, not a production cluster.
- JDBC currently reads each source table with one connection.
- Global quintile ranking requires sorting and is a scaling limit.
- Spark is currently integrated only for Olist RFM.
- Do not modify the source Olist tables while a Spark run is active.
- Running many concurrent local Spark jobs may exceed laptop resources.

## References

- [Apache Spark Python installation](https://spark.apache.org/docs/4.0.1/api/python/getting_started/install.html)
- [Spark JDBC data source](https://spark.apache.org/docs/4.0.1/sql-data-sources-jdbc.html)
- [PostgreSQL JDBC downloads](https://jdbc.postgresql.org/download/)
