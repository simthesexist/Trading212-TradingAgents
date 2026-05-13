# TradingView Webhook Setup Guide

## 1. Overview

TradingView webhooks allow you to trigger external actions (like executing trades) when an alert condition is met on your chart. Instead of relying on polling or manual monitoring, you configure an alert that sends an HTTP POST request to your server with the alert details as JSON.

## 2. Prerequisites

- **TradingView Account Tier**: To receive LSE (London Stock Exchange) data such as L:HSBA, you'll need at least the **Essential** plan (or higher). Free tier may have limited access to certain markets.
- **Web Server**: A server running your Flask/webhook bridge (e.g., `http://your-server:5000/webhook/tradingview`)
- **Flask App**: The webhook receiver must be running and accessible from the internet (or TradingView's servers)

## 3. Step-by-Step Alert Setup

### Step 1: Open Your Chart
1. Log in to TradingView (tradingview.com)
2. Open a chart for the instrument you want to trade (e.g., **L:HSBA** for HSBC Holdings on LSE)
3. The L: prefix indicates London Stock Exchange

### Step 2: Create an Alert
1. Click the **Alert** (bell) icon in the top toolbar, or right-click on the chart and select "Add Alert"
2. The Alert dialog will open

### Step 3: Configure Alert Condition
1. Set the **Condition** for your alert. Example: **RSI crosses 30** or **Price crosses below 500**
2. For RSI on L:HSBA:
   - Select "RSI" from the indicator dropdown
   - Set condition: "RSI crosses under 30"
3. Choose the **Timeframe** (e.g., "1 hour", "4 hours", "Daily")

### Step 4: Enable Webhook
1. In the Alert dialog, find the **"Webhook"** option
2. Check the box **"Enable webhook"**
3. Enter your webhook URL:
   ```
   http://your-server:5000/webhook/tradingview
   ```
   - Replace `your-server` with your server's IP or domain
   - Ensure your server is accessible from the internet (check firewall rules)

### Step 5: Set Alert Expiration
1. Set an expiration date for your alert (e.g., 1 month out)
2. Name your alert something descriptive (e.g., "HSBA RSI Oversold")

## 4. Webhook URL

Your Flask webhook receiver should be listening at:
```
http://your-server:5000/webhook/tradingview
```

For local testing, you can use ngrok to expose your local server:
```bash
ngrok http 5000
```
Then use the ngrok URL in TradingView.

## 5. Webhook Payload Format

TradingView sends a JSON payload when an alert fires. Example payload:

```json
{
  "password": "your_webhook_password",
  "exchange": "LSE",
  "symbol": "HSBA",
  "action": "buy",
  "price": 6.50,
  "quantity": 100,
  "alert_name": "HSBA RSI Oversold",
  "timestamp": 1715600000
}
```

### Recommended Payload Fields for Trading Agents
- `symbol` - Instrument code (e.g., "HSBA", "LLOY")
- `action` - "buy" or "sell"
- `price` - Trigger price (optional)
- `quantity` - Number of shares
- `order_type` - "market", "limit", etc.
- `alert_name` - Name of the TradingView alert

## 6. Testing the Webhook

### Test with curl
```bash
curl -X POST http://localhost:5000/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "password": "your_webhook_password",
    "symbol": "HSBA",
    "action": "buy",
    "quantity": 100,
    "price": 6.50,
    "alert_name": "Test Alert"
  }'
```

### Test with ngrok URL (from anywhere)
```bash
curl -X POST https://your-ngrok-url.ngrok.io/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "password": "your_webhook_password",
    "symbol": "HSBA",
    "action": "buy",
    "quantity": 100
  }'
```

## 7. Troubleshooting

| Issue | Possible Cause | Solution |
|-------|---------------|----------|
| Alert not triggering | Webhook URL not reachable | Check firewall, ensure server is running |
| 401/403 Error | Wrong or missing password | Verify password in payload matches config |
| 404 Not Found | Wrong endpoint path | Ensure URL path is `/webhook/tradingview` |
| Connection timeout | Server not running | Start Flask app: `python app.py` |
| No data in payload | TradingView account limits | Upgrade to Essential plan for LSE data |
| SSL certificate error | Using http instead of https | Use https or disable SSL verification in test |
| Alert fires but no trade | Error in order placement code | Check Flask app logs for exceptions |

### Common Fixes
1. **Verify server is running**: `curl http://localhost:5000/webhook/tradingview`
2. **Check ngrok tunnel**: Ensure ngrok is running if behind NAT
3. **Check TradingView console**: Open browser DevTools to see if request is sent
4. **Review Flask logs**: Check terminal output for incoming requests and errors
5. **Test with actual TradingView**: Create a test alert with a simple condition to verify connectivity

## 8. Example Flask Handler

```python
from flask import Flask, request, jsonify

app = Flask(__name__)

WEBHOOK_PASSWORD = "your_secret_password"

@app.route('/webhook/tradingview', methods=['POST'])
def webhook_tradingview():
    data = request.json

    # Verify password
    if data.get('password') != WEBHOOK_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401

    # Log the alert
    print(f"Alert received: {data}")

    # Process and execute trade via T212Client
    # ... your trading logic here ...

    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

## 9. Security Notes

- **Use HTTPS** in production (especially if exposing to public internet)
- **Set a strong webhook password** and keep it secret
- **Consider IP allowlisting** in your firewall
- **Validate all inputs** before executing trades
- **Add rate limiting** to prevent accidental duplicate trades