"""RuleFormatterTool — turns extracted LogicUnits into structured IF/THEN
business rules."""
from __future__ import annotations

import hashlib

from app.models.rule_models import LogicUnit, Rule

_VALIDATION_KEYWORDS = ("valid", "null", "empty", "blank", "required", "must", "illegal")
_EXCEPTION_KEYWORDS = ("throw", "exception", "error", "reject")


def score_confidence(unit: LogicUnit) -> float:
    """Heuristic confidence: higher when the condition clearly gates a
    validation/exception path, lower for generic branching."""
    text = f"{unit.condition} {unit.action}".lower()
    score = 0.5
    if any(k in text for k in _VALIDATION_KEYWORDS):
        score += 0.2
    if any(k in text for k in _EXCEPTION_KEYWORDS):
        score += 0.15
    if unit.annotations:
        score += 0.1
    if unit.extraction_method == "llm":
        score += 0.1  # LLM saw the full method body, not just keyword matches
    if not unit.condition.strip():
        score -= 0.3
    return max(0.0, min(1.0, score))


def to_statement(condition: str, action: str) -> str:
    condition = condition.strip() or "<unknown condition>"
    action = action.strip() or "<no explicit action>"
    return f"IF {condition} THEN {action}"


def format_rule(unit: LogicUnit) -> Rule:
    rule_id = hashlib.sha1(
        f"{unit.file_path}:{unit.class_name}:{unit.method_name}:{unit.condition}".encode("utf-8")
    ).hexdigest()[:16]
    return Rule(
        id=rule_id,
        source_file=unit.file_path,
        source_class=unit.class_name,
        source_method=unit.method_name,
        rule_type=unit.kind,
        condition=unit.condition,
        action=unit.action,
        statement=to_statement(unit.condition, unit.action),
        confidence=score_confidence(unit),
        raw_snippet=unit.raw_snippet,
        extraction_method=unit.extraction_method,
    )
