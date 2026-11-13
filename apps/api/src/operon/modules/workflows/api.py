from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status

from operon.access.context import TenantContext
from operon.access.dependencies import MetaDep, require_permission
from operon.core.deps import SessionDep
from operon.modules.intelligence.schemas import PersonOut
from operon.modules.organisations.service import Person, people
from operon.modules.permissions.catalogue import Perm
from operon.modules.workflows import service
from operon.modules.workflows.dispatch import WorkflowDispatcher
from operon.modules.workflows.models import (
    WorkflowApproval,
    WorkflowExecution,
    WorkflowVersion,
)
from operon.modules.workflows.schemas import (
    ApprovalOut,
    CancelRequest,
    DecisionRequest,
    ExecutionDetail,
    ExecutionEventOut,
    ExecutionListOut,
    ExecutionSummary,
    InboxItem,
    SubmitRequest,
    WorkflowConfigOut,
    WorkflowConfigUpdate,
    WorkflowVersionOut,
)

router = APIRouter(tags=["workflows"])

WfRead = Annotated[TenantContext, Depends(require_permission(Perm.WORKFLOWS_READ))]
WfRequest = Annotated[TenantContext, Depends(require_permission(Perm.WORKFLOWS_REQUEST))]
WfManage = Annotated[TenantContext, Depends(require_permission(Perm.WORKFLOWS_MANAGE))]
Decide = Annotated[TenantContext, Depends(require_permission(Perm.APPROVALS_DECIDE))]


def dispatcher(request: Request) -> WorkflowDispatcher:
    d: WorkflowDispatcher = request.app.state.workflow_dispatcher
    return d


def _person(p: Person | None) -> PersonOut | None:
    return PersonOut(user_id=p.user_id, full_name=p.full_name, email=p.email) if p else None


def _summary(
    e: WorkflowExecution, ppl: dict[UUID, Person], current: WorkflowApproval | None
) -> ExecutionSummary:
    return ExecutionSummary(
        id=e.id,
        reference=e.reference,
        title=e.title,
        status=e.status,
        requested_by=_person(ppl.get(e.requested_by)) if e.requested_by else None,
        supplier_name=e.input.get("supplier_name"),
        value_display=e.input.get("value_display"),
        insight_id=e.insight_id,
        insight_reference=e.input.get("insight_reference"),
        current_stage=current.name if current else None,
        target=e.input["target"]["type"],
        external_reference=(e.result or {}).get("reference"),
        created_at=e.created_at,
        updated_at=e.updated_at,
        completed_at=e.completed_at,
    )


def _approval(
    a: WorkflowApproval,
    ppl: dict[UUID, Person],
    role_names: dict[str, str],
    blocked: str | None,
) -> ApprovalOut:
    return ApprovalOut(
        id=a.id,
        stage=a.stage,
        name=a.name,
        approver_roles=a.approver_roles,
        approver_role_names=[role_names.get(r, r) for r in a.approver_roles],
        reason=a.reason,
        status=a.status,
        due_at=a.due_at,
        escalated_at=a.escalated_at,
        decided_by=_person(ppl.get(a.decided_by)) if a.decided_by else None,
        decided_at=a.decided_at,
        comment=a.comment,
        blocked_reason=blocked,
    )


async def _pending_by_execution(
    session: Any, org: UUID, ids: list[UUID]
) -> dict[UUID, WorkflowApproval]:
    from sqlalchemy import select

    if not ids:
        return {}
    rows = await session.scalars(
        select(WorkflowApproval)
        .where(
            WorkflowApproval.organisation_id == org,
            WorkflowApproval.execution_id.in_(ids),
            WorkflowApproval.status == "pending",
        )
        .order_by(WorkflowApproval.stage.desc())
    )
    return {a.execution_id: a for a in rows.all()}


async def _detail(session: Any, ctx: TenantContext, e: WorkflowExecution) -> ExecutionDetail:
    await session.flush()  # refresh() would discard unflushed changes
    await session.refresh(e)
    approvals = await service.approvals_of(session, e)
    events = await service.events_of(session, e)
    ppl = await people(
        session,
        ctx.organisation_id,
        {u for u in [e.requested_by, *(a.decided_by for a in approvals)] if u},
    )
    role_names = await service.roles_by_key(session, ctx.organisation_id)
    decided = {a.decided_by for a in approvals if a.decided_by}
    current = next((a for a in approvals if a.status == "pending"), None)
    version = await session.get(WorkflowVersion, e.version_id)
    return ExecutionDetail(
        **_summary(e, ppl, current).model_dump(),
        input={k: v for k, v in e.input.items() if k != "target"}
        | {
            "target_name": e.input["target"].get("connection_name"),
            "target_reason": e.input["target"].get("reason"),
        },
        result=e.result or {},
        error=e.error,
        attempts=e.attempts,
        policy_version=version.version if version else 0,
        approvals=[
            _approval(
                a,
                ppl,
                role_names,
                service.decision_block(ctx, e, a, decided) if a.status == "pending" else None,
            )
            for a in approvals
        ],
        events=[
            ExecutionEventOut(
                id=ev.id,
                kind=ev.kind,
                actor_label=ev.actor_label,
                message=ev.message,
                details=ev.details,
                created_at=ev.created_at,
            )
            for ev in events
        ],
        can_cancel=e.status in ("awaiting_approval", "approved", "failed")
        and (e.requested_by == ctx.user_id or ctx.has(Perm.WORKFLOWS_MANAGE)),
        can_retry=e.status == "failed" and ctx.has(Perm.WORKFLOWS_MANAGE),
    )


