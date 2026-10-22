"""UI and exploration router for RepoSage."""

from typing import Optional
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from reposage.api import UI_INDEX
from reposage.retrieval.store import get_store

router = APIRouter(tags=["UI & Explorer"])


@router.get("/", response_class=HTMLResponse, summary="Serve RepoSage IDE web interface")
def index_page():
    if UI_INDEX.exists():
        return HTMLResponse(content=UI_INDEX.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>RepoSage UI not found</h1>", status_code=404)


@router.get("/ui", response_class=HTMLResponse, summary="Alternative route for IDE web interface")
def ui_page():
    return index_page()


@router.get("/ui/repos", summary="List all indexed repositories")
def ui_repos(backend: Optional[str] = None):
    store = get_store(backend)
    return {"repos": store.list_repos() if hasattr(store, "list_repos") else []}


@router.get("/ui/files", summary="List all indexed files for a repository")
def ui_files(repo_id: int, backend: Optional[str] = None):
    store = get_store(backend)
    return {"files": store.list_files(repo_id) if hasattr(store, "list_files") else []}


@router.get("/ui/file", summary="Fetch file content for editor view")
def ui_file_content(repo_id: int, path: str, backend: Optional[str] = None):
    store = get_store(backend)
    content = store.read_lines(repo_id=repo_id, path=path, start_line=1, end_line=5000)
    if content is None:
        return {"path": path, "content": "# File content not cached in chunks"}
    return {"path": path, "content": content}

