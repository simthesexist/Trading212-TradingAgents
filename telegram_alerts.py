import os
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)


def send_telegram_alert(message: str) -> bool:
    """Send alert to Telegram bot. Graceful no-op if token not configured."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set — skipping alert")
        return False

    if not chat_id:
        logger.warning("TELEGRAM_CHAT_ID not set — skipping alert")
        return False

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        response = requests.post(
            url,
            json={"chat_id": chat_id, "text": message},
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