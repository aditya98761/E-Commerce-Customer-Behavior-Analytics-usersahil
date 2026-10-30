from datetime import datetime

from sqlalchemy import (JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index,
                        Integer, String, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Customer(Base):
    __tablename__ = "customers"
    customer_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    country: Mapped[str] = mapped_column(String(80), index=True)
    first_order_date: Mapped[datetime] = mapped_column(DateTime)
    last_order_date: Mapped[datetime] = mapped_column(DateTime)
    order_count: Mapped[int] = mapped_column(Integer, default=0)
    total_spent: Mapped[float] = mapped_column(Float, default=0.0)  # GBP, non-cancelled orders only


class Product(Base):
    __tablename__ = "products"
    stock_code: Mapped[str] = mapped_column(String(40), primary_key=True)
    description: Mapped[str] = mapped_column(String(255))


class Order(Base):
    __tablename__ = "orders"
    invoice_no: Mapped[str] = mapped_column(String(20), primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.customer_id"), index=True, nullable=True)
    invoice_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    country: Mapped[str] = mapped_column(String(80), index=True)
    is_cancellation: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("unit_price > 0", name="ck_item_price_positive"),
                      Index("ix_items_invoice_stock", "invoice_no", "stock_code"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_no: Mapped[str] = mapped_column(ForeignKey("orders.invoice_no"), index=True)
    stock_code: Mapped[str] = mapped_column(ForeignKey("products.stock_code"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)  # negative for cancellations
    unit_price: Mapped[float] = mapped_column(Float)
    line_total: Mapped[float] = mapped_column(Float)
    order: Mapped[Order] = relationship(back_populates="items")


class AnalyticsRun(Base):
    __tablename__ = "analytics_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_type: Mapped[str] = mapped_column(String(30), index=True)  # import|rfm|clustering|basket|forecast
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CustomerSegment(Base):
    __tablename__ = "customer_segments"
    __table_args__ = (UniqueConstraint("run_id", "customer_id", name="uq_segment_run_customer"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analytics_runs.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    recency: Mapped[int] = mapped_column(Integer)
    frequency: Mapped[int] = mapped_column(Integer)
    monetary: Mapped[float] = mapped_column(Float)
    r_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    f_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    m_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    segment: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)  # RFM segment
    cluster: Mapped[int | None] = mapped_column(Integer, nullable=True)  # K-Means cluster


class AssociationRule(Base):
    __tablename__ = "association_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analytics_runs.id", ondelete="CASCADE"), index=True)
    antecedents: Mapped[list] = mapped_column(JSON)
    consequents: Mapped[list] = mapped_column(JSON)
    support: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    lift: Mapped[float] = mapped_column(Float, index=True)


class Forecast(Base):
    __tablename__ = "forecasts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analytics_runs.id", ondelete="CASCADE"), index=True)
    date: Mapped[datetime] = mapped_column(DateTime)
    actual: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline: Mapped[float | None] = mapped_column(Float, nullable=True)
    phase: Mapped[str] = mapped_column(String(10))  # train | test | future
