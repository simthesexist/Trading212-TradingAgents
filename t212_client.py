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

    def _api_call(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make API call with error handling"""
        try:
            response = requests.request(method, endpoint, headers=self.headers, timeout=15, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP {e.response.status_code} for {endpoint}: {e.response.text[:200]}")
            raise
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error to {endpoint}: {e}")
            raise
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout for {endpoint}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error for {endpoint}: {e}")
            raise

    def get_account_summary(self) -> Dict:
        """Get account summary"""
        response = self._api_call("GET", f"{self.base_url}/equity/account/summary")
        return response.json()

    def get_positions(self) -> List[Dict]:
        """Get current positions"""
        response = self._api_call("GET", f"{self.base_url}/equity/positions")
        return response.json()

    def get_orders(self) -> List[Dict]:
        """Get pending orders"""
        response = self._api_call("GET", f"{self.base_url}/equity/orders")
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

        response = self._api_call("POST", endpoint, json=order_data)
        return response.json()

    def delete_order(self, order_id: str) -> Dict:
        """Cancel/delete an order"""
        response = self._api_call("DELETE", f"{self.base_url}/equity/orders/{order_id}")
        return response.json()

    def get_order_history(self) -> List[Dict]:
        """Get order history"""
        response = self._api_call("GET", f"{self.base_url}/equity/history/orders")
        return response.json()