"""OpenTelemetry tracing setup + a lightweight decorator for tracking agent
executions (duration, success/failure, retries). Degrades to a no-op tracer
if OpenTelemetry isn't installed/enabled so the rest of the system never hard
depends on it.
"""
from __future__ import annotations

import functools
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_tracer = None


def setup_telemetry() -> None:
    """Initialize the global tracer provider. Safe to call multiple times."""
    global _tracer
    if _tracer is not None:
        return
    if not settings.otel_enabled:
        _tracer = _NoOpTracer()
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            ConsoleSpanExporter,
            SimpleSpanProcessor,
        )

        resource = Resource.create({SERVICE_NAME: settings.otel_service_name})
        provider = TracerProvider(resource=resource)
        if settings.otel_console_export:
            # SimpleSpanProcessor (not Batch): console export doesn't benefit from
            # batching, and Batch's background flush thread can outlive a closed
            # stdout at process exit (e.g. under pytest), producing spurious errors.
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(settings.otel_service_name)
    except Exception:  # pragma: no cover - defensive fallback
        logger.warning("OpenTelemetry unavailable; falling back to no-op tracer", exc_info=True)
        _tracer = _NoOpTracer()


class _NoOpSpan:
    def set_attribute(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def record_exception(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def set_status(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class _NoOpTracer:
    @contextmanager
    def start_as_current_span(self, _name: str) -> Iterator[_NoOpSpan]:
        yield _NoOpSpan()


def get_tracer():
    if _tracer is None:
        setup_telemetry()
    return _tracer


@contextmanager
def traced_span(name: str, **attributes: Any) -> Iterator[Any]:
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            try:
                span.set_attribute(key, value)
            except Exception:
                pass
        yield span


class ExecutionRecord:
    """Captures timing/outcome metadata for a single agent execution."""

    __slots__ = ("agent_name", "duration_ms", "success", "retries", "error")

    def __init__(self, agent_name: str, duration_ms: float, success: bool, retries: int, error: str | None):
        self.agent_name = agent_name
        self.duration_ms = duration_ms
        self.success = success
        self.retries = retries
        self.error = error

    def as_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "retries": self.retries,
            "error": self.error,
        }


def track_execution(agent_name: str) -> Callable:
    """Decorator that wraps an async callable with a trace span + timing log."""

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            with traced_span(f"agent.{agent_name}"):
                result = await fn(*args, **kwargs)
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info("agent=%s duration_ms=%.2f", agent_name, duration_ms)
            return result

        return wrapper

    return decorator
