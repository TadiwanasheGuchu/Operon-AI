"""Integrations (connections, credentials, sync jobs, events) and canonical operational data.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-13 12:11:13.250740
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "integration_connections",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("connector", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sync_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "connector IN ('odoo', 'shopify', 'csv')",
            name=op.f("ck_integration_connections_connector_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'syncing', 'degraded', 'action_required', 'paused')",
            name=op.f("ck_integration_connections_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_integration_connections_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_integration_connections_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_connections")),
        sa.UniqueConstraint("organisation_id", "id", name="uq_integration_connections_org_id"),
        sa.UniqueConstraint("public_id", name=op.f("uq_integration_connections_public_id")),
    )
    op.create_index(
        "ix_integration_connections_org",
        "integration_connections",
        ["organisation_id"],
        unique=False,
    )
    op.create_table(
        "integration_credentials",
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id", "connection_id"],
            ["integration_connections.organisation_id", "integration_connections.id"],
            name="fk_integration_credentials_connection_same_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_integration_credentials_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("connection_id", name=op.f("pk_integration_credentials")),
    )
    op.create_table(
        "integration_events",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("source_event_id", sa.String(length=200), nullable=False),
        sa.Column("topic", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'processed', 'ignored')",
            name=op.f("ck_integration_events_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id", "connection_id"],
            ["integration_connections.organisation_id", "integration_connections.id"],
            name="fk_integration_events_connection_same_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_integration_events_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_events")),
        sa.UniqueConstraint(
            "connection_id",
            "source_event_id",
            name=op.f("uq_integration_events_connection_id_source_event_id"),
        ),
    )
    op.create_index(
        "ix_integration_events_connection",
        "integration_events",
        ["connection_id", "received_at"],
        unique=False,
    )
    op.create_table(
        "integration_sync_jobs",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("workflow_id", sa.String(length=200), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name=op.f("ck_integration_sync_jobs_status_valid"),
        ),
        sa.CheckConstraint(
            "trigger IN ('initial', 'schedule', 'manual', 'webhook', 'upload')",
            name=op.f("ck_integration_sync_jobs_trigger_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id", "connection_id"],
            ["integration_connections.organisation_id", "integration_connections.id"],
            name="fk_integration_sync_jobs_connection_same_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_integration_sync_jobs_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_sync_jobs")),
    )
    op.create_index(
        "ix_integration_sync_jobs_connection",
        "integration_sync_jobs",
        ["connection_id", "started_at"],
        unique=False,
    )
    op.create_table(
        "locations",
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=True),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organisation_id", "connection_id"],
            ["integration_connections.organisation_id", "integration_connections.id"],
            name="fk_locations_connection_same_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_locations_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_locations")),
        sa.UniqueConstraint(
            "connection_id", "external_id", name=op.f("uq_locations_connection_id_external_id")
        ),
        sa.UniqueConstraint("organisation_id", "id", name="uq_locations_org_id"),
    )
    op.create_table(
        "products",
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("uom", sa.String(length=40), nullable=True),
        sa.Column("unit_cost", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organisation_id", "connection_id"],
            ["integration_connections.organisation_id", "integration_connections.id"],
            name="fk_products_connection_same_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_products_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint(
            "connection_id", "external_id", name=op.f("uq_products_connection_id_external_id")
        ),
        sa.UniqueConstraint("organisation_id", "id", name="uq_products_org_id"),
    )
    op.create_index("ix_products_org_sku", "products", ["organisation_id", "sku"], unique=False)
    op.create_table(
        "suppliers",
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organisation_id", "connection_id"],
            ["integration_connections.organisation_id", "integration_connections.id"],
            name="fk_suppliers_connection_same_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_suppliers_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suppliers")),
        sa.UniqueConstraint(
            "connection_id", "external_id", name=op.f("uq_suppliers_connection_id_external_id")
        ),
        sa.UniqueConstraint("organisation_id", "id", name="uq_suppliers_org_id"),
    )
    op.create_table(
        "purchase_orders",
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("number", sa.String(length=100), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=True),
        sa.Column("location_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("total", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'open', 'received', 'cancelled')",
            name=op.f("ck_purchase_orders_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id", "connection_id"],
            ["integration_connections.organisation_id", "integration_connections.id"],
            name="fk_purchase_orders_connection_same_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id", "location_id"],
            ["locations.organisation_id", "locations.id"],
            name="fk_purchase_orders_location_same_org",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id", "supplier_id"],
            ["suppliers.organisation_id", "suppliers.id"],
            name="fk_purchase_orders_supplier_same_org",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_purchase_orders_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_orders")),
        sa.UniqueConstraint(
            "connection_id",
            "external_id",
            name=op.f("uq_purchase_orders_connection_id_external_id"),
        ),
        sa.UniqueConstraint("organisation_id", "id", name="uq_purchase_orders_org_id"),
    )
    op.create_table(
        "sales_daily",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=True),
        sa.Column("location_key", sa.String(length=40), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("quantity >= 0", name=op.f("ck_sales_daily_quantity_non_negative")),
        sa.ForeignKeyConstraint(
            ["organisation_id", "connection_id"],
            ["integration_connections.organisation_id", "integration_connections.id"],
            name="fk_sales_daily_connection_same_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id", "location_id"],
            ["locations.organisation_id", "locations.id"],
            name="fk_sales_daily_location_same_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id", "product_id"],
            ["products.organisation_id", "products.id"],
            name="fk_sales_daily_product_same_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_sales_daily_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sales_daily")),
        sa.UniqueConstraint(
            "connection_id",
            "product_id",
            "location_key",
            "day",
            name=op.f("uq_sales_daily_connection_id_product_id_location_key_day"),
        ),
        sa.UniqueConstraint("organisation_id", "id", name="uq_sales_daily_org_id"),
    )
    op.create_index(
        "ix_sales_daily_org_day", "sales_daily", ["organisation_id", "day"], unique=False
    )
    op.create_table(
        "stock_levels",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("on_hand", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("reserved", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organisation_id", "connection_id"],
            ["integration_connections.organisation_id", "integration_connections.id"],
            name="fk_stock_levels_connection_same_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id", "location_id"],
            ["locations.organisation_id", "locations.id"],
            name="fk_stock_levels_location_same_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id", "product_id"],
            ["products.organisation_id", "products.id"],
            name="fk_stock_levels_product_same_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_stock_levels_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_levels")),
        sa.UniqueConstraint(
            "connection_id",
            "product_id",
            "location_id",
            name=op.f("uq_stock_levels_connection_id_product_id_location_id"),
        ),
        sa.UniqueConstraint("organisation_id", "id", name="uq_stock_levels_org_id"),
    )
    op.create_table(
        "supplier_products",
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("min_quantity", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organisation_id", "connection_id"],
            ["integration_connections.organisation_id", "integration_connections.id"],
            name="fk_supplier_products_connection_same_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id", "product_id"],
            ["products.organisation_id", "products.id"],
            name="fk_supplier_products_product_same_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id", "supplier_id"],
            ["suppliers.organisation_id", "suppliers.id"],
            name="fk_supplier_products_supplier_same_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_supplier_products_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_supplier_products")),
        sa.UniqueConstraint(
            "connection_id",
            "external_id",
            name=op.f("uq_supplier_products_connection_id_external_id"),
        ),
        sa.UniqueConstraint("organisation_id", "id", name="uq_supplier_products_org_id"),
    )
    op.create_table(
        "purchase_order_lines",
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("received_quantity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("expected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organisation_id", "connection_id"],
            ["integration_connections.organisation_id", "integration_connections.id"],
            name="fk_purchase_order_lines_connection_same_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id", "product_id"],
            ["products.organisation_id", "products.id"],
            name="fk_purchase_order_lines_product_same_org",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id", "purchase_order_id"],
            ["purchase_orders.organisation_id", "purchase_orders.id"],
            name="fk_purchase_order_lines_po_same_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_purchase_order_lines_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_order_lines")),
        sa.UniqueConstraint(
            "connection_id",
            "external_id",
            name=op.f("uq_purchase_order_lines_connection_id_external_id"),
        ),
        sa.UniqueConstraint("organisation_id", "id", name="uq_purchase_order_lines_org_id"),
    )

    _security()
    _permissions()


TABLES = [
    "integration_connections",
    "integration_credentials",
    "integration_sync_jobs",
    "integration_events",
    "locations",
    "suppliers",
    "products",
    "supplier_products",
    "stock_levels",
    "sales_daily",
    "purchase_orders",
    "purchase_order_lines",
]

NEW_PERMISSIONS = [
    ("integrations.read", "View connected systems and their sync status"),
    ("integrations.manage", "Connect, configure and disconnect systems; import data"),
]
# Mirrors permissions/catalogue.py at this revision.
GRANTS = {
    "integrations.read": ["owner", "administrator", "operations_manager", "analyst"],
    "integrations.manage": ["owner", "administrator"],
}


def _security() -> None:
    for table in TABLES:
        op.execute(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            CREATE POLICY tenant_isolation ON {table}
              USING (organisation_id = app_current_org())
              WITH CHECK (organisation_id = app_current_org());
        """)
    # Webhook deliveries arrive before the organisation is known; resolve only by the
    # unguessable public id in the URL.
    op.execute("""
        CREATE FUNCTION operon_connection_by_public_id(p_public_id text)
        RETURNS TABLE (id uuid, organisation_id uuid)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
        $$ SELECT c.id, c.organisation_id FROM integration_connections c
           WHERE c.public_id = p_public_id $$;
        REVOKE ALL ON FUNCTION operon_connection_by_public_id(text) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION operon_connection_by_public_id(text) TO operon_app;
    """)


