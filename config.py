import os
from dotenv import load_dotenv

load_dotenv()

# T212 Mode: "demo" or "live"
T212_MODE = os.getenv("T212_MODE", "demo").lower()

# API Endpoints
T212_ENDPOINTS = {
    "demo": "https://demo.trading212.com/api/v0",
    "live": "https://live.trading212.com/api/v0"
}

def get_t212_base_url():
    """Get base URL based on current T212_MODE (dynamic, not cached at import time)"""
    return T212_ENDPOINTS.get(T212_MODE, T212_ENDPOINTS["demo"])

def get_t212_credentials():
    """Get API credentials based on current T212_MODE"""
    if T212_MODE == "demo":
        return os.getenv("T212_DEMO_API_KEY", ""), os.getenv("T212_DEMO_API_SECRET", "")
    elif T212_MODE == "live":
        return os.getenv("T212_LIVE_API_KEY", ""), os.getenv("T212_LIVE_API_SECRET", "")
    else:
        raise ValueError(f"Invalid T212_MODE: {T212_MODE}. Must be 'demo' or 'live'.")

# LLM Settings for TradingAgents
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
DEEP_THINK_LLM = os.getenv("DEEP_THINK_LLM", "claude-sonnet-4-7")
QUICK_THINK_LLM = os.getenv("QUICK_THINK_LLM", "claude-haiku-4-5")

# Anthropic-compatible API (MiniMax uses this endpoint)
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Data Provider
DATA_PROVIDER = os.getenv("DATA_PROVIDER", "yfinance")  # yfinance or alphavantage
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY", "")

# Reminder flag
if T212_MODE == "demo":
    print("REMINDER: Using T212 DEMO API - Switch website to https://demo.trading212.com for testing")
    print("REMINDER: No real money will be used")
else:
    print("WARNING: Using T212 LIVE API - Switch website to https://app.trading212.com for production")
    print("WARNING: REAL MONEY WILL BE AT RISK - Ensure you know what you're doing!")
