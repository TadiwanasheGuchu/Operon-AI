"""Incidents: opening (from scratch or from an insight), ownership, timeline, escalation."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from operon.access.context import Actor, RequestMeta, TenantContext
from operon.core.db import Database, set_rls_context
from operon.core.errors import ApiError
from operon.core.logging import get_logger
from operon.modules.audit import service as audit
from operon.modules.incidents.models import Incident, IncidentEvent
from operon.modules.intelligence.engine import insight_event, next_number
from operon.modules.intelligence.models import Insight
from operon.modules.notifications.service import notify
from operon.modules.permissions.catalogue import Perm
from operon.modules.permissions.service import member_has_permission, members_with_permission

log = get_logger(__name__)

NOT_FOUND = ApiError(404, "not_found", "Incident not found.")
# Time allowed to start investigating (status → investigating) before the incident escalates.
RESPONSE_TARGETS = {
    "critical": timedelta(hours=1),
    "high": timedelta(hours=4),
    "medium": timedelta(hours=24),
    "low": timedelta(hours=72),
}
MAX_ESCALATIONS = 3  # mirrored by operon_incidents_due_for_escalation
TRANSITIONS = {
    "open": {"investigating", "resolved"},
    "investigating": {"resolved"},
    "resolved": {"investigating"},
}
SEVERITY_ORDER = case(
    {"critical": 0, "high": 1, "medium": 2, "low": 3}, value=Incident.severity, else_=4
)
UNSET: Any = object()


def _event(
    incident: Incident,
    kind: str,
    *,
    ctx: TenantContext | None = None,
    body: str | None = None,
    details: dict[str, Any] | None = None,
) -> IncidentEvent:
    return IncidentEvent(
        organisation_id=incident.organisation_id,
        incident_id=incident.id,
        kind=kind,
        actor_user_id=ctx.user_id if ctx else None,
        actor_label=ctx.user_email if ctx else "Operon escalation",
        body=body,
        details=details or {},
    )


def _actor(ctx: TenantContext) -> Actor:
    return Actor.user(ctx.user_id, ctx.user_email)


async def _check_assignee(session: AsyncSession, ctx: TenantContext, user_id: UUID) -> None:
    if not await member_has_permission(session, ctx.organisation_id, user_id, Perm.INCIDENTS_READ):
        raise ApiError(
            422, "invalid_assignee", "The assignee must be a member who can see incidents."
        )


@dataclass(frozen=True)
class IncidentPage:
    items: list[Incident]
    total: int
    counts: dict[str, int]  # unresolved incidents by severity


async def list_incidents(
    session: AsyncSession,
    ctx: TenantContext,
    *,
    status: str,
    severity: str | None,
    assignee: str | None,
    limit: int,
    offset: int,
) -> IncidentPage:
    q = select(Incident).where(Incident.organisation_id == ctx.organisation_id)
    if status == "unresolved":
        q = q.where(Incident.status != "resolved")
    elif status != "all":
        q = q.where(Incident.status == status)
    if severity:
        q = q.where(Incident.severity == severity)
    if assignee == "me":
        q = q.where(Incident.assignee_user_id == ctx.user_id)
    elif assignee == "none":
        q = q.where(Incident.assignee_user_id.is_(None))
    total = await session.scalar(select(func.count()).select_from(q.subquery()))
    rows = await session.scalars(
        q.order_by(SEVERITY_ORDER, Incident.created_at.desc()).limit(limit).offset(offset)
    )
    counts: dict[str, int] = {
        sev: int(n)
        for sev, n in (
            await session.execute(
                select(Incident.severity, func.count())
                .where(
                    Incident.organisation_id == ctx.organisation_id, Incident.status != "resolved"
                )
                .group_by(Incident.severity)
            )
        ).all()
    }
    return IncidentPage(list(rows.all()), int(total or 0), counts)


async def get_incident(session: AsyncSession, ctx: TenantContext, incident_id: UUID) -> Incident:
    incident = await session.get(Incident, incident_id)
    if incident is None or incident.organisation_id != ctx.organisation_id:
        raise NOT_FOUND
    return incident


async def timeline(session: AsyncSession, incident: Incident) -> list[IncidentEvent]:
    return list(
        await session.scalars(
            select(IncidentEvent)
            .where(
                IncidentEvent.organisation_id == incident.organisation_id,
                IncidentEvent.incident_id == incident.id,
            )
            .order_by(IncidentEvent.created_at, IncidentEvent.id)
        )
    )


async def create_incident(
    session: AsyncSession,
    ctx: TenantContext,
    *,
    title: str,
    description: str,
    severity: str,
    assignee_user_id: UUID | None,
    insight: Insight | None,
    meta: RequestMeta,
) -> Incident:
    if assignee_user_id is not None:
        await _check_assignee(session, ctx, assignee_user_id)
    if insight is not None:
        existing = await session.scalar(
            select(Incident.id).where(
                Incident.organisation_id == ctx.organisation_id,
                Incident.insight_id == insight.id,
                Incident.status != "resolved",
            )
        )
        if existing is not None:
            raise ApiError(
                409,
                "incident_exists",
                "This insight already has an open incident.",
                {"incident_id": str(existing)},
            )
    now = datetime.now(UTC)
    incident = Incident(
        organisation_id=ctx.organisation_id,
        number=await next_number(session, Incident, ctx.organisation_id, "incident-number"),
        title=title.strip()[:300],
        description=description.strip(),
        severity=severity,
        status="open",
        insight_id=insight.id if insight else None,
        assignee_user_id=assignee_user_id,
        reported_by=ctx.user_id,
        response_due_at=now + RESPONSE_TARGETS[severity],
    )
    session.add(incident)
    await session.flush()
    session.add(_event(incident, "created", ctx=ctx, details={"severity": severity}))
    if insight is not None:
        session.add(
            _event(
                incident,
                "insight_linked",
                ctx=ctx,
                details={"insight_id": str(insight.id), "reference": insight.reference},
            )
        )
        session.add(
            insight_event(
                insight,
                "escalated",
                {"incident_id": str(incident.id), "reference": incident.reference},
                user_id=ctx.user_id,
                label=ctx.user_email,
            )
        )
        if insight.status == "open":
            insight.status = "acknowledged"
            session.add(
                insight_event(
                    insight,
                    "acknowledged",
                    {"from": "open", "reason": f"Escalated to {incident.reference}"},
                    user_id=ctx.user_id,
                    label=ctx.user_email,
                )
            )
    if assignee_user_id is not None:
        session.add(_event(incident, "assigned", ctx=ctx, details={"to": str(assignee_user_id)}))
    await audit.record(
        session,
        actor=_actor(ctx),
        action="incident.created",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="incident",
        target_id=incident.id,
        details={
            "reference": incident.reference,
            "severity": severity,
            "insight_id": str(insight.id) if insight else None,
        },
    )
    await _notify_assignee(session, ctx, incident, assignee_user_id)
    return incident


async def update_incident(
    session: AsyncSession,
    ctx: TenantContext,
    incident: Incident,
    *,
    status: str | None = None,
    severity: str | None = None,
    assignee_user_id: UUID | None = UNSET,
    resolution: str | None = None,
    meta: RequestMeta,
) -> Incident:
    changes: dict[str, Any] = {}
    if severity is not None and severity != incident.severity:
        session.add(
            _event(
                incident,
                "severity_changed",
                ctx=ctx,
                details={"from": incident.severity, "to": severity},
            )
        )
        changes["severity"] = {"from": incident.severity, "to": severity}
        incident.severity = severity
        if incident.status == "open":
            incident.response_due_at = incident.created_at + RESPONSE_TARGETS[severity]
    if assignee_user_id is not UNSET and assignee_user_id != incident.assignee_user_id:
        if assignee_user_id is not None:
            await _check_assignee(session, ctx, assignee_user_id)
        session.add(
            _event(
                incident,
                "assigned",
                ctx=ctx,
                details={
                    "from": str(incident.assignee_user_id) if incident.assignee_user_id else None,
                    "to": str(assignee_user_id) if assignee_user_id else None,
                },
            )
        )
        changes["assignee"] = str(assignee_user_id) if assignee_user_id else None
        incident.assignee_user_id = assignee_user_id
        await _notify_assignee(session, ctx, incident, assignee_user_id)
    if status is not None and status != incident.status:
        if status not in TRANSITIONS[incident.status]:
            raise ApiError(
                409,
                "invalid_transition",
                f"An incident that is {incident.status} can't move to {status}.",
            )
        if status == "resolved":
            if not (resolution and resolution.strip()):
                raise ApiError(422, "resolution_required", "Describe how it was resolved.")
            incident.resolution = resolution.strip()
            incident.resolved_at = datetime.now(UTC)
        elif incident.status == "resolved":  # reopened
            incident.resolution = None
            incident.resolved_at = None
        session.add(
            _event(
                incident,
                "status_changed",
                ctx=ctx,
                body=incident.resolution if status == "resolved" else None,
                details={"from": incident.status, "to": status},
            )
        )
        changes["status"] = {"from": incident.status, "to": status}
        incident.status = status
    if changes:
        await audit.record(
            session,
            actor=_actor(ctx),
            action="incident.updated",
            meta=meta,
            organisation_id=ctx.organisation_id,
            target_type="incident",
            target_id=incident.id,
            details={"reference": incident.reference, **changes},
        )
    return incident


async def add_comment(
    session: AsyncSession, ctx: TenantContext, incident: Incident, body: str, meta: RequestMeta
) -> IncidentEvent:
    event = _event(incident, "comment", ctx=ctx, body=body.strip())
    session.add(event)
    await session.flush()
    await audit.record(
        session,
        actor=_actor(ctx),
        action="incident.commented",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="incident",
        target_id=incident.id,
        details={"reference": incident.reference},
    )
    if incident.assignee_user_id and incident.assignee_user_id != ctx.user_id:
        await notify(
            session,
            organisation_id=ctx.organisation_id,
            user_ids=[incident.assignee_user_id],
            kind="incident",
            title=f"New comment on {incident.reference}",
            body=body.strip()[:500],
            link=f"/incidents/{incident.id}",
        )
    return event


async def _notify_assignee(
    session: AsyncSession, ctx: TenantContext, incident: Incident, user_id: UUID | None
) -> None:
    if user_id is None or user_id == ctx.user_id:
        return
    await notify(
        session,
        organisation_id=ctx.organisation_id,
        user_ids=[user_id],
        kind="incident",
        title=f"{incident.reference} assigned to you: {incident.title}"[:200],
        body=f"Severity {incident.severity}. Start investigating to stop it escalating.",
        link=f"/incidents/{incident.id}",
    )


# --- escalation -------------------------------------------------------------------------------


async def escalate_overdue(db: Database, *, now: datetime | None = None, limit: int = 200) -> int:
    """Escalate open incidents nobody started investigating in time. Safe to run concurrently.

    Called by the Temporal maintenance schedule (production) or the in-process loop (dev).
    """
    now = now or datetime.now(UTC)
    async with db.sessionmaker() as s, s.begin():
        due = (
            await s.execute(
                text("SELECT id, organisation_id FROM operon_incidents_due_for_escalation(:n, :l)"),
                {"n": now, "l": limit},
            )
        ).all()
    escalated = 0
    for incident_id, org in due:
        async with db.sessionmaker() as s, s.begin():
            await set_rls_context(s, organisation_id=org)
            incident = await s.get(Incident, incident_id, with_for_update=True)
            if (
                incident is None
                or incident.status != "open"
                or incident.response_due_at > now
                or incident.escalation_level >= MAX_ESCALATIONS
            ):
                continue  # another sweep got there first, or someone responded
            incident.escalation_level += 1
            incident.last_escalated_at = now
            incident.response_due_at = now + RESPONSE_TARGETS[incident.severity]
            s.add(
                _event(
                    incident,
                    "escalated",
                    details={"level": incident.escalation_level, "reason": "no response in time"},
                )
            )
            managers = await members_with_permission(s, org, Perm.INCIDENTS_MANAGE)
            recipients = set(managers)
            if incident.assignee_user_id:
                recipients.add(incident.assignee_user_id)
            await notify(
                s,
                organisation_id=org,
                user_ids=recipients,
                kind="incident",
                title=f"Escalated: {incident.reference} {incident.title}"[:200],
                body=(
                    f"Nobody has started investigating this {incident.severity} incident "
                    f"(escalation {incident.escalation_level} of {MAX_ESCALATIONS})."
                ),
                link=f"/incidents/{incident.id}",
            )
            await audit.record(
                s,
                actor=Actor("system", None, "Operon escalation"),
                action="incident.escalated",
                meta=None,
                organisation_id=org,
                target_type="incident",
                target_id=incident.id,
                details={"reference": incident.reference, "level": incident.escalation_level},
            )
            escalated += 1
    if escalated:
        log.info("incidents_escalated", count=escalated)
    return escalated
