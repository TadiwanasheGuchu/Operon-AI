"""Data retention and organisation data export (Phase 7)."""

import json
import tempfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from operon.access.context import Actor, RequestMeta, TenantContext
from operon.core.db import Database, set_rls_context
from operon.core.logging import get_logger
from operon.modules.agents.models import (
    Agent,
    AgentExecution,
    AgentExecutionStep,
    AgentToolPermission,
    AgentVersion,
)
from operon.modules.ai.models import AIGeneration, OrganisationAISettings
from operon.modules.audit import service as audit
from operon.modules.audit.models import AuditLog
from operon.modules.governance.models import RETENTION_BOUNDS, RetentionPolicy
from operon.modules.identity.models import User
from operon.modules.incidents.models import Incident, IncidentEvent
from operon.modules.integrations.models import Connection, SyncJob
from operon.modules.intelligence.models import (
    DetectionRun,
    DetectorConfig,
    Insight,
    InsightEvent,
    InsightEvidence,
)
from operon.modules.operations.models import (
    Location,
    Product,
    PurchaseOrder,
    PurchaseOrderLine,
    SalesDaily,
    StockLevel,
    Supplier,
    SupplierProduct,
)
from operon.modules.organisations.models import Membership, Organisation
from operon.modules.permissions.models import Role, RolePermission
from operon.modules.workflows.models import (
    Workflow,
    WorkflowApproval,
    WorkflowExecution,
    WorkflowExecutionEvent,
    WorkflowVersion,
)

log = get_logger(__name__)


class RetentionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_days: int = Field(
        ge=RETENTION_BOUNDS["audit_days"][0], le=RETENTION_BOUNDS["audit_days"][1]
    )
    conversation_days: int = Field(
        ge=RETENTION_BOUNDS["conversation_days"][0], le=RETENTION_BOUNDS["conversation_days"][1]
    )
    run_log_days: int = Field(
        ge=RETENTION_BOUNDS["run_log_days"][0], le=RETENTION_BOUNDS["run_log_days"][1]
    )
    sync_job_days: int = Field(
        ge=RETENTION_BOUNDS["sync_job_days"][0], le=RETENTION_BOUNDS["sync_job_days"][1]
    )


async def policy(s: AsyncSession, org: UUID) -> RetentionPolicy:
    row = await s.get(RetentionPolicy, org)
    return row or RetentionPolicy(
        organisation_id=org,
        audit_days=730,
        conversation_days=90,
        run_log_days=180,
        sync_job_days=90,
    )


async def update_policy(
    s: AsyncSession, ctx: TenantContext, body: RetentionUpdate, meta: RequestMeta
) -> RetentionPolicy:
    row = await s.get(RetentionPolicy, ctx.organisation_id)
    before = None
    if row is None:
        row = RetentionPolicy(organisation_id=ctx.organisation_id)
        s.add(row)
    else:
        before = {k: getattr(row, k) for k in RETENTION_BOUNDS}
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    row.updated_by = ctx.user_id
    await audit.record(
        s,
        actor=Actor.user(ctx.user_id, ctx.user_email),
        action="retention.updated",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="organisation",
        target_id=ctx.organisation_id,
        details={"before": before, "after": body.model_dump()},
    )
    await s.flush()
    return row


async def apply_retention(db: Database, *, now: datetime | None = None) -> dict[str, int]:
    """Delete data older than each organisation's policy. Business records (insights,
    incidents, purchase requests and their histories) are kept; only logs and conversations age
    out. Safe to run repeatedly."""
    now = now or datetime.now(UTC)
    totals = {"audit": 0, "conversations": 0, "runs": 0, "sync_jobs": 0}
    async with db.sessionmaker() as s, s.begin():
        orgs = list((await s.execute(text("SELECT id FROM operon_organisation_ids()"))).scalars())
    for org in orgs:
        async with db.sessionmaker() as s, s.begin():
            await set_rls_context(s, organisation_id=org)
            p = await policy(s, org)
            counts = {
                "audit": int(
                    await s.scalar(
                        text("SELECT operon_purge_audit(:o, :b)"),
                        {"o": org, "b": now - timedelta(days=p.audit_days)},
                    )
                    or 0
                ),
                "conversations": int(
                    await s.scalar(
                        text("SELECT operon_purge_conversations(:o, :b)"),
                        {"o": org, "b": now - timedelta(days=p.conversation_days)},
                    )
                    or 0
                ),
            }
            runs = await s.execute(
                delete(AgentExecution).where(
                    AgentExecution.organisation_id == org,
                    AgentExecution.started_at < now - timedelta(days=p.run_log_days),
                    AgentExecution.status != "running",
                )
            )
            counts["runs"] = int(getattr(runs, "rowcount", 0) or 0)
            jobs = await s.execute(
                delete(SyncJob).where(
                    SyncJob.organisation_id == org,
                    SyncJob.started_at < now - timedelta(days=p.sync_job_days),
                    SyncJob.status != "running",
                )
            )
            counts["sync_jobs"] = int(getattr(jobs, "rowcount", 0) or 0)
            if any(counts.values()):
                await audit.record(
                    s,
                    actor=Actor("system", None, "Operon retention"),
                    action="retention.applied",
                    meta=None,
                    organisation_id=org,
                    details=counts,
                )
            for k, v in counts.items():
                totals[k] += v
    if any(totals.values()):
        log.info("retention_applied", **totals)
    return totals


