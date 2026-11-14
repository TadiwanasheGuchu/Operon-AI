"""OpenTelemetry tracing and metrics (Phase 7).

Off unless `OPERON_OTEL_ENABLED=true`. Exports over OTLP/HTTP to the standard
`OTEL_EXPORTER_OTLP_ENDPOINT` (an OpenTelemetry Collector, Grafana Cloud, Honeycomb, Datadog, …),
so the backend is a deployment choice. Instruments FastAPI requests, SQLAlchemy queries and
outbound HTTP (integrations, identity providers). Request URLs are recorded without query
strings, and request and response bodies are never recorded.

Business metrics (counters) are recorded whether or not export is on; with no meter provider they
cost nothing.
"""

from typing import Any

from opentelemetry import metrics, trace

from operon.core.config import Settings
from operon.core.logging import get_logger

log = get_logger(__name__)

_meter = metrics.get_meter("operon")

SYNCS = _meter.create_counter(
    "operon.integration.syncs", description="Integration syncs by outcome"
)
INSIGHTS_RAISED = _meter.create_counter("operon.insights.raised", description="Insights raised")
WORKFLOWS = _meter.create_counter(
    "operon.workflows.finished", description="Purchase requests by final status"
)
AGENT_RUNS = _meter.create_counter("operon.agent.runs", description="Assistant and agent runs")
MODEL_TOKENS = _meter.create_counter(
    "operon.model.tokens", unit="{token}", description="Model tokens"
)

_configured = False


def configure_telemetry(settings: Settings, *, app: Any = None, engine: Any = None) -> bool:
    """Set up providers and instrumentation once per process. Returns whether export is on."""
    global _configured
    if not settings.otel_enabled:
        return False
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    if not _configured:
        resource = Resource.create(
            {
                "service.name": settings.service_name,
                "service.version": settings.version,
                "deployment.environment": settings.environment,
            }
        )
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        metrics.set_meter_provider(
            MeterProvider(
                resource=resource,
                metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
            )
        )
        HTTPXClientInstrumentor().instrument()
        _configured = True
    if app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, excluded_urls="api/v1/health/.*")
    if engine is not None:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    log.info("telemetry_enabled", service=settings.service_name)
    return True


def add_trace_ids(_: Any, __: str, event_dict: Any) -> Any:
    """structlog processor: put the current trace and span ids on every log line."""
    span = trace.get_current_span()
    ctx = span.get_span_context() if span else None
    if ctx is not None and ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict
