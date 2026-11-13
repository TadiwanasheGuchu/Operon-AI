from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from operon.access.context import TenantContext
from operon.access.dependencies import MetaDep, require_permission
from operon.core.deps import SessionDep
from operon.modules.incidents import service
from operon.modules.incidents.models import Incident
from operon.modules.incidents.schemas import (
    CommentRequest,
    CreateIncidentRequest,
    EscalateInsightRequest,
    IncidentDetail,
    IncidentEventOut,
    IncidentListOut,
    IncidentSummary,
    LinkedInsight,
    UpdateIncidentRequest,
)
from operon.modules.intelligence import service as insights
from operon.modules.intelligence.models import Insight
from operon.modules.intelligence.schemas import PersonOut
from operon.modules.organisations.service import Person, people
from operon.modules.permissions.catalogue import Perm

router = APIRouter(tags=["incidents"])

IncRead = Annotated[TenantContext, Depends(require_permission(Perm.INCIDENTS_READ))]
IncManage = Annotated[TenantContext, Depends(require_permission(Perm.INCIDENTS_MANAGE))]


def _person(p: Person | None) -> PersonOut | None:
    return PersonOut(user_id=p.user_id, full_name=p.full_name, email=p.email) if p else None


async def _context(
    session: Any, ctx: TenantContext, items: list[Incident]
) -> tuple[dict[UUID, Person], dict[UUID, Insight]]:
    from sqlalchemy import select

    users = {i.assignee_user_id for i in items if i.assignee_user_id} | {
        i.reported_by for i in items if i.reported_by
    }
    ppl = await people(session, ctx.organisation_id, users)
    ids = [i.insight_id for i in items if i.insight_id]
    linked: dict[UUID, Insight] = {}
    if ids:
        rows = await session.scalars(
            select(Insight).where(
                Insight.organisation_id == ctx.organisation_id, Insight.id.in_(ids)
            )
        )
        linked = {i.id: i for i in rows.all()}
    return ppl, linked


def _summary(i: Incident, ppl: dict[UUID, Person], linked: dict[UUID, Insight]) -> IncidentSummary:
    ins = linked.get(i.insight_id) if i.insight_id else None
    return IncidentSummary(
        id=i.id,
        reference=i.reference,
        title=i.title,
        severity=i.severity,
        status=i.status,
        assignee=_person(ppl.get(i.assignee_user_id)) if i.assignee_user_id else None,
        insight=LinkedInsight(
            id=ins.id,
            reference=ins.reference,
            title=ins.title,
            status=ins.status,
            severity=ins.severity,
        )
        if ins
        else None,
        response_due_at=i.response_due_at,
        response_overdue=i.status == "open" and i.response_due_at <= datetime.now(UTC),
        escalation_level=i.escalation_level,
        created_at=i.created_at,
        updated_at=i.updated_at,
        resolved_at=i.resolved_at,
    )


async def _detail(session: Any, ctx: TenantContext, incident: Incident) -> IncidentDetail:
    await session.flush()  # refresh() would discard unflushed changes
    await session.refresh(incident)
    ppl, linked = await _context(session, ctx, [incident])
    events = await service.timeline(session, incident)
    return IncidentDetail(
        **_summary(incident, ppl, linked).model_dump(),
        description=incident.description,
        resolution=incident.resolution,
        reported_by=_person(ppl.get(incident.reported_by)) if incident.reported_by else None,
        events=[
            IncidentEventOut(
                id=e.id,
                kind=e.kind,
                actor_label=e.actor_label,
                body=e.body,
                details=e.details,
                created_at=e.created_at,
            )
            for e in events
        ],
        allowed_transitions=sorted(service.TRANSITIONS[incident.status]),
    )


@router.get("/incidents", response_model=IncidentListOut)
async def list_incidents(
    ctx: IncRead,
    session: SessionDep,
    status_filter: Annotated[
        Literal["unresolved", "all", "open", "investigating", "resolved"], Query(alias="status")
    ] = "unresolved",
    severity: Annotated[Literal["low", "medium", "high", "critical"] | None, Query()] = None,
    assignee: Annotated[Literal["me", "none"] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> IncidentListOut:
    page = await service.list_incidents(
        session,
        ctx,
        status=status_filter,
        severity=severity,
        assignee=assignee,
        limit=limit,
        offset=offset,
    )
    ppl, linked = await _context(session, ctx, page.items)
    return IncidentListOut(
        items=[_summary(i, ppl, linked) for i in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
        unresolved_by_severity=page.counts,
    )


@router.post("/incidents", response_model=IncidentDetail, status_code=status.HTTP_201_CREATED)
async def create_incident(
    body: CreateIncidentRequest, ctx: IncManage, session: SessionDep, meta: MetaDep
) -> IncidentDetail:
    incident = await service.create_incident(
        session,
        ctx,
        title=body.title,
        description=body.description,
        severity=body.severity,
        assignee_user_id=body.assignee_user_id,
        insight=None,
        meta=meta,
    )
    await session.flush()
    return await _detail(session, ctx, incident)


@router.post(
    "/insights/{insight_id}/incident",
    response_model=IncidentDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Escalate an insight to an incident",
)
async def escalate_insight(
    insight_id: UUID,
    body: EscalateInsightRequest,
    ctx: IncManage,
    session: SessionDep,
    meta: MetaDep,
) -> IncidentDetail:
    insight = await insights.get_insight(session, ctx, insight_id)
    description = "\n\n".join(
        part
        for part in (
            body.note.strip(),
            f"Escalated from {insight.reference}. {insight.summary}",
        )
        if part
    )
    incident = await service.create_incident(
        session,
        ctx,
        title=insight.title,
        description=description,
        severity=insight.severity,
        assignee_user_id=body.assignee_user_id,
        insight=insight,
        meta=meta,
    )
    await session.flush()
    return await _detail(session, ctx, incident)


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
async def get_incident(incident_id: UUID, ctx: IncRead, session: SessionDep) -> IncidentDetail:
    return await _detail(session, ctx, await service.get_incident(session, ctx, incident_id))


@router.patch("/incidents/{incident_id}", response_model=IncidentDetail)
async def update_incident(
    incident_id: UUID,
    body: UpdateIncidentRequest,
    ctx: IncManage,
    session: SessionDep,
    meta: MetaDep,
) -> IncidentDetail:
    incident = await service.get_incident(session, ctx, incident_id)
    await service.update_incident(
        session,
        ctx,
        incident,
        status=body.status,
        severity=body.severity,
        assignee_user_id=body.assignee_user_id
        if "assignee_user_id" in body.model_fields_set
        else service.UNSET,
        resolution=body.resolution,
        meta=meta,
    )
    await session.flush()
    return await _detail(session, ctx, incident)


@router.post(
    "/incidents/{incident_id}/comments",
    response_model=IncidentEventOut,
    status_code=status.HTTP_201_CREATED,
)
async def comment(
    incident_id: UUID, body: CommentRequest, ctx: IncManage, session: SessionDep, meta: MetaDep
) -> IncidentEventOut:
    incident = await service.get_incident(session, ctx, incident_id)
    event = await service.add_comment(session, ctx, incident, body.body, meta)
    return IncidentEventOut(
        id=event.id,
        kind=event.kind,
        actor_label=event.actor_label,
        body=event.body,
        details=event.details,
        created_at=event.created_at,
    )
