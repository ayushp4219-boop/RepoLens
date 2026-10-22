"""Indexing and query processing router."""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from reposage.api import execute_ask_request, execute_index_request

router = APIRouter(tags=["Codebase Operations"])


class IndexRequest(BaseModel):
    repo_url_or_path: str
    backend: Optional[str] = None


class AskRequest(BaseModel):
    repo_url_or_path: str
    question: str
    backend: Optional[str] = None


@router.post("/index", summary="Index a codebase repository")
def index_endpoint(req: IndexRequest):
    try:
        return execute_index_request(req.repo_url_or_path, backend=req.backend)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ask", summary="Ask a grounded question about indexed code")
def ask_endpoint(req: AskRequest):
    try:
        return execute_ask_request(req.repo_url_or_path, req.question, backend=req.backend)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
