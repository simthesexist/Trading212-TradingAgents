"""
Position tracker module.
Tracks open positions, P&L history, and portfolio metrics.
"""

import logging
import json
import os
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

from t212_client import T212Client

logger = logging.getLogger(__name__)

TRADE_FEE = 1.0
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
HISTORY_FILE = os.path.join(DATA_DIR, "position_history.json")
SNAPSHOT_FILE = os.path.join(DATA_DIR, "position_snapshots.json")
REALIZED_PNL_FILE = os.path.join(DATA_DIR, "realized_pnl.json")

os.makedirs(DATA_DIR, exist_ok=True)


@dataclass
class Position:
    symbol: str
    quantity: float = 0.0
    avg_price: float = 0.0
    current_price: float = 0.0
    pnl: float = 0.0
    pnl_percent: float = 0.0
    exposure: float = 0.0
    instrument_type: str = "EQUITY"

    @classmethod
    def from_t212(cls, raw: Dict) -> "Position":
        # T212 portfolio returns: ticker, quantity, averagePrice, currentPrice, ppl, fxPpl, value, type
        quantity = float(raw.get("quantity", 0))
        avg_price = float(raw.get("averagePrice", 0))
        current_price = float(raw.get("currentPrice", 0))
        pnl = float(raw.get("ppl", 0))
        exposure = raw.get("value", 0) or (quantity * current_price)
        # Calculate pnl_percent if T212 doesn't provide it directly
        percentage_pnl = float(raw.get("percentagePnl", 0) or raw.get("percentagePpl", 0))
        if percentage_pnl == 0 and avg_price > 0 and quantity > 0:
            percentage_pnl = (pnl / (avg_price * quantity)) * 100
        return cls(
            symbol=raw.get("ticker", raw.get("symbol", "")),
            quantity=quantity,
            avg_price=avg_price,
            current_price=current_price,
            pnl=pnl,
            pnl_percent=percentage_pnl,
            exposure=float(exposure),
            instrument_type=raw.get("type", "EQUITY"),
        )

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class PositionSnapshot:
    timestamp: datetime
    positions: List[Position]
    total_pnl: float
    total_exposure: float
    position_count: int


@dataclass
class PortfolioSummary:
    total_pnl: float = 0.0
    total_fees: float = 0.0
    net_pnl: float = 0.0
    total_exposure: float = 0.0
    position_count: int = 0
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    monthly_pnl: float = 0.0
    yearly_pnl: float = 0.0
    all_time_pnl: float = 0.0
    yesterday_realized_pnl: float = 0.0
    today_count: int = 0
    positions: List[Position] = field(default_factory=list)


