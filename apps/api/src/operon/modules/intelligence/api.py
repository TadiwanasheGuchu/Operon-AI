from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request

from operon.access.context import TenantContext
from operon.access.dependencies import MetaDep, require_permission
from operon.core.deps import SessionDep
from operon.core.errors import ApiError
from operon.modules.ai import service as ai
from operon.modules.ai.models import AIGeneration
from operon.modules.incidents.models import Incident
from operon.modules.intelligence import service
from operon.modules.intelligence.detectors.registry import DETECTORS
from operon.modules.intelligence.engine import IntelligenceRuntime, explain_insight, run_detection
from operon.modules.intelligence.models import Insight, InsightEvidence
from operon.modules.intelligence.schemas import (
    AISettingsOut,
    AISettingsUpdate,
    DetectionRunOut,
    DetectorOut,
    DetectorParamOut,
    DetectorUpdate,
    EvidenceOut,
    ExplanationOut,
    InsightDetail,
    InsightEventOut,
    InsightListOut,
    InsightSummary,
    OwnerRequest,
    PersonOut,
    SourceConnection,
    StatusChangeRequest,
)
from operon.modules.organisations.service import Person, people
from operon.modules.permissions.catalogue import Perm

router = APIRouter(tags=["intelligence"])

InsRead = Annotated[TenantContext, Depends(require_permission(Perm.INSIGHTS_READ))]
InsManage = Annotated[TenantContext, Depends(require_permission(Perm.INSIGHTS_MANAGE))]
OrgManage = Annotated[TenantContext, Depends(require_permission(Perm.ORGANISATION_MANAGE))]

DATA_SHARED = (
    "When on, each new or changed insight's title, evidence labels and values, recommendation, "
    "assumptions and limitations are sent to the provider to write the explanation. Nothing "
    "else is sent, and provider output is checked against the evidence before it is shown."
)


def runtime(request: Request) -> IntelligenceRuntime:
    rt: IntelligenceRuntime = request.app.state.intelligence
    return rt


def _person(p: Person | None) -> PersonOut | None:
    return PersonOut(user_id=p.user_id, full_name=p.full_name, email=p.email) if p else None


async def _incident_links(session: Any, ctx: TenantContext, ids: list[UUID]) -> dict[UUID, UUID]:
    from sqlalchemy import select

    if not ids:
        return {}
    rows = await session.execute(
        select(Incident.insight_id, Incident.id).where(
            Incident.organisation_id == ctx.organisation_id,
            Incident.insight_id.in_(ids),
            Incident.status != "resolved",
        )
    )
    return {insight_id: incident_id for insight_id, incident_id in rows.all()}


def _summary(i: Insight, owners: dict[UUID, Person], incidents: dict[UUID, UUID]) -> InsightSummary:
    return InsightSummary(
        id=i.id,
        reference=i.reference,
        rule_id=i.rule_id,
        rule_version=i.rule_version,
        category=i.category,
        severity=i.severity,
        confidence=i.confidence,
        status=i.status,
        title=i.title,
        summary=i.summary,
        subject_label=i.subject_label,
        owner=_person(owners.get(i.owner_user_id)) if i.owner_user_id else None,
        detected_at=i.detected_at,
        last_evaluated_at=i.last_evaluated_at,
        incident_id=incidents.get(i.id),
    )


