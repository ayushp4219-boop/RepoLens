"""End-to-end integration tests on fixture repo demonstrating the three key query types."""

import tempfile
import unittest
from pathlib import Path

from reposage.agent.orchestrator import RepoSageOrchestrator
from reposage.cli import run_indexing
from reposage.models.ollama_client import MockOllamaClient
from reposage.retrieval.store import SQLiteStore


class TestEndToEndFixtureRepo(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "e2e.db"
        self.store = SQLiteStore(self.db_path)
        self.fixture_path = Path(__file__).parent / "fixtures" / "sample_repo"

        # Index the fixture repo
        self.client = MockOllamaClient()
        self.repo_id = self.store.save_repo(
            str(self.fixture_path.resolve()), "main", "fixture_sha_12345"
        )

        from reposage.ingest.clone import scan_repo_files
        from reposage.ingest.parse import parse_source_file
        from reposage.ingest.chunk import chunk_file
        from reposage.ingest.graph import SymbolGraph

        files = list(scan_repo_files(self.fixture_path))
        graph = SymbolGraph()
        parsed_files = {}
        chunks_by_file = {}

        for f in files:
            parsed = parse_source_file(f.relative_path, f.content, f.language)
            parsed_files[f.relative_path] = parsed

            chunks = chunk_file(
                repo_url=str(self.fixture_path),
                commit_sha="fixture_sha_12345",
                file_path=f.relative_path,
                content=f.content,
                language=f.language,
                symbols=parsed.symbols,
            )

            file_id = self.store.save_file(
                repo_id=self.repo_id,
                path=f.relative_path,
                language=f.language,
                content_hash=f.content_hash,
                summary=f"Summary for {f.relative_path}",
            )

            for c in chunks:
                emb = self.client.embeddings(f"{c.file_path} {c.symbol_name} {c.text}")
                cid = self.store.save_chunk(
                    file_id=file_id,
                    symbol_name=c.symbol_name,
                    kind=c.kind,
                    start_line=c.start_line,
                    end_line=c.end_line,
                    text=c.text,
                    embedding=emb,
                )
                graph.register_chunk(str(cid), c)
                chunks_by_file.setdefault(f.relative_path, []).append((str(cid), c))

        graph.build_edges(parsed_files, chunks_by_file)
        for edge in graph.edges:
            self.store.save_edge(
                caller_chunk_id=int(edge.caller_chunk_id) if edge.caller_chunk_id else None,
                callee_chunk_id=int(edge.callee_chunk_id) if edge.callee_chunk_id else None,
                callee_name=edge.callee_symbol,
                kind=edge.kind,
                confidence=edge.confidence,
            )

        self.orchestrator = RepoSageOrchestrator(
            store=self.store,
            repo_id=self.repo_id,
            ollama_client=self.client,
        )

    def tearDown(self):
        self.store.conn.close()
        self.temp_dir.cleanup()

    def test_query_1_explain_file(self):
        """1. What does auth/middleware.py do?"""
        resp = self.orchestrator.run("What does auth/middleware.py do?")
        self.assertEqual(resp.mode, "explain-file")
        self.assertTrue(resp.validation.is_grounded)
        self.assertTrue(any("auth/middleware.py" in c for c in resp.retrieved_citations))
        self.assertIn("### Sources", resp.answer)
        self.assertIn("auth/middleware.py", resp.answer)

    def test_query_2_connection_trace(self):
        """2. How does create_order end up calling the payment gateway?"""
        resp = self.orchestrator.run(
            "How does create_order end up calling the payment gateway?"
        )
        self.assertEqual(resp.mode, "connection")
        self.assertTrue(resp.validation.is_grounded)
        self.assertTrue(
            any("orders/service.py" in c or "payments/gateway.py" in c for c in resp.retrieved_citations)
        )
        self.assertIn("### Sources", resp.answer)

    def test_query_3_bug_hunt_session_expiration(self):
        """3. Users get logged out after 5 minutes, where might this originate?"""
        resp = self.orchestrator.run(
            "Users get logged out after 5 minutes, where might this originate?"
        )
        self.assertEqual(resp.mode, "bug-hunt")
        self.assertTrue(resp.validation.is_grounded)
        # Auth middleware with the 300 second timeout must be retrieved
        auth_citations = [c for c in resp.retrieved_citations if "auth/middleware.py" in c]
        self.assertTrue(len(auth_citations) > 0)
        self.assertIn("Ranked Suspects", resp.answer)
        self.assertIn("auth/middleware.py", resp.answer)
        self.assertIn("### Sources", resp.answer)


if __name__ == "__main__":
    unittest.main()
