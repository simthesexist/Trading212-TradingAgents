"""
Trading strategies with alert thresholds.
Each strategy defines conditions that trigger analysis/execution.
"""

STRATEGIES = {
    "RSI_OVERSOLD": {
        "name": "RSI Oversold",
        "indicator": "RSI",
        "condition": "crosses_below",
        "threshold": 30,
        "description": "RSI drops below 30 (oversold) - potential buy signal",
        "priority": "high"
    },
    "RSI_OVERBOUGHT": {
        "name": "RSI Overbought",
        "indicator": "RSI",
        "condition": "crosses_above",
        "threshold": 70,
        "description": "RSI rises above 70 (overbought) - potential sell signal",
        "priority": "high"
    },
    "RSI_EXTREME_OVERSOLD": {
        "name": "RSI Extreme Oversold",
        "indicator": "RSI",
        "condition": "crosses_below",
        "threshold": 20,
        "description": "RSI below 20 - extreme oversold, strong buy opportunity",
        "priority": "high"
    },
    "RSI_EXTREME_OVERBOUGHT": {
        "name": "RSI Extreme Overbought",
        "indicator": "RSI",
        "condition": "crosses_above",
        "threshold": 80,
        "description": "RSI above 80 - extreme overbought, strong sell signal",
        "priority": "high"
    },
    "MA_CROSS_ABOVE": {
        "name": "MA Bullish Crossover",
        "indicator": "MA",
        "fast_period": 50,
        "slow_period": 200,
        "condition": "fast_crosses_above_slow",
        "description": "50-day MA crosses above 200-day MA - bullish signal",
        "priority": "medium"
    },
    "MA_CROSS_BELOW": {
        "name": "MA Bearish Crossover",
        "indicator": "MA",
        "fast_period": 50,
        "slow_period": 200,
        "condition": "fast_crosses_below_slow",
        "description": "50-day MA crosses below 200-day MA - bearish signal",
        "priority": "medium"
    },
    "VOLUME_SPIKE": {
        "name": "Volume Spike",
        "indicator": "Volume",
        "condition": "spikes_above",
        "threshold": 2.5,  # 2.5x average volume
        "description": "Volume 2.5x above average - unusual activity",
        "priority": "medium"
    },
    "VOLUME_DROP": {
        "name": "Volume Drop",
        "indicator": "Volume",
        "condition": "drops_below",
        "threshold": 0.3,  # 30% of average
        "description": "Volume very low - potential dead period",
        "priority": "low"
    },
    "MACD_CROSS_ABOVE": {
        "name": "MACD Bullish",
        "indicator": "MACD",
        "condition": "macd_crosses_above_signal",
        "description": "MACD line crosses above signal line - buy",
        "priority": "medium"
    },
    "MACD_CROSS_BELOW": {
        "name": "MACD Bearish",
        "indicator": "MACD",
        "condition": "macd_crosses_below_signal",
        "description": "MACD line crosses below signal line - sell",
        "priority": "medium"
    },
    "PRICE_DROP_5PCT": {
        "name": "Price Drop 5%",
        "indicator": "Price",
        "condition": "drops_by_percent",
        "threshold": 5.0,
        "description": "Price dropped 5% or more - potential buy opportunity",
        "priority": "high"
    },
    "PRICE_RISE_5PCT": {
        "name": "Price Rise 5%",
        "indicator": "Price",
        "condition": "rises_by_percent",
        "threshold": 5.0,
        "description": "Price rose 5% or more - potential sell signal",
        "priority": "high"
    },
    # News-based strategies
    "NEWS_BULLISH": {
        "name": "Bullish News Sentiment",
        "indicator": "NewsSentiment",
        "condition": "sentiment_positive",
        "threshold": 0.65,
        "description": "AI-detected positive news sentiment - potential buy signal",
        "priority": "high"
    },
    "NEWS_BEARISH": {
        "name": "Bearish News Sentiment",
        "indicator": "NewsSentiment",
        "condition": "sentiment_negative",
        "threshold": 0.65,
        "description": "AI-detected negative news sentiment - potential sell signal",
        "priority": "high"
    },
    "NEWS_VERY_BULLISH": {
        "name": "Strong Bullish News",
        "indicator": "NewsSentiment",
        "condition": "sentiment_positive_high",
        "threshold": 0.80,
        "description": "High-confidence positive news - strong buy signal",
        "priority": "high"
    },
    "NEWS_VERY_BEARISH": {
        "name": "Strong Bearish News",
        "indicator": "NewsSentiment",
        "condition": "sentiment_negative_high",
        "threshold": 0.80,
        "description": "High-confidence negative news - strong sell signal",
        "priority": "high"
    },
    "EARNINGS_BEAT": {
        "name": "Earnings Beat",
        "indicator": "Earnings",
        "condition": "beat_expectations",
        "threshold": 0.0,
        "description": "Earnings exceeded expectations - bullish signal",
        "priority": "medium"
    },
    "EARNINGS_MISS": {
        "name": "Earnings Miss",
        "indicator": "Earnings",
        "condition": "miss_expectations",
        "threshold": 0.0,
        "description": "Earnings missed expectations - bearish signal",
        "priority": "medium"
    },
    "DIVIDEND_INCREASE": {
        "name": "Dividend Increase",
        "indicator": "Dividend",
        "condition": "increased",
        "threshold": 0.0,
        "description": "Dividend raised - positive signal for income investors",
        "priority": "medium"
    },
    "UPGRADE": {
        "name": "Analyst Upgrade",
        "indicator": "AnalystRating",
        "condition": "upgraded",
        "threshold": 0.0,
        "description": "Analyst upgraded rating - bullish signal",
        "priority": "high"
    },
    "DOWNGRADE": {
        "name": "Analyst Downgrade",
        "indicator": "AnalystRating",
        "condition": "downgraded",
        "threshold": 0.0,
        "description": "Analyst downgraded rating - bearish signal",
        "priority": "high"
    }
}

# Strategy keys for quick lookup
STRATEGY_KEYS = list(STRATEGIES.keys())