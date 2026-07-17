"""RuleMiningSubagent — converts LogicUnits into structured IF/THEN rules.

When `APP_LLM_ENABLED=true`, each rule's statement is additionally rewritten
by an LLM (model-independent via LiteLLM — see app/tools/llm_tool.py) into a
more naturally-worded sentence, run concurrently across rules and bounded by
`APP_MAX_CONCURRENT_SUBAGENTS`. A rule whose rewrite fails or is disabled
just keeps its heuristic `IF <condition> THEN <action>` statement.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.agents.base import BaseAgent
from app.core.config import settings
from app.core.logging import get_logger
from app.models.rule_models import LogicUnit, Rule
from app.tools.llm_tool import complete
from app.tools.parallel_execution_tool import run_bounded
from app.tools.rule_formatter_tool import format_rule

logger = get_logger(__name__)

_REWRITE_PROMPT_TEMPLATE = (
    "Rewrite this business rule as one clear sentence, preserving its meaning "
    "exactly and keeping the IF/THEN structure:\n{statement}"
)


class RuleMiningSubagent(BaseAgent):
    name = "rule_mining_subagent"

    async def _run(self, context: dict) -> Tuple[Any, float]:
        units: List[LogicUnit] = context.get("logic_units", [])
        rules_by_id: Dict[str, Rule] = {}
        for unit in units:
            rule = format_rule(unit)
            rules_by_id[rule.id] = rule

        rules = list(rules_by_id.values())

        if settings.llm_enabled and rules:
            rewrites = await run_bounded(
                [
                    (lambda r=rule: complete(_REWRITE_PROMPT_TEMPLATE.format(statement=r.statement)))
                    for rule in rules
                ],
                max_concurrency=settings.max_concurrent_subagents,
            )
            rewritten_count = 0
            for rule, rewrite in zip(rules, rewrites):
                if isinstance(rewrite, str) and rewrite.strip():
                    rule.statement = rewrite.strip()
                    rewritten_count += 1
            logger.info(
                "rule_mining: %d/%d rule statement(s) rewritten via LLM (model=%s)",
                rewritten_count,
                len(rules),
                settings.llm_model,
            )

        avg_confidence = sum(r.confidence for r in rules) / len(rules) if rules else 0.0
        return rules, avg_confidence
