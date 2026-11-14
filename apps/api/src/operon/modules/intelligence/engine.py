"""Run an organisation's detectors and reconcile insights with what they found.

Each detector runs in its own transaction, so one failing rule never blocks the others. Model
calls happen outside any transaction, and only after the findings are committed.
"""

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from operon.core import telemetry
from operon.core.db import Database, set_rls_context
from operon.core.logging import get_logger
from operon.modules.ai import service as ai
from operon.modules.ai.models import AIGeneration
from operon.modules.ai.provider import ProviderError
from operon.modules.ai.service import ProviderRegistry
from operon.modules.intelligence import explain
from operon.modules.intelligence.detectors.base import DetectionContext, Finding
from operon.modules.intelligence.detectors.registry import DETECTORS
from operon.modules.intelligence.models import (
    ACTIVE_STATUSES,
    SEVERITY_RANK,
    DetectionRun,
    DetectorConfig,
    Insight,
    InsightEvent,
    InsightEvidence,
)
from operon.modules.notifications.service import notify
from operon.modules.permissions.catalogue import Perm
from operon.modules.permissions.service import members_with_permission

log = get_logger(__name__)

SYSTEM = "Operon detection"
EXPLANATIONS_PER_RUN = 25
NOTIFY_SEVERITIES = ("high", "critical")


@dataclass
class IntelligenceRuntime:
    db: Database
    providers: ProviderRegistry


async def next_number(session: AsyncSession, model: Any, org: UUID, key: str) -> int:
    """Per-organisation sequence (INS-0001, INC-0001); serialised by a transaction lock."""
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"{key}:{org}"})
    current = await session.scalar(
        select(func.coalesce(func.max(model.number), 0)).where(model.organisation_id == org)
    )
    return int(current or 0) + 1


async def detector_settings(session: AsyncSession, org: UUID) -> dict[str, tuple[bool, Any]]:
    rows = {
        c.rule_id: c
        for c in await session.scalars(
            select(DetectorConfig).where(DetectorConfig.organisation_id == org)
        )
    }
    out: dict[str, tuple[bool, Any]] = {}
    for rule_id, det in DETECTORS.items():
        cfg = rows.get(rule_id)
        out[rule_id] = (
            cfg.enabled if cfg else True,
            det.params_model.model_validate(cfg.params if cfg else {}),
        )
    return out


async def run_detection(
    rt: IntelligenceRuntime,
    organisation_id: UUID,
    trigger: str,
    *,
    now: datetime | None = None,
) -> DetectionRun:
    now = now or datetime.now(UTC)
    org = organisation_id
    async with rt.db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=org)
        run = DetectionRun(organisation_id=org, trigger=trigger, as_of=now.date(), started_at=now)
        s.add(run)
        await s.flush()
        run_id = run.id
        settings = await detector_settings(s, org)

    ctx = DetectionContext(organisation_id=org, today=now.date(), now=now)
    stats: dict[str, Any] = {}
    failed = False
    for rule_id, (enabled, params) in settings.items():
        if not enabled:
            # Turning a detector off closes what it raised; nothing would keep them current.
            async with rt.db.sessionmaker() as s, s.begin():
                await set_rls_context(s, organisation_id=org)
                stats[rule_id] = {
                    "enabled": False,
                    **await reconcile(
                        s, org, rule_id, [], now, close_reason="The detector was turned off."
                    ),
                }
            continue
        try:
            async with rt.db.sessionmaker() as s, s.begin():
                await set_rls_context(s, organisation_id=org)
                findings = await DETECTORS[rule_id].evaluate(s, ctx, params)
                stats[rule_id] = await reconcile(s, org, rule_id, findings, now)
        except Exception as exc:
            failed = True
            log.exception("detector_failed", rule_id=rule_id, organisation_id=str(org))
            stats[rule_id] = {"error": type(exc).__name__}

    explained = await refresh_explanations(rt, org)

    async with rt.db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=org)
        done = await s.get(DetectionRun, run_id)
        assert done is not None
        done.stats = {**stats, "explanations": explained}
        done.status = "failed" if failed else "succeeded"
        done.error = "One or more detectors failed; see the logs." if failed else None
        done.finished_at = datetime.now(UTC)
    return done


