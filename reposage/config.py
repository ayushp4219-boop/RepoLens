"""Configuration settings for RepoSage."""

import os
from dataclasses import dataclass
from pathlib import Path


def _get_default_dir(name: str) -> Path:
    # First check env
    if f"REPOSAGE_{name.upper()}_DIR" in os.environ:
        return Path(os.environ[f"REPOSAGE_{name.upper()}_DIR"])
    # Default to local project directory .reposage for sandbox safety and portability
    local_dir = Path.cwd() / ".reposage"
    try:
        local_dir.mkdir(parents=True, exist_ok=True)
        return local_dir
    except Exception:
        return Path("/tmp/.reposage")


@dataclass
class Settings:
    # Ollama settings
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    chat_model: str = os.getenv("REPOSAGE_CHAT_MODEL", "qwen2.5-coder")
    embedding_model: str = os.getenv("REPOSAGE_EMBEDDING_MODEL", "nomic-embed-text")
    embedding_dim: int = int(os.getenv("REPOSAGE_EMBEDDING_DIM", "768"))

    # Storage settings
    # Default to sqlite for seamless zero-setup, configurable to postgres
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/reposage"
    )
    storage_backend: str = os.getenv("REPOSAGE_STORAGE_BACKEND", "sqlite")
    sqlite_db_path: Path = Path(
        os.getenv(
            "REPOSAGE_SQLITE_PATH",
            str(_get_default_dir("data") / "reposage.db"),
        )
    )

    # Ingestion constraints
    max_file_size_bytes: int = int(os.getenv("REPOSAGE_MAX_FILE_SIZE", str(100 * 1024)))
    cache_dir: Path = _get_default_dir("cache")

    # Orchestrator limits
    max_tool_steps: int = 4
    max_retrieved_tokens: int = 8000
    max_read_lines: int = 200


settings = Settings()
