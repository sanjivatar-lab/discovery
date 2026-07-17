"""LogicExtractionSubagent — walks normalized ASTs to find business rules,
validation logic, and conditional flows, turning each decision point into a
LogicUnit ready for rule mining.

Classifying each condition (validation vs business vs decision) and writing
a plain-English description of its action is done by an LLM whenever
`APP_LLM_ENABLED=true` — model-independent via LiteLLM (see
app/tools/llm_tool.py), one prompt per method (batching all of that
method's conditions into a single call rather than one call per
condition, to keep request volume sane on large codebases). Every method is
classified concurrently, bounded by `APP_MAX_CONCURRENT_SUBAGENTS`.

Falls back to a deterministic keyword heuristic per condition whenever the
LLM is disabled, unavailable, or returns something unusable — so the
pipeline never hard-depends on network/LLM access, and unit tests exercise
both paths without needing real credentials.
"""
from __future__ import annotations

from typing import Any, List, Tuple

from app.agents.base import BaseAgent
from app.core.config import settings
from app.core.logging import get_logger
from app.models.ast_models import ClassNode, ConditionNode, FileAST, MethodNode
from app.models.rule_models import LogicUnit
from app.tools.llm_tool import complete_json
from app.tools.parallel_execution_tool import run_bounded

logger = get_logger(__name__)

_VALID_KINDS = {"validation", "business", "decision"}
_VALIDATION_HINTS = ("null", "empty", "blank", "valid", "invalid", "required")
_EXCEPTION_HINTS = ("throw", "exception")

_SYSTEM_PROMPT = (
    "You are a senior software analyst extracting business rules from Java source code.\n"
    "For each numbered condition below, classify it as exactly one of:\n"
    "  - validation: guards/rejects bad input (null checks, range checks, throwing on invalid state)\n"
    "  - decision: a switch/multi-way branch choosing between named outcomes\n"
    "  - business: any other conditional business logic\n"
    "Then write a short, plain-English description of what happens when the condition is met "
    "(the 'action'), based only on the code shown — do not invent behavior that isn't there.\n"
    "Respond with ONLY a JSON array, one object per condition, in the same order, each shaped as:\n"
    '{"index": <int>, "kind": "validation|business|decision", "action": "<plain English>"}\n'
    "No prose, no markdown fences, no trailing commentary."
)


def _heuristic_classify(condition_kind: str, expression: str, then_summary: str) -> str:
    text = f"{expression} {then_summary}".lower()
    if any(hint in text for hint in _EXCEPTION_HINTS) or any(hint in text for hint in _VALIDATION_HINTS):
        return "validation"
    if condition_kind == "switch":
        return "decision"
    return "business"


def _heuristic_action(condition: ConditionNode) -> str:
    if condition.kind == "switch":
        return "; ".join(condition.case_labels) or "(no cases captured)"
    summary = condition.then_summary.strip().lstrip("{").strip()
    for sep in (";", "\n"):
        if sep in summary:
            summary = summary.split(sep, 1)[0]
            break
    return summary.strip().rstrip("}").strip() or "(no explicit action captured)"


def _heuristic_classify_method(conditions: List[ConditionNode]) -> Tuple[List[str], List[str]]:
    kinds = [_heuristic_classify(c.kind, c.expression, c.then_summary) for c in conditions]
    actions = [_heuristic_action(c) for c in conditions]
    return kinds, actions


def _build_prompt(cls: ClassNode, method: MethodNode, conditions: List[ConditionNode]) -> str:
    header = f"Class: {cls.name}"
    if cls.annotations:
        header += f" (annotations: {', '.join(a.name for a in cls.annotations)})"
    params = ", ".join(f"{p.type} {p.name}" for p in method.params)

    lines = [header, f"Method: {method.name}({params})", "Conditions:"]
    for idx, condition in enumerate(conditions):
        if condition.kind == "switch":
            cases = ", ".join(condition.case_labels) or "(none captured)"
            detail = f"switch ({condition.expression}) cases: {cases}"
        else:
            detail = f"if ({condition.expression}) then: {condition.then_summary[:200]}"
            if condition.else_summary:
                detail += f" else: {condition.else_summary[:200]}"
        lines.append(f"{idx}. {detail}")
    return "\n".join(lines)


async def _classify_method_conditions(
    cls: ClassNode, method: MethodNode, conditions: List[ConditionNode]
) -> Tuple[List[str], List[str], bool]:
    """Returns (kinds, actions, used_llm) — one kind/action per condition, in order."""
    if settings.llm_enabled:
        prompt = _build_prompt(cls, method, conditions)
        parsed = await complete_json(prompt, system=_SYSTEM_PROMPT)

        if isinstance(parsed, list) and len(parsed) == len(conditions):
            try:
                ordered = sorted(parsed, key=lambda item: item.get("index", 0))
                kinds = [str(item.get("kind", "business")) for item in ordered]
                actions = [str(item.get("action") or "(no action returned)").strip() for item in ordered]
                if all(kind in _VALID_KINDS for kind in kinds):
                    logger.info(
                        "logic_extraction: LLM classified %d condition(s) in %s.%s",
                        len(conditions),
                        cls.name,
                        method.name,
                    )
                    return kinds, actions, True
            except (TypeError, AttributeError, ValueError):
                pass

        logger.info(
            "logic_extraction: LLM classification unusable for %s.%s; falling back to heuristic",
            cls.name,
            method.name,
        )

    kinds, actions = _heuristic_classify_method(conditions)
    return kinds, actions, False


class LogicExtractionSubagent(BaseAgent):
    name = "logic_extraction_subagent"

    async def _run(self, context: dict) -> Tuple[Any, float]:
        file_asts: List[FileAST] = context["file_asts"]

        work: List[Tuple[FileAST, ClassNode, MethodNode]] = [
            (file_ast, cls, method)
            for file_ast in file_asts
            for cls in file_ast.classes
            for method in cls.methods
            if method.conditions
        ]
        methods_seen = sum(len(cls.methods) for file_ast in file_asts for cls in file_ast.classes)

        results = await run_bounded(
            [
                (lambda cls=cls, method=method: _classify_method_conditions(cls, method, method.conditions))
                for _file_ast, cls, method in work
            ],
            max_concurrency=settings.max_concurrent_subagents,
        )

        units: List[LogicUnit] = []
        llm_used_count = 0

        for (file_ast, cls, method), result in zip(work, results):
            if isinstance(result, Exception):
                logger.warning(
                    "logic_extraction: classification crashed for %s.%s: %s", cls.name, method.name, result
                )
                kinds, actions = _heuristic_classify_method(method.conditions)
                used_llm = False
            else:
                kinds, actions, used_llm = result

            if used_llm:
                llm_used_count += 1

            method_annotations = [a.name for a in method.annotations] + [a.name for a in cls.annotations]
            for condition, kind, action in zip(method.conditions, kinds, actions):
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
                        extraction_method="llm" if used_llm else "heuristic",
                    )
                )

        if settings.llm_enabled and work:
            logger.info(
                "logic_extraction: %d/%d method(s) with logic classified via LLM (model=%s), %d via heuristic fallback",
                llm_used_count,
                len(work),
                settings.llm_model,
                len(work) - llm_used_count,
            )

        confidence = len(work) / methods_seen if methods_seen else 0.0
        return units, confidence
