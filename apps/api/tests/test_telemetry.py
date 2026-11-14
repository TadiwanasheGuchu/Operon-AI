"""Telemetry is opt-in, and logs carry trace ids when there is a trace."""

from opentelemetry.sdk.trace import TracerProvider

from operon.core.config import Settings
from operon.core.telemetry import add_trace_ids, configure_telemetry


def test_disabled_by_default() -> None:
    assert configure_telemetry(Settings(environment="test")) is False


def test_log_lines_carry_trace_and_span_ids() -> None:
    tracer = TracerProvider().get_tracer("test")
    with tracer.start_as_current_span("request") as span:
        event = add_trace_ids(None, "info", {"event": "x"})
        ctx = span.get_span_context()
    assert event["trace_id"] == format(ctx.trace_id, "032x")
    assert event["span_id"] == format(ctx.span_id, "016x")
    assert "trace_id" not in add_trace_ids(None, "info", {"event": "outside"})
