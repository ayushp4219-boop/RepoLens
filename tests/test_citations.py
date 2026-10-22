"""Tests for citation extraction, validation, and hallucination rejection."""

import unittest
from reposage.agent.citations import (
    build_github_permalink,
    extract_citations,
    validate_citations,
)
from reposage.agent.tools import RetrievedChunkMeta


class TestCitations(unittest.TestCase):
    def test_extract_citations(self):
        text = "Check auth/middleware.py:10-25 and payments/gateway.py:42 for details."
        citations = extract_citations(text)
        self.assertEqual(len(citations), 2)
        self.assertEqual(citations[0], ("auth/middleware.py", 10, 25))
        self.assertEqual(citations[1], ("payments/gateway.py", 42, 42))

    def test_build_github_permalink(self):
        permalink = build_github_permalink(
            repo_url="https://github.com/my-org/my-repo.git",
            commit_sha="abcd1234efgh5678",
            file_path="src/main.py",
            start_line=15,
            end_line=30,
        )
        expected = "https://github.com/my-org/my-repo/blob/abcd1234efgh5678/src/main.py#L15-L30"
        self.assertEqual(permalink, expected)

    def test_validator_accepts_retrieved_citations(self):
        retrieved = {
            "auth/middleware.py:10-30": RetrievedChunkMeta(
                file_path="auth/middleware.py",
                start_line=10,
                end_line=30,
                symbol_name="verify_session",
                text="def verify_session(): ...",
                commit_sha="sha1",
                repo_url="https://github.com/org/repo",
            )
        }

        answer = "The session check occurs in auth/middleware.py:12-20."
        res = validate_citations(
            answer=answer,
            retrieved_chunks=retrieved,
            repo_url="https://github.com/org/repo",
            commit_sha="sha1",
        )

        self.assertTrue(res.is_grounded)
        self.assertEqual(len(res.valid_citations), 1)
        self.assertIn("### Sources", res.final_answer)
        self.assertIn("https://github.com/org/repo/blob/sha1/auth/middleware.py#L12-L20", res.final_answer)

    def test_validator_rejects_fabricated_citations(self):
        retrieved = {
            "auth/middleware.py:10-30": RetrievedChunkMeta(
                file_path="auth/middleware.py",
                start_line=10,
                end_line=30,
                symbol_name="verify_session",
                text="def verify_session(): ...",
                commit_sha="sha1",
                repo_url="https://github.com/org/repo",
            )
        }

        # Fabricated citation 1: file never retrieved (database/models.py:5-10)
        # Fabricated citation 2: out-of-range lines in retrieved file (auth/middleware.py:200-250)
        answer = "The bug is in database/models.py:5-10 and auth/middleware.py:200-250."
        res = validate_citations(
            answer=answer,
            retrieved_chunks=retrieved,
            repo_url="https://github.com/org/repo",
            commit_sha="sha1",
        )

        # Zero valid citations -> must reject and state lack of evidence
        self.assertFalse(res.is_grounded)
        self.assertEqual(len(res.valid_citations), 0)
        self.assertEqual(len(res.invalid_citations), 2)
        self.assertIn("I couldn't find evidence in the repo", res.final_answer)


if __name__ == "__main__":
    unittest.main()
