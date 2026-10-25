"""Thin REST API service for RepoSage (FastAPI with standard library fallback)."""

import json
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse, HTMLResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
except ImportError:
    FastAPI = None
    BaseModel = object
    FileResponse = None
    HTMLResponse = None

from reposage.agent.orchestrator import RepoSageOrchestrator
from reposage.cli import run_indexing
from reposage.config import settings
from reposage.models.ollama_client import OllamaClient
from reposage.retrieval.store import get_store

# Path to the bundled static UI
STATIC_DIR = Path(__file__).parent / "static"
UI_INDEX   = STATIC_DIR / "index.html"


def execute_index_request(repo_url_or_path: str, backend: Optional[str] = None) -> Dict[str, Any]:
    repo_id = run_indexing(repo_url_or_path, backend=backend)
    return {"status": "indexed", "repo_id": repo_id, "target": repo_url_or_path}


def execute_ask_request(repo_url_or_path: str, question: str, backend: Optional[str] = None) -> Dict[str, Any]:
    store = get_store(backend)
    target_path = Path(repo_url_or_path)
    url_to_lookup = str(target_path.resolve()) if target_path.exists() else repo_url_or_path

    repo = store.get_repo(url_to_lookup)
    if not repo:
        repo_id = run_indexing(repo_url_or_path, backend=backend)
        repo = store.get_repo(url_to_lookup)
    else:
        repo_id = repo["id"]

    orchestrator = RepoSageOrchestrator(
        store=store,
        repo_id=repo_id,
    )

    response = orchestrator.run(question)
    return {
        "question": response.question,
        "mode": response.mode,
        "answer": response.answer,
        "is_grounded": response.validation.is_grounded,
        "tool_calls": response.tool_calls,
        "retrieved_citations": response.retrieved_citations,
        "model_used": response.model_used,
        "attempted_models": response.attempted_models,
        "fallback_used": response.fallback_used,
        "sources": [
            {
                "file_path": c.file_path,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "permalink": c.permalink,
            }
            for c in response.validation.valid_citations
        ],
    }


# Standard library HTTP handler for zero-dependency operation
class RepoSageHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # silence noisy default logging
        pass

    def _send_json(self, status_code: int, data: Dict[str, Any]):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/ui"):
            if UI_INDEX.exists():
                body = UI_INDEX.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
            else:
                self._send_json(404, {"error": "UI not found"})
        elif parsed.path == "/health":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "version": "0.1.0",
                    "llm_provider": settings.llm_provider,
                    "model_order": settings.model_order,
                    "chat_model": settings.model_order[0] if settings.llm_provider == "jarvislabs" and settings.model_order else settings.chat_model,
                    "embedding_model": settings.embedding_model,
                },
            )
        elif parsed.path == "/audit":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [50])[0])
            backend = qs.get("backend", [None])[0]
            store = get_store(backend)
            self._send_json(200, {"audit_logs": store.get_audit_logs(limit=limit)})
        elif parsed.path == "/ui/repos":
            qs = parse_qs(parsed.query)
            backend = qs.get("backend", [None])[0]
            store = get_store(backend)
            try:
                repos = store.list_repos() if hasattr(store, "list_repos") else []
                self._send_json(200, {"repos": repos})
            except Exception as e:
                self._send_json(500, {"error": str(e)})
        elif parsed.path == "/ui/files":
            qs = parse_qs(parsed.query)
            repo_id = qs.get("repo_id", [None])[0]
            backend = qs.get("backend", [None])[0]
            if not repo_id:
                self._send_json(400, {"error": "Missing repo_id"})
                return
            store = get_store(backend)
            try:
                files = store.list_files(repo_id) if hasattr(store, "list_files") else []
                self._send_json(200, {"files": files})
            except Exception as e:
                self._send_json(500, {"error": str(e)})
        elif parsed.path.startswith("/static/"):
            rel = parsed.path[len("/static/"):]
            fpath = STATIC_DIR / rel
            if fpath.exists() and fpath.is_file():
                ct, _ = mimetypes.guess_type(str(fpath))
                self.send_response(200)
                self.send_header("Content-Type", ct or "application/octet-stream")
                self.end_headers()
                self.wfile.write(fpath.read_bytes())
            else:
                self._send_json(404, {"error": "Static file not found"})
        else:
            self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            self._send_json(400, {"error": "Invalid JSON"})
            return

        if parsed.path == "/index":
            target = payload.get("repo_url_or_path")
            if not target:
                self._send_json(400, {"error": "Missing 'repo_url_or_path'"})
                return
            backend = payload.get("backend")
            try:
                res = execute_index_request(target, backend)
                self._send_json(200, res)
            except Exception as e:
                self._send_json(500, {"error": str(e)})

        elif parsed.path == "/ask":
            target = payload.get("repo_url_or_path")
            question = payload.get("question")
            if not target or not question:
                self._send_json(400, {"error": "Missing 'repo_url_or_path' or 'question'"})
                return
            backend = payload.get("backend")
            try:
                res = execute_ask_request(target, question, backend)
                self._send_json(200, res)
            except Exception as e:
                self._send_json(500, {"error": str(e)})
        else:
            self._send_json(404, {"error": "Not Found"})


def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Run server using FastAPI if available, or HTTP server fallback."""
    if FastAPI is not None:
        try:
            import uvicorn
            uvicorn.run("reposage.api:app", host=host, port=port)
            return
        except Exception:
            pass

    server = HTTPServer((host, port), RepoSageHTTPHandler)
    print(f"[*] RepoSage server listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


# FastAPI app definition when fastapi is imported
if FastAPI is not None:
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(
        title="RepoSage API",
        version="0.1.0",
        description="Local-first codebase intelligence with exact citations.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from reposage.routers.codebase import router as codebase_router
    from reposage.routers.ui import router as ui_router
    from reposage.routers.system import router as system_router

    # Register modular routers
    app.include_router(ui_router)
    app.include_router(codebase_router)
    app.include_router(system_router)
else:
    app = None
