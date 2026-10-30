# Database Implementation Guide
E-Commerce Customer Behavior Analytics

> **Verification status.** The schema, Alembic migration and application queries were run on **SQLite** (tests, live server, and your own import of the full UCI dataset). The PostgreSQL DDL in `database/02_create_tables.sql` was generated from the same models with SQLAlchemy's PostgreSQL dialect but has **not been executed against a PostgreSQL server by the author**. The SQL examples in sections 6 and 7 use PostgreSQL syntax and are likewise unexecuted. Run them once and fix any error before you rely on them in a report.

---

## 1. Overview

The backend talks to the database through one setting, `DATABASE_URL`, in `backend/.env`. Nothing else in the code changes between databases.

| Mode | `DATABASE_URL` | Use for |
|---|---|---|
| SQLite | `sqlite:///./bda.db` | Quick local development, no installation |
| PostgreSQL | `postgresql+psycopg2://bda_user:change_me@localhost:5432/ecommerce_bda` | The project requirement, demos, submission |

Files that matter:

| File | Purpose |
|---|---|
| `backend/app/config.py` | Reads `.env` into settings |
| `backend/app/database.py` | Creates the SQLAlchemy engine and the `get_db` session dependency |
| `backend/app/models.py` | Table definitions (the single source of truth for the schema) |
| `backend/alembic/versions/0001_initial_schema.py` | Migration that creates all tables |
| `database/01_create_database.sql` | Creates the PostgreSQL user and database |
| `database/02_create_tables.sql` | Plain-SQL alternative to Alembic |
| `database/03_useful_checks.sql` | Row counts and recent runs |

---

## 2. Schema

```mermaid
erDiagram
    customers ||--o{ orders : places
    orders ||--|{ order_items : contains
    products ||--o{ order_items : appears_in
    analytics_runs ||--o{ customer_segments : produces
    analytics_runs ||--o{ association_rules : produces
    analytics_runs ||--o{ forecasts : produces
    customers ||--o{ customer_segments : scored_as
```

| Table | Primary key | Foreign keys | Contents |
|---|---|---|---|
| `customers` | `customer_id` | none | One row per identified customer: country, first/last order date, order count, total spent (GBP, non-cancelled) |
| `products` | `stock_code` | none | One canonical description per stock code |
| `orders` | `invoice_no` | `customer_id` → customers (nullable) | One row per invoice: date, country, `is_cancellation`, `total_amount` |
| `order_items` | `id` | `invoice_no` → orders, `stock_code` → products | Invoice lines: quantity, unit price, line total |
| `analytics_runs` | `id` | none | Every import and analysis: type, status, JSON parameters, JSON result, error, timestamps |
| `customer_segments` | `id` | `run_id` → runs (cascade delete), `customer_id` → customers | Per-run RFM values, scores, segment label or K-Means cluster |
| `association_rules` | `id` | `run_id` → runs (cascade delete) | Apriori rules: antecedents, consequents, support, confidence, lift |
| `forecasts` | `id` | `run_id` → runs (cascade delete) | Daily actual, model prediction, baseline, and phase (train/test/future) |

### Design decisions

- **Guest orders.** About a quarter of the raw rows have no CustomerID. `orders.customer_id` is nullable so these sales still count in revenue, product and forecast analysis, while being excluded from customer-level analysis.
- **Cancellations.** Invoices starting with `C` are stored with `is_cancellation = true` and negative quantities. Every revenue query filters them out; cancelled value is reported separately.
- **Denormalised totals.** `order_items.line_total`, `orders.total_amount` and `customers.total_spent` are precomputed at import time so dashboard queries are cheap aggregations rather than repeated multiplications.
- **Results are stored per run.** Segments, rules and forecasts carry a `run_id`, so history is preserved and the API simply reads the latest *completed* run. Deleting a run removes its results (`ON DELETE CASCADE`).
- **JSON columns.** `analytics_runs.params` and `.result` hold variable-shaped data (parameters differ per analysis type).
- **Constraints.** `order_items.unit_price > 0` (check constraint), unique `(run_id, customer_id)` on `customer_segments`.
- **Indexes.** On every foreign key and on the filter columns: `orders.invoice_date`, `orders.country`, `orders.is_cancellation`, `analytics_runs.run_type`, `analytics_runs.status`, `customer_segments.segment`, `association_rules.lift`, plus a composite `(invoice_no, stock_code)` on `order_items`.

