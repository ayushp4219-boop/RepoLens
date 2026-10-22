# RepoSage 🦉

A local-first AI code intelligence engine that understands codebases with exact file and line citations.

Point RepoSage at any GitHub repository or local directory, ask questions, and receive answers strictly grounded in the source code, complete with verified GitHub permalinks.

---

## Features

1. **File Explanations**: Concise, cached per-file summaries, symbol breakdowns, and dependency mapping.
2. **Call Chain Traces**: Multi-hop call and import graph resolution (`caller -> callee`) with confidence ratings (`resolved` vs `heuristic`).
3. **Grounded Bug Hunting**: Ranks suspect locations in order of likelihood, explains the failure mechanism, presents code evidence, and states uncertainty.
4. **Strict Citation Contract**:
   - Every factual claim about code includes an exact `path:start-end` citation at the indexed commit SHA.
   - Post-generation validator verifies citations against chunks retrieved *in that turn*. Fabrications are rejected; if zero valid citations exist, RepoSage responds *"I couldn't find evidence in the repo"* rather than hallucinating.
   - Appends verified GitHub permalinks (`https://github.com/<owner>/<repo>/blob/<sha>/<path>#L<start>-L<end>`).
5. **Hybrid Search (RAG)**: Merged FTS/keyword scoring (0.4) and dense vector similarity (0.6) with path glob filtering and hard retrieval caps (< 8k tokens per turn).
6. **Local-First & Private**: Runs completely on your machine using Ollama (e.g., `qwen2.5-coder` + `nomic-embed-text`). Repository code is never sent to third-party APIs.
7. **Dual-Backend Storage**: Production-ready PostgreSQL 16 + `pgvector` (HNSW index) + `pg_trgm`, plus a built-in SQLite engine for instant zero-dependency local runs.

---

## Tech Stack

- **Python**: 3.11+
- **Models**: [Ollama](https://ollama.com/) (Chat: `qwen2.5-coder` or `llama3.1`; Embeddings: `nomic-embed-text`)
- **Storage**: PostgreSQL with `pgvector` (HNSW) and `pg_trgm` via `docker-compose.yml`, or standalone SQLite fallback
- **Parsing**: AST symbol extractor (functions, classes, methods, imports, call sites)
- **Interfaces**: CLI (Typer) + REST API (FastAPI)

---

## Quickstart Guide

### 1. Setup Ollama (Local LLM & Embeddings)

Install [Ollama](https://ollama.com/) and download the models:

```bash
# Pull chat and embedding models
ollama pull qwen2.5-coder
ollama pull nomic-embed-text
```

### 2. Start PostgreSQL with pgvector (Optional for Production)

Launch the single-instance database via Docker Compose:

```bash
docker compose up -d
```

> **Note**: If Docker is not running, RepoSage automatically falls back to its built-in SQLite engine, providing immediate zero-setup functionality!

### 3. Install RepoSage

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .
```

---

## CLI Usage

### Indexing a Codebase (`reposage index`)

Clone/scan the repository, parse symbols, extract call graph edges, generate per-file summaries, and build embeddings:

```bash
# Index a remote GitHub repository
reposage index https://github.com/psf/requests.git

# Or index a local directory
reposage index ./path/to/my-project
```

- **Incremental Re-Indexing**: RepoSage hashes file contents (SHA-256). Subsequent index runs instantly skip unchanged files.
- **Guardrails**: Respects `.gitignore`, skips binary files and lockfiles, ignores files > 100KB, and automatically redacts `.env` files and API keys.

---

### Asking Questions (`reposage ask`)

#### 1. Explain a File
```bash
reposage ask ./my-repo "What does auth/middleware.py do?"
```

#### 2. Trace Connections and Call Chains
```bash
reposage ask ./my-repo "How does create_order end up calling the payment gateway?"
```

#### 3. Hunt for Bugs
```bash
reposage ask ./my-repo "Users get logged out after 5 minutes, where might this originate?"
```

---

## Example Output

```text
[*] Analyzing question: "Users get logged out after 5 minutes, where might this originate?"...

============================================================
Mode: BUG-HUNT
============================================================

### Ranked Suspects
1. **Location**: `auth/middleware.py:17-38` (`AuthMiddleware`)
   - **Why Suspect**: Logic in auth/middleware.py:17-38 explicitly enforces a 300-second session expiration timeout (now - session.created_at > 300).
   - **Evidence Present**: Direct expiration check and SessionExpiredError raise at lines 28-35.
   - **Missing Evidence & Uncertainty**: Needs runtime verification of session creation timestamp format.

### Sources
- [auth/middleware.py#L17-L38](https://github.com/example/shop/blob/c0ffee123456/auth/middleware.py#L17-L38)

============================================================
```

---

## REST API (FastAPI)

Launch the background API server:

```bash
reposage serve --port 8000
```

### Endpoints

- `GET /health`: Healthcheck, loaded models, and configuration.
- `POST /index`: Ingest and index a repository.
  ```json
  {
    "repo_url_or_path": "https://github.com/example/repo.git",
    "backend": "sqlite"
  }
  ```
- `POST /ask`: Ask questions and receive grounded answers with citations.
  ```json
  {
    "repo_url_or_path": "https://github.com/example/repo.git",
    "question": "What does auth/middleware.py do?"
  }
  ```
- `GET /audit`: Query audit trail of questions, tool invocations, and answers.

---

## Architecture Overview

```text
CLI / REST API
      │
      ▼
Orchestrator (Question Classification: explain-file | connection | bug-hunt | general)
      │
      ├─► Tool Loop (Max 4 steps, < 8k token budget)
      │     ├─► search_code(query, path_glob?, limit=10)
      │     ├─► get_file_summary(path)
      │     ├─► get_symbol(name_or_path)
      │     ├─► get_callers(symbol) / get_callees(symbol)
      │     └─► read_lines(path, start, end)  [max 200 lines]
      │
      ▼
Ollama LLM (qwen2.5-coder / llama3.1)
      │
      ▼
Citation Validator
      ├─► Checks every cited path:start-end against actually retrieved chunks
      ├─► Rejects hallucinations / fabricated line ranges
      └─► Builds GitHub permalinks (https://github.com/<owner>/<repo>/blob/<sha>/<path>#L<start>-L<end>)
      │
      ▼
Audit Log (Persisted to storage)
```

---

## Running the Test Suite

RepoSage includes 22 automated unit and integration tests covering symbol chunking, call graph edge resolution, hybrid keyword/vector search, strict citation validation, and end-to-end bug hunting on a fixture repo with a planted 5-minute timeout bug:

```bash
python3 -m unittest discover tests -v
```
