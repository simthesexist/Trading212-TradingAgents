#!/usr/bin/env python3
"""
T212 Log Health Check — Cron Job (every 5 mins)
Only reports ERROR-level events via Telegram. Silent when everything is OK.
"""
import os
import sys
import json
import subprocess
from datetime import date

LOG_DIR = "/home/server/Workspace/T212/logs"
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def send_telegram(text: str):
    """Send message via Telegram bot."""
    if not BOT_TOKEN or not CHAT_ID:
        return
    payload = {"chat_id": CHAT_ID, "text": text}
    data = json.dumps(payload).encode()
    cmd = [
        "curl", "-s", "-X", "POST",
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        "-H", "Content-Type: application/json",
        "-d", "@-"
    ]
    subprocess.run(cmd, input=data, check=False)


def main():
    today = date.today().isoformat()
    errors_found = []

    for fname in os.listdir(LOG_DIR):
        if not fname.endswith(".log"):
            continue
        fpath = os.path.join(LOG_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            with open(fpath) as f:
                lines = f.readlines()
        except Exception:
            continue

        today_errors = [
            line.strip() for line in lines
            if today in line and "ERROR" in line.upper()
        ]
        if today_errors:
            errors_found.append((fname, len(today_errors), today_errors[0]))

    if errors_found:
        total = sum(e[1] for e in errors_found)
        send_telegram(f"T212 Log Alert — {today}")
        for fname, cnt, sample in errors_found:
            send_telegram(f"{fname}: {cnt} error(s)\n{sample}")
        send_telegram(f"Total: {total} error(s) today")
    else:
        # Optional: periodic heartbeat (disabled by default)
        # send_telegram(f"T212 OK — {today}")
        pass


if __name__ == "__main__":
    main()