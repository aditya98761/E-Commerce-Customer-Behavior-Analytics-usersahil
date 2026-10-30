import os
import uuid
from datetime import datetime
from typing import Optional

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from pydantic import ValidationError
from sqlalchemy import String, cast, func, inspect, select, text
from sqlalchemy.orm import Session

from . import models as m
from .config import settings
from .database import SessionLocal, get_db
from .schemas import PARAM_MODELS, RunRequest
from .services import recommendations as recommendation_service
from .services.runner import execute_import, execute_run
from .services.spark_jobs import resolve_rfm_engine

router = APIRouter(prefix="/api")
NOT_CANC = m.Order.is_cancellation.is_(False)


def _page(total, items, page, size):
    return {"total": total, "page": page, "page_size": size, "items": items}


def latest_run(db: Session, run_type: str) -> Optional[m.AnalyticsRun]:
    return db.scalars(select(m.AnalyticsRun).where(m.AnalyticsRun.run_type == run_type, m.AnalyticsRun.status == "completed")
                      .order_by(m.AnalyticsRun.id.desc()).limit(1)).first()


def run_dict(r: m.AnalyticsRun, full=False):
    d = dict(id=r.id, run_type=r.run_type, status=r.status, params=r.params, error=r.error, created_at=r.created_at,
             started_at=r.started_at, finished_at=r.finished_at,
             duration_s=round((r.finished_at - r.started_at).total_seconds(), 2) if r.finished_at and r.started_at else None)
    if full:
        d["result"] = r.result
    return d


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "time": datetime.utcnow()}


def analytics_schema_ready(db: Session, source: Optional[str] = None) -> bool:
    source = source or recommendation_service.recommendation_source(db)
    inspector = inspect(db.get_bind())
    needed = ({"customers", "products", "orders", "order_items", "analytics_runs", "customer_segments",
               "association_rules", "forecasts", "analytics_customer_map"} if source == "olist" else
              {"customers", "products", "orders", "order_items", "analytics_runs", "customer_segments",
               "association_rules", "forecasts"})
    return source is not None and all(inspector.has_table(table) for table in needed)


def require_analytics_schema(db: Session):
    source = recommendation_service.recommendation_source(db)
    if not analytics_schema_ready(db, source):
        raise HTTPException(409, "Analytics tables are not ready. For Olist, run Databas_Olist/03_enable_project_analytics.sql after importing all nine CSV files.")
    return source


def dataset_currency(db: Session) -> str:
    return "BRL" if recommendation_service.recommendation_source(db) == "olist" else "GBP"


@router.get("/data-source")
def data_source(db: Session = Depends(get_db)):
    source = recommendation_service.recommendation_source(db)
    if source == "olist":
        totals = db.execute(text("""
            SELECT (SELECT COUNT(DISTINCT customer_unique_id) FROM olist_customers) AS customers,
                   (SELECT COUNT(*) FROM olist_orders) AS orders,
                   (SELECT COUNT(*) FROM olist_products) AS products,
                   (SELECT MIN(order_purchase_timestamp) FROM olist_orders) AS date_min,
                   (SELECT MAX(order_purchase_timestamp) FROM olist_orders) AS date_max
        """)).mappings().one()
        return {"source": source, "label": "Brazilian E-Commerce (Olist)", "currency": "BRL",
                "analytics_ready": analytics_schema_ready(db, source), "has_data": totals["orders"] > 0,
                **dict(totals)}
    if source == "legacy":
        customers_n = db.scalar(select(func.count()).select_from(m.Customer)) or 0
        orders_n = db.scalar(select(func.count()).select_from(m.Order)) or 0
        products_n = db.scalar(select(func.count()).select_from(m.Product)) or 0
        date_min, date_max = db.execute(select(func.min(m.Order.invoice_date), func.max(m.Order.invoice_date))).one()
        return {"source": "uci", "label": "UCI Online Retail", "currency": "GBP",
                "analytics_ready": analytics_schema_ready(db, source), "has_data": orders_n > 0,
                "customers": customers_n, "orders": orders_n, "products": products_n,
                "date_min": date_min, "date_max": date_max}
    return {"source": "unknown", "label": "Unrecognized database schema", "currency": "GBP",
            "analytics_ready": False, "has_data": False, "customers": 0, "orders": 0, "products": 0,
            "date_min": None, "date_max": None}


