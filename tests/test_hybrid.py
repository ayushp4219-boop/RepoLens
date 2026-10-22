"""Tests for hybrid search (keyword + vector) and retrieval ranking."""

import tempfile
import unittest
from pathlib import Path

from reposage.ingest.chunk import CodeChunk
from reposage.models.ollama_client import MockOllamaClient
from reposage.retrieval.hybrid import hybrid_search_code
from reposage.retrieval.store import SQLiteStore


class TestHybridRetrieval(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_hybrid.db"
        self.store = SQLiteStore(self.db_path)
        self.client = MockOllamaClient()

        # Seed test repository
        self.repo_id = self.store.save_repo(
            "https://github.com/example/auth-service", "main", "c0ffee123"
        )

        # File 1: auth middleware
        f1_id = self.store.save_file(
            self.repo_id, "auth/middleware.py", "python", "hash_auth", "Auth middleware"
        )
        c1 = CodeChunk(
            repo_url="https://github.com/example/auth-service",
            commit_sha="c0ffee123",
            file_path="auth/middleware.py",
            start_line=1,
            end_line=20,
            symbol_name="verify_session",
            kind="function",
            language="python",
            text="def verify_session(token: str):\n    # 300 second session timeout bug\n    if time.time() - session.created > 300:\n        raise SessionExpired()",
            docstring="Verify user session token validity.",
        )
        emb1 = self.client.embeddings(f"{c1.file_path} {c1.symbol_name} {c1.text}")
        self.store.save_chunk(
            f1_id, c1.symbol_name, c1.kind, c1.start_line, c1.end_line, c1.text, emb1
        )

        # File 2: payment gateway
        f2_id = self.store.save_file(
            self.repo_id, "payments/gateway.py", "python", "hash_pay", "Payment processing"
        )
        c2 = CodeChunk(
            repo_url="https://github.com/example/auth-service",
            commit_sha="c0ffee123",
            file_path="payments/gateway.py",
            start_line=5,
            end_line=30,
            symbol_name="process_payment",
            kind="function",
            language="python",
            text="def process_payment(amount: float):\n    gateway = StripeClient()\n    return gateway.charge(amount)",
            docstring="Charge customer amount via Stripe.",
        )
        emb2 = self.client.embeddings(f"{c2.file_path} {c2.symbol_name} {c2.text}")
        self.store.save_chunk(
            f2_id, c2.symbol_name, c2.kind, c2.start_line, c2.end_line, c2.text, emb2
        )

    def tearDown(self):
        self.store.conn.close()
        self.temp_dir.cleanup()

    def test_search_session_timeout(self):
        results = hybrid_search_code(
            store=self.store,
            repo_id=self.repo_id,
            query="session timeout expire 300 seconds",
            ollama_client=self.client,
            limit=5,
        )
        self.assertTrue(len(results) >= 1)
        top = results[0]
        self.assertEqual(top["file_path"], "auth/middleware.py")
        self.assertEqual(top["symbol_name"], "verify_session")
        self.assertEqual(top["citation"], "auth/middleware.py:1-20")

    def test_search_payment_with_path_glob(self):
        # Searching with a path glob should only return matching files
        results = hybrid_search_code(
            store=self.store,
            repo_id=self.repo_id,
            query="charge payment amount",
            ollama_client=self.client,
            path_glob="payments/*",
            limit=5,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["file_path"], "payments/gateway.py")

        # Disjoint path glob returns 0 results
        empty_results = hybrid_search_code(
            store=self.store,
            repo_id=self.repo_id,
            query="charge payment",
            ollama_client=self.client,
            path_glob="nonexistent/*",
            limit=5,
        )
        self.assertEqual(len(empty_results), 0)


if __name__ == "__main__":
    unittest.main()
