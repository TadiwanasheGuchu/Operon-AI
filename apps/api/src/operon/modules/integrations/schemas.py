from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

ConnectorKey = Literal["odoo", "shopify", "csv"]


class CatalogueField(BaseModel):
    name: str
    label: str
    secret: bool
    required: bool
    help: str | None = None
    choices: list[str] | None = None


class CatalogueEntry(BaseModel):
    key: ConnectorKey
    name: str
    description: str
    provides: list[str]
    fields: list[CatalogueField]
    supports_webhooks: bool
    verified_live: bool
    verification_note: str


class CreateConnectionRequest(BaseModel):
    connector: ConnectorKey
    name: str = Field(min_length=1, max_length=120)
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)
    sync_interval_minutes: int = Field(default=15, ge=5, le=1440)


class UpdateConnectionRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    sync_interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    paused: bool | None = None


class RotateCredentialsRequest(BaseModel):
    secrets: dict[str, str]


class ConnectionOut(BaseModel):
    id: UUID
    connector: ConnectorKey
    name: str
    status: str
    config: dict[str, Any]
    sync_interval_minutes: int
    last_sync_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    created_at: datetime
    webhook_url: str | None
    has_webhook_secret: bool


class CheckOut(BaseModel):
    ok: bool
    summary: str | None
    provides: list[str]
    message: str | None


class SyncJobOut(BaseModel):
    id: UUID
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    stats: dict[str, Any]
    error: str | None


class EventOut(BaseModel):
    id: UUID
    source_event_id: str
    topic: str
    status: str
    received_at: datetime
    processed_at: datetime | None


class UploadError(BaseModel):
    row: int
    column: str | None
    message: str


class UploadResult(BaseModel):
    kind: str
    accepted: bool
    rows: int
    written: int
    error_count: int
    errors: list[UploadError]