# ---------- Dashboard ----------
@router.get("/dashboard/summary")
def summary(db: Session = Depends(get_db)):
    require_analytics_schema(db)
    rev, items = db.execute(select(func.coalesce(func.sum(m.Order.total_amount), 0), func.count(m.Order.invoice_no))
                            .where(NOT_CANC)).one()
    canc_val, canc_n = db.execute(select(func.coalesce(func.sum(m.Order.total_amount), 0), func.count(m.Order.invoice_no))
                                  .where(m.Order.is_cancellation.is_(True))).one()
    custs = db.scalar(select(func.count(m.Customer.customer_id))) or 0
    repeat = db.scalar(select(func.count()).select_from(m.Customer).where(m.Customer.order_count >= 2)) or 0
    buyers = db.scalar(select(func.count()).select_from(m.Customer).where(m.Customer.order_count >= 1)) or 0
    dmin, dmax = db.execute(select(func.min(m.Order.invoice_date), func.max(m.Order.invoice_date))).one()
    return {"has_data": items > 0, "currency": dataset_currency(db), "revenue": round(rev, 2), "orders": items,
            "avg_order_value": round(rev / items, 2) if items else 0, "customers": custs,
            "repeat_purchase_rate": round(repeat / buyers, 4) if buyers else 0,
            "cancelled_value": round(abs(canc_val), 2), "cancelled_orders": canc_n,
            "date_min": dmin, "date_max": dmax}


@router.get("/dashboard/trends")
def trends(granularity: str = Query("month", pattern="^(day|week|month)$"),
           date_from: Optional[datetime] = None, date_to: Optional[datetime] = None, db: Session = Depends(get_db)):
    require_analytics_schema(db)
    q = select(func.date(m.Order.invoice_date).label("d"), func.sum(m.Order.total_amount).label("revenue"),
               func.count(m.Order.invoice_no).label("orders")).where(NOT_CANC).group_by("d").order_by("d")
    if date_from:
        q = q.where(m.Order.invoice_date >= date_from)
    if date_to:
        q = q.where(m.Order.invoice_date <= date_to)
    df = pd.DataFrame(db.execute(q).all(), columns=["date", "revenue", "orders"])
    if df.empty:
        return []
    df["date"] = pd.to_datetime(df["date"])
    if granularity != "day":
        df = df.set_index("date").resample("MS" if granularity == "month" else "W").sum().reset_index()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df["revenue"] = df["revenue"].round(2)
    return df.to_dict("records")


@router.get("/dashboard/top-products")
def top_products(limit: int = Query(10, ge=1, le=50), by: str = Query("revenue", pattern="^(revenue|quantity)$"),
                 db: Session = Depends(get_db)):
    require_analytics_schema(db)
    val = func.sum(m.OrderItem.line_total if by == "revenue" else m.OrderItem.quantity)
    q = (select(m.Product.stock_code, m.Product.description, func.sum(m.OrderItem.line_total).label("revenue"),
                func.sum(m.OrderItem.quantity).label("quantity"))
         .join(m.OrderItem, m.OrderItem.stock_code == m.Product.stock_code).join(m.Order, m.Order.invoice_no == m.OrderItem.invoice_no)
         .where(NOT_CANC).group_by(m.Product.stock_code, m.Product.description).order_by(val.desc()).limit(limit))
    return [dict(stock_code=a, description=b, revenue=round(c, 2), quantity=int(d)) for a, b, c, d in db.execute(q)]


@router.get("/dashboard/countries")
def countries(limit: int = Query(15, ge=1, le=60), db: Session = Depends(get_db)):
    require_analytics_schema(db)
    q = (select(m.Order.country, func.sum(m.Order.total_amount).label("revenue"), func.count(m.Order.invoice_no).label("orders"))
         .where(NOT_CANC).group_by(m.Order.country).order_by(func.sum(m.Order.total_amount).desc()).limit(limit))
    return [dict(country=a, revenue=round(b, 2), orders=c) for a, b, c in db.execute(q)]


