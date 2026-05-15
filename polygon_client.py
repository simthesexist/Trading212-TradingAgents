"""
Data providers for LSE stock data.
Primary: yfinance (free, no API key needed)
Fallback: Polygon.io (requires API key, limited free tier)
"""

import os
import logging
import time
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

def _retry_with_backoff(fn, retries=3, base_delay=2.0, max_delay=16.0):
    """Execute fn with exponential backoff on failure."""
    for attempt in range(retries):
        try:
            result = fn()
            if result is None and attempt < retries - 1:
                delay = min(base_delay * (2 ** attempt), max_delay)
                logger.debug(f"Retry {attempt+1}/{retries} after {delay:.1f}s")
                time.sleep(delay)
                continue
            return result
        except Exception as e:
            if attempt < retries - 1:
                delay = min(base_delay * (2 ** attempt), max_delay)
                logger.warning(f"Attempt {attempt+1}/{retries} failed: {e}, retry in {delay:.1f}s")
                time.sleep(delay)
            else:
                raise

class YFinanceDataProvider:
    """Free Yahoo Finance data provider - no API key needed"""
    
    def __init__(self):
        self.initialized = True
        logger.info("YFinance data provider initialized (free)")
    
    def get_aggregate_bars(
        self,
        symbol: str,
        timespan: str = "minute",
        multiplier: int = 1,
        from_date: str = None,
        to_date: str = None,
        limit: int = 100
    ) -> Optional[List[Dict]]:
        """
        Get OHLCV bars using yfinance with retry and exponential backoff.
        For LSE stocks, yfinance uses .L suffix (e.g., HSBA.L)
        """
        def _fetch():
            import yfinance as yf

            ticker = yf.Ticker(symbol)

            # Convert timespan to yfinance interval
            if timespan == "minute":
                interval = "5m" if multiplier >= 5 else "1m"
            elif timespan == "hour":
                interval = "1h"
            else:
                interval = "1d"

            # Get historical data
            hist = ticker.history(period="5d", interval=interval, actions=False)

            if hist.empty or len(hist) < 10:
                logger.warning(f"Insufficient data for {symbol} from yfinance")
                return None

            bars = []
            for idx, row in hist.iterrows():
                bars.append({
                    "symbol": symbol,
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": int(row["Volume"]),
                    "timestamp": idx.isoformat()
                })

            return bars[-limit:] if len(bars) > limit else bars

        try:
            result = _retry_with_backoff(_fetch, retries=3, base_delay=2.0, max_delay=8.0)
            return result
        except Exception as e:
            logger.error(f"yfinance failed for {symbol} after retries: {e}")
            return None
    
    def get_ticker_news(self, symbol: str, limit: int = 20) -> Optional[List[Dict]]:
        """
        Get news using yfinance with enhanced fetching.
        Returns financial news articles for the ticker.
        """
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)

            # Try get_news() first (more comprehensive)
            try:
                news_items = ticker.get_news()
            except Exception:
                news_items = ticker.news

            if not news_items:
                return None

            # Normalize news data from various possible formats
            results = []
            for n in news_items[:limit]:
                # Handle different news item formats from yfinance
                if isinstance(n, dict):
                    # New format with nested 'content' or direct fields
                    content = n.get('content', n)
                    results.append({
                        "symbol": symbol,
                        "title": content.get('title', ''),
                        "url": content.get('canonicalUrl', content.get('originalUrl', '')),
                        "published": content.get('pubDate', content.get('publishTime', '')),
                        "publisher": content.get('provider', {}).get('displayName', '') if isinstance(content.get('provider'), dict) else content.get('provider', ''),
                        "summary": content.get('summary', ''),
                        "related": content.get('relatedSymbols', [])
                    })
                else:
                    # Legacy format
                    results.append({
                        "symbol": symbol,
                        "title": getattr(n, 'title', ''),
                        "url": getattr(n, 'link', ''),
                        "published": getattr(n, 'pubDate', ''),
                        "publisher": getattr(n, 'publisher', '')
                    })

            return results if results else None

        except Exception as e:
            logger.error(f"yfinance news failed for {symbol}: {e}")
            return None
    
    def get_prev_close(self, symbol: str) -> Optional[Dict]:
        """Get previous close using yfinance"""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="2d")
            if len(hist) >= 2:
                last = hist.iloc[-2]
                return {
                    "symbol": symbol,
                    "close": float(last["Close"]),
                    "open": float(last["Open"]),
                    "high": float(last["High"]),
                    "low": float(last["Low"]),
                    "volume": int(last["Volume"]),
                    "timestamp": last.name.isoformat()
                }
            return None
        except Exception as e:
            logger.error(f"yfinance prev_close failed for {symbol}: {e}")
            return None