async def reconcile(
    s: AsyncSession,
    org: UUID,
    rule_id: str,
    findings: list[Finding],
    now: datetime,
    *,
    close_reason: str = "The condition was no longer detected.",
) -> dict[str, int]:
    det = DETECTORS[rule_id]
    counts = {"evaluated": len(findings), "raised": 0, "updated": 0, "resolved": 0, "suppressed": 0}
    active = {
        i.subject_key: i
        for i in await s.scalars(
            select(Insight).where(
                Insight.organisation_id == org,
                Insight.rule_id == rule_id,
                Insight.status.in_(ACTIVE_STATUSES),
            )
        )
    }
    seen: set[str] = set()
    notify_ids: list[Insight] = []
    for f in findings:
        seen.add(f.subject_key)
        existing = active.get(f.subject_key)
        if existing is not None:
            previous_severity = existing.severity
            if await _update(s, existing, f, det.version):
                counts["updated"] += 1
                if (
                    f.severity in NOTIFY_SEVERITIES
                    and SEVERITY_RANK[f.severity] > SEVERITY_RANK[previous_severity]
                ):
                    notify_ids.append(existing)
            existing.last_evaluated_at = now
            continue
        if await _suppressed(s, org, rule_id, f, now):
            counts["suppressed"] += 1
            continue
        insight = Insight(
            organisation_id=org,
            number=await next_number(s, Insight, org, "insight-number"),
            rule_id=rule_id,
            rule_version=det.version,
            category=det.category,
            subject_type=f.subject_type,
            subject_key=f.subject_key,
            detected_at=now,
            last_evaluated_at=now,
            status="open",
        )
        _apply(insight, f)
        s.add(insight)
        await s.flush()
        await _replace_evidence(s, insight, f, delete_first=False)
        s.add(insight_event(insight, "detected", {"severity": f.severity, "metrics": f.metrics}))
        counts["raised"] += 1
        telemetry.INSIGHTS_RAISED.add(1, {"rule": rule_id, "severity": f.severity})
        if f.severity in NOTIFY_SEVERITIES:
            notify_ids.append(insight)
    await s.flush()

    for key, insight in active.items():
        if key in seen:
            continue
        insight.status = "resolved"
        insight.closed_at = now
        insight.close_reason = close_reason
        s.add(insight_event(insight, "resolved", {"automatic": True}))
        counts["resolved"] += 1

    if notify_ids:
        recipients = await members_with_permission(s, org, Perm.INSIGHTS_MANAGE)
        for insight in notify_ids:
            await notify(
                s,
                organisation_id=org,
                user_ids={*recipients, *([insight.owner_user_id] if insight.owner_user_id else [])},
                kind="insight",
                title=f"{insight.reference}: {insight.title}"[:200],
                body=insight.summary[:500],
                link=f"/intelligence/{insight.id}",
            )
    return counts


def _apply(insight: Insight, f: Finding) -> None:
    insight.subject_label = f.subject_label[:300]
    insight.severity = f.severity
    insight.confidence = f.confidence
    insight.title = f.title[:300]
    insight.summary = f.summary
    insight.metrics = f.metrics
    insight.recommendation = f.recommendation
    insight.assumptions = f.assumptions
    insight.limitations = f.limitations
    insight.explanation = f.explanation
    insight.explanation_source = "template"
    insight.explanation_generation_id = None
    insight.explanation_stale = True


async def _update(s: AsyncSession, insight: Insight, f: Finding, version: int) -> bool:
    if (
        insight.metrics == f.metrics
        and insight.title == f.title[:300]
        and insight.subject_label == f.subject_label[:300]
        and insight.severity == f.severity
        and insight.confidence == f.confidence
        and insight.recommendation == f.recommendation
    ):
        return False
    before = {"severity": insight.severity, "metrics": insight.metrics}
    if insight.severity != f.severity:
        s.add(
            insight_event(insight, "severity_changed", {"from": insight.severity, "to": f.severity})
        )
    insight.rule_version = version
    _apply(insight, f)
    await _replace_evidence(s, insight, f, delete_first=True)
    s.add(insight_event(insight, "updated", {"before": before, "after": {"metrics": f.metrics}}))
    return True


async def _suppressed(s: AsyncSession, org: UUID, rule_id: str, f: Finding, now: datetime) -> bool:
    dismissed = await s.scalar(
        select(Insight)
        .where(
            Insight.organisation_id == org,
            Insight.rule_id == rule_id,
            Insight.subject_key == f.subject_key,
            Insight.status == "dismissed",
            Insight.suppressed_until > now,
        )
        .order_by(Insight.closed_at.desc())
        .limit(1)
    )
    # A dismissal holds only while things don't get worse.
    return dismissed is not None and SEVERITY_RANK[f.severity] <= SEVERITY_RANK[dismissed.severity]


async def _replace_evidence(
    s: AsyncSession, insight: Insight, f: Finding, *, delete_first: bool
) -> None:
    if delete_first:
        await s.execute(delete(InsightEvidence).where(InsightEvidence.insight_id == insight.id))
    for pos, e in enumerate(f.evidence):
        s.add(
            InsightEvidence(
                organisation_id=insight.organisation_id,
                insight_id=insight.id,
                position=pos,
                key=e.key,
                label=e.label[:200],
                value=e.value[:200],
                numeric_value=e.numeric,
                unit=e.unit,
                source_type=e.source_type,
                source_id=e.source_id,
                source_ref=e.source_ref[:300] if e.source_ref else None,
                connection_id=e.connection_id,
                observed_at=e.observed_at,
                formula=e.formula[:200] if e.formula else None,
            )
        )