---

## 3. Setting up PostgreSQL on Windows

### 3.1 Install
1. Download the installer from https://www.postgresql.org/download/windows/ and install version 15 or newer.
2. Remember the password you set for the `postgres` superuser. Keep port `5432`.
3. Make `psql` available in PowerShell. Add `C:\Program Files\PostgreSQL\<version>\bin` to your PATH, then open a new terminal and check:
   ```powershell
   psql --version
   ```

### 3.2 Create the user and database
From the project root:
```powershell
psql -U postgres -h localhost -f database\01_create_database.sql
```
This creates user `bda_user` (password `change_me`) and database `ecommerce_bda`. To use a different password, edit the file first and use the same password in `.env`.

Check that the login works:
```powershell
psql -U bda_user -h localhost -d ecommerce_bda -c "SELECT 1;"
```

### 3.3 Point the application at it
In `backend\.env`:
```
DATABASE_URL=postgresql+psycopg2://bda_user:change_me@localhost:5432/ecommerce_bda
```
Format: `postgresql+psycopg2://USER:PASSWORD@HOST:PORT/DATABASE`. URL-encode special characters in the password (`@` becomes `%40`, `#` becomes `%23`). Restart uvicorn after any `.env` change; `--reload` does not watch it.

### 3.4 Create the tables (choose one)

**Option A: Alembic (recommended).** Run from `backend` with the virtual environment active:
```powershell
alembic upgrade head
```

**Option B: plain SQL.**
```powershell
psql -U bda_user -h localhost -d ecommerce_bda -f ..\database\02_create_tables.sql
```
Do not run both on the same database. To switch method, drop and recreate the database first.

Confirm in psql: `\dt` should list the 8 tables (plus `alembic_version` if you used Option A).

### 3.5 Load the data
```powershell
python -m scripts.import_dataset                         # downloads from UCI
python -m scripts.import_dataset --file "Online Retail.xlsx"   # or use a local file
```
The import runs inside a single database session: it clears the data tables, then inserts products, customers, orders and items in chunks, and commits at the end. If it fails, the transaction is rolled back and the failure is recorded in `analytics_runs`.

### 3.6 Start the app
```powershell
uvicorn app.main:app --reload --port 8000
```
Open http://localhost:8000/api/health, then use the Run buttons on each page to generate analyses.

---

## 4. Switching from SQLite to PostgreSQL

1. Complete sections 3.1 to 3.2.
2. Change `DATABASE_URL` in `.env` (section 3.3) and restart uvicorn.
3. Create the tables on the new database (section 3.4).
4. **Re-import the dataset** (section 3.5) and re-run the analyses. Data is not copied between the two databases; `bda.db` is a separate file and can be kept as a backup or deleted.
5. Record how long the import and each run take on PostgreSQL (see Run History). A comparison with your SQLite timings is useful material for the report.

---

## 5. How the application connects

```
.env  →  app/config.py (Settings.database_url)
      →  app/database.py (create_engine, SessionLocal)
      →  FastAPI route: db: Session = Depends(get_db)   # one session per request
      →  SQLAlchemy models (app/models.py)
```

- The engine uses `pool_pre_ping=True`, so stale connections are replaced automatically.
- Long jobs (import and analyses) run as background tasks. Each opens its **own** session via `SessionLocal` and closes it when finished, so request sessions are never shared across threads.
- Alembic reads the same `DATABASE_URL` through `alembic/env.py`, so the migration always targets whatever your `.env` points to.

### Changing the schema later
```powershell
# edit app/models.py, then:
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
alembic downgrade -1        # undo the last migration
```
Review the generated migration file before applying it.

---

## 6. Verification queries

Run in psql or pgAdmin (`psql -U bda_user -h localhost -d ecommerce_bda`):

```sql
-- Row counts
SELECT 'orders' AS tbl, COUNT(*) FROM orders
UNION ALL SELECT 'order_items', COUNT(*) FROM order_items
UNION ALL SELECT 'customers', COUNT(*) FROM customers
UNION ALL SELECT 'products', COUNT(*) FROM products;

-- Run history
SELECT id, run_type, status, started_at, finished_at,
       EXTRACT(EPOCH FROM (finished_at - started_at)) AS seconds
FROM analytics_runs ORDER BY id DESC LIMIT 10;

-- Referential integrity: both should return 0
SELECT COUNT(*) FROM order_items oi LEFT JOIN orders o ON o.invoice_no = oi.invoice_no WHERE o.invoice_no IS NULL;
SELECT COUNT(*) FROM orders WHERE customer_id IS NOT NULL
  AND customer_id NOT IN (SELECT customer_id FROM customers);
```

