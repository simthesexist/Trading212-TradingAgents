import os
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram_alert(message: str) -> bool:
    """Send alert to Telegram bot. Graceful no-op if token not configured."""
    if not TELEGRAM_BOT_TOKEN:
        logger.info(f"[TELEGRAM MOCK] {message}")
        return False

    if not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_CHAT_ID not set — skipping alert")
        return False

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        response = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message},
            timeout=5
        )
        if response.status_code == 200:
            logger.info(f"Telegram alert sent: {message[:50]}")
            return True
        else:
            logger.warning(f"Telegram returned {response.status_code}: {response.text[:100]}")
            return False
    except Exception as e:
        logger.error(f"Telegram alert failed: {e}")
        return False