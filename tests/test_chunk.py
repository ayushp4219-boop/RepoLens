"""Tests for parsing and chunking line range preservation."""

import unittest
from reposage.ingest.parse import parse_source_file
from reposage.ingest.chunk import chunk_file, extract_line_range


SAMPLE_PYTHON_CODE = '''"""Module docstring."""

import os

class OrderProcessor:
    """Handles order processing operations."""

    def __init__(self, tax_rate: float):
        self.tax_rate = tax_rate

    def calculate_total(self, subtotal: float) -> float:
        """Calculate total with tax."""
        return subtotal * (1 + self.tax_rate)


def create_order(subtotal: float) -> float:
    """Create a new order and calculate total."""
    processor = OrderProcessor(tax_rate=0.08)
    return processor.calculate_total(subtotal)
'''


class TestChunking(unittest.TestCase):
    def test_line_ranges_exact(self):
        file_path = "services/order.py"
        parsed = parse_source_file(file_path, SAMPLE_PYTHON_CODE, "python")
        chunks = chunk_file(
            repo_url="https://github.com/example/repo",
            commit_sha="abcdef123456",
            file_path=file_path,
            content=SAMPLE_PYTHON_CODE,
            language="python",
            symbols=parsed.symbols,
        )

        source_lines = SAMPLE_PYTHON_CODE.splitlines()

        # We expect OrderProcessor class, OrderProcessor.__init__, OrderProcessor.calculate_total, and create_order
        names = [c.symbol_name for c in chunks]
        self.assertIn("OrderProcessor", names)
        self.assertIn("OrderProcessor.__init__", names)
        self.assertIn("OrderProcessor.calculate_total", names)
        self.assertIn("create_order", names)

        # Verify that for every chunk, the text matches exact line slice
        for chunk in chunks:
            expected_text = "\n".join(source_lines[chunk.start_line - 1 : chunk.end_line])
            self.assertEqual(chunk.text, expected_text)
            self.assertTrue(1 <= chunk.start_line <= chunk.end_line <= len(source_lines))

        # Check create_order specifically
        create_order_chunk = next(c for c in chunks if c.symbol_name == "create_order")
        self.assertTrue(create_order_chunk.text.startswith("def create_order(subtotal: float)"))
        self.assertIn("Create a new order and calculate total.", create_order_chunk.docstring or "")
        self.assertEqual(create_order_chunk.kind, "function")

    def test_empty_file_and_module_chunk(self):
        empty_chunks = chunk_file(
            repo_url="https://github.com/example/repo",
            commit_sha="abcdef123456",
            file_path="empty.py",
            content="",
            language="python",
            symbols=[],
        )
        self.assertEqual(len(empty_chunks), 0)

        # File with only constants/statements
        script_code = "API_KEY = 'demo'\nDEBUG = True\n"
        parsed = parse_source_file("config.py", script_code, "python")
        chunks = chunk_file(
            repo_url="https://github.com/example/repo",
            commit_sha="abcdef123456",
            file_path="config.py",
            content=script_code,
            language="python",
            symbols=parsed.symbols,
        )
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].kind, "module")
        self.assertEqual(chunks[0].start_line, 1)
        self.assertEqual(chunks[0].end_line, 2)


if __name__ == "__main__":
    unittest.main()
