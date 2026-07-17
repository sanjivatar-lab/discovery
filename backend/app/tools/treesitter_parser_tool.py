"""TreeSitterParserTool — mandatory Tree-sitter based Java parsing.

Wraps the `tree_sitter` Python bindings + the `tree_sitter_java` prebuilt
grammar. The tree-sitter binding API has shifted across versions (Language
construction, Parser construction, Query/QueryCursor split); the helpers here
are written defensively so the tool keeps working across the 0.21-0.23+
range without the rest of the codebase needing to know which one is active.
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

import tree_sitter_java as tsjava
from tree_sitter import Language, Parser, Tree

_LANGUAGE: Language | None = None
_PARSER: Parser | None = None


def get_language() -> Language:
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = Language(tsjava.language())
    return _LANGUAGE


def get_parser() -> Parser:
    """Lazily build (and cache) a Java Parser instance for this process."""
    global _PARSER
    if _PARSER is None:
        language = get_language()
        try:
            _PARSER = Parser(language)
        except TypeError:
            # Older tree-sitter bindings (<0.22) construct a bare Parser and
            # attach the language separately.
            _PARSER = Parser()
            _PARSER.set_language(language)  # type: ignore[attr-defined]
    return _PARSER


def parse_source(source: str) -> Tuple[Tree, bytes]:
    source_bytes = source.encode("utf-8")
    tree = get_parser().parse(source_bytes)
    return tree, source_bytes


def parse_file(path: str | Path) -> Tuple[Tree, bytes]:
    source_bytes = Path(path).read_bytes()
    tree = get_parser().parse(source_bytes)
    return tree, source_bytes


def tree_has_error(tree: Tree) -> bool:
    root = tree.root_node
    attr = getattr(root, "has_error", None)
    if callable(attr):
        return bool(attr())
    if attr is not None:
        return bool(attr)
    return "ERROR" in root.sexp()  # pragma: no cover - last-resort fallback
