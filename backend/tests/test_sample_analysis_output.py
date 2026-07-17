"""Runs the full supervisor pipeline against tests/sample_java and persists
the results to backend/output/ (JSON + Markdown), so they can be inspected
directly rather than only asserted on in-memory."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.supervisor_agent import SupervisorAgent
from app.utils.output_writer import write_analysis_output

SAMPLE_DIR = Path(__file__).parent / "sample_java"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

_EXPECTED_FILES = (
    "analysis_summary.json",
    "file_asts.json",
    "rules.json",
    "dependencies.json",
    "agent_runs.json",
    "documentation.md",
    "documentation_flows.json",
)


@pytest.mark.asyncio
async def test_sample_analysis_writes_output_artifacts():
    supervisor = SupervisorAgent()
    result = await supervisor.analyze(SAMPLE_DIR)
    assert result["file_count"] == 3
    assert len(result["rules"]) > 0

    write_analysis_output(result, OUTPUT_DIR)

    for filename in _EXPECTED_FILES:
        path = OUTPUT_DIR / filename
        assert path.exists(), f"missing output artifact: {filename}"
        assert path.stat().st_size > 0, f"output artifact is empty: {filename}"
