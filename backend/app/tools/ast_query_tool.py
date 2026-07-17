"""ASTQueryTool — query-based extraction over a parsed tree-sitter CST.

Runs tree-sitter `Query` objects to locate the mandated node types
(class_declaration, method_declaration, if_statement, switch_expression,
method_invocation, annotations), then normalizes each match into the
Pydantic models in `app.models.ast_models` using tree-sitter's stable
field-based node API (`child_by_field_name`), which — unlike the
Query/QueryCursor capture surface — has not changed shape across
tree-sitter-python releases.
"""
from __future__ import annotations

from typing import Iterable, List, Tuple

from tree_sitter import Language, Node, Query, Tree

from app.models.ast_models import (
    Annotation,
    CallNode,
    ClassNode,
    ConditionNode,
    FieldNode,
    FileAST,
    MethodNode,
    MethodParam,
)

CLASS_LIKE_TYPES = {
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
}
_KIND_BY_NODE_TYPE = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "record",
}

CLASS_QUERY = "[(class_declaration) (interface_declaration) (enum_declaration) (record_declaration)] @class"
METHOD_QUERY = "(method_declaration) @method"
IF_QUERY = "(if_statement) @if"
SWITCH_QUERY = "[(switch_expression) (switch_statement)] @switch"
CALL_QUERY = "(method_invocation) @call"
ANNOTATION_QUERY = "[(annotation) (marker_annotation)] @annotation"


def node_text(node: Node | None, source: bytes) -> str:
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def run_query(language: Language, root_node: Node, query_string: str) -> List[Tuple[Node, str]]:
    """Execute a tree-sitter query, returning (node, capture_name) pairs.

    Handles both the modern QueryCursor-based capture API (tree-sitter
    >=0.23, captures returned as a dict of name -> [nodes]) and the legacy
    Query.captures API (list of (node, name) tuples).
    """
    query = Query(language, query_string)
    captures: Iterable
    try:
        from tree_sitter import QueryCursor  # type: ignore

        cursor = QueryCursor(query)
        captures = cursor.captures(root_node)
    except ImportError:
        captures = query.captures(root_node)  # type: ignore[attr-defined]

    results: List[Tuple[Node, str]] = []
    if isinstance(captures, dict):
        for name, nodes in captures.items():
            for node in nodes:
                results.append((node, name))
    else:
        for node, name in captures:  # type: ignore[misc]
            results.append((node, name))
    return results


def collect_by_type(node: Node, types: set[str]) -> List[Node]:
    result: List[Node] = []

    def walk(n: Node) -> None:
        if n.type in types:
            result.append(n)
        for child in n.children:
            walk(child)

    walk(node)
    return result


def _extract_modifiers_and_annotations(node: Node, source: bytes) -> Tuple[List[str], List[Annotation]]:
    modifiers_node = node.child_by_field_name("modifiers")
    if modifiers_node is None:
        for child in node.children:
            if child.type == "modifiers":
                modifiers_node = child
                break

    modifiers: List[str] = []
    annotations: List[Annotation] = []
    if modifiers_node is not None:
        for child in modifiers_node.children:
            if child.type in ("annotation", "marker_annotation"):
                name_node = child.child_by_field_name("name")
                args_node = child.child_by_field_name("arguments")
                annotations.append(
                    Annotation(
                        name=node_text(name_node, source) or node_text(child, source),
                        arguments=node_text(args_node, source),
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                    )
                )
            else:
                text = node_text(child, source).strip()
                if text:
                    modifiers.append(text)
    return modifiers, annotations


def _extract_conditions(body: Node, source: bytes) -> List[ConditionNode]:
    conditions: List[ConditionNode] = []
    for node in collect_by_type(body, {"if_statement"}):
        condition_node = node.child_by_field_name("condition")
        consequence = node.child_by_field_name("consequence")
        alternative = node.child_by_field_name("alternative")
        conditions.append(
            ConditionNode(
                kind="if",
                expression=node_text(condition_node, source).strip("()"),
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                then_summary=node_text(consequence, source)[:160].strip(),
                else_summary=node_text(alternative, source)[:160].strip(),
            )
        )
    for node in collect_by_type(body, {"switch_expression", "switch_statement"}):
        condition_node = node.child_by_field_name("condition")
        switch_body = node.child_by_field_name("body")
        case_labels: List[str] = []
        if switch_body is not None:
            for label_node in collect_by_type(switch_body, {"switch_label"}):
                case_labels.append(node_text(label_node, source).strip())
        conditions.append(
            ConditionNode(
                kind="switch",
                expression=node_text(condition_node, source).strip("()"),
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                case_labels=case_labels[:32],
            )
        )
    return conditions


