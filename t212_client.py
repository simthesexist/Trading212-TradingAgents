import requests
import base64
import logging
from typing import Optional, Dict, List
import config  # Import module, not values - we read values at runtime

logger = logging.getLogger(__name__)

class T212Client:
    """Trading 212 API Client with Demo/Live mode switch"""

    def __init__(self):
        # Re-read config at runtime to get current mode
        import importlib
        importlib.reload(config)

        self.base_url = config.get_t212_base_url()
        self.api_key, self.api_secret = config.get_t212_credentials()
        self.auth = base64.b64encode(
            f"{self.api_key}:{self.api_secret}".encode()
        ).decode()
        self.headers = {
            "Authorization": f"Basic {self.auth}",
            "Content-Type": "application/json"
        }
        logger.info(f"T212Client initialized with base URL: {self.base_url}")

    def get_account_summary(self) -> Dict:
        """Get account summary"""
        response = requests.get(
            f"{self.base_url}/equity/account/summary",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_positions(self) -> List[Dict]:
        """Get current positions"""
        response = requests.get(
            f"{self.base_url}/equity/positions",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_orders(self) -> List[Dict]:
        """Get pending orders"""
        response = requests.get(
            f"{self.base_url}/equity/orders",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def place_order(self, instrument_code: str, quantity: int, order_type: str = "market", side: str = "buy", limit_price: Optional[float] = None) -> Dict:
        """
        Place an order
        order_type: "market", "limit", "stop", "stop_limit"
        side: "buy" or "sell"
        """
        endpoint = f"{self.base_url}/equity/orders"

        order_data = {
            "instrument_code": instrument_code,
            "quantity": quantity,
            "order_type": order_type,
            "side": side
        }

        if limit_price:
            order_data["limit_price"] = limit_price

        response = requests.post(endpoint, headers=self.headers, json=order_data)
        response.raise_for_status()
        return response.json()

    def delete_order(self, order_id: str) -> Dict:
        """Cancel/delete an order"""
        response = requests.delete(
            f"{self.base_url}/equity/orders/{order_id}",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_order_history(self) -> List[Dict]:
        """Get order history"""
        response = requests.get(
            f"{self.base_url}/equity/history/orders",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()