# ---------- Customers ----------
@router.get("/customers")
def customers(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200), search: Optional[str] = None,
              segment: Optional[str] = None, country: Optional[str] = None,
              sort: str = Query("total_spent", pattern="^(total_spent|order_count|customer_id|recency|frequency|monetary)$"),
              desc: bool = True, db: Session = Depends(get_db)):
    require_analytics_schema(db)
    run = latest_run(db, "rfm")
    S = m.CustomerSegment
    q = select(m.Customer, S.recency, S.frequency, S.monetary, S.r_score, S.f_score, S.m_score, S.segment)
    q = q.outerjoin(S, (S.customer_id == m.Customer.customer_id) & (S.run_id == (run.id if run else -1)))
    if search:
        q = q.where(cast(m.Customer.customer_id, String).like(f"%{search}%"))
    if segment:
        q = q.where(S.segment == segment)
    if country:
        q = q.where(m.Customer.country == country)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    col = {"recency": S.recency, "frequency": S.frequency, "monetary": S.monetary}.get(sort, getattr(m.Customer, sort, None))
    q = q.order_by(col.desc() if desc else col.asc()).offset((page - 1) * page_size).limit(page_size)
    items = [dict(customer_id=c.customer_id, country=c.country, order_count=c.order_count, total_spent=c.total_spent,
                  last_order_date=c.last_order_date, recency=r, frequency=f, monetary=mo, r_score=rs, f_score=fs, m_score=ms, segment=sg)
             for c, r, f, mo, rs, fs, ms, sg in db.execute(q)]
    return _page(total, items, page, page_size) | {"rfm_run_id": run.id if run else None, "currency": dataset_currency(db)}


@router.get("/rfm/summary")
def rfm_summary(db: Session = Depends(get_db)):
    require_analytics_schema(db)
    run = latest_run(db, "rfm")
    return {"run": run_dict(run, True) if run else None, "currency": dataset_currency(db)}


@router.get("/clusters/latest")
def clusters_latest(db: Session = Depends(get_db)):
    require_analytics_schema(db)
    run = latest_run(db, "clustering")
    return {"run": run_dict(run, True) if run else None, "currency": dataset_currency(db)}


@router.get("/association-rules")
def rules(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200), search: Optional[str] = None,
          min_lift: float = 0, sort: str = Query("lift", pattern="^(lift|confidence|support)$"), db: Session = Depends(get_db)):
    require_analytics_schema(db)
    run = latest_run(db, "basket")
    if not run:
        return _page(0, [], page, page_size) | {"run": None}
    R = m.AssociationRule
    q = select(R).where(R.run_id == run.id, R.lift >= min_lift)
    rows = db.scalars(q.order_by(getattr(R, sort).desc())).all()
    if search:
        s = search.lower()
        rows = [r for r in rows if s in " ".join(r.antecedents + r.consequents).lower()]
    items = [dict(id=r.id, antecedents=r.antecedents, consequents=r.consequents, support=r.support, confidence=r.confidence, lift=r.lift)
             for r in rows[(page - 1) * page_size: page * page_size]]
    return _page(len(rows), items, page, page_size) | {"run": run_dict(run, True)}


@router.get("/forecast/latest")
def forecast_latest(db: Session = Depends(get_db)):
    require_analytics_schema(db)
    run = latest_run(db, "forecast")
    if not run:
        return {"run": None, "series": [], "currency": dataset_currency(db)}
    rows = db.scalars(select(m.Forecast).where(m.Forecast.run_id == run.id).order_by(m.Forecast.date)).all()
    series = [dict(date=r.date.strftime("%Y-%m-%d"), actual=r.actual, predicted=r.predicted, baseline=r.baseline, phase=r.phase) for r in rows]
    return {"run": run_dict(run, True), "series": series, "currency": dataset_currency(db)}


# ---------- Personalized recommendations ----------
def require_recommendation_schema(db: Session) -> str:
    source = recommendation_service.recommendation_source(db)
    if source is None:
        raise HTTPException(409, "Recommendation tables are not available. Point backend/.env at a database with either the project tables or the loaded Olist tables.")
    return source


