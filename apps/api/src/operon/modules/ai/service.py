"""Which providers exist, whether an organisation uses one, and how much it has spent."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from operon.access.context import Actor, RequestMeta, TenantContext
from operon.core.config import Settings
from operon.core.errors import ApiError
from operon.modules.ai.models import AIGeneration, OrganisationAISettings
from operon.modules.ai.provider import LLMProvider
from operon.modules.audit import service as audit


@dataclass
class ProviderRegistry:
    """Providers configured on this deployment (keys present). Tests inject fakes here."""

    providers: dict[str, LLMProvider] = field(default_factory=dict)
    max_output_tokens: int = 4000

    @classmethod
    def from_settings(cls, settings: Settings) -> "ProviderRegistry":
        providers: dict[str, LLMProvider] = {}
        if settings.anthropic_api_key is not None:
            from operon.modules.ai.anthropic_provider import AnthropicProvider

            providers["anthropic"] = AnthropicProvider(
                api_key=settings.anthropic_api_key.get_secret_value(),
                model=settings.anthropic_model,
                timeout=settings.ai_timeout_seconds,
            )
        if settings.openai_api_key is not None and settings.openai_model:
            from operon.modules.ai.openai_provider import OpenAIProvider

            providers["openai"] = OpenAIProvider(
                api_key=settings.openai_api_key.get_secret_value(),
                model=settings.openai_model,
                timeout=settings.ai_timeout_seconds,
            )
        return cls(providers, settings.ai_max_output_tokens)


@dataclass(frozen=True)
class AIStatus:
    enabled: bool
    provider: str
    provider_available: bool
    model: str | None
    monthly_token_budget: int
    tokens_used_this_month: int
    available_providers: list[str]


async def load_settings(session: AsyncSession, org: UUID) -> OrganisationAISettings:
    row = await session.get(OrganisationAISettings, org)
    return row or OrganisationAISettings(
        organisation_id=org, enabled=False, provider="anthropic", monthly_token_budget=200_000
    )


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def tokens_used_this_month(session: AsyncSession, org: UUID) -> int:
    """Explanations plus assistant and agent runs: one budget for all model use."""
    from operon.modules.agents.models import AgentExecution

    explanations = await session.scalar(
        select(
            func.coalesce(func.sum(AIGeneration.input_tokens + AIGeneration.output_tokens), 0)
        ).where(AIGeneration.organisation_id == org, AIGeneration.created_at >= month_start())
    )
    runs = await session.scalar(
        select(
            func.coalesce(func.sum(AgentExecution.input_tokens + AgentExecution.output_tokens), 0)
        ).where(AgentExecution.organisation_id == org, AgentExecution.started_at >= month_start())
    )
    return int(explanations or 0) + int(runs or 0)


async def status(session: AsyncSession, org: UUID, registry: ProviderRegistry) -> AIStatus:
    cfg = await load_settings(session, org)
    provider = registry.providers.get(cfg.provider)
    return AIStatus(
        enabled=cfg.enabled,
        provider=cfg.provider,
        provider_available=provider is not None,
        model=provider.model if provider else None,
        monthly_token_budget=cfg.monthly_token_budget,
        tokens_used_this_month=await tokens_used_this_month(session, org),
        available_providers=sorted(registry.providers),
    )


async def update_settings(
    session: AsyncSession,
    ctx: TenantContext,
    registry: ProviderRegistry,
    *,
    enabled: bool,
    provider: str,
    monthly_token_budget: int,
    meta: RequestMeta,
) -> None:
    if enabled and provider not in registry.providers:
        raise ApiError(
            409,
            "provider_unavailable",
            "That provider isn't configured on this deployment. Ask your platform administrator "
            "to add its API key, or keep AI explanations off.",
        )
    row = await session.get(OrganisationAISettings, ctx.organisation_id)
    before = None
    if row is None:
        row = OrganisationAISettings(organisation_id=ctx.organisation_id)
        session.add(row)
    else:
        before = {
            "enabled": row.enabled,
            "provider": row.provider,
            "monthly_token_budget": row.monthly_token_budget,
        }
    row.enabled = enabled
    row.provider = provider
    row.monthly_token_budget = monthly_token_budget
    row.updated_by = ctx.user_id
    await audit.record(
        session,
        actor=Actor.user(ctx.user_id, ctx.user_email),
        action="ai.settings_updated",
        meta=meta,
        organisation_id=ctx.organisation_id,
        target_type="organisation",
        target_id=ctx.organisation_id,
        details={
            "before": before,
            "after": {
                "enabled": enabled,
                "provider": provider,
                "monthly_token_budget": monthly_token_budget,
            },
        },
    )
