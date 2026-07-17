"""ParsingSubagent — one instance owns one chunk of files. The supervisor
runs many instances concurrently (asyncio); each instance fans its own
files out across the shared process pool (multiprocessing) since tree-sitter
parsing is CPU-bound. This gives two layers of parallelism: subagent-level
concurrency and process-level parsing throughput."""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Tuple

from app.agents.base import BaseAgent
from app.models.ast_models import FileAST
from app.tools.parallel_execution_tool import run_cpu_bound


def parse_and_extract_file(file_path: str) -> dict:
    """Process-pool worker. Must stay a top-level, picklable function (no
    closures/bound methods) so it works under Windows' `spawn` start method.

    tree-sitter Tree/Node objects cannot cross a process boundary, so both
    parsing AND normalization happen here, in-process, and only the plain
    (picklable) dict is sent back to the parent.
    """
    from app.tools.ast_query_tool import extract_file_ast
    from app.tools.treesitter_parser_tool import get_language, parse_file

    try:
        tree, source = parse_file(file_path)
        file_ast = extract_file_ast(file_path, tree, source, get_language())
        return file_ast.model_dump()
    except Exception as exc:  # noqa: BLE001
        return FileAST(file_path=file_path, parse_errors=[str(exc)], has_syntax_error=True).model_dump()


class ParsingSubagent(BaseAgent):
    def __init__(self, chunk_id: int, file_paths: List[Path]):
        self.name = f"parsing_subagent[{chunk_id}]"
        self.chunk_id = chunk_id
        self.file_paths = file_paths

    async def _run(self, context: dict) -> Tuple[Any, float]:
        results = await run_cpu_bound(parse_and_extract_file, [str(p) for p in self.file_paths])

        file_asts: List[FileAST] = []
        errors = 0
        for result in results:
            if isinstance(result, Exception):
                errors += 1
                continue
            file_ast = FileAST.model_validate(result)
            if file_ast.has_syntax_error:
                errors += 1
            file_asts.append(file_ast)

        confidence = 1.0 if not self.file_paths else max(0.0, 1 - errors / len(self.file_paths))
        return file_asts, confidence
