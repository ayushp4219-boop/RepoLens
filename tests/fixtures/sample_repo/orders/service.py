"""Order processing service connecting cart to payment gateway."""

from payments.gateway import process_payment


def checkout(order_id: str, amount: float) -> dict:
    """Execute order checkout by charging payment."""
    payment_result = process_payment(amount=amount, currency="USD")
    return {
        "order_id": order_id,
        "payment": payment_result,
        "status": "completed",
    }


def create_order(cart_id: str, user_id: str, amount: float) -> dict:
    """Create order from user cart and initiate checkout."""
    order_id = f"ord_{cart_id}_{user_id}"
    return checkout(order_id=order_id, amount=amount)
