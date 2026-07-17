"""BaseAgent — shared contract for every subagent: timed execution, retry on
failure, tracing, and a uniform AgentResult so the supervisor/orchestrator
never needs to know an individual subagent's internals."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from app.core.config import settings
from app.core.logging import get_logger
from app.core.telemetry import traced_span

logger = get_logger(__name__)


@dataclass
class AgentResult:
    agent_name: str
    success: bool
    output: Any = None
    confidence: float = 0.0
    error: Optional[str] = None
    duration_ms: float = 0.0
    retries: int = 0


class BaseAgent(ABC):
    name: str = "base_agent"
    max_retries: int = settings.agent_max_retries

    @abstractmethod
    async def _run(self, context: dict) -> Tuple[Any, float]:
        """Do the agent's work. Return (output, confidence)."""
        raise NotImplementedError

    async def execute(self, context: dict) -> AgentResult:
        start = time.perf_counter()
        retries = 0
        last_error: Optional[str] = None
        max_attempts = max(1, self.max_retries + 1)

        with traced_span(f"agent.{self.name}"):
            for attempt in range(max_attempts):
                try:
                    output, confidence = await self._run(context)
                    duration_ms = (time.perf_counter() - start) * 1000
                    logger.info(
                        "agent=%s status=success attempt=%d duration_ms=%.2f confidence=%.2f",
                        self.name,
                        attempt + 1,
                        duration_ms,
                        confidence,
                    )
                    return AgentResult(
                        agent_name=self.name,
                        success=True,
                        output=output,
                        confidence=confidence,
                        duration_ms=duration_ms,
                        retries=retries,
                    )
                except Exception as exc:  # noqa: BLE001 - isolate agent failures
                    last_error = f"{type(exc).__name__}: {exc}"
                    retries = attempt
                    logger.warning(
                        "agent=%s status=retry attempt=%d error=%s", self.name, attempt + 1, last_error
                    )

        duration_ms = (time.perf_counter() - start) * 1000
        logger.error("agent=%s status=failed error=%s", self.name, last_error)
        return AgentResult(
            agent_name=self.name,
            success=False,
            error=last_error,
            duration_ms=duration_ms,
            retries=retries,
        )
