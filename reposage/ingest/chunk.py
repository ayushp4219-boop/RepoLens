"""Symbol-based chunking with exact line range preservation."""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CodeChunk:
    repo_url: str
    commit_sha: str
    file_path: str
    start_line: int
    end_line: int
    symbol_name: str
    kind: str  # "function", "method", "class", "module"
    language: str
    text: str
    docstring: Optional[str] = None

    @property
    def citation_label(self) -> str:
        return f"{self.file_path}:{self.start_line}-{self.end_line}"


def extract_line_range(source_lines: List[str], start_line: int, end_line: int) -> str:
    """Extract 1-indexed line range from list of source lines."""
    # Ensure bounds are within [1, len(lines)]
    start = max(1, start_line)
    end = min(len(source_lines), max(start, end_line))
    return "\n".join(source_lines[start - 1 : end])


def chunk_file(
    repo_url: str,
    commit_sha: str,
    file_path: str,
    content: str,
    language: str,
    symbols: list,
) -> List[CodeChunk]:
    """Chunk source code by parsed symbols (functions, methods, classes).
    
    If no symbols are found, returns a module-level chunk covering the entire file.
    Preserves exact 1-based start_line and end_line coordinates.
    """
    source_lines = content.splitlines()
    if not source_lines:
        return []

    chunks: List[CodeChunk] = []
    covered_lines = set()

    for sym in symbols:
        start_line = max(1, sym.start_line)
        end_line = min(len(source_lines), max(start_line, sym.end_line))
        text = extract_line_range(source_lines, start_line, end_line)

        chunk = CodeChunk(
            repo_url=repo_url,
            commit_sha=commit_sha,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            symbol_name=sym.name,
            kind=sym.kind,
            language=language,
            text=text,
            docstring=sym.docstring,
        )
        chunks.append(chunk)

        for line_idx in range(start_line, end_line + 1):
            covered_lines.add(line_idx)

    # If the file had no symbols, or significant top-level module code exists
    if not chunks:
        # Full file as a module chunk
        full_text = "\n".join(source_lines)
        chunks.append(
            CodeChunk(
                repo_url=repo_url,
                commit_sha=commit_sha,
                file_path=file_path,
                start_line=1,
                end_line=len(source_lines),
                symbol_name=f"<{Path(file_path).stem or 'module'}>",
                kind="module",
                language=language,
                text=full_text,
                docstring=None,
            )
        )

    return chunks


from pathlib import Path
