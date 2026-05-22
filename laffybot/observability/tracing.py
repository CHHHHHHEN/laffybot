"""OpenTelemetry tracing integration.

ARCHITECTURE.md 第 185-190 行要求 OpenTelemetry tracing + Prometheus metrics.
当前为桩代码 (stub)，集成具体后端后启用。
"""

from __future__ import annotations

from typing import Any

# ── Tracer stub ──────────────────────────────────────────────────────────


class _TracerStub:
    """No-op tracer until a real OpenTelemetry SDK is wired in."""

    def start_span(self, name: str, **kwargs: Any) -> "_SpanStub":
        return _SpanStub(name)

    def start_as_current_span(self, name: str, **kwargs: Any) -> "_SpanContext":
        return _SpanContext(name)


class _SpanStub:
    def __init__(self, name: str) -> None:
        self._name = name

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def end(self) -> None:
        pass

    def __enter__(self) -> "_SpanStub":
        return self

    def __exit__(self, *args: Any) -> None:
        self.end()


class _SpanContext:
    def __init__(self, name: str) -> None:
        self._name = name

    def __enter__(self) -> _SpanStub:
        return _SpanStub(self._name)

    def __exit__(self, *args: Any) -> None:
        pass


# Module-level tracer instance — swap with real tracer when OTEL is configured.
tracer: _TracerStub = _TracerStub()


def configure_opentelemetry(endpoint: str = "", service_name: str = "laffybot") -> None:
    """Wire in a real OpenTelemetry tracer.

    Called from the composition root when OTEL is available:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        configure_opentelemetry()
        tracer = trace.get_tracer(__name__)
    """
    # Placeholder — real wiring here when dependencies are installed.
    _ = endpoint, service_name
