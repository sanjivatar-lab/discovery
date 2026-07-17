"""CriticSubagent — the loop-engineering piece: validates the outputs of
every other subagent, assigns a single weighted confidence score, and
surfaces tagged weak areas so the orchestrator can decide what to
selectively re-run."""
from __future__ import annotations

from typing import Any, List, Tuple

from app.agents.base import BaseAgent
from app.models.ast_models import FileAST
from app.models.graph_models import DependencyGraph
from app.models.rule_models import Rule

_WEIGHTS = {
    "parse": 0.35,
    "logic_coverage": 0.25,
    "rule_yield": 0.20,
    "graph_resolution": 0.20,
}


class CriticSubagent(BaseAgent):
    name = "critic_subagent"

    async def _run(self, context: dict) -> Tuple[Any, float]:
        file_asts: List[FileAST] = context.get("file_asts", [])
        rules: List[Rule] = context.get("rules", [])
        graph: DependencyGraph = context.get("graph") or DependencyGraph()
        logic_confidence: float = context.get("logic_confidence", 0.0)

        weak_areas: List[str] = []

        total_files = len(file_asts) or 1
        clean_files = sum(1 for f in file_asts if not f.has_syntax_error)
        parse_score = clean_files / total_files
        if parse_score < 0.9:
            bad_files = [f.file_path for f in file_asts if f.has_syntax_error]
            weak_areas.append(f"parsing:{len(bad_files)} file(s) had syntax errors: {bad_files[:5]}")

        if logic_confidence < 0.4:
            weak_areas.append("logic:low proportion of methods yielded extractable business logic")

        total_methods = sum(len(c.methods) for f in file_asts for c in f.classes) or 1
        rule_yield = min(1.0, len(rules) / total_methods)
        if rule_yield < 0.1:
            weak_areas.append("rules:very few rules mined relative to method count")

        resolved_calls = sum(1 for e in graph.edges if e.type == "calls")
        total_calls = resolved_calls + len(graph.unresolved_calls)
        graph_resolution = resolved_calls / total_calls if total_calls else 1.0
        if graph_resolution < 0.5:
            weak_areas.append(
                f"dependencies:{len(graph.unresolved_calls)} call(s) could not be resolved to a known method"
            )

        confidence = (
            _WEIGHTS["parse"] * parse_score
            + _WEIGHTS["logic_coverage"] * logic_confidence
            + _WEIGHTS["rule_yield"] * rule_yield
            + _WEIGHTS["graph_resolution"] * graph_resolution
        )

        return {"confidence": confidence, "weak_areas": weak_areas}, confidence