@router.get("/insights", response_model=InsightListOut)
async def list_insights(
    ctx: InsRead,
    session: SessionDep,
    status: Annotated[
        Literal[
            "active", "closed", "all", "open", "acknowledged", "actioned", "resolved", "dismissed"
        ],
        Query(),
    ] = "active",
    severity: Annotated[Literal["low", "medium", "high", "critical"] | None, Query()] = None,
    category: Annotated[Literal["inventory", "procurement"] | None, Query()] = None,
    owner: Annotated[Literal["me", "none"] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> InsightListOut:
    page = await service.list_insights(
        session,
        ctx,
        status=status,
        severity=severity,
        category=category,
        owner=owner,
        limit=limit,
        offset=offset,
    )
    owners = await people(
        session, ctx.organisation_id, {i.owner_user_id for i in page.items if i.owner_user_id}
    )
    incidents = await _incident_links(session, ctx, [i.id for i in page.items])
    return InsightListOut(
        items=[_summary(i, owners, incidents) for i in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
        active_by_severity=page.counts,
    )


async def _detail(session: Any, ctx: TenantContext, insight: Insight) -> InsightDetail:
    evidence = await service.evidence_of(session, insight)
    events = await service.events_of(session, insight)
    generation: AIGeneration | None = await service.generation_of(session, insight)
    connections = await service.connections_by_id(
        session, ctx.organisation_id, {e.connection_id for e in evidence if e.connection_id}
    )
    owners = await people(
        session, ctx.organisation_id, {insight.owner_user_id} if insight.owner_user_id else set()
    )
    incidents = await _incident_links(session, ctx, [insight.id])
    base = _summary(insight, owners, incidents)
    explanation = insight.explanation or {}
    return InsightDetail(
        **base.model_dump(),
        metrics=insight.metrics,
        recommendation=insight.recommendation,
        recommended_action=service.describe_recommendation(insight.recommendation),
        assumptions=insight.assumptions,
        limitations=insight.limitations,
        explanation=ExplanationOut(
            what_happened=explanation.get("what_happened", ""),
            why_it_matters=explanation.get("why_it_matters", ""),
            source=insight.explanation_source,
            provider=generation.provider if generation else None,
            model=generation.model if generation else None,
            generated_at=generation.created_at if generation else None,
            pending=insight.explanation_stale,
        ),
        evidence=[_evidence(e, connections) for e in evidence],
        events=[
            InsightEventOut(
                id=e.id,
                kind=e.kind,
                actor_label=e.actor_label,
                details=e.details,
                created_at=e.created_at,
            )
            for e in events
        ],
        closed_at=insight.closed_at,
        close_reason=insight.close_reason,
        suppressed_until=insight.suppressed_until,
        allowed_transitions=sorted(service.TRANSITIONS.get(insight.status, set())),
    )


def _evidence(e: InsightEvidence, connections: dict[UUID, Any]) -> EvidenceOut:
    conn = connections.get(e.connection_id) if e.connection_id else None
    return EvidenceOut(
        id=e.id,
        key=e.key,
        label=e.label,
        value=e.value,
        unit=e.unit,
        source_type=e.source_type,
        source_id=e.source_id,
        source_ref=e.source_ref,
        connection=SourceConnection(id=conn.id, name=conn.name, connector=conn.connector)
        if conn
        else None,
        observed_at=e.observed_at,
        formula=e.formula,
        resolvable=e.source_type in service.SOURCE_MODELS and e.source_id is not None,
    )


@router.get("/insights/{insight_id}", response_model=InsightDetail)
async def get_insight(insight_id: UUID, ctx: InsRead, session: SessionDep) -> InsightDetail:
    insight = await service.get_insight(session, ctx, insight_id)
    return await _detail(session, ctx, insight)


@router.get("/insights/{insight_id}/evidence/{evidence_id}/source")
async def evidence_source(
    insight_id: UUID, evidence_id: UUID, ctx: InsRead, session: SessionDep
) -> dict[str, Any]:
    insight = await service.get_insight(session, ctx, insight_id)
    evidence = await session.get(InsightEvidence, evidence_id)
    if (
        evidence is None
        or evidence.insight_id != insight.id
        or evidence.organisation_id != ctx.organisation_id
    ):
        raise ApiError(404, "not_found", "Evidence not found.")
    return await service.resolve_source(session, ctx, evidence)


@router.post("/insights/{insight_id}/status", response_model=InsightDetail)
async def change_status(
    insight_id: UUID,
    body: StatusChangeRequest,
    ctx: InsManage,
    session: SessionDep,
    meta: MetaDep,
) -> InsightDetail:
    insight = await service.get_insight(session, ctx, insight_id)
    await service.change_status(
        session, ctx, insight, to=body.status, reason=body.reason, meta=meta
    )
    await session.flush()
    return await _detail(session, ctx, insight)


@router.put("/insights/{insight_id}/owner", response_model=InsightDetail)
async def set_owner(
    insight_id: UUID, body: OwnerRequest, ctx: InsManage, session: SessionDep, meta: MetaDep
) -> InsightDetail:
    insight = await service.get_insight(session, ctx, insight_id)
    await service.assign_owner(session, ctx, insight, body.user_id, meta)
    await session.flush()
    return await _detail(session, ctx, insight)


@router.post("/insights/{insight_id}/explain", status_code=202)
async def regenerate_explanation(
    insight_id: UUID,
    ctx: InsManage,
    session: SessionDep,
    request: Request,
    background: BackgroundTasks,
) -> dict[str, str]:
    insight = await service.get_insight(session, ctx, insight_id)
    await service.request_explanation(session, insight)
    background.add_task(explain_insight, runtime(request), ctx.organisation_id, insight.id)
    return {"status": "requested"}


# --- detection and configuration ---------------------------------------------------------------


def _run_out(r: Any) -> DetectionRunOut:
    return DetectionRunOut.model_validate(r, from_attributes=True)


@router.post("/intelligence/run", response_model=DetectionRunOut)
async def run_now(ctx: InsManage, request: Request) -> DetectionRunOut:
    return _run_out(await run_detection(runtime(request), ctx.organisation_id, "manual"))


@router.get("/intelligence/runs", response_model=list[DetectionRunOut])
async def runs(
    ctx: InsRead, session: SessionDep, limit: Annotated[int, Query(ge=1, le=50)] = 10
) -> list[DetectionRunOut]:
    return [_run_out(r) for r in await service.recent_runs(session, ctx, limit)]


def _params(model: Any, values: dict[str, Any]) -> list[DetectorParamOut]:
    schema = model.model_json_schema()
    out = []
    for name, prop in schema.get("properties", {}).items():
        out.append(
            DetectorParamOut(
                name=name,
                description=prop.get("description"),
                type="choice" if "enum" in prop else prop.get("type", "string"),
                default=prop.get("default"),
                value=values.get(name, prop.get("default")),
                minimum=prop.get("minimum"),
                maximum=prop.get("maximum"),
                choices=prop.get("enum"),
            )
        )
    return out


@router.get("/intelligence/detectors", response_model=list[DetectorOut])
async def detectors(ctx: InsRead, session: SessionDep) -> list[DetectorOut]:
    out = []
    for rule_id, det, cfg in await service.list_detectors(session, ctx):
        values = det.params_model.model_validate(cfg.params if cfg else {}).model_dump(mode="json")
        out.append(
            DetectorOut(
                rule_id=rule_id,
                version=det.version,
                name=det.name,
                category=det.category,
                description=det.description,
                enabled=cfg.enabled if cfg else True,
                params=_params(det.params_model, values),
                updated_at=cfg.updated_at if cfg else None,
            )
        )
    return out


@router.put("/intelligence/detectors/{rule_id}", response_model=DetectorOut)
async def update_detector(
    rule_id: str, body: DetectorUpdate, ctx: InsManage, session: SessionDep, meta: MetaDep
) -> DetectorOut:
    cfg = await service.update_detector(
        session, ctx, rule_id, enabled=body.enabled, params=body.params, meta=meta
    )
    det = DETECTORS[rule_id]
    return DetectorOut(
        rule_id=rule_id,
        version=det.version,
        name=det.name,
        category=det.category,
        description=det.description,
        enabled=cfg.enabled,
        params=_params(det.params_model, cfg.params),
        updated_at=cfg.updated_at,
    )


async def _ai_out(session: Any, ctx: TenantContext, request: Request) -> AISettingsOut:
    st = await ai.status(session, ctx.organisation_id, runtime(request).providers)
    return AISettingsOut(
        enabled=st.enabled,
        provider=st.provider,
        provider_available=st.provider_available,
        model=st.model,
        monthly_token_budget=st.monthly_token_budget,
        tokens_used_this_month=st.tokens_used_this_month,
        available_providers=st.available_providers,
        data_shared=DATA_SHARED,
    )


@router.get("/intelligence/ai-settings", response_model=AISettingsOut)
async def get_ai_settings(ctx: InsRead, session: SessionDep, request: Request) -> AISettingsOut:
    return await _ai_out(session, ctx, request)


@router.put("/intelligence/ai-settings", response_model=AISettingsOut)
async def put_ai_settings(
    body: AISettingsUpdate, ctx: OrgManage, session: SessionDep, request: Request, meta: MetaDep
) -> AISettingsOut:
    await ai.update_settings(
        session,
        ctx,
        runtime(request).providers,
        enabled=body.enabled,
        provider=body.provider,
        monthly_token_budget=body.monthly_token_budget,
        meta=meta,
    )
    await session.flush()
    return await _ai_out(session, ctx, request)
