"""The controlled tool loop shared by the assistant and agents (plan §6.4, ADR 0014).

Guarantees enforced here, in code, whatever the model asks for:
- only tools offered for this run can execute (anything else is denied and logged);
- tool input is validated against the tool's schema before it runs;
- the run stops at its step, tool-call, token and wall-clock limits, and at the organisation's
  monthly token budget;
- every model turn and tool call is written to `agent_execution_steps` as it happens.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from operon.access.context import TenantContext
from operon.core import telemetry
from operon.core.db import Database, set_rls_context
from operon.core.errors import ApiError
from operon.core.logging import get_logger
from operon.modules.agents.models import AgentExecution, AgentExecutionStep
from operon.modules.agents.tools import Citation, Tool, ToolContext
from operon.modules.ai import service as ai
from operon.modules.ai.provider import ProviderError, ToolLoopProvider, ToolResult, ToolSpec
from operon.modules.ai.service import ProviderRegistry

log = get_logger(__name__)

MAX_OUTPUT_CHARS = 12_000
MAX_LOGGED_CHARS = 8_000


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_steps: int = Field(8, ge=1, le=30, description="Model turns per run.")
    max_tool_calls: int = Field(20, ge=1, le=100)
    max_tokens: int = Field(80_000, ge=1_000, le=2_000_000, description="Tokens per run.")
    max_seconds: int = Field(180, ge=10, le=1_800, description="Wall-clock time per run.")


@dataclass
class RunSpec:
    kind: str  # "assistant" | "agent"
    trigger: str  # "chat" | "manual" | "schedule"
    system: str
    prompt_version: str
    history: list[tuple[str, str]]
    user_text: str
    tools: list[Tool]
    actor: TenantContext
    limits: Limits
    triggered_by: UUID | None
    agent_id: UUID | None = None
    agent_version: int | None = None
    agent_name: str | None = None
    conversation_id: UUID | None = None
    state: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    execution_id: UUID
    status: str
    text: str | None
    stop_reason: str | None
    citations: dict[str, Citation]
    # Everything the tools returned, to check the answer's figures against.
    tool_text: str


def choose_provider(settings: Any, registry: ProviderRegistry) -> ToolLoopProvider:
    if not settings.enabled:
        raise ApiError(
            409,
            "ai_disabled",
            "AI is turned off for this organisation. An administrator can turn it on under "
            "Intelligence → Detectors and AI.",
        )
    provider = registry.providers.get(settings.provider)
    if provider is None or not hasattr(provider, "converse"):
        raise ApiError(
            409,
            "provider_unavailable",
            "No model provider is configured on this deployment, so the assistant and agents "
            "can't run.",
        )
    return cast(ToolLoopProvider, provider)


async def preflight(db: Database, registry: ProviderRegistry, org: UUID) -> ToolLoopProvider:
    async with db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=org)
        settings = await ai.load_settings(s, org)
        provider = choose_provider(settings, registry)
        if await ai.tokens_used_this_month(s, org) >= settings.monthly_token_budget:
            raise ApiError(
                409,
                "budget_exhausted",
                "This month's AI token budget is used up. An administrator can raise it.",
            )
    return provider


def _clip(value: Any, limit: int) -> Any:
    text = json.dumps(value, default=str, ensure_ascii=False)
    if len(text) <= limit:
        return value
    return {"truncated": True, "preview": text[:limit]}


class _Log:
    def __init__(self, db: Database, org: UUID, execution_id: UUID) -> None:
        self.db, self.org, self.execution_id, self.position = db, org, execution_id, 0

    async def add(self, kind: str, **kw: Any) -> None:
        self.position += 1
        async with self.db.sessionmaker() as s, s.begin():
            await set_rls_context(s, organisation_id=self.org)
            s.add(
                AgentExecutionStep(
                    organisation_id=self.org,
                    execution_id=self.execution_id,
                    position=self.position,
                    kind=kind,
                    **kw,
                )
            )


async def run(db: Database, registry: ProviderRegistry, spec: RunSpec) -> RunResult:
    org = spec.actor.organisation_id
    provider = await preflight(db, registry, org)
    offered = {t.name: t for t in spec.tools}
    async with db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=org)
        execution = AgentExecution(
            organisation_id=org,
            kind=spec.kind,
            agent_id=spec.agent_id,
            agent_version=spec.agent_version,
            conversation_id=spec.conversation_id,
            trigger=spec.trigger,
            triggered_by=spec.triggered_by,
            provider=provider.name,
            model=provider.model,
            prompt_version=spec.prompt_version,
            tools_offered=sorted(offered),
        )
        s.add(execution)
        await s.flush()
        execution_id = execution.id
    steplog = _Log(db, org, execution_id)
    ctx = ToolContext(
        db=db,
        actor=spec.actor,
        execution_id=execution_id,
        agent_name=spec.agent_name,
        state=spec.state,
    )
    tool_specs = [ToolSpec(t.name, t.description, t.schema()) for t in spec.tools]
    transcript = provider.start(spec.history, spec.user_text)
    citations: dict[str, Citation] = {}
    tool_texts: list[str] = []
    totals = {"in": 0, "out": 0, "steps": 0, "calls": 0}
    started = time.monotonic()
    status, stop, text, error, model = "succeeded", "end", None, None, provider.model

    while True:
        elapsed = time.monotonic() - started
        limit = (
            "max_steps"
            if totals["steps"] >= spec.limits.max_steps
            else "max_tokens"
            if totals["in"] + totals["out"] >= spec.limits.max_tokens
            else "max_seconds"
            if elapsed >= spec.limits.max_seconds
            else None
        )
        if limit:
            status, stop = "limited", limit
            await steplog.add("limit", message=f"Stopped: {limit.replace('_', ' ')} reached.")
            break
        totals["steps"] += 1
        t0 = time.monotonic()
        try:
            turn = await asyncio.wait_for(
                provider.converse(
                    system=spec.system,
                    transcript=transcript,
                    tools=tool_specs,
                    max_output_tokens=registry.max_output_tokens,
                ),
                timeout=max(1.0, spec.limits.max_seconds - elapsed),
            )
        except TimeoutError:
            status, stop = "limited", "max_seconds"
            await steplog.add("limit", message="Stopped: the model didn't answer in time.")
            break
        except ProviderError as exc:
            status, stop, error = "failed", "provider_error", str(exc)[:500]
            await steplog.add("error", message=error)
            break
        except Exception as exc:  # a provider bug must still end the run cleanly
            log.exception("model_turn_crashed", execution_id=str(execution_id))
            status, stop, error = "failed", "provider_error", type(exc).__name__
            await steplog.add("error", message="The model call failed unexpectedly.")
            break
        latency = int((time.monotonic() - t0) * 1000)
        model = turn.model
        totals["in"] += turn.input_tokens
        totals["out"] += turn.output_tokens
        await steplog.add(
            "model_turn",
            message=(turn.text or "")[:2000] or None,
            output={
                "outcome": turn.outcome,
                "tool_calls": [{"name": c.name, "id": c.id} for c in turn.tool_calls],
                "model": turn.model,
            },
            input_tokens=turn.input_tokens,
            output_tokens=turn.output_tokens,
            latency_ms=latency,
        )
        if turn.outcome == "refused":
            status, stop = "refused", "refused"
            await steplog.add("refused", message=turn.detail or "The model declined.")
            break
        if turn.outcome == "truncated":
            status, stop, text = "limited", "max_output_tokens", turn.text
            await steplog.add("limit", message="Stopped: the answer hit the output limit.")
            break
        if turn.outcome == "end":
            text = turn.text
            await steplog.add("final", message=(text or "")[:4000])
            break

        results: list[ToolResult] = []
        for call in turn.tool_calls:
            totals["calls"] += 1
            if totals["calls"] > spec.limits.max_tool_calls:
                results.append(ToolResult(call.id, "Error: tool call limit reached.", True))
                await steplog.add("limit", tool_name=call.name, message="Tool call limit reached.")
                continue
            tool = offered.get(call.name)
            if tool is None:
                results.append(
                    ToolResult(call.id, f"Error: the tool '{call.name}' isn't available.", True)
                )
                await steplog.add(
                    "tool_denied",
                    tool_name=call.name[:60],
                    input=_clip(call.input, MAX_LOGGED_CHARS),
                    message="Not in this run's allowlist.",
                )
                continue
            try:
                parsed = tool.input_model.model_validate(call.input)
            except ValidationError as exc:
                msg = "; ".join(
                    f"{'.'.join(str(p) for p in e['loc']) or 'input'}: {e['msg']}"
                    for e in exc.errors()
                )[:500]
                results.append(ToolResult(call.id, f"Error: invalid input. {msg}", True))
                await steplog.add(
                    "tool_error",
                    tool_name=tool.name,
                    input=_clip(call.input, MAX_LOGGED_CHARS),
                    message=f"Invalid input: {msg}",
                )
                continue
            t0 = time.monotonic()
            try:
                out = await tool.handler(ctx, parsed)
            except ApiError as exc:
                results.append(ToolResult(call.id, f"Error: {exc.message}", True))
                await steplog.add(
                    "tool_error",
                    tool_name=tool.name,
                    input=parsed.model_dump(mode="json"),
                    message=exc.message,
                    latency_ms=int((time.monotonic() - t0) * 1000),
                )
                continue
            except Exception:
                log.exception("tool_crashed", tool=tool.name, execution_id=str(execution_id))
                results.append(ToolResult(call.id, "Error: the tool failed unexpectedly.", True))
                await steplog.add(
                    "tool_error",
                    tool_name=tool.name,
                    input=parsed.model_dump(mode="json"),
                    message="The tool failed unexpectedly.",
                )
                continue
            payload = json.dumps(out.data, default=str, ensure_ascii=False)
            if len(payload) > MAX_OUTPUT_CHARS:
                payload = payload[:MAX_OUTPUT_CHARS] + " …(truncated)"
            tool_texts.append(payload)
            for c in out.citations:
                citations[c.ref] = c
            results.append(ToolResult(call.id, payload))
            await steplog.add(
                "tool_call",
                tool_name=tool.name,
                input=parsed.model_dump(mode="json"),
                output=_clip(
                    {"data": out.data, "refs": [c.ref for c in out.citations]}, MAX_LOGGED_CHARS
                ),
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
        provider.extend(transcript, turn, results)

    async with db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=org)
        e = await s.get(AgentExecution, execution_id)
        assert e is not None
        e.status = status
        e.stop_reason = stop
        e.error = error
        e.model = model[:100]
        e.steps = totals["steps"]
        e.tool_calls = totals["calls"]
        e.input_tokens = totals["in"]
        e.output_tokens = totals["out"]
        e.summary = text[:8000] if text else None
        e.finished_at = datetime.now(UTC)
    telemetry.AGENT_RUNS.add(1, {"kind": spec.kind, "status": status})
    telemetry.MODEL_TOKENS.add(
        totals["in"] + totals["out"], {"kind": spec.kind, "provider": provider.name}
    )
    return RunResult(execution_id, status, text, stop, citations, "\n".join(tool_texts))
