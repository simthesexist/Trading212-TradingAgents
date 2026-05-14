# TradingView + Trading 212 + TradingAgents Integration

A hybrid trading system: TradingView alerts → TradingAgents analysis → Trading 212 execution.

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# Edit .env with your credentials
nano .env
```

## Configuration

### T212 Mode

Set in `.env`:
- **demo**: Uses `https://demo.trading212.com` - no real money
- **live**: Uses `https://live.trading212.com` - REAL MONEY

### LLM Provider (TradingAgents)

Supported providers: `anthropic`, `openai`, `google`, `deepseek`, etc.

### Execution Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_EXECUTE` | `false` | Set `true` for automated execution |
| `CONFIDENCE_THRESHOLD` | `0.7` | Min confidence to execute (0.0-1.0) |
| `ALLOW_SELL` | `true` | Enable/disable SELL signals |

## Run

```bash
python app.py
```

The Flask server starts on `http://0.0.0.0:5000`.

**Demo mode reminder:** Website must be set to https://demo.trading212.com

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhook/tradingview` | POST | TradingView webhook with TradingAgents analysis |
| `/analyze/<symbol>` | GET | Direct TradingAgents analysis |
| `/webhook` | POST | Simple TradingView webhook (signal only) |
| `/health` | GET | Health check |

### Webhook Payload

```json
{
    "symbol": "HSBA.L",
    "action": "buy",
    "price": 685.50,
    "quantity": 10
}
```

### Analysis Response

```json
{
    "symbol": "HSBA.L",
    "decision": "BUY",
    "confidence": 0.75,
    "details": { ... },
    "would_execute": true,
    "reason": "Approved for execution",
    "auto_execute": false
}
```

## Flow

```
TradingView Alert (Webhook)
         │
         ▼
Flask /webhook/tradingview
         │
         ▼
TradingAgents.analyze_and_decide(HSBA.L)
         │
         ├── Run: Fundamentals + Sentiment + News + Technical Analysts
         ├── Run: Bull/Bear Researchers debate
         ├── Run: Trader Agent decision
         └── Return: (BUY/SELL/HOLD, confidence, details)
         │
         ▼
should_execute() check
         │
         ├── confidence >= 0.7?
         ├── SELL allowed?
         └── decision in [BUY, SELL]?
         │
         ▼
T212ExecutionLayer.execute_order()
         │
         ▼
T212 Demo/Live API → Order Executed
```

## ⚠️ Trading Disclosure

**This software is for informational and educational purposes only.**

- This system executes real trades on a live Trading 212 account using REAL MONEY when set to live mode.
- Autonomously trading involves substantial risk of financial loss.
- Past performance does not guarantee future results.
- This system is not a licensed financial advisor or investment service.
- You are solely responsible for any trades placed using this software and must accept all associated risks.
- The maintainer(s) of this project accept no liability for any financial losses incurred as a result of using this software.
- **Only trade with money you can afford to lose.** Start in demo mode and understand all risks before switching to live execution.

**Never invest more than you can afford to lose.**

---

## Files

- `config.py` - Configuration loader
- `t212_client.py` - Trading 212 REST API client
- `tradingagents_integration.py` - TradingAgents wrapper
- `app.py` - Flask webhook server
- `flask_webhook_bridge.py` - T212 execution layer