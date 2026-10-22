"""Storage layer with BaseStore interface, PostgresStore (pgvector), and SQLiteStore."""

import fnmatch
import json
import math
import re
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from reposage.config import settings


class BaseStore(ABC):
    @abstractmethod
    def init_db(self):
        """Initialize database schema, tables, and indexes."""
        pass

    @abstractmethod
    def save_repo(self, url: str, default_branch: str, commit_sha: str) -> int:
        """Upsert repo and return repo_id."""
        pass

    @abstractmethod
    def get_repo(self, url: str) -> Optional[Dict[str, Any]]:
        """Retrieve repo metadata by url or path."""
        pass

    @abstractmethod
    def save_file(
        self,
        repo_id: int,
        path: str,
        language: str,
        content_hash: str,
        summary: Optional[str] = None,
    ) -> int:
        """Upsert file entry and return file_id."""
        pass

    @abstractmethod
    def get_file(self, repo_id: int, path: str) -> Optional[Dict[str, Any]]:
        """Get file record by repo_id and path."""
        pass

    @abstractmethod
    def save_chunk(
        self,
        file_id: int,
        symbol_name: str,
        kind: str,
        start_line: int,
        end_line: int,
        text: str,
        embedding: Optional[List[float]] = None,
    ) -> int:
        """Save chunk and return chunk_id."""
        pass

    @abstractmethod
    def delete_file_chunks(self, file_id: int):
        """Remove chunks for a file during re-indexing."""
        pass

    @abstractmethod
    def save_edge(
        self,
        caller_chunk_id: Optional[int],
        callee_chunk_id: Optional[int],
        callee_name: str,
        kind: str,
        confidence: str,
    ) -> int:
        """Store an edge between symbols/chunks."""
        pass

    @abstractmethod
    def get_file_summary(self, repo_id: int, path: str) -> Optional[Dict[str, Any]]:
        """Return summary of file and list of symbols."""
        pass

    @abstractmethod
    def get_symbol(self, repo_id: int, name_or_path: str) -> List[Dict[str, Any]]:
        """Lookup function/class symbol and its source."""
        pass

    @abstractmethod
    def get_callers(self, repo_id: int, symbol: str, depth: int = 2) -> List[Dict[str, Any]]:
        """Find callers of symbol up to depth."""
        pass

    @abstractmethod
    def get_callees(self, repo_id: int, symbol: str, depth: int = 2) -> List[Dict[str, Any]]:
        """Find callees of symbol up to depth."""
        pass

    @abstractmethod
    def read_lines(
        self, repo_id: int, path: str, start_line: int, end_line: int
    ) -> Optional[str]:
        """Read raw source lines from indexed chunks."""
        pass

    @abstractmethod
    def hybrid_search(
        self,
        repo_id: int,
        query: str,
        query_embedding: Optional[List[float]] = None,
        path_glob: Optional[str] = None,
        limit: int = 10,
        keyword_weight: float = 0.4,
        vector_weight: float = 0.6,
    ) -> List[Dict[str, Any]]:
        """Hybrid search combining keyword and vector similarity."""
        pass

    @abstractmethod
    def audit_log(
        self,
        question: str,
        tool_calls: List[Dict[str, Any]],
        retrieved_chunk_ids: List[int],
        answer: str,
    ) -> int:
        """Audit-log a complete interaction."""
        pass

    def list_repos(self) -> List[Dict[str, Any]]:
        """List all indexed repositories."""
        return []

    def list_files(self, repo_id: int) -> List[Dict[str, Any]]:
        """List all files indexed for a repo."""
        return []

    @abstractmethod
    def get_audit_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent audit logs."""
        pass


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm_a = math.sqrt(sum(a * a for a in vec1))
    norm_b = math.sqrt(sum(b * b for b in vec2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def bm25_text_score(query: str, doc: str) -> float:
    """Lightweight keyword relevance score for text search."""
    q_tokens = [w.lower() for w in re.findall(r"[a-zA-Z0-9_]+", query) if len(w) > 1]
    if not q_tokens:
        return 0.0
    doc_lower = doc.lower()
    score = 0.0
    for tok in q_tokens:
        count = doc_lower.count(tok)
        if count > 0:
            score += 1.0 + math.log(1.0 + count)
    return score


class SQLiteStore(BaseStore):
    """Zero-dependency SQLite store with hybrid search and vector support."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or settings.sqlite_db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init_db()

    def init_db(self):
        cur = self.conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS repos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                default_branch TEXT,
                last_commit_sha TEXT
            );

            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_id INTEGER,
                path TEXT,
                language TEXT,
                content_hash TEXT,
                summary TEXT,
                UNIQUE(repo_id, path),
                FOREIGN KEY(repo_id) REFERENCES repos(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER,
                symbol_name TEXT,
                kind TEXT,
                start_line INTEGER,
                end_line INTEGER,
                text TEXT,
                embedding_json TEXT,
                FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                caller_chunk_id INTEGER,
                callee_chunk_id INTEGER,
                callee_name TEXT,
                kind TEXT,
                confidence TEXT
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT,
                tool_calls TEXT,
                retrieved_chunk_ids TEXT,
                answer TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
            CREATE INDEX IF NOT EXISTS idx_chunks_symbol ON chunks(symbol_name);
            CREATE INDEX IF NOT EXISTS idx_chunks_file_id ON chunks(file_id);
            CREATE INDEX IF NOT EXISTS idx_edges_caller ON edges(caller_chunk_id);
            CREATE INDEX IF NOT EXISTS idx_edges_callee ON edges(callee_chunk_id);
            CREATE INDEX IF NOT EXISTS idx_edges_name ON edges(callee_name);
        """)
        self.conn.commit()

    def save_repo(self, url: str, default_branch: str, commit_sha: str) -> int:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO repos (url, default_branch, last_commit_sha)
            VALUES (?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                default_branch=excluded.default_branch,
                last_commit_sha=excluded.last_commit_sha
            """,
            (url, default_branch, commit_sha),
        )
        self.conn.commit()
        cur.execute("SELECT id FROM repos WHERE url = ?", (url,))
        return cur.fetchone()["id"]

    def get_repo(self, url: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM repos WHERE url = ?", (url,))
        row = cur.fetchone()
        return dict(row) if row else None

    def save_file(
        self,
        repo_id: int,
        path: str,
        language: str,
        content_hash: str,
        summary: Optional[str] = None,
    ) -> int:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO files (repo_id, path, language, content_hash, summary)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(repo_id, path) DO UPDATE SET
                language=excluded.language,
                content_hash=excluded.content_hash,
                summary=COALESCE(excluded.summary, files.summary)
            """,
            (repo_id, path, language, content_hash, summary),
        )
        self.conn.commit()
        cur.execute(
            "SELECT id FROM files WHERE repo_id = ? AND path = ?", (repo_id, path)
        )
        return cur.fetchone()["id"]

    def get_file(self, repo_id: int, path: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM files WHERE repo_id = ? AND path = ?", (repo_id, path)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def delete_file_chunks(self, file_id: int):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))
        self.conn.commit()

    def save_chunk(
        self,
        file_id: int,
        symbol_name: str,
        kind: str,
        start_line: int,
        end_line: int,
        text: str,
        embedding: Optional[List[float]] = None,
    ) -> int:
        cur = self.conn.cursor()
        emb_json = json.dumps(embedding) if embedding else None
        cur.execute(
            """
            INSERT INTO chunks (file_id, symbol_name, kind, start_line, end_line, text, embedding_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (file_id, symbol_name, kind, start_line, end_line, text, emb_json),
        )
        self.conn.commit()
        return cur.lastrowid

    def save_edge(
        self,
        caller_chunk_id: Optional[int],
        callee_chunk_id: Optional[int],
        callee_name: str,
        kind: str,
        confidence: str,
    ) -> int:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO edges (caller_chunk_id, callee_chunk_id, callee_name, kind, confidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            (caller_chunk_id, callee_chunk_id, callee_name, kind, confidence),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_file_summary(self, repo_id: int, path: str) -> Optional[Dict[str, Any]]:
        file_rec = self.get_file(repo_id, path)
        if not file_rec:
            return None
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT symbol_name, kind, start_line, end_line
            FROM chunks
            WHERE file_id = ?
            ORDER BY start_line ASC
            """,
            (file_rec["id"],),
        )
        symbols = [dict(r) for r in cur.fetchall()]
        return {
            "path": file_rec["path"],
            "language": file_rec["language"],
            "summary": file_rec["summary"] or "No summary available.",
            "symbols": symbols,
        }

    def get_symbol(self, repo_id: int, name_or_path: str) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        # Look for exact symbol name or path match
        query = """
            SELECT c.id, c.symbol_name, c.kind, c.start_line, c.end_line, c.text,
                   f.path as file_path, r.url as repo_url, r.last_commit_sha as commit_sha
            FROM chunks c
            JOIN files f ON c.file_id = f.id
            JOIN repos r ON f.repo_id = r.id
            WHERE f.repo_id = ? AND (
                c.symbol_name = ?
                OR c.symbol_name LIKE ?
                OR f.path = ?
            )
            LIMIT 5
        """
        cur.execute(query, (repo_id, name_or_path, f"%.{name_or_path}", name_or_path))
        return [dict(r) for r in cur.fetchall()]

    def get_callers(self, repo_id: int, symbol: str, depth: int = 2) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        # Find callers where callee_name = symbol
        query = """
            SELECT e.id, e.kind, e.confidence, e.callee_name,
                   caller_c.symbol_name as caller_symbol,
                   caller_c.start_line as caller_line,
                   caller_f.path as caller_file
            FROM edges e
            LEFT JOIN chunks caller_c ON e.caller_chunk_id = caller_c.id
            LEFT JOIN files caller_f ON caller_c.file_id = caller_f.id
            WHERE (e.callee_name = ? OR e.callee_name LIKE ?)
            LIMIT 20
        """
        cur.execute(query, (symbol, f"%.{symbol}"))
        return [dict(r) for r in cur.fetchall()]

    def get_callees(self, repo_id: int, symbol: str, depth: int = 2) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        query = """
            SELECT e.id, e.kind, e.confidence, e.callee_name,
                   caller_c.symbol_name as caller_symbol,
                   callee_c.start_line as callee_line,
                   callee_f.path as callee_file
            FROM edges e
            JOIN chunks caller_c ON e.caller_chunk_id = caller_c.id
            LEFT JOIN chunks callee_c ON e.callee_chunk_id = callee_c.id
            LEFT JOIN files callee_f ON callee_c.file_id = callee_f.id
            WHERE (caller_c.symbol_name = ? OR caller_c.symbol_name LIKE ?)
            LIMIT 20
        """
        cur.execute(query, (symbol, f"%.{symbol}"))
        return [dict(r) for r in cur.fetchall()]

    def read_lines(
        self, repo_id: int, path: str, start_line: int, end_line: int
    ) -> Optional[str]:
        # Enforce max 200 lines per read_lines call
        if end_line - start_line + 1 > settings.max_read_lines:
            end_line = start_line + settings.max_read_lines - 1

        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT c.start_line, c.end_line, c.text
            FROM chunks c
            JOIN files f ON c.file_id = f.id
            WHERE f.repo_id = ? AND f.path = ?
            ORDER BY c.start_line ASC
            """,
            (repo_id, path),
        )
        rows = cur.fetchall()
        if not rows:
            return None

        # Assemble file content or overlapping chunks
        assembled_lines: Dict[int, str] = {}
        for r in rows:
            chunk_lines = r["text"].splitlines()
            for idx, line in enumerate(chunk_lines):
                ln = r["start_line"] + idx
                if start_line <= ln <= end_line:
                    assembled_lines[ln] = line

        if not assembled_lines:
            return None

        result_lines = [
            assembled_lines.get(ln, "")
            for ln in range(start_line, end_line + 1)
            if ln in assembled_lines
        ]
        return "\n".join(result_lines)

    def hybrid_search(
        self,
        repo_id: int,
        query: str,
        query_embedding: Optional[List[float]] = None,
        path_glob: Optional[str] = None,
        limit: int = 10,
        keyword_weight: float = 0.4,
        vector_weight: float = 0.6,
    ) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT c.id, c.symbol_name, c.kind, c.start_line, c.end_line, c.text,
                   c.embedding_json, f.path as file_path, r.url as repo_url, r.last_commit_sha as commit_sha
            FROM chunks c
            JOIN files f ON c.file_id = f.id
            JOIN repos r ON f.repo_id = r.id
            WHERE f.repo_id = ?
            """,
            (repo_id,),
        )
        rows = cur.fetchall()
        scored: List[Tuple[float, Dict[str, Any]]] = []

        max_bm25 = 1e-6
        raw_scores = []

        for r in rows:
            file_path = r["file_path"]
            if path_glob and not fnmatch.fnmatch(file_path, path_glob):
                continue

            text = r["text"]
            sym = r["symbol_name"]
            # Search both symbol and text
            kw_score = bm25_text_score(query, f"{sym}\n{text}\n{file_path}")
            if kw_score > max_bm25:
                max_bm25 = kw_score

            v_score = 0.0
            if query_embedding and r["embedding_json"]:
                emb = json.loads(r["embedding_json"])
                v_score = cosine_similarity(query_embedding, emb)

            item = {
                "id": r["id"],
                "symbol_name": r["symbol_name"],
                "kind": r["kind"],
                "start_line": r["start_line"],
                "end_line": r["end_line"],
                "text": r["text"],
                "file_path": r["file_path"],
                "repo_url": r["repo_url"],
                "commit_sha": r["commit_sha"],
            }
            raw_scores.append((kw_score, v_score, item))

        has_vectors = query_embedding is not None and any(r["embedding_json"] for r in rows)
        for kw, v, item in raw_scores:
            norm_kw = kw / max_bm25 if max_bm25 > 0 else 0.0
            if has_vectors:
                norm_v = max(0.0, min(1.0, (v + 1.0) / 2.0))
                combined = (keyword_weight * norm_kw) + (vector_weight * norm_v)
            else:
                combined = norm_kw
            if combined <= 0.0:
                continue
            item["score"] = round(combined, 4)
            scored.append((combined, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def audit_log(
        self,
        question: str,
        tool_calls: List[Dict[str, Any]],
        retrieved_chunk_ids: List[int],
        answer: str,
    ) -> int:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO audit_log (question, tool_calls, retrieved_chunk_ids, answer)
            VALUES (?, ?, ?, ?)
            """,
            (
                question,
                json.dumps(tool_calls),
                json.dumps(retrieved_chunk_ids),
                answer,
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_audit_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["tool_calls"] = json.loads(d["tool_calls"]) if d["tool_calls"] else []
            d["retrieved_chunk_ids"] = (
                json.loads(d["retrieved_chunk_ids"]) if d["retrieved_chunk_ids"] else []
            )
            result.append(d)
        return result

    def list_repos(self) -> List[Dict[str, Any]]:
        """List all indexed repos in SQLite."""
        cur = self.conn.cursor()
        cur.execute("SELECT id, url, default_branch, last_commit_sha FROM repos ORDER BY id DESC")
        return [dict(r) for r in cur.fetchall()]

    def list_files(self, repo_id: int) -> List[Dict[str, Any]]:
        """List all indexed files for a repo in SQLite."""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, repo_id, path, language, content_hash, summary FROM files WHERE repo_id = ? ORDER BY path ASC",
            (repo_id,),
        )
        return [dict(r) for r in cur.fetchall()]


class PostgresStore(BaseStore):
    """PostgreSQL store with pgvector HNSW index and GIN FTS/trigram indexes."""

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or settings.database_url
        self._pool = None

    def _get_connection(self):
        try:
            import psycopg
            from pgvector.psycopg import register_vector
            conn = psycopg.connect(self.db_url, autocommit=True)
            register_vector(conn)
            return conn
        except Exception as e:
            raise ConnectionError(f"Cannot connect to PostgreSQL at {self.db_url}: {e}")

    def init_db(self):
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS repos (
                    id SERIAL PRIMARY KEY,
                    url TEXT UNIQUE NOT NULL,
                    default_branch TEXT,
                    last_commit_sha TEXT
                );

                CREATE TABLE IF NOT EXISTS files (
                    id SERIAL PRIMARY KEY,
                    repo_id INTEGER REFERENCES repos(id) ON DELETE CASCADE,
                    path TEXT NOT NULL,
                    language TEXT,
                    content_hash TEXT,
                    summary TEXT,
                    UNIQUE(repo_id, path)
                );

                CREATE TABLE IF NOT EXISTS chunks (
                    id SERIAL PRIMARY KEY,
                    file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
                    symbol_name TEXT,
                    kind TEXT,
                    start_line INTEGER,
                    end_line INTEGER,
                    text TEXT,
                    embedding vector(768)
                );

                CREATE TABLE IF NOT EXISTS edges (
                    id SERIAL PRIMARY KEY,
                    caller_chunk_id INTEGER,
                    callee_chunk_id INTEGER,
                    callee_name TEXT,
                    kind TEXT,
                    confidence TEXT
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    id SERIAL PRIMARY KEY,
                    question TEXT,
                    tool_calls JSONB,
                    retrieved_chunk_ids JSONB,
                    answer TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);
                CREATE INDEX IF NOT EXISTS chunks_fts_idx ON chunks USING gin (to_tsvector('english', text));
                CREATE INDEX IF NOT EXISTS chunks_symbol_trgm ON chunks USING gin (symbol_name gin_trgm_ops);
                CREATE INDEX IF NOT EXISTS files_path_trgm ON files USING gin (path gin_trgm_ops);
            """)
        conn.close()

    def save_repo(self, url: str, default_branch: str, commit_sha: str) -> int:
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO repos (url, default_branch, last_commit_sha)
                VALUES (%s, %s, %s)
                ON CONFLICT (url) DO UPDATE SET
                    default_branch = EXCLUDED.default_branch,
                    last_commit_sha = EXCLUDED.last_commit_sha
                RETURNING id;
                """,
                (url, default_branch, commit_sha),
            )
            repo_id = cur.fetchone()[0]
        conn.close()
        return repo_id

    def get_repo(self, url: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT id, url, default_branch, last_commit_sha FROM repos WHERE url = %s", (url,))
            row = cur.fetchone()
            if not row:
                conn.close()
                return None
            result = {
                "id": row[0],
                "url": row[1],
                "default_branch": row[2],
                "last_commit_sha": row[3],
            }
        conn.close()
        return result

    def save_file(
        self,
        repo_id: int,
        path: str,
        language: str,
        content_hash: str,
        summary: Optional[str] = None,
    ) -> int:
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO files (repo_id, path, language, content_hash, summary)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (repo_id, path) DO UPDATE SET
                    language = EXCLUDED.language,
                    content_hash = EXCLUDED.content_hash,
                    summary = COALESCE(EXCLUDED.summary, files.summary)
                RETURNING id;
                """,
                (repo_id, path, language, content_hash, summary),
            )
            file_id = cur.fetchone()[0]
        conn.close()
        return file_id

    def get_file(self, repo_id: int, path: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, repo_id, path, language, content_hash, summary FROM files WHERE repo_id = %s AND path = %s",
                (repo_id, path),
            )
            row = cur.fetchone()
            if not row:
                conn.close()
                return None
            result = {
                "id": row[0],
                "repo_id": row[1],
                "path": row[2],
                "language": row[3],
                "content_hash": row[4],
                "summary": row[5],
            }
        conn.close()
        return result

    def delete_file_chunks(self, file_id: int):
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chunks WHERE file_id = %s", (file_id,))
        conn.close()

    def save_chunk(
        self,
        file_id: int,
        symbol_name: str,
        kind: str,
        start_line: int,
        end_line: int,
        text: str,
        embedding: Optional[List[float]] = None,
    ) -> int:
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chunks (file_id, symbol_name, kind, start_line, end_line, text, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (file_id, symbol_name, kind, start_line, end_line, text, embedding),
            )
            chunk_id = cur.fetchone()[0]
        conn.close()
        return chunk_id

    def save_edge(
        self,
        caller_chunk_id: Optional[int],
        callee_chunk_id: Optional[int],
        callee_name: str,
        kind: str,
        confidence: str,
    ) -> int:
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO edges (caller_chunk_id, callee_chunk_id, callee_name, kind, confidence)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (caller_chunk_id, callee_chunk_id, callee_name, kind, confidence),
            )
            edge_id = cur.fetchone()[0]
        conn.close()
        return edge_id

    def get_file_summary(self, repo_id: int, path: str) -> Optional[Dict[str, Any]]:
        file_rec = self.get_file(repo_id, path)
        if not file_rec:
            return None
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT symbol_name, kind, start_line, end_line
                FROM chunks
                WHERE file_id = %s
                ORDER BY start_line ASC
                """,
                (file_rec["id"],),
            )
            symbols = [
                {"symbol_name": r[0], "kind": r[1], "start_line": r[2], "end_line": r[3]}
                for r in cur.fetchall()
            ]
        conn.close()
        return {
            "path": file_rec["path"],
            "language": file_rec["language"],
            "summary": file_rec["summary"] or "No summary available.",
            "symbols": symbols,
        }

    def get_symbol(self, repo_id: int, name_or_path: str) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id, c.symbol_name, c.kind, c.start_line, c.end_line, c.text,
                       f.path, r.url, r.last_commit_sha
                FROM chunks c
                JOIN files f ON c.file_id = f.id
                JOIN repos r ON f.repo_id = r.id
                WHERE f.repo_id = %s AND (
                    c.symbol_name = %s
                    OR c.symbol_name LIKE %s
                    OR f.path = %s
                )
                LIMIT 5;
                """,
                (repo_id, name_or_path, f"%.{name_or_path}", name_or_path),
            )
            results = [
                {
                    "id": r[0],
                    "symbol_name": r[1],
                    "kind": r[2],
                    "start_line": r[3],
                    "end_line": r[4],
                    "text": r[5],
                    "file_path": r[6],
                    "repo_url": r[7],
                    "commit_sha": r[8],
                }
                for r in cur.fetchall()
            ]
        conn.close()
        return results

    def get_callers(self, repo_id: int, symbol: str, depth: int = 2) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT e.id, e.kind, e.confidence, e.callee_name,
                       caller_c.symbol_name, caller_c.start_line, caller_f.path
                FROM edges e
                LEFT JOIN chunks caller_c ON e.caller_chunk_id = caller_c.id
                LEFT JOIN files caller_f ON caller_c.file_id = caller_f.id
                WHERE (e.callee_name = %s OR e.callee_name LIKE %s)
                LIMIT 20;
                """,
                (symbol, f"%.{symbol}"),
            )
            results = [
                {
                    "id": r[0],
                    "kind": r[1],
                    "confidence": r[2],
                    "callee_name": r[3],
                    "caller_symbol": r[4],
                    "caller_line": r[5],
                    "caller_file": r[6],
                }
                for r in cur.fetchall()
            ]
        conn.close()
        return results

    def get_callees(self, repo_id: int, symbol: str, depth: int = 2) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT e.id, e.kind, e.confidence, e.callee_name,
                       caller_c.symbol_name, callee_c.start_line, callee_f.path
                FROM edges e
                JOIN chunks caller_c ON e.caller_chunk_id = caller_c.id
                LEFT JOIN chunks callee_c ON e.callee_chunk_id = callee_c.id
                LEFT JOIN files callee_f ON callee_c.file_id = callee_f.id
                WHERE (caller_c.symbol_name = %s OR caller_c.symbol_name LIKE %s)
                LIMIT 20;
                """,
                (symbol, f"%.{symbol}"),
            )
            results = [
                {
                    "id": r[0],
                    "kind": r[1],
                    "confidence": r[2],
                    "callee_name": r[3],
                    "caller_symbol": r[4],
                    "callee_line": r[5],
                    "callee_file": r[6],
                }
                for r in cur.fetchall()
            ]
        conn.close()
        return results

    def read_lines(
        self, repo_id: int, path: str, start_line: int, end_line: int
    ) -> Optional[str]:
        if end_line - start_line + 1 > settings.max_read_lines:
            end_line = start_line + settings.max_read_lines - 1

        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.start_line, c.end_line, c.text
                FROM chunks c
                JOIN files f ON c.file_id = f.id
                WHERE f.repo_id = %s AND f.path = %s
                ORDER BY c.start_line ASC;
                """,
                (repo_id, path),
            )
            rows = cur.fetchall()
        conn.close()

        if not rows:
            return None

        assembled: Dict[int, str] = {}
        for r_start, r_end, r_text in rows:
            lines = r_text.splitlines()
            for idx, line in enumerate(lines):
                ln = r_start + idx
                if start_line <= ln <= end_line:
                    assembled[ln] = line

        if not assembled:
            return None

        result_lines = [assembled[ln] for ln in range(start_line, end_line + 1) if ln in assembled]
        return "\n".join(result_lines)

    def hybrid_search(
        self,
        repo_id: int,
        query: str,
        query_embedding: Optional[List[float]] = None,
        path_glob: Optional[str] = None,
        limit: int = 10,
        keyword_weight: float = 0.4,
        vector_weight: float = 0.6,
    ) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        with conn.cursor() as cur:
            # Postgres hybrid search combining ts_rank and cosine similarity
            if query_embedding is not None:
                cur.execute(
                    """
                    SELECT c.id, c.symbol_name, c.kind, c.start_line, c.end_line, c.text,
                           f.path, r.url, r.last_commit_sha,
                           ts_rank_cd(to_tsvector('english', c.text), plainto_tsquery('english', %s)) as kw_rank,
                           1 - (c.embedding <=> %s::vector) as vec_sim
                    FROM chunks c
                    JOIN files f ON c.file_id = f.id
                    JOIN repos r ON f.repo_id = r.id
                    WHERE f.repo_id = %s
                      AND (%s IS NULL OR f.path LIKE %s)
                    ORDER BY (%s * ts_rank_cd(to_tsvector('english', c.text), plainto_tsquery('english', %s)) +
                              %s * (1 - (c.embedding <=> %s::vector))) DESC
                    LIMIT %s;
                    """,
                    (
                        query,
                        query_embedding,
                        repo_id,
                        path_glob,
                        path_glob.replace("*", "%") if path_glob else None,
                        keyword_weight,
                        query,
                        vector_weight,
                        query_embedding,
                        limit,
                    ),
                )
            else:
                cur.execute(
                    """
                    SELECT c.id, c.symbol_name, c.kind, c.start_line, c.end_line, c.text,
                           f.path, r.url, r.last_commit_sha,
                           ts_rank_cd(to_tsvector('english', c.text), plainto_tsquery('english', %s)) as kw_rank,
                           0.0 as vec_sim
                    FROM chunks c
                    JOIN files f ON c.file_id = f.id
                    JOIN repos r ON f.repo_id = r.id
                    WHERE f.repo_id = %s
                      AND (%s IS NULL OR f.path LIKE %s)
                    ORDER BY kw_rank DESC
                    LIMIT %s;
                    """,
                    (
                        query,
                        repo_id,
                        path_glob,
                        path_glob.replace("*", "%") if path_glob else None,
                        limit,
                    ),
                )

            rows = cur.fetchall()
            results = [
                {
                    "id": r[0],
                    "symbol_name": r[1],
                    "kind": r[2],
                    "start_line": r[3],
                    "end_line": r[4],
                    "text": r[5],
                    "file_path": r[6],
                    "repo_url": r[7],
                    "commit_sha": r[8],
                    "score": round((keyword_weight * float(r[9])) + (vector_weight * float(r[10])), 4),
                }
                for r in rows
            ]
        conn.close()
        return results

    def audit_log(
        self,
        question: str,
        tool_calls: List[Dict[str, Any]],
        retrieved_chunk_ids: List[int],
        answer: str,
    ) -> int:
        import json
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_log (question, tool_calls, retrieved_chunk_ids, answer)
                VALUES (%s, %s, %s, %s)
                RETURNING id;
                """,
                (
                    question,
                    json.dumps(tool_calls),
                    json.dumps(retrieved_chunk_ids),
                    answer,
                ),
            )
            audit_id = cur.fetchone()[0]
        conn.close()
        return audit_id

    def get_audit_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, question, tool_calls, retrieved_chunk_ids, answer, created_at FROM audit_log ORDER BY id DESC LIMIT %s",
                (limit,),
            )
            results = [
                {
                    "id": r[0],
                    "question": r[1],
                    "tool_calls": r[2],
                    "retrieved_chunk_ids": r[3],
                    "answer": r[4],
                    "created_at": str(r[5]),
                }
                for r in cur.fetchall()
            ]
        conn.close()
        return results


def get_store(backend: Optional[str] = None) -> BaseStore:
    """Factory to get the configured BaseStore instance."""
    selected_backend = (backend or settings.storage_backend).lower()
    if selected_backend == "postgres":
        try:
            store = PostgresStore()
            store.init_db()
            return store
        except Exception:
            # Fallback to SQLite if Postgres is unavailable
            return SQLiteStore()
    return SQLiteStore()
