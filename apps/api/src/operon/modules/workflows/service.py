"""Purchase requests: configuration, submission, decisions, cancel and retry (plan §5.3-5.5)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from operon.access.context import Actor, RequestMeta, TenantContext
from operon.core.errors import ApiError
from operon.modules.audit import service as audit
from operon.modules.integrations.models import Connection
from operon.modules.intelligence.engine import insight_event, next_number
from operon.modules.intelligence.models import ACTIVE_STATUSES, Insight
from operon.modules.operations.models import Location, Product, Supplier
from operon.modules.permissions.catalogue import Perm
from operon.modules.permissions.models import Role
from operon.modules.workflows.engine import (
    TERMINAL,
    current_stage,
    event,
    notify_approvers,
)
from operon.modules.workflows.models import (
    ACTIVE_EXECUTION,
    Workflow,
    WorkflowApproval,
    WorkflowExecution,
    WorkflowExecutionEvent,
    WorkflowVersion,
)
from operon.modules.workflows.policy import PurchaseRequestParams, defaults, plan_stages

KEY = "purchase_request"
NOT_FOUND = ApiError(404, "not_found", "Purchase request not found.")
MAX_QUANTITY = 1_000_000


def _actor(ctx: TenantContext) -> Actor:
    return Actor.user(ctx.user_id, ctx.user_email)


# --- configuration --------------------------------------------------------------------------


async def ensure_workflow(session: AsyncSession, org: UUID) -> tuple[Workflow, WorkflowVersion]:
    """The organisation's purchase-request workflow, created with defaults on first use."""
    wf = await session.scalar(
        select(Workflow).where(Workflow.organisation_id == org, Workflow.key == KEY)
    )
    if wf is None:
        wf = Workflow(organisation_id=org, key=KEY, name="Purchase requests", current_version=1)
        session.add(wf)
        await session.flush()
        session.add(
            WorkflowVersion(organisation_id=org, workflow_id=wf.id, version=1, params=defaults())
        )
        await session.flush()
    version = await session.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == wf.id, WorkflowVersion.version == wf.current_version
        )
    )
    assert version is not None
    return wf, version


async def versions(session: AsyncSession, wf: Workflow) -> list[WorkflowVersion]:
    return list(
        await session.scalars(
            select(WorkflowVersion)
            .where(WorkflowVersion.workflow_id == wf.id)
            .order_by(WorkflowVersion.version.desc())
        )
    )


async def update_workflow(
    session: AsyncSession,
    ctx: TenantContext,
    *,
    enabled: bool,
    params: dict[str, Any],
    meta: RequestMeta,
) -> Workflow:
    wf, current = await ensure_workflow(session, ctx.organisation_id)
    try:
        validated = PurchaseRequestParams.model_validate(params).model_dump(mode="json")
    except ValidationError as exc:
        raise ApiError(
            422,
            "invalid_params",
            "Some settings are invalid.",
            {
                "errors": [
                    {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]}
                    for e in exc.errors()
                ]
            },
        ) from exc
    changes: dict[str, Any] = {}
    if validated != current.params:
        wf.current_version += 1
        session.add(
            WorkflowVersion(
                organisation_id=ctx.organisation_id,
                workflow_id=wf.id,
                version=wf.current_version,
                params=validated,
                created_by=ctx.user_id,
            )
        )
        changes["version"] = wf.current_version
    if enabled != wf.enabled:
        wf.enabled = enabled
        changes["enabled"] = enabled
    if changes:
        await audit.record(
            session,
            actor=_actor(ctx),
            action="workflow.configured",
            meta=meta,
            organisation_id=ctx.organisation_id,
            target_type="workflow",
            target_id=wf.id,
            details={**changes, "params": validated},
        )
    await session.flush()
    return wf


# --- submission -------------------------------------------------------------------------------


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except InvalidOperation:
        return None


