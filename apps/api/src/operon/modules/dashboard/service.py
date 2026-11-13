"""Operations overview: one read model assembled from every module.

Each section states where its data came from. Real organisations get live data for what exists
today and an explicit "unavailable" (with the phase that brings it) for the rest. Organisations
flagged ``is_demo`` get labelled sample data from ``demo.py``. Sections the viewer lacks
permission for are "restricted" and carry no data.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from operon.access.context import TenantContext
from operon.core.errors import ApiError
from operon.modules.audit.models import AuditLog
from operon.modules.dashboard import demo
from operon.modules.dashboard.layouts import PRESETS, default_preset
from operon.modules.dashboard.models import DashboardLayout
from operon.modules.dashboard.schemas import (
    ActivityEvent,
    Approval,
    DashboardSummary,
    EvidenceItem,
    IncidentCounts,
    Indicator,
    Insight,
    IntegrationStatus,
    LayoutOut,
    LayoutSection,
    LocationRisk,
    OrganisationRef,
    Period,
    RecentJoin,
    Section,
    SetupStep,
    Team,
    Viewer,
    WorkflowStatus,
)
from operon.modules.identity.models import MfaFactor, User
from operon.modules.incidents.models import Incident
from operon.modules.integrations.models import Connection
from operon.modules.intelligence.models import ACTIVE_STATUSES, InsightEvidence
from operon.modules.intelligence.models import Insight as InsightRow
from operon.modules.intelligence.service import SEVERITY_ORDER, describe_recommendation
from operon.modules.operations.models import Location, StockLevel
from operon.modules.organisations.models import Invitation, Membership, Organisation
from operon.modules.permissions.catalogue import Perm
from operon.modules.permissions.models import Role
from operon.modules.workflows.models import WorkflowApproval, WorkflowExecution

INTEGRATIONS_PHASE = 3
INSIGHTS_PHASE = 4
WORKFLOWS_PHASE = 5


def _unavailable(message: str, phase: int | None = None) -> Section[Any]:
    return Section(
        state="unavailable", provenance="unavailable", message=message, available_in_phase=phase
    )


def _restricted(permission: str) -> Section[Any]:
    return Section(state="restricted", provenance="unavailable", message=f"Requires {permission}.")


def _ready[T](data: T, provenance: str, as_of: datetime) -> Section[T]:
    return Section(state="ready", provenance=provenance, as_of=as_of, data=data)


# --- layout ------------------------------------------------------------------------------------


async def get_layout(session: AsyncSession, ctx: TenantContext) -> LayoutOut:
    saved = await session.get(DashboardLayout, (ctx.organisation_id, ctx.user_id))
    key = saved.preset if saved else default_preset(ctx.role_key)
    preset = PRESETS[key]
    return LayoutOut(
        preset=key,
        name=preset.name,
        is_default=saved is None,
        sections=[LayoutSection(key=k, size=s) for k, s in preset.sections],
    )


async def set_layout(session: AsyncSession, ctx: TenantContext, preset: str | None) -> LayoutOut:
    if preset is None:
        saved = await session.get(DashboardLayout, (ctx.organisation_id, ctx.user_id))
        if saved:
            await session.delete(saved)
    else:
        await session.execute(
            insert(DashboardLayout)
            .values(organisation_id=ctx.organisation_id, user_id=ctx.user_id, preset=preset)
            .on_conflict_do_update(
                index_elements=["organisation_id", "user_id"],
                set_={"preset": preset, "updated_at": func.now()},
            )
        )
    await session.flush()
    session.expire_all()
    return await get_layout(session, ctx)


# --- live sections -----------------------------------------------------------------------------


async def _team(session: AsyncSession, ctx: TenantContext) -> Team:
    members = (
        await session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.organisation_id == ctx.organisation_id)
        )
        or 0
    )
    pending = (
        await session.scalar(
            select(func.count())
            .select_from(Invitation)
            .where(
                Invitation.organisation_id == ctx.organisation_id,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
                Invitation.expires_at > func.now(),
            )
        )
        or 0
    )
    with_mfa = (
        await session.scalar(
            select(func.count())
            .select_from(Membership)
            .join(MfaFactor, MfaFactor.user_id == Membership.user_id)
            .where(
                Membership.organisation_id == ctx.organisation_id,
                MfaFactor.confirmed_at.is_not(None),
            )
        )
        or 0
    )
    joins = (
        await session.execute(
            select(User.full_name, Role.name, Membership.created_at)
            .join(User, User.id == Membership.user_id)
            .join(Role, Role.id == Membership.role_id)
            .where(Membership.organisation_id == ctx.organisation_id)
            .order_by(Membership.created_at.desc())
            .limit(5)
        )
    ).all()
    return Team(
        members=members,
        pending_invitations=pending,
        mfa_enabled=with_mfa,
        recent_joins=[RecentJoin(name=n, role_name=r, joined_at=at) for n, r, at in joins],
    )


def _describe(event: AuditLog) -> str | None:
    """Human sentence for the activity feed. None = not operational activity (stays in audit)."""
    d: dict[str, Any] = event.details or {}
    match event.action:
        case "organisation.created":
            return "Created the organisation"
        case "organisation.updated":
            if "mfa_required" in d:
                on = d["mfa_required"].get("to")
                return (
                    "Required two-factor authentication"
                    if on
                    else "Removed the two-factor requirement"
                )
            return "Renamed the organisation" if "name" in d else "Changed organisation settings"
        case "member.joined" | "invitation.accepted":
            return "Joined the organisation"
        case "member.role_changed":
            return (
                f"Changed {d.get('user', 'a member')}'s role to {d.get('to', '').replace('_', ' ')}"
            )
        case "member.removed":
            return f"Removed {d.get('user', 'a member')}"
        case "invitation.created":
            return f"Invited {d.get('email', 'someone')} as {d.get('role', '').replace('_', ' ')}"
        case "integration.connected":
            return f"Connected {d.get('name', 'a system')}"
        case "integration.disconnected":
            return f"Disconnected {d.get('name', 'a system')}"
        case "integration.data_imported":
            rows = int(d.get("rows", 0))
            kind = IMPORT_LABELS.get(str(d.get("kind")), "data")
            return f"Imported {rows} {'row' if rows == 1 else 'rows'} of {kind}"
        case "invitation.revoked":
            return f"Withdrew the invitation to {d.get('email', 'someone')}"
    return None


async def _activity(session: AsyncSession, ctx: TenantContext) -> list[ActivityEvent]:
    rows = (
        await session.execute(
            select(AuditLog, User.full_name)
            .outerjoin(User, User.id == AuditLog.actor_user_id)
            .where(AuditLog.organisation_id == ctx.organisation_id, AuditLog.outcome == "success")
            .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
            .limit(40)
        )
    ).all()
    events = []
    for entry, name in rows:
        message = _describe(entry)
        if message:
            events.append(
                ActivityEvent(
                    id=str(entry.id),
                    at=entry.occurred_at,
                    actor_type="user" if entry.actor_type == "user" else "system",
                    actor=name or entry.actor_label,
                    message=message,
                    ref=None,
                )
            )
        if len(events) == 8:
            break
    return events


IMPORT_LABELS = {
    "locations": "locations",
    "products": "products",
    "supplier_terms": "supplier terms",
    "stock": "stock levels",
    "sales": "sales",
    "purchase_orders": "purchase order lines",
}
STATUS_MAP = {
    "active": "healthy",
    "syncing": "healthy",
    "degraded": "degraded",
    "action_required": "disconnected",
    "paused": "paused",
}


async def _integrations(session: AsyncSession, ctx: TenantContext) -> list[IntegrationStatus]:
    rows = (
        await session.scalars(
            select(Connection)
            .where(Connection.organisation_id == ctx.organisation_id)
            .order_by(Connection.created_at)
        )
    ).all()
    out = []
    for c in rows:
        detail = c.last_error or {
            "csv": "Imported from CSV files",
            "odoo": "Inventory, purchasing and sales",
            "shopify": "Sales, products and stock",
        }.get(c.connector, "")
        out.append(
            IntegrationStatus(
                id=str(c.id),
                name=c.name,
                system={"csv": "CSV import", "odoo": "Odoo", "shopify": "Shopify"}.get(
                    c.connector, c.connector
                ),
                status=STATUS_MAP.get(c.status, "degraded"),
                last_sync_at=c.last_success_at,
                detail=detail,
            )
        )
    return out


def _setup_steps(
    ctx: TenantContext, viewer_has_mfa: bool, team: Team | None, connected: bool
) -> list[SetupStep]:
    return [
        SetupStep(
            key="mfa",
            title="Protect your account with two-factor authentication",
            body="Required by many organisations, and the best defence against stolen passwords.",
            done=viewer_has_mfa,
            available=True,
            href="/account/security",
            action_label="Set up",
        ),
        SetupStep(
            key="team",
            title="Invite your team",
            body="Give colleagues the role that matches what they need to do.",
            done=bool(team and team.members > 1),
            available=ctx.has(Perm.MEMBERS_INVITE),
            href="/admin/members",
            action_label="Invite people",
        ),
        SetupStep(
            key="integrations",
            title="Connect your inventory and sales systems",
            body="Connect Odoo or Shopify, or import CSV files. Operational insights start once "
            "data flows.",
            done=connected,
            available=ctx.has(Perm.INTEGRATIONS_MANAGE),
            href="/integrations",
            action_label="Connect a system",
        ),
    ]


# --- intelligence -------------------------------------------------------------------------------

TOP_INSIGHTS = 5


async def _insights(
    session: AsyncSession, ctx: TenantContext
) -> tuple[list[Insight], dict[str, int]]:
    org = ctx.organisation_id
    rows = list(
        await session.scalars(
            select(InsightRow)
            .where(InsightRow.organisation_id == org, InsightRow.status.in_(ACTIVE_STATUSES))
            .order_by(SEVERITY_ORDER, InsightRow.detected_at.desc())
            .limit(TOP_INSIGHTS)
        )
    )
    counts = {
        sev: int(n)
        for sev, n in (
            await session.execute(
                select(InsightRow.severity, func.count())
                .where(InsightRow.organisation_id == org, InsightRow.status.in_(ACTIVE_STATUSES))
                .group_by(InsightRow.severity)
            )
        ).all()
    }
    if not rows:
        return [], counts
    ids = [r.id for r in rows]
    evidence: dict[Any, list[InsightEvidence]] = {i: [] for i in ids}
    for e in await session.scalars(
        select(InsightEvidence)
        .where(InsightEvidence.organisation_id == org, InsightEvidence.insight_id.in_(ids))
        .order_by(InsightEvidence.position)
    ):
        evidence[e.insight_id].append(e)
    conn_ids = {e.connection_id for es in evidence.values() for e in es if e.connection_id}
    conns = (
        {
            c.id: c
            for c in await session.scalars(
                select(Connection).where(
                    Connection.organisation_id == org, Connection.id.in_(conn_ids)
                )
            )
        }
        if conn_ids
        else {}
    )
    owner_ids = {r.owner_user_id for r in rows if r.owner_user_id}
    owners = (
        {
            uid: name
            for uid, name in (
                await session.execute(select(User.id, User.full_name).where(User.id.in_(owner_ids)))
            ).all()
        }
        if owner_ids
        else {}
    )
    out = []
    for r in rows:
        ev = evidence[r.id]
        source_names = sorted({conns[e.connection_id].name for e in ev if e.connection_id in conns})
        out.append(
            Insight(
                id=str(r.id),
                ref=r.reference,
                title=r.title,
                category=r.category,
                severity=r.severity,
                status=r.status,
                detected_at=r.detected_at,
                owner=owners.get(r.owner_user_id) if r.owner_user_id else None,
                source_system=", ".join(source_names) or "Operon",
                rule_id=r.rule_id,
                rule_version=r.rule_version,
                summary=r.summary,
                why_it_matters=(r.explanation or {}).get("why_it_matters", ""),
                recommended_action=describe_recommendation(r.recommendation),
                assumptions=r.assumptions,
                limitations=r.limitations,
                evidence=[
                    EvidenceItem(
                        label=e.label,
                        value=e.value,
                        source=e.formula
                        if e.source_type == "computed"
                        else (conns[e.connection_id].name if e.connection_id in conns else None),
                    )
                    for e in ev[:8]
                ],
                explanation_generated_by=r.explanation_source,
                explanation_model=None,
            )
        )
    return out, counts


async def _incident_counts(session: AsyncSession, ctx: TenantContext) -> IncidentCounts:
    counts = {
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
    return IncidentCounts(**{k: counts.get(k, 0) for k in ("critical", "high", "medium", "low")})


async def _inventory_risk(session: AsyncSession, ctx: TenantContext) -> list[LocationRisk]:
    """SKUs tracked per location, and how many have an active stockout insight."""
    org = ctx.organisation_id
    tracked = (
        await session.execute(
            select(Location.id, Location.name, func.count(func.distinct(StockLevel.product_id)))
            .join(StockLevel, StockLevel.location_id == Location.id)
            .where(Location.organisation_id == org)
            .group_by(Location.id, Location.name)
            .order_by(Location.name)
        )
    ).all()
    if not tracked:
        return []
    at_risk: dict[str, int] = {}
    for key in await session.scalars(
        select(InsightRow.subject_key).where(
            InsightRow.organisation_id == org,
            InsightRow.rule_id == "inventory.stockout_risk",
            InsightRow.status.in_(ACTIVE_STATUSES),
        )
    ):
        loc = key.split(":", 1)[1] if ":" in key else "*"
        at_risk[loc] = at_risk.get(loc, 0) + 1
    out = [
        LocationRisk(location=name, skus_at_risk=at_risk.get(str(lid), 0), skus_tracked=n)
        for lid, name, n in tracked
    ]
    if at_risk.get("*"):
        out.append(
            LocationRisk(
                location="Across locations",
                skus_at_risk=at_risk["*"],
                skus_tracked=sum(n for _, _, n in tracked),
            )
        )
    return out


# --- workflows --------------------------------------------------------------------------------


async def _approvals(session: AsyncSession, ctx: TenantContext) -> list[Approval]:
    rows = (
        await session.execute(
            select(WorkflowApproval, WorkflowExecution, User.full_name)
            .join(WorkflowExecution, WorkflowExecution.id == WorkflowApproval.execution_id)
            .outerjoin(User, User.id == WorkflowExecution.requested_by)
            .where(
                WorkflowApproval.organisation_id == ctx.organisation_id,
                WorkflowApproval.status == "pending",
                WorkflowExecution.status == "awaiting_approval",
            )
            .order_by(WorkflowExecution.created_at)
            .limit(8)
        )
    ).all()
    out = []
    for stage, e, requester in rows:
        value = e.input.get("value")
        out.append(
            Approval(
                id=str(e.id),
                ref=e.reference,
                title=e.title,
                requester=requester or "Former member",
                amount=float(value) if value is not None else None,
                currency=e.input.get("currency") if value is not None else None,
                policy=f"{stage.name}: {stage.reason}",
                requested_at=e.created_at,
                related_insight_ref=e.input.get("insight_reference"),
            )
        )
    return out


async def _workflow_status(session: AsyncSession, ctx: TenantContext) -> list[WorkflowStatus]:
    org = ctx.organisation_id
    counts = {
        k: int(n)
        for k, n in (
            await session.execute(
                select(WorkflowExecution.status, func.count())
                .where(WorkflowExecution.organisation_id == org)
                .group_by(WorkflowExecution.status)
            )
        ).all()
    }
    if not counts:
        return []
    since = datetime.now(UTC) - timedelta(hours=24)
    failed_24h = await session.scalar(
        select(func.count()).where(
            WorkflowExecution.organisation_id == org,
            WorkflowExecution.status == "failed",
            WorkflowExecution.updated_at >= since,
        )
    )
    completed = counts.get("completed", 0)
    finished = completed + counts.get("failed", 0)
    return [
        WorkflowStatus(
            workflow="Purchase requests",
            running=counts.get("approved", 0) + counts.get("executing", 0),
            awaiting_approval=counts.get("awaiting_approval", 0),
            failed_24h=int(failed_24h or 0),
            completed=completed,
            # Of requests that were approved and sent: how many went through.
            success_rate=round(100 * completed / finished, 1) if finished else 100.0,
        )
    ]


# --- summary -----------------------------------------------------------------------------------


async def build_summary(
    session: AsyncSession, ctx: TenantContext, period: Period, viewer_has_mfa: bool
) -> DashboardSummary:
    now = datetime.now(UTC)
    org = await session.get(Organisation, ctx.organisation_id)
    viewer = (
        await session.execute(
            select(User.full_name, Role.name)
            .join(Membership, Membership.user_id == User.id)
            .join(Role, Role.id == Membership.role_id)
            .where(Membership.id == ctx.membership_id)
        )
    ).first()
    if org is None or viewer is None:
        raise ApiError(404, "organisation_not_found", "Organisation not found.")

    team = await _team(session, ctx) if ctx.has(Perm.MEMBERS_READ) else None
    team_section = _ready(team, "live", now) if team else _restricted(Perm.MEMBERS_READ)
    activity_section = (
        _ready(await _activity(session, ctx), "live", now)
        if ctx.has(Perm.AUDIT_READ)
        else _restricted(Perm.AUDIT_READ)
    )
    base: dict[str, Any] = {
        "organisation": OrganisationRef(id=str(org.id), name=org.name, is_demo=org.is_demo),
        "viewer": Viewer(name=viewer[0], role_key=ctx.role_key, role_name=viewer[1]),
        "layout": await get_layout(session, ctx),
        "period": period,
        "generated_at": now,
        "team": team_section,
    }

    if org.is_demo:
        return DashboardSummary(
            **base,
            indicators=demo.indicators(period),
            getting_started=_ready([], "demo", now),
            insights=_ready(demo.insights(now), "demo", now),
            approvals=_ready(demo.approvals(now), "demo", now),
            incidents=_ready(demo.incidents(), "demo", now),
            fill_rate=_ready(demo.fill_rate(period, now), "demo", now),
            inventory_risk=_ready(demo.inventory_risk(), "demo", now),
            workflows=_ready(demo.workflows(), "demo", now),
            integrations=_ready(demo.integrations(now), "demo", now),
            activity=_ready(demo.activity(now), "demo", now),
        )

    indicators: list[Indicator] = []
    if team:
        indicators.append(
            Indicator(
                key="members",
                label="Members",
                value=team.members,
                provenance="live",
                detail=(
                    f"{team.pending_invitations} invitation pending"
                    if team.pending_invitations == 1
                    else f"{team.pending_invitations} invitations pending"
                ),
            )
        )
        all_mfa = team.mfa_enabled == team.members
        indicators.append(
            Indicator(
                key="mfa_coverage",
                label="Two-factor enabled",
                value=team.mfa_enabled,
                total=team.members,
                increase_is="good",
                provenance="live",
                state="healthy" if all_mfa else "attention",
                detail="Everyone is protected"
                if all_mfa
                else f"{team.members - team.mfa_enabled} without two-factor",
            )
        )
    connections = await _integrations(session, ctx) if ctx.has(Perm.INTEGRATIONS_READ) else None
    synced = bool(connections and any(c.last_sync_at for c in connections))
    if connections:
        healthy = sum(c.status == "healthy" for c in connections)
        problems = [c for c in connections if c.status in ("degraded", "disconnected")]
        indicators.append(
            Indicator(
                key="integrations",
                label="Integrations healthy",
                value=healthy,
                total=len(connections),
                increase_is="good",
                provenance="live",
                state="attention" if problems else "healthy",
                detail=f"{problems[0].name} needs attention"
                if problems
                else "All syncing normally",
            )
        )
    else:
        indicators.append(
            Indicator(
                key="integrations",
                label="Integrations connected",
                value=None,
                provenance="unavailable",
                detail="No systems connected yet",
            )
        )
    if ctx.has(Perm.INSIGHTS_READ):
        top, by_severity = await _insights(session, ctx)
        open_count = sum(by_severity.values())
        urgent = by_severity.get("critical", 0) + by_severity.get("high", 0)
        if synced or open_count:
            insights_section: Section[Any] = _ready(top, "live", now)
            indicators.append(
                Indicator(
                    key="open_insights",
                    label="Open insights",
                    value=open_count,
                    provenance="live",
                    state="critical"
                    if by_severity.get("critical")
                    else "attention"
                    if urgent
                    else "healthy",
                    detail=f"{urgent} high or critical" if urgent else "Nothing urgent",
                )
            )
        else:
            insights_section = _unavailable(
                "Insights appear once a connected system supplies data."
            )
            indicators.append(
                Indicator(
                    key="open_insights",
                    label="Open insights",
                    value=None,
                    provenance="unavailable",
                    detail="Detection starts once data flows",
                )
            )
    else:
        insights_section = _restricted(Perm.INSIGHTS_READ)
    incidents_section: Section[Any] = (
        _ready(await _incident_counts(session, ctx), "live", now)
        if ctx.has(Perm.INCIDENTS_READ)
        else _restricted(Perm.INCIDENTS_READ)
    )
    risk = await _inventory_risk(session, ctx) if ctx.has(Perm.INSIGHTS_READ) else None
    if risk is None:
        risk_section: Section[Any] = _restricted(Perm.INSIGHTS_READ)
    elif risk:
        risk_section = _ready(risk, "live", now)
    else:
        risk_section = _unavailable("Needs stock levels from a connected system.")
    if ctx.has(Perm.WORKFLOWS_READ):
        approvals = await _approvals(session, ctx)
        approvals_section: Section[Any] = _ready(approvals, "live", now)
        workflow_rows = await _workflow_status(session, ctx)
        workflows_section: Section[Any] = (
            _ready(workflow_rows, "live", now)
            if workflow_rows
            else _unavailable("No purchase requests yet. Raise one from a stockout insight.")
        )
        indicators.append(
            Indicator(
                key="pending_approvals",
                label="Pending approvals",
                value=len(approvals),
                provenance="live",
                state="attention" if approvals else "healthy",
                detail="Waiting for a decision" if approvals else "Nothing waiting",
            )
        )
    else:
        approvals_section = _restricted(Perm.WORKFLOWS_READ)
        workflows_section = _restricted(Perm.WORKFLOWS_READ)
    if connections is None:
        integrations_section: Section[Any] = _restricted(Perm.INTEGRATIONS_READ)
    elif connections:
        integrations_section = _ready(connections, "live", now)
    else:
        integrations_section = _unavailable("No systems are connected yet.", INTEGRATIONS_PHASE)
    return DashboardSummary(
        **base,
        indicators=indicators,
        getting_started=_ready(_setup_steps(ctx, viewer_has_mfa, team, synced), "live", now),
        insights=insights_section,
        approvals=approvals_section,
        incidents=incidents_section,
        fill_rate=_unavailable(
            "Fill rate needs customer order lines, which the current integrations don't import yet."
        ),
        inventory_risk=risk_section,
        workflows=workflows_section,
        integrations=integrations_section,
        activity=activity_section,
    )
