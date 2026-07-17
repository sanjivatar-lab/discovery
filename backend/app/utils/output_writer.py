"""Dumps a SupervisorAgent.analyze() result to a directory as JSON/Markdown
artifacts, for direct inspection outside the API/DB (sample runs, demos,
manual QA)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def write_analysis_output(result: Dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    file_asts = result.get("file_asts", [])
    rules = result.get("rules", [])
    graph = result.get("graph")
    documentation = result.get("documentation", {})

    summary = {
        "file_count": result.get("file_count", 0),
        "class_count": sum(len(f.classes) for f in file_asts),
        "method_count": sum(len(c.methods) for f in file_asts for c in f.classes),
        "rule_count": len(rules),
        "confidence_score": result.get("confidence", 0.0),
        "iterations": result.get("iterations", 0),
        "weak_areas": result.get("weak_areas", []),
    }
    (output_dir / "analysis_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    (output_dir / "file_asts.json").write_text(
        json.dumps([f.model_dump() for f in file_asts], indent=2), encoding="utf-8"
    )
    (output_dir / "rules.json").write_text(
        json.dumps([r.model_dump() for r in rules], indent=2), encoding="utf-8"
    )
    (output_dir / "dependencies.json").write_text(
        json.dumps(
            graph.model_dump() if graph else {"nodes": [], "edges": [], "unresolved_calls": []}, indent=2
        ),
        encoding="utf-8",
    )
    (output_dir / "agent_runs.json").write_text(
        json.dumps(result.get("agent_runs", []), indent=2), encoding="utf-8"
    )

    (output_dir / "documentation.md").write_text(
        documentation.get("documentation_markdown", ""), encoding="utf-8"
    )
    (output_dir / "documentation_flows.json").write_text(
        json.dumps(
            {
                "flow_summaries": documentation.get("flow_summaries", []),
                "decision_trees_mermaid": documentation.get("decision_trees_mermaid", []),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