async def submit_from_insight(
    session: AsyncSession,
    ctx: TenantContext,
    *,
    insight_id: UUID,
    quantity: int,
    note: str,
    meta: RequestMeta | None,
    origin: dict[str, Any] | None = None,
) -> WorkflowExecution:
    """Create a purchase request from a stockout insight's recommendation.

    Product, supplier and price come from the insight (server-side), never from the client.
    The requester may change only the quantity; the change is recorded.
    """
    insight = await session.get(Insight, insight_id)
    if insight is None or insight.organisation_id != ctx.organisation_id:
        raise ApiError(404, "not_found", "Insight not found.")
    rec = insight.recommendation or {}
    if rec.get("action") != "create_purchase_request":
        raise ApiError(409, "not_orderable", "This insight doesn't recommend a purchase.")
    if insight.status not in ACTIVE_STATUSES:
        raise ApiError(409, "insight_closed", "This insight is closed.")
    if not 1 <= quantity <= MAX_QUANTITY:
        raise ApiError(422, "invalid_quantity", f"Quantity must be 1 to {MAX_QUANTITY:,}.")
    wf, version = await ensure_workflow(session, ctx.organisation_id)
    if not wf.enabled:
        raise ApiError(409, "workflow_disabled", "Purchase requests are turned off.")
    existing = await session.scalar(
        select(WorkflowExecution).where(
            WorkflowExecution.organisation_id == ctx.organisation_id,
            WorkflowExecution.insight_id == insight.id,
            WorkflowExecution.status.in_(ACTIVE_EXECUTION),
        )
    )
    if existing is not None:
        raise ApiError(
            409,
            "request_exists",
            f"{existing.reference} is already in progress for this insight.",
            {"execution_id": str(existing.id)},
        )

    product = await session.get(Product, UUID(rec["product_id"]))
    if product is None or product.organisation_id != ctx.organisation_id:
        raise ApiError(409, "product_gone", "The product no longer exists in Operon.")
    supplier = (
        await session.get(Supplier, UUID(rec["supplier_id"])) if rec.get("supplier_id") else None
    )
    location = (
        await session.get(Location, UUID(rec["location_id"])) if rec.get("location_id") else None
    )
    unit_price = _decimal(rec.get("unit_price"))
    currency = rec.get("currency")
    value = unit_price * quantity if unit_price is not None else None
    target = await _target(session, product, supplier)
    params = PurchaseRequestParams.model_validate(version.params)
    stages = plan_stages(params, value, currency)
    uom = product.uom or "units"
    title = f"{quantity:,} {uom} of {product.name}"
    inp: dict[str, Any] = {
        "product_id": str(product.id),
        "product_name": product.name,
        "sku": product.sku,
        "uom": uom,
        "location_id": str(location.id) if location else None,
        "location_name": location.name if location else None,
        "supplier_id": str(supplier.id) if supplier else None,
        "supplier_name": supplier.name if supplier else None,
        "quantity": quantity,
        "recommended_quantity": rec.get("quantity"),
        "unit_price": str(unit_price) if unit_price is not None else None,
        "currency": currency,
        "value": str(value.quantize(Decimal("0.01"))) if value is not None else None,
        "value_display": f"{currency or ''} {value:,.2f}".strip() if value is not None else None,
        "note": note.strip()[:2000],
        "insight_reference": insight.reference,
        "target": target,
        # Who drafted it: a person, or an agent acting for that person (ADR 0014).
        "origin": origin or {"type": "user"},
    }
    now = datetime.now(UTC)
    e = WorkflowExecution(
        organisation_id=ctx.organisation_id,
        number=await next_number(session, WorkflowExecution, ctx.organisation_id, "pr-number"),
        workflow_id=wf.id,
        version_id=version.id,
        status="awaiting_approval",
        title=title[:300],
        input=inp,
        insight_id=insight.id,
        requested_by=ctx.user_id,
    )
    session.add(e)
    try:
        await session.flush()
    except IntegrityError as exc:  # a concurrent submission for the same insight won
        raise ApiError(409, "request_exists", "A request is already in progress.") from exc
    due = now + timedelta(hours=params.approval_timeout_hours)
    for st in stages:
        session.add(
            WorkflowApproval(
                organisation_id=ctx.organisation_id,
                execution_id=e.id,
                stage=st.stage,
                name=st.name,
                approver_roles=st.approver_roles,
                reason=st.reason,
                status="pending" if st.stage == 1 else "waiting",
                due_at=due if st.stage == 1 else None,
            )
        )
    e.next_wake_at = due
    by_agent = bool(origin and origin.get("type") == "agent")
    actor_label = (
        f"{origin.get('agent')} for {ctx.user_email}" if by_agent and origin else ctx.user_email
    )
    session.add(
        event(
            e,
            "submitted",
            f"Requested {title} from {inp['supplier_name'] or 'a supplier to be chosen'}"
            + (f", {inp['value_display']}" if inp["value_display"] else "")
            + f". Needs {len(stages)} approval(s).",
            {
                "policy_version": version.version,
                "stages": [s.model_dump() for s in stages],
                "origin": inp["origin"],
            },
            user_id=ctx.user_id,
            label=actor_label,
        )
    )
    if rec.get("quantity") is not None and int(rec["quantity"]) != quantity:
        session.add(
            event(
                e,
                "quantity_changed",
                f"Quantity changed from the recommended {int(rec['quantity']):,} to {quantity:,}.",
                {"recommended": rec["quantity"], "requested": quantity},
                user_id=ctx.user_id,
                label=ctx.user_email,
            )
        )
    if insight.status == "open":
        insight.status = "acknowledged"
    session.add(
        insight_event(
            insight,
            "purchase_requested",
            {"execution_id": str(e.id), "reference": e.reference, "quantity": quantity},
            user_id=ctx.user_id,
            label=ctx.user_email,
        )
    )
    await session.flush()
    first = await current_stage(session, e)
    if first is not None:
        await notify_approvers(session, e, first)
    await audit.record(
        session,
        actor=Actor("agent", ctx.user_id, actor_label) if by_agent else _actor(ctx),
        action="workflow.submitted",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="workflow_execution",
        target_id=e.id,
        details={
            "reference": e.reference,
            "quantity": quantity,
            "recommended_quantity": rec.get("quantity"),
            "value": inp["value"],
            "currency": currency,
            "insight": insight.reference,
            "origin": inp["origin"],
        },
    )
    return e


