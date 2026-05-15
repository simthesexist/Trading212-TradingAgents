# Trading Strategy Analysis

This document provides an analysis of the trading strategies implemented in `strategies.py`.

## 1. Sentiment Strategy (`sentiment_strategy`)

This strategy attempts to use news sentiment to make trading decisions.

**Logic:**
1.  Fetches a sentiment score for a given stock symbol using the `news_sentiment.get_sentiment()` function.
2.  **Buy Signal:** If the sentiment score is greater than 0.5.
3.  **Sell Signal:** If the sentiment score is less than -0.5.
4.  **Hold Signal:** If the sentiment score is between -0.5 and 0.5.

**Analysis:**
*   The sentiment analysis logic in `news_sentiment.py` is currently a **placeholder**. It generates a random number between -1 and 1 and does not perform any real sentiment analysis.
*   Therefore, this strategy will generate random buy/sell signals.
*   **Recommendation:** This strategy should not be used in a live trading environment without implementing a proper sentiment analysis model.

## 2. Technical Strategy (`technical_strategy`)

This strategy uses common technical indicators to generate trading signals.

**Logic:**
1.  Fetches historical daily closing prices for a given stock symbol.
2.  Calculates the following technical indicators:
    *   **Relative Strength Index (RSI):** 14-day window.
    *   **Short-term Simple Moving Average (SMA):** 20-day window.
    *   **Long-term Simple Moving Average (LMA):** 50-day window.
3.  **Buy Signal:** When the RSI is below 30 (indicating the asset is oversold) AND the short-term SMA is above the long-term LMA (indicating an upward trend).
4.  **Sell Signal:** When the RSI is above 70 (indicating the asset is overbought) AND the short-term SMA is below the long-term LMA (indicating a downward trend).
5.  **Hold Signal:** All other conditions.

**Analysis:**
*   This strategy is a standard implementation of a common technical trading strategy.
*   The combination of RSI and moving average crossovers is a popular technique to identify entry and exit points.
*   The parameters (RSI window, SMA/LMA windows) are standard, but may not be optimal for all market conditions or all stocks.
*   **Recommendation:** This strategy can be used as a baseline, but its performance should be backtested and the parameters may need to be optimized.

## 3. News-Based Strategy (`news_based_strategy`)

This strategy is intended to trade based on news events, but it is not implemented.

**Logic:**
*   The function is a placeholder and always returns a "hold" signal.

**Analysis:**
*   This strategy is incomplete and serves no purpose in its current state.
*   **Recommendation:** This strategy needs to be fully implemented with logic to parse news and generate trading signals based on specific news events.
