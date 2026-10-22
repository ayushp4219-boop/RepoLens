"""Repository cloning, fetching, discovery, and file filtering."""

import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, Optional, Tuple

from reposage.config import settings

# Binary and generated file extensions to ignore
IGNORED_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".exe", ".bin",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".pdf",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".woff", ".woff2", ".ttf", ".eot", ".mp3", ".mp4", ".wav",
    ".db", ".sqlite", ".sqlite3",
}

# Lockfiles and generated files to ignore
IGNORED_FILENAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Pipfile.lock", "Cargo.lock", "composer.lock", "Gemfile.lock",
}

# Directories to skip
IGNORED_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
    "__pycache__", "dist", "build", "target", "vendor", ".idea",
    ".vscode", ".pytest_cache", ".mypy_cache", ".tox", ".eggs",
}

# Likely secret files to skip entirely
SECRET_FILE_PATTERNS = [
    re.compile(r"^\.env(\..+)?$", re.IGNORECASE),
    re.compile(r"^id_rsa.*$", re.IGNORECASE),
    re.compile(r"^id_ed25519.*$", re.IGNORECASE),
    re.compile(r".*\.pem$", re.IGNORECASE),
    re.compile(r".*\.key$", re.IGNORECASE),
    re.compile(r".*credentials.*", re.IGNORECASE),
]

LANGUAGE_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "jsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c_header",
    ".hpp": "cpp_header",
    ".rb": "ruby",
    ".php": "php",
    ".sh": "bash",
    ".sql": "sql",
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".html": "html",
    ".css": "css",
}


@dataclass
class RepoMetadata:
    url: str
    owner: str
    repo_name: str
    default_branch: str
    commit_sha: str
    local_path: Path


@dataclass
class ScannedFile:
    relative_path: str
    absolute_path: Path
    language: str
    content: str
    content_hash: str
    size_bytes: int


def is_binary_content(raw_bytes: bytes) -> bool:
    """Check if file content looks like binary."""
    if b"\x00" in raw_bytes[:1024]:
        return True
    return False


def is_secret_file(path_name: str) -> bool:
    """Check if file name matches sensitive/secret patterns."""
    for pattern in SECRET_FILE_PATTERNS:
        if pattern.match(path_name):
            return True
    return False


def redact_secrets(text: str) -> str:
    """Basic redaction of high-entropy secrets and keys from code."""
    # Redact AWS access keys
    text = re.sub(r"(AKIA[0-9A-Z]{16})", "[REDACTED_AWS_KEY]", text)
    # Redact standard bearer tokens / secret assignments
    text = re.sub(
        r'(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*["\']([a-zA-Z0-9_\-\.]{16,})["\']',
        r'\1: "[REDACTED_SECRET]"',
        text,
    )
    return text


def parse_repo_info(url_or_path: str) -> Tuple[str, str]:
    """Extract owner and repo name from github URL or local path."""
    clean = url_or_path.strip().rstrip("/")
    if clean.endswith(".git"):
        clean = clean[:-4]

    # Check for github url format
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+)", clean)
    if match:
        return match.group(1), match.group(2)

    # Local path
    path = Path(clean).resolve()
    return "local", path.name


def resolve_git_info(repo_path: Path) -> Tuple[str, str]:
    """Retrieve default branch / current branch and commit SHA from git repo."""
    try:
        sha_proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        commit_sha = sha_proc.stdout.strip()
    except Exception:
        # Fallback hash if not a git repo
        commit_sha = hashlib.sha256(str(repo_path.resolve()).encode("utf-8")).hexdigest()[:12]

    try:
        branch_proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        branch = branch_proc.stdout.strip()
    except Exception:
        branch = "main"

    return branch, commit_sha


def clone_or_fetch_repo(url_or_path: str) -> RepoMetadata:
    """Prepare repo metadata and local directory for indexing."""
    target_path = Path(url_or_path)

    if target_path.exists():
        local_path = target_path.resolve()
        owner, repo_name = parse_repo_info(str(local_path))
        default_branch, commit_sha = resolve_git_info(local_path)
        return RepoMetadata(
            url=str(local_path),
            owner=owner,
            repo_name=repo_name,
            default_branch=default_branch,
            commit_sha=commit_sha,
            local_path=local_path,
        )

    # Remote Git URL
    owner, repo_name = parse_repo_info(url_or_path)
    cache_base = settings.cache_dir / "repos" / f"{owner}_{repo_name}"
    cache_base.parent.mkdir(parents=True, exist_ok=True)

    if (cache_base / ".git").exists():
        # Fetch latest
        subprocess.run(["git", "fetch"], cwd=cache_base, check=False)
        subprocess.run(["git", "reset", "--hard", "origin/HEAD"], cwd=cache_base, check=False)
    else:
        if cache_base.exists():
            shutil.rmtree(cache_base)
        subprocess.run(["git", "clone", "--depth", "1", url_or_path, str(cache_base)], check=True)

    default_branch, commit_sha = resolve_git_info(cache_base)
    return RepoMetadata(
        url=url_or_path,
        owner=owner,
        repo_name=repo_name,
        default_branch=default_branch,
        commit_sha=commit_sha,
        local_path=cache_base,
    )


def load_gitignore_spec(repo_path: Path):
    """Load gitignore rules if pathspec is available."""
    gitignore_file = repo_path / ".gitignore"
    if not gitignore_file.exists():
        return None
    try:
        import pathspec
        with open(gitignore_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return pathspec.PathSpec.from_lines("gitwildmatch", lines)
    except ImportError:
        return None


def scan_repo_files(repo_path: Path) -> Generator[ScannedFile, None, None]:
    """Iterate through valid, non-binary, non-secret files in the repo."""
    spec = load_gitignore_spec(repo_path)

    for root, dirs, files in os.walk(repo_path):
        rel_root = os.path.relpath(root, repo_path)
        if rel_root == ".":
            rel_root = ""

        # Filter out ignored directories in-place
        dirs[:] = [
            d for d in dirs
            if d not in IGNORED_DIRS
            and not (spec and spec.match_file(os.path.join(rel_root, d) if rel_root else d))
        ]

        for file_name in files:
            rel_file_path = os.path.join(rel_root, file_name) if rel_root else file_name

            # Check gitignore
            if spec and spec.match_file(rel_file_path):
                continue

            # Check lockfiles and secrets
            if file_name in IGNORED_FILENAMES or is_secret_file(file_name):
                continue

            file_ext = Path(file_name).suffix.lower()
            if file_ext in IGNORED_EXTENSIONS:
                continue

            abs_path = Path(root) / file_name

            try:
                stat = abs_path.stat()
                if stat.st_size > settings.max_file_size_bytes or stat.st_size == 0:
                    continue

                raw_bytes = abs_path.read_bytes()
                if is_binary_content(raw_bytes):
                    continue

                text = raw_bytes.decode("utf-8", errors="replace")
                text = redact_secrets(text)
                content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                language = LANGUAGE_BY_EXT.get(file_ext, "text")

                yield ScannedFile(
                    relative_path=rel_file_path,
                    absolute_path=abs_path,
                    language=language,
                    content=text,
                    content_hash=content_hash,
                    size_bytes=stat.st_size,
                )
            except Exception:
                continue
