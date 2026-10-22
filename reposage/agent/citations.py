"""Strict citation validation, hallucination rejection, and GitHub permalink generation."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from reposage.agent.tools import RetrievedChunkMeta


@dataclass
class ValidatedCitation:
    file_path: str
    start_line: int
    end_line: int
    is_valid: bool
    permalink: str
    reason: str = ""


@dataclass
class CitationValidationResult:
    is_grounded: bool
    original_answer: str
    final_answer: str
    valid_citations: List[ValidatedCitation] = field(default_factory=list)
    invalid_citations: List[ValidatedCitation] = field(default_factory=list)
    sources_markdown: str = ""


CITATION_REGEX = re.compile(
    r"(?:\[|\b)([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+):([0-9]+)(?:-([0-9]+))?(?:\]|\b)"
)


def extract_citations(text: str) -> List[Tuple[str, int, int]]:
    """Extract all (file_path, start_line, end_line) citations from text."""
    found = []
    for match in CITATION_REGEX.finditer(text):
        file_path = match.group(1).replace("\\", "/")
        start = int(match.group(2))
        end = int(match.group(3)) if match.group(3) else start
        if start > end:
            start, end = end, start
        found.append((file_path, start, end))
    return found


def build_github_permalink(
    repo_url: str,
    commit_sha: str,
    file_path: str,
    start_line: int,
    end_line: int,
) -> str:
    """Build exact GitHub permalink or local file URI for citation."""
    clean_url = repo_url.rstrip("/")
    if clean_url.endswith(".git"):
        clean_url = clean_url[:-4]

    # Check for github repo pattern
    gh_match = re.search(r"github\.com[:/]([^/]+)/([^/]+)", clean_url)
    if gh_match:
        owner = gh_match.group(1)
        repo = gh_match.group(2)
        sha = commit_sha or "HEAD"
        line_anchor = f"L{start_line}-L{end_line}" if start_line != end_line else f"L{start_line}"
        return f"https://github.com/{owner}/{repo}/blob/{sha}/{file_path}#{line_anchor}"

    # Local fallback
    line_anchor = f"L{start_line}-L{end_line}" if start_line != end_line else f"L{start_line}"
    return f"file:///{clean_url}/{file_path}#{line_anchor}"


def validate_citations(
    answer: str,
    retrieved_chunks: Dict[str, RetrievedChunkMeta],
    repo_url: str,
    commit_sha: str,
) -> CitationValidationResult:
    """Validate that every code citation in answer exists in the retrieved set.
    
    If no valid citations exist, returns "I couldn't find evidence in the repo".
    Appends a 'Sources' section with GitHub permalinks for all verified citations.
    """
    raw_citations = extract_citations(answer)

    valid_citations: List[ValidatedCitation] = []
    invalid_citations: List[ValidatedCitation] = []
    seen_valid_keys: Set[Tuple[str, int, int]] = set()

    # Pre-index retrieved chunks by file_path
    retrieved_by_file: Dict[str, List[RetrievedChunkMeta]] = {}
    for chunk in retrieved_chunks.values():
        retrieved_by_file.setdefault(chunk.file_path, []).append(chunk)

    for file_path, start, end in raw_citations:
        key = (file_path, start, end)
        permalink = build_github_permalink(repo_url, commit_sha, file_path, start, end)

        # 1. Check if file was retrieved
        matching_chunks = retrieved_by_file.get(file_path, [])
        if not matching_chunks:
            # Check with basename match if full path prefix differed
            base_matches = [
                c for c in retrieved_chunks.values()
                if c.file_path.endswith(file_path) or file_path.endswith(c.file_path)
            ]
            matching_chunks = base_matches

        if not matching_chunks:
            invalid_citations.append(
                ValidatedCitation(
                    file_path=file_path,
                    start_line=start,
                    end_line=end,
                    is_valid=False,
                    permalink=permalink,
                    reason="File was never retrieved this turn.",
                )
            )
            continue

        # 2. Check line range overlap with any retrieved chunk in that file
        # A citation is valid if [start, end] overlaps or is contained within a retrieved chunk
        line_verified = False
        for c in matching_chunks:
            # Allow slight line boundary tolerance (+- 2 lines)
            c_start = max(1, c.start_line - 2)
            c_end = c.end_line + 2
            if not (end < c_start or start > c_end):
                line_verified = True
                break

        if line_verified:
            if key not in seen_valid_keys:
                seen_valid_keys.add(key)
                valid_citations.append(
                    ValidatedCitation(
                        file_path=file_path,
                        start_line=start,
                        end_line=end,
                        is_valid=True,
                        permalink=permalink,
                    )
                )
        else:
            invalid_citations.append(
                ValidatedCitation(
                    file_path=file_path,
                    start_line=start,
                    end_line=end,
                    is_valid=False,
                    permalink=permalink,
                    reason=f"Line range {start}-{end} outside retrieved chunks for {file_path}.",
                )
            )

    # Clean the answer text: flag or strip invalid citations
    clean_answer = answer
    for inv in invalid_citations:
        inv_str = f"{inv.file_path}:{inv.start_line}-{inv.end_line}"
        clean_answer = clean_answer.replace(inv_str, f"[UNVERIFIED_CITATION: {inv_str}]")
        clean_answer = clean_answer.replace(f"[{inv.file_path}:{inv.start_line}]", f"[UNVERIFIED_CITATION: {inv.file_path}:{inv.start_line}]")

    # If answer made claims without any valid citations or all citations failed
    if not valid_citations:
        fallback_msg = "I couldn't find evidence in the repo to answer this question."
        return CitationValidationResult(
            is_grounded=False,
            original_answer=answer,
            final_answer=fallback_msg,
            valid_citations=[],
            invalid_citations=invalid_citations,
            sources_markdown="",
        )

    # Build sources section
    sources_lines = ["\n\n### Sources"]
    for v in valid_citations:
        sources_lines.append(f"- [{v.file_path}#L{v.start_line}-L{v.end_line}]({v.permalink})")
    sources_md = "\n".join(sources_lines)

    final_answer = clean_answer.strip() + sources_md

    return CitationValidationResult(
        is_grounded=True,
        original_answer=answer,
        final_answer=final_answer,
        valid_citations=valid_citations,
        invalid_citations=invalid_citations,
        sources_markdown=sources_md,
    )
