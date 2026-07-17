"""End-to-end test of the supervisor's chunk -> parse (parallel) -> extract
-> critique -> refine pipeline against the sample Java mini-codebase."""
from pathlib import Path

import pytest

from app.agents.supervisor_agent import SupervisorAgent

SAMPLE_DIR = Path(__file__).parent / "sample_java"


@pytest.mark.asyncio
async def test_end_to_end_analysis_on_sample_java():
    supervisor = SupervisorAgent()
    result = await supervisor.analyze(SAMPLE_DIR)

    assert result["file_count"] == 3
    assert len(result["file_asts"]) == 3
    assert all(not f.has_syntax_error for f in result["file_asts"])

    assert len(result["rules"]) > 0

    assert result["graph"] is not None
    assert len(result["graph"].nodes) > 0
    assert any(e.type == "calls" for e in result["graph"].edges)

    assert result["documentation"]["documentation_markdown"]
    assert "OrderService" in result["documentation"]["documentation_markdown"]

    assert result["confidence"] > 0.0
    assert result["iterations"] >= 1


@pytest.mark.asyncio
async def test_analysis_on_empty_directory_reports_no_files(tmp_path):
    supervisor = SupervisorAgent()
    result = await supervisor.analyze(tmp_path)

    assert result["file_count"] == 0
    assert result["confidence"] == 0.0
    assert result["weak_areas"]
