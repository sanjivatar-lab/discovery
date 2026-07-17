"""Runs the full agentic pipeline against tests/sample_java and writes the
results to backend/output/ — a quick way to see what the system extracts
without going through the HTTP API.

Usage (from backend/):
    python scripts/run_sample_analysis.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.supervisor_agent import SupervisorAgent  # noqa: E402
from app.utils.output_writer import write_analysis_output  # noqa: E402

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "tests" / "sample_java"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


async def main() -> None:
    supervisor = SupervisorAgent()
    result = await supervisor.analyze(SAMPLE_DIR)
    write_analysis_output(result, OUTPUT_DIR)

    print(f"Analyzed {result['file_count']} file(s)")
    print(f"Confidence: {result['confidence']:.2f} (iterations: {result['iterations']})")
    print(f"Rules mined: {len(result['rules'])}")
    if result["weak_areas"]:
        print(f"Weak areas: {result['weak_areas']}")
    print(f"Output written to: {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
