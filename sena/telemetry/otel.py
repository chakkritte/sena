"""OpenTelemetry instrumentation for tracing agent workflows."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from opentelemetry import trace  # type: ignore
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter  # type: ignore
from opentelemetry.sdk.resources import Resource  # type: ignore
from opentelemetry.sdk.trace import TracerProvider  # type: ignore
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter  # type: ignore

if TYPE_CHECKING:
    from sena.config.settings import SenaConfig

_TRACER_NAME = "sena"


def setup_telemetry(config: SenaConfig) -> None:
    """Initialize the global OpenTelemetry TracerProvider."""
    resource = Resource.create(
        {
            "service.name": "sena",
            "service.version": "0.1.1",
        }
    )

    provider = TracerProvider(resource=resource)

    # Export to OTLP if endpoint is provided, otherwise fallback to console for dev
    if config.otel_endpoint:
        otlp_exporter = OTLPSpanExporter(endpoint=config.otel_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    else:
        # Default to console exporter in development if no endpoint is configured
        console_exporter = ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(console_exporter))

    trace.set_tracer_provider(provider)


def get_tracer() -> trace.Tracer:
    """Get the global sena tracer."""
    return trace.get_tracer(_TRACER_NAME)


@contextlib.contextmanager
def trace_span(
    name: str,
    attributes: dict[str, Any] | None = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
) -> Iterator[trace.Span]:
    """Context manager for creating a span with optional attributes."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name, kind=kind, attributes=attributes) as span:
        yield span
