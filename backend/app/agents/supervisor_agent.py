"""SupervisorAgent — the core orchestrator (Agent Harness supervisor).

Responsibilities: accept an ingested codebase directory, split it into
file-level chunks, spawn parsing subagents in parallel, aggregate their
output, then drive the extraction -> critique -> selective-refinement loop
via the generic RefinementLoop engine until confidence clears the
configured threshold or iterations run out.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.agents.critic_subagent import CriticSubagent
from app.agents.dependency_subagent import DependencyGraphSubagent
from app.agents.doc_subagent import DocumentationSubagent
from app.agents.logic_subagent import LogicExtractionSubagent
from app.agents.parsing_subagent import ParsingSubagent
from app.agents.rule_subagent import RuleMiningSubagent
from app.core.config import settings
from app.core.logging import get_logger
from app.models.ast_models import FileAST
from app.orchestrator.pipeline import RefinementLoop
from app.tools.file_chunking_tool import chunk_files, discover_java_files
from app.tools.parallel_execution_tool import run_bounded

logger = get_logger(__name__)


def _log_result(context: dict, result) -> None:
    context["_run_logs"].append(
        {
            "agent_name": result.agent_name,
            "iteration": context.get("_iteration", 1),
            "duration_ms": result.duration_ms,
            "success": result.success,
            "retries": result.retries,
            "error": result.error,
        }
    )


async def _parsing_step(context: dict) -> None:
    chunks: List[List[Path]] = context["chunks"]
    subagents = [ParsingSubagent(i, chunk) for i, chunk in enumerate(chunks)]

    results = await run_bounded(
        [(lambda a=agent: a.execute(context)) for agent in subagents],
        max_concurrency=settings.max_concurrent_subagents,
    )

    file_asts: List[FileAST] = []
    for agent, result in zip(subagents, results):
        if isinstance(result, Exception):
            logger.error("parsing subagent %s crashed: %s", agent.name, result)
            continue
        _log_result(context, result)
        if result.success and result.output:
            file_asts.extend(result.output)

    context["file_asts"] = file_asts


async def _logic_step(context: dict) -> None:
    result = await LogicExtractionSubagent().execute(context)
    _log_result(context, result)
    context["logic_units"] = result.output or []
    context["logic_confidence"] = result.confidence


async def _rules_step(context: dict) -> None:
    result = await RuleMiningSubagent().execute(context)
    _log_result(context, result)
    context["rules"] = result.output or []


async def _dependencies_step(context: dict) -> None:
    result = await DependencyGraphSubagent().execute(context)
    _log_result(context, result)
    context["graph"] = result.output


async def _documentation_step(context: dict) -> None:
    result = await DocumentationSubagent().execute(context)
    _log_result(context, result)
    context["documentation"] = result.output or {}


async def _critic(context: dict) -> Tuple[float, List[str]]:
    result = await CriticSubagent().execute(context)
    _log_result(context, result)
    output = result.output or {"confidence": 0.0, "weak_areas": ["critic:failed to run"]}
    return output["confidence"], output["weak_areas"]


class SupervisorAgent:
    """Core orchestrator: chunk -> parse (parallel) -> extract -> critique ->
    refine (loop) -> return the aggregated analysis context."""

    name = "supervisor_agent"

    def __init__(self) -> None:
        self.steps = {
            "parsing": _parsing_step,
            "logic": _logic_step,
            "rules": _rules_step,
            "dependencies": _dependencies_step,
            "documentation": _documentation_step,
        }
        self.loop = RefinementLoop(
            steps=self.steps,
            critic=_critic,
            confidence_threshold=settings.confidence_threshold,
            max_iterations=settings.max_refinement_iterations,
        )

    async def analyze(self, codebase_root: str | Path) -> Dict[str, Any]:
        files = discover_java_files(codebase_root)
        chunks = chunk_files(files, settings.files_per_chunk, settings.max_chunk_bytes)
        logger.info("supervisor: %d file(s) split into %d chunk(s)", len(files), len(chunks))

        context: Dict[str, Any] = {"chunks": chunks, "codebase_root": str(codebase_root)}

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

        result = await self.loop.run(context, list(self.steps.keys()))

        return {
            "file_asts": result.context.get("file_asts", []),
            "rules": result.context.get("rules", []),
            "graph": result.context.get("graph"),
            "documentation": result.context.get("documentation", {}),
            "confidence": result.confidence,
            "iterations": result.iterations,
            "weak_areas": result.weak_areas,
            "agent_runs": result.agent_runs,
            "file_count": len(files),
        }