@router.post(
    "/purchase-requests", response_model=ExecutionDetail, status_code=status.HTTP_201_CREATED
)
async def submit(
    body: SubmitRequest,
    ctx: WfRequest,
    session: SessionDep,
    request: Request,
    background: BackgroundTasks,
    meta: MetaDep,
) -> ExecutionDetail:
    e = await service.submit_from_insight(
        session, ctx, insight_id=body.insight_id, quantity=body.quantity, note=body.note, meta=meta
    )
    # After commit: start the durable execution (it waits for approval).
    background.add_task(dispatcher(request).start, ctx.organisation_id, e.id)
    return await _detail(session, ctx, e)


@router.get("/purchase-requests", response_model=ExecutionListOut)
async def list_requests(
    ctx: WfRead,
    session: SessionDep,
    status_filter: Annotated[
        Literal["active", "finished", "all", "awaiting_approval", "failed", "completed"],
        Query(alias="status"),
    ] = "active",
    mine: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> ExecutionListOut:
    page = await service.list_executions(
        session, ctx, status=status_filter, mine=mine, limit=limit, offset=offset
    )
    ppl = await people(
        session, ctx.organisation_id, {e.requested_by for e in page.items if e.requested_by}
    )
    pending = await _pending_by_execution(session, ctx.organisation_id, [e.id for e in page.items])
    return ExecutionListOut(
        items=[_summary(e, ppl, pending.get(e.id)) for e in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
        by_status=page.counts,
    )


@router.get("/purchase-requests/{execution_id}", response_model=ExecutionDetail)
async def get_request(execution_id: UUID, ctx: WfRead, session: SessionDep) -> ExecutionDetail:
    return await _detail(session, ctx, await service.get_execution(session, ctx, execution_id))


@router.post("/purchase-requests/{execution_id}/cancel", response_model=ExecutionDetail)
async def cancel(
    execution_id: UUID,
    body: CancelRequest,
    ctx: WfRead,
    session: SessionDep,
    request: Request,
    background: BackgroundTasks,
    meta: MetaDep,
) -> ExecutionDetail:
    e = await service.cancel(session, ctx, execution_id, body.reason, meta)
    background.add_task(dispatcher(request).wake, ctx.organisation_id, e.id)
    return await _detail(session, ctx, e)


@router.post("/purchase-requests/{execution_id}/retry", response_model=ExecutionDetail)
async def retry(
    execution_id: UUID,
    ctx: WfManage,
    session: SessionDep,
    request: Request,
    background: BackgroundTasks,
    meta: MetaDep,
) -> ExecutionDetail:
    e = await service.retry(session, ctx, execution_id, meta)
    background.add_task(dispatcher(request).wake, ctx.organisation_id, e.id)
    return await _detail(session, ctx, e)


@router.get("/approvals", response_model=list[InboxItem])
async def approvals_inbox(
    ctx: WfRead, session: SessionDep, actionable: bool = False
) -> list[InboxItem]:
    items = await service.inbox(session, ctx)
    ppl = await people(
        session, ctx.organisation_id, {e.requested_by for _, e, _ in items if e.requested_by}
    )
    role_names = await service.roles_by_key(session, ctx.organisation_id)
    return [
        InboxItem(
            approval=_approval(stage, ppl, role_names, block),
            execution=_summary(e, ppl, stage),
        )
        for stage, e, block in items
        if not actionable or block is None
    ]


@router.post("/approvals/{approval_id}/decision", response_model=ExecutionDetail)
async def decide(
    approval_id: UUID,
    body: DecisionRequest,
    ctx: Decide,
    session: SessionDep,
    request: Request,
    background: BackgroundTasks,
    meta: MetaDep,
) -> ExecutionDetail:
    e = await service.decide(
        session,
        ctx,
        approval_id,
        approve=body.decision == "approve",
        comment=body.comment,
        meta=meta,
    )
    background.add_task(dispatcher(request).wake, ctx.organisation_id, e.id)
    return await _detail(session, ctx, e)


async def _config(session: Any, ctx: TenantContext) -> WorkflowConfigOut:
    wf, current = await service.ensure_workflow(session, ctx.organisation_id)
    history = await service.versions(session, wf)
    ppl = await people(
        session, ctx.organisation_id, {v.created_by for v in history if v.created_by}
    )
    return WorkflowConfigOut(
        key=wf.key,
        name=wf.name,
        enabled=wf.enabled,
        current_version=wf.current_version,
        params=current.params,
        versions=[
            WorkflowVersionOut(
                version=v.version,
                params=v.params,
                created_at=v.created_at,
                created_by=_person(ppl.get(v.created_by)) if v.created_by else None,
            )
            for v in history
        ],
        role_names=await service.roles_by_key(session, ctx.organisation_id),
    )


@router.get("/workflows/purchase-requests", response_model=WorkflowConfigOut)
async def get_config(ctx: WfRead, session: SessionDep) -> WorkflowConfigOut:
    return await _config(session, ctx)


@router.put("/workflows/purchase-requests", response_model=WorkflowConfigOut)
async def put_config(
    body: WorkflowConfigUpdate, ctx: WfManage, session: SessionDep, meta: MetaDep
) -> WorkflowConfigOut:
    await service.update_workflow(session, ctx, enabled=body.enabled, params=body.params, meta=meta)
    return await _config(session, ctx)
