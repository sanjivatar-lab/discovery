"""Business-rule representations produced by the rule-mining subagent."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class LogicUnit(BaseModel):
    """An intermediate representation between raw AST conditions and mined rules."""

    file_path: str
    class_name: str
    method_name: str
    kind: str = Field(description="validation | business | decision")
    condition: str
    action: str
    raw_snippet: str = ""
    annotations: List[str] = Field(default_factory=list)


class Rule(BaseModel):
    id: str
    source_file: str
    source_class: str
    source_method: str
    rule_type: str = Field(description="validation | business | decision")
    condition: str
    action: str
    statement: str = Field(description="Human-readable IF <condition> THEN <action>")
    confidence: float = 0.5
    raw_snippet: str = ""


class RuleSet(BaseModel):
    rules: List[Rule] = Field(default_factory=list)
