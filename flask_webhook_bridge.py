"""
Minimal fallback - T212ExecutionLayer and OrderRequest
Only used by app.py for webhook execution
"""
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class OrderRequest:
    symbol: str
    action: str  # "buy" or "sell"
    quantity: int
    order_type: str = "market"
    instrument_type: str = "equity"
    limit_price: Optional[float] = None

class T212ExecutionLayer:
    """Execute orders via T212Client"""

    def __init__(self):
        from t212_client import T212Client
        self.t212 = T212Client()

    def execute_order(self, order: OrderRequest) -> dict:
        """Execute a single order"""
        try:
            side = order.action  # "buy" or "sell"
            result = self.t212.place_order(
                instrument_code=order.symbol,
                quantity=order.quantity,
                order_type=order.order_type,
                side=side,
                limit_price=order.limit_price
            )
            logger.info(f"Order executed: {side} {order.quantity} {order.symbol}")
            return {"status": "executed", "order": result}
        except Exception as e:
            logger.error(f"Order execution failed: {e}")
            return {"status": "failed", "error": str(e)}