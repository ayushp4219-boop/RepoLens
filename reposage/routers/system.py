"""System health and audit logging router."""

from typing import Optional
from fastapi import APIRouter

from reposage.config import settings
from reposage.retrieval.store import get_store

router = APIRouter(tags=["System & Audit"])


@router.get("/health", summary="Health check and model status")
def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "llm_provider": settings.llm_provider,
        "model_order": settings.model_order,
        "chat_model": settings.model_order[0] if settings.llm_provider == "jarvislabs" and settings.model_order else settings.chat_model,
        "embedding_model": settings.embedding_model,
    }


@router.get("/audit", summary="Get recent query audit logs")
def audit_endpoint(limit: int = 50, backend: Optional[str] = None):
    store = get_store(backend)
    return {"audit_logs": store.get_audit_logs(limit=limit)}