@router.get("/recommendations/customers")
def recommendation_customers(search: str = Query("", max_length=100), limit: int = Query(25, ge=1, le=100),
                             db: Session = Depends(get_db)):
    source = require_recommendation_schema(db)
    return recommendation_service.list_customers(db, source, search.strip(), limit)


@router.get("/recommendations/{customer_id}")
def customer_recommendations(customer_id: str, limit: int = Query(12, ge=1, le=50), db: Session = Depends(get_db)):
    source = require_recommendation_schema(db)
    if source == "legacy" and not customer_id.isdigit():
        raise HTTPException(422, "Customer ID must be numeric for this database.")
    result = recommendation_service.recommend_for_customer(db, source, customer_id, limit)
    if result["method"] == "none":
        raise HTTPException(404, "No delivered purchase history found for this customer.")
    return result


# ---------- Runs / import ----------
@router.post("/runs", status_code=202)
def create_run(req: RunRequest, bg: BackgroundTasks, db: Session = Depends(get_db)):
    source = require_analytics_schema(db)
    try:
        params = PARAM_MODELS[req.run_type](**req.params).model_dump()
    except ValidationError as e:
        raise HTTPException(422, detail=e.errors(include_url=False, include_context=False))
    if req.run_type == "rfm":
        try:
            params["engine"] = resolve_rfm_engine(params["engine"], source)
            if params["engine"] == "spark" and db.get_bind().dialect.name != "postgresql":
                raise ValueError("Spark JDBC requires PostgreSQL.")
        except ValueError as e:
            raise HTTPException(422, detail=str(e))
    run = m.AnalyticsRun(run_type=req.run_type, params=params, status="pending")
    db.add(run)
    db.commit()
    bg.add_task(execute_run, SessionLocal, run.id)
    return run_dict(run)


@router.get("/runs")
def list_runs(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), run_type: Optional[str] = None,
              status: Optional[str] = None, db: Session = Depends(get_db)):
    require_analytics_schema(db)
    q = select(m.AnalyticsRun)
    if run_type:
        q = q.where(m.AnalyticsRun.run_type == run_type)
    if status:
        q = q.where(m.AnalyticsRun.status == status)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(m.AnalyticsRun.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return _page(total, [run_dict(r) for r in rows], page, page_size)


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    require_analytics_schema(db)
    run = db.get(m.AnalyticsRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run_dict(run, True)


@router.post("/import", status_code=202)
async def import_file(bg: BackgroundTasks, file: UploadFile = File(...), db: Session = Depends(get_db)):
    source = recommendation_service.recommendation_source(db)
    if source == "olist":
        raise HTTPException(409, "Import Olist files into their matching PostgreSQL tables with pgAdmin. The UCI workbook importer cannot load Olist files.")
    require_analytics_schema(db)
    name = file.filename or "upload"
    if not name.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(400, "Only .csv, .xlsx or .xls files are accepted.")
    os.makedirs(settings.upload_dir, exist_ok=True)
    path = os.path.join(settings.upload_dir, f"{uuid.uuid4().hex}_{os.path.basename(name)}")
    size = 0
    with open(path, "wb") as fh:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > settings.max_upload_mb * 1024 * 1024:
                fh.close()
                os.remove(path)
                raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB limit.")
            fh.write(chunk)
    run = m.AnalyticsRun(run_type="import", params={"filename": name, "bytes": size}, status="pending")
    db.add(run)
    db.commit()
    bg.add_task(execute_import, SessionLocal, run.id, path, name)
    return run_dict(run)


@router.get("/import/latest")
def import_latest(db: Session = Depends(get_db)):
    source = recommendation_service.recommendation_source(db)
    if source == "olist":
        return {"run": None, "source": source}
    require_analytics_schema(db)
    run = db.scalars(select(m.AnalyticsRun).where(m.AnalyticsRun.run_type == "import").order_by(m.AnalyticsRun.id.desc()).limit(1)).first()
    return {"run": run_dict(run, True) if run else None}
