#!/bin/bash
# ================================================================
# T212 Log Health Check — Cron Job (every 5 mins)
# Only reports ERROR-level events. Silent when everything is OK.
# Fix button clears the log files.
# ================================================================

LOG_DIR="/home/server/Workspace/T212/logs"
BOT_TOKEN="${TELEGRAM_BOT_TOKEN}"
CHAT_ID="${TELEGRAM_CHAT_ID}"

# Run entirely in Python to avoid bash quoting/escaping nightmares
python3 - "$BOT_TOKEN" "$CHAT_ID" "$LOG_DIR" <<'PYEOF'
import sys, os, json, subprocess
from datetime import date

bot_token = sys.argv[1]
chat_id = sys.argv[2]
log_dir = sys.argv[3]
today = date.today().isoformat()

def send(text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    data = json.dumps(payload).encode()
    cmd = [
        "curl", "-s", "-X", "POST",
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        "-H", "Content-Type: application/json",
        "-d", "@-"
    ]
    subprocess.run(cmd, input=data, check=False)

errors_found = []

for fname in os.listdir(log_dir):
    if not fname.endswith(".log"):
        continue
    fpath = os.path.join(log_dir, fname)
    if not os.path.isfile(fpath):
        continue
    try:
        with open(fpath) as f:
            lines = f.readlines()
    except:
        continue

    today_errors = [l.strip() for l in lines if today in l and "ERROR" in l.upper()]
    if today_errors:
        errors_found.append((fname, len(today_errors), today_errors[0]))

if errors_found:
    total = sum(e[1] for e in errors_found)
    fix_btn = {"inline_keyboard": [[
        {"text": "\u2699\ufe0f Fix", "callback_data": "fix_logs"}
    ]]}
    send(f"T212 Log Alert — {today}", reply_markup=fix_btn)
    for fname, cnt, sample in errors_found:
        send(f"{fname}: {cnt} error(s)\n{sample}")
    send(f"Total: {total} error(s) today")

PYEOF