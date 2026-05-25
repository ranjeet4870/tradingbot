"""
Paper trading / signal history — last 20 signals with win-loss tracking.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import pandas as pd

import config


def _ensure_data_dir() -> None:
    folder = os.path.dirname(config.SIGNAL_HISTORY_FILE)
    if folder:
        os.makedirs(folder, exist_ok=True)


def _load_history() -> list[dict]:
    _ensure_data_dir()
    if not os.path.exists(config.SIGNAL_HISTORY_FILE):
        return []
    try:
        with open(config.SIGNAL_HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_history(records: list[dict]) -> None:
    _ensure_data_dir()
    with open(config.SIGNAL_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(records[-config.SIGNAL_HISTORY_MAX :], f, indent=2)


def _evaluate_outcome(
    record: dict, current_price: float
) -> dict:
    """Mark win/loss for closed paper trades using current price."""
    action = record.get("action", "WAIT")
    if action == "WAIT" or record.get("outcome") not in (None, "open"):
        return record

    entry = record.get("entry")
    tp = record.get("take_profit")
    sl = record.get("stop_loss")
    if not entry or not tp or not sl:
        record["outcome"] = "no_levels"
        return record

    if "BUY" in action:
        if current_price >= tp:
            record["outcome"] = "win"
            record["exit_reason"] = "take_profit_hit"
        elif current_price <= sl:
            record["outcome"] = "loss"
            record["exit_reason"] = "stop_loss_hit"
        else:
            move_pct = (current_price - entry) / entry * 100
            record["move_pct"] = round(move_pct, 2)
    elif "SELL" in action:
        if current_price <= tp:
            record["outcome"] = "win"
            record["exit_reason"] = "take_profit_hit"
        elif current_price >= sl:
            record["outcome"] = "loss"
            record["exit_reason"] = "stop_loss_hit"
        else:
            move_pct = (entry - current_price) / entry * 100
            record["move_pct"] = round(move_pct, 2)

    return record


def record_signal(signal, current_price: float | None = None) -> None:
    """Append signal and update prior open paper trades."""
    if not config.PAPER_TRADING:
        return

    history = _load_history()
    price = current_price or signal.price

    for i, rec in enumerate(history):
        if rec.get("outcome") == "open":
            history[i] = _evaluate_outcome(rec, price)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": signal.action,
        "confidence": signal.confidence_pct,
        "price_at_signal": signal.price,
        "entry": signal.entry,
        "stop_loss": signal.stop_loss,
        "take_profit": signal.take_profit,
        "market_state": signal.market_state,
        "outcome": "open" if signal.action != "WAIT" else "wait",
        "move_pct": None,
        "exit_reason": None,
    }
    history.append(entry)
    _save_history(history)


def get_backtest_stats(current_price: float) -> dict[str, Any]:
    history = _load_history()
    updated = [_evaluate_outcome(dict(r), current_price) for r in history]
    _save_history(updated)

    trades = [r for r in updated if r.get("action", "WAIT") != "WAIT"]
    closed = [r for r in trades if r.get("outcome") in ("win", "loss")]
    wins = sum(1 for r in closed if r["outcome"] == "win")
    losses = sum(1 for r in closed if r["outcome"] == "loss")

    accuracy = round(wins / len(closed) * 100, 1) if closed else 0.0

    return {
        "paper_trading": config.PAPER_TRADING,
        "total_signals": len(updated),
        "trade_signals": len(trades),
        "closed_trades": len(closed),
        "wins": wins,
        "losses": losses,
        "accuracy_pct": accuracy,
        "last_signals": list(reversed(updated[-config.SIGNAL_HISTORY_MAX :])),
    }
