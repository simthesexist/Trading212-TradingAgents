"""
Bank set-aside management.
Money set aside (banked) is excluded from trading balance calculations.
"""

import json
import os
import logging

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
BANK_FILE = os.path.join(DATA_DIR, "bank_set_aside.json")

os.makedirs(DATA_DIR, exist_ok=True)


def get_bank_set_aside() -> float:
    """Get the current bank set-aside amount."""
    try:
        if os.path.exists(BANK_FILE):
            with open(BANK_FILE, "r") as f:
                data = json.load(f)
                return float(data.get("amount", 0.0))
    except Exception as e:
        logger.warning(f"Could not read bank set-aside: {e}")
    return 0.0


def set_bank_set_aside(amount: float):
    """Set the bank set-aside amount (clamped to 0 minimum)."""
    clamped = max(0.0, float(amount))
    try:
        with open(BANK_FILE, "w") as f:
            json.dump({"amount": clamped}, f)
        _write_env_var("TRADING_BANK", clamped)
        logger.info(f"Bank set-aside set to {clamped}")
    except Exception as e:
        logger.error(f"Could not write bank set-aside: {e}")


def _write_env_var(key, value):
    """Persist key=value to .env file."""
    try:
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        with open(env_path, 'r') as f:
            lines = f.readlines()
        with open(env_path, 'w') as f:
            found = False
            for line in lines:
                if line.startswith(f'{key}='):
                    f.write(f'{key}={value}\n')
                    found = True
                else:
                    f.write(line)
            if not found:
                f.write(f'{key}={value}\n')
    except Exception as e:
        logger.warning(f"Could not persist {key}={value} to .env: {e}")