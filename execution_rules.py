"""
Execution rules engine.
Validates trades against risk management rules before execution.
"""

import logging
from typing import Tuple, Optional, Dict, Any, List, TYPE_CHECKING
from position_tracker import PositionTracker, Position
from t212_client import T212Client

if TYPE_CHECKING:
    from monitor import Alert

logger = logging.getLogger(__name__)

STOP_LOSS_PCT = 5.0
TAKE_PROFIT_PCT = 10.0
MAX_POSITION_PCT = 10
MIN_BALANCE = 100
MAX_DAILY_TRADES = 10

SELL_SIGNAL_STRATEGIES = frozenset({
    "MA_CROSS_BELOW", "MACD_CROSS_BELOW", "RSI_OVERBOUGHT",
    "RSI_EXTREME_OVERBOUGHT", "NEWS_BEARISH", "NEWS_VERY_BEARISH",
    "PRICE_RISE_5PCT", "EARNINGS_MISS", "DOWNGRADE",
})


class ExecutionRules:
    def __init__(self, position_tracker: PositionTracker, t212_client: Optional[T212Client] = None):
        self.pt = position_tracker
        self.t212 = t212_client or T212Client()
        self._daily_trade_count: int = 0
        self._daily_trade_date: Optional[str] = None
        self._tp1_triggered: Dict[str, bool] = {}

    def _get_open_positions(self) -> List[Position]:
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

    def _unmark_tp1(self, symbol: str):
        self._tp1_triggered.pop(symbol.upper(), None)

    def _is_sell_signal(self, alert) -> bool:
        return alert is not None and alert.strategy_key in SELL_SIGNAL_STRATEGIES

    def _reset_daily_count(self):
        from datetime import date
        today = str(date.today())
        if self._daily_trade_date != today:
            self._daily_trade_count = 0
            self._daily_trade_date = today

    def check_buy(self, symbol: str, alert: "Alert", balance: float) -> Tuple[bool, str]:
        """
        Validate whether a buy order should be executed.

        Rules:
        - No repeat buys — reject if symbol already in open positions
        - Position size <= MAX_POSITION_PCT% of balance
        - Balance >= MIN_BALANCE
        - Market must be open
        - Daily trade limit not exceeded
        """
        self._reset_daily_count()

        if self._has_position(symbol):
            return False, f"Already holding {symbol} — no repeat buys"

        if balance < MIN_BALANCE:
            return False, f"Balance £{balance:.2f} below minimum £{MIN_BALANCE}"

        from monitor import is_lse_market_open
        if not is_lse_market_open():
            return False, "LSE market is closed"

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
        price = getattr(alert, 'indicator_value', None) or position.avg_price if hasattr(position, 'avg_price') else 0
        if price <= 0:
            return False, f"Cannot determine price for {symbol}"

        required_value = price * 1  # rough estimate — use indicator value when available
        if required_value > max_position_value:
            return False, f"Position too large{reason_suffix} — £{required_value:.2f} > £{max_position_value:.2f}"

        return True, f"All buy checks passed{reason_suffix}"

    def check_sell(self, symbol: str, position: Position, current_price: float, alert=None) -> Tuple[bool, str]:
        """
        Check whether an open position should be closed.

        TP1: At +10% → sell half the position.
        After TP1: trailing breakeven stop + opposing sell signal detection.
        Before TP1: standard stop loss.
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

        # After TP1: trailing breakeven stop or opposing signal
        if tp1_done:
            if current_price <= position.avg_price:
                return True, (
                    f"TP2 EXIT: Trailing stop hit for {symbol} at £{current_price:.2f} "
                    f"— remaining half exited at breakeven"
                )
            if self._is_sell_signal(alert):
                return True, (
                    f"TP2 EXIT: Opposing sell signal for {symbol} "
                    f"({alert.strategy_name})"
                )

        # Before TP1: standard stop loss
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

    def execute_buy(self, symbol: str, alert, balance: float, quantity: Optional[int] = None) -> Dict[str, Any]:
        """Check rules and execute buy if all pass."""
        can_buy, reason = self.check_buy(symbol, alert, balance)
        if not can_buy:
            logger.info(f"Buy blocked for {symbol}: {reason}")
            return {"status": "blocked", "reason": reason}

        price = 0.0
        try:
            account = self.t212.get_account_summary()
            price = account.get("equity", 0) / 100
        except Exception:
            pass

        stock_boost = getattr(alert, 'stock_mentioned', False)
        max_pct = 15 if stock_boost else MAX_POSITION_PCT

        if quantity is None:
            quantity = self.get_quantity(balance, price or 1, max_pct=max_pct)

        if quantity <= 0:
            return {"status": "blocked", "reason": f"Quantity {quantity} too low for {symbol}"}

        pct_note = f" (15% boost)" if stock_boost else ""
        try:
            result = self.t212.place_order(
                instrument_code=symbol,
                quantity=quantity,
                order_type="market",
                side="buy",
            )
            self._daily_trade_count += 1
            logger.info(f"BUY executed: {quantity} x {symbol}{pct_note}")
            return {"status": "executed", "quantity": quantity, "result": result}
        except Exception as e:
            logger.error(f"Buy execution failed for {symbol}: {e}")
            return {"status": "failed", "reason": str(e)}

    def execute_sell(self, symbol: str, position: Position, current_price: float, quantity: Optional[int] = None, alert=None) -> Dict[str, Any]:
        """Check rules and execute sell if triggered.

        Handles TP1 partial sells (half the position).
        """
        should_sell, reason = self.check_sell(symbol, position, current_price, alert=alert)
        if not should_sell:
            return {"status": "holding", "reason": reason}

        symbol_key = symbol.upper()

        # TP1: sell exactly half
        if reason.startswith("TP1"):
            half = max(1, int(position.quantity // 2))
            qty = quantity or half
            if qty < position.quantity:
                self._mark_tp1(symbol_key)
            logger.info(f"TP1 HIT: Sold {qty}/{int(position.quantity)} of {symbol} at £{current_price:.2f}")
        else:
            qty = quantity or int(position.quantity)
            self._unmark_tp1(symbol_key)

        if qty <= 0:
            return {"status": "blocked", "reason": f"Quantity {qty} too low for {symbol}"}

        try:
            result = self.t212.place_order(
                instrument_code=symbol,
                quantity=qty,
                order_type="market",
                side="sell",
            )
            self._daily_trade_count += 1
            logger.info(f"SELL executed: {qty} x {symbol}")
            return {"status": "executed", "quantity": qty, "result": result}
        except Exception as e:
            logger.error(f"Sell execution failed for {symbol}: {e}")
            return {"status": "failed", "reason": str(e)}
