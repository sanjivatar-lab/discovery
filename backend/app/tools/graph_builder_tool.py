"""GraphBuilderTool — builds a service/call dependency graph with networkx
from the aggregated, normalized ASTs.

Resolution is intentionally best-effort (name-based, not type-checked
against a full classpath): callee methods are matched first within the
same class, then against any class exposing a method of that name.
Anything that can't be resolved is recorded in `unresolved_calls` rather
than silently dropped, so gaps in coverage stay visible.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import networkx as nx

from app.core.logging import get_logger
from app.models.ast_models import FileAST
from app.models.graph_models import DependencyGraph, GraphEdge, GraphNode

logger = get_logger(__name__)

_SERVICE_ANNOTATIONS = {"Service", "Component", "Repository", "RestController", "Controller"}
_INJECT_ANNOTATIONS = {"Autowired", "Inject", "Resource"}


def build_dependency_graph(file_asts: List[FileAST]) -> DependencyGraph:
    graph = nx.MultiDiGraph()
    class_lookup: Dict[str, FileAST] = {}
    method_owners: Dict[str, List[str]] = {}

    for file_ast in file_asts:
        for cls in file_ast.classes:
            class_lookup[cls.name] = file_ast
            is_service = any(a.name in _SERVICE_ANNOTATIONS for a in cls.annotations)
            graph.add_node(cls.name, label=cls.name, type="service" if is_service else "class")
            for method in cls.methods:
                method_id = f"{cls.name}.{method.name}"
                graph.add_node(method_id, label=method_id, type="method")
                graph.add_edge(cls.name, method_id, type="defines")
                method_owners.setdefault(method.name, []).append(cls.name)

    unresolved: List[str] = []

    for file_ast in file_asts:
        for cls in file_ast.classes:
            if cls.superclass and cls.superclass in class_lookup:
                graph.add_edge(cls.name, cls.superclass, type="extends")
            for iface in cls.interfaces:
                if iface in class_lookup:
                    graph.add_edge(cls.name, iface, type="implements")

            for field in cls.fields:
                if not any(a.name in _INJECT_ANNOTATIONS for a in field.annotations):
                    continue
                target_type = field.type.split("<")[0].strip()
                if target_type in class_lookup:
                    graph.add_edge(cls.name, target_type, type="depends_on")

            for method in cls.methods:
                caller_id = f"{cls.name}.{method.name}"
                for call in method.calls:
                    resolved = False
                    if call.callee_object in ("", "this", "super"):
                        candidate = f"{cls.name}.{call.callee_name}"
                        if graph.has_node(candidate):
                            graph.add_edge(caller_id, candidate, type="calls")
                            resolved = True
                    if not resolved:
                        owners = method_owners.get(call.callee_name, [])
                        if owners:
                            graph.add_edge(caller_id, f"{owners[0]}.{call.callee_name}", type="calls")
                            resolved = True
                    if not resolved:
                        target = f"{call.callee_object + '.' if call.callee_object else ''}{call.callee_name}"
                        unresolved.append(f"{caller_id} -> {target}")

    nodes = [
        GraphNode(id=str(n), label=data.get("label", str(n)), type=data.get("type", "class"))
        for n, data in graph.nodes(data=True)
    ]

    edge_weights: Dict[Tuple[str, str, str], int] = {}
    for u, v, data in graph.edges(data=True):
        key = (str(u), str(v), data.get("type", "calls"))
        edge_weights[key] = edge_weights.get(key, 0) + 1
    edges = [GraphEdge(source=u, target=v, type=t, weight=w) for (u, v, t), w in edge_weights.items()]

    return DependencyGraph(nodes=nodes, edges=edges, unresolved_calls=unresolved[:500])


def export_to_neo4j(graph: DependencyGraph, uri: str, user: str, password: str) -> bool:
    """Optional bonus exporter. No-ops (with a log line) if the `neo4j`
    driver isn't installed or connection settings are blank."""
    if not uri:
        logger.info("Neo4j export skipped: no URI configured")
        return False
    try:
        from neo4j import GraphDatabase
    except ImportError:
        logger.warning("Neo4j export skipped: `neo4j` package not installed")
        return False

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            for node in graph.nodes:
                session.run(
                    "MERGE (n:Node {id: $id}) SET n.label = $label, n.type = $type",
                    id=node.id,
                    label=node.label,
                    type=node.type,
                )
            for edge in graph.edges:
                session.run(
                    "MATCH (a:Node {id: $source}), (b:Node {id: $target}) "
                    "MERGE (a)-[r:RELATES {type: $type}]->(b) SET r.weight = $weight",
                    source=edge.source,
                    target=edge.target,
                    type=edge.type,
                    weight=edge.weight,
                )
    finally:
        driver.close()
    return True