def _extract_calls(body: Node, caller_method: str, source: bytes) -> List[CallNode]:
    calls: List[CallNode] = []
    for node in collect_by_type(body, {"method_invocation"}):
        name_node = node.child_by_field_name("name")
        object_node = node.child_by_field_name("object")
        if name_node is None:
            continue
        calls.append(
            CallNode(
                caller_method=caller_method,
                callee_object=node_text(object_node, source),
                callee_name=node_text(name_node, source),
                start_line=node.start_point[0] + 1,
            )
        )
    return calls


def _extract_params(method_node: Node, source: bytes) -> List[MethodParam]:
    params_node = method_node.child_by_field_name("parameters")
    params: List[MethodParam] = []
    if params_node is None:
        return params
    for child in params_node.children:
        if child.type not in ("formal_parameter", "spread_parameter"):
            continue
        type_node = child.child_by_field_name("type")
        name_node = child.child_by_field_name("name")
        params.append(
            MethodParam(
                type=node_text(type_node, source) or "Object",
                name=node_text(name_node, source) or "arg",
            )
        )
    return params


def _extract_method(method_node: Node, source: bytes) -> MethodNode:
    name_node = method_node.child_by_field_name("name")
    type_node = method_node.child_by_field_name("type")
    body_node = method_node.child_by_field_name("body")
    modifiers, annotations = _extract_modifiers_and_annotations(method_node, source)
    name = node_text(name_node, source) or "<anonymous>"

    conditions: List[ConditionNode] = []
    calls: List[CallNode] = []
    if body_node is not None:
        conditions = _extract_conditions(body_node, source)
        calls = _extract_calls(body_node, name, source)

    return MethodNode(
        name=name,
        return_type=node_text(type_node, source) or "void",
        modifiers=modifiers,
        params=_extract_params(method_node, source),
        annotations=annotations,
        conditions=conditions,
        calls=calls,
        start_line=method_node.start_point[0] + 1,
        end_line=method_node.end_point[0] + 1,
    )


def _extract_field(field_node: Node, source: bytes) -> List[FieldNode]:
    type_node = field_node.child_by_field_name("type")
    modifiers, annotations = _extract_modifiers_and_annotations(field_node, source)
    fields: List[FieldNode] = []
    for declarator in field_node.children:
        if declarator.type != "variable_declarator":
            continue
        name_node = declarator.child_by_field_name("name")
        fields.append(
            FieldNode(
                type=node_text(type_node, source) or "Object",
                name=node_text(name_node, source) or "field",
                annotations=annotations,
                modifiers=modifiers,
            )
        )
    return fields


def _extract_class(class_node: Node, source: bytes, package: str) -> ClassNode:
    name_node = class_node.child_by_field_name("name")
    superclass_node = class_node.child_by_field_name("superclass")
    interfaces_node = class_node.child_by_field_name("interfaces")
    body_node = class_node.child_by_field_name("body")
    modifiers, annotations = _extract_modifiers_and_annotations(class_node, source)

    superclass = node_text(superclass_node, source).replace("extends", "").strip()
    interfaces_text = node_text(interfaces_node, source).replace("implements", "").strip()
    interfaces = [i.strip() for i in interfaces_text.split(",") if i.strip()]

    methods: List[MethodNode] = []
    fields: List[FieldNode] = []
    if body_node is not None:
        for child in body_node.children:
            if child.type == "method_declaration" or child.type == "constructor_declaration":
                methods.append(_extract_method(child, source))
            elif child.type == "field_declaration":
                fields.extend(_extract_field(child, source))

    return ClassNode(
        name=node_text(name_node, source) or "<anonymous>",
        kind=_KIND_BY_NODE_TYPE.get(class_node.type, "class"),
        package=package,
        superclass=superclass,
        interfaces=interfaces,
        annotations=annotations,
        modifiers=modifiers,
        fields=fields,
        methods=methods,
        start_line=class_node.start_point[0] + 1,
        end_line=class_node.end_point[0] + 1,
    )


def extract_file_ast(file_path: str, tree: Tree, source: bytes, language: Language) -> FileAST:
    root = tree.root_node

    package = ""
    imports: List[str] = []
    for child in root.children:
        if child.type == "package_declaration":
            package = node_text(child, source).replace("package", "").strip().rstrip(";").strip()
        elif child.type == "import_declaration":
            imports.append(node_text(child, source).replace("import", "").strip().rstrip(";").strip())

    class_captures = run_query(language, root, CLASS_QUERY)
    classes = [_extract_class(node, source, package) for node, _ in class_captures]

    parse_errors = [
        f"line {n.start_point[0] + 1}: {node_text(n, source)[:80]!r}"
        for n in collect_by_type(root, {"ERROR"})
    ]

    has_error_attr = getattr(root, "has_error", None)
    syntax_error = bool(has_error_attr()) if callable(has_error_attr) else bool(has_error_attr)

    return FileAST(
        file_path=file_path,
        package=package,
        imports=imports,
        classes=classes,
        parse_errors=parse_errors,
        has_syntax_error=bool(parse_errors) or syntax_error,
    )
