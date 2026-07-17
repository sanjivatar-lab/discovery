"""HTTP API surface:

POST /analyze/codebase  - accept a ZIP upload or a git repo URL, kick off
                          analysis in the background, return immediately.
GET  /analysis/{id}     - status + summary stats of a run.
GET  /rules/{id}        - mined business rules.
GET  /dependencies/{id} - the service/call dependency graph.
GET  /documentation/{id}- generated functional docs, flow summaries, and
                          mermaid decision trees.
"""
from __future__ import annotations

import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from app.agents.supervisor_agent import SupervisorAgent
from app.api.deps import get_store
from app.core.config import settings
from app.core.logging import get_logger
from app.models.analysis_models import AnalysisResult, AnalysisStatus
from app.models.graph_models import DependencyGraph
from app.schemas.responses import (
    AnalyzeAcceptedResponse,
    AnalysisStatusResponse,
    DependenciesResponse,
    DocumentationResponse,
    RulesResponse,
)
from app.utils.ids import new_id
from app.utils.repo_ingest import clone_git_repo, extract_zip

logger = get_logger(__name__)
router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_supervisor():
    if settings.use_langgraph:
        from app.orchestrator.langgraph_orchestrator import LangGraphSupervisor

        return LangGraphSupervisor()
    return SupervisorAgent()


async def _run_analysis(analysis_id: str, source_dir: Path) -> None:
    store = get_store()
    orchestrator = _build_supervisor()
    try:
        await store.update_status(analysis_id, AnalysisStatus.PARSING)
        result = await orchestrator.analyze(source_dir)

        status = AnalysisStatus.COMPLETED if result["file_count"] else AnalysisStatus.FAILED
        await store.save_results(
            analysis_id=analysis_id,
            file_asts=result["file_asts"],
            rules=result["rules"],
            graph=result["graph"],
            documentation=result["documentation"],
            agent_runs=result["agent_runs"],
        )
        await store.finalize_analysis(
            analysis_id=analysis_id,
            status=status,
            file_count=result["file_count"],
            class_count=sum(len(f.classes) for f in result["file_asts"]),
            method_count=sum(len(c.methods) for f in result["file_asts"] for c in f.classes),
            rule_count=len(result["rules"]),
            confidence_score=result["confidence"],
            iterations=result["iterations"],
            weak_areas=result["weak_areas"],
        )
    except Exception as exc:  # noqa: BLE001 - background task must never raise silently
        logger.exception("analysis %s failed", analysis_id)
        await store.mark_failed(analysis_id, str(exc))


@router.post("/analyze/codebase", response_model=AnalyzeAcceptedResponse, status_code=202)
async def analyze_codebase(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    git_url: Optional[str] = Form(None),
    branch: Optional[str] = Form(None),
):
    if not file and not git_url:
        raise HTTPException(400, "Provide either a ZIP `file` upload or a `git_url` form field.")
    if file and git_url:
        raise HTTPException(400, "Provide only one of `file` or `git_url`, not both.")

    analysis_id = new_id()
    workdir = settings.upload_dir / analysis_id
    workdir.mkdir(parents=True, exist_ok=True)

    if file is not None:
        zip_path = workdir / "upload.zip"
        with open(zip_path, "wb") as out:
            shutil.copyfileobj(file.file, out)
        try:
            source_dir = extract_zip(zip_path, workdir)
        except zipfile.BadZipFile as exc:
            raise HTTPException(400, f"Invalid ZIP archive: {exc}") from exc
        source = "zip"
    else:
        try:
            source_dir = clone_git_repo(git_url, workdir, branch)
        except RuntimeError as exc:
            raise HTTPException(400, str(exc)) from exc
        source = "git"

    now = _now()
    analysis = AnalysisResult(
        id=analysis_id, status=AnalysisStatus.PENDING, created_at=now, updated_at=now, source=source
    )
    await get_store().create_analysis(analysis)

    background_tasks.add_task(_run_analysis, analysis_id, source_dir)

    return AnalyzeAcceptedResponse(analysis_id=analysis_id, status=AnalysisStatus.PENDING.value)


@router.get("/analysis/{analysis_id}", response_model=AnalysisStatusResponse)
async def get_analysis(analysis_id: str):
    analysis = await get_store().get_analysis(analysis_id)
    if analysis is None:
        raise HTTPException(404, "analysis not found")
    return analysis


@router.get("/rules/{analysis_id}", response_model=RulesResponse)
async def get_rules(analysis_id: str):
    store = get_store()
    if await store.get_analysis(analysis_id) is None:
        raise HTTPException(404, "analysis not found")
    rules = await store.get_rules(analysis_id)
    return RulesResponse(analysis_id=analysis_id, rule_count=len(rules), rules=rules)


@router.get("/dependencies/{analysis_id}", response_model=DependenciesResponse)
async def get_dependencies(analysis_id: str):
    store = get_store()
    if await store.get_analysis(analysis_id) is None:
        raise HTTPException(404, "analysis not found")
    graph = await store.get_graph(analysis_id)
    return DependenciesResponse(analysis_id=analysis_id, graph=graph or DependencyGraph())


@router.get("/documentation/{analysis_id}", response_model=DocumentationResponse)
async def get_documentation(analysis_id: str):
    store = get_store()
    if await store.get_analysis(analysis_id) is None:
        raise HTTPException(404, "analysis not found")
    doc = await store.get_documentation(analysis_id) or {}
    return DocumentationResponse(
        analysis_id=analysis_id,
        documentation_markdown=doc.get("documentation_markdown", ""),
        flow_summaries=doc.get("flow_summaries", []),
        decision_trees_mermaid=doc.get("decision_trees_mermaid", []),
    )
