from flask import Flask, request, jsonify, render_template
import logging
import os
import threading
import time
from t212_client import T212Client
import config
from tradingagents_integration import TradingAgentsIntegration
from monitor import get_monitor

try:
    from flask_webhook_bridge import OrderRequest, T212ExecutionLayer
    HAS_WEBHOOK_BRIDGE = True
except ImportError:
    HAS_WEBHOOK_BRIDGE = False
    OrderRequest = None
    T212ExecutionLayer = None
from watchlist import LSE_WATCHLIST
from strategies import STRATEGIES
from position_tracker import get_tracker

try:
    from news_sentiment import get_sentiment_analyzer
    HAS_NEWS_SENTIMENT = True
except ImportError:
    HAS_NEWS_SENTIMENT = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global runtime mode (overrides config.T212_MODE)
RUNTIME_MODE = None

# Global instances
t212_client = None
execution_layer = None
tradingagents = TradingAgentsIntegration()

def get_mode():
    """Get current mode - RUNTIME_MODE takes precedence over config"""
    return RUNTIME_MODE or config.T212_MODE

def init_t212_client():
    global t212_client, execution_layer
    t212_client = T212Client()
    if HAS_WEBHOOK_BRIDGE:
        execution_layer = T212ExecutionLayer()
    return t212_client

def get_account_info():
    """Fetch account info from T212"""
    global t212_client
    try:
        if t212_client is None:
            init_t212_client()
        return t212_client.get_account_summary()
    except Exception as e:
        logger.error(f"Failed to get account info: {e}")
        return None

@app.route('/')
@app.route('/ui')
def ui():
    """Render the web UI"""
    return render_template('index.html')

@app.route('/api/mode', methods=['GET'])
def get_mode_api():
    """Get current mode and account info"""
    mode = get_mode()
    account = get_account_info()
    return jsonify({
        "mode": mode,
        "endpoint": f"https://{'demo' if mode == 'demo' else 'live'}.trading212.com/api/v0",
        "account": account
    })