async def _target(
    session: AsyncSession, product: Product, supplier: Supplier | None
) -> dict[str, Any]:
    conn = await session.get(Connection, product.connection_id)
    if (
        conn is not None
        and conn.connector == "odoo"
        and supplier is not None
        and supplier.connection_id == conn.id
    ):
        return {
            "type": "odoo",
            "connection_id": str(conn.id),
            "connection_name": conn.name,
            "product_external_id": product.external_id,
            "supplier_external_id": supplier.external_id,
        }
    reason = (
        "The product isn't linked to a supplier in the same purchasing system."
        if conn is not None and conn.connector == "odoo"
        else f"{conn.name if conn else 'The source'} can't receive purchase orders."
    )
    return {"type": "record_only", "reason": reason}


# --- reading ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionPage:
    items: list[WorkflowExecution]
    total: int
    counts: dict[str, int]


async def list_executions(
    session: AsyncSession,
    ctx: TenantContext,
    *,
    status: str,
    mine: bool,
    limit: int,
    offset: int,
) -> ExecutionPage:
    q = select(WorkflowExecution).where(WorkflowExecution.organisation_id == ctx.organisation_id)
    if status == "active":
        q = q.where(WorkflowExecution.status.in_(ACTIVE_EXECUTION))
    elif status == "finished":
        q = q.where(WorkflowExecution.status.in_(TERMINAL))
    elif status != "all":
        q = q.where(WorkflowExecution.status == status)
    if mine:
        q = q.where(WorkflowExecution.requested_by == ctx.user_id)
    total = await session.scalar(select(func.count()).select_from(q.subquery()))
    rows = await session.scalars(
        q.order_by(WorkflowExecution.created_at.desc()).limit(limit).offset(offset)
    )
    counts = {
        k: int(n)
        for k, n in (
            await session.execute(
                select(WorkflowExecution.status, func.count())
                .where(WorkflowExecution.organisation_id == ctx.organisation_id)
                .group_by(WorkflowExecution.status)
            )
        ).all()
    }
    return ExecutionPage(list(rows.all()), int(total or 0), counts)


