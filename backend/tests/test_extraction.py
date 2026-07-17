"""Unit tests for the logic-extraction and rule-mining subagents."""
from pathlib import Path

import pytest

from app.agents.logic_subagent import LogicExtractionSubagent
from app.agents.rule_subagent import RuleMiningSubagent
from app.tools.ast_query_tool import extract_file_ast
from app.tools.treesitter_parser_tool import get_language, parse_file

SAMPLE_DIR = Path(__file__).parent / "sample_java"


def _parse_all():
    file_asts = []
    for path in sorted(SAMPLE_DIR.glob("*.java")):
        tree, source = parse_file(path)
        file_asts.append(extract_file_ast(str(path), tree, source, get_language()))
    return file_asts


@pytest.mark.asyncio
async def test_logic_extraction_classifies_validation_conditions():
    context = {"file_asts": _parse_all()}
    result = await LogicExtractionSubagent().execute(context)

    assert result.success
    assert len(result.output) > 0
    assert any(unit.kind == "validation" for unit in result.output)
    assert any(unit.kind == "decision" for unit in result.output)


@pytest.mark.asyncio
async def test_rule_mining_produces_if_then_statements():
    context = {"file_asts": _parse_all()}
    logic_result = await LogicExtractionSubagent().execute(context)
    context["logic_units"] = logic_result.output

    rule_result = await RuleMiningSubagent().execute(context)

    assert rule_result.success
    rules = rule_result.output
    assert len(rules) > 0
    assert all(r.statement.startswith("IF ") and " THEN " in r.statement for r in rules)
    assert any(r.rule_type == "validation" and r.confidence > 0.5 for r in rules)
