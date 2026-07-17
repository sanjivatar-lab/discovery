"""DependencyGraphSubagent — builds the networkx-backed call/service
dependency graph from the aggregated ASTs."""
from __future__ import annotations

from typing import Any, List, Tuple

from app.agents.base import BaseAgent
from app.models.ast_models import FileAST
from app.tools.graph_builder_tool import build_dependency_graph


class DependencyGraphSubagent(BaseAgent):
    name = "dependency_graph_subagent"

    async def _run(self, context: dict) -> Tuple[Any, float]:
        file_asts: List[FileAST] = context["file_asts"]
        graph = build_dependency_graph(file_asts)

        resolved_calls = sum(1 for e in graph.edges if e.type == "calls")
        total_calls = resolved_calls + len(graph.unresolved_calls)
        confidence = resolved_calls / total_calls if total_calls else 1.0
        return graph, confidence
