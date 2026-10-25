"""Per-file LLM summary generation with content-hash caching."""

import json
from pathlib import Path
from typing import Dict, List, Optional

from reposage.config import settings


class FileSummarizer:
    def __init__(
        self,
        ollama_client=None,
        llm_client=None,
        cache_path: Optional[Path] = None,
    ):
        self.client = llm_client or ollama_client
        self.ollama_client = self.client
        self.cache_path = cache_path or (settings.cache_dir / "summaries_cache.json")
        self.cache: Dict[str, str] = self._load_cache()

    def _load_cache(self) -> Dict[str, str]:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self):
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)
        except Exception:
            pass

    def summarize_file(
        self,
        file_path: str,
        content: str,
        content_hash: str,
        symbols: List[str],
    ) -> str:
        """Generate a concise file summary, cached by file content hash."""
        # 1. Check cache
        if content_hash in self.cache:
            return self.cache[content_hash]

        # 2. Try LLM generation if client available
        summary = ""
        if self.client is not None:
            symbols_str = ", ".join(symbols) if symbols else "No explicit symbols"
            # Truncate content to avoid exceeding token limit
            truncated_content = content[:3000]

            prompt = (
                f"You are a code analysis system. Provide a concise 2-sentence summary of the purpose "
                f"and key responsibilities of the file '{file_path}'.\n\n"
                f"Symbols defined: {symbols_str}\n\n"
                f"Source preview:\n```\n{truncated_content}\n```\n\n"
                f"Concise summary:"
            )

            try:
                response = self.client.generate(prompt=prompt)
                summary = response.strip()
            except Exception:
                summary = ""

        # 3. Fallback deterministic summary if LLM not present or failed
        if not summary:
            if symbols:
                summary = (
                    f"File '{file_path}' defines key symbols: {', '.join(symbols[:5])}."
                )
            else:
                summary = f"File '{file_path}' provides module definitions and utility routines."

        # 4. Cache and return
        self.cache[content_hash] = summary
        self._save_cache()
        return summary
