"""Canonical operational data, normalised from connected systems (CLAUDE.md §5, plan §3.3).

Every row belongs to one organisation and one connection, and records the source system's id
(`external_id`) so values trace back to their source and re-syncs are idempotent upserts.
Quantities and money are NUMERIC, never floats.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from operon.core.db import Base, IdMixin

QTY = Numeric(18, 4)
MONEY = Numeric(18, 4)


def _source(table: str) -> tuple[object, ...]:
    """Tenant + source-record constraints shared by every synced table."""
    return (
        ForeignKeyConstraint(
            ["organisation_id", "connection_id"],
            ["integration_connections.organisation_id", "integration_connections.id"],
            ondelete="CASCADE",
            name=f"fk_{table}_connection_same_org",
        ),
        UniqueConstraint("organisation_id", "id", name=f"uq_{table}_org_id"),
    )


class SourcedMixin(IdMixin):
    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    connection_id: Mapped[UUID] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Location(SourcedMixin, Base):
    __tablename__ = "locations"
    __table_args__ = (*_source("locations"), UniqueConstraint("connection_id", "external_id"))

    external_id: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str | None] = mapped_column(String(50))


class Supplier(SourcedMixin, Base):
    __tablename__ = "suppliers"
    __table_args__ = (*_source("suppliers"), UniqueConstraint("connection_id", "external_id"))

    external_id: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    active: Mapped[bool] = mapped_column(default=True)


class Product(SourcedMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        *_source("products"),
        UniqueConstraint("connection_id", "external_id"),
        Index("ix_products_org_sku", "organisation_id", "sku"),
    )

    external_id: Mapped[str] = mapped_column(String(100))
    sku: Mapped[str | None] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(300))
    uom: Mapped[str | None] = mapped_column(String(40))
    unit_cost: Mapped[Decimal | None] = mapped_column(MONEY)
    currency: Mapped[str | None] = mapped_column(String(3))
    active: Mapped[bool] = mapped_column(default=True)


class SupplierProduct(SourcedMixin, Base):
    """Supplier terms for a product: lead time, minimum order, price."""

    __tablename__ = "supplier_products"
    __table_args__ = (
        *_source("supplier_products"),
        UniqueConstraint("connection_id", "external_id"),
        ForeignKeyConstraint(
            ["organisation_id", "supplier_id"],
            ["suppliers.organisation_id", "suppliers.id"],
            ondelete="CASCADE",
            name="fk_supplier_products_supplier_same_org",
        ),
        ForeignKeyConstraint(
            ["organisation_id", "product_id"],
            ["products.organisation_id", "products.id"],
            ondelete="CASCADE",
            name="fk_supplier_products_product_same_org",
        ),
    )

    external_id: Mapped[str] = mapped_column(String(100))
    supplier_id: Mapped[UUID] = mapped_column()
    product_id: Mapped[UUID] = mapped_column()
    lead_time_days: Mapped[int | None] = mapped_column()
    min_quantity: Mapped[Decimal | None] = mapped_column(QTY)
    price: Mapped[Decimal | None] = mapped_column(MONEY)
    currency: Mapped[str | None] = mapped_column(String(3))


class StockLevel(SourcedMixin, Base):
    __tablename__ = "stock_levels"
    __table_args__ = (
        *_source("stock_levels"),
        UniqueConstraint("connection_id", "product_id", "location_id"),
        ForeignKeyConstraint(
            ["organisation_id", "product_id"],
            ["products.organisation_id", "products.id"],
            ondelete="CASCADE",
            name="fk_stock_levels_product_same_org",
        ),
        ForeignKeyConstraint(
            ["organisation_id", "location_id"],
            ["locations.organisation_id", "locations.id"],
            ondelete="CASCADE",
            name="fk_stock_levels_location_same_org",
        ),
    )

    product_id: Mapped[UUID] = mapped_column()
    location_id: Mapped[UUID] = mapped_column()
    on_hand: Mapped[Decimal] = mapped_column(QTY)
    reserved: Mapped[Decimal] = mapped_column(QTY, default=Decimal(0))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SalesDaily(SourcedMixin, Base):
    """Units sold per product, location (if known) and day."""

    __tablename__ = "sales_daily"
    __table_args__ = (
        *_source("sales_daily"),
        UniqueConstraint("connection_id", "product_id", "location_key", "day"),
        ForeignKeyConstraint(
            ["organisation_id", "product_id"],
            ["products.organisation_id", "products.id"],
            ondelete="CASCADE",
            name="fk_sales_daily_product_same_org",
        ),
        ForeignKeyConstraint(
            ["organisation_id", "location_id"],
            ["locations.organisation_id", "locations.id"],
            ondelete="CASCADE",
            name="fk_sales_daily_location_same_org",
        ),
        CheckConstraint("quantity >= 0", name="quantity_non_negative"),
        Index("ix_sales_daily_org_day", "organisation_id", "day"),
    )

    product_id: Mapped[UUID] = mapped_column()
    location_id: Mapped[UUID | None] = mapped_column()
    # location_id or "" — lets the unique constraint treat "no location" as one bucket.
    location_key: Mapped[str] = mapped_column(String(40), default="")
    day: Mapped[date] = mapped_column(Date)
    quantity: Mapped[Decimal] = mapped_column(QTY)


class PurchaseOrder(SourcedMixin, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        *_source("purchase_orders"),
        UniqueConstraint("connection_id", "external_id"),
        ForeignKeyConstraint(
            ["organisation_id", "supplier_id"],
            ["suppliers.organisation_id", "suppliers.id"],
            name="fk_purchase_orders_supplier_same_org",
        ),
        ForeignKeyConstraint(
            ["organisation_id", "location_id"],
            ["locations.organisation_id", "locations.id"],
            name="fk_purchase_orders_location_same_org",
        ),
        CheckConstraint(
            "status IN ('draft', 'open', 'received', 'cancelled')", name="status_valid"
        ),
    )

    external_id: Mapped[str] = mapped_column(String(100))
    number: Mapped[str] = mapped_column(String(100))
    supplier_id: Mapped[UUID | None] = mapped_column()
    location_id: Mapped[UUID | None] = mapped_column()
    status: Mapped[str] = mapped_column(String(20))
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    currency: Mapped[str | None] = mapped_column(String(3))
    total: Mapped[Decimal | None] = mapped_column(MONEY)


class PurchaseOrderLine(SourcedMixin, Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        *_source("purchase_order_lines"),
        UniqueConstraint("connection_id", "external_id"),
        ForeignKeyConstraint(
            ["organisation_id", "purchase_order_id"],
            ["purchase_orders.organisation_id", "purchase_orders.id"],
            ondelete="CASCADE",
            name="fk_purchase_order_lines_po_same_org",
        ),
        ForeignKeyConstraint(
            ["organisation_id", "product_id"],
            ["products.organisation_id", "products.id"],
            name="fk_purchase_order_lines_product_same_org",
        ),
    )

    external_id: Mapped[str] = mapped_column(String(100))
    purchase_order_id: Mapped[UUID] = mapped_column()
    product_id: Mapped[UUID | None] = mapped_column()
    quantity: Mapped[Decimal] = mapped_column(QTY)
    received_quantity: Mapped[Decimal] = mapped_column(QTY, default=Decimal(0))
    unit_price: Mapped[Decimal | None] = mapped_column(MONEY)
    expected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
