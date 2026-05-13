"""
TradingAgents Integration Layer

Receives TradingView webhook → Runs TradingAgents analysis →
If BUY/SELL signal → Execute via T212
"""

import os
import logging
import time
from typing import Optional, Tuple, List, Dict, Generator
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# LLM Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
DEEP_THINK_LLM = os.getenv("DEEP_THINK_LLM", "claude-sonnet-4-7")
QUICK_THINK_LLM = os.getenv("QUICK_THINK_LLM", "claude-haiku-4-5")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# TradingAgents settings
AUTO_EXECUTE = os.getenv("AUTO_EXECUTE", "false").lower() == "true"  # Default: manual review
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.7"))  # 70% min confidence
ALLOW_SELL = os.getenv("ALLOW_SELL", "true").lower() == "true"

# Simulated agent reasoning (placeholder until TradingAgents exposes internals)
AGENT_REASONING = {
    "researcher": {
        "name": "Researcher",
        "emoji": "🔍",
        "template": "Analyzing {symbol}: Checking RSI ({rsi}), MACD ({macd}), news sentiment ({news})..."
    },
    "analyzer": {
        "name": "Technical Analyst",
        "emoji": "📊",
        "template": "RSI at {rsi} indicates {rsi_status}. MACD histogram shows {macd_signal} momentum."
    },
    "risk_advisor": {
        "name": "Risk Advisor",
        "emoji": "⚖️",
        "template": "Risk assessment: Volatility is {volatility}, position size recommendation: {position_size}"
    },
    "sentiment": {
        "name": "News Sentiment",
        "emoji": "📰",
        "template": "News sentiment for {symbol}: {sentiment_label} ({sentiment_score:.0%}) with key themes: {themes}"
    },
    "final": {
        "name": "Final Decision",
        "emoji": "🎯",
        "template": "Decision: {decision} | Confidence: {confidence:.0%} | Reasoning: {reasoning}"
    }
}

