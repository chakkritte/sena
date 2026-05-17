"""OpenTelemetry instrumentation for tracing agent workflows."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

if TYPE_CHECKING:
    from carbonclaw.config.settings import CarbonClawConfig

from carbonclaw import __version__
import os

_TRACER_NAME = "carbonclaw"


def setup_telemetry(config: CarbonClawConfig) -> None:
    """Initialize the global OpenTelemetry TracerProvider."""
    resource = Resource.create(
        {
            "service.name": "carbonclaw",
            "service.version": __version__,
            "deployment.environment": os.environ.get("CARBONCLAW_ENV", "production"),
            "host.name": os.uname().nodename,
        }
    )

    provider = TracerProvider(resource=resource)

    if config.otel_endpoint:
        try:
            otlp_exporter = OTLPSpanExporter(endpoint=config.otel_endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        except Exception:
            # Silent fail to prevent crash in case of network issues
            pass

    trace.set_tracer_provider(provider)


def get_tracer() -> trace.Tracer:
    """Get the global carbonclaw tracer."""
    return trace.get_tracer(_TRACER_NAME, __version__)


@contextlib.contextmanager
def trace_span(
    name: str,
    attributes: dict[str, Any] | None = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
) -> Iterator[trace.Span]:
    """Context manager for creating a span with automated standard attributes."""
    tracer = get_tracer()
    
    attrs = attributes or {}
    if "project" not in attrs:
        attrs["project"] = os.path.basename(os.getcwd())
        
    with tracer.start_as_current_span(name, kind=kind, attributes=attrs) as span:
        yield span


def record_usage_to_span(span: trace.Span, prompt_tokens: int, completion_tokens: int, carbon_kg: float = 0.0) -> None:
    """Helper to record LLM usage metrics to the current span."""
    if not span or not span.is_recording():
        return
    span.set_attribute("llm.usage.prompt_tokens", prompt_tokens)
    span.set_attribute("llm.usage.completion_tokens", completion_tokens)
    span.set_attribute("llm.usage.total_tokens", prompt_tokens + completion_tokens)
    if carbon_kg > 0:
        span.set_attribute("sustainability.carbon_kg", carbon_kg)
