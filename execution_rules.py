"""
Execution rules engine.
Validates trades against risk management rules before execution.
"""

import logging
import time
from datetime import date
from typing import Tuple, Optional, Dict, Any, List, TYPE_CHECKING
from position_tracker import PositionTracker, Position
from t212_client import T212Client
from telegram_alerts import send_telegram_alert

if TYPE_CHECKING:
    from monitor import Alert

logger = logging.getLogger(__name__)

# Risk management constants
STOP_LOSS_PCT = 5.0
TAKE_PROFIT_PCT = 10.0
MAX_POSITION_PCT = 10
MIN_BALANCE = 100
MAX_DAILY_TRADES = 10
TRADE_FEE = 1.0  # £1 per trade transaction cost
DAILY_LOSS_CAP_PCT = 3.0  # block buys if daily P&L < -3%
TRAILING_STOP_PCT = 3.0  # 3% trailing stop after TP1
BUY_COOLDOWN_SECS = 60  # seconds between buys of same symbol

SELL_SIGNAL_STRATEGIES = frozenset({
    "MA_CROSS_BELOW", "MACD_CROSS_BELOW", "RSI_OVERBOUGHT",
    "RSI_EXTREME_OVERBOUGHT", "NEWS_BEARISH", "NEWS_VERY_BEARISH",
    "PRICE_RISE_5PCT", "EARNINGS_MISS", "DOWNGRADE",
})


