"""
Stock monitor service.
Run in background thread to continuously monitor watchlist.
"""

import logging
import os
import time
import threading
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field
from watchlist import LSE_WATCHLIST
from strategies import STRATEGIES, STRATEGY_KEYS
from polygon_client import YFinanceDataProvider, PolygonDataProvider
from position_tracker import get_tracker
from execution_rules import ExecutionRules

# Try to import ZoneInfo (Python 3.9+)
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

try:
    from news_sentiment import get_sentiment_analyzer, SentimentResult
    HAS_NEWS_SENTIMENT = True
except ImportError:
    HAS_NEWS_SENTIMENT = False

try:
    import holidays
    # UK public holidays (London Stock Exchange)
    UK_HOLIDAYS = holidays.UK(years=range(2020, 2030))
    HAS_HOLIDAYS = True
except ImportError:
    HAS_HOLIDAYS = False
    UK_HOLIDAYS = []
    logging.getLogger(__name__).warning("Optional dependency 'holidays' not found. Bank holiday checks will be skipped.")

def is_lse_market_open() -> bool:
    """
    Check if LSE market is currently open (UK local time, GMT/BST aware).
    Returns True if within 07:45-16:45 UK local time on weekdays.
    UK bank holidays are excluded if 'holidays' package is available.
    """
    try:
        if ZoneInfo:
            uk_tz = ZoneInfo("Europe/London")
            now_uk = datetime.now(uk_tz)
        else:
            # Fallback if ZoneInfo not available
            now_uk = datetime.now()
    except Exception:
        # Fallback if ZoneInfo fails (e.g. missing tzdata)
        now_uk = datetime.now() 

    # Weekend check (Saturday=5, Sunday=6)
    if now_uk.weekday() >= 5:
        return False

    # UK bank holiday check
    if HAS_HOLIDAYS and now_uk.date() in UK_HOLIDAYS:
        return False

    # LSE open: 07:45 to 16:45 UK local time (handles GMT/BST automatically)
    current_minutes = now_uk.hour * 60 + now_uk.minute
    return 465 <= current_minutes < 1005

# Use yfinance as primary (free), fallback to Polygon.io if API key available
def get_data_provider():
    polygon_key = os.getenv("POLYGON_API_KEY", "")
    if polygon_key:
        return PolygonDataProvider(polygon_key)
    return YFinanceDataProvider()

logger = logging.getLogger(__name__)

BUY_SIGNAL_STRATEGIES = frozenset({
    "RSI_OVERSOLD", "RSI_EXTREME_OVERSOLD",
    "MA_CROSS_ABOVE", "MACD_CROSS_ABOVE",
    "VOLUME_SPIKE", "PRICE_DROP_5PCT",
    "NEWS_BULLISH", "NEWS_VERY_BULLISH",
    "EARNINGS_BEAT", "DIVIDEND_INCREASE", "UPGRADE",
})

@dataclass
class Alert:
    """Represents a triggered alert"""
    timestamp: datetime
    symbol: str
    strategy_key: str
    strategy_name: str
    priority: str
    message: str
    indicator_value: float = 0.0
    details: Dict = field(default_factory=dict)
    stock_mentioned: bool = False

@dataclass
class StockStatus:
    """Status of a monitored stock"""
    symbol: str
    price: float = 0.0
    price_change_pct: float = 0.0
    rsi: float = 0.0
    volume: float = 0.0
    volume_avg: float = 0.0
    prev_close: float = 0.0
    ma_fast: float = 0.0
    ma_slow: float = 0.0
    macd: float = 0.0
    macd_signal: float = 0.0
    last_updated: datetime = None
    active_alerts: List[Alert] = field(default_factory=list)

