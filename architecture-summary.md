# Architecture Diagrams Summary

## 1. architecture-diagram.mmd
**Purpose:** High-level system flow

Shows the 6 main components and data flow:
- TradingView triggers alerts → Flask webhook
- Flask analyzes via TradingAgents AI
- TradingAgents fetches data from yfinance/Alpha Vantage
- Flask executes orders via T212 Client
- Trading212 broker confirms execution

## 2. sequence-diagram.mmd
**Purpose:** Step-by-step request lifecycle

10-step flow from alert to execution:
1. TradingView alert fires webhook
2. Flask receives POST request
3. TradingAgents.propagate() called
4. Market data fetched
5. Analysts run analysis
6. Researchers debate
7. Signal (BUY/SELL/HOLD) returned
8. If actionable → T212 API called
9. Order executed at broker
10. Confirmation returned

## 3. component-diagram.mmd
**Purpose:** Component relationships grouped by layer

Three layers:
- **External:** TradingView alerts
- **Core Engine:** Flask server + TradingAgents AI
- **Data Layer:** yfinance, Alpha Vantage
- **Execution Layer:** T212 Client → Trading212 Broker

## Key Design Points
- TradingView is the trigger source
- Flask is the central coordinator
- TradingAgents handles all AI logic
- T212 Client abstracts broker API
- Async data flow with confirmation loop