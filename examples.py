"""
TradingView -> T212 Webhook Bridge - Usage Example

This module demonstrates how to use the Flask webhook bridge
and the T212 execution layer directly.
"""

from flask_webhook_bridge import (
    OrderRequest,
    OrderType,
    InstrumentType,
    T212ExecutionLayer,
)


def example_direct_execution():
    """Example: Execute orders directly via the execution layer."""
    execution = T212ExecutionLayer(
        email="your_email@example.com",
        password="your_password"
    )

    # Market buy order
    order = OrderRequest(
        symbol="AAPL",
        action="buy",
        order_type="market",
        quantity=10,
        instrument_type="equity"
    )
    result = execution.execute_order(order)
    print(f"Market buy result: {result}")

    # Limit sell order
    limit_order = OrderRequest(
        symbol="AAPL",
        action="sell",
        order_type="limit",
        limit_price=150.00,
        quantity=5,
        instrument_type="equity"
    )
    result = execution.execute_order(limit_order)
    print(f"Limit sell result: {result}")

    # Get current price
    price = execution.get_current_price("AAPL", "equity")
    print(f"AAPL current price: {price}")

    execution.close()


def example_cfd_order():
    """Example: Execute a CFD order with stop loss and take profit."""
    execution = T212ExecutionLayer(
        email="your_email@example.com",
        password="your_password"
    )

    order = OrderRequest(
        symbol="AAPL",
        action="buy",
        order_type="market",
        quantity=10,
        take_profit=160.00,
        stop_loss=140.00,
        instrument_type="cfd"
    )
    result = execution.execute_order(order)
    print(f"CFD order result: {result}")

    execution.close()


if __name__ == "__main__":
    print("=== Direct Execution Example ===")
    print("Uncomment and fill in credentials to run examples")
    # example_direct_execution()
    # example_cfd_order()