class PositionTracker:
    def __init__(self, t212_client: Optional[T212Client] = None):
        self.client = t212_client or T212Client()
        self._snapshots: List[PositionSnapshot] = []
        self._last_positions: List[Position] = []
        self._total_fees: float = 0.0
        self._realized_pnl_by_date: Dict[str, float] = {}
        self._load_history()
        self._load_realized_pnl()

    def _load_history(self):
        if os.path.exists(SNAPSHOT_FILE):
            try:
                with open(SNAPSHOT_FILE, "r") as f:
                    raw = json.load(f)
                for entry in raw[-500:]:
                    positions = [Position(**p) for p in entry.get("positions", [])]
                    self._snapshots.append(PositionSnapshot(
                        timestamp=datetime.fromisoformat(entry["timestamp"]),
                        positions=positions,
                        total_pnl=entry.get("total_pnl", 0),
                        total_exposure=entry.get("total_exposure", 0),
                        position_count=entry.get("position_count", 0),
                    ))
                logger.info(f"Loaded {len(self._snapshots)} position snapshots")
            except Exception as e:
                logger.warning(f"Could not load position history: {e}")

    def _save_snapshot(self, snapshot: PositionSnapshot):
        self._snapshots.append(snapshot)
        if len(self._snapshots) > 1000:
            self._snapshots = self._snapshots[-1000:]
        try:
            entries = [
                {
                    "timestamp": s.timestamp.isoformat(),
                    "total_pnl": s.total_pnl,
                    "total_exposure": s.total_exposure,
                    "position_count": s.position_count,
                    "positions": [asdict(p) for p in s.positions],
                }
                for s in self._snapshots[-200:]
            ]
            with open(SNAPSHOT_FILE, "w") as f:
                json.dump(entries, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save position snapshot: {e}")

    def _load_realized_pnl(self):
        if os.path.exists(REALIZED_PNL_FILE):
            try:
                with open(REALIZED_PNL_FILE, "r") as f:
                    self._realized_pnl_by_date = json.load(f)
                logger.info(f"Loaded realized P&L for {len(self._realized_pnl_by_date)} days")
            except Exception as e:
                logger.warning(f"Could not load realized P&L: {e}")

    def _save_realized_pnl(self):
        try:
            with open(REALIZED_PNL_FILE, "w") as f:
                json.dump(self._realized_pnl_by_date, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save realized P&L: {e}")

    def add_trade_fee(self, count: int = 1):
        self._total_fees += TRADE_FEE * count

    def fetch_positions(self) -> List[Position]:
        try:
            raw = self.client.get_positions()
            positions = [Position.from_t212(p) for p in raw]

            now = datetime.now()
            total_pnl = sum(p.pnl for p in positions)
            total_exposure = sum(p.exposure for p in positions)

            # Detect closed positions and track their P&L as realized
            if self._last_positions:
                old_by_symbol = {p.symbol: p for p in self._last_positions}
                new_by_symbol = {p.symbol: p for p in positions}
                today_key = now.strftime("%Y-%m-%d")
                for symbol, pos in old_by_symbol.items():
                    if symbol not in new_by_symbol:
                        realized = pos.pnl
                        self._realized_pnl_by_date[today_key] = self._realized_pnl_by_date.get(today_key, 0.0) + realized
                        logger.info(f"Realized P&L: {symbol} -> £{realized:.2f}")
                self._save_realized_pnl()

            snapshot = PositionSnapshot(
                timestamp=now,
                positions=positions,
                total_pnl=total_pnl,
                total_exposure=total_exposure,
                position_count=len(positions),
            )
            self._save_snapshot(snapshot)
            self._last_positions = positions

            return positions
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
            return self._last_positions

    def get_summary(self) -> PortfolioSummary:
        positions = self.fetch_positions()
        if not positions:
            return PortfolioSummary()

        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=today_start.weekday())
        month_start = today_start.replace(day=1)
        year_start = today_start.replace(month=1, day=1)

        current_total_pnl = sum(p.pnl for p in positions)
        total_exposure = sum(p.exposure for p in positions)

        pnl_by_period = self._calculate_pnl_by_period(today_start, week_start, month_start, year_start)

        net_total_pnl = current_total_pnl - self._total_fees
        net_all_time = pnl_by_period.get("all_time", current_total_pnl) - self._total_fees

        yesterday_key = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday_realized = self._realized_pnl_by_date.get(yesterday_key, 0.0)

        return PortfolioSummary(
            total_pnl=current_total_pnl,
            total_fees=self._total_fees,
            net_pnl=net_total_pnl,
            total_exposure=total_exposure,
            position_count=len(positions),
            daily_pnl=pnl_by_period.get("daily", current_total_pnl),
            weekly_pnl=pnl_by_period.get("weekly", current_total_pnl),
            monthly_pnl=pnl_by_period.get("monthly", current_total_pnl),
            yearly_pnl=pnl_by_period.get("yearly", current_total_pnl),
            all_time_pnl=net_all_time,
            yesterday_realized_pnl=yesterday_realized,
            today_count=self._count_today_trades(today_start),
            positions=positions,
        )

    def _calculate_pnl_by_period(self, today_start, week_start, month_start, year_start) -> Dict[str, float]:
        periods = {"daily": 0.0, "weekly": 0.0, "monthly": 0.0, "yearly": 0.0, "all_time": 0.0}

        if len(self._snapshots) < 2:
            if self._snapshots:
                periods["all_time"] = self._snapshots[-1].total_pnl
            return periods

        first_snapshot = self._snapshots[0]
        last_snapshot = self._snapshots[-1]

        periods["all_time"] = last_snapshot.total_pnl - first_snapshot.total_pnl

        for period_name, period_start in [
            ("daily", today_start),
            ("weekly", week_start),
            ("monthly", month_start),
            ("yearly", year_start),
        ]:
            snapshot_at_start = None
            for s in reversed(self._snapshots):
                if s.timestamp < period_start:
                    snapshot_at_start = s
                    break
            if snapshot_at_start:
                periods[period_name] = last_snapshot.total_pnl - snapshot_at_start.total_pnl
            elif self._snapshots and self._snapshots[0].timestamp >= period_start:
                periods[period_name] = last_snapshot.total_pnl
            else:
                periods[period_name] = 0.0

        return periods

    def _count_today_trades(self, today_start: datetime) -> int:
        today_trades = 0
        for s in reversed(self._snapshots):
            if s.timestamp >= today_start:
                today_trades = s.position_count
            else:
                break
        if self._snapshots:
            yest_snapshots = [s for s in self._snapshots if s.timestamp < today_start]
            if yest_snapshots:
                yest_count = yest_snapshots[-1].position_count
                current_count = self._snapshots[-1].position_count
                return max(0, current_count - yest_count)
        return 0

    def get_diversification(self) -> Dict[str, Any]:
        positions = self.fetch_positions()
        if not positions:
            return {"total_exposure": 0, "positions": [], "concentration": {}}

        total_exposure = sum(p.exposure for p in positions) or 1
        top_positions = sorted(positions, key=lambda p: p.exposure, reverse=True)
        concentration = {}
        for p in top_positions[:5]:
            concentration[p.symbol] = round((p.exposure / total_exposure) * 100, 1)

        return {
            "total_exposure": sum(p.exposure for p in positions),
            "positions": [p.to_dict() for p in sorted(positions, key=lambda p: p.exposure, reverse=True)],
            "concentration": concentration,
            "num_positions": len(positions),
        }

    def get_position(self, symbol: str) -> Optional[Position]:
        for p in self.fetch_positions():
            if p.symbol.upper() == symbol.upper():
                return p
        return None

    def detect_changes(self) -> Dict[str, Any]:
        positions = self.fetch_positions()
        current_symbols = {p.symbol for p in positions}
        prev_symbols = {p.symbol for p in self._last_positions} if self._last_positions else set()

        opened = current_symbols - prev_symbols
        closed = prev_symbols - current_symbols

        return {
            "opened": list(opened),
            "closed": list(closed),
            "open_count": len(current_symbols),
            "prev_count": len(prev_symbols),
            "current_positions": [p.to_dict() for p in positions],
        }


_tracker: Optional[PositionTracker] = None


def get_tracker() -> PositionTracker:
    global _tracker
    if _tracker is None:
        _tracker = PositionTracker()
    return _tracker
