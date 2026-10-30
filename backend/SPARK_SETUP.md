# Apache Spark with Olist and PostgreSQL

Olist RFM runs now read the raw PostgreSQL tables through JDBC, join and score
customers in PySpark, and save customer-level results to the existing
`customer_segments` and `analytics_runs` tables. FastAPI and React continue
reading those tables. Source tables are never replaced by Spark.

## Windows setup

Use **Python 3.11 and Java 17**. This project pins PySpark 4.0.1.

Use `backend/.venv` for this setup. The older root-level `myenv` uses Python
3.9; packages installed there are separate. If your terminal prompt shows
`(myenv)`, run `deactivate` before switching environments. The explicit Python
paths below work even without activation.

From the project root, create the environment if it does not already exist:

```powershell
py -3.11 -m venv backend/.venv
cd backend
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-spark.txt
.\.venv\Scripts\python.exe -m pip check
java -version
```

If your terminal is already in `backend`, use `py -3.11 -m venv .venv` for the
creation step and omit `cd backend`. If `.venv` already exists with Python 3.11
and the requirements installed, reuse it.

### Fix: greenlet wheel build fails with a Visual C++ error

If the error names `myenv\Scripts\python.exe` and `cpython-39`, the failed
installation ran in the older Python 3.9 environment. The compiler error means
pip attempted to build `greenlet` from source and could not find the required
Microsoft C++ compiler. Switch to the project's Python 3.11 environment first.

From a PowerShell terminal already in `backend` with `(myenv)` active:

```powershell
deactivate
.\.venv\Scripts\Activate.ps1
python --version
python -m pip check
```

The version should be Python 3.11.x and the prompt should show `(.venv)`. Select
`backend/.venv/Scripts/python.exe` as your IDE's Python interpreter too. If
PowerShell blocks activation, use `.\.venv\Scripts\python.exe` explicitly;
activation is optional and no execution-policy change is required.

If packages are missing from that environment, install them using the explicit
`.venv` command in the setup block above. These steps only prepare/check the
environment; they do not start FastAPI or a Spark job.

## Start the backend when ready

Set `JAVA_HOME` to your JDK installation if it is not already configured. Start
the backend using this same environment, so the Spark worker can import PySpark:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

`backend/.env` must point to your loaded Olist PostgreSQL database. Keep your
existing database credentials. Import the nine Olist CSVs and run
`Databas_Olist/03_enable_project_analytics.sql` first. That script supplies the
customer ID mapping, compatibility views and result tables.

Optional settings (defaults already work on a laptop):

```env
SPARK_MASTER=local[2]
SPARK_SHUFFLE_PARTITIONS=4
SPARK_JDBC_PACKAGE=org.postgresql:postgresql:42.7.14
SPARK_JDBC_JAR=
SPARK_JOB_TIMEOUT_SECONDS=1800
```

The first run downloads the PostgreSQL JDBC driver from Maven. If internet
access to Maven is blocked, download a driver from
https://jdbc.postgresql.org/download/ and set `SPARK_JDBC_JAR` to its absolute
local path. Credentials are taken from `DATABASE_URL`, not embedded in code or
passed as command-line arguments. `sslmode` and URL-encoded passwords are
supported; libpq `connect_timeout` and `application_name` are translated to
their JDBC names. Other driver-specific libpq options may need adjustment.

## Run it

In **Customers & RFM**, leave **Automatic (Spark for Olist)** selected and click
**Run RFM analysis**. Explicit **Apache Spark (Olist)** and **Pandas** options
are available for comparison. The last completed engine and Spark version are
shown on the page. Run history stores the resolved engine and result metadata.

From the backend directory, a standalone run uses the same database and tables:

```powershell
.\.venv\Scripts\python.exe -m scripts.spark_rfm
```

Or submit through the API:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/runs `
  -ContentType 'application/json' `
  -Body '{"run_type":"rfm","params":{"engine":"spark"}}'
```

The API launches a separate Python/JVM process for each Spark run. Existing
polling shows its progress. Worker output is in `backend/data/spark-logs/`.
Failures are recorded without silently falling back to Pandas. Inserts and the
completed run status commit together, so a failed run cannot publish a partial
customer set. The last successful run remains visible. Local jobs have a
30-minute timeout; avoid launching many concurrent jobs on a small laptop.

## Calculation rules and scope

- Delivered orders only. Group repeat purchases by Olist `customer_unique_id`
  and use `analytics_customer_map.customer_id` for the dashboard.
- Frequency counts distinct orders, not order items. Monetary sums item prices
  in BRL, excluding freight and payments to avoid duplicate joins.
- Snapshot is midnight after the latest identified purchase. Recency is whole
  elapsed days, matching the existing Pandas calculation.
- Positive-spend customers receive deterministic quintile scores, with ties
  broken by the mapped customer ID. At least ten eligible customers are needed.
- All raw joins, aggregations, scores and segment summaries execute in Spark.
  Only aggregated customer rows stream to Python for transactional DB inserts.
- UCI RFM defaults to Pandas. K-Means, basket analysis, forecasting and
  recommendations retain their existing implementations; this integration
  specifically moves Olist RFM into Spark.
- Local mode runs on this machine. JDBC reads currently use one connection per
  source table; Spark performs the joins and shuffles. Global quintile sorting
  is a single-partition step and is a scaling limit. No cluster speedup is
  claimed. Avoid changing source tables during a run.

## Verification

From `backend`, ordinary tests do not require Spark or PostgreSQL:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Real Spark tests launch a JVM, compare RFM to Pandas for uneven populations and
ties, and check repeated customers, multiple items, canceled orders and missing
customer mappings. They use synthetic data and do not modify PostgreSQL:

```powershell
$env:RUN_SPARK_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_spark_analytics.py -q
Remove-Item Env:RUN_SPARK_TESTS
```

Reference: https://spark.apache.org/docs/4.0.1/api/python/getting_started/install.html
and https://spark.apache.org/docs/4.0.1/sql-data-sources-jdbc.html.
