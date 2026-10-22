"""Tests for call graph resolution and multi-hop traversal."""

import unittest
from reposage.ingest.parse import parse_source_file
from reposage.ingest.chunk import chunk_file
from reposage.ingest.graph import SymbolGraph


ORDER_SERVICE_CODE = '''"""Order service."""
from payments.gateway import process_payment

def checkout(cart_id: str, amount: float):
    """Checkout cart and call payment."""
    return process_payment(amount)

def create_order(cart_id: str, amount: float):
    """Entrypoint to create order."""
    return checkout(cart_id, amount)
'''

PAYMENT_GATEWAY_CODE = '''"""Payment gateway."""

def charge_card(amount: float):
    """Charge credit card."""
    return True

def process_payment(amount: float):
    """Process payment entrypoint."""
    return charge_card(amount)
'''


class TestCallGraph(unittest.TestCase):
    def setUp(self):
        self.graph = SymbolGraph()

        # Parse and chunk order service
        parsed_order = parse_source_file("orders/service.py", ORDER_SERVICE_CODE, "python")
        order_chunks = chunk_file(
            repo_url="https://github.com/example/shop",
            commit_sha="c0ffee123456",
            file_path="orders/service.py",
            content=ORDER_SERVICE_CODE,
            language="python",
            symbols=parsed_order.symbols,
        )

        # Parse and chunk payment gateway
        parsed_pay = parse_source_file("payments/gateway.py", PAYMENT_GATEWAY_CODE, "python")
        pay_chunks = chunk_file(
            repo_url="https://github.com/example/shop",
            commit_sha="c0ffee123456",
            file_path="payments/gateway.py",
            content=PAYMENT_GATEWAY_CODE,
            language="python",
            symbols=parsed_pay.symbols,
        )

        # Register chunks
        chunks_by_file = {}
        for c in order_chunks:
            chunk_id = f"orders:{c.symbol_name}"
            self.graph.register_chunk(chunk_id, c)
            chunks_by_file.setdefault("orders/service.py", []).append((chunk_id, c))

        for c in pay_chunks:
            chunk_id = f"pay:{c.symbol_name}"
            self.graph.register_chunk(chunk_id, c)
            chunks_by_file.setdefault("payments/gateway.py", []).append((chunk_id, c))

        parsed_files = {
            "orders/service.py": parsed_order,
            "payments/gateway.py": parsed_pay,
        }

        self.graph.build_edges(parsed_files, chunks_by_file)

    def test_callee_chain_resolution(self):
        callees = self.graph.get_callees("create_order", max_depth=2)
        # Hop 1: create_order -> checkout
        # Hop 2: checkout -> process_payment
        self.assertTrue(len(callees) >= 2)

        hop1 = next((c for c in callees if c["hop"] == 1 and c["callee"] == "checkout"), None)
        self.assertIsNotNone(hop1)
        self.assertEqual(hop1["caller"], "create_order")
        self.assertEqual(hop1["confidence"], "resolved")

        hop2 = next((c for c in callees if c["hop"] == 2 and c["callee"] == "process_payment"), None)
        self.assertIsNotNone(hop2)
        self.assertEqual(hop2["caller"], "checkout")
        self.assertEqual(hop2["confidence"], "resolved")

    def test_caller_chain_resolution(self):
        callers = self.graph.get_callers("process_payment", max_depth=2)
        # Hop 1: checkout calls process_payment
        # Hop 2: create_order calls checkout
        self.assertTrue(len(callers) >= 2)

        hop1 = next((c for c in callers if c["hop"] == 1 and c["caller"] == "checkout"), None)
        self.assertIsNotNone(hop1)
        self.assertEqual(hop1["callee"], "process_payment")

        hop2 = next((c for c in callers if c["hop"] == 2 and c["caller"] == "create_order"), None)
        self.assertIsNotNone(hop2)
        self.assertEqual(hop2["callee"], "checkout")


if __name__ == "__main__":
    unittest.main()
