"""Code parsing and symbol extraction using AST and language patterns."""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class CallSite:
    caller_name: str
    callee_name: str
    line: int
    context: str = ""


@dataclass
class ImportInfo:
    module: str
    name: str
    alias: Optional[str] = None
    line: int = 1


@dataclass
class ParsedSymbol:
    name: str
    kind: str  # "function", "method", "class"
    start_line: int
    end_line: int
    docstring: Optional[str] = None
    calls: List[str] = field(default_factory=list)
    call_sites: List[CallSite] = field(default_factory=list)
    language: str = "python"


@dataclass
class ParsedFile:
    file_path: str
    language: str
    symbols: List[ParsedSymbol] = field(default_factory=list)
    imports: List[ImportInfo] = field(default_factory=list)
    all_calls: List[CallSite] = field(default_factory=list)


class PythonASTVisitor(ast.NodeVisitor):
    def __init__(self, source_lines: List[str]):
        self.source_lines = source_lines
        self.symbols: List[ParsedSymbol] = []
        self.imports: List[ImportInfo] = []
        self.all_calls: List[CallSite] = []
        self.current_class: Optional[str] = None
        self.current_function: Optional[str] = None

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append(
                ImportInfo(
                    module=alias.name,
                    name=alias.name,
                    alias=alias.asname,
                    line=node.lineno,
                )
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            self.imports.append(
                ImportInfo(
                    module=module,
                    name=alias.name,
                    alias=alias.asname,
                    line=node.lineno,
                )
            )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        class_name = node.name
        start_line = node.lineno
        end_line = getattr(node, "end_lineno", node.lineno)
        docstring = ast.get_docstring(node)

        # Include decorator lines in start_line if present
        if node.decorator_list:
            start_line = min(d.lineno for d in node.decorator_list)

        class_sym = ParsedSymbol(
            name=class_name,
            kind="class",
            start_line=start_line,
            end_line=end_line,
            docstring=docstring,
            language="python",
        )
        self.symbols.append(class_sym)

        old_class = self.current_class
        self.current_class = class_name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._handle_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._handle_function(node)

    def _handle_function(self, node):
        fn_name = node.name
        if self.current_class:
            full_name = f"{self.current_class}.{fn_name}"
            kind = "method"
        else:
            full_name = fn_name
            kind = "function"

        start_line = node.lineno
        if node.decorator_list:
            start_line = min(d.lineno for d in node.decorator_list)
        end_line = getattr(node, "end_lineno", node.lineno)
        docstring = ast.get_docstring(node)

        old_fn = self.current_function
        self.current_function = full_name

        calls: List[str] = []
        call_sites: List[CallSite] = []

        # Collect nested calls within this function
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                callee = self._extract_callee_name(child.func)
                if callee:
                    calls.append(callee)
                    line_num = getattr(child, "lineno", node.lineno)
                    ctx = ""
                    if 1 <= line_num <= len(self.source_lines):
                        ctx = self.source_lines[line_num - 1].strip()
                    call_site = CallSite(
                        caller_name=full_name,
                        callee_name=callee,
                        line=line_num,
                        context=ctx,
                    )
                    call_sites.append(call_site)
                    self.all_calls.append(call_site)

        sym = ParsedSymbol(
            name=full_name,
            kind=kind,
            start_line=start_line,
            end_line=end_line,
            docstring=docstring,
            calls=calls,
            call_sites=call_sites,
            language="python",
        )
        self.symbols.append(sym)

        # Do not recurse blindly into nested functions as current_function
        self.generic_visit(node)
        self.current_function = old_fn

    def _extract_callee_name(self, func_node) -> Optional[str]:
        if isinstance(func_node, ast.Name):
            return func_node.id
        elif isinstance(func_node, ast.Attribute):
            # e.g. self.do_something() or gateway.charge()
            val_name = self._extract_callee_name(func_node.value)
            if val_name:
                return f"{val_name}.{func_node.attr}"
            return func_node.attr
        return None


def parse_python_source(file_path: str, source: str) -> ParsedFile:
    """Parse python source using AST visitor."""
    lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=file_path)
        visitor = PythonASTVisitor(lines)
        visitor.visit(tree)
        return ParsedFile(
            file_path=file_path,
            language="python",
            symbols=visitor.symbols,
            imports=visitor.imports,
            all_calls=visitor.all_calls,
        )
    except SyntaxError:
        # Fallback to line-based parser if syntax is invalid
        return parse_generic_source(file_path, source, language="python")


