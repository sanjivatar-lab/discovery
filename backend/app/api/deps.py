"""Shared, process-wide singletons for FastAPI dependency injection."""
from __future__ import annotations

from app.core.config import settings
from app.memory.sqlite_store import SQLiteStore

_store: SQLiteStore | None = None


def get_store() -> SQLiteStore:
    global _store
    if _store is None:
        _store = SQLiteStore(settings.database_path)
    return _store
