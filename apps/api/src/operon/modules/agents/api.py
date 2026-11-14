from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status
from pydantic import BaseModel, Field

from operon.access.context import TenantContext
from operon.access.dependencies import MetaDep, require_permission
from operon.core import usage_limits as usage
from operon.core.deps import DatabaseDep, SessionDep
from operon.core.errors import ApiError
from operon.modules.agents import service
from operon.modules.agents.models import AgentExecution, AgentExecutionStep, ConversationMessage
from operon.modules.agents.runner import choose_provider
from operon.modules.agents.tools import READ_TOOLS, TOOLS, permitted
from operon.modules.ai import service as ai
from operon.modules.ai.service import ProviderRegistry
from operon.modules.organisations.service import people
from operon.modules.permissions.catalogue import Perm

router = APIRouter(tags=["assistant and agents"])

Assistant = Annotated[TenantContext, Depends(require_permission(Perm.ASSISTANT_USE))]
AgentsRead = Annotated[TenantContext, Depends(require_permission(Perm.AGENTS_READ))]
AgentsRun = Annotated[TenantContext, Depends(require_permission(Perm.AGENTS_RUN))]
AgentsManage = Annotated[TenantContext, Depends(require_permission(Perm.AGENTS_MANAGE))]


def registry(request: Request) -> ProviderRegistry:
    r: ProviderRegistry = request.app.state.intelligence.providers
    return r


# --- schemas ---------------------------------------------------------------------------------


class CitationOut(BaseModel):
    ref: str
    label: str
    kind: str
    href: str | None


class MessageOut(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    citations: list[CitationOut]
    checked: bool
    problems: list[str]
    execution_id: UUID | None
    created_at: datetime


class ConversationOut(BaseModel):
    id: UUID
    title: str
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    conversation_id: UUID | None = None


class AskResponse(BaseModel):
    conversation_id: UUID
    message: MessageOut


class Availability(BaseModel):
    available: bool
    reason: str | None
    provider: str | None
    model: str | None
    tools: list[str]


class StepOut(BaseModel):
    position: int
    kind: str
    tool_name: str | None
    input: dict[str, Any] | None
    output: dict[str, Any] | None
    message: str | None
    input_tokens: int
    output_tokens: int
    latency_ms: int
    created_at: datetime


class RunOut(BaseModel):
    id: UUID
    kind: str
    trigger: str
    status: str
    agent_version: int | None
    provider: str
    model: str
    prompt_version: str
    tools_offered: list[str]
    steps: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    summary: str | None
    stop_reason: str | None
    error: str | None
    started_at: datetime
    finished_at: datetime | None
    triggered_by_name: str | None = None


class RunDetail(RunOut):
    log: list[StepOut]


class ToolOut(BaseModel):
    name: str
    description: str
    permission: str
    writes: bool
    enabled: bool
    # Whether the member the agent acts for holds the permission (else it's never offered).
    run_as_permitted: bool | None


class AgentConfigOut(BaseModel):
    key: str
    name: str
    enabled: bool
    schedule: Literal["off", "daily"]
    next_run_at: datetime | None
    run_as_user_id: UUID | None
    run_as_name: str | None
    current_version: int
    params: dict[str, Any]
    tools: list[ToolOut]
    availability: Availability


class AgentConfigUpdate(BaseModel):
    enabled: bool
    schedule: Literal["off", "daily"]
    run_as_user_id: UUID | None
    params: dict[str, Any]
    tools: dict[str, bool]


def _msg(m: ConversationMessage) -> MessageOut:
    return MessageOut(
        id=m.id,
        role=m.role,
        content=m.content,
        citations=[CitationOut(**c) for c in m.citations],
        checked=m.checked,
        problems=m.problems,
        execution_id=m.execution_id,
        created_at=m.created_at,
    )


def _run(e: AgentExecution, names: dict[UUID, str] | None = None) -> RunOut:
    return RunOut(
        **{k: getattr(e, k) for k in RunOut.model_fields if k not in ("triggered_by_name",)},
        triggered_by_name=(names or {}).get(e.triggered_by) if e.triggered_by else None,
    )


async def _availability(
    session: Any, ctx: TenantContext, reg: ProviderRegistry, tools: list[str]
) -> Availability:
    settings = await ai.load_settings(session, ctx.organisation_id)
    try:
        provider = choose_provider(settings, reg)
    except ApiError as exc:
        return Availability(
            available=False, reason=exc.message, provider=None, model=None, tools=tools
        )
    if (
        await ai.tokens_used_this_month(session, ctx.organisation_id)
        >= settings.monthly_token_budget
    ):
        return Availability(
            available=False,
            reason="This month's AI token budget is used up.",
            provider=provider.name,
            model=provider.model,
            tools=tools,
        )
    return Availability(
        available=True, reason=None, provider=provider.name, model=provider.model, tools=tools
    )


# --- assistant -------------------------------------------------------------------------------


@router.get("/assistant/status", response_model=Availability)
async def assistant_status(ctx: Assistant, session: SessionDep, request: Request) -> Availability:
    tools = [t.name for t in permitted(READ_TOOLS, ctx)]
    return await _availability(session, ctx, registry(request), tools)


@router.post("/assistant/messages", response_model=AskResponse)
async def ask(
    body: AskRequest, ctx: Assistant, db: DatabaseDep, request: Request, meta: MetaDep
) -> AskResponse:
    await usage.hit(request, usage.ASSISTANT_PER_USER, ctx.user_id)
    await usage.hit(request, usage.ASSISTANT_PER_ORG, ctx.organisation_id)
    answer = await service.ask(
        db,
        registry(request),
        ctx,
        conversation_id=body.conversation_id,
        question=body.question,
        meta=meta,
    )
    return AskResponse(conversation_id=answer.conversation_id, message=_msg(answer.message))


@router.get("/assistant/conversations", response_model=list[ConversationOut])
async def conversations(ctx: Assistant, session: SessionDep) -> list[ConversationOut]:
    return [
        ConversationOut(id=c.id, title=c.title, updated_at=c.updated_at)
        for c in await service.list_conversations(session, ctx)
    ]


@router.get("/assistant/conversations/{conversation_id}", response_model=ConversationDetail)
async def conversation(
    conversation_id: UUID, ctx: Assistant, session: SessionDep
) -> ConversationDetail:
    conv, msgs = await service.get_conversation(session, ctx, conversation_id)
    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        updated_at=conv.updated_at,
        messages=[_msg(m) for m in msgs],
    )


