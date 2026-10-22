"""Tests for RepoSage API logic (execute_index_request and execute_ask_request)."""

import unittest
from pathlib import Path

from reposage.api import execute_ask_request, execute_index_request
from reposage.retrieval.store import SQLiteStore


class TestAPILogic(unittest.TestCase):
    def setUp(self):
        self.fixture_dir = Path(__file__).parent / "fixtures" / "sample_repo"

    def test_execute_index_and_ask_api(self):
        # 1. Test execute_index_request
        res_index = execute_index_request(str(self.fixture_dir))
        self.assertEqual(res_index["status"], "indexed")
        self.assertIn("repo_id", res_index)

        # 2. Test execute_ask_request
        res_ask = execute_ask_request(
            repo_url_or_path=str(self.fixture_dir),
            question="What does auth/middleware.py do?",
        )
        self.assertEqual(res_ask["mode"], "explain-file")
        self.assertTrue(res_ask["is_grounded"])
        self.assertIn("auth/middleware.py", res_ask["answer"])
        self.assertTrue(len(res_ask["sources"]) > 0)

        # 3. Test execute_ask_request bug hunt
        res_bug = execute_ask_request(
            repo_url_or_path=str(self.fixture_dir),
            question="Users get logged out after 5 minutes, where might this originate?",
        )
        self.assertEqual(res_bug["mode"], "bug-hunt")
        self.assertTrue(res_bug["is_grounded"])
        self.assertIn("auth/middleware.py", res_bug["answer"])
        self.assertTrue(len(res_bug["sources"]) > 0)


if __name__ == "__main__":
    unittest.main()
