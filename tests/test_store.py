"""Tests for storage layer (BaseStore and SQLiteStore)."""

import tempfile
import unittest
from pathlib import Path
from reposage.retrieval.store import SQLiteStore, cosine_similarity, bm25_text_score


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.store = SQLiteStore(self.db_path)

    def tearDown(self):
        self.store.conn.close()
        self.temp_dir.cleanup()

    def test_repo_and_file_crud(self):
        repo_id = self.store.save_repo(
            url="https://github.com/example/repo",
            default_branch="main",
            commit_sha="a1b2c3d4e5f6",
        )
        self.assertIsInstance(repo_id, int)

        repo = self.store.get_repo("https://github.com/example/repo")
        self.assertEqual(repo["default_branch"], "main")
        self.assertEqual(repo["last_commit_sha"], "a1b2c3d4e5f6")

        file_id = self.store.save_file(
            repo_id=repo_id,
            path="auth/middleware.py",
            language="python",
            content_hash="hash123",
            summary="Session middleware for user auth.",
        )
        self.assertIsInstance(file_id, int)

        file_rec = self.store.get_file(repo_id, "auth/middleware.py")
        self.assertEqual(file_rec["language"], "python")
        self.assertEqual(file_rec["summary"], "Session middleware for user auth.")

    def test_chunks_and_hybrid_search(self):
        repo_id = self.store.save_repo("https://github.com/example/repo", "main", "sha123")
        file_id = self.store.save_file(repo_id, "payments/gateway.py", "python", "h1")

        # Save two chunks with embeddings
        # Chunk 1: charge_card (vector pointing towards [1.0, 0.0])
        c1_id = self.store.save_chunk(
            file_id=file_id,
            symbol_name="charge_card",
            kind="function",
            start_line=10,
            end_line=25,
            text="def charge_card(amount: float):\n    return payment_gateway.charge(amount)",
            embedding=[1.0, 0.0, 0.0],
        )

        # Chunk 2: refund_card (vector pointing towards [0.0, 1.0])
        c2_id = self.store.save_chunk(
            file_id=file_id,
            symbol_name="refund_card",
            kind="function",
            start_line=26,
            end_line=40,
            text="def refund_card(transaction_id: str):\n    return payment_gateway.refund(transaction_id)",
            embedding=[0.0, 1.0, 0.0],
        )

        # Search for "charge" with query embedding [1.0, 0.0, 0.0]
        results = self.store.hybrid_search(
            repo_id=repo_id,
            query="charge payment",
            query_embedding=[1.0, 0.0, 0.0],
            limit=5,
        )
        self.assertTrue(len(results) >= 1)
        top = results[0]
        self.assertEqual(top["symbol_name"], "charge_card")
        self.assertEqual(top["file_path"], "payments/gateway.py")
        self.assertTrue(top["score"] > 0.5)

    def test_read_lines(self):
        repo_id = self.store.save_repo("https://github.com/example/repo", "main", "sha123")
        file_id = self.store.save_file(repo_id, "utils.py", "python", "h2")

        chunk_text = "line 1\nline 2\nline 3\nline 4\nline 5"
        self.store.save_chunk(
            file_id=file_id,
            symbol_name="util_fn",
            kind="function",
            start_line=1,
            end_line=5,
            text=chunk_text,
        )

        lines = self.store.read_lines(repo_id, "utils.py", 2, 4)
        self.assertEqual(lines, "line 2\nline 3\nline 4")

    def test_audit_log(self):
        log_id = self.store.audit_log(
            question="Where is payment processed?",
            tool_calls=[{"tool": "search_code", "query": "payment"}],
            retrieved_chunk_ids=[1, 2],
            answer="Payments are processed in payments/gateway.py:10-25",
        )
        self.assertIsInstance(log_id, int)

        logs = self.store.get_audit_logs(limit=10)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["question"], "Where is payment processed?")
        self.assertEqual(logs[0]["tool_calls"][0]["tool"], "search_code")


if __name__ == "__main__":
    unittest.main()
