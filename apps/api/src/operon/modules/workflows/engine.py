"""Advance a purchase-request execution as far as it can go (plan §5.2).

`advance` is the only place executions move forward on their own. It is idempotent and safe to
call at any time, from anywhere: the Temporal workflow calls it after every signal and timer;
the inline runner calls it after submissions and decisions, and the maintenance sweep calls it
when a deadline or retry is due. People's decisions are recorded by `service.decide`, which then
wakes the execution.

Exactly-once external writes: the external call uses the execution id as an idempotency key
that the target system stores (Odoo `partner_ref`) and is searched before creating. If the
process dies after the order is created but before Operon records it, the next attempt finds
the existing order instead of creating a second one.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from operon.access.context import Actor
from operon.core.db import Database, set_rls_context
from operon.core.logging import get_logger
from operon.modules.audit import service as audit
from operon.modules.integrations.connectors.base import ConfigError, ConnectorError, TransientError
from operon.modules.integrations.models import Connection
from operon.modules.integrations.sync import SyncRuntime, build_connector
from operon.modules.intelligence.engine import insight_event
from operon.modules.intelligence.models import ACTIVE_STATUSES, Insight
from operon.modules.notifications.service import notify
from operon.modules.organisations.models import Membership
from operon.modules.permissions.catalogue import Perm
from operon.modules.permissions.models import Role, RolePermission
from operon.modules.permissions.service import members_with_permission
from operon.modules.workflows.models import (
    WorkflowApproval,
    WorkflowExecution,
    WorkflowExecutionEvent,
    WorkflowVersion,
)
from operon.modules.workflows.policy import PurchaseRequestParams

log = get_logger(__name__)

SYSTEM = "Operon workflow"
TERMINAL = ("completed", "rejected", "expired", "failed", "cancelled")
LOCK_RETRY = timedelta(seconds=30)


@dataclass
class WorkflowRuntime:
    sync: SyncRuntime  # database, settings, secrets and HTTP for the external write

    @property
    def db(self) -> Database:
        return self.sync.db


@dataclass(frozen=True)
class Step:
    done: bool
    wake_at: datetime | None = None


def idempotency_key(execution_id: UUID) -> str:
    return f"operon-{execution_id}"


def event(
    e: WorkflowExecution,
    kind: str,
    message: str,
    details: dict[str, Any] | None = None,
    *,
    user_id: UUID | None = None,
    label: str = SYSTEM,
) -> WorkflowExecutionEvent:
    return WorkflowExecutionEvent(
        organisation_id=e.organisation_id,
        execution_id=e.id,
        kind=kind,
        actor_user_id=user_id,
        actor_label=label,
        message=message[:500],
        details=details or {},
    )


async def params_of(s: AsyncSession, e: WorkflowExecution) -> PurchaseRequestParams:
    version = await s.get(WorkflowVersion, e.version_id)
    assert version is not None
    return PurchaseRequestParams.model_validate(version.params)


async def eligible_approvers(
    s: AsyncSession, org: UUID, roles: list[str], exclude: set[UUID]
) -> list[UUID]:
    """Members whose role is listed for the stage and who hold approvals.decide."""
    rows = await s.scalars(
        select(Membership.user_id)
        .join(Role, Role.id == Membership.role_id)
        .join(RolePermission, RolePermission.role_id == Role.id)
        .where(
            Membership.organisation_id == org,
            Role.key.in_(roles),
            RolePermission.permission_key == Perm.APPROVALS_DECIDE,
        )
    )
    return [u for u in rows.all() if u not in exclude]


async def current_stage(s: AsyncSession, e: WorkflowExecution) -> WorkflowApproval | None:
    stage: WorkflowApproval | None = await s.scalar(
        select(WorkflowApproval)
        .where(WorkflowApproval.execution_id == e.id, WorkflowApproval.status == "pending")
        .order_by(WorkflowApproval.stage)
        .limit(1)
    )
    return stage


async def notify_approvers(
    s: AsyncSession, e: WorkflowExecution, stage: WorkflowApproval, *, escalation: bool = False
) -> None:
    exclude = {e.requested_by} if e.requested_by else set()
    # Nobody may decide two stages of the same request.
    exclude |= {
        a.decided_by
        for a in await s.scalars(
            select(WorkflowApproval).where(
                WorkflowApproval.execution_id == e.id, WorkflowApproval.decided_by.is_not(None)
            )
        )
        if a.decided_by
    }
    users = set(await eligible_approvers(s, e.organisation_id, stage.approver_roles, exclude))
    if escalation:
        users |= set(await members_with_permission(s, e.organisation_id, Perm.WORKFLOWS_MANAGE))
    value = e.input.get("value_display") or "value unknown"
    await notify(
        s,
        organisation_id=e.organisation_id,
        user_ids=users,
        kind="approval",
        title=(
            f"Overdue approval: {e.reference} {e.title}"
            if escalation
            else f"Approval needed: {e.reference} {e.title}"
        )[:200],
        body=f"{stage.name} · {value}",
        link=f"/workflows/{e.id}",
    )


async def advance(
    rt: WorkflowRuntime, org: UUID, execution_id: UUID, *, now: datetime | None = None
) -> Step:
    now = now or datetime.now(UTC)
    async with rt.db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=org)
        e = await s.get(WorkflowExecution, execution_id, with_for_update=True)
        if e is None or e.organisation_id != org or e.status in TERMINAL:
            return Step(True)
        params = await params_of(s, e)

        if e.status == "awaiting_approval":
            stage = await current_stage(s, e)
            if stage is None:
                # Every stage decided in favour (decide() normally does this; defensive).
                e.status = "approved"
            elif stage.due_at is not None and stage.due_at <= now:
                if stage.escalated_at is None:
                    stage.escalated_at = now
                    stage.due_at = now + timedelta(hours=params.approval_timeout_hours)
                    e.next_wake_at = stage.due_at
                    s.add(
                        event(
                            e,
                            "approval_escalated",
                            f"{stage.name} wasn't decided in time; approvers and workflow "
                            "managers were reminded.",
                            {"stage": stage.stage, "new_due_at": stage.due_at.isoformat()},
                        )
                    )
                    await notify_approvers(s, e, stage, escalation=True)
                    return Step(False, stage.due_at)
                stage.status = "expired"
                e.status = "expired"
                e.next_wake_at = None
                e.completed_at = now
                s.add(
                    event(
                        e,
                        "expired",
                        f"{stage.name} wasn't decided after a reminder. The request expired.",
                        {"stage": stage.stage},
                    )
                )
                await _cancel_remaining(s, e, "expired")
                await _notify_requester(s, e, f"{e.reference} expired without a decision")
                return Step(True)
            else:
                e.next_wake_at = stage.due_at
                return Step(False, stage.due_at)

        if e.status == "approved":
            e.status = "executing"
            e.next_wake_at = None
            s.add(event(e, "execution_started", _target_message(e.input)))

        if e.next_wake_at is not None and e.next_wake_at > now:
            return Step(False, e.next_wake_at)  # waiting out a retry backoff
        target: dict[str, Any] = dict(e.input["target"])
        snapshot = dict(e.input)
        attempts = e.attempts

    # External write: outside the transaction, one runner at a time per execution.
    async with rt.db.engine.connect() as lock_conn:
        got = (
            await lock_conn.execute(
                text("SELECT pg_try_advisory_lock(hashtext(:k))"), {"k": f"wf:{execution_id}"}
            )
        ).scalar()
        if not got:
            return Step(False, now + LOCK_RETRY)
        try:
            try:
                result = await _write(rt, org, execution_id, target, snapshot)
            except ConnectorError as exc:
                return await _attempt_failed(rt, org, execution_id, exc, attempts, params, now)
            except Exception as exc:  # unknown failure: retry like a transient one
                log.exception("workflow_write_crashed", execution_id=str(execution_id))
                err = TransientError("The request couldn't be sent. Operon will retry.")
                err.detail = repr(exc)
                return await _attempt_failed(rt, org, execution_id, err, attempts, params, now)
            await record_completion(rt, org, execution_id, result)
            return Step(True)
        finally:
            await lock_conn.execute(
                text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": f"wf:{execution_id}"}
            )
            await lock_conn.commit()


def _target_message(inp: dict[str, Any]) -> str:
    t = inp["target"]
    if t["type"] == "odoo":
        return f"Approved. Creating a draft purchase order in {t.get('connection_name', 'Odoo')}."
    return "Approved. Recording the purchase request in Operon."


async def _write(
    rt: WorkflowRuntime,
    org: UUID,
    execution_id: UUID,
    target: dict[str, Any],
    inp: dict[str, Any],
) -> dict[str, Any]:
    if target["type"] == "record_only":
        return {"mode": "record_only", "note": target.get("reason", "")}
    async with rt.sync.http_factory() as http:
        async with rt.db.sessionmaker() as s, s.begin():
            await set_rls_context(s, organisation_id=org)
            conn = await s.get(Connection, UUID(target["connection_id"]))
            if conn is None or conn.organisation_id != org:
                raise ConfigError("The connected system for this request was disconnected.")
            if conn.status == "paused":
                raise TransientError(f"{conn.name} is paused. Resume it to send this request.")
            connector = await build_connector(rt.sync, s, conn, http)
        key = idempotency_key(execution_id)
        external_id = await connector.create_draft_purchase_order(
            supplier_external_id=target["supplier_external_id"],
            product_external_id=target["product_external_id"],
            quantity=Decimal(str(inp["quantity"])),
            unit_price=Decimal(inp["unit_price"]) if inp.get("unit_price") else None,
            idempotency_key=key,
        )
        order = await connector.get_purchase_order(external_id)
        if order is None or order.get("partner_ref") != key:
            raise TransientError("The purchase order couldn't be confirmed. Operon will retry.")
        return {
            "mode": "odoo",
            "connection_id": target["connection_id"],
            "external_id": external_id,
            "reference": order.get("name"),
            "state": order.get("state"),
            "idempotency_key": key,
        }


async def record_completion(
    rt: WorkflowRuntime, org: UUID, execution_id: UUID, result: dict[str, Any]
) -> None:
    now = datetime.now(UTC)
    async with rt.db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=org)
        e = await s.get(WorkflowExecution, execution_id, with_for_update=True)
        if e is None or e.status != "executing":
            return
        e.result = result
        e.status = "completed"
        e.error = None
        e.next_wake_at = None
        e.completed_at = now
        if result["mode"] == "odoo":
            msg = (
                f"Draft purchase order {result.get('reference')} created in "
                f"{e.input['target'].get('connection_name', 'Odoo')} for a person to confirm."
            )
        else:
            msg = "Purchase request recorded in Operon. Raise it in your purchasing system."
        s.add(event(e, "completed", msg, result))
        if e.insight_id:
            insight = await s.get(Insight, e.insight_id)
            if insight is not None and insight.status in ACTIVE_STATUSES:
                before = insight.status
                insight.status = "actioned"
                s.add(
                    insight_event(
                        insight,
                        "actioned",
                        {"from": before, "reason": f"{e.reference} completed"},
                        label=SYSTEM,
                    )
                )
        await audit.record(
            s,
            actor=Actor("system", None, SYSTEM),
            action="workflow.completed",
            meta=None,
            organisation_id=org,
            target_type="workflow_execution",
            target_id=e.id,
            details={"reference": e.reference, **result},
        )
        await _notify_requester(s, e, f"{e.reference} is done", msg)


async def _attempt_failed(
    rt: WorkflowRuntime,
    org: UUID,
    execution_id: UUID,
    exc: ConnectorError,
    attempts: int,
    params: PurchaseRequestParams,
    now: datetime,
) -> Step:
    log.warning(
        "workflow_attempt_failed",
        execution_id=str(execution_id),
        error=exc.user_message,
        detail=exc.detail,
    )
    async with rt.db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=org)
        e = await s.get(WorkflowExecution, execution_id, with_for_update=True)
        if e is None or e.status != "executing":
            return Step(True)
        e.attempts = attempts + 1
        e.error = exc.user_message[:500]
        if exc.retryable and e.attempts < params.max_attempts:
            delay = timedelta(minutes=min(2 ** (e.attempts - 1), 60))
            e.next_wake_at = now + delay
            s.add(
                event(
                    e,
                    "attempt_failed",
                    f"Attempt {e.attempts} failed: {exc.user_message} Retrying.",
                    {"attempt": e.attempts, "retry_at": e.next_wake_at.isoformat()},
                )
            )
            return Step(False, e.next_wake_at)
        e.status = "failed"
        e.next_wake_at = None
        s.add(
            event(
                e,
                "failed",
                f"Stopped after {e.attempts} attempt(s): {exc.user_message}",
                {"attempt": e.attempts, "retryable": exc.retryable},
            )
        )
        managers = await members_with_permission(s, org, Perm.WORKFLOWS_MANAGE)
        recipients = set(managers) | ({e.requested_by} if e.requested_by else set())
        await notify(
            s,
            organisation_id=org,
            user_ids=recipients,
            kind="workflow",
            title=f"{e.reference} failed: {e.title}"[:200],
            body=exc.user_message[:500],
            link=f"/workflows/{e.id}",
        )
        await audit.record(
            s,
            actor=Actor("system", None, SYSTEM),
            action="workflow.failed",
            outcome="failure",
            meta=None,
            organisation_id=org,
            target_type="workflow_execution",
            target_id=e.id,
            details={"reference": e.reference, "error": exc.user_message},
        )
        return Step(True)


async def _cancel_remaining(s: AsyncSession, e: WorkflowExecution, status: str) -> None:
    for a in await s.scalars(
        select(WorkflowApproval).where(
            WorkflowApproval.execution_id == e.id,
            WorkflowApproval.status.in_(("waiting", "pending")),
        )
    ):
        a.status = "cancelled"


async def _notify_requester(
    s: AsyncSession, e: WorkflowExecution, title: str, body: str = ""
) -> None:
    if e.requested_by:
        await notify(
            s,
            organisation_id=e.organisation_id,
            user_ids=[e.requested_by],
            kind="workflow",
            title=title[:200],
            body=body[:500],
            link=f"/workflows/{e.id}",
        )


async def due_executions(db: Database, now: datetime, limit: int = 200) -> list[tuple[UUID, UUID]]:
    async with db.sessionmaker() as s, s.begin():
        rows = (
            await s.execute(
                text("SELECT id, organisation_id FROM operon_workflow_executions_due(:n, :l)"),
                {"n": now, "l": limit},
            )
        ).all()
    return [(r[0], r[1]) for r in rows]


async def sweep(rt: WorkflowRuntime, *, now: datetime | None = None) -> int:
    """Advance every execution with a deadline or retry due. Used without Temporal."""
    now = now or datetime.now(UTC)
    count = 0
    for execution_id, org in await due_executions(rt.db, now):
        await advance(rt, org, execution_id, now=now)
        count += 1
    return count
