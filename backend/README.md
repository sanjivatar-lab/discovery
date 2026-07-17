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

## LLM usage (model-independent via LiteLLM)

Classification of each `if`/`switch` condition (validation vs business vs
decision) and its plain-English action, plus the final rule wording, can be
done by an LLM instead of the built-in keyword heuristic. This is **off by
default** (`APP_LLM_ENABLED=false`) so the pipeline stays deterministic and
network-free; when off, everything below is skipped entirely and only the
heuristic path runs (this is what the tests exercise, so they never need
network access or an API key).

Enable it:

```bash
pip install -r requirements-optional.txt   # installs litellm
export APP_LLM_ENABLED=true
export APP_LLM_MODEL=gpt-4o-mini           # any LiteLLM model string
export APP_LLM_API_KEY=sk-...
```

`APP_LLM_MODEL` is passed straight through to `litellm.acompletion` — swap
providers by changing this one string, no code changes:

| Provider | Example `APP_LLM_MODEL` |
|---|---|
| OpenAI | `gpt-4o-mini` |
| Anthropic | `anthropic/claude-3-5-sonnet-20241022` |
| Azure OpenAI | `azure/<your-deployment-name>` (+ `APP_LLM_API_BASE`) |
| Local Ollama | `ollama/llama3` (+ `APP_LLM_API_BASE=http://localhost:11434`) |

What actually happens when it's on:

- `LogicExtractionSubagent` (`app/agents/logic_subagent.py`) sends one
  prompt per method (batching all of that method's conditions into a
  single call) asking the LLM to classify each condition and describe its
  action — see `_SYSTEM_PROMPT`/`_build_prompt` in that file. Every method
  is classified concurrently (bounded by `APP_MAX_CONCURRENT_SUBAGENTS`).
- `RuleMiningSubagent` (`app/agents/rule_subagent.py`) optionally rewrites
  each mined rule's `IF ... THEN ...` statement into a more natural
  sentence, also concurrently.
- Every LogicUnit/Rule carries an `extraction_method` field (`"llm"` or
  `"heuristic"`) so you can see, per rule, which path actually produced
  it — visible in `/rules/{id}` and in `output/rules.json`.
- If the LLM call fails, times out, or returns something that doesn't
  parse as the expected JSON shape, that specific method/rule silently
  falls back to the heuristic — one bad LLM response never fails the
  whole analysis. Every fallback is logged (`app.agents.logic_subagent` /
  `app.agents.rule_subagent` loggers).
- `tests/test_llm_logic_extraction.py` exercises both the LLM and the
  fallback path using a stubbed LLM response (no real network/API key
  needed) — read it to see the exact call shape without spending API
  credits.

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
| `APP_LLM_ENABLED` | false | Turn on LLM-based logic classification + rule rewriting (see "LLM usage" above) |
| `APP_LLM_MODEL` | `gpt-4o-mini` | Any LiteLLM model string (OpenAI/Anthropic/Azure/Ollama/etc.) |
| `APP_LLM_API_KEY` | "" | Provider API key (not needed for local providers like Ollama) |
| `APP_LLM_API_BASE` | "" | Custom endpoint (Azure deployment URL, local Ollama server, ...) |
| `APP_LLM_TIMEOUT_SECONDS` | 30 | Per-call LLM timeout before falling back to heuristics |
| `APP_USE_LANGGRAPH` | false | Use the LangGraph orchestrator instead of the built-in loop |
| `APP_NEO4J_URI` | "" | Optional: export the dependency graph to Neo4j |

## Bonus features

- **LangGraph orchestrator** — `app/orchestrator/langgraph_orchestrator.py`
- **Neo4j export** — `GraphBuilderTool.export_to_neo4j()` in
  `app/tools/graph_builder_tool.py`
