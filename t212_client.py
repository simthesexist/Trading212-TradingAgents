import requests
import base64
import logging
import time
from typing import Optional, Dict, List

import config

logger = logging.getLogger(__name__)


class T212Client:
    """Trading 212 API Client with Demo/Live mode switch"""

    def __init__(self):
        import importlib
        importlib.reload(config)

        self.base_url = config.get_t212_base_url()
        self.api_key, self.api_secret = config.get_t212_credentials()

        if self.api_secret:
            auth_str = base64.b64encode(f"{self.api_key}:{self.api_secret}".encode()).decode()
            self.headers = {
                "Authorization": f"Basic {auth_str}",
                "Content-Type": "application/json"
            }
        else:
            self.headers = {
                "Authorization": self.api_key,
                "Content-Type": "application/json"
            }

        logger.info(f"T212Client initialized with base URL: {self.base_url}")

    def _api_call(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make API call with retry logic for rate limits (429) and server errors"""
        retries = kwargs.pop("retries", 3)
        for attempt in range(retries):
            try:
                if "headers" not in kwargs:
                    kwargs["headers"] = self.headers
                response = requests.request(method, endpoint, timeout=15, **kwargs)

                if response.status_code == 429:
                    wait = (attempt + 1) * 2.0
                    logger.warning(f"Rate limited (429) on {endpoint}, retry {attempt+1}/{retries} in {wait}s")
                    time.sleep(wait)
                    continue

                if response.status_code == 401:
                    logger.error(f"Authentication failed for {endpoint}. Check your API key.")

                # T212 demo API sometimes returns 400 with empty body for invalid paths
                if response.status_code >= 400:
                    logger.warning(f"HTTP {response.status_code} for {endpoint}: {response.text[:150]}")

                response.raise_for_status()
                return response

            except requests.exceptions.HTTPError as e:
                if attempt < retries - 1 and e.response.status_code in (429, 500, 502, 503, 504):
                    wait = (attempt + 1) * 2.0
                    logger.warning(f"HTTP {e.response.status_code} on {endpoint}, retry {attempt+1}/{retries} in {wait}s")
                    time.sleep(wait)
                    continue
                logger.error(f"HTTP {e.response.status_code} for {endpoint}: {e.response.text[:200]}")
                raise
            except requests.exceptions.ConnectionError as e:
                if attempt < retries - 1:
                    wait = (attempt + 1) * 1.5
                    logger.warning(f"Connection error on {endpoint}, retry {attempt+1}/{retries} in {wait}s")
                    time.sleep(wait)
                    continue
                logger.error(f"Connection failed for {endpoint}: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error for {endpoint}: {e}")
                raise

        raise Exception(f"Failed after {retries} retries on {endpoint}")

    def get_account_summary(self) -> Dict:
        """Get account summary — returns empty dict on failure (fallback)"""
        try:
            response = self._api_call("GET", f"{self.base_url}/equity/account/summary")
            return response.json()
        except Exception as e:
            logger.warning(f"get_account_summary failed, returning fallback: {e}")
            return {"totalValue": 0.0, "equity": 0.0, "freeCash": 0.0, "currency": "GBP"}

    def get_positions(self) -> List[Dict]:
        """Get current positions from /equity/portfolio"""
        try:
            response = self._api_call("GET", f"{self.base_url}/equity/portfolio")
            raw = response.json()
            # Portfolio returns {"items": [...], ...} OR just a list [...directly
            if isinstance(raw, list):
                return raw  # already a list
            return raw.get("items", [])  # dict with items key
        except Exception as e:
            logger.warning(f"get_positions failed, returning fallback: {e}")
            return []

    def get_orders(self) -> List[Dict]:
        """Get pending orders"""
        try:
            response = self._api_call("GET", f"{self.base_url}/equity/orders")
            return response.json()
        except Exception as e:
            logger.warning(f"get_orders failed: {e}")
            return []

    def place_order(self, instrument_code: str, quantity: int, order_type: str = "market", side: str = "buy", limit_price: Optional[float] = None) -> Dict:
        """
        Place an order using the minimal payload that T212 accepts.

        DISCOVERY: T212's equity orders endpoint accepts ONLY ticker + quantity.
        Adding 'side', 'strategy', or 'type' fields causes 400 "Invalid payload" errors.
        T212 auto-detects BUY vs SELL based on whether you have an open position.
        - No position in ticker → BUY order
        - Have position in ticker → SELL order

        This is the only working format found after extensive testing.
        """
        # Map internal ticker format (e.g. "NFLX") to T212 format with _US_EQ suffix
        # For LSE stocks the format is like "LLOY_EQ" or "LLOY_GB" etc.
        ticker_value = self._format_ticker(instrument_code)
        
        # Minimal payload - only ticker + quantity work
        # Any additional fields (side, strategy, type, currency) cause 400 errors
        order_data = {
            "ticker": ticker_value,
            "quantity": float(quantity),
        }

        endpoint = f"{self.base_url}/equity/orders/market"
        logger.info(f"Placing order: {endpoint} — {order_data}")
        try:
            response = self._api_call("POST", endpoint, json=order_data)
            return response.json()
        except Exception as e:
            logger.error(f"place_order failed for {instrument_code} (ticker={ticker_value}): {e}")
            raise

    def _format_ticker(self, instrument_code: str) -> str:
        """
        Format instrument code to T212 ticker format.

        T212 uses format like:
        - US stocks: NFLX_US_EQ
        - UK stocks (LSE): XXXl_EQ (lowercase 'l' before _EQ suffix)

        DISCOVERED: UK stocks use lowercase 'l' suffix, not uppercase. Example: LLOY.L → LLOYl_EQ
        """
        # If already has T212 suffix — case-insensitive check to handle LLOYl_EQ
        for suffix in ["_US_EQ", "_l_EQ", "_l_GB", "_l_EU"]:
            if suffix.lower() in instrument_code.lower():
                return instrument_code  # preserve original case

        # Handle UK/LSE stocks (e.g. "HSBA.L" -> "HSBAl_EQ")
        if ".L" in instrument_code:
            base = instrument_code.replace(".L", "")
            return f"{base}l_EQ"  # lowercase l

        # Default: treat as US equity
        return f"{instrument_code.upper()}_US_EQ"

    def delete_order(self, order_id: str) -> Dict:
        """Cancel/delete an order"""
        response = self._api_call("DELETE", f"{self.base_url}/equity/orders/{order_id}")
        return response.json()

    def get_order_history(self) -> List[Dict]:
        """Get order history"""
        response = self._api_call("GET", f"{self.base_url}/equity/history/orders")
        return response.json()