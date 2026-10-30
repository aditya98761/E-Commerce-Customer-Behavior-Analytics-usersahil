# E-Commerce Customer Behavior Analytics

React + FastAPI + PostgreSQL analytics platform on the **real UCI Online Retail dataset** (UK online retailer, 01/12/2010–09/12/2011, currency **GBP**, ~541k raw rows). Dashboards, RFM, K-Means, Apriori, forecasting and run history all read from backend APIs and persisted results. Nothing is hardcoded.

> **Actual vs synthetic data.** The app only ever shows data you import. `backend/tests/synthetic.py` generates *synthetic* rows used **only by automated tests**; they are never loaded by the app.

## Quick start (Windows, PowerShell)

Prerequisites: Python 3.11+, Node.js 20+, PostgreSQL 15+ (with `psql` on PATH).

```powershell
# 1. Database (enter the postgres superuser password when asked)
psql -U postgres -c "CREATE USER bda_user WITH PASSWORD 'change_me';"
psql -U postgres -c "CREATE DATABASE ecommerce_bda OWNER bda_user;"

# 2. Backend
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
copy .env.example .env              # edit DATABASE_URL if you changed the password
alembic upgrade head                # creates all tables
python -m scripts.import_dataset    # downloads UCI zip, cleans, loads (xlsx: several minutes)
uvicorn app.main:app --reload --port 8000

# 3. Frontend (second terminal)
cd frontend
copy .env.example .env
npm install
npm run dev                         # http://localhost:5173
```

Alternatives: if the download is blocked, get the file from https://archive.ics.uci.edu/dataset/352/online+retail and run `python -m scripts.import_dataset --file "C:\path\Online Retail.xlsx"`, or upload it on the **Data Import & Quality** page. Then open the Customers, Segmentation, Products and Forecasting pages and click the **Run** buttons (each runs in the background; results are saved).

API docs: http://localhost:8000/docs

Tests: `cd backend; pytest -q` (uses a temporary SQLite database, no PostgreSQL needed). Frontend build check: `cd frontend; npm run build`.

## Architecture

```
frontend/ (React, Vite, TS, Tailwind, Recharts, Axios)  --HTTP/JSON-->  backend/app/
  src/pages: Dashboard, Customers, Segmentation,                          api.py        REST routes, pagination, filters
             Products, Forecast, ImportPage, History                      schemas.py    Pydantic validation of run parameters
                                                                          models.py     SQLAlchemy tables (PostgreSQL)
                                                                          services/cleaning.py   validation + cleaning
                                                                          services/analytics.py  RFM, K-Means, Apriori, forecast (pure functions)
                                                                          services/runner.py     import + background run executor
backend/alembic/  migrations      backend/tests/  analytics + API tests      backend/scripts/  import + Spark benchmark
```

Tables: `customers`, `products`, `orders`, `order_items`, `analytics_runs`, `customer_segments`, `association_rules`, `forecasts` with foreign keys, a positive-price check constraint, a unique `(run_id, customer_id)` constraint and indexes on join/filter columns. Credentials come from `.env`.

**Expensive work is never done per request.** `POST /api/runs` stores a run (`pending`), a background task executes it (`running` → `completed`/`failed`) and writes results to PostgreSQL; the UI polls the run and then reads the stored results.

**Personalized recommendations.** The Recommendations page finds customers with similar delivered-product histories, scores products they have not bought using Jaccard similarity, and falls back to popular products when no similar-customer candidates exist. It supports the current UCI schema and the Olist schema in `Databas_Olist`; the Olist database must be loaded and selected in `backend/.env` to use Olist customers. Olist's public catalog contains product IDs and categories rather than product names, so recommendations display those fields.

**Olist support for analytics.** After importing all Olist CSVs, run `Databas_Olist/03_enable_project_analytics.sql` in pgAdmin. It creates read-only views that adapt Olist customers, products, orders and items to the existing analytics query shape, plus tables for saved analysis runs. The app detects Olist and displays amounts in BRL. The UCI workbook importer remains UCI-specific; Olist data is imported into its source tables with pgAdmin.

**Apache Spark for Olist RFM.** Olist RFM now defaults to a separate PySpark job that reads PostgreSQL through JDBC and saves scores into the existing result tables. Install the optional Spark requirements using Python 3.11 and Java 17, then use the Customers & RFM run button. The page also offers Pandas for comparison. See [Spark setup and verification](backend/SPARK_SETUP.md). Other analytics retain their current engines.

