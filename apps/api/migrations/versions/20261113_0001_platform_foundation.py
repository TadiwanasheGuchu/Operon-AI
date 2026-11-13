"""Platform foundation: extensions and system_events.

Revision ID: 0001
Revises:
Create Date: 2026-11-13 09:32:37.005166
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Trusted extensions (PG13+): the database owner can create them without superuser.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.create_table(
        "system_events",
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_events")),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'error', 'critical')",
            name=op.f("ck_system_events_severity_valid"),
        ),
    )
    op.create_index(
        op.f("ix_system_events_event_type"), "system_events", ["event_type"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_system_events_event_type"), table_name="system_events")
    op.drop_table("system_events")
    # Extensions are intentionally left installed: other database objects may depend on them.
