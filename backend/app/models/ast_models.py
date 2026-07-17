"""Normalized, JSON-friendly representations of the tree-sitter Java AST/CST."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class Annotation(BaseModel):
    name: str
    arguments: str = ""
    start_line: int
    end_line: int


class MethodParam(BaseModel):
    type: str
    name: str


class ConditionNode(BaseModel):
    """A decision point extracted from an if_statement or switch_expression/statement."""

    kind: str = Field(description="'if' or 'switch'")
    expression: str
    start_line: int
    end_line: int
    then_summary: str = ""
    else_summary: str = ""
    case_labels: List[str] = Field(default_factory=list)


class CallNode(BaseModel):
    caller_method: str
    callee_object: str = ""
    callee_name: str
    start_line: int


class MethodNode(BaseModel):
    name: str
    return_type: str = "void"
    modifiers: List[str] = Field(default_factory=list)
    params: List[MethodParam] = Field(default_factory=list)
    annotations: List[Annotation] = Field(default_factory=list)
    conditions: List[ConditionNode] = Field(default_factory=list)
    calls: List[CallNode] = Field(default_factory=list)
    start_line: int
    end_line: int


class FieldNode(BaseModel):
    type: str
    name: str
    annotations: List[Annotation] = Field(default_factory=list)
    modifiers: List[str] = Field(default_factory=list)


class ClassNode(BaseModel):
    name: str
    kind: str = Field(default="class", description="class | interface | enum | record")
    package: str = ""
    superclass: str = ""
    interfaces: List[str] = Field(default_factory=list)
    annotations: List[Annotation] = Field(default_factory=list)
    modifiers: List[str] = Field(default_factory=list)
    fields: List[FieldNode] = Field(default_factory=list)
    methods: List[MethodNode] = Field(default_factory=list)
    start_line: int
    end_line: int


class FileAST(BaseModel):
    file_path: str
    package: str = ""
    imports: List[str] = Field(default_factory=list)
    classes: List[ClassNode] = Field(default_factory=list)
    parse_errors: List[str] = Field(default_factory=list)
    has_syntax_error: bool = False


class AggregatedAST(BaseModel):
    files: List[FileAST] = Field(default_factory=list)

    @property
    def total_classes(self) -> int:
        return sum(len(f.classes) for f in self.files)

    @property
    def total_methods(self) -> int:
        return sum(len(c.methods) for f in self.files for c in f.classes)
