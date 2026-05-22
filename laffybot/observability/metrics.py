"""Prometheus metrics integration.

ARCHITECTURE.md 第 185-190 行要求 OpenTelemetry tracing + Prometheus metrics.
当前为桩代码 — 接入 prometheus_client 后取消注释并注册默认指标。
"""

from __future__ import annotations

# ── Counter / Histogram stubs ────────────────────────────────────────────


class _CounterStub:
    def inc(self, amount: float = 1) -> None:
        pass


class _HistogramStub:
    def observe(self, amount: float) -> None:
        pass


def counter(
    name: str, description: str = "", labelnames: tuple[str, ...] = ()
) -> _CounterStub:
    return _CounterStub()


def histogram(
    name: str,
    description: str = "",
    labelnames: tuple[str, ...] = (),
    buckets: tuple[float, ...] = (),
) -> _HistogramStub:
    return _HistogramStub()


# ── Default metrics —─────────────────────────────────────────────────────

# Active sessions (gauge)
active_sessions = counter("laffybot_sessions_active", "Active sessions")

# Messages processed (counter)
messages_total = counter(
    "laffybot_messages_total", "Messages processed", labelnames=("status",)
)

# Provider calls (histogram)
provider_latency = histogram(
    "laffybot_provider_latency_seconds",
    "Provider API call latency",
    labelnames=("provider",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


def configure_prometheus(port: int = 9090) -> None:
    """Start the Prometheus metrics HTTP endpoint.

    When prometheus_client is installed:
        from prometheus_client import start_http_server
        start_http_server(port)
    """
    _ = port
