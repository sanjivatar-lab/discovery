"""FileChunkingTool — splits a large Java codebase into balanced chunks so
parsing subagents can each own an independent slice of work.

Chunking is size-aware (bytes) as well as count-aware: a handful of very
large files won't get bundled into one overloaded chunk while the rest sit
idle.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Sequence

JAVA_SUFFIX = ".java"


def discover_java_files(root: str | Path) -> List[Path]:
    root = Path(root)
    return sorted(p for p in root.rglob(f"*{JAVA_SUFFIX}") if p.is_file())


def chunk_files(
    files: Sequence[Path],
    files_per_chunk: int = 25,
    max_chunk_bytes: int = 512_000,
) -> List[List[Path]]:
    """Greedily bin-pack files into chunks bounded by both count and total size."""
    chunks: List[List[Path]] = []
    current: List[Path] = []
    current_bytes = 0

    for path in files:
        try:
            size = path.stat().st_size
        except OSError:
            size = 0

        would_overflow_count = len(current) >= files_per_chunk
        would_overflow_bytes = current and (current_bytes + size) > max_chunk_bytes
        if current and (would_overflow_count or would_overflow_bytes):
            chunks.append(current)
            current = []
            current_bytes = 0

        current.append(path)
        current_bytes += size

    if current:
        chunks.append(current)

    return chunks


def plan_chunks(root: str | Path, files_per_chunk: int, max_chunk_bytes: int) -> List[List[Path]]:
    files = discover_java_files(root)
    return chunk_files(files, files_per_chunk=files_per_chunk, max_chunk_bytes=max_chunk_bytes)
