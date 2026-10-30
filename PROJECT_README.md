# E-Commerce Customer Behavior Analytics

## 1. Project overview

E-Commerce Customer Behavior Analytics is a full-stack analytics platform for
understanding online retail purchasing behavior. It combines:

- A React and TypeScript frontend.
- A FastAPI and Python backend.
- PostgreSQL for persistent data and analysis results.
- Pandas and scikit-learn for the standard analytics workflow.
- PySpark for scalable Olist RFM processing.

The application provides dashboards, customer segmentation, product analysis,
market-basket rules, personalized recommendations, revenue forecasting, data
quality reporting, and analysis run history.

The system is designed around persisted batch analysis. Expensive calculations
are started as background runs, saved to PostgreSQL, and then read by the
frontend. The application does not retrain or recalculate expensive models on
every page request.

## 2. Main objectives

The project demonstrates:

1. A complete extract-transform-load (ETL) pipeline.
2. Data quality validation for messy transactional data.
3. Relational data modeling with primary keys, foreign keys, constraints, and
   indexes.
4. Customer-level RFM analysis.
5. Unsupervised customer clustering.
6. Market-basket and association-rule mining.
7. Time-series revenue forecasting.
8. Collaborative-filtering-style product recommendations.
9. Persistent background analytics jobs.
10. Distributed processing concepts through Apache Spark and PySpark.

## 3. Data sources

### UCI Online Retail

The main UCI dataset represents transactions from a UK online retailer between
01/12/2010 and 09/12/2011. It contains approximately 541,000 raw rows, and
amounts are represented in GBP.

- Dataset page: https://archive.ics.uci.edu/dataset/352/online+retail
- Direct download: https://archive.ics.uci.edu/static/public/352/online+retail.zip

The UCI workbook importer downloads the ZIP archive, extracts the workbook,
cleans it, and loads it into PostgreSQL.

### Brazilian Olist

The project also supports the Brazilian Olist e-commerce dataset. Olist data
is imported from its CSV files into PostgreSQL using the SQL scripts in
`Databas_Olist/`. The compatibility layer created by
`Databas_Olist/03_enable_project_analytics.sql` exposes Olist data in the
analytics shape expected by the application.

Olist amounts are displayed in BRL. Olist RFM analysis uses the stable
`customer_unique_id` mapped to the application's internal customer ID.

## 4. Application features

### Dashboard

The dashboard displays:

- Total revenue.
- Number of orders.
- Average order value.
- Customer count.
- Repeat-purchase rate.
- Cancellations and canceled value.
- Revenue trends by day, week, or month.
- Top products by revenue or quantity.
- Revenue and orders by country.

### Customers and RFM

The customer view provides paginated customer data and RFM analysis. RFM
stands for:

- **Recency** - days since the customer's latest purchase.
- **Frequency** - number of distinct invoices or orders.
- **Monetary** - total non-cancelled customer spending.

Customers receive scores from 1 to 5 and are assigned segments such as
Champions, Loyal Customers, At Risk, New Customers, and Hibernating.

