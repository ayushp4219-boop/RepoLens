"""Hybrid code retrieval combining keyword and vector similarity."""

from typing import Any, Dict, List, Optional

from reposage.models.ollama_client import OllamaClient
from reposage.retrieval.store import BaseStore


def hybrid_search_code(
    store: BaseStore,
    repo_id: int,
    query: str,
    ollama_client: Optional[OllamaClient] = None,
    path_glob: Optional[str] = None,
    limit: int = 10,
    keyword_weight: float = 0.4,
    vector_weight: float = 0.6,
) -> List[Dict[str, Any]]:
    """Execute hybrid search over code chunks.
    
    1. Computes dense embedding of query using Ollama (if client provided).
    2. Runs hybrid search against the store with weighted FTS + vector score.
    3. Attaches formatted citation label (e.g. 'path:start-end').
    """
    limit = min(max(1, limit), 20)  # Bound limit to [1, 20]

    query_embedding: Optional[List[float]] = None
    if ollama_client is not None:
        try:
            query_embedding = ollama_client.embeddings(query)
        except Exception:
            query_embedding = None

    results = store.hybrid_search(
        repo_id=repo_id,
        query=query,
        query_embedding=query_embedding,
        path_glob=path_glob,
        limit=limit,
        keyword_weight=keyword_weight,
        vector_weight=vector_weight,
    )

    for item in results:
        item["citation"] = f"{item['file_path']}:{item['start_line']}-{item['end_line']}"

    return results