Main endpoints: `GET /api/dashboard/{summary,trends,top-products,countries}`, `GET /api/customers`, `GET /api/recommendations/customers`, `GET /api/recommendations/{customer_id}`, `GET /api/rfm/summary`, `GET /api/clusters/latest`, `GET /api/association-rules`, `GET /api/forecast/latest`, `POST /api/runs`, `GET /api/runs[/id]`, `POST /api/import`, `GET /api/import/latest`.

## Preprocessing decisions (all counted in the data-quality report)

| Issue | Decision |
|---|---|
| Exact duplicate rows | Removed (can include genuine repeated scans; documented trade-off) |
| Missing `CustomerID` (~25%) | Rows **kept** for revenue/product/forecast analysis as guest sales; excluded from RFM, clustering and customer counts |
| Cancellations (`InvoiceNo` starts with `C`) | Kept and flagged `is_cancellation`; excluded from revenue, RFM, baskets and forecasts; reported separately |
| Quantity ≤ 0 on a normal invoice, or ≥ 0 on a cancellation | Removed as invalid |
| `UnitPrice` ≤ 0 | Removed (also enforced by a DB check constraint) |
| Non-product codes (POST, D, M, BANK CHARGES, AMAZONFEE…) | Removed from the item table |
| Missing description | Filled from the most frequent description of the same stock code, else `UNKNOWN` |
| Currency | GBP, never converted |

## Algorithms

- **RFM**: Recency = days from last purchase to (last dataset date + 1 day); Frequency = distinct invoices; Monetary = sum of non-cancelled line totals. Each is scored 1–5 by quintile (rank-based to avoid tied bin edges; recency reversed). Rules map R/F scores to nine named segments (Champions, Loyal, Potential Loyalists, New, Need Attention, About to Sleep, At Risk, Can't Lose Them, Hibernating); the rules cover all 25 R/F combinations (unit tested).
- **K-Means**: `log1p` to reduce right skew, `StandardScaler`, k in [2, 8] evaluated by silhouette score (sampled to 5,000 points), best k chosen unless fixed; cluster profiles and a PCA 2-D projection are stored.
- **Market basket**: invoices × products boolean matrix limited to the 150 most frequent products (memory bound), single-item baskets dropped, `apriori` (mlxtend) then `association_rules`, filtered by confidence and lift ≥ 1. Support = share of baskets containing the itemset; confidence = P(B | A); lift = confidence / P(B).
- **Forecasting**: daily GBP revenue (non-trading days are zeros). Chronological split: last 28 days = test. Features are calendar fields plus revenue lags of 28/35/42 days and a 7-day rolling mean shifted by 28 days, so every feature is available at prediction time for horizons up to 28 days (no recursive forecasting, no look-ahead). A `GradientBoostingRegressor` is scored on the test window using a model fitted **only on the training window**; it is then refitted on all history to produce the future forecast. Baseline = seasonal naive (repeat last observed week). Metrics: MAE and RMSE for both. A unit test corrupts test-period actuals and asserts that test predictions do not change.

## BDA concepts covered

Volume/Variety/Veracity (541k rows, dirty transactional data, quality report), ETL pipeline (extract → validate/clean → load), relational storage with indexing, batch analytics with persisted results, unsupervised learning (clustering), pattern mining (association rules), time-series forecasting with leakage control, and an optional scale-out discussion via PySpark.

**Optional Pandas vs PySpark benchmark:** `pip install -r requirements-spark.txt` (needs Java), then `python -m scripts.benchmark_pandas_vs_spark --file "data\Online Retail.xlsx" --scale 10 --repeat 3`. On a single laptop Pandas is normally faster for 0.5M rows; Spark's advantage appears at data sizes that exceed one machine's memory.

## Verification status

See the notes delivered with this project for what was and was not executed in the build environment. Re-run `pytest -q` and `npm run build` on your machine to confirm.

## Known limitations

- Background tasks run inside the API process (adequate for a coursework/local setup; use Celery/RQ for production). Re-importing replaces all data.
- Apriori is limited to the top 150 products and `max_len` 3 to keep memory bounded.
- The .xlsx version of the dataset loads slowly through `openpyxl`; convert to CSV for faster imports.
