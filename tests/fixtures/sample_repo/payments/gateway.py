"""Payment processing gateway integrations."""


class PaymentGatewayClient:
    """External payment processor client."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def charge(self, amount: float, currency: str = "USD") -> dict:
        """Execute card charge transaction with provider."""
        return {
            "status": "success",
            "amount": amount,
            "currency": currency,
            "transaction_id": "tx_mock_12345",
        }


def process_payment(amount: float, currency: str = "USD") -> dict:
    """Primary entrypoint for payment processing."""
    client = PaymentGatewayClient(api_key="mock_key")
    return client.charge(amount, currency)
