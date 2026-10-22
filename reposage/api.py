"""Thin REST API service for RepoSage (FastAPI with standard library fallback)."""

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
except ImportError:
    FastAPI = None
    BaseModel = object

from reposage.agent.orchestrator import RepoSageOrchestrator
from reposage.cli import run_indexing
from reposage.config import settings
from reposage.models.ollama_client import OllamaClient
from reposage.retrieval.store import get_store


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

    client = OllamaClient()
    orchestrator = RepoSageOrchestrator(
        store=store,
        repo_id=repo_id,
        ollama_client=client,
    )

    response = orchestrator.run(question)
    return {
        "question": response.question,
        "mode": response.mode,
        "answer": response.answer,
        "is_grounded": response.validation.is_grounded,
        "tool_calls": response.tool_calls,
        "retrieved_citations": response.retrieved_citations,
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
    def _send_json(self, status_code: int, data: Dict[str, Any]):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "version": "0.1.0",
                    "chat_model": settings.chat_model,
                    "embedding_model": settings.embedding_model,
                },
            )
        elif parsed.path == "/audit":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", [50])[0])
            backend = qs.get("backend", [None])[0]
            store = get_store(backend)
            self._send_json(200, {"audit_logs": store.get_audit_logs(limit=limit)})
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
    app = FastAPI(
        title="RepoSage API",
        version="0.1.0",
        description="Local-first codebase intelligence with exact citations.",
    )

    class IndexRequest(BaseModel):
        repo_url_or_path: str
        backend: Optional[str] = None

    class AskRequest(BaseModel):
        repo_url_or_path: str
        question: str
        backend: Optional[str] = None

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "version": "0.1.0",
            "chat_model": settings.chat_model,
            "embedding_model": settings.embedding_model,
        }

    @app.post("/index")
    def index_endpoint(req: IndexRequest):
        try:
            return execute_index_request(req.repo_url_or_path, backend=req.backend)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/ask")
    def ask_endpoint(req: AskRequest):
        try:
            return execute_ask_request(req.repo_url_or_path, req.question, backend=req.backend)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/audit")
    def audit_endpoint(limit: int = 50, backend: Optional[str] = None):
        store = get_store(backend)
        return {"audit_logs": store.get_audit_logs(limit=limit)}
else:
    app = None