---

## 7. Example analytical SQL (for your report)

```sql
-- Monthly revenue (GBP, excluding cancellations)
SELECT date_trunc('month', invoice_date) AS month,
       ROUND(SUM(total_amount)::numeric, 2) AS revenue,
       COUNT(*) AS orders
FROM orders WHERE NOT is_cancellation
GROUP BY 1 ORDER BY 1;

-- Top 10 products by revenue
SELECT p.stock_code, p.description, ROUND(SUM(oi.line_total)::numeric, 2) AS revenue
FROM order_items oi
JOIN orders o ON o.invoice_no = oi.invoice_no AND NOT o.is_cancellation
JOIN products p ON p.stock_code = oi.stock_code
GROUP BY 1, 2 ORDER BY revenue DESC LIMIT 10;

-- Repeat purchase rate
SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE order_count >= 2) / COUNT(*), 1) AS repeat_pct
FROM customers WHERE order_count >= 1;

-- Revenue by RFM segment (latest completed RFM run)
SELECT cs.segment, COUNT(*) AS customers, ROUND(SUM(cs.monetary)::numeric, 0) AS revenue
FROM customer_segments cs
WHERE cs.run_id = (SELECT MAX(id) FROM analytics_runs WHERE run_type = 'rfm' AND status = 'completed')
GROUP BY 1 ORDER BY revenue DESC;

-- Strongest association rules of the latest basket run
SELECT antecedents, consequents, support, confidence, lift
FROM association_rules
WHERE run_id = (SELECT MAX(id) FROM analytics_runs WHERE run_type = 'basket' AND status = 'completed')
ORDER BY lift DESC LIMIT 10;
```

### Checking index use
```sql
EXPLAIN ANALYZE
SELECT country, SUM(total_amount) FROM orders WHERE NOT is_cancellation GROUP BY country;
```
Run it before and after dropping an index to show the effect in your report.

---

## 8. Maintenance

```powershell
# Backup and restore (custom format)
pg_dump -U bda_user -h localhost -d ecommerce_bda -F c -f bda_backup.dump
pg_restore -U bda_user -h localhost -d ecommerce_bda --clean --if-exists bda_backup.dump

# Start completely fresh
psql -U postgres -h localhost -c "DROP DATABASE ecommerce_bda;"
psql -U postgres -h localhost -c "CREATE DATABASE ecommerce_bda OWNER bda_user;"
alembic upgrade head
```

- Re-importing a dataset **deletes** all existing business data and derived results (segments, rules, forecasts) but keeps run history.
- Do not commit `.env` or `bda.db` to Git (both are in `.gitignore`).

---

## 9. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `password authentication failed for user "bda_user"` | Password in `.env` differs from the database. Reset: `psql -U postgres -h localhost -c "ALTER USER bda_user WITH PASSWORD 'change_me';"` |
| Browser shows "Cannot reach the API" but uvicorn is running | The backend is returning 500 (usually a database error); read the uvicorn log |
| `could not connect to server` | PostgreSQL service not running. Start it in Windows Services |
| `database "ecommerce_bda" does not exist` | Run `01_create_database.sql` |
| `relation "orders" does not exist` | Tables not created. Run `alembic upgrade head` |
| `permission denied for schema public` (PostgreSQL 15+) | Run as superuser: `psql -U postgres -h localhost -d ecommerce_bda -c "GRANT ALL ON SCHEMA public TO bda_user;"` |
| `table ... already exists` during migration | Tables were created by both options. Drop and recreate the database |
| Changes to `.env` ignored | Restart uvicorn |
| Dashboard says "No data yet" | The import has not been run, or it ran against a different database than the one in `.env` |

---

## 10. Known limitations

- Background jobs run inside the API process and are lost if the server restarts mid-run.
- A cancellation is stored as its own invoice; it is not linked back to the original order it reverses.
- The import replaces the whole dataset; there is no incremental load.
- There is no authentication or per-user data separation.
- Automated tests run on SQLite only.