async def get_execution(
    session: AsyncSession, ctx: TenantContext, execution_id: UUID, *, lock: bool = False
) -> WorkflowExecution:
    e = await session.get(WorkflowExecution, execution_id, with_for_update=lock)
    if e is None or e.organisation_id != ctx.organisation_id:
        raise NOT_FOUND
    return e


async def approvals_of(session: AsyncSession, e: WorkflowExecution) -> list[WorkflowApproval]:
    return list(
        await session.scalars(
            select(WorkflowApproval)
            .where(
                WorkflowApproval.organisation_id == e.organisation_id,
                WorkflowApproval.execution_id == e.id,
            )
            .order_by(WorkflowApproval.stage)
        )
    )


async def events_of(session: AsyncSession, e: WorkflowExecution) -> list[WorkflowExecutionEvent]:
    return list(
        await session.scalars(
            select(WorkflowExecutionEvent)
            .where(
                WorkflowExecutionEvent.organisation_id == e.organisation_id,
                WorkflowExecutionEvent.execution_id == e.id,
            )
            .order_by(WorkflowExecutionEvent.created_at, WorkflowExecutionEvent.id)
        )
    )


def decision_block(
    ctx: TenantContext, e: WorkflowExecution, stage: WorkflowApproval, decided: set[UUID]
) -> str | None:
    """Why this user can't decide this stage, or None if they can (separation of duties)."""
    if e.status != "awaiting_approval" or stage.status != "pending":
        return "This stage isn't waiting for a decision."
    if not ctx.has(Perm.APPROVALS_DECIDE):
        return "You don't have permission to approve requests."
    if e.requested_by == ctx.user_id:
        return "You requested this, so someone else must approve it."
    if ctx.user_id in decided:
        return "You already decided an earlier stage of this request."
    if ctx.role_key not in stage.approver_roles:
        return "Your role isn't one of the approvers for this stage."
    return None


async def inbox(
    session: AsyncSession, ctx: TenantContext
) -> list[tuple[WorkflowApproval, WorkflowExecution, str | None]]:
    """Pending stages in the organisation, each with why (or whether) this user can decide."""
    rows = (
        await session.execute(
            select(WorkflowApproval, WorkflowExecution)
            .join(WorkflowExecution, WorkflowExecution.id == WorkflowApproval.execution_id)
            .where(
                WorkflowApproval.organisation_id == ctx.organisation_id,
                WorkflowApproval.status == "pending",
                WorkflowExecution.status == "awaiting_approval",
            )
            .order_by(WorkflowApproval.due_at)
        )
    ).all()
    out = []
    for stage, e in rows:
        decided = {a.decided_by for a in await approvals_of(session, e) if a.decided_by is not None}
        out.append((stage, e, decision_block(ctx, e, stage, decided)))
    return out


# --- decisions, cancel, retry -----------------------------------------------------------------


