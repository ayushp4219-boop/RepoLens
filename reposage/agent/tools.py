"""The five exact tools with row and size caps for RepoSage orchestrator."""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from reposage.config import settings
from reposage.models.ollama_client import OllamaClient
from reposage.retrieval.hybrid import hybrid_search_code
from reposage.retrieval.store import BaseStore


@dataclass
class RetrievedChunkMeta:
    file_path: str
    start_line: int
    end_line: int
    symbol_name: str
    text: str
    commit_sha: str
    repo_url: str

    @property
    def citation(self) -> str:
        clean_path = self.file_path.replace("\\", "/")
        return f"{clean_path}:{self.start_line}-{self.end_line}"


@dataclass
class ToolResult:
    tool_name: str
    arguments: Dict[str, Any]
    output_text: str
    retrieved_chunks: List[RetrievedChunkMeta] = field(default_factory=list)


class CodebaseTools:
    """Provides the 5 exact tools with strict row and size caps."""

    def __init__(
        self,
        store: BaseStore,
        repo_id: int,
        ollama_client: Optional[OllamaClient] = None,
    ):
        self.store = store
        self.repo_id = repo_id
        self.ollama_client = ollama_client
        # Track all chunks ever retrieved during the current turn/session
        self.session_retrieved_chunks: Dict[str, RetrievedChunkMeta] = {}

    def search_code(
        self,
        query: str,
        path_glob: Optional[str] = None,
        limit: int = 10,
    ) -> ToolResult:
        """Tool 1: Hybrid FTS + vector search with merged score."""
        limit = min(max(1, limit), 10)  # Hard cap at 10 results
        results = hybrid_search_code(
            store=self.store,
            repo_id=self.repo_id,
            query=query,
            ollama_client=self.ollama_client,
            path_glob=path_glob,
            limit=limit,
        )

        retrieved: List[RetrievedChunkMeta] = []
        output_lines = [f"Found {len(results)} chunks matching '{query}':"]

        for r in results:
            meta = RetrievedChunkMeta(
                file_path=r["file_path"],
                start_line=r["start_line"],
                end_line=r["end_line"],
                symbol_name=r["symbol_name"],
                text=r["text"],
                commit_sha=r.get("commit_sha", ""),
                repo_url=r.get("repo_url", ""),
            )
            retrieved.append(meta)
            self.session_retrieved_chunks[meta.citation] = meta

            output_lines.append(
                f"\n--- [{meta.citation}] {meta.symbol_name} ({r.get('kind', 'code')}) (score: {r.get('score', 0)}) ---"
            )
            output_lines.append(meta.text)

        output_text = "\n".join(output_lines)
        return ToolResult(
            tool_name="search_code",
            arguments={"query": query, "path_glob": path_glob, "limit": limit},
            output_text=output_text,
            retrieved_chunks=retrieved,
        )

    def get_file_summary(self, path: str) -> ToolResult:
        """Tool 2: Stored summary plus symbol list."""
        summary_data = self.store.get_file_summary(self.repo_id, path)
        if not summary_data:
            return ToolResult(
                tool_name="get_file_summary",
                arguments={"path": path},
                output_text=f"File '{path}' not found in indexed repository.",
            )

        symbols = summary_data.get("symbols", [])
        sym_desc = []
        for s in symbols[:50]:  # Cap symbol list to 50
            sym_desc.append(f"- {s['symbol_name']} ({s['kind']}): lines {s['start_line']}-{s['end_line']}")

        output_lines = [
            f"File: {path}",
            f"Language: {summary_data.get('language', 'unknown')}",
            f"Summary:\n{summary_data.get('summary', '')}",
            "\nSymbols Defined:",
            ("\n".join(sym_desc) if sym_desc else "No explicit top-level symbols."),
        ]
        return ToolResult(
            tool_name="get_file_summary",
            arguments={"path": path},
            output_text="\n".join(output_lines),
        )

    def get_symbol(self, name_or_path: str) -> ToolResult:
        """Tool 3: Exact lookup of a function or class with source."""
        results = self.store.get_symbol(self.repo_id, name_or_path)
        if not results:
            return ToolResult(
                tool_name="get_symbol",
                arguments={"name_or_path": name_or_path},
                output_text=f"Symbol or path '{name_or_path}' not found in indexed repository.",
            )

        retrieved: List[RetrievedChunkMeta] = []
        output_lines = [f"Found {len(results)} matches for '{name_or_path}':"]

        for r in results[:5]:  # Cap to 5 matches
            meta = RetrievedChunkMeta(
                file_path=r["file_path"],
                start_line=r["start_line"],
                end_line=r["end_line"],
                symbol_name=r["symbol_name"],
                text=r["text"],
                commit_sha=r.get("commit_sha", ""),
                repo_url=r.get("repo_url", ""),
            )
            retrieved.append(meta)
            self.session_retrieved_chunks[meta.citation] = meta

            output_lines.append(
                f"\n--- [{meta.citation}] {meta.symbol_name} ({r['kind']}) ---"
            )
            output_lines.append(meta.text)

        return ToolResult(
            tool_name="get_symbol",
            arguments={"name_or_path": name_or_path},
            output_text="\n".join(output_lines),
            retrieved_chunks=retrieved,
        )

    def get_callers(self, symbol: str, depth: int = 2) -> ToolResult:
        """Tool 4a: Graph traversal to find callers of a symbol (depth <= 2)."""
        depth = min(max(1, depth), 2)
        callers = self.store.get_callers(self.repo_id, symbol, depth=depth)

        if not callers:
            return ToolResult(
                tool_name="get_callers",
                arguments={"symbol": symbol, "depth": depth},
                output_text=f"No callers found in call graph for symbol '{symbol}'.",
            )

        output_lines = [f"Callers of '{symbol}' (depth <= {depth}):"]
        for c in callers[:20]:  # Cap to 20
            conf = c.get("confidence", "heuristic")
            caller = c.get("caller_symbol", "unknown")
            file_p = c.get("caller_file", "unknown")
            line = c.get("caller_line", "?")
            output_lines.append(f"- {caller} ({file_p}:{line}) [confidence: {conf}]")

        return ToolResult(
            tool_name="get_callers",
            arguments={"symbol": symbol, "depth": depth},
            output_text="\n".join(output_lines),
        )

    def get_callees(self, symbol: str, depth: int = 2) -> ToolResult:
        """Tool 4b: Graph traversal to find functions called by a symbol (depth <= 2)."""
        depth = min(max(1, depth), 2)
        callees = self.store.get_callees(self.repo_id, symbol, depth=depth)

        if not callees:
            return ToolResult(
                tool_name="get_callees",
                arguments={"symbol": symbol, "depth": depth},
                output_text=f"No callees found in call graph for symbol '{symbol}'.",
            )

        output_lines = [f"Callees of '{symbol}' (depth <= {depth}):"]
        for c in callees[:20]:  # Cap to 20
            conf = c.get("confidence", "heuristic")
            callee = c.get("callee_name", "unknown")
            file_p = c.get("callee_file", "external/unknown")
            line = c.get("callee_line", "?")
            output_lines.append(f"- {callee} ({file_p}:{line}) [confidence: {conf}]")

        return ToolResult(
            tool_name="get_callees",
            arguments={"symbol": symbol, "depth": depth},
            output_text="\n".join(output_lines),
        )

    def read_lines(self, path: str, start: int, end: int) -> ToolResult:
        """Tool 5: Read raw source lines (hard-capped at 200 lines per call)."""
        start = max(1, start)
        # Cap range to 200 lines max
        if end - start + 1 > settings.max_read_lines:
            end = start + settings.max_read_lines - 1

        content = self.store.read_lines(self.repo_id, path, start, end)
        if content is None:
            return ToolResult(
                tool_name="read_lines",
                arguments={"path": path, "start": start, "end": end},
                output_text=f"Could not read lines {start}-{end} from '{path}'.",
            )

        repo = self.store.get_repo(str(self.repo_id)) or {}
        meta = RetrievedChunkMeta(
            file_path=path,
            start_line=start,
            end_line=end,
            symbol_name=f"<{path}:{start}-{end}>",
            text=content,
            commit_sha=repo.get("last_commit_sha", ""),
            repo_url=repo.get("url", ""),
        )
        self.session_retrieved_chunks[meta.citation] = meta

        output_text = f"--- [{meta.citation}] ---\n{content}"
        return ToolResult(
            tool_name="read_lines",
            arguments={"path": path, "start": start, "end": end},
            output_text=output_text,
            retrieved_chunks=[meta],
        )

    def graphify_query(self, query: str) -> ToolResult:
        """Query knowledge graph extracted via Graphify if available."""
        import subprocess, shutil
        graphify_bin = shutil.which("graphify") or ".venv/bin/graphify"
        try:
            res = subprocess.run(
                [graphify_bin, "query", query],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = res.stdout if res.returncode == 0 else res.stderr
        except Exception as e:
            output = f"Graphify query unavailable: {e}"
        return ToolResult(
            tool_name="graphify_query",
            arguments={"query": query},
            output_text=output or "No graph paths found.",
        )

    def graphify_path(self, start_node: str, end_node: str) -> ToolResult:
        """Trace deterministic call path between two symbols using Graphify."""
        import subprocess, shutil
        graphify_bin = shutil.which("graphify") or ".venv/bin/graphify"
        try:
            res = subprocess.run(
                [graphify_bin, "path", start_node, end_node],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = res.stdout if res.returncode == 0 else res.stderr
        except Exception as e:
            output = f"Graphify path unavailable: {e}"
        return ToolResult(
            tool_name="graphify_path",
            arguments={"start_node": start_node, "end_node": end_node},
            output_text=output or f"No path found between {start_node} and {end_node}.",
        )

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """Dispatch a tool invocation by name."""
        if tool_name == "search_code":
            return self.search_code(
                query=arguments.get("query", ""),
                path_glob=arguments.get("path_glob"),
                limit=arguments.get("limit", 10),
            )
        elif tool_name == "get_file_summary":
            return self.get_file_summary(path=arguments.get("path", ""))
        elif tool_name == "get_symbol":
            return self.get_symbol(name_or_path=arguments.get("name_or_path", ""))
        elif tool_name == "get_callers":
            return self.get_callers(
                symbol=arguments.get("symbol", ""),
                depth=arguments.get("depth", 2),
            )
        elif tool_name == "get_callees":
            return self.get_callees(
                symbol=arguments.get("symbol", ""),
                depth=arguments.get("depth", 2),
            )
        elif tool_name == "read_lines":
            return self.read_lines(
                path=arguments.get("path", ""),
                start=int(arguments.get("start", 1)),
                end=int(arguments.get("end", 50)),
            )
        elif tool_name == "graphify_query":
            return self.graphify_query(query=arguments.get("query", ""))
        elif tool_name == "graphify_path":
            return self.graphify_path(
                start_node=arguments.get("start_node", ""),
                end_node=arguments.get("end_node", ""),
            )
        else:
            return ToolResult(
                tool_name=tool_name,
                arguments=arguments,
                output_text=f"Unknown tool '{tool_name}'. Available tools: search_code, get_file_summary, get_symbol, get_callers, get_callees, read_lines, graphify_query, graphify_path.",
            )
