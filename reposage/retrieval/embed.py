"""Code embedding generation and chunk representation."""

from typing import List, Optional

from reposage.ingest.chunk import CodeChunk
from reposage.models.ollama_client import OllamaClient


def format_chunk_for_embedding(chunk: CodeChunk) -> str:
    """Format file_path + symbol_name + docstring + code into an embedding prompt."""
    parts = [
        f"File: {chunk.file_path}",
        f"Symbol: {chunk.symbol_name} ({chunk.kind})",
    ]
    if chunk.docstring:
        parts.append(f"Docstring: {chunk.docstring.strip()}")
    parts.append(f"Code:\n{chunk.text}")
    return "\n".join(parts)


def compute_chunk_embedding(
    chunk: CodeChunk, client: OllamaClient
) -> List[float]:
    """Compute vector embedding for a single code chunk."""
    text = format_chunk_for_embedding(chunk)
    try:
        return client.embeddings(text)
    except Exception:
        return []


def embed_chunks(
    chunks: List[CodeChunk], client: OllamaClient
) -> List[List[float]]:
    """Compute embeddings for a list of code chunks."""
    embeddings = []
    for chunk in chunks:
        embeddings.append(compute_chunk_embedding(chunk, client))
    return embeddings