class PolygonDataProvider:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("POLYGON_API_KEY", "")
        self.client = None
        if self.api_key:
            try:
                from polygon import RESTClient
                self.client = RESTClient(self.api_key)
                logger.info("Polygon.io client initialized")
            except ImportError:
                logger.warning("polygon package not installed. Run: pip install polygon-api-client")
        else:
            logger.warning("POLYGON_API_KEY not set")

    def _format_symbol(self, symbol: str) -> str:
        """Convert LSE symbol format: HSBA.L -> XLON:HSBA"""
        return f"XLON:{symbol.replace('.L', '')}"

    def get_aggregate_bars(
        self,
        symbol: str,
        timespan: str = "minute",
        multiplier: int = 1,
        from_date: str = None,
        to_date: str = None,
        limit: int = 50
    ) -> Optional[List[Dict]]:
        """
        Get OHLCV aggregate bars for a ticker.

        Args:
            symbol: LSE ticker (e.g., "HSBA.L")
            timespan: minute, hour, day, week, month
            multiplier: multiplier for timespan (e.g., 5 for 5-minute bars)
            from_date: start date ISO format (YYYY-MM-DD)
            to_date: end date ISO format (YYYY-MM-DD)
            limit: max number of bars (free tier limited)
        """
        if not self.client:
            return None

        try:
            ticker = self._format_symbol(symbol)
            kwargs = {"timespan": timespan, "multiplier": multiplier, "limit": limit}

            if from_date:
                kwargs["from"] = from_date
            if to_date:
                kwargs["to"] = to_date

            bars = self.client.get_aggregate_bars(ticker, **kwargs)
            return [
                {
                    "symbol": symbol,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "timestamp": bar.timestamp
                }
                for bar in bars
            ]
        except Exception as e:
            logger.error(f"Failed to get aggregate bars for {symbol}: {e}")
            return None

    def get_ticker_news(self, symbol: str, limit: int = 10) -> Optional[List[Dict]]:
        """Get news for a ticker"""
        if not self.client:
            return None

        try:
            ticker = self._format_symbol(symbol)
            news = self.client.get_ticker_news(ticker, limit=limit)
            return [
                {
                    "symbol": symbol,
                    "title": n.title,
                    "url": n.url,
                    "published": n.published_utc,
                    "publisher": n.publisher.name if n.publisher else None
                }
                for n in news
            ]
        except Exception as e:
            logger.error(f"Failed to get news for {symbol}: {e}")
            return None

    def get_prev_close(self, symbol: str) -> Optional[Dict]:
        """Get previous day close price"""
        if not self.client:
            return None

        try:
            ticker = self._format_symbol(symbol)
            prev = self.client.get_previous_close(ticker)
            if prev and prev.results:
                r = prev.results[0]
                return {
                    "symbol": symbol,
                    "close": r.close,
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "volume": r.volume,
                    "timestamp": r.timestamp
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get prev close for {symbol}: {e}")
            return None

    def get_daily_price(self, symbol: str, date: str = None) -> Optional[Dict]:
        """Get daily price for a specific date"""
        if not self.client:
            return None

        try:
            from datetime import datetime, timedelta

            ticker = self._format_symbol(symbol)

            if not date:
                date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

            aggs = self.client.get_aggregate_bars(
                ticker,
                timespan="day",
                multiplier=1,
                from_=date,
                to=date,
                limit=1
            )

            if aggs and len(aggs) > 0:
                bar = aggs[0]
                return {
                    "symbol": symbol,
                    "date": date,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get daily price for {symbol}: {e}")
            return None


def get_polygon_client() -> PolygonDataProvider:
    """Factory function to get Polygon client"""
    return PolygonDataProvider()