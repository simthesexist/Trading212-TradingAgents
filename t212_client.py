import requests
import base64
import logging
from typing import Optional, Dict, List
import config

logger = logging.getLogger(__name__)

class T212Client:
    """Trading 212 API Client with Demo/Live mode switch"""

    def __init__(self):
        # Re-read config at runtime to get current mode
        import importlib
        importlib.reload(config)

        self.base_url = config.get_t212_base_url()
        self.api_key, self.api_secret = config.get_t212_credentials()
        
        # T212 Public API v0 typically uses the API key directly in the Authorization header
        # or sometimes as Basic auth. We'll support both via a flexible approach.
        if self.api_secret:
            # If secret is present, use Basic Auth
            auth_str = base64.b64encode(f"{self.api_key}:{self.api_secret}".encode()).decode()
            self.headers = {
                "Authorization": f"Basic {auth_str}",
                "Content-Type": "application/json"
            }
        else:
            # If no secret, use the key directly (standard for T212 Public API v0)
            self.headers = {
                "Authorization": self.api_key,
                "Content-Type": "application/json"
            }
            
        logger.info(f"T212Client initialized with base URL: {self.base_url}")

    def _api_call(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make API call with error handling"""
        try:
            # Inject headers into kwargs if not present
            if 'headers' not in kwargs:
                kwargs['headers'] = self.headers
                
            response = requests.request(method, endpoint, timeout=15, **kwargs)
            
            if response.status_code == 401:
                logger.error(f"Authentication failed for {endpoint}. Check your API key.")
                
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP {e.response.status_code} for {endpoint}: {e.response.text[:200]}")
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
        response = self._api_call("GET", f"{self.base_url}/equity/portfolio/positions")
        return response.json()

    def get_orders(self) -> List[Dict]:
        """Get pending orders"""
        response = self._api_call("GET", f"{self.base_url}/equity/orders")
        return response.json()

    def place_order(self, instrument_code: str, quantity: int, order_type: str = "market", side: str = "buy", limit_price: Optional[float] = None) -> Dict:
        """
        Place an order
        """
        endpoint = f"{self.base_url}/equity/orders/{order_type}"

        order_data = {
            "instrumentCode": instrument_code,
            "quantity": quantity
        }
        
        # T212 API v0 expects different fields for different order types
        if order_type == "market":
            # Market order doesn't need limitPrice
            pass
        elif order_type == "limit":
            order_data["limitPrice"] = limit_price
        
        # Side is usually part of the data or endpoint?
        # In T212 v0, it's often POST /equity/orders/market with side in payload
        order_data["side"] = side.upper()

        response = self._api_call("POST", endpoint, json=order_data)
        return response.json()

    def delete_order(self, order_id: str) -> Dict:
        """Cancel/delete an order"""
        response = self._api_call("DELETE", f"{self.base_url}/equity/orders/{order_id}")
        return response.json()

    def get_order_history(self) -> List[Dict]:
        """Get order history"""
        # Note: v0 history endpoint is /equity/history/orders or similar
        response = self._api_call("GET", f"{self.base_url}/equity/history/orders")
        return response.json()
