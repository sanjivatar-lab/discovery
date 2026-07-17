"""RuleMiningSubagent — converts LogicUnits into structured IF/THEN rules."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.agents.base import BaseAgent
from app.core.config import settings
from app.models.rule_models import LogicUnit, Rule
from app.tools.llm_tool import complete
from app.tools.rule_formatter_tool import format_rule


class RuleMiningSubagent(BaseAgent):
    name = "rule_mining_subagent"

    async def _run(self, context: dict) -> Tuple[Any, float]:
        units: List[LogicUnit] = context.get("logic_units", [])
        rules_by_id: Dict[str, Rule] = {}
        for unit in units:
            rule = format_rule(unit)
            rules_by_id[rule.id] = rule

        rules = list(rules_by_id.values())

        if settings.llm_enabled:
            for rule in rules:
                enhanced = await complete(
                    "Rewrite this business rule as one clear sentence, preserving its "
                    f"meaning exactly and keeping the IF/THEN structure:\n{rule.statement}"
                )
                if enhanced:
                    rule.statement = enhanced

        avg_confidence = sum(r.confidence for r in rules) / len(rules) if rules else 0.0
        return rules, avg_confidence
