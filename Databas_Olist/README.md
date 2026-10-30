# Olist PostgreSQL database setup

This folder contains a PostgreSQL schema for the nine CSV files in the Olist archive (`archive (5).zip`). It creates a separate database named `olist_ecommerce`, so the existing UCI Online Retail database can remain available.

The Olist public dataset contains Brazilian marketplace orders from 2016–2018. It is not recent enough to represent current 2026 trends, but it provides more related data than the project's current UK dataset: customer and seller locations, products, order items, payments, reviews, and delivery timestamps.

## Files

- `01_create_database.sql` optionally creates the `olist_user` login and `olist_ecommerce` database. Skip it if you already created the database and login in pgAdmin.
- `02_create_tables.sql` creates all nine Olist tables and indexes. Run it after connecting to `olist_ecommerce`.
- `03_enable_project_analytics.sql` adds read-only compatibility views and result tables so the existing dashboard and analytics can work with Olist. Run it after all nine CSVs are loaded.

## Setup in pgAdmin

1. Extract `archive (5).zip` to a convenient folder. It contains these nine CSV files:
   `olist_customers_dataset.csv`, `olist_geolocation_dataset.csv`, `olist_order_items_dataset.csv`, `olist_order_payments_dataset.csv`, `olist_order_reviews_dataset.csv`, `olist_orders_dataset.csv`, `olist_products_dataset.csv`, `olist_sellers_dataset.csv`, and `product_category_name_translation.csv`.
2. If needed, create a PostgreSQL database called `olist_ecommerce` in pgAdmin. If using `01_create_database.sql`, open Query Tool on the default `postgres` database and run it. `CREATE DATABASE` must run outside a transaction; if pgAdmin reports a transaction error, execute that statement separately with Auto-commit enabled.
3. In pgAdmin, select `olist_ecommerce`, open Query Tool, and run `02_create_tables.sql`.
4. Import the CSVs using each target table's **Import/Export Data** dialog. Choose **Import**, select the matching CSV, enable **Header**, set delimiter to comma, quote to `"`, and encoding to UTF-8. Keep the column list in the CSV's original order. For blank fields, use an empty string as NULL so nullable dates, text and product measurements load as SQL NULL.
5. Import in this order to satisfy foreign keys:

   `olist_customers`, `olist_sellers`, `olist_products`, `product_category_name_translation`, `olist_geolocation`, `olist_orders`, `olist_order_items`, `olist_order_payments`, `olist_order_reviews`.

   `olist_geolocation` has an extra generated `geolocation_id` column not present in its CSV. Import the CSV columns by name and let PostgreSQL generate that ID.
6. Refresh `Schemas > public > Tables` in pgAdmin and verify the row counts with the SQL below.

```sql
SELECT 'olist_customers' AS table_name, COUNT(*) FROM olist_customers
UNION ALL SELECT 'olist_geolocation', COUNT(*) FROM olist_geolocation
UNION ALL SELECT 'olist_order_items', COUNT(*) FROM olist_order_items
UNION ALL SELECT 'olist_order_payments', COUNT(*) FROM olist_order_payments
UNION ALL SELECT 'olist_order_reviews', COUNT(*) FROM olist_order_reviews
UNION ALL SELECT 'olist_orders', COUNT(*) FROM olist_orders
UNION ALL SELECT 'olist_products', COUNT(*) FROM olist_products
UNION ALL SELECT 'olist_sellers', COUNT(*) FROM olist_sellers
UNION ALL SELECT 'product_category_name_translation', COUNT(*) FROM product_category_name_translation
ORDER BY table_name;
```

7. After the row counts look right, open Query Tool on the same database and run `03_enable_project_analytics.sql`. This creates compatibility views named `customers`, `products`, `orders`, and `order_items`, plus result tables used by the app. The views read from the Olist source tables without changing or deleting the imported data. The script ends with row counts for the compatibility views.

## Backend connection

After the database is created, point `backend/.env` at it, using the login and password you configured:

```env
DATABASE_URL=postgresql+psycopg2://olist_user:change_me@localhost:5432/olist_ecommerce
```

URL-encode special characters in the password (for example, `@` as `%40`). The Olist recommendation page reads directly from the Olist tables. The other analytics use the compatibility views and result tables created by `03_enable_project_analytics.sql`. The UCI workbook upload is not available in Olist mode; import or replace Olist CSV data through pgAdmin.

## Table relationships

- `olist_orders.customer_id` → `olist_customers.customer_id`
- `olist_order_items.order_id` → `olist_orders.order_id`
- `olist_order_items.product_id` → `olist_products.product_id`
- `olist_order_items.seller_id` → `olist_sellers.seller_id`
- `olist_order_payments.order_id` → `olist_orders.order_id`
- `olist_order_reviews.order_id` → `olist_orders.order_id`
- Product category translation joins to `olist_products` by category name.
- Geolocation is kept as a lookup dataset because postal prefixes can have multiple coordinate rows.

## Apache Spark RFM

After loading Olist and running `03_enable_project_analytics.sql`, follow
[the Spark setup guide](../backend/SPARK_SETUP.md). The Customers & RFM page
uses Spark by default for Olist, with a Pandas option for comparison. Spark
reads the source tables through JDBC and saves scores to the existing analytics
tables; no changes to `02_create_tables.sql` are needed.