class StockMonitor:
    def __init__(
        self,
        poll_interval: int = 60,
        on_alert: Optional[Callable[[Alert], None]] = None
    ):
        """
        Initialize stock monitor.

        Args:
            poll_interval: Seconds between polls (default 60)
            on_alert: Callback function when alert triggered
        """
        self.poll_interval = poll_interval
        self.on_alert = on_alert

        self.running = False
        self.monitor_thread = None

        self.watched_stocks: Dict[str, StockStatus] = {}
        self.alerts: List[Alert] = []
        self.alert_history: List[Alert] = []

        # Initialize data provider (yfinance by default, polygon if key available)
        self.data_provider = get_data_provider()

        # Position tracking and execution rules
        self.position_tracker = get_tracker()
        self.execution_rules = ExecutionRules(self.position_tracker)

        # Previous values for crossover detection
        self.prev_values: Dict[str, Dict] = {}

        # News sentiment state
        self.sentiment_analyzer = None
        self.sentiment_cache: Dict[str, SentimentResult] = {}
        self.news_cache: Dict[str, List[Dict]] = {}
        self.news_hashes: Dict[str, str] = {} # For change detection

        if HAS_NEWS_SENTIMENT:
            try:
                self.sentiment_analyzer = get_sentiment_analyzer()
                logger.info("News sentiment analyzer initialized")
            except Exception as e:
                logger.warning(f"Could not initialize sentiment analyzer: {e}")

        for symbol in LSE_WATCHLIST:
            self.watched_stocks[symbol] = StockStatus(symbol=symbol)
            self.prev_values[symbol] = {}

    def _calculate_rsi(self, prices: List[float], period: int = 14) -> Optional[float]:
        """Calculate RSI from price list"""
        if len(prices) < period + 1:
            return None

        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas[-period:]]
        losses = [-d if d < 0 else 0 for d in deltas[-period:]]

        avg_gain = sum(gains) / period if gains else 0
        avg_loss = sum(losses) / period if losses else 0

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _calculate_sma(self, prices: List[float], period: int) -> Optional[float]:
        """Calculate SMA from price list"""
        if len(prices) < period:
            return None
        return sum(prices[-period:]) / period

    def _calculate_macd(
        self,
        prices: List[float],
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Optional[Dict]:
        """Calculate MACD, signal line, and histogram"""
        if len(prices) < slow + signal:
            return None

        def ema(data, period):
            if not data: return 0
            k = 2 / (period + 1)
            ema_val = data[0]
            for d in data[1:]:
                ema_val = d * k + ema_val * (1 - k)
            return ema_val

        ema_fast = ema(prices, fast)
        ema_slow = ema(prices, slow)
        macd_line = ema_fast - ema_slow

        macd_values = []
        for i in range(slow, len(prices)):
            e_f = ema(prices[:i+1], fast)
            e_s = ema(prices[:i+1], slow)
            macd_values.append(e_f - e_s)

        if len(macd_values) >= signal:
            signal_line = ema(macd_values, signal)
            return {
                "macd": macd_line,
                "signal": signal_line,
                "histogram": macd_line - signal_line
            }

        return {"macd": macd_line, "signal": 0, "histogram": macd_line}

    def _calculate_avg_volume(self, volumes: List[float], period: int = 20) -> float:
        """Calculate average volume"""
        if not volumes:
            return 0
        relevant = volumes[-period:] if len(volumes) >= period else volumes
        return sum(relevant) / len(relevant) if relevant else 0

    def update_stock_data(self, symbol: str) -> bool:
        """Fetch and update data for a single stock"""
        try:
            bars = self.data_provider.get_aggregate_bars(
                symbol,
                timespan="minute",
                multiplier=5,
                limit=100
            )

            if not bars or len(bars) < 10:
                logger.warning(f"Insufficient data for {symbol}: only {len(bars) if bars else 0} bars")
                return False

            prices = [b["close"] for b in bars]
            volumes = [b["volume"] for b in bars]

            status = self.watched_stocks[symbol]
            status.price = prices[-1]
            status.volume = volumes[-1]
            status.volume_avg = self._calculate_avg_volume(volumes)
            status.rsi = self._calculate_rsi(prices) or 0
            status.ma_fast = self._calculate_sma(prices, 50) or 0
            status.ma_slow = self._calculate_sma(prices, 200) or 0

            macd_data = self._calculate_macd(prices)
            if macd_data:
                status.macd = macd_data["macd"]
                status.macd_signal = macd_data["signal"]

            # Calculate price change from previous close
            prev_close_data = self.data_provider.get_prev_close(symbol)
            if prev_close_data:
                status.prev_close = prev_close_data.get("close", prices[0])
            else:
                status.prev_close = prices[0]
            
            status.price_change_pct = ((status.price - status.prev_close) / status.prev_close) * 100 if status.prev_close else 0

            status.last_updated = datetime.now()

            logger.info(
                f"{symbol}: price={status.price:.2f} ({status.price_change_pct:+.1f}%), "
                f"rsi={status.rsi:.1f}, vol={status.volume:.0f}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to update {symbol}: {e}")
            return False

    def check_strategies(self, symbol: str) -> List[Alert]:
        """Check all strategies against stock data"""
        alerts = []
        status = self.watched_stocks[symbol]
        prev = self.prev_values.get(symbol, {})

        for strategy_key, strategy in STRATEGIES.items():
            try:
                indicator = strategy["indicator"]
                condition = strategy["condition"]
                threshold = strategy.get("threshold")

                # RSI checks
                if indicator == "RSI":
                    if condition == "crosses_below":
                        prev_rsi = prev.get("rsi", 50)
                        if prev_rsi >= threshold > status.rsi:
                            alerts.append(Alert(
                                timestamp=datetime.now(),
                                symbol=symbol,
                                strategy_key=strategy_key,
                                strategy_name=strategy["name"],
                                priority=strategy["priority"],
                                message=strategy["description"],
                                indicator_value=status.rsi
                            ))
                    elif condition == "crosses_above":
                        prev_rsi = prev.get("rsi", 50)
                        if prev_rsi <= threshold < status.rsi:
                            alerts.append(Alert(
                                timestamp=datetime.now(),
                                symbol=symbol,
                                strategy_key=strategy_key,
                                strategy_name=strategy["name"],
                                priority=strategy["priority"],
                                message=strategy["description"],
                                indicator_value=status.rsi
                            ))

                # Volume checks
                elif indicator == "Volume":
                    if status.volume_avg > 0:
                        ratio = status.volume / status.volume_avg
                        if condition == "spikes_above" and ratio >= threshold:
                            alerts.append(Alert(
                                timestamp=datetime.now(),
                                symbol=symbol,
                                strategy_key=strategy_key,
                                strategy_name=strategy["name"],
                                priority=strategy["priority"],
                                message=f"{strategy['description']} (vol={ratio:.1f}x avg)",
                                indicator_value=ratio
                            ))
                        elif condition == "drops_below" and ratio <= threshold:
                            alerts.append(Alert(
                                timestamp=datetime.now(),
                                symbol=symbol,
                                strategy_key=strategy_key,
                                strategy_name=strategy["name"],
                                priority=strategy["priority"],
                                message=f"{strategy['description']} (vol={ratio:.1f}x avg)",
                                indicator_value=ratio
                            ))

                # MA crossover checks
                elif indicator == "MA" and status.ma_fast > 0 and status.ma_slow > 0:
                    prev_fast = prev.get("ma_fast", status.ma_fast)
                    prev_slow = prev.get("ma_slow", status.ma_slow)

                    if condition == "fast_crosses_above_slow":
                        if prev_fast <= prev_slow and status.ma_fast > status.ma_slow:
                            alerts.append(Alert(
                                timestamp=datetime.now(),
                                symbol=symbol,
                                strategy_key=strategy_key,
                                strategy_name=strategy["name"],
                                priority=strategy["priority"],
                                message=strategy["description"],
                                indicator_value=status.ma_fast
                            ))
                    elif condition == "fast_crosses_below_slow":
                        if prev_fast >= prev_slow and status.ma_fast < status.ma_slow:
                            alerts.append(Alert(
                                timestamp=datetime.now(),
                                symbol=symbol,
                                strategy_key=strategy_key,
                                strategy_name=strategy["name"],
                                priority=strategy["priority"],
                                message=strategy["description"],
                                indicator_value=status.ma_fast
                            ))

                # MACD checks
                elif indicator == "MACD" and status.macd != 0:
                    prev_macd = prev.get("macd", 0)
                    prev_signal = prev.get("macd_signal", 0)

                    if condition == "macd_crosses_above_signal":
                        if prev_macd <= prev_signal and status.macd > status.macd_signal:
                            alerts.append(Alert(
                                timestamp=datetime.now(),
                                symbol=symbol,
                                strategy_key=strategy_key,
                                strategy_name=strategy["name"],
                                priority=strategy["priority"],
                                message=strategy["description"],
                                indicator_value=status.macd
                            ))
                    elif condition == "macd_crosses_below_signal":
                        if prev_macd >= prev_signal and status.macd < status.macd_signal:
                            alerts.append(Alert(
                                timestamp=datetime.now(),
                                symbol=symbol,
                                strategy_key=strategy_key,
                                strategy_name=strategy["name"],
                                priority=strategy["priority"],
                                message=strategy["description"],
                                indicator_value=status.macd
                            ))
                
                # Price checks
                elif indicator == "Price":
                    if condition == "drops_by_percent" and status.price_change_pct <= -threshold:
                        alerts.append(Alert(
                            timestamp=datetime.now(),
                            symbol=symbol,
                            strategy_key=strategy_key,
                            strategy_name=strategy["name"],
                            priority=strategy["priority"],
                            message=f"{strategy['description']} ({status.price_change_pct:+.1f}%)",
                            indicator_value=status.price_change_pct
                        ))
                    elif condition == "rises_by_percent" and status.price_change_pct >= threshold:
                        alerts.append(Alert(
                            timestamp=datetime.now(),
                            symbol=symbol,
                            strategy_key=strategy_key,
                            strategy_name=strategy["name"],
                            priority=strategy["priority"],
                            message=f"{strategy['description']} ({status.price_change_pct:+.1f}%)",
                            indicator_value=status.price_change_pct
                        ))

            except Exception as e:
                logger.error(f"Strategy check error for {symbol}/{strategy_key}: {e}")

        # Store current values as previous for next check
        self.prev_values[symbol] = {
            "rsi": status.rsi,
            "volume": status.volume,
            "ma_fast": status.ma_fast,
            "ma_slow": status.ma_slow,
            "macd": status.macd,
            "macd_signal": status.macd_signal,
            "price": status.price
        }

        return alerts

    def check_all_stocks(self) -> List[Alert]:
        """Check all watched stocks"""
        all_alerts = []

        for symbol in self.watched_stocks:
            if self.update_stock_data(symbol):
                status = self.watched_stocks[symbol]
                current_price = status.price

                # Check stop loss / take profit on open positions
                sell_result = self.check_open_positions(symbol, current_price)
                if sell_result and sell_result.get("status") == "executed":
                    logger.info(f"SELL EXECUTED: {symbol} — position closed via SL/TP")

                alerts = self.check_strategies(symbol)
                # Also check news-based strategies
                news_alerts = self._check_news_strategies(symbol)
                alerts.extend(news_alerts)
                all_alerts.extend(alerts)

                for alert in alerts:
                    self.alerts.append(alert)
                    self.alert_history.append(alert)
                    if self.on_alert:
                        self.on_alert(alert)

                    # Check sell signals for TP2 exit (opposing signal on remaining half)
                    from execution_rules import SELL_SIGNAL_STRATEGIES
                    if alert.strategy_key in SELL_SIGNAL_STRATEGIES:
                        tp2_result = self.check_open_positions(
                            symbol, current_price, alert=alert
                        )
                        if tp2_result and tp2_result.get("status") == "executed":
                            logger.info(f"TP2 EXIT: {symbol} via {alert.strategy_name}")

                    # Execute buy signals if strategy qualifies
                    if alert.strategy_key in BUY_SIGNAL_STRATEGIES:
                        balance = self._get_balance()
                        can_buy, reason = self.execution_rules.check_buy(
                            symbol, alert, balance, equity=balance
                        )
                        if can_buy:
                            result = self.execution_rules.execute_buy(
                                symbol, alert, balance, equity=balance
                            )
                            if result.get("status") == "executed":
                                logger.info(
                                    f"BUY EXECUTED: {symbol} — "
                                    f"{result.get('quantity')} shares"
                                )
                        else:
                            logger.info(f"BUY BLOCKED: {symbol} — {reason}")

        # Keep only recent alerts in memory
        self.alerts = [a for a in self.alerts[-50:] if
                      (datetime.now() - a.timestamp).total_seconds() < 3600]

        return all_alerts

    def check_open_positions(self, symbol: str, current_price: float, alert=None) -> Optional[Dict]:
        """Check open positions for stop loss / take profit triggers."""
        try:
            position = self.position_tracker.get_position(symbol)
        except Exception:
            position = None
        if not position:
            return None
        should_sell, reason = self.execution_rules.check_sell(symbol, position, current_price, alert=alert)
        if should_sell:
            result = self.execution_rules.execute_sell(symbol, position, current_price, alert=alert)
            logger.info(f"SELL TRIGGERED: {symbol} — {reason}")
            return result
        return None

    def _get_balance(self) -> float:
        """Get current account balance (total equity)."""
        try:
            account = self.position_tracker.client.get_account_summary()
            return float(account.get("totalValue", account.get("equity", 0)))
        except Exception as e:
            logger.warning(f"Could not fetch balance: {e}")
            return 0.0

    def run(self):
        """Main monitoring loop"""
        logger.info(f"Stock monitor started (interval={self.poll_interval}s)")
        self.running = True

        while self.running:
            try:
                # Check if LSE market is open
                if is_lse_market_open():
                    alerts = self.check_all_stocks()
                    if alerts:
                        logger.info(f"Triggered {len(alerts)} alerts")
                    time.sleep(self.poll_interval)
                else:
                    # Market closed - sleep 5 minutes and check again
                    logger.info("LSE market closed. Pausing until next trading window.")
                    # Wait 5 minutes but allow interruption if self.running changes
                    for _ in range(30):
                        if not self.running: break
                        time.sleep(10)
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                time.sleep(self.poll_interval)

    def start(self):
        """Start monitoring in background thread"""
        if self.running:
            return

        self.monitor_thread = threading.Thread(target=self.run, daemon=True)
        self.monitor_thread.start()
        logger.info("Monitor thread started")

    def stop(self):
        """Stop monitoring"""
        self.running = False
        logger.info("Monitor stop requested")

    def get_status(self) -> Dict:
        """Get current monitor status"""
        stocks_data = {}
        for symbol, status in self.watched_stocks.items():
            stocks_data[symbol] = {
                "price": status.price,
                "price_change_pct": status.price_change_pct,
                "rsi": status.rsi,
                "volume": status.volume,
                "volume_avg": status.volume_avg,
                "ma_fast": status.ma_fast,
                "ma_slow": status.ma_slow,
                "macd": status.macd,
                "macd_signal": status.macd_signal,
                "last_updated": status.last_updated.isoformat() if status.last_updated else None
            }

        return {
            "running": self.running,
            "poll_interval": self.poll_interval,
            "is_market_open": is_lse_market_open(),
            "stocks": stocks_data,
            "recent_alerts": [
                {
                    "timestamp": a.timestamp.isoformat(),
                    "symbol": a.symbol,
                    "strategy": a.strategy_name,
                    "priority": a.priority,
                    "message": a.message
                }
                for a in self.alerts[-10:]
            ],
            "alert_count": len(self.alert_history),
            "news_sentiment_enabled": HAS_NEWS_SENTIMENT and self.sentiment_analyzer is not None,
            "cached_sentiments": list(self.sentiment_cache.keys())
        }

    def _fetch_news_for_symbol(self, symbol: str) -> Optional[List[Dict]]:
        """Fetch and cache news for a symbol"""
        # Check cache age (refresh every 15 min)
        cache_key = symbol
        if cache_key in self.news_cache:
            cached_time = self.news_cache.get(f"{cache_key}_time")
            if cached_time and (datetime.now() - cached_time).seconds < 900:
                return self.news_cache.get(cache_key, [])

        try:
            news = self.data_provider.get_ticker_news(symbol, limit=20)
            if news:
                self.news_cache[cache_key] = news
                self.news_cache[f"{cache_key}_time"] = datetime.now()
                
                # Create a simple hash/string of news titles to detect actual changes
                titles = "|".join([n.get("title", "") for n in news[:5]])
                self.news_hashes[symbol] = titles
            return news
        except Exception as e:
            logger.error(f"Failed to fetch news for {symbol}: {e}")
            return None

    def _check_news_strategies(self, symbol: str) -> List[Alert]:
        """Check news-based strategies for a symbol"""
        alerts = []

        if not self.sentiment_analyzer or not HAS_NEWS_SENTIMENT:
            return alerts

        try:
            # Get cached or fresh news
            news_items = self._fetch_news_for_symbol(symbol)
            if not news_items:
                return alerts

            # Only analyze if news content has changed or we have no sentiment yet
            news_hash = self.news_hashes.get(symbol, "")
            last_hash = getattr(self, f"_last_hash_{symbol}", None)
            
            if news_hash != last_hash or symbol not in self.sentiment_cache:
                logger.info(f"News changed for {symbol}, re-analyzing sentiment")
                sentiment = self.sentiment_analyzer.analyze_news(news_items, target_symbol=symbol)
                self.sentiment_cache[symbol] = sentiment
                setattr(self, f"_last_hash_{symbol}", news_hash)
            else:
                sentiment = self.sentiment_cache[symbol]

            logger.info(
                f"{symbol} news sentiment: {sentiment.sentiment} "
                f"(confidence: {sentiment.confidence:.0%})"
                + (f" ⚡ Stock mentioned in news — boosted confidence" if sentiment.stock_mentioned else "")
            )

            # Check against news strategies
            for strategy_key, strategy in STRATEGIES.items():
                if strategy["indicator"] != "NewsSentiment":
                    continue

                condition = strategy["condition"]
                threshold = strategy.get("threshold", 0.65)

                # Boost: lower thresholds when stock explicitly mentioned in news
                if sentiment.stock_mentioned:
                    if condition in ("sentiment_positive", "sentiment_negative"):
                        threshold = 0.50
                    elif condition in ("sentiment_positive_high", "sentiment_negative_high"):
                        threshold = 0.65

                effective_confidence = sentiment.confidence

                if condition == "sentiment_positive" and sentiment.sentiment == "POSITIVE":
                    if effective_confidence >= threshold:
                        alerts.append(Alert(
                            timestamp=datetime.now(),
                            symbol=symbol,
                            strategy_key=strategy_key,
                            strategy_name=strategy["name"],
                            priority=strategy["priority"],
                            message=f"{strategy['description']} ({effective_confidence:.0%})",
                            indicator_value=effective_confidence,
                            stock_mentioned=sentiment.stock_mentioned
                        ))

                elif condition == "sentiment_negative" and sentiment.sentiment == "NEGATIVE":
                    if effective_confidence >= threshold:
                        alerts.append(Alert(
                            timestamp=datetime.now(),
                            symbol=symbol,
                            strategy_key=strategy_key,
                            strategy_name=strategy["name"],
                            priority=strategy["priority"],
                            message=f"{strategy['description']} ({effective_confidence:.0%})",
                            indicator_value=effective_confidence,
                            stock_mentioned=sentiment.stock_mentioned
                        ))

                elif condition == "sentiment_positive_high" and sentiment.sentiment == "POSITIVE":
                    if effective_confidence >= threshold:
                        alerts.append(Alert(
                            timestamp=datetime.now(),
                            symbol=symbol,
                            strategy_key=strategy_key,
                            strategy_name=strategy["name"],
                            priority=strategy["priority"],
                            message=f"{strategy['description']} ({effective_confidence:.0%})",
                            indicator_value=effective_confidence,
                            stock_mentioned=sentiment.stock_mentioned
                        ))

                elif condition == "sentiment_negative_high" and sentiment.sentiment == "NEGATIVE":
                    if effective_confidence >= threshold:
                        alerts.append(Alert(
                            timestamp=datetime.now(),
                            symbol=symbol,
                            strategy_key=strategy_key,
                            strategy_name=strategy["name"],
                            priority=strategy["priority"],
                            message=f"{strategy['description']} ({effective_confidence:.0%})",
                            indicator_value=effective_confidence,
                            stock_mentioned=sentiment.stock_mentioned
                        ))

        except Exception as e:
            logger.error(f"News strategy check failed for {symbol}: {e}")

        return alerts

# Global monitor instance
_monitor: Optional[StockMonitor] = None

def get_monitor() -> StockMonitor:
    """Get or create global monitor instance"""
    global _monitor
    if _monitor is None:
        _monitor = StockMonitor(poll_interval=60)
    return _monitor