class ExecutionRules:
    _max_open_trades: int = 10  # class-level limit

    def __init__(self, position_tracker: PositionTracker, t212_client: Optional[T212Client] = None):
        self.pt = position_tracker
        self.t212 = t212_client or T212Client()
        self._daily_trade_count: int = 0
        self._daily_trade_date: Optional[str] = None
        self._tp1_triggered: Dict[str, bool] = {}
        self._tp1_highs: Dict[str, float] = {}  # highest price since TP1 triggered
        self._last_buy_time: Dict[str, float] = {}  # symbol -> timestamp of last buy
        self._day_start_equity: Optional[float] = None  # equity at start of trading day
        self._cached_positions: Optional[List[Position]] = None  # cache to reduce API calls

    @classmethod
    def set_max_open_trades(cls, limit: int):
        cls._max_open_trades = max(1, limit)

    def set_cached_positions(self, positions: List[Position]):
        self._cached_positions = positions

    def clear_position_cache(self):
        self._cached_positions = None

    def _get_open_positions(self) -> List[Position]:
        if self._cached_positions is not None:
            return self._cached_positions
        try:
            return self.pt.fetch_positions()
        except Exception as e:
            logger.warning(f"Could not fetch positions: {e}")
            return []

    def _has_position(self, symbol: str) -> bool:
        for p in self._get_open_positions():
            if p.symbol.upper() == symbol.upper():
                return True
        return False

    def _get_position(self, symbol: str) -> Optional[Position]:
        for p in self._get_open_positions():
            if p.symbol.upper() == symbol.upper():
                return p
        return None

    def _is_tp1_triggered(self, symbol: str) -> bool:
        return self._tp1_triggered.get(symbol.upper(), False)

    def _mark_tp1(self, symbol: str):
        self._tp1_triggered[symbol.upper()] = True

    def _clear_tp1(self, symbol: str):
        key = symbol.upper()
        self._tp1_triggered.pop(key, None)
        self._tp1_highs.pop(key, None)

    def _update_tp1_high(self, symbol: str, current_price: float):
        """Track highest price since TP1 was triggered for trailing stop."""
        key = symbol.upper()
        if key not in self._tp1_highs:
            self._tp1_highs[key] = current_price
        else:
            self._tp1_highs[key] = max(self._tp1_highs[key], current_price)

    def _is_sell_signal(self, alert) -> bool:
        return alert is not None and alert.strategy_key in SELL_SIGNAL_STRATEGIES

    def _reset_daily_count(self, equity: float = None):
        today = str(date.today())
        if self._daily_trade_date != today:
            self._daily_trade_count = 0
            self._daily_trade_date = today
            self._day_start_equity = equity

    def check_buy(self, symbol: str, alert: "Alert", balance: float, equity: float = None, current_price: float = None) -> Tuple[bool, str]:
        """
        Validate whether a buy order should be executed.

        Rules:
        - No repeat buys — reject if symbol already in open positions
        - Position size <= MAX_POSITION_PCT% of balance (15% if stock mentioned in news)
        - Balance >= MIN_BALANCE
        - Market must be open
        - Daily trade limit not exceeded
        - Daily loss cap not triggered (< -3% intraday)
        - Buy cooldown not active (60s between buys of same symbol)
        """
        self._reset_daily_count(equity)
        symbol_key = symbol.upper()

        # Daily loss cap: block all buys if intraday P&L < -3%
        if self._day_start_equity and equity:
            daily_pnl_pct = ((equity - self._day_start_equity) / self._day_start_equity) * 100
            if daily_pnl_pct < -DAILY_LOSS_CAP_PCT:
                msg = f"Daily loss cap reached ({daily_pnl_pct:+.1f}%)"
                logger.warning(msg)
                send_telegram_alert(f"🛡 BUY BLOCKED: {symbol} — {msg}")
                return False, msg

        # Buy cooldown check
        if symbol_key in self._last_buy_time:
            elapsed = time.time() - self._last_buy_time[symbol_key]
            if elapsed < BUY_COOLDOWN_SECS:
                remaining = int(BUY_COOLDOWN_SECS - elapsed)
                msg = f"Buy cooldown active for {symbol} ({remaining}s remaining)"
                logger.info(msg)
                return False, msg

        if self._has_position(symbol):
            return False, f"Already holding {symbol} — no repeat buys"

        if balance < MIN_BALANCE:
            return False, f"Balance £{balance:.2f} below minimum £{MIN_BALANCE}"

        from monitor import is_lse_market_open
        if not is_lse_market_open():
            return False, "LSE market is closed"

        open_count = len(self._get_open_positions())
        if open_count >= self._max_open_trades:
            return False, f"Max open trades ({self._max_open_trades}) reached"

        if self._daily_trade_count >= MAX_DAILY_TRADES:
            return False, f"Daily trade limit ({MAX_DAILY_TRADES}) reached"

        # Position size check — boost cap if stock mentioned in news
        if hasattr(alert, 'stock_mentioned') and alert.stock_mentioned:
            effective_max_pct = min(15.0, MAX_POSITION_PCT * 1.5)
            reason_suffix = f" (stock mentioned — up to {effective_max_pct:.0f}% of balance)"
        else:
            effective_max_pct = float(MAX_POSITION_PCT)
            reason_suffix = ""

        max_position_value = balance * effective_max_pct / 100
        price = current_price or getattr(alert, 'indicator_value', None) or 0
        if price <= 0:
            return False, f"Cannot determine price for {symbol}"

        if price > max_position_value:
            return False, f"Position too large{reason_suffix} — £{price:.2f} > £{max_position_value:.2f}"

        return True, f"All buy checks passed{reason_suffix}"

    def check_sell(self, symbol: str, position: Position, current_price: float, alert=None) -> Tuple[bool, str]:
        """
        Check whether an open position should be closed.

        TP1: At +10% → sell half the position.
        After TP1: trailing stop (3% from post-TP1 high) + opposing sell signal detection.
        Before TP1: standard stop loss (-5%).
        """
        if position.avg_price <= 0:
            return False, f"Cannot evaluate {symbol}: avg_price is zero"

        symbol_key = symbol.upper()
        tp1_done = self._is_tp1_triggered(symbol_key)

        # TP1: +10% → sell half
        if not tp1_done:
            tp1_price = position.avg_price * (1 + TAKE_PROFIT_PCT / 100)
            if current_price >= tp1_price:
                gain_pct = ((current_price - position.avg_price) / position.avg_price) * 100
                return True, (
                    f"TP1 HIT: Sell half of {symbol} at £{current_price:.2f} "
                    f"({gain_pct:+.1f}%)"
                )

        # After TP1: 3% trailing stop from post-TP1 high OR opposing signal
        if tp1_done:
            self._update_tp1_high(symbol, current_price)
            trailing_sl = self._tp1_highs[symbol_key] * (1 - TRAILING_STOP_PCT / 100)
            if current_price <= trailing_sl:
                return True, (
                    f"TP2 EXIT: Trailing stop hit for {symbol} "
                    f"(price £{current_price:.2f} <= trailing SL £{trailing_sl:.2f})"
                )
            if self._is_sell_signal(alert):
                return True, (
                    f"TP2 EXIT: Opposing sell signal for {symbol} "
                    f"({getattr(alert, 'strategy_name', 'unknown')})"
                )

        # Before TP1: standard stop loss (-5%)
        if not tp1_done:
            stop_loss_price = position.avg_price * (1 - STOP_LOSS_PCT / 100)
            if current_price <= stop_loss_price:
                loss_pct = ((current_price - position.avg_price) / position.avg_price) * 100
                return True, (
                    f"Stop loss triggered for {symbol}: "
                    f"current=£{current_price:.2f}, "
                    f"stop=£{stop_loss_price:.2f} "
                    f"({loss_pct:+.1f}%)"
                )

        return False, f"No exit signal for {symbol}"

    def get_quantity(self, balance: float, price: float, max_pct: float = MAX_POSITION_PCT) -> int:
        """Calculate max shares to buy = (balance * max_pct/100) / price"""
        if price <= 0 or balance <= 0:
            return 0
        return int((balance * max_pct / 100) / price)

    def execute_buy(self, symbol: str, alert, balance: float, equity: float = None, quantity: Optional[int] = None, current_price: float = None) -> Dict[str, Any]:
        """Check rules and execute buy if all pass."""
        can_buy, reason = self.check_buy(symbol, alert, balance, equity, current_price=current_price)
        if not can_buy:
            logger.info(f"Buy blocked for {symbol}: {reason}")
            send_telegram_alert(f"🛡 BUY BLOCKED: {symbol} — {reason}")
            return {"status": "blocked", "reason": reason}

        price = current_price or getattr(alert, 'indicator_value', None) or 0.0
        if price <= 0:
            try:
                price = self.pt._get_current_price(symbol)  # fallback to ticker price
            except Exception:
                price = 0.0

        stock_boost = getattr(alert, 'stock_mentioned', False)
        max_pct = 15.0 if stock_boost else float(MAX_POSITION_PCT)

        if quantity is None:
            quantity = self.get_quantity(balance, price or 1, max_pct=max_pct)

        if quantity <= 0:
            return {"status": "blocked", "reason": f"Quantity {quantity} too low for {symbol}"}

        pct_note = " (15% boost)" if stock_boost else ""
        fee_note = f" (net after £{TRADE_FEE} fee)"
        try:
            result = self.t212.place_order(
                instrument_code=symbol,
                quantity=quantity,
                order_type="market",
                side="buy",
            )
            self._daily_trade_count += 1
            self._last_buy_time[symbol.upper()] = time.time()
            logger.info(f"BUY executed: {quantity} x {symbol}{pct_note}{fee_note}")
            send_telegram_alert(f"🚀 BUY EXECUTED: {symbol} — {quantity} shares @ £{price:.2f}{fee_note}")
            return {"status": "executed", "quantity": quantity, "price": price, "result": result}
        except Exception as e:
            logger.error(f"Buy execution failed for {symbol}: {e}")
            send_telegram_alert(f"❌ BUY FAILED: {symbol} — {e}")
            return {"status": "failed", "reason": str(e)}

    def execute_sell(self, symbol: str, position: Position, current_price: float, quantity: Optional[int] = None, alert=None) -> Dict[str, Any]:
        """
        Check rules and execute sell if triggered.

        Handles TP1 partial sells (half the position) and full sells.
        Deducts TRADE_FEE from net P&L.
        """
        should_sell, reason = self.check_sell(symbol, position, current_price, alert=alert)
        if not should_sell:
            return {"status": "holding", "reason": reason}

        symbol_key = symbol.upper()
        tp1_this_round = False

        # TP1: sell exactly half
        if reason.startswith("TP1"):
            tp1_this_round = True
            half = max(1, int(position.quantity // 2))
            qty = quantity or half
            self._mark_tp1(symbol_key)
            self._tp1_highs[symbol_key] = current_price
            logger.info(f"TP1 HIT: Sold {qty}/{int(position.quantity)} of {symbol} at £{current_price:.2f}")
            send_telegram_alert(f"📊 TP1: Sold 1/2 of {symbol} at £{current_price:.2f} — trailing SL active")
        else:
            qty = quantity or int(position.quantity)
            self._clear_tp1(symbol_key)

        if qty <= 0:
            return {"status": "blocked", "reason": f"Quantity {qty} too low for {symbol}"}

        fee_note = f" (net after £{TRADE_FEE} fee)"
        try:
            result = self.t212.place_order(
                instrument_code=symbol,
                quantity=qty,
                order_type="market",
                side="sell",
            )
            self._daily_trade_count += 1
            logger.info(f"SELL executed: {qty} x {symbol} — {reason}{fee_note}")
            send_telegram_alert(f"🔴 SELL EXECUTED: {symbol} — {qty} shares @ £{current_price:.2f} ({reason}){fee_note}")
            return {"status": "executed", "quantity": qty, "price": current_price, "reason": reason, "result": result}
        except Exception as e:
            logger.error(f"Sell execution failed for {symbol}: {e}")
            send_telegram_alert(f"❌ SELL FAILED: {symbol} — {e}")
            return {"status": "failed", "reason": str(e)}