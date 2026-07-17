"""FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.deps import get_store
from app.api.routes import router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.telemetry import setup_telemetry
from app.tools.parallel_execution_tool import shutdown_process_pool

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    setup_telemetry()
    await get_store().init_db()
    logger.info("%s starting up (env=%s)", settings.app_name, settings.environment)
    yield
    shutdown_process_pool()
    logger.info("%s shut down", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description=(
        "Agentic AI system that analyzes large Java codebases and extracts business rules, "
        "functional logic, service dependencies, domain entities, and workflows/decision trees."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name}
