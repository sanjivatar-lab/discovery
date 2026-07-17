"""LogicExtractionSubagent — walks normalized ASTs to find business rules,
validation logic, and conditional flows, turning each decision point into a
LogicUnit ready for rule mining."""
from __future__ import annotations

from typing import Any, List, Tuple

from app.agents.base import BaseAgent
from app.models.ast_models import FileAST
from app.models.rule_models import LogicUnit

_VALIDATION_HINTS = ("null", "empty", "blank", "valid", "invalid", "required")
_EXCEPTION_HINTS = ("throw", "exception")


def _classify(condition_kind: str, expression: str, then_summary: str) -> str:
    text = f"{expression} {then_summary}".lower()
    if any(hint in text for hint in _EXCEPTION_HINTS) or any(hint in text for hint in _VALIDATION_HINTS):
        return "validation"
    if condition_kind == "switch":
        return "decision"
    return "business"


def _first_statement(summary: str) -> str:
    summary = summary.strip().lstrip("{").strip()
    for sep in (";", "\n"):
        if sep in summary:
            summary = summary.split(sep, 1)[0]
            break
    return summary.strip().rstrip("}").strip() or "(no explicit action captured)"


class LogicExtractionSubagent(BaseAgent):
    name = "logic_extraction_subagent"

    async def _run(self, context: dict) -> Tuple[Any, float]:
        file_asts: List[FileAST] = context["file_asts"]
        units: List[LogicUnit] = []
        methods_seen = 0
        methods_with_logic = 0

        for file_ast in file_asts:
            for cls in file_ast.classes:
                class_annotation_names = [a.name for a in cls.annotations]
                for method in cls.methods:
                    methods_seen += 1
                    if not method.conditions:
                        continue
                    methods_with_logic += 1
                    method_annotations = [a.name for a in method.annotations] + class_annotation_names

                    for condition in method.conditions:
                        kind = _classify(condition.kind, condition.expression, condition.then_summary)
                        if condition.kind == "switch":
                            action = "; ".join(condition.case_labels) or "(no cases captured)"
                        else:
                            action = _first_statement(condition.then_summary)

                        units.append(
                            LogicUnit(
                                file_path=file_ast.file_path,
                                class_name=cls.name,
                                method_name=method.name,
                                kind=kind,
                                condition=condition.expression,
                                action=action,
                                raw_snippet=condition.then_summary or condition.expression,
                                annotations=method_annotations,
                            )
                        )

        confidence = methods_with_logic / methods_seen if methods_seen else 0.0
        return units, confidence
