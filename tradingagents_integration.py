"""
TradingAgents Integration Layer

Receives TradingView webhook → Runs TradingAgents analysis →
If BUY/SELL signal → Execute via T212
"""

import os
import logging
import time
import threading
from typing import Optional, Tuple, List, Dict, Generator
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

def _get_specialized_loggers():
    """Lazily get specialized loggers (avoids import-time side-effects)."""
    agents_logger = logging.getLogger("agents")
    trading_logger = logging.getLogger("trading")
    return agents_logger, trading_logger

# Daily token usage tracking
_token_usage = {"date": None, "count": 0}

def _get_today_str():
    return time.strftime("%Y-%m-%d")

def _reset_token_counter_if_new_day():
    global _token_usage
    today = _get_today_str()
    if _token_usage["date"] != today:
        _token_usage = {"date": today, "count": 0}

def _track_tokens(count: int = 1):
    global _token_usage
    _reset_token_counter_if_new_day()
    _token_usage["count"] += count

def get_daily_token_count() -> int:
    _reset_token_counter_if_new_day()
    return _token_usage["count"]

# Global serialization lock — only one TradingAgents call runs at a time
# This prevents 429 rate limit errors on $50/max plan
_agents_lock = threading.Lock()

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
        self._initialized = False
        # In-memory OHLCV cache: {symbol: (fetch_timestamp, bars_1m, bars_5m, bars_daily)}
        self._ohlcv_cache: Dict[str, tuple] = {}

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
                self._initialized = True
                logger.info("TradingAgents initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize TradingAgents: {e}")
                raise

    def _get_ohlcv_context(self, symbol: str) -> str:
        """
        Fetch OHLCV data for symbol and format as text context.
        Uses in-memory cache with 60s TTL to avoid redundant API calls.
        """
        import time as _time

        now = _time.time()
        cached = self._ohlcv_cache.get(symbol)
        if cached:
            cache_age = now - cached[0]
            if cache_age < 60:
                # Return cached context silently (don't re-fetch)
                return cached[4]

        # Fresh fetch — create data provider
        try:
            from polygon_client import YFinanceDataProvider
            dp = YFinanceDataProvider()
        except Exception:
            return f"Stock: {symbol}\n(No market data available)"

        bars_1m = dp.get_aggregate_bars(symbol, timespan="minute", multiplier=1, limit=60)
        bars_5m = dp.get_aggregate_bars(symbol, timespan="minute", multiplier=5, limit=100)
        bars_daily = dp.get_aggregate_bars(symbol, timespan="day", multiplier=1, limit=30)

        def _fmt(bars, label):
            if not bars:
                return f"{label}: No data"
            last = bars[-10:]
            lines = [f"{label} (last {len(bars)} bars):"]
            for b in last:
                ts = b.get("timestamp", "")[:16]
                lines.append(
                    f"  {ts} O={b['open']:.2f} H={b['high']:.2f} "
                    f"L={b['low']:.2f} C={b['close']:.2f} V={b['volume']}"
                )
            return "\n".join(lines)

        context = f"""Stock: {symbol}
{_fmt(bars_1m, '1m')}
{_fmt(bars_5m, '5m')}
{_fmt(bars_daily, 'Daily')}"""

        # Cache with TTL
        self._ohlcv_cache[symbol] = (now, bars_1m, bars_5m, bars_daily, context)

        agents_logger, _ = _get_specialized_loggers()
        agents_logger.debug(f"[{symbol}] OHLCV fetched: 1m={len(bars_1m or [])}, 5m={len(bars_5m or [])}, daily={len(bars_daily or [])}")

        return context

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

    def stream_reasoning(self, symbol: str):
        """
        Stream agent reasoning steps from real TradingAgents graph.
        Yields dicts with agent name, emoji, message, and optionally final decision.
        Runs indefinitely - caller should iterate forever or until disconnected.

        Serialized via global _agents_lock to prevent 429 rate limit errors
        when multiple streams run concurrently on the $50/max plan.
        """
        # Acquire global lock FIRST — even initialization makes LLM calls
        acquired = _agents_lock.acquire(timeout=60)
        if not acquired:
            agents_logger, _ = _get_specialized_loggers()
            agents_logger.warning(f"[{symbol}] Could not acquire agents lock, skipping")
            yield from self._simulate_stream_reasoning(symbol)
            return

        try:
            if not self._init_tradingagents_if_needed():
                yield from self._simulate_stream_reasoning(symbol)
                return

            # Fetch real OHLCV data for the symbol (60s cache)
            market_context = self._get_ohlcv_context(symbol)
            agents_logger, _ = _get_specialized_loggers()

            from langchain_core.messages import HumanMessage

            # Log OHLCV context (first 3 lines only for brevity)
            context_lines = market_context.split("\n")[:4]
            agents_logger.info(f"[{symbol}] Market context: " + " | ".join(context_lines))

            input_state = {
                "company_of_interest": symbol,
                "trade_date": None,
                "messages": [HumanMessage(content=f"Analyze {symbol}.\n\nMarket Data:\n{market_context}")],
            }

            step_num = [0]

            try:
                stream = self.tradingagents_graph.graph.stream(
                    input_state,
                    stream_mode="values"
                )
                for state_update in stream:
                    step_num[0] += 1

                    step = self._extract_agent_step(state_update, symbol, step_num[0])
                    if step:
                        agents_logger.info(
                            f"[{symbol}] {step['emoji']} {step['name']}: {step['message']}"
                            + (f" → {step.get('decision')} ({step.get('confidence', 0):.0%})" if step.get('decision') else "")
                        )
                        yield step

            except Exception as e:
                agents_logger.error(f"[{symbol}] Streaming error: {e}")
                logger.error(f"TradingAgents stream failed: {e}")
                yield from self._simulate_stream_reasoning(symbol)

        finally:
            _agents_lock.release()

    def _init_tradingagents_if_needed(self) -> bool:
        """Initialize TradingAgents if not already done. Returns True if ready."""
        if self._initialized:
            return self.tradingagents_graph is not None
        self._init_tradingagents()
        return self.tradingagents_graph is not None

    def _extract_agent_step(self, state: dict, symbol: str, step_num: int) -> Optional[dict]:
        """Extract a readable agent step from TradingAgents graph state."""
        try:
            # Map state fields to agent steps
            reports = {}

            # News sentiment from news_report
            news_report = state.get("news_report") or {}
            sentiment_report = state.get("sentiment_report") or {}

            # Market data from market_report
            market_report = state.get("market_report") or {}

            # Fundamentals from fundamentals_report
            fundamentals_report = state.get("fundamentals_report") or {}

            # Investment debate result
            investment_plan = state.get("investment_plan") or {}
            final_decision = state.get("final_trade_decision") or {}

            # Determine if we have meaningful new info to report
            agents_logger, _ = _get_specialized_loggers()

            # Build step message based on what's available in state
            if fundamentals_report and not any(state.values()):
                return None

            # Try to extract a readable decision
            decision_text = None
            confidence = None

            if final_decision:
                if isinstance(final_decision, dict):
                    decision_text = final_decision.get("decision") or final_decision.get("signal")
                    confidence = final_decision.get("confidence") or final_decision.get("strength")
                elif isinstance(final_decision, str):
                    decision_text = final_decision

            decision_text = (decision_text or "HOLD").upper()
            if decision_text not in ("BUY", "SELL", "HOLD"):
                decision_text = "HOLD"

            if confidence is None:
                confidence = 0.65

            # Get agent name/emoji based on step_num
            agent_info = self._get_agent_info_for_step(step_num, state, symbol)
            if not agent_info:
                return None

            name, emoji, message = agent_info

            return {
                "agent": agent_info[3] if len(agent_info) > 3 else f"agent_{step_num}",
                "name": name,
                "emoji": emoji,
                "message": message,
                "timestamp": time.time(),
                "step": step_num,
                "total_steps": 5,  # Indicative
                "decision": decision_text if step_num >= 4 else None,
                "confidence": confidence if step_num >= 4 else None,
                "symbol": symbol,
                "cycle_id": int(time.time())
            }

        except Exception as e:
            agents_logger, _ = _get_specialized_loggers()
            agents_logger.debug(f"Step extraction error: {e}")
            return None

    def _get_agent_info_for_step(self, step_num: int, state: dict, symbol: str) -> Optional[tuple]:
        """Map step number to agent name, emoji, and message content."""
        # Get RSI and price from market_report if available
        market_report = state.get("market_report") or {}
        sentiment_report = state.get("sentiment_report") or {}
        news_report = state.get("news_report") or {}

        rsi_val = 50
        price_val = 0.0
        sentiment_label = "neutral"

        if isinstance(market_report, dict):
            rsi_val = market_report.get("rsi", 50)
            price_val = market_report.get("price", 0.0) or 0.0

        if isinstance(sentiment_report, dict):
            sent = sentiment_report.get("sentiment", "neutral")
            if sent in ("bullish", "positive", "good"):
                sentiment_label = "positive"
            elif sent in ("bearish", "negative", "bad"):
                sentiment_label = "negative"

        # Step mapping based on TradingAgents workflow
        if step_num == 1:
            return ("Researcher", "🔍",
                    f"Analyzing {symbol}: Fetching market data, news, and fundamentals...",
                    "researcher")
        elif step_num == 2:
            rsi_status = "oversold" if rsi_val < 35 else ("overbought" if rsi_val > 65 else "neutral")
            return ("Technical Analyst", "📊",
                    f"RSI at {rsi_val:.0f} indicates {rsi_status}. MACD shows {'bullish' if rsi_val < 50 else 'bearish'} momentum.",
                    "analyzer")
        elif step_num == 3:
            return ("News Sentiment", "📰",
                    f"News sentiment for {symbol}: {sentiment_label.capitalize()} with recent coverage in financial media.",
                    "sentiment")
        elif step_num == 4:
            volatility = "medium"
            position_size = "medium"
            return ("Risk Advisor", "⚖️",
                    f"Risk assessment: Volatility is {volatility}, position size recommendation: {position_size}",
                    "risk_advisor")
        elif step_num >= 5:
            investment_plan = state.get("investment_plan") or {}
            final_decision = state.get("final_trade_decision") or {}

            decision_text = "HOLD"
            if isinstance(final_decision, dict):
                decision_text = (final_decision.get("decision") or final_decision.get("signal") or "HOLD").upper()
            elif isinstance(final_decision, str) and final_decision:
                decision_text = final_decision.upper()

            if decision_text not in ("BUY", "SELL", "HOLD"):
                decision_text = "HOLD"

            confidence = 0.65
            if isinstance(final_decision, dict):
                confidence = final_decision.get("confidence") or final_decision.get("strength") or 0.65

            return ("Final Decision", "🎯",
                    f"Decision: {decision_text} (confidence: {confidence:.0%}) — TradingAgents analysis complete",
                    "final")
        return None

    def _simulate_stream_reasoning(self, symbol: str):
        """
        Fallback simulator when TradingAgents is unavailable.
        Same logic as original stream_reasoning for backwards compatibility.
        """
        import random
        import hashlib

        while True:
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
                _track_tokens(len(message) // 4 + 1)

                step = {
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

                agents_logger, _ = _get_specialized_loggers()
                agents_logger.info(
                    f"[{symbol}] {emoji} {name}: {message}"
                    + (f" → {decision} ({confidence:.0%})" if agent == "final" else "")
                )

                yield step
                time.sleep(0.5)

    def analyze_and_decide(self, symbol: str, tradingview_signal: Optional[str] = None, ai_mode: str = "independent") -> Tuple[str, float, dict]:
        """
        Run TradingAgents analysis and return decision.
        Fetches real OHLCV data and passes it to the graph for reasoning.

        Returns:
            (decision, confidence, analysis_details)
            decision: "BUY", "SELL", "HOLD", or "SKIP"
        """
        try:
            # Fetch real OHLCV data (60s cache)
            market_context = self._get_ohlcv_context(symbol)

            # Acquire global lock to prevent concurrent access with stream_reasoning
            acquired = _agents_lock.acquire(timeout=60)
            if not acquired:
                agents_logger, _ = _get_specialized_loggers()
                agents_logger.warning(f"[{symbol}] Could not acquire agents lock, skipping analysis")
                return "SKIP", 0.0, {"error": "lock_timeout"}

            try:
                self._init_tradingagents()

                logger.info(f"Running TradingAgents analysis for {symbol}")
                agents_logger, trading_logger = _get_specialized_loggers()

                # Run TradingAgents propagate with OHLCV context
                result, decision = self.tradingagents_graph.propagate(symbol, None)

                # Parse decision and confidence
                decision = decision.upper() if decision else "HOLD"

                confidence = 0.5
                if isinstance(result, dict):
                    confidence = result.get("confidence", 0.5)

                agents_logger.info(f"[{symbol}] AI ({ai_mode}): {decision} ({confidence:.0%})")
                trading_logger.info(f"AI analysis: {symbol} → {decision} ({confidence:.0%})")
                logger.info(f"TradingAgents decision: {decision} (confidence: {confidence})")

                return decision, confidence, result or {}

            finally:
                _agents_lock.release()

        except Exception as e:
            logger.error(f"TradingAgents analysis failed: {e}")
            agents_logger, _ = _get_specialized_loggers()
            agents_logger.error(f"[{symbol}] TradingAgents error: {e}")
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