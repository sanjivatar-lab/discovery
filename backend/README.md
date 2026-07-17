# Java Codebase Agentic Analyzer — User Manual

An agentic backend (FastAPI) that reads a Java codebase and hands back three
things: the **business rules** hidden in its `if`/`switch` logic, a **map of
which services/methods call which**, and **generated documentation** with
decision-flow diagrams. It works using a Supervisor + Subagents harness with
parallel Tree-sitter parsing and a critic-driven refinement loop.

Looking for a plain-English, non-technical explanation instead? See
[`PRD.md`](PRD.md). This document is the operator's manual — how to install,
run, and use the application.

---

## Table of contents

1. [Prerequisites](#1-prerequisites)
2. [Installation](#2-installation)
3. [Starting the application](#3-starting-the-application)
4. [Confirming it's running](#4-confirming-its-running)
5. [Using the application, step by step](#5-using-the-application-step-by-step)
6. [Understanding the output](#6-understanding-the-output)
7. [Try it without your own code](#7-try-it-without-your-own-code)
8. [Enabling AI-assisted extraction (optional)](#8-enabling-ai-assisted-extraction-optional)
9. [Configuration reference](#9-configuration-reference)
10. [Advanced / optional features](#10-advanced--optional-features)
11. [Running the automated tests](#11-running-the-automated-tests)
12. [Troubleshooting](#12-troubleshooting)
13. [Project layout](#13-project-layout)
14. [Architecture reference](#14-architecture-reference)

---

## 1. Prerequisites

- **Python 3.10+**
- **git** — only needed if you plan to submit codebases by Git URL rather
  than ZIP upload (the app shells out to your machine's `git`)
- **Docker** — optional, only needed if you'd rather run the app in a
  container than install Python dependencies directly

## 2. Installation

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

This installs everything the mandatory pipeline needs (FastAPI, tree-sitter,
networkx, aiosqlite, OpenTelemetry, pytest). Optional add-ons — the LLM
provider library, LangGraph, Neo4j — live in `requirements-optional.txt` and
are covered in their own sections below; skip that file unless you're
enabling one of those features.

## 3. Starting the application

**Option A — directly:**

```bash
uvicorn app.main:app --reload
```

The `--reload` flag auto-restarts the server on code changes; drop it in
production.

**Option B — Docker:**

```bash
docker build -t java-agentic-analyzer .
docker run -p 8000:8000 java-agentic-analyzer
```

Either way, the API is now listening on **http://localhost:8000**.

## 4. Confirming it's running

```bash
curl http://localhost:8000/health
# {"status": "ok", "app": "Java Codebase Agentic Analyzer"}
```

FastAPI also generates an interactive API explorer automatically — open
**http://localhost:8000/docs** in a browser. Every endpoint below can be
tried directly from that page (click an endpoint → "Try it out" → fill in
the fields → "Execute") without needing `curl` or Postman at all.

## 5. Using the application, step by step

### Step 1 — Prepare a codebase to analyze

You can point the analyzer at either:

- **A ZIP file** containing `.java` files (any folder structure — it
  recursively finds every `*.java` file inside), or
- **A Git repository URL** (public, or one your machine's `git` already has
  credentials for) — this is cloned with `--depth 1` (shallow clone; history
  isn't needed).

### Step 2 — Submit it for analysis

Pick one:

```bash
# From a ZIP file
curl -X POST http://localhost:8000/analyze/codebase \
  -F "file=@/path/to/my-java-project.zip"
```

```bash
# From a Git repo
curl -X POST http://localhost:8000/analyze/codebase \
  -F "git_url=https://github.com/example/some-java-service.git" \
  -F "branch=main"
```

`branch` is optional (defaults to the repo's default branch). Provide
exactly one of `file` or `git_url` — not both.

The request returns **immediately** — analysis runs in the background, so
this call never blocks on large codebases:

```json
{"analysis_id": "3f9c2b1a5e7d4c8a9b1f2e3d4c5b6a7f", "status": "pending"}
```

Save that `analysis_id` — every other step uses it.

### Step 3 — Check analysis status

```bash
curl http://localhost:8000/analysis/3f9c2b1a5e7d4c8a9b1f2e3d4c5b6a7f
```

```json
{
  "id": "3f9c2b1a...",
  "status": "completed",
  "file_count": 3,
  "class_count": 3,
  "method_count": 8,
  "rule_count": 8,
  "confidence_score": 0.77,
  "iterations": 1,
  "weak_areas": ["dependencies:16 call(s) could not be resolved to a known method"],
  "errors": []
}
```

`status` moves through `pending` → `parsing` → (internally: extracting →
critiquing → possibly refining) → `completed` or `failed`. Poll this
endpoint every second or two until it reaches a terminal state. There is no
webhook/notification — polling is the intended integration pattern for now.

### Step 4 — Retrieve the business rules

```bash
curl http://localhost:8000/rules/3f9c2b1a5e7d4c8a9b1f2e3d4c5b6a7f
```

Returns every mined `IF <condition> THEN <action>` rule, with its source
file/class/method and a confidence score. See [§6](#6-understanding-the-output)
for the full field reference.

### Step 5 — Retrieve the dependency graph

```bash
curl http://localhost:8000/dependencies/3f9c2b1a5e7d4c8a9b1f2e3d4c5b6a7f
```

Returns nodes (classes/methods/services) and edges (`calls` / `depends_on` /
`extends` / `implements`), plus a list of calls it couldn't confidently
resolve.

### Step 6 — Retrieve the documentation

```bash
curl http://localhost:8000/documentation/3f9c2b1a5e7d4c8a9b1f2e3d4c5b6a7f
```

Returns a Markdown write-up per class/method, a list of one-line call-flow
summaries, and Mermaid `graph TD` decision-tree diagrams (paste any of them
into a Mermaid renderer — e.g. the Mermaid Live Editor, or a Markdown viewer
that supports Mermaid fences — to see it visually).

## 6. Understanding the output

**`/analysis/{id}`**

| Field | Meaning |
|---|---|
| `status` | `pending` / `parsing` / `completed` / `failed` |
| `file_count` / `class_count` / `method_count` | What was found in the codebase |
| `rule_count` | Total business rules mined |
| `confidence_score` | 0–1 self-assessed quality score (see PRD §7) |
| `iterations` | How many refinement passes the critic triggered |
| `weak_areas` | Tagged gaps the critic flagged, e.g. `parsing:...`, `dependencies:...` |
| `errors` | Unexpected failures (should be empty for a healthy run) |

**`/rules/{id}` — each rule**

| Field | Meaning |
|---|---|
| `statement` | The full `IF ... THEN ...` sentence |
| `rule_type` | `validation` (guards bad input), `business` (a business decision), or `decision` (a switch/multi-way branch) |
| `condition` / `action` | The two halves of the statement, separately |
| `source_class` / `source_method` / `source_file` | Where it came from |
| `confidence` | 0–1, higher for clear validation/exception patterns |
| `extraction_method` | `"heuristic"` (rule-based) or `"llm"` (AI-assisted, only when enabled — see §8) |

**`/dependencies/{id}`**

| Field | Meaning |
|---|---|
| `nodes[].type` | `class`, `service` (annotated `@Service`/`@Component`/`@RestController`/etc.), or `method` |
| `edges[].type` | `calls`, `depends_on` (field injection), `extends`, `implements` |
| `edges[].weight` | Number of times that exact call/relationship occurs |
| `unresolved_calls` | Calls the analyzer found but couldn't confidently match to a known method (common for calls through method parameters rather than a service's own fields — see PRD §8) |

**`/documentation/{id}`**

| Field | Meaning |
|---|---|
| `documentation_markdown` | Full per-class/method write-up |
| `flow_summaries` | One line per method listing what it calls |
| `decision_trees_mermaid` | One Mermaid diagram per method that has conditional logic |

## 7. Try it without your own code

The project ships with a small 3-file sample Java "place an order" mini-app
under `tests/sample_java/`. Two ways to see the full pipeline run against it
without uploading anything:

**Run the standalone script** — prints a summary and writes the same
artifacts you'd get from the API into `backend/output/`:

```bash
python scripts/run_sample_analysis.py
```

```
Analyzed 3 file(s)
Confidence: 0.77 (iterations: 1)
Rules mined: 8
Output written to: backend/output
```

Inspect `output/rules.json`, `output/dependencies.json`, and
`output/documentation.md` directly afterward.

**Or run it through pytest** (also writes to `output/`, plus asserts the
result is sane):

```bash
pytest tests/test_sample_analysis_output.py -v
```

## 8. Enabling AI-assisted extraction (optional)

By default, classifying each `if`/`switch` condition (validation vs
business vs decision) and writing its plain-English action is done by a
**deterministic keyword heuristic** — no AI model, no network call. You can
optionally hand that step to an LLM instead, for more nuanced wording and
classification.

This is **off by default** (`APP_LLM_ENABLED=false`); nothing below runs
unless you turn it on, and the automated tests never require it.

```bash
pip install -r requirements-optional.txt   # installs litellm
export APP_LLM_ENABLED=true
export APP_LLM_MODEL=gpt-4o-mini           # any LiteLLM model string
export APP_LLM_API_KEY=sk-...
```

`APP_LLM_MODEL` is forwarded straight to `litellm.acompletion` — swapping
providers is a config change, not a code change:

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
  action. Every method is classified concurrently (bounded by
  `APP_MAX_CONCURRENT_SUBAGENTS`).
- `RuleMiningSubagent` (`app/agents/rule_subagent.py`) optionally rewrites
  each mined rule's statement into more natural wording, also concurrently.
- Every rule's `extraction_method` field tells you which path actually
  produced it (see §6) — check this if you want to confirm the LLM is
  really being used rather than silently falling back.
- If a call fails, times out, or returns something that doesn't parse as
  the expected JSON shape, that specific method/rule falls back to the
  heuristic — logged, and never fatal to the whole analysis.
- `tests/test_llm_logic_extraction.py` exercises both the LLM path and the
  fallback path using a stubbed response, so you can see the exact prompt
  shape without spending API credits.

## 9. Configuration reference

All settings are environment variables prefixed `APP_` (see
`app/core/config.py`):

| Variable | Default | Purpose |
|---|---|---|
| `APP_MAX_PROCESS_WORKERS` | 4 | Process pool size for tree-sitter parsing |
| `APP_FILES_PER_CHUNK` | 25 | Max files per parsing subagent chunk |
| `APP_MAX_CONCURRENT_SUBAGENTS` | 8 | Concurrency cap for subagents/LLM calls |
| `APP_CONFIDENCE_THRESHOLD` | 0.75 | Refinement loop stop condition |
| `APP_MAX_REFINEMENT_ITERATIONS` | 3 | Cap on critic-triggered re-runs |
| `APP_LLM_ENABLED` | false | Turn on LLM-based logic classification + rule rewriting (§8) |
| `APP_LLM_MODEL` | `gpt-4o-mini` | Any LiteLLM model string |
| `APP_LLM_API_KEY` | "" | Provider API key (not needed for local providers like Ollama) |
| `APP_LLM_API_BASE` | "" | Custom endpoint (Azure deployment URL, local Ollama server, ...) |
| `APP_LLM_TIMEOUT_SECONDS` | 30 | Per-call LLM timeout before falling back to heuristics |
| `APP_USE_LANGGRAPH` | false | Use the LangGraph orchestrator instead of the built-in loop |
| `APP_NEO4J_URI` | "" | Optional: export the dependency graph to Neo4j |
| `APP_DATABASE_PATH` | `./data/analysis.db` | SQLite file location |
| `APP_UPLOAD_DIR` | `./data/uploads` | Where uploaded ZIPs / cloned repos are staged |

## 10. Advanced / optional features

- **LangGraph orchestrator** (`app/orchestrator/langgraph_orchestrator.py`)
  — the identical pipeline expressed as a LangGraph `StateGraph` instead of
  the built-in refinement loop. Enable with `APP_USE_LANGGRAPH=true` after
  `pip install -r requirements-optional.txt`.
- **Neo4j export** (`GraphBuilderTool.export_to_neo4j()` in
  `app/tools/graph_builder_tool.py`) — pushes the dependency graph into a
  Neo4j instance for advanced graph querying. Set `APP_NEO4J_URI`,
  `APP_NEO4J_USER`, `APP_NEO4J_PASSWORD` and call it directly (not yet wired
  to an API endpoint).

## 11. Running the automated tests

```bash
pytest
```

Runs parsing, logic-extraction, rule-mining, dependency-graph, end-to-end
orchestration, and LLM-wiring tests (with the LLM stubbed, so no network/API
key is needed) against the bundled sample Java files.

## 12. Troubleshooting

**Analysis is stuck on `pending` or `parsing`.**
Check the server logs — the background task logs each subagent's
start/success/failure. If the process itself crashed, `/analysis/{id}` will
never update; restart the server and resubmit.

**`status: "failed"` with an entry in `errors`.**
Read the error message — most commonly a bad ZIP (`Invalid ZIP archive`) or
a failed `git clone` (private repo without credentials, wrong URL, network
issue).

**`confidence_score` is lower than expected, with a `dependencies:...` weak
area.** This is usually expected, not a bug: the dependency resolver is
name-based, not a full type checker, so calls through method parameters
(e.g. `order.getSku()` where `order` is data, not a service) are reported as
unresolved rather than guessed. See PRD §8.

**I turned on `APP_LLM_ENABLED` but rules still show
`"extraction_method": "heuristic"`.** Check, in order: (1)
`requirements-optional.txt` installed (`litellm` importable), (2)
`APP_LLM_API_KEY` set (unless using a keyless local provider), (3) server
logs for `LLM classification unusable ... falling back to heuristic` —
that means a call went out but the response didn't parse; check
`APP_LLM_MODEL` is a valid LiteLLM model string for your provider.

**Windows: multiprocessing / parsing seems to hang or behaves oddly when run
from a custom script.** The parsing subagents use a `ProcessPoolExecutor`,
which on Windows requires the process that creates it to be the real
`__main__` entry point. Running via `uvicorn`, `pytest`, or
`scripts/run_sample_analysis.py` (all provided) is safe; if you embed the
supervisor in your own script, guard your entry point with
`if __name__ == "__main__":`.

**No rules/classes found for a codebase I know has logic in it.**
Confirm the ZIP actually contains `.java` files at some depth (the analyzer
recursively searches for `*.java`, but an incorrectly-zipped folder — e.g.
zipping the parent of your project instead of the project itself — is a
common mistake). Check `/analysis/{id}`'s `file_count`.

## 13. Project layout

```
backend/
├── app/
│   ├── main.py              FastAPI app entrypoint
│   ├── api/                 HTTP routes + dependency wiring
│   ├── core/                config, logging, OpenTelemetry setup
│   ├── agents/               Supervisor + 6 subagents
│   ├── tools/                Tree-sitter parsing, chunking, parallel exec,
│   │                          graph building, rule formatting, LLM client
│   ├── orchestrator/         Refinement-loop engine + LangGraph variant
│   ├── memory/               SQLite persistence
│   ├── models/                Pydantic domain models (AST/rules/graph/analysis)
│   ├── schemas/               API request/response schemas
│   └── utils/                 Repo ingestion, ID generation, output writer
├── scripts/
│   └── run_sample_analysis.py  Standalone CLI demo runner
├── tests/
│   ├── sample_java/            3-file sample "place an order" mini-app
│   └── test_*.py               Unit + end-to-end tests
├── output/                     Generated artifacts from sample runs
├── requirements.txt             Mandatory dependencies
├── requirements-optional.txt    LLM / LangGraph / Neo4j add-ons
├── Dockerfile
├── PRD.md                       Plain-English product explanation
└── README.md                    This document
```

## 14. Architecture reference

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

Every step's timing, success/failure, and retry count is traced via
OpenTelemetry and logged (`app/core/telemetry.py`), and persisted per-run in
the `agent_runs` SQLite table — useful for diagnosing exactly which stage a
given analysis spent its time in, or failed at.
