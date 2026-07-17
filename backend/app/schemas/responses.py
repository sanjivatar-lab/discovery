"""API response schemas."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel

from app.models.analysis_models import AnalysisResult
from app.models.graph_models import DependencyGraph
from app.models.rule_models import Rule


class AnalyzeAcceptedResponse(BaseModel):
    analysis_id: str
    status: str


class AnalysisStatusResponse(AnalysisResult):
    pass


class RulesResponse(BaseModel):
    analysis_id: str
    rule_count: int
    rules: List[Rule]


class DependenciesResponse(BaseModel):
    analysis_id: str
    graph: DependencyGraph


class DocumentationResponse(BaseModel):
    analysis_id: str
    documentation_markdown: str
    flow_summaries: List[str]
    decision_trees_mermaid: List[str]