# --- agents ----------------------------------------------------------------------------------


async def _config(session: Any, ctx: TenantContext, reg: ProviderRegistry) -> AgentConfigOut:
    agent, version = await service.ensure_agent(session, ctx.organisation_id)
    settings = await service.tool_settings(session, agent)
    member = (
        await service.member_context(session, ctx.organisation_id, agent.run_as_user_id)
        if agent.run_as_user_id
        else None
    )
    names = await people(
        session, ctx.organisation_id, {agent.run_as_user_id} if agent.run_as_user_id else set()
    )
    capped = member.permissions & service.AGENT_CEILING if member else None
    return AgentConfigOut(
        key=agent.key,
        name=agent.name,
        enabled=agent.enabled,
        schedule=agent.schedule,
        next_run_at=agent.next_run_at,
        run_as_user_id=agent.run_as_user_id,
        run_as_name=names[agent.run_as_user_id].full_name
        if agent.run_as_user_id in names
        else None,
        current_version=agent.current_version,
        params=version.params,
        tools=[
            ToolOut(
                name=t.name,
                description=t.description,
                permission=t.permission,
                writes=t.writes,
                enabled=settings.get(t.name, False),
                run_as_permitted=(t.permission in capped) if capped is not None else None,
            )
            for t in TOOLS.values()
        ],
        availability=await _availability(
            session, ctx, reg, [n for n, on in settings.items() if on]
        ),
    )


@router.get("/agents/inventory-replenishment", response_model=AgentConfigOut)
async def get_agent(ctx: AgentsRead, session: SessionDep, request: Request) -> AgentConfigOut:
    return await _config(session, ctx, registry(request))


@router.put("/agents/inventory-replenishment", response_model=AgentConfigOut)
async def put_agent(
    body: AgentConfigUpdate,
    ctx: AgentsManage,
    session: SessionDep,
    request: Request,
    meta: MetaDep,
) -> AgentConfigOut:
    await service.update_agent(
        session,
        ctx,
        enabled=body.enabled,
        schedule=body.schedule,
        run_as_user_id=body.run_as_user_id,
        params=body.params,
        tools=body.tools,
        meta=meta,
    )
    return await _config(session, ctx, registry(request))


@router.post("/agents/inventory-replenishment/runs", status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    ctx: AgentsRun, db: DatabaseDep, request: Request, background: BackgroundTasks
) -> dict[str, str]:
    reg = registry(request)
    await usage.hit(request, usage.AGENT_RUNS_PER_ORG, ctx.organisation_id)
    # Validate now so the caller sees why a run can't start; run after the response.
    prepared = await service.prepare_run(
        db, reg, ctx.organisation_id, trigger="manual", triggered_by=ctx.user_id
    )
    background.add_task(service.execute_run, db, reg, prepared)
    return {"status": "started"}


@router.get("/agents/runs", response_model=list[RunOut])
async def runs(
    ctx: AgentsRead, session: SessionDep, limit: Annotated[int, Query(ge=1, le=50)] = 20
) -> list[RunOut]:
    items = await service.executions(session, ctx, kind="agent", limit=limit)
    ppl = await people(
        session, ctx.organisation_id, {e.triggered_by for e in items if e.triggered_by}
    )
    return [_run(e, {k: v.full_name for k, v in ppl.items()}) for e in items]


@router.get("/agents/runs/{run_id}", response_model=RunDetail)
async def run_detail(run_id: UUID, ctx: Assistant, session: SessionDep) -> RunDetail:
    e, steps = await service.execution_detail(session, ctx, run_id)
    if e.kind == "agent" and not ctx.has(Perm.AGENTS_READ):
        raise ApiError(404, "not_found", "Run not found.")
    ppl = await people(session, ctx.organisation_id, {e.triggered_by} if e.triggered_by else set())
    return RunDetail(
        **_run(e, {k: v.full_name for k, v in ppl.items()}).model_dump(),
        log=[_step(s) for s in steps],
    )


def _step(s: AgentExecutionStep) -> StepOut:
    return StepOut(
        position=s.position,
        kind=s.kind,
        tool_name=s.tool_name,
        input=s.input,
        output=s.output,
        message=s.message,
        input_tokens=s.input_tokens,
        output_tokens=s.output_tokens,
        latency_ms=s.latency_ms,
        created_at=s.created_at,
    )