def _permissions() -> None:
    table = sa.table(
        "permissions", sa.column("key", sa.String), sa.column("description", sa.String)
    )
    op.bulk_insert(table, [{"key": k, "description": d} for k, d in NEW_PERMISSIONS])
    # Existing organisations' system roles get the new permissions too.
    for key, roles in GRANTS.items():
        op.execute(
            sa.text(
                "INSERT INTO role_permissions (organisation_id, role_id, permission_key) "
                "SELECT r.organisation_id, r.id, :key FROM roles r WHERE r.is_system AND r.key = ANY(:roles)"
            ).bindparams(key=key, roles=roles)
        )


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_key LIKE 'integrations.%'")
    op.execute("DELETE FROM permissions WHERE key LIKE 'integrations.%'")
    op.execute("DROP FUNCTION IF EXISTS operon_connection_by_public_id(text)")
    op.drop_table("purchase_order_lines")
    op.drop_table("supplier_products")
    op.drop_table("stock_levels")
    op.drop_index("ix_sales_daily_org_day", table_name="sales_daily")
    op.drop_table("sales_daily")
    op.drop_table("purchase_orders")
    op.drop_table("suppliers")
    op.drop_index("ix_products_org_sku", table_name="products")
    op.drop_table("products")
    op.drop_table("locations")
    op.drop_index("ix_integration_sync_jobs_connection", table_name="integration_sync_jobs")
    op.drop_table("integration_sync_jobs")
    op.drop_index("ix_integration_events_connection", table_name="integration_events")
    op.drop_table("integration_events")
    op.drop_table("integration_credentials")
    op.drop_index("ix_integration_connections_org", table_name="integration_connections")
    op.drop_table("integration_connections")