For UCI data, RFM uses Pandas. For Olist data, automatic mode uses the Spark
implementation described in [Spark implementation](#13-apache-spark-implementation).

### Customer segmentation

The clustering workflow:

1. Computes RFM features.
2. Applies `log1p` to reduce right skew.
3. Standardizes features using `StandardScaler`.
4. Evaluates candidate values of `k` from 2 through 8 using silhouette score.
5. Samples up to 5,000 points for model selection.
6. Stores cluster assignments, profiles, and a PCA two-dimensional projection.

### Products and market baskets

The market-basket workflow:

1. Builds invoice-product baskets.
2. Limits processing to the most frequent products to control memory usage.
3. Drops single-item baskets.
4. Runs Apriori itemset mining.
5. Generates association rules.
6. Filters rules by support, confidence, and lift.

The current implementation uses at most the top 150 products and a maximum
itemset length of three. At most 2,000 generated rules are stored for a run.

The main metrics are:

```text
support    = proportion of baskets containing the itemset
confidence = P(consequent | antecedent)
lift       = confidence / P(consequent)
```

### Recommendations

Recommendations use delivered-product purchase histories:

1. Find customers with similar product histories.
2. Calculate Jaccard similarity.
3. Score products the selected customer has not purchased.
4. Fall back to popular products when no similar-customer candidates exist.

The UCI workflow uses product codes and descriptions. Olist recommendations
use the Olist product identifiers and category information because Olist's
public catalog does not always contain product names.

### Forecasting

The forecasting workflow predicts daily revenue:

- Non-trading days are represented as zero revenue.
- The final 28 days are held out as a chronological test window.
- Features include calendar fields, 28/35/42-day revenue lags, and a shifted
  seven-day rolling mean.
- A `GradientBoostingRegressor` is compared with a seasonal-naive baseline.
- Metrics include MAE and RMSE.
- The final model is refitted on all available history before forecasting the
  future horizon.

The feature shifts prevent test-period look-ahead and recursive forecasting
leakage.

### Data import and quality

The import page accepts the UCI workbook or a compatible CSV. It reports:

- Raw and cleaned row counts.
- Removed duplicates.
- Missing customer IDs.
- Cancellations.
- Invalid quantities and prices.
- Removed non-product codes.
- Description filling.
- Final loaded counts.

### Run history

Each import or analytics operation is represented by a persisted run:

```text
pending -> running -> completed
                    -> failed
```

The history page displays parameters, timing, results, errors, and the engine
used for the run.

## 5. Data-cleaning rules

The cleaning pipeline in `backend/app/services/cleaning.py` applies these
decisions:

| Data issue | Project decision |
|---|---|
| Exact duplicate rows | Remove them and report the count. |
| Missing `CustomerID` | Keep for revenue, product, and forecast analysis; exclude from customer-level RFM and clustering. |
| Cancellations | Keep and flag them, but exclude them from revenue, RFM, baskets, and forecasts. |
| Invalid quantity on normal invoice | Remove quantities less than or equal to zero. |
| Invalid quantity on cancellation | Remove quantities greater than or equal to zero. |
| Non-positive unit price | Remove and enforce a database constraint. |
| Non-product codes | Remove codes such as POST, D, M, BANK CHARGES, and AMAZONFEE. |
| Missing description | Use the most frequent description for the stock code, otherwise `UNKNOWN`. |
| Currency | Keep the source currency; do not convert it. |

Guest sales remain available for business-level revenue analysis but cannot be
assigned to an identified customer.

## 6. System architecture

```text
React + Vite + TypeScript + Tailwind + Recharts
                         |
                    Axios/HTTP
                         |
FastAPI + Pydantic + SQLAlchemy + background jobs
                         |
                      PostgreSQL
                         |
       UCI importer / Olist compatibility views

Optional Olist RFM path:
FastAPI -> Spark worker -> PostgreSQL JDBC -> PySpark joins and aggregations
         -> customer-level result batches -> PostgreSQL result tables
```

### Frontend

The frontend is in `frontend/` and uses:

- React 18.
- TypeScript.
- Vite.
- React Router.
- Axios.
- Recharts.
- Tailwind CSS.

Pages include Dashboard, Customers & RFM, Segmentation, Products & Baskets,
Recommendations, Forecasting, Data Import & Quality, and Run History.

### Backend

The backend is in `backend/` and uses:

- FastAPI for REST endpoints.
- Pydantic for request validation.
- SQLAlchemy for database access.
- Alembic for migrations.
- Pandas for tabular analytics and import processing.
- scikit-learn for clustering and forecasting.
- mlxtend for Apriori and association rules.
- PySpark for Olist RFM.

### Database

The normal analytics schema contains:

- `customers`
- `products`
- `orders`
- `order_items`
- `analytics_runs`
- `customer_segments`
- `association_rules`
- `forecasts`

The Olist compatibility layer adds source tables, views, and the customer
mapping needed by the shared dashboard and Spark RFM workflow.

The database includes foreign keys, indexes, a positive-price check constraint,
and a unique `(run_id, customer_id)` constraint for customer-analysis results.

## 7. API surface

The API is served by FastAPI under the `/api` prefix.

Important endpoints include:

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Check API and database connectivity. |
| `GET /api/data-source` | Detect UCI or Olist and report readiness and currency. |
| `GET /api/dashboard/summary` | Return headline business metrics. |
| `GET /api/dashboard/trends` | Return daily, weekly, or monthly trends. |
| `GET /api/dashboard/top-products` | Return top products by revenue or quantity. |
| `GET /api/dashboard/countries` | Return country-level revenue and order counts. |
| `GET /api/customers` | Return filtered and paginated customers. |
| `GET /api/rfm/summary` | Return the latest RFM summary. |
| `GET /api/clusters/latest` | Return the latest clustering output. |
| `GET /api/association-rules` | Return saved market-basket rules. |
| `GET /api/forecast/latest` | Return the latest forecast and metrics. |
| `GET /api/recommendations/customers` | Return customers available for recommendations. |
| `GET /api/recommendations/{customer_id}` | Return recommendations for a customer. |
| `POST /api/import` | Start a dataset import. |
| `GET /api/import/latest` | Return the latest import report. |
| `POST /api/runs` | Start an analytics run. |
| `GET /api/runs` | List analysis runs. |
| `GET /api/runs/{id}` | Return one run and its result. |

Interactive API documentation is available at `http://localhost:8000/docs`
when the backend is running.

## 8. Local setup

### Prerequisites

- Windows PowerShell.
- Python 3.11 or newer.
- Node.js 20 or newer.
- PostgreSQL 15 or newer with `psql` on `PATH`.
- Java 17 only when using Spark.

### Create the database

```powershell
psql -U postgres -c "CREATE USER bda_user WITH PASSWORD 'change_me';"
psql -U postgres -c "CREATE DATABASE ecommerce_bda OWNER bda_user;"
```

Use a real local password in your environment. Do not commit credentials.

### Install the backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend/.env` and set `DATABASE_URL` for the local PostgreSQL database.
Then create the schema:

```powershell
alembic upgrade head
```

### Import the UCI dataset

The default importer downloads the UCI Online Retail archive:

```powershell
python -m scripts.import_dataset
```

If downloading is unavailable, download `Online Retail.xlsx` manually and run:

```powershell
python -m scripts.import_dataset --file "C:\path\Online Retail.xlsx"
```

### Prepare Olist

For Olist support:

1. Import all nine Olist CSV files into PostgreSQL.
2. Run `Databas_Olist/03_enable_project_analytics.sql`.
3. Point `DATABASE_URL` at that database.
4. Confirm readiness with `GET /api/data-source`.

### Start the backend

```powershell
uvicorn app.main:app --reload --port 8000
```

### Install and start the frontend

In a second terminal:

```powershell
cd frontend
Copy-Item .env.example .env
npm install
npm run dev
```

Open `http://localhost:5173`.

## 9. Apache Spark implementation

### Purpose

Apache Spark is a distributed data-processing engine. PySpark is its Python
API. In this project, Spark is integrated specifically for Olist RFM
processing; it does not replace every existing analytics engine.

The Spark implementation is documented separately in
[backend/SPARK_README.md](backend/SPARK_README.md) and configured by:

- `backend/app/services/spark_analytics.py`
- `backend/app/services/spark_jobs.py`
- `backend/scripts/spark_rfm.py`
- `backend/requirements-spark.txt`

### Spark execution flow

```text
Customers & RFM page
        |
        v
FastAPI creates a pending run
        |
        v
Separate Python/JVM Spark worker
        |
        v
JDBC reads Olist PostgreSQL tables
        |
        v
Spark filters, joins, aggregates, ranks, and segments
        |
        v
Customer-level rows stream to Python in batches
        |
        v
PostgreSQL customer_segments and analytics_runs
        |
        v
React reads the persisted result through FastAPI
```

### Spark data processing

The worker:

1. Reads Olist customers, orders, order items, and the analytics customer map
   through JDBC.
2. Filters to delivered orders.
3. Joins source tables on customer and order identifiers.
4. Converts Olist's stable customer identifier to the application's integer
   customer ID.
5. Calculates maximum purchase date, distinct order count, and total item
   price per customer.
6. Calculates elapsed-day recency from the day after the last purchase.
7. Assigns deterministic quintile scores for recency, frequency, and monetary
   value.
8. Assigns a customer segment from the RFM scores.
9. Calculates segment summaries.
10. Streams only customer-level rows back to Python using
    `toLocalIterator()`.

This avoids collecting the entire transaction dataset in driver memory.
Customer rows are inserted in batches of 1,000.

### Spark configuration

Optional values in `backend/.env`:

```env
SPARK_MASTER=local[2]
SPARK_SHUFFLE_PARTITIONS=4
SPARK_JDBC_PACKAGE=org.postgresql:postgresql:42.7.14
SPARK_JDBC_JAR=
SPARK_JOB_TIMEOUT_SECONDS=1800
```

`local[2]` runs Spark locally with two worker threads. A production cluster
could use a different master and partition configuration.

### Install Spark dependencies

Use Python 3.11 and Java 17:

```powershell
cd backend
python -m pip install -r requirements.txt -r requirements-spark.txt
java -version
```

### Run Spark RFM

From the Customers & RFM page, choose **Automatic (Spark for Olist)** or
**Apache Spark (Olist)** and click **Run RFM analysis**.

The API can also start a run:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/runs `
  -ContentType 'application/json' `
  -Body '{"run_type":"rfm","params":{"engine":"spark"}}'
```

Or run the worker directly:

```powershell
.\.venv\Scripts\python.exe -m scripts.spark_rfm
```

Spark logs are saved under `backend/data/spark-logs/`.

### Spark reliability

The integration:

- Runs Spark outside the FastAPI process.
- Enforces a configurable timeout.
- Records failed runs explicitly.
- Rolls back partial customer-score inserts.
- Keeps the previous successful run available after a failure.
- Redacts database credentials from error messages.
- Commits scores and completed-run status together.
- Stops the Spark session when the worker exits.

### Pandas versus PySpark benchmark

The optional benchmark compares both engines on country-and-month revenue
aggregation:

```powershell
cd backend
python -m scripts.benchmark_pandas_vs_spark `
  --file "data\Online Retail.xlsx" `
  --scale 10 `
  --repeat 3
```

Spark can be slower than Pandas for approximately 500,000 rows on one laptop
because JVM startup and query planning add overhead. Spark becomes more useful
when data exceeds one machine's memory or processing is distributed across
multiple machines.

## 10. Testing and verification

### Backend tests

```powershell
cd backend
python -m pytest -q
```

The standard tests use temporary databases and synthetic fixtures. Synthetic
rows are test data only; they are never loaded into the application.

### Frontend build

```powershell
cd frontend
npm run build
```

### Spark tests

Spark tests are opt-in because they start a JVM:

```powershell
cd backend
$env:RUN_SPARK_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest tests/test_spark_analytics.py -q
Remove-Item Env:RUN_SPARK_TESTS
```

Spark tests verify JDBC startup, RFM parity with Pandas, tie handling,
delivered-order filtering, repeated orders, multiple items, missing mappings,
empty input, rollback behavior, and error sanitization.

## 11. Project structure

```text
.
├── backend/
│   ├── app/
│   │   ├── api.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── services/
│   │       ├── analytics.py
│   │       ├── cleaning.py
│   │       ├── recommendations.py
│   │       ├── runner.py
│   │       ├── spark_analytics.py
│   │       └── spark_jobs.py
│   ├── scripts/
│   │   ├── import_dataset.py
│   │   ├── benchmark_pandas_vs_spark.py
│   │   └── spark_rfm.py
│   ├── tests/
│   ├── alembic/
│   ├── requirements.txt
│   ├── requirements-spark.txt
│   ├── SPARK_README.md
│   └── SPARK_SETUP.md
├── database/
├── Databas_Olist/
├── frontend/
│   └── src/
│       ├── pages/
│       ├── App.tsx
│       └── lib/
├── output/
├── tmp/
├── README.md
└── PROJECT_README.md
```

## 12. Limitations and future improvements

- Local Spark mode is intended for development and coursework, not production
  cluster deployment.
- Spark JDBC reads currently use one connection per source table.
- Global quintile ranking requires sorting and is a scaling limit.
- Spark is integrated only for Olist RFM.
- Apriori is limited to the top 150 products and maximum itemset length three.
- The `.xlsx` importer is slower than CSV loading.
- Background jobs run in the API environment; a production deployment should
  use a durable worker queue such as Celery or RQ.
- Re-importing the UCI dataset replaces the existing imported analytics data.
- Recommendations are based on historical similarity and are not causal
  predictions of sales impact.
- Olist compatibility views intentionally expose a shared subset of the full
  Olist schema.

## 13. Security and operational practices

- Keep database credentials in `.env`, never in source control.
- Do not commit `.env` files.
- Spark credentials are passed through the worker environment, not command-line
  arguments.
- Spark errors redact database URLs and passwords.
- Validate API run parameters through Pydantic schemas.
- Use database constraints and foreign keys to protect data integrity.
- Review `backend/data/spark-logs/` when diagnosing a failed Spark run.

## 14. References

- UCI Online Retail: https://archive.ics.uci.edu/dataset/352/online+retail
- Apache Spark Python installation: https://spark.apache.org/docs/4.0.1/api/python/getting_started/install.html
- Spark JDBC data source: https://spark.apache.org/docs/4.0.1/sql-data-sources-jdbc.html
- PostgreSQL JDBC drivers: https://jdbc.postgresql.org/download/