@app.route('/api/mode', methods=['POST'])
def post_mode_api():
    """Switch between demo and live mode"""
    global RUNTIME_MODE, t212_client, execution_layer

    data = request.json
    new_mode = data.get('mode', '').lower()

    if new_mode not in ['demo', 'live']:
        return jsonify({"error": "Invalid mode. Use 'demo' or 'live'"}), 400

    old_mode = get_mode()
    if old_mode == new_mode:
        return jsonify({"status": "no_change", "mode": new_mode})

    RUNTIME_MODE = new_mode
    logger.info(f"MODE SWITCH: {old_mode} -> {new_mode}")

    # Reinitialize T212 client and execution layer with new mode
    os.environ["T212_MODE"] = new_mode
    t212_client = T212Client()
    if HAS_WEBHOOK_BRIDGE:
        execution_layer = T212ExecutionLayer()
    
    logger.info(f"t212_client base_url: {t212_client.base_url}")

    account = get_account_info()

    return jsonify({
        "status": "switched",
        "old_mode": old_mode,
        "new_mode": new_mode,
        "endpoint": f"https://{'demo' if new_mode == 'demo' else 'live'}.trading212.com/api/v0",
        "account": account
    })

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Receive TradingView webhook alerts"""
    try:
        payload = request.json
        logger.info(f"Received webhook: {payload}")

        symbol = payload.get('symbol', '')
        action = payload.get('action', '')
        price = payload.get('price', 0)

        logger.info(f"TradingView Alert: {action} {symbol} @ {price}")

        # Check if this is a trading action
        if action.upper() in ['BUY', 'SELL']:
            logger.info(f"Trading signal received: {action} {symbol}")
            return jsonify({
                "status": "signal_received",
                "symbol": symbol,
                "action": action,
                "mode": get_mode()
            })

        return jsonify({"status": "acknowledged"})

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/webhook/tradingview', methods=['POST'])
def webhook_tradingview():
    """
    TradingView webhook with TradingAgents analysis.
    """
    try:
        data = request.get_json()
        symbol = data.get('symbol', '')
        quantity = data.get('quantity', 1)

        # Run TradingAgents analysis
        decision, confidence, details = tradingagents.analyze_and_decide(symbol)

        logger.info(f"Analysis result: {decision} (confidence: {confidence})")

        # Check if should execute
        should_exec, reason = tradingagents.should_execute(decision, confidence)

        if should_exec:
            # Execute via T212
            if execution_layer is None:
                init_t212_client()
                
            logger.info(f"Executing {decision} for {symbol} via T212")
            order_result = execution_layer.execute_order(OrderRequest(
                symbol=symbol,
                action=decision.lower(),
                quantity=quantity,
                order_type="market",
                instrument_type="equity"
            ))
            return jsonify({
                "status": "executed",
                "symbol": symbol,
                "decision": decision,
                "confidence": confidence,
                "order_result": order_result,
                "mode": get_mode()
            })
        else:
            return jsonify({
                "status": "skipped",
                "symbol": symbol,
                "decision": decision,
                "confidence": confidence,
                "reason": reason,
                "mode": get_mode()
            })

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/analyze/<symbol>', methods=['GET'])
def analyze_symbol(symbol: str):
    """
    Direct analysis endpoint - run TradingAgents without webhook.
    """
    try:
        decision, confidence, details = tradingagents.analyze_and_decide(symbol)
        should_exec, reason = tradingagents.should_execute(decision, confidence)

        return jsonify({
            "symbol": symbol,
            "decision": decision,
            "confidence": confidence,
            "details": details,
            "would_execute": should_exec,
            "reason": reason,
            "auto_execute": tradingagents.auto_execute
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/chat', methods=['POST'])
def chat_with_ai():
    """
    Chat with the AI about trading analysis.
    """
    try:
        data = request.json
        message = data.get('message', '').strip()
        symbol = data.get('symbol', '').strip()

        if not message:
            return jsonify({"error": "Message is required"}), 400

        # If symbol provided, run TradingAgents analysis first
        analysis = None
        if symbol:
            decision, confidence, details = tradingagents.analyze_and_decide(symbol)
            should_exec, reason = tradingagents.should_execute(decision, confidence)
            analysis = {
                "symbol": symbol,
                "decision": decision,
                "confidence": confidence,
                "details": details,
                "would_execute": should_exec,
                "reason": reason
            }

        # Build AI response
        if symbol and analysis:
            response = (
                f"I've analyzed {symbol} for you. "
                f"My recommendation is **{analysis['decision']}** with {analysis['confidence']:.0%} confidence. "
            )
            if analysis['decision'] in ['BUY', 'SELL']:
                if analysis['would_execute']:
                    response += f"This signal would {'automatically execute' if tradingagents.auto_execute else 'be queued for manual review'}. "
                else:
                    response += f"However, it won't execute because: {analysis['reason']}. "
        else:
            response = (
                "I'm your trading assistant. I can help you analyze stocks, "
                "explain trading signals, and discuss market trends. "
            )

        return jsonify({
            "response": response,
            "analysis": analysis,
            "symbol": symbol or None
        })
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/chat/stream', methods=['GET'])
def chat_stream_reasoning():
    """
    Stream agent reasoning continuously for a symbol.
    Uses SSE (Server-Sent Events) to stream intermediate steps forever.
    """
    from flask import Response
    import json

    try:
        symbol = (request.args.get('symbol') or '').strip().upper()

        if not symbol:
            return jsonify({"error": "Symbol is required"}), 400

        logger.info(f"Streaming reasoning continuously for {symbol}")

        def generate():
            last_keepalive = time.time()
            try:
                for step in tradingagents.stream_reasoning(symbol):
                    # Format timestamp
                    step['time'] = time.strftime('%H:%M:%S', time.localtime(step['timestamp']))
                    # Send as SSE
                    yield f"data: {json.dumps(step)}\n\n"
                    # Send keepalive comment every ~15s
                    now = time.time()
                    if now - last_keepalive > 15:
                        yield ": keepalive\n\n"
                        last_keepalive = now
            except GeneratorExit:
                logger.info(f"Stream client disconnected for {symbol}")

        return Response(
            generate(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive'
            }
        )
    except Exception as e:
        logger.error(f"Stream error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "mode": get_mode(),
        "t212_configured": bool(config.get_t212_credentials()[0])
    })

@app.route('/monitor', methods=['GET'])
def monitor_status():
    """Get monitor status and recent alerts"""
    monitor = get_monitor()
    status = monitor.get_status()
    status["strategies"] = STRATEGIES
    status["watchlist"] = LSE_WATCHLIST
    return jsonify(status)

@app.route('/monitor/start', methods=['POST'])
def monitor_start():
    """Start the stock monitor"""
    monitor = get_monitor()
    if not monitor.running:
        monitor.start()
        logger.info("Monitor started via API")
    return jsonify({"status": "started", "running": monitor.running})

@app.route('/monitor/stop', methods=['POST'])
def monitor_stop():
    """Stop the stock monitor"""
    monitor = get_monitor()
    if monitor.running:
        monitor.stop()
        logger.info("Monitor stopped via API")
    return jsonify({"status": "stopped", "running": monitor.running})

@app.route('/api/emergency/sell-all', methods=['POST'])
def emergency_sell_all():
    """Emergency: sell ALL open positions at market price immediately."""
    from t212_client import T212Client
    from position_tracker import get_tracker
    try:
        tracker = get_tracker()
        client = T212Client()
        positions = tracker.fetch_positions()
        sold = []
        for pos in positions:
            if pos.quantity > 0:
                try:
                    result = client.place_order(
                        instrument_code=pos.symbol,
                        quantity=int(pos.quantity),
                        order_type="market",
                        side="sell"
                    )
                    from telegram_alerts import send_telegram_alert
                    send_telegram_alert(f"EMERGENCY SELL: {pos.symbol} — {int(pos.quantity)} shares @ market")
                    sold.append({"symbol": pos.symbol, "qty": int(pos.quantity), "price": "market"})
                    logger.warning(f"EMERGENCY SELL executed: {pos.symbol} x {pos.quantity}")
                except Exception as e:
                    logger.error(f"Emergency sell failed for {pos.symbol}: {e}")
                    send_telegram_alert(f"❌ EMERGENCY SELL FAILED: {pos.symbol} — {e}")
        return jsonify({"status": "executed", "sold": sold})
    except Exception as e:
        logger.error(f"Emergency sell-all failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/emergency/stop-trading', methods=['POST'])
def emergency_stop_trading():
    """Stop the monitor loop and block all trading."""
    from telegram_alerts import send_telegram_alert
    try:
        monitor = get_monitor()
        if monitor.running:
            monitor.stop()
        send_telegram_alert("🛑 TRADING STOPPED — Emergency stop triggered by user")
        return jsonify({"status": "stopped", "message": "Monitor stopped"})
    except Exception as e:
        logger.error(f"Emergency stop failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/monitor/check', methods=['POST'])
def monitor_check():
    """Trigger immediate check of all stocks"""
    monitor = get_monitor()
    alerts = monitor.check_all_stocks()
    return jsonify({
        "status": "checked",
        "alerts_triggered": len(alerts),
        "alerts": [
            {
                "timestamp": a.timestamp.isoformat(),
                "symbol": a.symbol,
                "strategy": a.strategy_name,
                "priority": a.priority,
                "message": a.message
            }
            for a in alerts
        ]
    })

@app.route('/api/positions', methods=['GET'])
def get_positions():
    """Get open positions and PnL summary from position tracker"""
    try:
        tracker = get_tracker()
        summary = tracker.get_summary()

        return jsonify({
            "status": "success",
            "positions": [p.to_dict() for p in summary.positions],
            "count": summary.position_count,
            "totalPnL": summary.total_pnl,
            "totalFees": summary.total_fees,
            "netPnL": summary.net_pnl,
            "totalExposure": summary.total_exposure,
            "todayCount": summary.today_count,
            "dailyPnL": summary.daily_pnl,
            "weeklyPnL": summary.weekly_pnl,
            "monthlyPnL": summary.monthly_pnl,
            "yearlyPnL": summary.yearly_pnl,
            "allTimePnL": summary.all_time_pnl,
        })
    except Exception as e:
        logger.error(f"Failed to get positions: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/positions/diversification', methods=['GET'])
def get_diversification():
    """Get portfolio diversification breakdown"""
    try:
        tracker = get_tracker()
        return jsonify({"status": "success", **tracker.get_diversification()})
    except Exception as e:
        logger.error(f"Failed to get diversification: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/positions/changes', methods=['GET'])
def get_position_changes():
    """Detect recently opened/closed positions"""
    try:
        tracker = get_tracker()
        return jsonify({"status": "success", **tracker.detect_changes()})
    except Exception as e:
        logger.error(f"Failed to detect changes: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/settings/max-trades', methods=['POST'])
def set_max_trades():
    """Set max open trades limit"""
    try:
        data = request.json
        max_trades = int(data.get('max_open_trades', 10))
        from execution_rules import ExecutionRules
        ExecutionRules.set_max_open_trades(max_trades)
        return jsonify({"status": "success", "max_open_trades": max_trades})
    except Exception as e:
        logger.error(f"Failed to set max trades: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/settings/auto-close', methods=['POST'])
def set_auto_close():
    """Enable/disable auto-close before market close"""
    try:
        data = request.json
        enabled = bool(data.get('auto_close', False))
        from monitor import get_monitor
        monitor = get_monitor()
        monitor.auto_close_before_market_close = enabled
        return jsonify({"status": "success", "auto_close": enabled})
    except Exception as e:
        logger.error(f"Failed to set auto-close: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/orders', methods=['GET'])
def get_orders():
    """Get order history from T212"""
    global t212_client
    try:
        if t212_client is None:
            init_t212_client()
        orders = t212_client.get_order_history()
        return jsonify({
            "status": "success",
            "orders": orders,
            "count": len(orders)
        })
    except Exception as e:
        logger.error(f"Failed to get orders: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/news/<symbol>', methods=['GET'])
def get_symbol_news(symbol: str):
    """
    Get news and sentiment for a specific symbol.
    """
    try:
        from monitor import get_monitor
        monitor = get_monitor()
        news_items = monitor._fetch_news_for_symbol(symbol)

        sentiment_data = None
        if news_items and HAS_NEWS_SENTIMENT:
            # Check cache first
            if symbol in monitor.sentiment_cache:
                sentiment = monitor.sentiment_cache[symbol]
            else:
                from news_sentiment import get_sentiment_analyzer
                analyzer = get_sentiment_analyzer()
                sentiment = analyzer.analyze_news(news_items)
                monitor.sentiment_cache[symbol] = sentiment
            
            sentiment_data = {
                "sentiment": sentiment.sentiment,
                "confidence": sentiment.confidence,
                "summary": sentiment.summary,
                "key_themes": sentiment.key_themes,
                "relevant_tickers": sentiment.relevant_tickers,
                "provider": sentiment.provider
            }

        return jsonify({
            "symbol": symbol,
            "news_count": len(news_items) if news_items else 0,
            "news": news_items[:10] if news_items else [],
            "sentiment": sentiment_data,
            "news_sentiment_enabled": HAS_NEWS_SENTIMENT
        })
    except Exception as e:
        logger.error(f"News fetch error for {symbol}: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Initialize T212 client
    init_t212_client()

    # Set initial runtime mode from config
    RUNTIME_MODE = config.T212_MODE

    # Log mode reminder
    if get_mode() == "demo":
        print("="*60)
        print("T212 DEMO MODE ACTIVE")
        print("="*60 + "\n")
    else:
        print("\n" + "="*60)
        print("T212 LIVE MODE ACTIVE")
        print("REAL MONEY IS AT RISK!")
        print("="*60 + "\n")

    app.run(host='0.0.0.0', port=5000, debug=False)
