"""SQLite-backed memory store (Phase 1 — see class docstring for the
Phase 2 Postgres+pgvector migration path).

Stores analysis metadata, extracted AST summaries, mined rules, dependency
graphs, generated documentation, and per-agent execution logs (for
observability: duration, success/failure, retries).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

from app.models.analysis_models import AnalysisResult, AnalysisStatus
from app.models.ast_models import FileAST
from app.models.graph_models import DependencyGraph
from app.models.rule_models import Rule

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source TEXT NOT NULL,
    file_count INTEGER DEFAULT 0,
    class_count INTEGER DEFAULT 0,
    method_count INTEGER DEFAULT 0,
    rule_count INTEGER DEFAULT 0,
    confidence_score REAL DEFAULT 0.0,
    iterations INTEGER DEFAULT 0,
    weak_areas TEXT DEFAULT '[]',
    errors TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS file_asts (
    analysis_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    ast_json TEXT NOT NULL,
    PRIMARY KEY (analysis_id, file_path)
);

CREATE TABLE IF NOT EXISTS rules (
    analysis_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    rule_json TEXT NOT NULL,
    PRIMARY KEY (analysis_id, rule_id)
);

CREATE TABLE IF NOT EXISTS graphs (
    analysis_id TEXT PRIMARY KEY,
    graph_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documentation (
    analysis_id TEXT PRIMARY KEY,
    doc_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_runs (
    analysis_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    iteration INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    success INTEGER NOT NULL,
    retries INTEGER DEFAULT 0,
    error TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteStore:
    """Phase 1 memory backend. Swap for a Postgres+pgvector implementation
    behind the same method signatures for Phase 2 semantic-search use cases
    without touching callers."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    async def init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    async def create_analysis(self, analysis: AnalysisResult) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO analyses (id, status, created_at, updated_at, source, file_count, "
                "class_count, method_count, rule_count, confidence_score, iterations, weak_areas, errors) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    analysis.id,
                    analysis.status.value,
                    analysis.created_at,
                    analysis.updated_at,
                    analysis.source,
                    analysis.file_count,
                    analysis.class_count,
                    analysis.method_count,
                    analysis.rule_count,
                    analysis.confidence_score,
                    analysis.iterations,
                    json.dumps(analysis.weak_areas),
                    json.dumps(analysis.errors),
                ),
            )
            await db.commit()

    async def update_status(self, analysis_id: str, status: AnalysisStatus) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE analyses SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, _now(), analysis_id),
            )
            await db.commit()

    async def mark_failed(self, analysis_id: str, error: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT errors FROM analyses WHERE id = ?", (analysis_id,))
            row = await cursor.fetchone()
            errors = json.loads(row[0]) if row and row[0] else []
            errors.append(error)
            await db.execute(
                "UPDATE analyses SET status = ?, updated_at = ?, errors = ? WHERE id = ?",
                (AnalysisStatus.FAILED.value, _now(), json.dumps(errors), analysis_id),
            )
            await db.commit()

    async def finalize_analysis(
        self,
        analysis_id: str,
        status: AnalysisStatus,
        file_count: int,
        class_count: int,
        method_count: int,
        rule_count: int,
        confidence_score: float,
        iterations: int,
        weak_areas: List[str],
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE analyses SET status=?, updated_at=?, file_count=?, class_count=?, method_count=?, "
                "rule_count=?, confidence_score=?, iterations=?, weak_areas=? WHERE id=?",
                (
                    status.value,
                    _now(),
                    file_count,
                    class_count,
                    method_count,
                    rule_count,
                    confidence_score,
                    iterations,
                    json.dumps(weak_areas),
                    analysis_id,
                ),
            )
            await db.commit()

    async def get_analysis(self, analysis_id: str) -> Optional[AnalysisResult]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,))
            row = await cursor.fetchone()
        if row is None:
            return None
        return AnalysisResult(
            id=row["id"],
            status=AnalysisStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            source=row["source"],
            file_count=row["file_count"],
            class_count=row["class_count"],
            method_count=row["method_count"],
            rule_count=row["rule_count"],
            confidence_score=row["confidence_score"],
            iterations=row["iterations"],
            weak_areas=json.loads(row["weak_areas"] or "[]"),
            errors=json.loads(row["errors"] or "[]"),
        )

    async def save_results(
        self,
        analysis_id: str,
        file_asts: List[FileAST],
        rules: List[Rule],
        graph: Optional[DependencyGraph],
        documentation: Dict[str, Any],
        agent_runs: List[dict],
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM file_asts WHERE analysis_id = ?", (analysis_id,))
            for file_ast in file_asts:
                await db.execute(
                    "INSERT INTO file_asts (analysis_id, file_path, ast_json) VALUES (?,?,?)",
                    (analysis_id, file_ast.file_path, file_ast.model_dump_json()),
                )

            await db.execute("DELETE FROM rules WHERE analysis_id = ?", (analysis_id,))
            for rule in rules:
                await db.execute(
                    "INSERT INTO rules (analysis_id, rule_id, rule_json) VALUES (?,?,?)",
                    (analysis_id, rule.id, rule.model_dump_json()),
                )

            if graph is not None:
                await db.execute(
                    "INSERT INTO graphs (analysis_id, graph_json) VALUES (?,?) "
                    "ON CONFLICT(analysis_id) DO UPDATE SET graph_json = excluded.graph_json",
                    (analysis_id, graph.model_dump_json()),
                )

            await db.execute(
                "INSERT INTO documentation (analysis_id, doc_json) VALUES (?,?) "
                "ON CONFLICT(analysis_id) DO UPDATE SET doc_json = excluded.doc_json",
                (analysis_id, json.dumps(documentation)),
            )

            for run in agent_runs:
                await db.execute(
                    "INSERT INTO agent_runs (analysis_id, agent_name, iteration, started_at, duration_ms, "
                    "success, retries, error) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        analysis_id,
                        run["agent_name"],
                        run.get("iteration", 1),
                        _now(),
                        run["duration_ms"],
                        int(bool(run["success"])),
                        run.get("retries", 0),
                        run.get("error"),
                    ),
                )
            await db.commit()

    async def get_rules(self, analysis_id: str) -> List[Rule]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT rule_json FROM rules WHERE analysis_id = ?", (analysis_id,))
            rows = await cursor.fetchall()
        return [Rule.model_validate_json(row[0]) for row in rows]

    async def get_graph(self, analysis_id: str) -> Optional[DependencyGraph]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT graph_json FROM graphs WHERE analysis_id = ?", (analysis_id,))
            row = await cursor.fetchone()
        return DependencyGraph.model_validate_json(row[0]) if row else None

    async def get_documentation(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT doc_json FROM documentation WHERE analysis_id = ?", (analysis_id,))
            row = await cursor.fetchone()
        return json.loads(row[0]) if row else None

    async def get_agent_runs(self, analysis_id: str) -> List[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM agent_runs WHERE analysis_id = ? ORDER BY started_at", (analysis_id,)
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]
