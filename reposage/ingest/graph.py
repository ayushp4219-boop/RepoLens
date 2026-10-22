"""Call and import graph construction and resolution."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from reposage.ingest.chunk import CodeChunk
from reposage.ingest.parse import CallSite, ImportInfo, ParsedFile


@dataclass
class GraphEdge:
    caller_chunk_id: Optional[str]
    caller_symbol: str
    callee_chunk_id: Optional[str]
    callee_symbol: str
    kind: str  # "calls", "imports", "inherits"
    confidence: str  # "resolved" or "heuristic"
    caller_file: str
    callee_file: Optional[str] = None
    line_number: Optional[int] = None


class SymbolGraph:
    def __init__(self):
        # Maps chunk_id -> CodeChunk
        self.chunks: Dict[str, CodeChunk] = {}
        # Maps symbol_name -> List of chunk_ids
        self.symbol_to_chunk_ids: Dict[str, List[str]] = {}
        # Maps (file_path, symbol_name) -> chunk_id
        self.file_symbol_to_chunk_id: Dict[Tuple[str, str], str] = {}
        # Edges
        self.edges: List[GraphEdge] = []
        # Adjacency: caller_symbol -> edges
        self.callee_edges: Dict[str, List[GraphEdge]] = {}
        # Reverse adjacency: callee_symbol -> edges
        self.caller_edges: Dict[str, List[GraphEdge]] = {}

    def register_chunk(self, chunk_id: str, chunk: CodeChunk):
        self.chunks[chunk_id] = chunk
        self.symbol_to_chunk_ids.setdefault(chunk.symbol_name, []).append(chunk_id)
        self.file_symbol_to_chunk_id[(chunk.file_path, chunk.symbol_name)] = chunk_id

        # Also index bare function name if method (e.g. ClassName.fn -> fn)
        if "." in chunk.symbol_name:
            bare_name = chunk.symbol_name.split(".")[-1]
            self.symbol_to_chunk_ids.setdefault(bare_name, []).append(chunk_id)

    def build_edges(
        self,
        parsed_files: Dict[str, ParsedFile],
        chunks_by_file: Dict[str, List[Tuple[str, CodeChunk]]],
    ):
        """Resolve call sites and imports into graph edges."""
        for file_path, parsed in parsed_files.items():
            file_chunks = chunks_by_file.get(file_path, [])
            file_imports = parsed.imports

            # Build local import map: alias_or_name -> module / target
            import_map: Dict[str, str] = {}
            for imp in file_imports:
                key = imp.alias or imp.name
                import_map[key] = f"{imp.module}.{imp.name}" if imp.module else imp.name

            # Process all calls in this file
            for site in parsed.all_calls:
                caller_sym = site.caller_name
                callee_sym = site.callee_name
                caller_chunk_id = self.file_symbol_to_chunk_id.get((file_path, caller_sym))

                callee_chunk_id, callee_file, confidence = self._resolve_callee(
                    callee_name=callee_sym,
                    caller_file=file_path,
                    import_map=import_map,
                )

                edge = GraphEdge(
                    caller_chunk_id=caller_chunk_id,
                    caller_symbol=caller_sym,
                    callee_chunk_id=callee_chunk_id,
                    callee_symbol=callee_sym,
                    kind="calls",
                    confidence=confidence,
                    caller_file=file_path,
                    callee_file=callee_file,
                    line_number=site.line,
                )
                self.add_edge(edge)

    def _resolve_callee(
        self,
        callee_name: str,
        caller_file: str,
        import_map: Dict[str, str],
    ) -> Tuple[Optional[str], Optional[str], str]:
        """Attempt to resolve callee to a known chunk.
        
        Returns: (callee_chunk_id, callee_file, confidence)
        """
        # 1. Check if callee is in the same file
        if (caller_file, callee_name) in self.file_symbol_to_chunk_id:
            chunk_id = self.file_symbol_to_chunk_id[(caller_file, callee_name)]
            return chunk_id, caller_file, "resolved"

        # Check if caller is Class.method and callee is another method in same class
        if "." in callee_name:
            bare_callee = callee_name.split(".")[-1]
            if (caller_file, bare_callee) in self.file_symbol_to_chunk_id:
                chunk_id = self.file_symbol_to_chunk_id[(caller_file, bare_callee)]
                return chunk_id, caller_file, "resolved"

        # 2. Check if callee or its root was imported
        root_ident = callee_name.split(".")[0]
        if root_ident in import_map:
            imported_target = import_map[root_ident]
            # See if imported_target matches a known symbol
            target_symbol = callee_name.split(".")[-1]
            if target_symbol in self.symbol_to_chunk_ids:
                candidates = self.symbol_to_chunk_ids[target_symbol]
                if candidates:
                    target_chunk = self.chunks[candidates[0]]
                    return candidates[0], target_chunk.file_path, "resolved"

        # 3. Check if callee matches a globally unique symbol in the repo
        if callee_name in self.symbol_to_chunk_ids:
            candidates = self.symbol_to_chunk_ids[callee_name]
            if len(candidates) == 1:
                target_chunk = self.chunks[candidates[0]]
                return candidates[0], target_chunk.file_path, "heuristic"

        # Check bare function name
        bare_name = callee_name.split(".")[-1]
        if bare_name in self.symbol_to_chunk_ids:
            candidates = self.symbol_to_chunk_ids[bare_name]
            if len(candidates) == 1:
                target_chunk = self.chunks[candidates[0]]
                return candidates[0], target_chunk.file_path, "heuristic"

        # External / unresolvable
        return None, None, "heuristic"

    def add_edge(self, edge: GraphEdge):
        self.edges.append(edge)
        self.callee_edges.setdefault(edge.caller_symbol, []).append(edge)
        self.caller_edges.setdefault(edge.callee_symbol, []).append(edge)

        # Also index bare caller/callee names for lookup flexibility
        bare_caller = edge.caller_symbol.split(".")[-1]
        bare_callee = edge.callee_symbol.split(".")[-1]
        if bare_caller != edge.caller_symbol:
            self.callee_edges.setdefault(bare_caller, []).append(edge)
        if bare_callee != edge.callee_symbol:
            self.caller_edges.setdefault(bare_callee, []).append(edge)

    def get_callees(self, symbol: str, max_depth: int = 2) -> List[Dict]:
        """Find functions/methods called by the given symbol up to max_depth."""
        results: List[Dict] = []
        visited_edges: Set[Tuple[str, str, int]] = set()

        def dfs(current_sym: str, depth: int, chain: List[str]):
            if depth > max_depth:
                return
            edges = self.callee_edges.get(current_sym, [])
            for edge in edges:
                edge_key = (edge.caller_symbol, edge.callee_symbol, edge.line_number or 0)
                if edge_key in visited_edges:
                    continue
                visited_edges.add(edge_key)

                results.append(
                    {
                        "hop": depth,
                        "caller": edge.caller_symbol,
                        "callee": edge.callee_symbol,
                        "caller_file": edge.caller_file,
                        "callee_file": edge.callee_file,
                        "line": edge.line_number,
                        "kind": edge.kind,
                        "confidence": edge.confidence,
                        "chain": " -> ".join(chain + [edge.callee_symbol]),
                    }
                )
                dfs(edge.callee_symbol, depth + 1, chain + [edge.callee_symbol])

        dfs(symbol, 1, [symbol])
        return results

    def get_callers(self, symbol: str, max_depth: int = 2) -> List[Dict]:
        """Find functions/methods that call the given symbol up to max_depth."""
        results: List[Dict] = []
        visited_edges: Set[Tuple[str, str, int]] = set()

        def dfs(current_sym: str, depth: int, chain: List[str]):
            if depth > max_depth:
                return
            edges = self.caller_edges.get(current_sym, [])
            for edge in edges:
                edge_key = (edge.caller_symbol, edge.callee_symbol, edge.line_number or 0)
                if edge_key in visited_edges:
                    continue
                visited_edges.add(edge_key)

                results.append(
                    {
                        "hop": depth,
                        "caller": edge.caller_symbol,
                        "callee": edge.callee_symbol,
                        "caller_file": edge.caller_file,
                        "callee_file": edge.callee_file,
                        "line": edge.line_number,
                        "kind": edge.kind,
                        "confidence": edge.confidence,
                        "chain": " <- ".join([edge.caller_symbol] + chain),
                    }
                )
                dfs(edge.caller_symbol, depth + 1, [edge.caller_symbol] + chain)

        dfs(symbol, 1, [symbol])
        return results
