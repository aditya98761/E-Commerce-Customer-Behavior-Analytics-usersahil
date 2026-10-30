"""Personalized product recommendations for the UCI and Olist schemas."""

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session


REQUIRED_TABLES = {
    "olist_customers",
    "olist_orders",
    "olist_order_items",
    "olist_products",
    "product_category_name_translation",
}
LEGACY_TABLES = {"customers", "orders", "order_items", "products"}


def recommendation_source(db: Session) -> str | None:
    inspector = inspect(db.get_bind())
    if all(inspector.has_table(table) for table in REQUIRED_TABLES):
        return "olist"
    if all(inspector.has_table(table) for table in LEGACY_TABLES):
        return "legacy"
    return None


CUSTOMERS_SQL = text("""
    SELECT c.customer_unique_id AS customer_id,
           COUNT(DISTINCT o.order_id) AS order_count,
           MAX(o.order_purchase_timestamp) AS last_order
    FROM olist_customers c
    JOIN olist_orders o ON o.customer_id = c.customer_id
    WHERE o.order_status = 'delivered'
      AND (:search = '' OR c.customer_unique_id ILIKE '%' || :search || '%')
    GROUP BY c.customer_unique_id
    ORDER BY order_count DESC, last_order DESC, customer_id
    LIMIT :limit
""")


TARGET_PRODUCTS_SQL = text("""
    SELECT oi.product_id,
           COALESCE(t.product_category_name_english, p.product_category_name, 'Uncategorized') AS category,
           COUNT(DISTINCT o.order_id) AS order_count,
           SUM(oi.price)::float AS spend
    FROM olist_customers c
    JOIN olist_orders o ON o.customer_id = c.customer_id
    JOIN olist_order_items oi ON oi.order_id = o.order_id
    JOIN olist_products p ON p.product_id = oi.product_id
    LEFT JOIN product_category_name_translation t
      ON t.product_category_name = p.product_category_name
    WHERE c.customer_unique_id = :customer_id AND o.order_status = 'delivered'
    GROUP BY oi.product_id, category
    ORDER BY order_count DESC, spend DESC
""")


COLLABORATIVE_SQL = text("""
    WITH customer_products AS (
        SELECT DISTINCT c.customer_unique_id, oi.product_id
        FROM olist_customers c
        JOIN olist_orders o ON o.customer_id = c.customer_id
        JOIN olist_order_items oi ON oi.order_id = o.order_id
        WHERE o.order_status = 'delivered'
    ),
    target_products AS (
        SELECT DISTINCT oi.product_id
        FROM olist_customers c
        JOIN olist_orders o ON o.customer_id = c.customer_id
        JOIN olist_order_items oi ON oi.order_id = o.order_id
        WHERE c.customer_unique_id = :customer_id AND o.order_status = 'delivered'
    ),
    target_size AS (SELECT COUNT(*)::float AS n FROM target_products),
    neighbors AS (
        SELECT cp.customer_unique_id,
               COUNT(*) FILTER (WHERE tp.product_id IS NOT NULL)::float AS shared,
               COUNT(*) FILTER (WHERE tp.product_id IS NOT NULL)::float
                   / NULLIF((SELECT n FROM target_size) + COUNT(*)
                       - COUNT(*) FILTER (WHERE tp.product_id IS NOT NULL), 0) AS similarity
        FROM customer_products cp
        LEFT JOIN target_products tp ON tp.product_id = cp.product_id
        WHERE cp.customer_unique_id <> :customer_id
        GROUP BY cp.customer_unique_id
        HAVING COUNT(*) FILTER (WHERE tp.product_id IS NOT NULL) > 0
        ORDER BY similarity DESC, shared DESC
        LIMIT 100
    ),
    scored AS (
        SELECT cp.product_id,
               COUNT(DISTINCT n.customer_unique_id)::integer AS similar_customer_count,
               SUM(n.similarity)::float AS score
        FROM neighbors n
        JOIN customer_products cp ON cp.customer_unique_id = n.customer_unique_id
        LEFT JOIN target_products tp ON tp.product_id = cp.product_id
        WHERE tp.product_id IS NULL
        GROUP BY cp.product_id
    )
    SELECT s.product_id,
           COALESCE(t.product_category_name_english, p.product_category_name, 'Uncategorized') AS category,
           s.similar_customer_count,
           s.score
    FROM scored s
    JOIN olist_products p ON p.product_id = s.product_id
    LEFT JOIN product_category_name_translation t
      ON t.product_category_name = p.product_category_name
    ORDER BY s.score DESC, s.similar_customer_count DESC, s.product_id
    LIMIT :limit
""")


