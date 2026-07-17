"""Verifies the LLM-assisted logic-extraction and rule-rewrite paths using a
stubbed LLM response — no real network access or API key required. This
proves the LiteLLM wiring is actually exercised (prompts built, responses
parsed, results attributed back to specific LogicUnits/Rules) rather than
just present in code that never runs when APP_LLM_ENABLED=true.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.agents.logic_subagent import LogicExtractionSubagent
from app.agents.rule_subagent import RuleMiningSubagent
from app.core.config import settings
from app.tools.ast_query_tool import extract_file_ast
from app.tools.treesitter_parser_tool import get_language, parse_file

SAMPLE_DIR = Path(__file__).parent / "sample_java"


def _parse(filename: str):
    path = SAMPLE_DIR / filename
    tree, source = parse_file(path)
    return extract_file_ast(str(path), tree, source, get_language())


def _conditions_in_prompt(prompt: str) -> int:
    """Count only the numbered condition entries (a `then`/`else` summary can
    itself contain embedded newlines, so a naive non-blank-line count would
    over-count)."""
    section = prompt.split("Conditions:")[1]
    return len(re.findall(r"^\d+\.", section, re.MULTILINE))


@pytest.mark.asyncio
async def test_logic_extraction_uses_llm_when_enabled(monkeypatch):
    async def fake_complete_json(prompt, system=None, max_tokens=800):
        count = _conditions_in_prompt(prompt)
        return [{"index": i, "kind": "validation", "action": f"llm-generated action {i}"} for i in range(count)]

    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr("app.agents.logic_subagent.complete_json", fake_complete_json)

    context = {"file_asts": [_parse("OrderService.java")]}
    result = await LogicExtractionSubagent().execute(context)

    assert result.success
    units = result.output
    assert len(units) > 0
    assert all(u.extraction_method == "llm" for u in units)
    assert all(u.action.startswith("llm-generated action") for u in units)


@pytest.mark.asyncio
async def test_logic_extraction_falls_back_to_heuristic_on_bad_llm_output(monkeypatch):
    async def fake_complete_json_bad(prompt, system=None, max_tokens=800):
        return {"not": "a list"}  # wrong shape -> must fall back

    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr("app.agents.logic_subagent.complete_json", fake_complete_json_bad)

    context = {"file_asts": [_parse("OrderService.java")]}
    result = await LogicExtractionSubagent().execute(context)

    assert result.success
    units = result.output
    assert len(units) > 0
    assert all(u.extraction_method == "heuristic" for u in units)


@pytest.mark.asyncio
async def test_rule_mining_rewrites_statements_via_llm(monkeypatch):
    async def fake_complete(prompt, system=None, max_tokens=500):
        return "Rewritten: " + prompt.splitlines()[-1]

    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr("app.agents.rule_subagent.complete", fake_complete)

    context = {"file_asts": [_parse("OrderService.java")]}
    logic_result = await LogicExtractionSubagent().execute(context)
    context["logic_units"] = logic_result.output

    rule_result = await RuleMiningSubagent().execute(context)

    assert rule_result.success
    rules = rule_result.output
    assert len(rules) > 0
    assert all(r.statement.startswith("Rewritten: ") for r in rules)
