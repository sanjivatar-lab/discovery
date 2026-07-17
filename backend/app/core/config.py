"""Central application configuration, loaded from environment variables / .env."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_", extra="ignore")

    app_name: str = "Java Codebase Agentic Analyzer"
    environment: str = "development"

    # Storage
    data_dir: Path = Path("./data")
    upload_dir: Path = Path("./data/uploads")
    database_path: Path = Path("./data/analysis.db")

    # Parallel execution
    max_process_workers: int = 4
    max_concurrent_subagents: int = 8
    files_per_chunk: int = 25
    max_chunk_bytes: int = 512_000

    # Refinement loop
    confidence_threshold: float = 0.75
    max_refinement_iterations: int = 3
    agent_max_retries: int = 2

    # LLM (pluggable via LiteLLM — model-independent: `llm_model` is any
    # LiteLLM model string, e.g. "gpt-4o-mini", "anthropic/claude-3-5-sonnet",
    # "azure/<deployment>", "ollama/llama3"). Disabled by default -> the
    # extraction pipeline stays fully deterministic/heuristic/offline.
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""
    llm_api_base: str = ""
    llm_timeout_seconds: int = 30
    llm_enabled: bool = False

    # Orchestration engine selection
    use_langgraph: bool = False

    # Observability
    otel_enabled: bool = True
    otel_service_name: str = "java-agentic-analyzer"
    otel_console_export: bool = True

    # Optional Neo4j export (bonus)
    neo4j_uri: str = ""
    neo4j_user: str = ""
    neo4j_password: str = ""

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
