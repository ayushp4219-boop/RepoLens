"""Agent orchestrator with question classification, 4-step tool loop, and audit logging."""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from reposage.agent.citations import CitationValidationResult, validate_citations
from reposage.agent.prompts import MODE_PROMPTS, QueryMode, classify_query
from reposage.agent.tools import CodebaseTools, RetrievedChunkMeta, ToolResult
from reposage.config import settings
from reposage.models.ollama_client import OllamaClient
from reposage.retrieval.store import BaseStore


@dataclass
class OrchestratorResponse:
    question: str
    mode: QueryMode
    answer: str
    tool_calls: List[Dict[str, Any]]
    retrieved_citations: List[str]
    validation: CitationValidationResult


def estimate_tokens(text: str) -> int:
    """Rough estimation of token count (~4 characters per token)."""
    return len(text) // 4


class RepoSageOrchestrator:
    def __init__(
        self,
        store: BaseStore,
        repo_id: int,
        ollama_client: Optional[OllamaClient] = None,
    ):
        self.store = store
        self.repo_id = repo_id
        self.client = ollama_client or OllamaClient()
        self.repo = self.store.get_repo(str(self.repo_id)) or {}
        self.tools = CodebaseTools(
            store=self.store,
            repo_id=self.repo_id,
            ollama_client=self.client,
        )

    def run(self, question: str) -> OrchestratorResponse:
        """Run the full reasoning loop (classification -> tool loop <= 4 steps -> generation -> validation -> audit)."""
        mode = classify_query(question)
        tool_call_history: List[Dict[str, Any]] = []

        # Execute up to max 4 tool steps based on mode and question
        self._execute_tool_loop(question, mode, tool_call_history)

        # Assemble retrieved context under the 8k token cap
        evidence_text = self._build_evidence_context()

        # Prompt LLM for answer in the given mode
        system_prompt = MODE_PROMPTS[mode]
        user_message = (
            f"User Question: {question}\n\n"
            f"Mode: {mode}\n\n"
            f"RETRIEVED EVIDENCE FROM REPO:\n{evidence_text}\n\n"
            f"Answer the question following the instructions and citing exact [path:start-end] ranges."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        try:
            raw_answer = self.client.chat(messages=messages)
        except Exception:
            raw_answer = self._generate_fallback_answer(mode, question)

        # Citation validation
        repo_url = self.repo.get("url", "https://github.com/local/repo")
        commit_sha = self.repo.get("last_commit_sha", "HEAD")
        validation = validate_citations(
            answer=raw_answer,
            retrieved_chunks=self.tools.session_retrieved_chunks,
            repo_url=repo_url,
            commit_sha=commit_sha,
        )

        final_answer = validation.final_answer

        # Audit logging
        retrieved_ids = [
            chunk.start_line for chunk in self.tools.session_retrieved_chunks.values()
        ]
        try:
            self.store.audit_log(
                question=question,
                tool_calls=tool_call_history,
                retrieved_chunk_ids=retrieved_ids,
                answer=final_answer,
            )
        except Exception:
            pass

        return OrchestratorResponse(
            question=question,
            mode=mode,
            answer=final_answer,
            tool_calls=tool_call_history,
            retrieved_citations=list(self.tools.session_retrieved_chunks.keys()),
            validation=validation,
        )

    def _execute_tool_loop(
        self,
        question: str,
        mode: QueryMode,
        history: List[Dict[str, Any]],
    ):
        """Execute up to 4 deterministic agentic tool steps."""
        step = 0
        max_steps = settings.max_tool_steps

        if mode == "explain-file":
            # Extract possible file path
            file_match = re.search(r"([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+)", question)
            file_path = file_match.group(1) if file_match else ""

            # Step 1: get_file_summary
            if file_path and step < max_steps:
                res1 = self.tools.get_file_summary(file_path)
                history.append({"step": step + 1, "tool": "get_file_summary", "args": {"path": file_path}})
                step += 1

            # Step 2: search_code for the file chunks
            if step < max_steps:
                res2 = self.tools.search_code(query=file_path or question, path_glob=f"*{file_path}*" if file_path else None, limit=5)
                history.append({"step": step + 1, "tool": "search_code", "args": {"query": file_path or question}})
                step += 1

            # Step 3: Check callers of main symbols in file if any were found
            for c in list(self.tools.session_retrieved_chunks.values())[:2]:
                if step < max_steps and c.symbol_name and not c.symbol_name.startswith("<"):
                    self.tools.get_callers(c.symbol_name, depth=1)
                    history.append({"step": step + 1, "tool": "get_callers", "args": {"symbol": c.symbol_name}})
                    step += 1

        elif mode == "connection":
            # Identify caller and callee candidates from question
            tokens = re.findall(r"[a-zA-Z0-9_]{3,}", question)
            # Step 1: Search for origin symbol
            candidate = tokens[0] if tokens else question
            res1 = self.tools.get_symbol(candidate)
            if not res1.retrieved_chunks:
                res1 = self.tools.search_code(query=question, limit=5)
            history.append({"step": step + 1, "tool": "search_or_symbol", "args": {"query": candidate}})
            step += 1

            # Step 2: Trace callees from found symbol
            first_chunk = next(iter(self.tools.session_retrieved_chunks.values()), None)
            if first_chunk and step < max_steps:
                self.tools.get_callees(first_chunk.symbol_name, depth=2)
                history.append({"step": step + 1, "tool": "get_callees", "args": {"symbol": first_chunk.symbol_name}})
                step += 1

            # Step 3: Search for target keywords in call chain
            if len(tokens) > 1 and step < max_steps:
                target_sym = tokens[-1]
                self.tools.search_code(query=target_sym, limit=5)
                history.append({"step": step + 1, "tool": "search_code", "args": {"query": target_sym}})
                step += 1

        elif mode == "bug-hunt":
            # Step 1: Hybrid search with the bug query
            res1 = self.tools.search_code(query=question, limit=5)
            history.append({"step": step + 1, "tool": "search_code", "args": {"query": question}})
            step += 1

            # Step 2: Read context lines around top suspect if found
            top_chunk = next(iter(self.tools.session_retrieved_chunks.values()), None)
            if top_chunk and step < max_steps:
                self.tools.read_lines(
                    path=top_chunk.file_path,
                    start=max(1, top_chunk.start_line - 5),
                    end=top_chunk.end_line + 5,
                )
                history.append(
                    {
                        "step": step + 1,
                        "tool": "read_lines",
                        "args": {"path": top_chunk.file_path, "start": top_chunk.start_line, "end": top_chunk.end_line},
                    }
                )
                step += 1

            # Step 3: Check callers to see where this suspect is triggered
            if top_chunk and top_chunk.symbol_name and step < max_steps:
                self.tools.get_callers(top_chunk.symbol_name, depth=1)
                history.append({"step": step + 1, "tool": "get_callers", "args": {"symbol": top_chunk.symbol_name}})
                step += 1

        else:  # General
            # Step 1: Hybrid search
            res1 = self.tools.search_code(query=question, limit=5)
            history.append({"step": step + 1, "tool": "search_code", "args": {"query": question}})
            step += 1

            # Step 2: Read lines of top match if available
            top_chunk = next(iter(self.tools.session_retrieved_chunks.values()), None)
            if top_chunk and step < max_steps:
                self.tools.read_lines(
                    path=top_chunk.file_path,
                    start=top_chunk.start_line,
                    end=min(top_chunk.start_line + 50, top_chunk.end_line),
                )
                history.append(
                    {
                        "step": step + 1,
                        "tool": "read_lines",
                        "args": {"path": top_chunk.file_path, "start": top_chunk.start_line},
                    }
                )
                step += 1

    def _build_evidence_context(self) -> str:
        """Concatenate retrieved chunks while strictly adhering to < 8k token limit."""
        chunks = list(self.tools.session_retrieved_chunks.values())
        if not chunks:
            return "No relevant code chunks retrieved."

        lines = []
        total_tokens = 0
        token_cap = settings.max_retrieved_tokens

        for c in chunks:
            chunk_header = f"\n=== [{c.citation}] Symbol: {c.symbol_name} ==="
            chunk_body = f"{chunk_header}\n{c.text}\n"
            c_tokens = estimate_tokens(chunk_body)

            if total_tokens + c_tokens > token_cap:
                # Truncate text if needed to fit under token cap
                remaining_tokens = max(0, token_cap - total_tokens)
                if remaining_tokens > 50:
                    char_limit = remaining_tokens * 4
                    lines.append(f"{chunk_header}\n{c.text[:char_limit]}\n... [truncated due to token limit]")
                break

            lines.append(chunk_body)
            total_tokens += c_tokens

        return "".join(lines)

    def _generate_fallback_answer(self, mode: QueryMode, question: str) -> str:
        """Deterministic fallback answer generator if Ollama is unreachable."""
        chunks = list(self.tools.session_retrieved_chunks.values())
        if not chunks:
            return "I couldn't find evidence in the repo to answer this question."

        top = chunks[0]
        if mode == "explain-file":
            return (
                f"### Purpose\nThe file `{top.file_path}` ({top.citation}) provides key logic "
                f"for `{top.symbol_name}`.\n\n"
                f"### Key Symbols\n- `{top.symbol_name}` defined at {top.citation}."
            )
        elif mode == "connection":
            return (
                f"### Call Chain Overview\nExecution initiates at `{top.symbol_name}` "
                f"in {top.citation}.\n\n"
                f"### Step-by-Step Call Trace\n1. `{top.symbol_name}` ({top.citation}) performs the operation."
            )
        elif mode == "bug-hunt":
            return (
                f"### Ranked Suspects\n"
                f"1. **Location**: `{top.citation}` (`{top.symbol_name}`)\n"
                f"   - **Why Suspect**: Logic in {top.citation} handles critical conditional state related to '{question}'.\n"
                f"   - **Evidence Present**: Code found in {top.citation}.\n"
                f"   - **Missing Evidence & Uncertainty**: Needs runtime verification of arguments."
            )
        else:
            return f"Relevant code was identified in {top.citation} for `{top.symbol_name}`."
