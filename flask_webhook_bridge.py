"""
Trading 212 Execution Layer + Flask Webhook Bridge

Receives TradingView webhook signals and executes trades via T212 API.
Supports both Equity and CFD order types.
"""

import os
import json
import logging
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional
from flask import Flask, request, jsonify

# T212 REST API client (primary)
from t212_client import T212Client

# T212 API wrapper import (optional - community Selenium library)
# This is for reference only - we use t212_client.py for REST API instead
try:
    from Trading212API.equity import Equity
    from Trading212API.cfd import CFD
    T212_LEGACY_AVAILABLE = True
except ImportError:
    T212_LEGACY_AVAILABLE = False
    Equity = None
    CFD = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    VALUE = "value"


class InstrumentType(Enum):
    EQUITY = "equity"
    CFD = "cfd"


@dataclass
class OrderRequest:
    """Standard order request format from TradingView webhooks."""
    symbol: str
    action: str  # "buy" or "sell"
    order_type: str = "market"
    quantity: Optional[float] = None
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    instrument_type: str = "equity"


@dataclass
class OrderResult:
    """Standard order result format."""
    success: bool
    order_id: Optional[str] = None
    message: str = ""
    filled_price: Optional[float] = None


class T212ExecutionLayer:
    """
    Execution layer for Trading 212.

    Uses T212Client (REST API) for order execution.
    Falls back to legacy Selenium-based Trading212API if REST API fails.
    """

    def __init__(self, email: str = None, password: str = None):
        self.email = email or os.environ.get("T212_EMAIL")
        self.password = password or os.environ.get("T212_PASSWORD")
        self._t212_client: Optional[T212Client] = None
        self._equity_session: Optional[Equity] = None
        self._cfd_session: Optional[CFD] = None

    def _get_t212_client(self) -> T212Client:
        """Get or create T212 REST API client"""
        if self._t212_client is None:
            self._t212_client = T212Client()
        return self._t212_client

    def execute_order(self, order: OrderRequest) -> OrderResult:
        """Execute a trading order on T212 via REST API."""
        try:
            client = self._get_t212_client()

            # Use REST API via T212Client
            result = client.place_order(
                instrument_code=order.symbol,
                quantity=order.quantity or 1,
                order_type=order.order_type,
                side=order.action,
                limit_price=order.limit_price
            )

            return OrderResult(
                success=True,
                order_id=result.get("order_id") or result.get("id"),
                message="Order placed successfully via REST API",
                filled_price=result.get("filled_price") or result.get("price")
            )

        except Exception as e:
            logger.error(f"REST API order failed: {e}")
            # Fall back to legacy Selenium-based approach if available
            if T212_LEGACY_AVAILABLE:
                return self._execute_legacy(order)
            return OrderResult(success=False, message=str(e))

    def _execute_legacy(self, order: OrderRequest) -> OrderResult:
        """Fallback to Selenium-based Trading212API library"""
        try:
            if order.instrument_type.lower() == "cfd":
                return self._execute_cfd_order(order)
            return self._execute_equity_order(order)
        except Exception as e:
            logger.error(f"Legacy order execution failed: {e}")
            return OrderResult(success=False, message=str(e))

    def _get_equity(self) -> Equity:
        """Get legacy equity session (Selenium-based)"""
        if not T212_LEGACY_AVAILABLE:
            raise RuntimeError(
                "Trading212API library not installed. "
                "Install via: pip install trading212api"
            )
        if self._equity_session is None:
            self._equity_session = Equity(self.email, self.password)
        return self._equity_session

    def _get_cfd(self) -> CFD:
        """Get legacy CFD session (Selenium-based)"""
        if not T212_LEGACY_AVAILABLE:
            raise RuntimeError(
                "Trading212API library not installed. "
                "Install via: pip install trading212api"
            )
        if self._cfd_session is None:
            self._cfd_session = CFD(self.email, self.password)
        return self._cfd_session

    def check_order(self, order_id: str, instrument_type: str = "equity") -> dict:
        """Check status of an existing order via REST API"""
        try:
            client = self._get_t212_client()
            orders = client.get_orders()
            for order in orders:
                if str(order.get("id")) == str(order_id):
                    return {"status": "open", "order": order}
            # Not found in open orders - check history
            history = client.get_order_history()
            for order in history:
                if str(order.get("id")) == str(order_id):
                    return {"status": "filled/historical", "order": order}
            return {"status": "not_found", "order_id": order_id}
        except Exception as e:
            logger.error(f"REST API check_order failed: {e}")
            if T212_LEGACY_AVAILABLE:
                if instrument_type.lower() == "cfd":
                    return self._get_cfd().check_order(order_id)
                return self._get_equity().check_order(order_id)
            return {"error": str(e)}

    def get_current_price(self, symbol: str, instrument_type: str = "equity") -> float:
        """Get current price for a symbol"""
        if T212_LEGACY_AVAILABLE:
            if instrument_type.lower() == "cfd":
                return self._get_cfd().get_current_price(symbol)
            return self._get_equity().get_current_price(symbol)
        raise RuntimeError("No price source available - install trading212api for legacy support")

    def get_companies(self, instrument_type: str = "equity") -> list:
        """Get list of available instruments via REST API"""
        try:
            client = self._get_t212_client()
            positions = client.get_positions()
            return [p.get("instrument_code") or p.get("symbol") for p in positions]
        except Exception as e:
            logger.error(f"REST API get_companies failed: {e}")
            if T212_LEGACY_AVAILABLE:
                if instrument_type.lower() == "cfd":
                    return self._get_cfd().get_companies()
                return self._get_equity().get_companies()
            return []

    def close(self):
        """Close browser sessions and REST client"""
        self._t212_client = None
        if self._equity_session:
            self._equity_session.close()
        if self._cfd_session:
            self._cfd_session.close()
        equity = self._get_equity()

        if order.action.lower() == "buy":
            if order.order_type == OrderType.MARKET.value:
                result = equity.execute_order(
                    order.symbol, "buy", quantity=order.quantity
                )
            elif order.order_type == OrderType.LIMIT.value:
                result = equity.execute_order(
                    order.symbol, "buy", limit_price=order.limit_price
                )
            elif order.order_type == OrderType.STOP.value:
                result = equity.execute_order(
                    order.symbol, "buy", stop_price=order.stop_price
                )
            else:
                return OrderResult(
                    success=False,
                    message=f"Unsupported order type: {order.order_type}"
                )
        elif order.action.lower() == "sell":
            if order.order_type == OrderType.MARKET.value:
                result = equity.execute_order(
                    order.symbol, "sell", quantity=order.quantity
                )
            elif order.order_type == OrderType.LIMIT.value:
                result = equity.execute_order(
                    order.symbol, "sell", limit_price=order.limit_price
                )
            elif order.order_type == OrderType.STOP.value:
                result = equity.execute_order(
                    order.symbol, "sell", stop_price=order.stop_price
                )
            else:
                return OrderResult(
                    success=False,
                    message=f"Unsupported order type: {order.order_type}"
                )
        else:
            return OrderResult(
                success=False,
                message=f"Unknown action: {order.action}"
            )

        return OrderResult(
            success=result.get("success", False),
            order_id=result.get("order_id"),
            message=result.get("message", "Order processed"),
            filled_price=result.get("filled_price")
        )

    def _execute_cfd_order(self, order: OrderRequest) -> OrderResult:
        cfd = self._get_cfd()

        kwargs = {}
        if order.quantity:
            kwargs["quantity"] = order.quantity
        if order.limit_price:
            kwargs["limit_price"] = order.limit_price
        if order.stop_price:
            kwargs["stop_price"] = order.stop_price
        if order.take_profit:
            kwargs["take_profit"] = order.take_profit
        if order.stop_loss:
            kwargs["stop_loss"] = order.stop_loss

        if order.action.lower() == "buy":
            result = cfd.execute_order(order.symbol, "buy", **kwargs)
        elif order.action.lower() == "sell":
            result = cfd.execute_order(order.symbol, "sell", **kwargs)
        else:
            return OrderResult(success=False, message=f"Unknown action: {order.action}")

        return OrderResult(
            success=result.get("success", False),
            order_id=result.get("order_id"),
            message=result.get("message", "Order processed"),
            filled_price=result.get("filled_price")
        )

    def check_order(self, order_id: str, instrument_type: str = "equity") -> dict:
        """Check status of an existing order."""
        if instrument_type.lower() == "cfd":
            return self._get_cfd().check_order(order_id)
        return self._get_equity().check_order(order_id)

    def get_current_price(self, symbol: str, instrument_type: str = "equity") -> float:
        """Get current price for a symbol."""
        if instrument_type.lower() == "cfd":
            return self._get_cfd().get_current_price(symbol)
        return self._get_equity().get_current_price(symbol)

    def get_companies(self, instrument_type: str = "equity") -> list:
        """Get list of available instruments."""
        if instrument_type.lower() == "cfd":
            return self._get_cfd().get_companies()
        return self._get_equity().get_companies()

    def close(self):
        """Close browser sessions."""
        if self._equity_session:
            self._equity_session.close()
        if self._cfd_session:
            self._cfd_session.close()


