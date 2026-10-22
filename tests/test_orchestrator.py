"""Tests for RepoSage orchestrator mode classification, tool loop, and token capping."""

import tempfile
import unittest
from pathlib import Path

from reposage.agent.orchestrator import RepoSageOrchestrator, estimate_tokens
from reposage.agent.prompts import classify_query
from reposage.agent.tools import RetrievedChunkMeta
from reposage.models.ollama_client import MockOllamaClient
from reposage.retrieval.store import SQLiteStore


class TestOrchestrator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_orch.db"
        self.store = SQLiteStore(self.db_path)

        # Seed repo
        self.repo_id = self.store.save_repo(
            "https://github.com/org/ecommerce", "main", "sha_orchestrator"
        )

        # Seed auth file with timeout bug
        f1 = self.store.save_file(
            self.repo_id,
            "auth/middleware.py",
            "python",
            "h_auth",
            "Session validation middleware",
        )
        self.store.save_chunk(
            file_id=f1,
            symbol_name="verify_session",
            kind="function",
            start_line=10,
            end_line=25,
            text="def verify_session(req):\n    # 300 second timeout bug\n    if time.time() - req.session.created > 300:\n        raise SessionExpired()",
            embedding=[1.0, 0.0],
        )

        # Seed orders service
        f2 = self.store.save_file(
            self.repo_id,
            "orders/service.py",
            "python",
            "h_order",
            "Order management service",
        )
        c2_id = self.store.save_chunk(
            file_id=f2,
            symbol_name="create_order",
            kind="function",
            start_line=5,
            end_line=18,
            text="def create_order(cart_id):\n    return checkout(cart_id)",
            embedding=[0.0, 1.0],
        )

        # Seed callee edge
        self.store.save_edge(
            caller_chunk_id=c2_id,
            callee_chunk_id=None,
            callee_name="checkout",
            kind="calls",
            confidence="resolved",
        )

        self.mock_client = MockOllamaClient()
        self.orchestrator = RepoSageOrchestrator(
            store=self.store,
            repo_id=self.repo_id,
            ollama_client=self.mock_client,
        )

    def tearDown(self):
        self.store.conn.close()
        self.temp_dir.cleanup()

    def test_query_classification(self):
        self.assertEqual(
            classify_query("What does auth/middleware.py do?"), "explain-file"
        )
        self.assertEqual(
            classify_query("How does create_order end up calling the payment gateway?"),
            "connection",
        )
        self.assertEqual(
            classify_query("Users get logged out after 5 minutes, where might this originate?"),
            "bug-hunt",
        )
        self.assertEqual(classify_query("Tell me about the project structure"), "general")

    def test_explain_file_orchestration(self):
        resp = self.orchestrator.run("What does auth/middleware.py do?")
        self.assertEqual(resp.mode, "explain-file")
        self.assertTrue(len(resp.tool_calls) <= 4)
        self.assertIn("auth/middleware.py:10-25", resp.retrieved_citations)
        self.assertTrue(resp.validation.is_grounded)
        self.assertIn("auth/middleware.py#L10-L25", resp.answer)

    def test_connection_orchestration(self):
        resp = self.orchestrator.run("How does create_order end up calling checkout?")
        self.assertEqual(resp.mode, "connection")
        self.assertTrue(len(resp.tool_calls) <= 4)
        self.assertIn("orders/service.py:5-18", resp.retrieved_citations)

    def test_bug_hunt_orchestration(self):
        resp = self.orchestrator.run("Users get logged out after 5 minutes, where might this originate?")
        self.assertEqual(resp.mode, "bug-hunt")
        self.assertTrue(len(resp.tool_calls) <= 4)
        # Should retrieve the session expiration chunk
        self.assertIn("auth/middleware.py:10-25", resp.retrieved_citations)
        self.assertTrue(resp.validation.is_grounded)
        self.assertIn("Ranked Suspects", resp.answer)

    def test_token_capping_limit(self):
        # Verify estimate_tokens works
        txt = "a" * 400
        self.assertEqual(estimate_tokens(txt), 100)


if __name__ == "__main__":
    unittest.main()