POPULAR_SQL = text("""
    SELECT oi.product_id,
           COALESCE(t.product_category_name_english, p.product_category_name, 'Uncategorized') AS category,
           COUNT(DISTINCT o.order_id)::integer AS order_count
    FROM olist_order_items oi
    JOIN olist_orders o ON o.order_id = oi.order_id
    JOIN olist_products p ON p.product_id = oi.product_id
    LEFT JOIN product_category_name_translation t
      ON t.product_category_name = p.product_category_name
    WHERE o.order_status = 'delivered'
      AND NOT EXISTS (
          SELECT 1 FROM olist_customers c
          JOIN olist_orders own_o ON own_o.customer_id = c.customer_id
          JOIN olist_order_items own_i ON own_i.order_id = own_o.order_id
          WHERE c.customer_unique_id = :customer_id
            AND own_o.order_status = 'delivered'
            AND own_i.product_id = oi.product_id
      )
    GROUP BY oi.product_id, category
    ORDER BY order_count DESC, oi.product_id
    LIMIT :limit
""")


LEGACY_CUSTOMERS_SQL = text("""
    SELECT CAST(c.customer_id AS TEXT) AS customer_id,
           COUNT(DISTINCT o.invoice_no) AS order_count,
           MAX(o.invoice_date) AS last_order
    FROM customers c JOIN orders o ON o.customer_id = c.customer_id
    WHERE (:search = '' OR LOWER(CAST(c.customer_id AS TEXT)) LIKE '%' || LOWER(:search) || '%')
    GROUP BY c.customer_id
    ORDER BY order_count DESC, last_order DESC, customer_id
    LIMIT :limit
""")

LEGACY_TARGET_PRODUCTS_SQL = text("""
    SELECT oi.stock_code AS product_id, p.description AS category,
           COUNT(DISTINCT o.invoice_no) AS order_count,
           SUM(oi.line_total) * 1.0 AS spend
    FROM customers c
    JOIN orders o ON o.customer_id = c.customer_id
    JOIN order_items oi ON oi.invoice_no = o.invoice_no
    JOIN products p ON p.stock_code = oi.stock_code
    WHERE c.customer_id = :customer_id AND o.is_cancellation = FALSE
    GROUP BY oi.stock_code, p.description
    ORDER BY order_count DESC, spend DESC
""")