# Flask Webhook Bridge
app = Flask(__name__)
execution_layer: Optional[T212ExecutionLayer] = None


@app.route("/webhook/tradingview", methods=["POST"])
def webhook_tradingview():
    """
    TradingView webhook endpoint.

    Expected payload:
    {
        "symbol": "AAPL",
        "action": "buy",
        "order_type": "market",
        "quantity": 10,
        "instrument_type": "equity"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON payload"}), 400

        order = OrderRequest(
            symbol=data.get("symbol"),
            action=data.get("action"),
            order_type=data.get("order_type", "market"),
            quantity=data.get("quantity"),
            limit_price=data.get("limit_price"),
            stop_price=data.get("stop_price"),
            take_profit=data.get("take_profit"),
            stop_loss=data.get("stop_loss"),
            instrument_type=data.get("instrument_type", "equity")
        )

        if not order.symbol or not order.action:
            return jsonify({
                "error": "Missing required fields: symbol, action"
            }), 400

        logger.info(f"Received order: {asdict(order)}")
        result = execution_layer.execute_order(order)

        return jsonify(asdict(result)), 200 if result.success else 400

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/order/check/<order_id>", methods=["GET"])
def check_order(order_id: str):
    """Check order status."""
    instrument_type = request.args.get("instrument_type", "equity")
    try:
        result = execution_layer.check_order(order_id, instrument_type)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/price/<symbol>", methods=["GET"])
def get_price(symbol: str):
    """Get current price for a symbol."""
    instrument_type = request.args.get("instrument_type", "equity")
    try:
        price = execution_layer.get_current_price(symbol, instrument_type)
        return jsonify({"symbol": symbol, "price": price})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/instruments", methods=["GET"])
def get_instruments():
    """Get list of available instruments."""
    instrument_type = request.args.get("instrument_type", "equity")
    try:
        instruments = execution_layer.get_companies(instrument_type)
        return jsonify({"instruments": instruments})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "t212_available": T212_LEGACY_AVAILABLE,
        "execution_layer_ready": execution_layer is not None
    })


def init_app(email: str = None, password: str = None) -> Flask:
    """Initialize the Flask app with T212 execution layer."""
    global execution_layer
    execution_layer = T212ExecutionLayer(email=email, password=password)
    return app


if __name__ == "__main__":
    init_app()
    app.run(host="0.0.0.0", port=5000, debug=False)