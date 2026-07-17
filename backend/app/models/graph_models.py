"""Dependency / call graph representations, built with networkx and exposed as
plain Pydantic models for JSON serialization and storage."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    label: str
    type: str = Field(description="class | method | service")


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str = Field(description="calls | depends_on | implements | extends")
    weight: int = 1


class DependencyGraph(BaseModel):
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)
    unresolved_calls: List[str] = Field(default_factory=list)
