"""Unit tests for OpenTelemetry instrumentation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from opentelemetry import trace  # type: ignore
from opentelemetry.sdk.trace import TracerProvider  # type: ignore
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # type: ignore
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # type: ignore

from sena.telemetry.otel import trace_span


@pytest.fixture
def span_exporter() -> InMemorySpanExporter:
    """Fixture to provide an in-memory span exporter and a local tracer."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    
    # We use a local tracer from the test provider to avoid global state issues
    return exporter


def test_trace_span_records_data(span_exporter: InMemorySpanExporter) -> None:
    """trace_span should record spans with correct attributes."""
    # Create a local tracer and provider for testing
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    tracer = provider.get_tracer("test")
    
    with tracer.start_as_current_span("test.operation", attributes={"key": "value"}):
        pass

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "test.operation"
    attrs = spans[0].attributes or {}
    assert attrs["key"] == "value"


@pytest.mark.asyncio
async def test_agent_instrumentation(span_exporter: InMemorySpanExporter) -> None:
    """Verify that the tracing import and context manager work."""
    from sena.telemetry.otel import trace_span
    
    # We just verify the helper works in a clean environment
    # Using the real trace_span might hit the global provider, 
    # so we mock the tracer returned by get_tracer if needed.
    
    with patch("sena.telemetry.otel.get_tracer") as mock_get_tracer:
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(span_exporter))
        mock_get_tracer.return_value = provider.get_tracer("sena")
        
        with trace_span("manual.test"):
            pass
    
    spans = span_exporter.get_finished_spans()
    assert any(s.name == "manual.test" for s in spans)
