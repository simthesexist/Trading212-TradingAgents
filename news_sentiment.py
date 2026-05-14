"""
AI-powered news sentiment analyzer using TradingAgents.

Analyzes news headlines and articles for sentiment to generate
BUY/SELL/HOLD signals based on financial news.
"""

import logging
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SentimentResult:
    """Result of sentiment analysis"""
    sentiment: str  # "POSITIVE", "NEGATIVE", "NEUTRAL"
    confidence: float  # 0.0 to 1.0
    summary: str
    key_themes: List[str]
    relevant_tickers: List[str]
    stock_mentioned: bool = False  # target ticker explicitly in news
    provider: str = "N/A"  # "MiniMax", "Fallback", etc.


import os
from dotenv import load_dotenv
load_dotenv()

# MiniMax Anthropic-compatible endpoint
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


class NewsSentimentAnalyzer:
    """
    Analyze news for sentiment using LLM-based reasoning.

    Connects to MiniMax via Anthropic-compatible API.
    Falls back to keyword-based sentiment if unavailable.
    """

    def __init__(self, confidence_threshold: float = 0.6):
        self.confidence_threshold = confidence_threshold
        self._client = None

    def _get_client(self):
        """Lazy init MiniMax via Anthropic-compatible API"""
        if self._client is None:
            try:
                from anthropic import Anthropic
                self._client = Anthropic(
                    base_url=ANTHROPIC_BASE_URL,
                    api_key=ANTHROPIC_API_KEY
                )
                logger.info(f"Connected to MiniMax at {ANTHROPIC_BASE_URL}")
            except Exception as e:
                logger.warning(f"MiniMax not available: {e}. Using fallback sentiment.")
                self._client = None
        return self._client

    def analyze_news(self, news_items: List[Dict], target_symbol: str = "") -> SentimentResult:
        """
        Analyze a list of news items and return sentiment.

        Args:
            news_items: List of dicts with 'title', 'summary', 'published', 'publisher'
            target_symbol: Check if this ticker is explicitly mentioned in news

        Returns:
            SentimentResult with sentiment, confidence, and themes
        """
        if not news_items:
            return SentimentResult(
                sentiment="NEUTRAL",
                confidence=0.0,
                summary="No news available",
                key_themes=[],
                relevant_tickers=[],
                provider="N/A"
            )

        # Check if target symbol is explicitly mentioned in any news item
        stock_mentioned = False
        if target_symbol:
            symbol_clean = target_symbol.replace(".L", "")
            for item in news_items:
                text = f"{item.get('title', '')} {item.get('summary', '')}".upper()
                if symbol_clean.upper() in text or target_symbol.upper() in text:
                    stock_mentioned = True
                    break

        # Combine titles for batch analysis
        titles = [n.get("title", "") for n in news_items if n.get("title")]
        summaries = [n.get("summary", "") for n in news_items if n.get("summary")]

        combined_text = " ".join(titles[:5])  # Focus on recent headlines
        combined_summary = " ".join(summaries[:3]) if summaries else combined_text

        result = self._analyze_text(combined_text, combined_summary, news_items)
        result.stock_mentioned = stock_mentioned
        return result

    def _analyze_text(self, text: str, summary: str, news_items: List[Dict]) -> SentimentResult:
        """Internal analysis using MiniMax or fallback heuristic."""

        client = self._get_client()

        if client is None:
            return self._fallback_sentiment(text, news_items)

        try:
            tickers = self._extract_tickers(news_items)

            # Use MiniMax (Anthropic-compatible) for sentiment analysis
            response = client.messages.create(
                model="minimax/m2.7",
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": f"Analyze this financial news sentiment. Reply with ONLY: POSITIVE/NEGATIVE/NEUTRAL and a confidence 0-1.\n\nNews: {text[:500]}"
                }]
            )

            # Parse response - handle both TextBlock and ThinkingBlock
            response_text = ""
            for block in response.content:
                if hasattr(block, 'text') and block.text:
                    response_text = block.text.strip().upper()
                    break

            # Parse response
            if "POSITIVE" in response_text:
                sentiment = "POSITIVE"
            elif "NEGATIVE" in response_text:
                sentiment = "NEGATIVE"
            else:
                sentiment = "NEUTRAL"

            # Extract confidence from response
            import re
            conf_match = re.search(r'0\.\d+', response_text)
            confidence = float(conf_match.group(0)) if conf_match else 0.7

            return SentimentResult(
                sentiment=sentiment,
                confidence=min(confidence, 1.0),
                summary=f"MiniMax analysis: {sentiment}",
                key_themes=self._extract_themes(text),
                relevant_tickers=tickers,
                provider="MiniMax"
            )

        except Exception as e:
            logger.error(f"MiniMax sentiment analysis failed: {e}")
            return self._fallback_sentiment(text, news_items)

    def _fallback_sentiment(self, text: str, news_items: List[Dict]) -> SentimentResult:
        """Rule-based fallback sentiment when LLM unavailable."""

        text_lower = text.lower()

        positive_words = [
            "beat", "beats", "bullish", "buy", "gain", "gains", "growth",
            "outperform", "upgrade", "rally", "rise", "soar", "surge",
            "profit", "profitable", "record", "high", "strong", "positive"
        ]
        negative_words = [
            "miss", "misses", "bearish", "sell", "loss", "decline",
            "underperform", "downgrade", "drop", "fall", "plunge", "fear",
            "risk", "warning", "cut", "low", "weak", "negative", "concern"
        ]

        pos_count = sum(1 for w in positive_words if w in text_lower)
        neg_count = sum(1 for w in negative_words if w in text_lower)

        total = pos_count + neg_count
        if total == 0:
            sentiment = "NEUTRAL"
            confidence = 0.4
        elif pos_count > neg_count:
            sentiment = "POSITIVE"
            confidence = min(0.5 + (pos_count - neg_count) * 0.1, 0.9)
        else:
            sentiment = "NEGATIVE"
            confidence = min(0.5 + (neg_count - pos_count) * 0.1, 0.9)

        return SentimentResult(
            sentiment=sentiment,
            confidence=confidence,
            summary=f"Based on {pos_count} positive, {neg_count} negative indicators",
            key_themes=self._extract_themes(text),
            relevant_tickers=self._extract_tickers(news_items),
            provider="Fallback"
        )

    def _extract_tickers(self, news_items: List[Dict]) -> List[str]:
        """Extract stock ticker symbols from news items."""
        import re
        tickers = []

        for item in news_items:
            text = item.get("title", "") + " " + item.get("summary", "")
            # Look for London Stock Exchange tickers (e.g., HSBA.L, BP.L)
            lse_tickers = re.findall(r'\b[A-Z]{2,5}\.L\b', text)
            tickers.extend(lse_tickers)

        # Also check 'related' field if present
        for item in news_items:
            related = item.get("related", [])
            if isinstance(related, list):
                tickers.extend([r for r in related if isinstance(r, str)])

        return list(set(tickers))[:5]  # Dedupe, limit to 5

    def _extract_themes(self, text: str) -> List[str]:
        """Extract financial themes from text."""
        themes = []
        theme_keywords = {
            "earnings": ["earnings", "revenue", "profit", "loss", "eps", "guidance"],
            "acquisition": ["acquire", "merger", "deal", "buyout", "takeover"],
            "dividend": ["dividend", "payout", "yield", "distribution"],
            "regulatory": ["regulation", "sec", "ftse", "ban", "approval"],
            "macro": ["rate", "inflation", "gdp", "fed", "boe", "ecb"],
            "products": ["launch", "product", "update", "release", "feature"],
        }

        text_lower = text.lower()
        for theme, keywords in theme_keywords.items():
            if any(kw in text_lower for kw in keywords):
                themes.append(theme)

        return themes[:5]

    def generate_trading_signal(
        self,
        sentiment: SentimentResult,
        price_change: Optional[float] = None
    ) -> Tuple[str, float, str]:
        """
        Convert sentiment to a trading signal.

        Returns:
            (signal, confidence, reason)
        """

        # High confidence positive + positive price action = BUY
        if sentiment.confidence >= self.confidence_threshold:
            if sentiment.sentiment == "POSITIVE":
                if price_change and price_change > 1.0:
                    return "BUY", sentiment.confidence, f"Positive news ({sentiment.confidence:.0%}) + price up {price_change:.1f}%"
                return "BUY", sentiment.confidence, f"Positive news sentiment ({sentiment.confidence:.0%})"

            elif sentiment.sentiment == "NEGATIVE":
                if price_change and price_change < -1.0:
                    return "SELL", sentiment.confidence, f"Negative news ({sentiment.confidence:.0%}) + price down {abs(price_change):.1f}%"
                return "SELL", sentiment.confidence, f"Negative news sentiment ({sentiment.confidence:.0%})"

        return "HOLD", 0.5, f"Low conviction ({sentiment.confidence:.0%})"


# Standalone analyzer instance
_analyzer: Optional[NewsSentimentAnalyzer] = None


def get_sentiment_analyzer() -> NewsSentimentAnalyzer:
    """Get or create global sentiment analyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = NewsSentimentAnalyzer()
    return _analyzer