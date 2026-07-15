"""
OpenTelemetry setup for the digest agent — exports traces to Honeycomb via OTLP.

Configure via environment variables (see .env.example). If OTEL_EXPORTER_OTLP_HEADERS
is unset, HONEYCOMB_API_KEY is used to build the x-honeycomb-team header.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "signal-news-digest")
TRACER_NAME = "signal-news-agent"

_initialized = False


def _build_otlp_headers() -> dict[str, str]:
    explicit = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
    if explicit:
        headers: dict[str, str] = {}
        for part in explicit.split(","):
            if "=" in part:
                key, value = part.split("=", 1)
                headers[key.strip()] = value.strip()
        return headers

    api_key = os.getenv("HONEYCOMB_API_KEY")
    if api_key:
        return {"x-honeycomb-team": api_key}

    return {}


def init_telemetry() -> None:
    """Initialize tracing and auto-instrument outbound HTTP (Anthropic SDK uses httpx)."""
    global _initialized
    if _initialized:
        return

    headers = _build_otlp_headers()
    if not headers.get("x-honeycomb-team"):
        print("[telemetry] HONEYCOMB_API_KEY / OTEL_EXPORTER_OTLP_HEADERS not set — tracing disabled")
        _initialized = True
        return

    endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://api.honeycomb.io") + "/v1/traces",
    )

    resource = Resource.create(
        {
            "service.name": SERVICE_NAME,
            "service.version": os.getenv("OTEL_SERVICE_VERSION", "0.1.0"),
            "deployment.environment": os.getenv("DEPLOYMENT_ENVIRONMENT", "production"),
        }
    )

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    HTTPXClientInstrumentor().instrument()

    _initialized = True


def get_tracer() -> Tracer:
    return trace.get_tracer(TRACER_NAME)


def shutdown_telemetry(timeout_millis: int = 10_000) -> None:
    """Flush pending spans before the batch job exits."""
    provider = trace.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush(timeout_millis=timeout_millis)
    if hasattr(provider, "shutdown"):
        provider.shutdown()
