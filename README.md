# RepoSage 🦉

An open-source codebase intelligence assistant that analyzes repositories with exact file and line citations, powered by **JarvisLabs Multi-Model Cloud AI** with automatic fallback and local dense embeddings.

Point RepoSage at any GitHub repository or local directory, ask questions, and receive answers strictly grounded in the source code, complete with verified GitHub permalinks.

---

## Architecture & AI System Design

RepoSage features a hybrid AI architecture:
- **Cloud LLM Generation**: High-performance multi-model reasoning via [JarvisLabs AI](https://models.jarvislabs.net) with automatic fallback across 3 frontier models.
- **Local Dense Embeddings**: Private, zero-cost code indexing via local [Ollama](https://ollama.com) (`nomic-embed-text`).
- **Deterministic Guardrails**: Strict citation verification, AST call graph resolution, and deterministic evidence-only fallback.

> [!NOTE]
> **Cloud Inference Notice**: When JarvisLabs is enabled (`REPOSAGE_LLM_PROVIDER=jarvislabs`), prompt text and relevant retrieved code excerpts are sent to JarvisLabs OpenAI-compatible API for generation. Dense vector embeddings and repository indexing remain 100% local on your machine via Ollama.

---

## Multi-Model Automatic Fallback Chain

When answering questions or summarizing files, RepoSage attempts models in a cascading fallback sequence:

```text
               User Query / Summarization
                           │
                           ▼
             ┌───────────────────────────┐
             │  Primary: Gemma 4 31B IT  │
             │     (gemma-4-31b-it)      │
             └─────────────┬─────────────┘
                           │ (on timeout, 429, 5xx, or empty response)
                           ▼
             ┌───────────────────────────┐
             │ Fallback 1: DeepSeek V4.1 │
             │ (deepseek-v4.1-flash-1017)│
             └─────────────┬─────────────┘
                           │ (on timeout, 429, 5xx, or empty response)
                           ▼
             ┌───────────────────────────┐
             │ Fallback 2: GLM-5.3 Flash │
             │      (glm-5.3-flash)      │
             └─────────────┬─────────────┘
                           │ (if all cloud models fail)
                           ▼
             ┌───────────────────────────┐
             │   Deterministic Evidence  │
             │     Offline Fallback      │
             └───────────────────────────┘
```

- **Fail-Fast on Invalid Credentials**: Authentication errors (401/403) fail immediately without retrying subsequent models to prevent wasting calls.
- **Request-Scoped Metadata**: Concurrency-safe tracking returns `model_used`, `attempted_models`, and `fallback_used` in every API and CLI response.
- **Quality-Grounded Check**: Empty or whitespace responses trigger model fallback rather than returning blank answers.

---

## Key Features

1. **Multi-Model JarvisLabs AI**: Reliable cloud LLM generation with automatic fallback (`gemma-4-31b-it` → `deepseek-v4.1-flash-1017` → `glm-5.3-flash`).
2. **Local Dense Embeddings**: Embedding pipeline via Ollama (`nomic-embed-text`) with 768-dimensional vector representations.
3. **File Explanations**: Concise, cached per-file summaries, symbol breakdowns, and dependency mapping.
4. **Call Chain Traces**: Multi-hop call and import graph resolution (`caller -> callee`) with confidence ratings (`resolved` vs `heuristic`).
5. **Grounded Bug Hunting**: Ranks suspect locations in order of likelihood, explains the failure mechanism, presents code evidence, and states uncertainty.
6. **Strict Citation Contract**:
   - Every factual claim about code includes an exact `path:start-end` citation at the indexed commit SHA.
   - Post-generation validator verifies citations against chunks retrieved *in that turn*. Fabrications are rejected; if zero valid citations exist, RepoSage responds *"I couldn't find evidence in the repo"* rather than hallucinating.
   - Appends verified GitHub permalinks (`https://github.com/<owner>/<repo>/blob/<sha>/<path>#L<start>-L<end>`).
7. **Dual-Backend Storage**: Production-ready PostgreSQL 16 + `pgvector` (HNSW index) + `pg_trgm`, plus a built-in SQLite engine for instant zero-dependency local runs.
8. **Interactive Web UI**: Modern dark-mode interface with file tree, code viewer, and real-time model indicator.

---

## Quickstart Guide

### 1. Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com/) (for local embeddings)
- A JarvisLabs API key

### 2. Configure Local Embeddings (Ollama)

Start the Ollama service and download the embedding model:

```bash
ollama serve
ollama pull nomic-embed-text
```

### 3. Create a JarvisLabs API Key

1. Sign up or log in at [JarvisLabs AI](https://models.jarvislabs.net).
2. Generate an API key from your dashboard.
3. Keep the key secure (never commit it to Git).

### 4. Install RepoSage

```bash
# Clone the repository
git clone https://github.com/ayushp4219-boop/RepoSage.git
cd RepoSage

# Create and activate virtual environment
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate
# On Windows PowerShell:
.venv\Scripts\Activate.ps1

# Install dependencies (includes openai SDK and python-dotenv)
pip install -e ".[dev]"
```

### 5. Configure Environment (`.env`)

Copy the template:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
# JarvisLabs Cloud AI Settings
JARVISLABS_API_KEY=your_actual_api_key_here
JARVISLABS_BASE_URL=https://models.jarvislabs.net/v1
REPOSAGE_MODEL_ORDER=gemma-4-31b-it,deepseek-v4.1-flash-1017,glm-5.3-flash
REPOSAGE_LLM_PROVIDER=jarvislabs
REPOSAGE_LLM_TIMEOUT=18

# Local Ollama Settings (for code embeddings)
OLLAMA_BASE_URL=http://localhost:11434
REPOSAGE_EMBEDDING_MODEL=nomic-embed-text
REPOSAGE_EMBEDDING_DIM=768

# Storage backend (sqlite or postgresql)
REPOSAGE_STORAGE_BACKEND=sqlite
```

> [!IMPORTANT]
> `.env` is excluded in `.gitignore`. Never commit API keys or secret files to version control.

---

## Customizing Model Priority

You can change the fallback order at runtime using the `REPOSAGE_MODEL_ORDER` environment variable without modifying Python source code:

```env
# Example: Prioritize GLM-5.3 Flash first, then DeepSeek, then Gemma
REPOSAGE_MODEL_ORDER=glm-5.3-flash,deepseek-v4.1-flash-1017,gemma-4-31b-it
```

---

## CLI Usage

### Indexing a Codebase (`reposage index`)

Clone/scan the repository, parse symbols, extract call graph edges, generate per-file summaries via JarvisLabs, and build local embeddings via Ollama:

```bash
# Index a remote GitHub repository
reposage index https://github.com/psf/requests.git

# Or index a local directory
reposage index ./path/to/my-project
```

- **Incremental Re-Indexing**: RepoSage hashes file contents (SHA-256). Subsequent index runs instantly skip unchanged files.
- **Guardrails**: Respects `.gitignore`, skips binary files and lockfiles, ignores files > 100KB, and automatically redacts secrets.

---

### Asking Questions (`reposage ask`)

Ask questions and see the active model and fallback chain in the terminal:

```bash
# 1. Explain a File
reposage ask ./my-repo "What does auth/middleware.py do?"

# 2. Trace Connections and Call Chains
reposage ask ./my-repo "How does create_order end up calling the payment gateway?"

# 3. Hunt for Bugs
reposage ask ./my-repo "Users get logged out after 5 minutes, where might this originate?"
```

#### CLI Terminal Output Example

```text
[*] Analyzing question: "Users get logged out after 5 minutes, where might this originate?"...

============================================================
Mode: BUG-HUNT
Model: deepseek-v4.1-flash-1017 (fallback)
Attempted: gemma-4-31b-it -> deepseek-v4.1-flash-1017
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

## Running the Web UI and REST API

Start the FastAPI server:

```bash
reposage serve --port 8000
```

Open your browser to:
`http://localhost:8000/`

The web interface features:
- **Interactive File Tree & Code Viewer**
- **Live Model Badge**: Shows which JarvisLabs model answered (e.g. `🤖 gemma-4-31b-it` or `🤖 deepseek-v4.1-flash-1017 · fallback`)
- **Status Bar**: Real-time display of active model and backend configuration

### REST API Endpoints

- `GET /health`: Healthcheck, provider info, and fallback model order:
  ```json
  {
    "status": "ok",
    "version": "0.1.0",
    "llm_provider": "jarvislabs",
    "model_order": ["gemma-4-31b-it", "deepseek-v4.1-flash-1017", "glm-5.3-flash"],
    "chat_model": "gemma-4-31b-it",
    "embedding_model": "nomic-embed-text"
  }
  ```
- `POST /ask`: Ask questions and receive grounded answers with model execution metadata:
  ```json
  {
    "repo_url_or_path": "./my-repo",
    "question": "What does auth/middleware.py do?"
  }
  ```
  Response contains:
  ```json
  {
    "question": "What does auth/middleware.py do?",
    "mode": "explain-file",
    "answer": "...",
    "is_grounded": true,
    "model_used": "gemma-4-31b-it",
    "attempted_models": ["gemma-4-31b-it"],
    "fallback_used": false,
    "sources": [...]
  }
  ```

---

## Running Automated Tests

Run the full automated test suite (all tests use mocks; no real API credits are consumed):

```bash
# Run all tests
pytest -v

# Run only JarvisLabs multi-model fallback tests
pytest tests/test_jarvis_client.py -v
```

Test coverage includes:
- Gemma succeeds (only Gemma called)
- Gemma fails → DeepSeek succeeds
- Gemma & DeepSeek fail → GLM succeeds
- All 3 models fail → graceful fallback
- API timeout triggers fallback
- HTTP 429 and 5xx trigger fallback
- Invalid credentials (401/403) abort immediately without retries
- Empty responses trigger fallback
- Custom model priority from environment variables
- Structured JSON generation for upcoming visual repository explorer
- Preservation of local Ollama embeddings

---

## Troubleshooting

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| **HTTP 401 Unauthorized** | Missing or incorrect `JARVISLABS_API_KEY` | Check `.env` and verify your key at [JarvisLabs](https://models.jarvislabs.net). |
| **HTTP 429 Rate Limit** | Rate limit reached on a specific model | Automatic fallback will seamlessly try the next model in `REPOSAGE_MODEL_ORDER`. |
| **Request Timeout** | Cloud model is taking longer than configured timeout | Increase `REPOSAGE_LLM_TIMEOUT` in `.env` (default is 18s). |
| **Embedding Connection Error** | Ollama is not running on `localhost:11434` | Run `ollama serve` and ensure `ollama pull nomic-embed-text` was run. |
| **All Models Failed** | Outage or lack of internet connectivity | RepoSage automatically provides deterministic evidence-only answers based on retrieved code. |