def insight_event(
    insight: Insight,
    kind: str,
    details: dict[str, Any],
    *,
    user_id: UUID | None = None,
    label: str = SYSTEM,
) -> InsightEvent:
    return InsightEvent(
        organisation_id=insight.organisation_id,
        insight_id=insight.id,
        kind=kind,
        actor_user_id=user_id,
        actor_label=label,
        details=details,
    )


# --- explanations -------------------------------------------------------------------------------


async def refresh_explanations(rt: IntelligenceRuntime, org: UUID) -> dict[str, int]:
    """Replace template text with validated model text where the organisation allows it."""
    counts = {"accepted": 0, "rejected": 0, "failed": 0, "skipped": 0, "template": 0}
    async with rt.db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=org)
        stale = list(
            await s.scalars(
                select(Insight.id)
                .where(
                    Insight.organisation_id == org,
                    Insight.explanation_stale.is_(True),
                    Insight.status.in_(ACTIVE_STATUSES),
                )
                .order_by(Insight.detected_at.desc())
                .limit(EXPLANATIONS_PER_RUN)
            )
        )
    for insight_id in stale:
        outcome = await explain_insight(rt, org, insight_id)
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


async def explain_insight(rt: IntelligenceRuntime, org: UUID, insight_id: UUID) -> str:
    """Returns "accepted", "rejected", "failed", "skipped" or "template"."""
    async with rt.db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=org)
        insight = await s.get(Insight, insight_id)
        if insight is None:
            return "skipped"
        cfg = await ai.load_settings(s, org)
        provider = rt.providers.providers.get(cfg.provider) if cfg.enabled else None
        if provider is None:
            insight.explanation_stale = False
            return "template"
        if await ai.tokens_used_this_month(s, org) >= cfg.monthly_token_budget:
            s.add(
                AIGeneration(
                    organisation_id=org,
                    purpose="insight_explanation",
                    subject_type="insight",
                    subject_id=insight.id,
                    provider=provider.name,
                    model=provider.model,
                    prompt_version=explain.PROMPT_VERSION,
                    status="skipped",
                    error="Monthly token budget reached.",
                )
            )
            insight.explanation_stale = False
            return "skipped"
        evidence = list(
            await s.scalars(
                select(InsightEvidence)
                .where(InsightEvidence.insight_id == insight.id)
                .order_by(InsightEvidence.position)
            )
        )
        payload = explain.build_payload(insight, evidence)
        fingerprint = dict(insight.metrics)

    started = time.monotonic()
    status, output, problems, error = "failed", None, [], None
    model, tokens_in, tokens_out = provider.model, 0, 0
    try:
        result = await provider.generate(
            system=explain.SYSTEM_PROMPT,
            user=explain.user_message(payload),
            schema=explain.Explanation,
            max_output_tokens=rt.providers.max_output_tokens,
        )
        model, tokens_in, tokens_out = result.model, result.input_tokens, result.output_tokens
        if result.output is None:
            status = "refused" if result.outcome == "refused" else "failed"
            error = f"No usable output ({result.outcome})"
        else:
            output = result.output
            problems = explain.validate(output, payload)
            status = "rejected" if problems else "accepted"
    except ProviderError as exc:
        error = str(exc)[:500]
        log.warning("ai_provider_error", provider=provider.name, error=error)
    except Exception as exc:  # a provider bug must not break detection
        error = type(exc).__name__
        log.exception("ai_provider_crashed", provider=provider.name)
    latency = int((time.monotonic() - started) * 1000)

    async with rt.db.sessionmaker() as s, s.begin():
        await set_rls_context(s, organisation_id=org)
        generation = AIGeneration(
            organisation_id=org,
            purpose="insight_explanation",
            subject_type="insight",
            subject_id=insight_id,
            provider=provider.name,
            model=model[:100],
            prompt_version=explain.PROMPT_VERSION,
            status=status,
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            latency_ms=latency,
            output=output.model_dump() if output else None,
            problems=problems,
            error=error,
        )
        s.add(generation)
        await s.flush()
        insight = await s.get(Insight, insight_id, with_for_update=True)
        if insight is None:
            return status
        # Only apply if the numbers didn't change while the model was writing.
        if status == "accepted" and output is not None and insight.metrics == fingerprint:
            insight.explanation = output.model_dump()
            insight.explanation_source = "model"
            insight.explanation_generation_id = generation.id
            s.add(
                insight_event(
                    insight, "explained", {"generation_id": str(generation.id), "model": model}
                )
            )
        if insight.metrics == fingerprint:
            insight.explanation_stale = False
    return status


def suppress_until(now: datetime, days: int = 7) -> datetime:
    return now + timedelta(days=days)
