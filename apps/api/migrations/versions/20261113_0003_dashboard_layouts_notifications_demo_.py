"""Dashboard layouts, notifications, demo organisations (with RLS and column privileges).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-13 11:22:28.743847
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dashboard_layouts",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("preset", sa.String(length=30), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "preset IN ('executive', 'operations', 'finance', 'warehouse')",
            name=op.f("ck_dashboard_layouts_preset_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_dashboard_layouts_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_dashboard_layouts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("organisation_id", "user_id", name=op.f("pk_dashboard_layouts")),
    )
    op.create_table(
        "notifications",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.String(length=500), nullable=False),
        sa.Column("link", sa.String(length=300), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('member', 'security', 'insight', 'approval', 'incident', 'integration', 'workflow')",
            name=op.f("ck_notifications_kind_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_notifications_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(
        "ix_notifications_recipient",
        "notifications",
        ["organisation_id", "user_id", "created_at"],
        unique=False,
    )
    op.add_column(
        "organisations", sa.Column("is_demo", sa.Boolean(), server_default="false", nullable=False)
    )

    _security()


ORG_WRITABLE_COLUMNS = "id, name, mfa_required, created_by, created_at, updated_at"


def _security() -> None:
    # Layouts: strictly the current user's own row in the current organisation.
    op.execute("""
        ALTER TABLE dashboard_layouts ENABLE ROW LEVEL SECURITY;
        CREATE POLICY own_layout ON dashboard_layouts
          USING (organisation_id = app_current_org() AND user_id = app_current_user())
          WITH CHECK (organisation_id = app_current_org() AND user_id = app_current_user());
    """)
    # Notifications: anyone acting in the organisation may notify a member of it, but only the
    # recipient can read, mark or delete their own.
    op.execute("""
        ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
        CREATE POLICY notifications_insert ON notifications FOR INSERT
          WITH CHECK (organisation_id = app_current_org());
        CREATE POLICY notifications_select ON notifications FOR SELECT
          USING (organisation_id = app_current_org() AND user_id = app_current_user());
        CREATE POLICY notifications_update ON notifications FOR UPDATE
          USING (organisation_id = app_current_org() AND user_id = app_current_user())
          WITH CHECK (organisation_id = app_current_org() AND user_id = app_current_user());
        CREATE POLICY notifications_delete ON notifications FOR DELETE
          USING (organisation_id = app_current_org() AND user_id = app_current_user());
    """)
    # The demo flag is owner-only: the application role can neither set it on insert nor flip it.
    op.execute(f"""
        REVOKE INSERT, UPDATE ON organisations FROM operon_app;
        GRANT INSERT ({ORG_WRITABLE_COLUMNS}) ON organisations TO operon_app;
        GRANT UPDATE ({ORG_WRITABLE_COLUMNS}) ON organisations TO operon_app;
    """)


def downgrade() -> None:
    op.execute(f"""
        REVOKE INSERT ({ORG_WRITABLE_COLUMNS}), UPDATE ({ORG_WRITABLE_COLUMNS})
          ON organisations FROM operon_app;
        GRANT INSERT, UPDATE ON organisations TO operon_app;
    """)
    op.drop_column("organisations", "is_demo")
    op.drop_index("ix_notifications_recipient", table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("dashboard_layouts")