def parse_generic_source(file_path: str, source: str, language: str) -> ParsedFile:
    """Fallback regex/line-based parser for non-Python or broken files."""
    lines = source.splitlines()
    symbols: List[ParsedSymbol] = []
    imports: List[ImportInfo] = []
    all_calls: List[CallSite] = []

    # Patterns for functions, classes, and calls
    fn_pattern = re.compile(
        r"^\s*(?:export\s+)?(?:async\s+)?(?:function\s+([a-zA-Z0-9_$]+)|(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>|def\s+([a-zA-Z0-9_$]+)|fn\s+([a-zA-Z0-9_$]+)|func\s+([a-zA-Z0-9_$]+))"
    )
    class_pattern = re.compile(
        r"^\s*(?:export\s+)?class\s+([a-zA-Z0-9_$]+)"
    )
    import_pattern = re.compile(
        r"^\s*(?:import\s+(?:\{([^}]+)\}|\*\s+as\s+([a-zA-Z0-9_$]+)|([a-zA-Z0-9_$]+))\s+from\s+['\"]([^'\"]+)['\"]|const\s+([a-zA-Z0-9_$]+)\s*=\s*require\(['\"]([^'\"]+)['\"]\))"
    )
    call_pattern = re.compile(r"([a-zA-Z0-9_$]+(?:\.[a-zA-Z0-9_$]+)?)\s*\(")

    current_sym: Optional[ParsedSymbol] = None

    for idx, line in enumerate(lines, start=1):
        # Check imports
        imp_match = import_pattern.match(line)
        if imp_match:
            mod = imp_match.group(4) or imp_match.group(6) or ""
            name = (
                imp_match.group(1)
                or imp_match.group(2)
                or imp_match.group(3)
                or imp_match.group(5)
                or ""
            )
            imports.append(ImportInfo(module=mod, name=name.strip(), line=idx))

        # Check class
        cls_match = class_pattern.match(line)
        if cls_match:
            if current_sym:
                current_sym.end_line = idx - 1
                symbols.append(current_sym)
            c_name = cls_match.group(1)
            current_sym = ParsedSymbol(
                name=c_name,
                kind="class",
                start_line=idx,
                end_line=len(lines),
                language=language,
            )
            continue

        # Check function
        fn_match = fn_pattern.match(line)
        if fn_match:
            if current_sym:
                current_sym.end_line = idx - 1
                symbols.append(current_sym)
            f_name = next(g for g in fn_match.groups() if g is not None)
            current_sym = ParsedSymbol(
                name=f_name,
                kind="function",
                start_line=idx,
                end_line=len(lines),
                language=language,
            )
            continue

        # Check calls within current symbol
        if current_sym:
            for match in call_pattern.finditer(line):
                callee = match.group(1)
                if callee not in {"if", "for", "while", "switch", "catch", "return"}:
                    current_sym.calls.append(callee)
                    site = CallSite(
                        caller_name=current_sym.name,
                        callee_name=callee,
                        line=idx,
                        context=line.strip(),
                    )
                    current_sym.call_sites.append(site)
                    all_calls.append(site)

    if current_sym:
        current_sym.end_line = len(lines)
        symbols.append(current_sym)

    return ParsedFile(
        file_path=file_path,
        language=language,
        symbols=symbols,
        imports=imports,
        all_calls=all_calls,
    )


def parse_source_file(file_path: str, source: str, language: str) -> ParsedFile:
    """Parse source file using best available parser for language."""
    if language == "python":
        return parse_python_source(file_path, source)
    return parse_generic_source(file_path, source, language)
