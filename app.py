"""
Professional signal terminal — single source of truth for API + dashboard.

Engine: strategy.py + candle_patterns + market_structure + news_sentiment + risk_levels
"""

import threading
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template

import config
from backtest import get_backtest_stats
from market_data import get_last_provider
from strategy import run_analysis
from telegram_alerts import send_telegram_alert

ENGINE_VERSION = "pro-2.0"

app = Flask(__name__, template_folder="templates", static_folder="static")

_cache: dict = {"status": "loading", "symbol": config.SYMBOL, "engine_version": ENGINE_VERSION}
_cache_lock = threading.Lock()

# Fields only present in professional JSON (used to detect stale/legacy cache)
_PRO_KEYS = frozenset(
    {
        "engine_version",
        "market_state",
        "news_sentiment",
        "candle_patterns",
        "atr",
        "wait_explanation",
    }
)


def _signal_payload(signal) -> dict:
    data = signal.to_dict()
    data["engine_version"] = ENGINE_VERSION
    data["symbol"] = config.SYMBOL
    data["interval"] = config.INTERVAL
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["reasons"] = signal.reasons
    data["fake_breakout_alert"] = signal.fake_breakout
    data["fake_trap_type"] = signal.fake_trap_type
    data["paper_trading"] = config.PAPER_TRADING
    # Legacy alias for dashboards expecting confidence
    data["confidence"] = signal.confidence_pct
    return data


def _is_legacy_cache(data: dict) -> bool:
    if data.get("engine_version") != ENGINE_VERSION:
        return True
    if not _PRO_KEYS.issubset(data.keys()):
        return True
    # Old bot set equal levels on WAIT
    if data.get("action") == "WAIT":
        e, sl, tp = data.get("entry"), data.get("stop_loss"), data.get("take_profit")
        if e is not None and e == sl == tp:
            return True
    return False


def _refresh_cache() -> None:
    global _cache
    try:
        signal = run_analysis()
        payload = _signal_payload(signal)
        payload["status"] = "ok"
        payload["backtest"] = get_backtest_stats(signal.price)
        payload["data_provider"] = get_last_provider()
        payload["candle_source"] = f"{config.SYMBOL} {config.INTERVAL} via {get_last_provider()}"
        with _cache_lock:
            _cache = payload
        send_telegram_alert(payload)
    except Exception as exc:
        with _cache_lock:
            _cache = {
                "status": "error",
                "message": str(exc),
                "symbol": config.SYMBOL,
                "engine_version": ENGINE_VERSION,
            }


def _background_loop() -> None:
    while True:
        _refresh_cache()
        time.sleep(config.SCAN_INTERVAL_SECONDS)


def _start_background_refresh() -> None:
    threading.Thread(target=_background_loop, daemon=True, name="signal-refresh").start()


@app.route("/")
def dashboard():
    return render_template("index.html", symbol=config.SYMBOL, interval=config.INTERVAL)


@app.route("/signal")
def signal_json():
    with _cache_lock:
        data = dict(_cache)
    if _is_legacy_cache(data) or data.get("status") == "loading":
        _refresh_cache()
        with _cache_lock:
            data = dict(_cache)
    if data.get("status") == "error":
        return jsonify(data), 500
    return jsonify(data)


@app.route("/backtest")
def backtest_json():
    with _cache_lock:
        price = _cache.get("price", 0)
    return jsonify(get_backtest_stats(price))


@app.route("/health")
def health():
    with _cache_lock:
        provider = _cache.get("data_provider", get_last_provider())
        cache_status = _cache.get("status", "unknown")
    return jsonify({
        "status": "ok" if cache_status == "ok" else cache_status,
        "symbol": config.SYMBOL,
        "engine_version": ENGINE_VERSION,
        "data_provider": provider,
        "market_data": "bybit (no binance sdk)",
    })


# Prime cache before serving requests
_refresh_cache()
_start_background_refresh()


if __name__ == "__main__":
    print(f"Professional terminal ({ENGINE_VERSION}): http://127.0.0.1:{config.PORT}")
    app.run(host=config.HOST, port=config.PORT, debug=False)
