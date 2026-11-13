"""Connections to external systems, their encrypted credentials, sync history and inbound events."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from operon.core.db import Base, IdMixin, TimestampMixin

CONNECTION_STATUSES = ("active", "syncing", "degraded", "action_required", "paused")


class Connection(IdMixin, TimestampMixin, Base):
    __tablename__ = "integration_connections"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'syncing', 'degraded', 'action_required', 'paused')",
            name="status_valid",
        ),
        CheckConstraint("connector IN ('odoo', 'shopify', 'csv')", name="connector_valid"),
        UniqueConstraint("organisation_id", "id", name="uq_integration_connections_org_id"),
        Index("ix_integration_connections_org", "organisation_id"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    connector: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="active")
    # Non-secret settings only (URLs, database name, shop domain, sync interval).
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Per-entity sync cursors, e.g. {"products": "2026-11-13T10:00:00+00:00"}.
    sync_state: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Unguessable identifier used in the webhook URL; not the primary key.
    public_id: Mapped[str] = mapped_column(String(64), unique=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Sanitised, user-facing explanation of the last problem. Never raw upstream errors.
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class ConnectionCredential(Base):
    """Secrets for one connection, AES-256-GCM encrypted and bound to the connection id."""

    __tablename__ = "integration_credentials"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organisation_id", "connection_id"],
            ["integration_connections.organisation_id", "integration_connections.id"],
            ondelete="CASCADE",
            name="fk_integration_credentials_connection_same_org",
        ),
    )

    connection_id: Mapped[UUID] = mapped_column(primary_key=True)
    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    secret_encrypted: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SyncJob(IdMixin, Base):
    __tablename__ = "integration_sync_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="status_valid"),
        CheckConstraint(
            "trigger IN ('initial', 'schedule', 'manual', 'webhook', 'upload')",
            name="trigger_valid",
        ),
        ForeignKeyConstraint(
            ["organisation_id", "connection_id"],
            ["integration_connections.organisation_id", "integration_connections.id"],
            ondelete="CASCADE",
            name="fk_integration_sync_jobs_connection_same_org",
        ),
        Index("ix_integration_sync_jobs_connection", "connection_id", "started_at"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    connection_id: Mapped[UUID] = mapped_column()
    trigger: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # {"products": {"fetched": 10, "upserted": 10}, ...}
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(String(500))
    workflow_id: Mapped[str | None] = mapped_column(String(200))


class InboundEvent(IdMixin, Base):
    """Webhook delivery, stored before processing. Unique per connection + source event id."""

    __tablename__ = "integration_events"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'processed', 'ignored')", name="status_valid"),
        UniqueConstraint("connection_id", "source_event_id"),
        ForeignKeyConstraint(
            ["organisation_id", "connection_id"],
            ["integration_connections.organisation_id", "integration_connections.id"],
            ondelete="CASCADE",
            name="fk_integration_events_connection_same_org",
        ),
        Index("ix_integration_events_connection", "connection_id", "received_at"),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE")
    )
    connection_id: Mapped[UUID] = mapped_column()
    source_event_id: Mapped[str] = mapped_column(String(200))
    topic: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