class TradingAgentsIntegration:
    """Integration layer between TradingView webhook and TradingAgents"""

    def __init__(self):
        self.llm_provider = LLM_PROVIDER
        self.deep_llm = DEEP_THINK_LLM
        self.quick_llm = QUICK_THINK_LLM
        self.auto_execute = AUTO_EXECUTE
        self.confidence_threshold = CONFIDENCE_THRESHOLD
        self.tradingagents_graph = None

    def _init_tradingagents(self):
        """Lazy initialization of TradingAgents"""
        if self.tradingagents_graph is None:
            try:
                from tradingagents.graph.trading_graph import TradingAgentsGraph
                from tradingagents.default_config import DEFAULT_CONFIG

                config = DEFAULT_CONFIG.copy()
                config["llm_provider"] = self.llm_provider
                config["deep_think_llm"] = self.deep_llm
                config["quick_think_llm"] = self.quick_llm

                # Set API keys based on provider
                if self.llm_provider == "openai" and OPENAI_API_KEY:
                    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
                elif self.llm_provider == "anthropic" and ANTHROPIC_API_KEY:
                    os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY
                elif self.llm_provider == "google" and GOOGLE_API_KEY:
                    os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY

                self.tradingagents_graph = TradingAgentsGraph(debug=True, config=config)
                logger.info("TradingAgents initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize TradingAgents: {e}")
                raise

    def _simulate_agent_reasoning(self, symbol: str) -> List[Dict]:
        """Simulate multi-agent reasoning chain for demonstration"""
        import random
        import hashlib

        # Generate deterministic but varied values based on symbol
        seed = int(hashlib.md5(symbol.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)

        rsi = rng.randint(25, 85)
        macd = rng.uniform(-2, 2)
        news_score = rng.uniform(-1, 1)
        volatility = rng.choice(["low", "medium", "high"])

        # Determine indicators
        rsi_status = "oversold" if rsi < 35 else ("overbought" if rsi > 65 else "neutral")
        macd_signal = "bullish" if macd > 0.5 else ("bearish" if macd < -0.5 else "neutral")
        sentiment_label = "positive" if news_score > 0.3 else ("negative" if news_score < -0.3 else "neutral")
        position_size = "small" if volatility == "high" else ("medium" if volatility == "medium" else "large")

        themes = rng.sample(["earnings", "dividends", "mergers", "regulatory", "macro", "sector"], 2)
        reasoning_texts = [
            f"Based on technicals and sentiment, {symbol} shows {rsi_status} conditions.",
            f"MACD indicates {macd_signal} momentum with RSI at {rsi}.",
            f"News analysis reveals {sentiment_label} sentiment driven by {themes[0]} and {themes[1]}.",
            f"Volatility is {volatility} - adjusting position sizing accordingly.",
            f"Overall assessment supports a {rsi_status} outlook with {macd_signal} confirmation."
        ]

        steps = [
            {
                "agent": "researcher",
                "name": "Researcher",
                "emoji": "🔍",
                "message": AGENT_REASONING["researcher"]["template"].format(
                    symbol=symbol, rsi=rsi, macd=macd, news=sentiment_label
                ),
                "timestamp": None
            },
            {
                "agent": "analyzer",
                "name": "Technical Analyst",
                "emoji": "📊",
                "message": AGENT_REASONING["analyzer"]["template"].format(
                    rsi=rsi, rsi_status=rsi_status, macd_signal=macd_signal
                ),
                "timestamp": None
            },
            {
                "agent": "sentiment",
                "name": "News Sentiment",
                "emoji": "📰",
                "message": AGENT_REASONING["sentiment"]["template"].format(
                    symbol=symbol, sentiment_label=sentiment_label,
                    sentiment_score=abs(news_score), themes=", ".join(themes)
                ),
                "timestamp": None
            },
            {
                "agent": "risk_advisor",
                "name": "Risk Advisor",
                "emoji": "⚖️",
                "message": AGENT_REASONING["risk_advisor"]["template"].format(
                    volatility=volatility, position_size=position_size
                ),
                "timestamp": None
            },
        ]

        # Final decision based on RSI and sentiment
        if rsi > 70 and news_score < -0.2:
            decision = "SELL"
            confidence = 0.75 + rng.uniform(0, 0.2)
            reasoning = reasoning_texts[0] + " " + reasoning_texts[1]
        elif rsi < 30 and news_score > 0.2:
            decision = "BUY"
            confidence = 0.75 + rng.uniform(0, 0.2)
            reasoning = reasoning_texts[1] + " " + reasoning_texts[2]
        else:
            decision = "HOLD"
            confidence = 0.50 + rng.uniform(0, 0.3)
            reasoning = reasoning_texts[4]

        steps.append({
            "agent": "final",
            "name": "Final Decision",
            "emoji": "🎯",
            "message": AGENT_REASONING["final"]["template"].format(
                decision=decision, confidence=min(confidence, 0.99), reasoning=reasoning[:100]
            ),
            "timestamp": None,
            "decision": decision,
            "confidence": min(confidence, 0.99)
        })

        return steps

    def stream_reasoning(self, symbol: str) -> Generator[Dict, None, None]:
        """
        Stream agent reasoning steps continuously.
        Yields dicts with agent name, emoji, message, and optionally final decision.
        Runs indefinitely - caller should iterate forever or until disconnected.
        """
        import random
        import hashlib

        while True:
            # Use time-based seed for fresh values each cycle
            seed = int(hashlib.md5(symbol.encode()).hexdigest()[:8], 16) + int(time.time())
            rng = random.Random(seed)

            rsi = rng.randint(25, 85)
            macd = rng.uniform(-2, 2)
            news_score = rng.uniform(-1, 1)
            volatility = rng.choice(["low", "medium", "high"])

            rsi_status = "oversold" if rsi < 35 else ("overbought" if rsi > 65 else "neutral")
            macd_signal = "bullish" if macd > 0.5 else ("bearish" if macd < -0.5 else "neutral")
            sentiment_label = "positive" if news_score > 0.3 else ("negative" if news_score < -0.3 else "neutral")
            position_size = "small" if volatility == "high" else ("medium" if volatility == "medium" else "large")
            themes = rng.sample(["earnings", "dividends", "mergers", "regulatory", "macro", "sector"], 2)

            reasoning_texts = [
                f"Based on technicals and sentiment, {symbol} shows {rsi_status} conditions.",
                f"MACD indicates {macd_signal} momentum with RSI at {rsi}.",
                f"News analysis reveals {sentiment_label} sentiment driven by {themes[0]} and {themes[1]}.",
                f"Volatility is {volatility} - adjusting position sizing accordingly.",
                f"Overall assessment supports a {rsi_status} outlook with {macd_signal} confirmation."
            ]

            # Determine decision
            if rsi > 70 and news_score < -0.2:
                decision = "SELL"
                confidence = min(0.75 + rng.uniform(0, 0.2), 0.99)
                reasoning = reasoning_texts[0] + " " + reasoning_texts[1]
            elif rsi < 30 and news_score > 0.2:
                decision = "BUY"
                confidence = min(0.75 + rng.uniform(0, 0.2), 0.99)
                reasoning = reasoning_texts[1] + " " + reasoning_texts[2]
            else:
                decision = "HOLD"
                confidence = min(0.50 + rng.uniform(0, 0.3), 0.99)
                reasoning = reasoning_texts[4]

            # Yield each agent step with 0.5s delay
            steps_data = [
                ("researcher", "Researcher", "🔍",
                 AGENT_REASONING["researcher"]["template"].format(
                     symbol=symbol, rsi=rsi, macd=round(macd, 2), news=sentiment_label)),
                ("analyzer", "Technical Analyst", "📊",
                 AGENT_REASONING["analyzer"]["template"].format(
                     rsi=rsi, rsi_status=rsi_status, macd_signal=macd_signal)),
                ("sentiment", "News Sentiment", "📰",
                 AGENT_REASONING["sentiment"]["template"].format(
                     symbol=symbol, sentiment_label=sentiment_label,
                     sentiment_score=abs(news_score), themes=", ".join(themes))),
                ("risk_advisor", "Risk Advisor", "⚖️",
                 AGENT_REASONING["risk_advisor"]["template"].format(
                     volatility=volatility, position_size=position_size)),
                ("final", "Final Decision", "🎯",
                 AGENT_REASONING["final"]["template"].format(
                     decision=decision, confidence=confidence, reasoning=reasoning[:100])),
            ]

            for i, (agent, name, emoji, message) in enumerate(steps_data):
                yield {
                    "agent": agent,
                    "name": name,
                    "emoji": emoji,
                    "message": message,
                    "timestamp": time.time(),
                    "step": i + 1,
                    "total_steps": len(steps_data),
                    "decision": decision if agent == "final" else None,
                    "confidence": confidence if agent == "final" else None,
                    "symbol": symbol,
                    "cycle_id": int(time.time())
                }
                time.sleep(0.5)

    def analyze_and_decide(self, symbol: str, tradingview_signal: Optional[str] = None) -> Tuple[str, float, dict]:
        """
        Run TradingAgents analysis and return decision.

        Returns:
            (decision, confidence, analysis_details)
            decision: "BUY", "SELL", "HOLD", or "SKIP"
        """
        try:
            self._init_tradingagents()

            logger.info(f"Running TradingAgents analysis for {symbol}")

            # Run TradingAgents propagate
            result, decision = self.tradingagents_graph.propagate(symbol, None)

            # Parse decision and confidence
            decision = decision.upper() if decision else "HOLD"

            confidence = 0.5
            if isinstance(result, dict):
                confidence = result.get("confidence", 0.5)

            logger.info(f"TradingAgents decision: {decision} (confidence: {confidence})")

            return decision, confidence, result or {}

        except Exception as e:
            logger.error(f"TradingAgents analysis failed: {e}")
            return "ERROR", 0.0, {"error": str(e)}

    def should_execute(self, decision: str, confidence: float) -> Tuple[bool, str]:
        """
        Determine if a signal should be executed based on policy.

        Returns:
            (should_execute, reason)
        """
        # Check confidence threshold
        if confidence < self.confidence_threshold:
            return False, f"Confidence {confidence} below threshold {self.confidence_threshold}"

        # Check if sell is allowed
        if decision == "SELL" and not ALLOW_SELL:
            return False, "SELL signals disabled by configuration"

        # Only execute BUY or SELL
        if decision not in ["BUY", "SELL"]:
            return False, f"Decision {decision} is not executable (only BUY/SELL)"

        return True, "Approved for execution"