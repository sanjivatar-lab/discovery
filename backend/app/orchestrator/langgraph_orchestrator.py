"""LangGraph-based orchestrator (bonus).

Mirrors `SupervisorAgent`'s exact same step functions and critic as a
LangGraph `StateGraph` with a conditional refinement loop, for teams that
want LangGraph's execution/visualization model instead of the built-in
`RefinementLoop` engine (app/orchestrator/pipeline.py).

`langgraph` is an optional dependency — this module is only imported when
`settings.use_langgraph` is True, and raises a clear error at construction
time if the package isn't installed rather than failing on unrelated
imports elsewhere in the app.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, TypedDict

from app.agents.supervisor_agent import (
    _critic,
    _dependencies_step,
    _documentation_step,
    _logic_step,
    _parsing_step,
    _rules_step,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.orchestrator.pipeline import select_rerun_steps
from app.tools.file_chunking_tool import chunk_files, discover_java_files

logger = get_logger(__name__)


class GraphState(TypedDict, total=False):
    context: Dict[str, Any]
    confidence: float
    weak_areas: List[str]
    iteration: int


class LangGraphSupervisor:
    name = "supervisor_agent_langgraph"

    def __init__(self) -> None:
        try:
            from langgraph.graph import END, StateGraph
        except ImportError as exc:
            raise RuntimeError(
                "settings.use_langgraph is enabled but the `langgraph` package is "
                "not installed. `pip install langgraph` or set APP_USE_LANGGRAPH=false."
            ) from exc

        self.step_fns = {
            "parsing": _parsing_step,
            "logic": _logic_step,
            "rules": _rules_step,
            "dependencies": _dependencies_step,
            "documentation": _documentation_step,
        }
        self.step_order = list(self.step_fns.keys())

        graph = StateGraph(GraphState)
        for step_name, fn in self.step_fns.items():
            graph.add_node(step_name, self._make_step_node(fn))
        graph.add_node("critic", self._make_critic_node())

        try:
            graph.set_entry_point(self.step_order[0])
        except AttributeError:  # newer langgraph versions drop set_entry_point
            from langgraph.graph import START

            graph.add_edge(START, self.step_order[0])

        for a, b in zip(self.step_order, self.step_order[1:]):
            graph.add_edge(a, b)
        graph.add_edge(self.step_order[-1], "critic")

        graph.add_conditional_edges(
            "critic",
            self._route_after_critic,
            {**{s: s for s in self.step_order}, "done": END},
        )

        self._compiled = graph.compile()

    @staticmethod
    def _make_step_node(fn):
        async def run(state: GraphState) -> GraphState:
            state["context"]["_iteration"] = state.get("iteration", 1)
            await fn(state["context"])
            return state

        return run

    @staticmethod
    def _make_critic_node():
        async def run(state: GraphState) -> GraphState:
            confidence, weak_areas = await _critic(state["context"])
            state["confidence"] = confidence
            state["weak_areas"] = weak_areas
            state["iteration"] = state.get("iteration", 1) + 1
            return state

        return run

    def _route_after_critic(self, state: GraphState) -> str:
        if state["confidence"] >= settings.confidence_threshold or not state["weak_areas"]:
            return "done"
        if state["iteration"] > settings.max_refinement_iterations:
            return "done"
        rerun = select_rerun_steps(state["weak_areas"], self.step_order)
        return rerun[0] if rerun else "done"

    async def analyze(self, codebase_root: str | Path) -> Dict[str, Any]:
        files = discover_java_files(codebase_root)
        chunks = chunk_files(files, settings.files_per_chunk, settings.max_chunk_bytes)
        logger.info("langgraph supervisor: %d file(s) split into %d chunk(s)", len(files), len(chunks))

        if not files:
            return {
                "file_asts": [],
                "rules": [],
                "graph": None,
                "documentation": {},
                "confidence": 0.0,
                "iterations": 0,
                "weak_areas": ["ingest:no .java files found in the provided codebase"],
                "agent_runs": [],
                "file_count": 0,
            }

        context: Dict[str, Any] = {"chunks": chunks, "codebase_root": str(codebase_root), "_run_logs": []}
        initial_state: GraphState = {"context": context, "confidence": 0.0, "weak_areas": [], "iteration": 1}

        final_state = await self._compiled.ainvoke(initial_state)

        return {
            "file_asts": context.get("file_asts", []),
            "rules": context.get("rules", []),
            "graph": context.get("graph"),
            "documentation": context.get("documentation", {}),
            "confidence": final_state.get("confidence", 0.0),
            "iterations": max(0, final_state.get("iteration", 1) - 1),
            "weak_areas": final_state.get("weak_areas", []),
            "agent_runs": context.get("_run_logs", []),
            "file_count": len(files),
        }