# --- export -----------------------------------------------------------------------------------

# Never exported: credentials, password hashes, sessions, MFA secrets, invitation tokens, other
# people's private assistant conversations, and the SSO client secret.
_EXCLUDE_COLUMNS = {
    "integration_connections": {"public_id"},
    "audit_logs": {"ip_address"},
}

EXPORT_TABLES: list[tuple[str, Any]] = [
    ("roles", Role),
    ("role_permissions", RolePermission),
    ("integration_connections", Connection),
    ("integration_sync_jobs", SyncJob),
    ("locations", Location),
    ("suppliers", Supplier),
    ("products", Product),
    ("supplier_products", SupplierProduct),
    ("stock_levels", StockLevel),
    ("sales_daily", SalesDaily),
    ("purchase_orders", PurchaseOrder),
    ("purchase_order_lines", PurchaseOrderLine),
    ("detector_configs", DetectorConfig),
    ("detection_runs", DetectionRun),
    ("ai_insights", Insight),
    ("insight_evidence", InsightEvidence),
    ("insight_events", InsightEvent),
    ("ai_settings", OrganisationAISettings),
    ("ai_generations", AIGeneration),
    ("incidents", Incident),
    ("incident_events", IncidentEvent),
    ("workflows", Workflow),
    ("workflow_versions", WorkflowVersion),
    ("workflow_executions", WorkflowExecution),
    ("workflow_approvals", WorkflowApproval),
    ("workflow_execution_events", WorkflowExecutionEvent),
    ("agents", Agent),
    ("agent_versions", AgentVersion),
    ("agent_tool_permissions", AgentToolPermission),
    ("agent_executions", AgentExecution),
    ("agent_execution_steps", AgentExecutionStep),
    ("audit_logs", AuditLog),
    ("retention_policy", RetentionPolicy),
]


def _plain(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID | Decimal):
        return str(value)
    return value


def _row(obj: Any, name: str) -> dict[str, Any]:
    skip = _EXCLUDE_COLUMNS.get(name, set())
    return {
        c.key: _plain(getattr(obj, c.key))
        for c in inspect(type(obj)).column_attrs
        if c.key not in skip
    }


@dataclass
class ExportFile:
    path: str
    filename: str
    counts: dict[str, int]


async def export_organisation(s: AsyncSession, ctx: TenantContext, meta: RequestMeta) -> ExportFile:
    """A ZIP of JSON Lines files, one per table, scoped to the organisation (RLS applies)."""
    org = await s.get(Organisation, ctx.organisation_id)
    assert org is not None
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)  # noqa: SIM115 — streamed later
    tmp.close()
    counts: dict[str, int] = {}
    with zipfile.ZipFile(tmp.name, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        members = (
            await s.execute(
                select(Membership, User, Role)
                .join(User, User.id == Membership.user_id)
                .join(Role, Role.id == Membership.role_id)
                .where(Membership.organisation_id == ctx.organisation_id)
            )
        ).all()
        zf.writestr(
            "members.jsonl",
            "".join(
                json.dumps(
                    {
                        "user_id": str(u.id),
                        "email": u.email,
                        "full_name": u.full_name,
                        "role": r.key,
                        "joined_at": m.created_at.isoformat(),
                    }
                )
                + "\n"
                for m, u, r in members
            ),
        )
        counts["members"] = len(members)
        for name, model in EXPORT_TABLES:
            with zf.open(f"{name}.jsonl", "w") as fh:
                n = 0
                stream = await s.stream_scalars(
                    select(model).where(model.organisation_id == ctx.organisation_id)
                )
                async for obj in stream:
                    fh.write((json.dumps(_row(obj, name), default=str) + "\n").encode())
                    n += 1
                counts[name] = n
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "organisation": {"id": str(org.id), "name": org.name},
                    "exported_at": datetime.now(UTC).isoformat(),
                    "exported_by": ctx.user_email,
                    "format": "One JSON object per line; one file per table.",
                    "not_included": [
                        "integration credentials and webhook addresses",
                        "passwords, sessions and two-factor secrets",
                        "invitation tokens",
                        "members' private assistant conversations",
                        "the single sign-on client secret",
                    ],
                    "counts": counts,
                },
                indent=1,
            ),
        )
    await audit.record(
        s,
        actor=Actor.user(ctx.user_id, ctx.user_email),
        action="organisation.exported",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="organisation",
        target_id=ctx.organisation_id,
        details={"counts": counts},
    )
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    return ExportFile(tmp.name, f"operon-export-{stamp}.zip", counts)


def iter_file(path: str, chunk: int = 64 * 1024) -> Iterator[bytes]:
    import os

    try:
        with open(path, "rb") as fh:
            while data := fh.read(chunk):
                yield data
    finally:
        os.unlink(path)