async def decide(
    session: AsyncSession,
    ctx: TenantContext,
    approval_id: UUID,
    *,
    approve: bool,
    comment: str,
    meta: RequestMeta,
) -> WorkflowExecution:
    stage = await session.get(WorkflowApproval, approval_id)
    if stage is None or stage.organisation_id != ctx.organisation_id:
        raise ApiError(404, "not_found", "Approval not found.")
    e = await get_execution(session, ctx, stage.execution_id, lock=True)
    await session.refresh(stage)
    stages = await approvals_of(session, e)
    decided = {a.decided_by for a in stages if a.decided_by is not None}
    block = decision_block(ctx, e, stage, decided)
    if block is not None:
        status = 409 if "isn't waiting" in block else 403
        raise ApiError(status, "cannot_decide", block)
    if not approve and not comment.strip():
        raise ApiError(422, "comment_required", "Say why you're rejecting the request.")
    now = datetime.now(UTC)
    stage.status = "approved" if approve else "rejected"
    stage.decided_by = ctx.user_id
    stage.decided_at = now
    stage.comment = comment.strip()[:2000] or None
    verb = "approved" if approve else "rejected"
    session.add(
        event(
            e,
            f"stage_{verb}",
            f"{stage.name} {verb}" + (f": {stage.comment}" if stage.comment else "."),
            {"stage": stage.stage},
            user_id=ctx.user_id,
            label=ctx.user_email,
        )
    )
    if not approve:
        e.status = "rejected"
        e.next_wake_at = None
        e.completed_at = now
        for a in stages:
            if a.status in ("waiting", "pending") and a.id != stage.id:
                a.status = "cancelled"
    else:
        following = [a for a in stages if a.status == "waiting"]
        if following:
            nxt = following[0]
            params = PurchaseRequestParams.model_validate(
                (await session.get(WorkflowVersion, e.version_id)).params  # type: ignore[union-attr]
            )
            nxt.status = "pending"
            nxt.due_at = now + timedelta(hours=params.approval_timeout_hours)
            e.next_wake_at = nxt.due_at
            await session.flush()
            await notify_approvers(session, e, nxt)
        else:
            e.status = "approved"
            e.next_wake_at = now
            session.add(event(e, "approved", "All approvals given."))
    if e.requested_by and e.requested_by != ctx.user_id:
        from operon.modules.notifications.service import notify

        await notify(
            session,
            organisation_id=ctx.organisation_id,
            user_ids=[e.requested_by],
            kind="approval",
            title=f"{e.reference} {stage.name.lower()} {verb}"[:200],
            body=stage.comment or "",
            link=f"/workflows/{e.id}",
        )
    await audit.record(
        session,
        actor=_actor(ctx),
        action=f"approval.{verb}",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="workflow_execution",
        target_id=e.id,
        details={"reference": e.reference, "stage": stage.name, "comment": stage.comment},
    )
    return e


async def cancel(
    session: AsyncSession, ctx: TenantContext, execution_id: UUID, reason: str, meta: RequestMeta
) -> WorkflowExecution:
    e = await get_execution(session, ctx, execution_id, lock=True)
    if e.requested_by != ctx.user_id and not ctx.has(Perm.WORKFLOWS_MANAGE):
        raise ApiError(403, "forbidden", "Only the requester or a workflow manager can cancel.")
    if e.status not in ("awaiting_approval", "approved", "failed"):
        raise ApiError(
            409,
            "cannot_cancel",
            "Requests can be cancelled only before they're sent to the purchasing system "
            "(or after they failed).",
        )
    e.status = "cancelled"
    e.next_wake_at = None
    e.completed_at = datetime.now(UTC)
    for a in await approvals_of(session, e):
        if a.status in ("waiting", "pending"):
            a.status = "cancelled"
    session.add(
        event(
            e,
            "cancelled",
            "Cancelled" + (f": {reason.strip()}" if reason.strip() else "."),
            user_id=ctx.user_id,
            label=ctx.user_email,
        )
    )
    await audit.record(
        session,
        actor=_actor(ctx),
        action="workflow.cancelled",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="workflow_execution",
        target_id=e.id,
        details={"reference": e.reference, "reason": reason},
    )
    return e


async def retry(
    session: AsyncSession, ctx: TenantContext, execution_id: UUID, meta: RequestMeta
) -> WorkflowExecution:
    e = await get_execution(session, ctx, execution_id, lock=True)
    if e.status != "failed":
        raise ApiError(409, "cannot_retry", "Only failed requests can be retried.")
    e.status = "executing"
    e.attempts = 0
    e.next_wake_at = datetime.now(UTC)
    session.add(
        event(
            e,
            "retried",
            "Retry requested. The same idempotency key is used, so a request that did reach the "
            "purchasing system isn't duplicated.",
            user_id=ctx.user_id,
            label=ctx.user_email,
        )
    )
    await audit.record(
        session,
        actor=_actor(ctx),
        action="workflow.retried",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="workflow_execution",
        target_id=e.id,
        details={"reference": e.reference},
    )
    return e


async def roles_by_key(session: AsyncSession, org: UUID) -> dict[str, str]:
    rows = await session.execute(
        select(Role.key, Role.name).where(Role.organisation_id == org, Role.is_system.is_(True))
    )
    return {key: name for key, name in rows.all()}
