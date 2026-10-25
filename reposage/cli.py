"""CLI interface for RepoSage using Typer."""

import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import typer
except ImportError:
    class TyperFallback:
        def __init__(self, *args, **kwargs):
            pass
        def command(self, *args, **kwargs):
            def decorator(f: Callable):
                return f
            return decorator
        def echo(self, message: Any, *args, **kwargs):
            print(message)
        def Argument(self, *args, default=..., **kwargs):
            return default
        def Option(self, *args, default=None, **kwargs):
            return default
        def Typer(self, *args, **kwargs):
            return self
        def __call__(self, *args, **kwargs):
            pass

    typer = TyperFallback()

from reposage.agent.orchestrator import RepoSageOrchestrator
from reposage.config import settings
from reposage.ingest.chunk import chunk_file
from reposage.ingest.clone import clone_or_fetch_repo, scan_repo_files
from reposage.ingest.graph import SymbolGraph
from reposage.ingest.parse import parse_source_file
from reposage.ingest.summarize import FileSummarizer
from reposage.models.jarvis_client import get_llm_client
from reposage.models.ollama_client import OllamaClient
from reposage.retrieval.embed import embed_chunks
from reposage.retrieval.store import get_store

if hasattr(typer, "Typer"):
    app = typer.Typer(
        name="reposage",
        help="RepoSage: A local-first AI that understands codebases with grounded citations.",
        no_args_is_help=True,
    )
else:
    app = typer


def run_indexing(url_or_path: str, backend: Optional[str] = None):
    """Core logic to index a repository."""
    start_time = time.time()
    store = get_store(backend)
    embed_client = OllamaClient()
    llm_client = get_llm_client()
    summarizer = FileSummarizer(llm_client=llm_client if llm_client.is_available() else None)

    typer.echo(f"[*] Discovering and preparing repository: {url_or_path}")
    repo_meta = clone_or_fetch_repo(url_or_path)
    typer.echo(
        f"[*] Resolved commit SHA: {repo_meta.commit_sha} (branch: {repo_meta.default_branch})"
    )

    repo_id = store.save_repo(
        url=repo_meta.url,
        default_branch=repo_meta.default_branch,
        commit_sha=repo_meta.commit_sha,
    )

    scanned_files = list(scan_repo_files(repo_meta.local_path))
    typer.echo(f"[*] Found {len(scanned_files)} eligible source files.")

    graph = SymbolGraph()
    parsed_files = {}
    chunks_by_file = {}
    saved_chunks_count = 0
    saved_files_count = 0
    skipped_files_count = 0

    for f in scanned_files:
        existing_file = store.get_file(repo_id, f.relative_path)

        # Incremental re-index: skip re-embedding if content hash unchanged
        if existing_file and existing_file.get("content_hash") == f.content_hash:
            skipped_files_count += 1
            continue

        saved_files_count += 1
        parsed = parse_source_file(f.relative_path, f.content, f.language)
        parsed_files[f.relative_path] = parsed

        # Chunk by symbols
        chunks = chunk_file(
            repo_url=repo_meta.url,
            commit_sha=repo_meta.commit_sha,
            file_path=f.relative_path,
            content=f.content,
            language=f.language,
            symbols=parsed.symbols,
        )

        # Generate summary
        sym_names = [s.name for s in parsed.symbols]
        summary = summarizer.summarize_file(
            file_path=f.relative_path,
            content=f.content,
            content_hash=f.content_hash,
            symbols=sym_names,
        )

        file_id = store.save_file(
            repo_id=repo_id,
            path=f.relative_path,
            language=f.language,
            content_hash=f.content_hash,
            summary=summary,
        )

        store.delete_file_chunks(file_id)

        # Embed chunks locally with Ollama
        embeddings = []
        if embed_client.is_available():
            embeddings = embed_chunks(chunks, embed_client)
        else:
            embeddings = [None] * len(chunks)

        for idx, chunk in enumerate(chunks):
            emb = embeddings[idx] if idx < len(embeddings) else None
            chunk_id = store.save_chunk(
                file_id=file_id,
                symbol_name=chunk.symbol_name,
                kind=chunk.kind,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                text=chunk.text,
                embedding=emb,
            )
            saved_chunks_count += 1

            cid_str = str(chunk_id)
            graph.register_chunk(cid_str, chunk)
            chunks_by_file.setdefault(f.relative_path, []).append((cid_str, chunk))

    # Build call and import graph
    typer.echo("[*] Building call and import graph...")
    graph.build_edges(parsed_files, chunks_by_file)
    edges_count = 0
    for edge in graph.edges:
        store.save_edge(
            caller_chunk_id=int(edge.caller_chunk_id) if edge.caller_chunk_id else None,
            callee_chunk_id=int(edge.callee_chunk_id) if edge.callee_chunk_id else None,
            callee_name=edge.callee_symbol,
            kind=edge.kind,
            confidence=edge.confidence,
        )
        edges_count += 1

    elapsed = round(time.time() - start_time, 2)
    typer.echo(
        f"[+] Ingestion complete in {elapsed}s! "
        f"Indexed {saved_files_count} files ({skipped_files_count} cached), "
        f"{saved_chunks_count} chunks, {edges_count} call graph edges."
    )
    return repo_id


@app.command()
def index(
    repo_url_or_path: str = typer.Argument(
        ..., help="GitHub repo URL (https://github.com/...) or local directory path"
    ),
    backend: Optional[str] = typer.Option(
        None, "--backend", "-b", help="Storage backend (postgres or sqlite)"
    ),
):
    """Index a repository: clone, parse symbols, chunk, build graph, and embed."""
    run_indexing(repo_url_or_path, backend)


@app.command()
def ask(
    repo_url_or_path: str = typer.Argument(
        ..., help="GitHub repo URL or local directory path that was indexed"
    ),
    question: str = typer.Argument(..., help="Question to ask about the codebase"),
    backend: Optional[str] = typer.Option(
        None, "--backend", "-b", help="Storage backend (postgres or sqlite)"
    ),
):
    """Ask a question about the repository with grounded citations."""
    store = get_store(backend)
    target_path = Path(repo_url_or_path)
    url_to_lookup = str(target_path.resolve()) if target_path.exists() else repo_url_or_path

    repo = store.get_repo(url_to_lookup)
    if not repo:
        typer.echo(
            f"[!] Repository '{repo_url_or_path}' has not been indexed yet. Running index first..."
        )
        repo_id = run_indexing(repo_url_or_path, backend)
    else:
        repo_id = repo["id"]

    orchestrator = RepoSageOrchestrator(
        store=store,
        repo_id=repo_id,
    )

    typer.echo(f"[*] Analyzing question: \"{question}\"...")
    response = orchestrator.run(question)

    typer.echo("\n" + "=" * 60)
    typer.echo(f"Mode: {response.mode.upper()}")
    if response.model_used:
        fallback_str = " (fallback)" if response.fallback_used else ""
        typer.echo(f"Model: {response.model_used}{fallback_str}")
        if response.attempted_models and len(response.attempted_models) > 1:
            typer.echo(f"Attempted: {' -> '.join(response.attempted_models)}")
    typer.echo("=" * 60 + "\n")
    typer.echo(response.answer)
    typer.echo("\n" + "=" * 60)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Bind host"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
):
    """Start the RepoSage FastAPI server."""
    from reposage.api import run_server
    typer.echo(f"[*] Starting RepoSage API server on http://{host}:{port}")
    run_server(host=host, port=port)


if __name__ == "__main__":
    app()
