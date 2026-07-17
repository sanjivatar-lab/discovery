"""Generic, agent-agnostic refinement-loop engine.

Flow: run a set of named async steps in order -> critique the resulting
context -> if confidence clears the threshold (or the critic has nothing
left to flag), stop; otherwise map the critic's weak-area tags back to the
steps most likely to fix them and re-run only those, up to a max number of
iterations. This is the "loop-based orchestration" piece, deliberately kept
independent of what the steps/critic actually do so it can drive any
pipeline, not just the Java-analysis one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Tuple

from app.core.logging import get_logger

logger = get_logger(__name__)

StepFn = Callable[[dict], Awaitable[None]]
CriticFn = Callable[[dict], Awaitable[Tuple[float, List[str]]]]

# Maps a critic weak-area tag (the text before the first ":") to the steps
# that should re-run, in case fixing that area requires downstream steps to
# re-derive their output from fresh input.
_DOWNSTREAM_STEPS: Dict[str, List[str]] = {
    "parsing": ["parsing", "logic", "rules", "dependencies", "documentation"],
    "logic": ["logic", "rules", "documentation"],
    "rules": ["rules", "documentation"],
    "dependencies": ["dependencies", "documentation"],
}


@dataclass
class RefinementLoopResult:
    context: dict
    confidence: float
    iterations: int
    weak_areas: List[str] = field(default_factory=list)
    agent_runs: List[dict] = field(default_factory=list)


def select_rerun_steps(weak_areas: List[str], all_steps: List[str]) -> List[str]:
    rerun: set[str] = set()
    for area in weak_areas:
        tag = area.split(":", 1)[0]
        rerun.update(_DOWNSTREAM_STEPS.get(tag, []))
    return [s for s in all_steps if s in rerun]


class RefinementLoop:
    """Drives: run steps -> critique -> (selectively rerun | stop)."""

    def __init__(
        self,
        steps: Dict[str, StepFn],
        critic: CriticFn,
        confidence_threshold: float,
        max_iterations: int,
    ):
        self.steps = steps
        self.critic = critic
        self.confidence_threshold = confidence_threshold
        self.max_iterations = max(1, max_iterations)

    async def run(self, context: dict, initial_step_order: List[str]) -> RefinementLoopResult:
        context.setdefault("_run_logs", [])
        pending = list(initial_step_order)
        confidence = 0.0
        weak_areas: List[str] = []
        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1
            context["_iteration"] = iteration

            for step_name in pending:
                await self.steps[step_name](context)

            confidence, weak_areas = await self.critic(context)
            logger.info(
                "refinement iteration=%d confidence=%.3f weak_areas=%s", iteration, confidence, weak_areas
            )

            if confidence >= self.confidence_threshold or not weak_areas:
                break

            pending = select_rerun_steps(weak_areas, list(self.steps.keys()))
            if not pending:
                break

        return RefinementLoopResult(
            context=context,
            confidence=confidence,
            iterations=iteration,
            weak_areas=weak_areas,
            agent_runs=context["_run_logs"],
        )
