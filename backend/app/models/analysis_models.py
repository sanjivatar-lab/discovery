"""Top-level analysis run state tracked by the supervisor + persisted to SQLite."""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class AnalysisStatus(str, Enum):
    PENDING = "pending"
    INGESTING = "ingesting"
    PARSING = "parsing"
    EXTRACTING = "extracting"
    CRITIQUING = "critiquing"
    REFINING = "refining"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentRunLog(BaseModel):
    agent_name: str
    iteration: int
    started_at: str
    duration_ms: float
    success: bool
    retries: int = 0
    error: Optional[str] = None


class AnalysisResult(BaseModel):
    id: str
    status: AnalysisStatus = AnalysisStatus.PENDING
    created_at: str
    updated_at: str
    source: str = Field(description="zip | git")
    file_count: int = 0
    class_count: int = 0
    method_count: int = 0
    rule_count: int = 0
    confidence_score: float = 0.0
    iterations: int = 0
    weak_areas: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