LEGACY_COLLABORATIVE_SQL = text("""
    WITH customer_products AS (
        SELECT DISTINCT c.customer_id, oi.stock_code AS product_id
        FROM customers c JOIN orders o ON o.customer_id = c.customer_id
        JOIN order_items oi ON oi.invoice_no = o.invoice_no
        WHERE o.is_cancellation = FALSE
    ),
    target_products AS (
        SELECT DISTINCT oi.stock_code AS product_id
        FROM orders o JOIN order_items oi ON oi.invoice_no = o.invoice_no
        WHERE o.customer_id = :customer_id AND o.is_cancellation = FALSE
    ),
    target_size AS (SELECT COUNT(*) * 1.0 AS n FROM target_products),
    neighbors AS (
        SELECT cp.customer_id,
               COUNT(*) FILTER (WHERE tp.product_id IS NOT NULL) * 1.0 AS shared,
               COUNT(*) FILTER (WHERE tp.product_id IS NOT NULL) * 1.0
                   / NULLIF((SELECT n FROM target_size) + COUNT(*)
                       - COUNT(*) FILTER (WHERE tp.product_id IS NOT NULL), 0) AS similarity
        FROM customer_products cp LEFT JOIN target_products tp ON tp.product_id = cp.product_id
        WHERE cp.customer_id <> :customer_id
        GROUP BY cp.customer_id
        HAVING COUNT(*) FILTER (WHERE tp.product_id IS NOT NULL) > 0
        ORDER BY similarity DESC, shared DESC
        LIMIT 100
    ),
    scored AS (
        SELECT cp.product_id, COUNT(DISTINCT n.customer_id) AS similar_customer_count,
               SUM(n.similarity) * 1.0 AS score
        FROM neighbors n JOIN customer_products cp ON cp.customer_id = n.customer_id
        LEFT JOIN target_products tp ON tp.product_id = cp.product_id
        WHERE tp.product_id IS NULL
        GROUP BY cp.product_id
    )
    SELECT s.product_id, p.description AS category, s.similar_customer_count, s.score
    FROM scored s JOIN products p ON p.stock_code = s.product_id
    ORDER BY s.score DESC, s.similar_customer_count DESC, s.product_id
    LIMIT :limit
""")

LEGACY_POPULAR_SQL = text("""
    SELECT oi.stock_code AS product_id, p.description AS category,
           COUNT(DISTINCT o.invoice_no) AS order_count
    FROM order_items oi JOIN orders o ON o.invoice_no = oi.invoice_no
    JOIN products p ON p.stock_code = oi.stock_code
    WHERE o.is_cancellation = FALSE
      AND NOT EXISTS (
          SELECT 1 FROM orders own_o JOIN order_items own_i ON own_i.invoice_no = own_o.invoice_no
          WHERE own_o.customer_id = :customer_id AND own_o.is_cancellation = FALSE
            AND own_i.stock_code = oi.stock_code
      )
    GROUP BY oi.stock_code, p.description
    ORDER BY order_count DESC, oi.stock_code
    LIMIT :limit
""")


def list_customers(db: Session, source: str, search: str = "", limit: int = 25) -> list[dict]:
    statement = CUSTOMERS_SQL if source == "olist" else LEGACY_CUSTOMERS_SQL
    return [dict(row) for row in db.execute(statement, {"search": search, "limit": limit}).mappings()]


def recommend_for_customer(db: Session, source: str, customer_id: str, limit: int = 12) -> dict:
    params = {"customer_id": customer_id if source == "olist" else int(customer_id)}
    target_sql = TARGET_PRODUCTS_SQL if source == "olist" else LEGACY_TARGET_PRODUCTS_SQL
    similar_sql = COLLABORATIVE_SQL if source == "olist" else LEGACY_COLLABORATIVE_SQL
    popular_sql = POPULAR_SQL if source == "olist" else LEGACY_POPULAR_SQL
    history = [dict(row) for row in db.execute(target_sql, params).mappings()]
    if not history:
        return {"customer_id": customer_id, "history": [], "recommendations": [], "method": "none"}

    rows = [dict(row) for row in db.execute(similar_sql, params | {"limit": limit}).mappings()]
    method = "similar_customers"
    if not rows:
        rows = [dict(row) for row in db.execute(popular_sql, params | {"limit": limit}).mappings()]
        rows = [row | {"similar_customer_count": 0, "score": None} for row in rows]
        method = "popular_fallback"

    recommendations = []
    for row in rows:
        if row.get("score") is not None:
            reason = f"Purchased by {row['similar_customer_count']} similar customers"
        else:
            reason = f"Popular among delivered orders ({row['order_count']} orders)"
        recommendations.append({
            "product_id": row["product_id"],
            "category": row["category"],
            "similar_customer_count": row["similar_customer_count"],
            "score": round(row["score"], 4) if row.get("score") is not None else None,
            "reason": reason,
        })
    return {"customer_id": customer_id, "history": history[:20], "recommendations": recommendations, "method": method}
