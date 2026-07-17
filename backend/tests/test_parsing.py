"""Unit tests for the mandatory Tree-sitter parsing + query-based extraction."""
from pathlib import Path

from app.tools.ast_query_tool import extract_file_ast
from app.tools.treesitter_parser_tool import get_language, parse_file

SAMPLE_DIR = Path(__file__).parent / "sample_java"


def _extract(filename: str):
    file_path = SAMPLE_DIR / filename
    tree, source = parse_file(file_path)
    return extract_file_ast(str(file_path), tree, source, get_language())


def test_parse_order_service_extracts_class_and_methods():
    file_ast = _extract("OrderService.java")

    assert not file_ast.has_syntax_error
    assert file_ast.package == "com.example.orders"
    assert len(file_ast.classes) == 1

    order_service = file_ast.classes[0]
    assert order_service.name == "OrderService"
    assert any(a.name == "Service" for a in order_service.annotations)

    method_names = {m.name for m in order_service.methods}
    assert {"placeOrder", "describeStatus"}.issubset(method_names)

    place_order = next(m for m in order_service.methods if m.name == "placeOrder")
    assert len(place_order.conditions) >= 2
    assert any(c.kind == "if" for c in place_order.conditions)

    describe_status = next(m for m in order_service.methods if m.name == "describeStatus")
    switch_conditions = [c for c in describe_status.conditions if c.kind == "switch"]
    assert switch_conditions
    assert len(switch_conditions[0].case_labels) >= 3


def test_parse_inventory_service_extracts_method_calls():
    file_ast = _extract("InventoryService.java")
    cls = file_ast.classes[0]

    reserve_stock = next(m for m in cls.methods if m.name == "reserveStock")
    callee_names = {c.callee_name for c in reserve_stock.calls}
    assert "lookupStock" in callee_names
    assert "notifyLowStock" in callee_names


def test_parse_controller_extracts_field_annotations():
    file_ast = _extract("OrderController.java")
    cls = file_ast.classes[0]

    order_service_field = next(f for f in cls.fields if f.name == "orderService")
    assert any(a.name == "Autowired" for a in order_service_field.annotations)
