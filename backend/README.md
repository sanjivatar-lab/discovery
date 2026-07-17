# Java Codebase Agentic Analyzer

Agentic AI backend (FastAPI) that analyzes large Java codebases and extracts
business rules, functional logic, service dependencies, domain entities, and
workflows/decision trees — using a Supervisor + Subagents harness with
parallel parsing and loop-based (critic-driven) refinement.

## Architecture

```
Supervisor Agent (app/agents/supervisor_agent.py)
  -> chunk codebase (FileChunkingTool)
  -> Parsing Subagents, N in parallel (asyncio + ProcessPoolExecutor, tree-sitter)
  -> Logic Extraction Subagent   -> business/validation/decision conditions
  -> Rule Mining Subagent        -> IF <condition> THEN <action> JSON rules
  -> Dependency Graph Subagent   -> networkx call/service graph
  -> Documentation Subagent      -> markdown docs + mermaid decision trees
  -> Critic Subagent             -> confidence score + weak-area tags
       -> below threshold? selectively re-run only the affected steps
          (app/orchestrator/pipeline.py: RefinementLoop), up to max iterations
  -> persist everything to SQLite (app/memory/sqlite_store.py)
```

An alternative LangGraph-based orchestrator (`app/orchestrator/langgraph_orchestrator.py`)
implements the identical step graph; enable it with `APP_USE_LANGGRAPH=true`
(requires `pip install -r requirements-optional.txt`).

## Running locally

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Or with Docker:

```bash
docker build -t java-agentic-analyzer .
docker run -p 8000:8000 java-agentic-analyzer
```

## Running tests

```bash
pytest
```

## Sample API usage

Kick off analysis from a ZIP of a Java project:

```bash
curl -X POST http://localhost:8000/analyze/codebase \
  -F "file=@/path/to/my-java-project.zip"
```

...or from a git repo:

```bash
curl -X POST http://localhost:8000/analyze/codebase \
  -F "git_url=https://github.com/example/some-java-service.git" \
  -F "branch=main"
```

Both return immediately (analysis runs in the background):

```json
{"analysis_id": "3f9c2b1a...", "status": "pending"}
```

Poll status:

```bash
curl http://localhost:8000/analysis/3f9c2b1a...
```

Once `"status": "completed"`, fetch the results:

```bash
curl http://localhost:8000/rules/3f9c2b1a...
curl http://localhost:8000/dependencies/3f9c2b1a...
curl http://localhost:8000/documentation/3f9c2b1a...
```

## Configuration

All settings are environment variables prefixed `APP_` (see
`app/core/config.py`), e.g.:

| Variable | Default | Purpose |
|---|---|---|
| `APP_MAX_PROCESS_WORKERS` | 4 | Process pool size for tree-sitter parsing |
| `APP_FILES_PER_CHUNK` | 25 | Max files per parsing subagent chunk |
| `APP_CONFIDENCE_THRESHOLD` | 0.75 | Refinement loop stop condition |
| `APP_MAX_REFINEMENT_ITERATIONS` | 3 | Cap on critic-triggered re-runs |
| `APP_LLM_ENABLED` | false | Enable LiteLLM-backed extraction enhancement |
| `APP_USE_LANGGRAPH` | false | Use the LangGraph orchestrator instead of the built-in loop |
| `APP_NEO4J_URI` | "" | Optional: export the dependency graph to Neo4j |

## Bonus features

- **LangGraph orchestrator** — `app/orchestrator/langgraph_orchestrator.py`
- **Neo4j export** — `GraphBuilderTool.export_to_neo4j()` in
  `app/tools/graph_builder_tool.py`
