"""
Logging configuration for the trading system.
Writes to /logs directory with separate files for different concerns.
"""

import logging
import os
from logging.handlers import TimedRotatingFileHandler, RotatingFileHandler
from datetime import datetime

# Ensure logs directory exists
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_setup_done = False

def setup_logging():
    """Configure all application loggers. Idempotent — safe to call multiple times."""
    global _setup_done
    if _setup_done:
        return

    # Base format for all loggers
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # ── errors.log ─ all errors (redacted for secrets) ──────────────────────
    errors_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "errors.log"),
        maxBytes=5_000_000, backupCount=5
    )
    errors_handler.setLevel(logging.ERROR)
    errors_handler.setFormatter(formatter)

    errors_logger = logging.getLogger("errors")
    errors_logger.setLevel(logging.ERROR)
    errors_logger.addHandler(errors_handler)

    # ── trades.log ─ executed trade records ─────────────────────────────────
    trades_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "trades.log"),
        maxBytes=10_000_000, backupCount=10
    )
    trades_handler.setLevel(logging.INFO)
    trades_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    trades_logger = logging.getLogger("trades")
    trades_logger.setLevel(logging.INFO)
    trades_logger.addHandler(trades_handler)

    # ── agents.log ─ TradingAgents full reasoning output ───────────────────
    agents_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "agents.log"),
        maxBytes=20_000_000, backupCount=5
    )
    agents_handler.setLevel(logging.INFO)
    agents_handler.setFormatter(formatter)
    agents_logger = logging.getLogger("agents")
    agents_logger.setLevel(logging.INFO)
    agents_logger.addHandler(agents_handler)

    # ── monitor.log ─ Monitor loop, market status, alerts ─────────────────
    monitor_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "monitor.log"),
        maxBytes=10_000_000, backupCount=5
    )
    monitor_handler.setLevel(logging.INFO)
    monitor_handler.setFormatter(formatter)
    monitor_logger = logging.getLogger("monitor")
    monitor_logger.setLevel(logging.INFO)
    monitor_logger.addHandler(monitor_handler)

    # ── trading.log ─ General trading activity ─────────────────────────────
    trading_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "trading.log"),
        maxBytes=10_000_000, backupCount=5
    )
    trading_handler.setLevel(logging.INFO)
    trading_handler.setFormatter(formatter)
    trading_logger = logging.getLogger("trading")
    trading_logger.setLevel(logging.INFO)
    trading_logger.addHandler(trading_handler)

    # ── Root logger setup ──────────────────────────────────────────────────
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Console handler (INFO+)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    root_logger.addHandler(console)

    # Errors handler (ERROR+) — separate file for errors with sensitive data redacted
    root_logger.addHandler(errors_handler)

    # Redirect werkzeug (flask dev server) to avoid noise
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    _setup_done = True

    return {
        "errors": errors_logger,
        "trades": trades_logger,
        "agents": agents_logger,
        "monitor": monitor_logger,
        "trading": trading_logger,
    }