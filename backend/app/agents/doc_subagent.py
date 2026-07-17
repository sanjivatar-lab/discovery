"""DocumentationSubagent — generates functional documentation, per-method
flow summaries, and mermaid decision trees from the mined rules, the
dependency graph, and the normalized ASTs."""
from __future__ import annotations

from typing import Any, List, Tuple

from app.agents.base import BaseAgent
from app.models.ast_models import ConditionNode, FileAST
from app.models.graph_models import DependencyGraph
from app.models.rule_models import Rule


def _decision_tree_mermaid(class_name: str, method_name: str, conditions: List[ConditionNode]) -> str:
    lines = ["graph TD", f'  Start(["{class_name}.{method_name}"])']
    prev = "Start"
    for idx, condition in enumerate(conditions):
        node_id = f"C{idx}"
        label = (condition.expression or "condition").replace('"', "'")[:60]
        lines.append(f'  {prev} --> {node_id}{{{{"{label}"}}}}')
        if condition.kind == "switch" and condition.case_labels:
            for case_idx, case_label in enumerate(condition.case_labels[:6]):
                clean_label = case_label.replace('"', "'")[:40]
                lines.append(f'  {node_id} -->|"{clean_label}"| E{idx}_{case_idx}(["..."])')
        else:
            then_label = (condition.then_summary[:30] or "...").replace('"', "'")
            lines.append(f'  {node_id} -->|"true"| T{idx}(["{then_label}"])')
            if condition.else_summary:
                else_label = condition.else_summary[:30].replace('"', "'")
                lines.append(f'  {node_id} -->|"false"| F{idx}(["{else_label}"])')
        prev = node_id
    return "\n".join(lines)


class DocumentationSubagent(BaseAgent):
    name = "documentation_subagent"

    async def _run(self, context: dict) -> Tuple[Any, float]:
        file_asts: List[FileAST] = context["file_asts"]
        rules: List[Rule] = context.get("rules", [])
        graph: DependencyGraph = context.get("graph") or DependencyGraph()

        sections = ["# Functional Documentation", ""]
        sections.append(
            f"- Files analyzed: {len(file_asts)}\n"
            f"- Classes: {sum(len(f.classes) for f in file_asts)}\n"
            f"- Methods: {sum(len(c.methods) for f in file_asts for c in f.classes)}\n"
            f"- Business rules mined: {len(rules)}\n"
            f"- Dependency edges: {len(graph.edges)} ({len(graph.unresolved_calls)} unresolved)\n"
        )

        flow_summaries: List[str] = []
        decision_trees: List[str] = []

        for file_ast in file_asts:
            for cls in file_ast.classes:
                sections.append(f"\n## {cls.kind.title()} `{cls.name}` ({file_ast.file_path})\n")
                if cls.annotations:
                    sections.append(f"Annotations: {', '.join(a.name for a in cls.annotations)}\n")

                for method in cls.methods:
                    params = ", ".join(f"{p.type} {p.name}" for p in method.params)
                    sections.append(f"- **{method.name}({params})**")

                    if method.calls:
                        calls_summary = ", ".join(
                            f"{c.callee_object + '.' if c.callee_object else ''}{c.callee_name}()"
                            for c in method.calls[:8]
                        )
                        flow = f"{cls.name}.{method.name} calls: {calls_summary}"
                        sections.append(f"  - Flow: {flow}")
                        flow_summaries.append(flow)

                    for rule in rules:
                        if rule.source_class == cls.name and rule.source_method == method.name:
                            sections.append(f"  - Rule: {rule.statement}")

                    if method.conditions:
                        decision_trees.append(_decision_tree_mermaid(cls.name, method.name, method.conditions))

        documentation_markdown = "\n".join(sections)
        coverage = 1.0 if file_asts else 0.0
        output = {
            "documentation_markdown": documentation_markdown,
            "flow_summaries": flow_summaries,
            "decision_trees_mermaid": decision_trees,
        }
        return output, coverage
