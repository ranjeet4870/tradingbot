"""
Telegram alerts when a new trading signal is generated.

Set in Railway / .env:
  TELEGRAM_BOT_TOKEN=...
  TELEGRAM_CHAT_ID=...
  TELEGRAM_ALERTS=true
"""

from __future__ import annotations

import logging
import requests

import config

logger = logging.getLogger(__name__)

_last_sent_action: str | None = None


def _enabled() -> bool:
    return (
        config.TELEGRAM_ALERTS
        and bool(config.TELEGRAM_BOT_TOKEN)
        and bool(config.TELEGRAM_CHAT_ID)
    )


def format_alert(payload: dict) -> str:
    action = payload.get("action", "WAIT")
    conf = payload.get("confidence_pct", payload.get("confidence", 0))
    price = payload.get("price", 0)
    state = (payload.get("market_state") or "").replace("_", " ")
    news = payload.get("news_sentiment", "neutral")

    lines = [
        f"BTCUSDT Signal ({config.INTERVAL})",
        f"Action: {action}",
        f"Confidence: {conf}%",
        f"Price: ${price:,.2f}",
        f"Market: {state}",
        f"News: {news}",
    ]

    if action != "WAIT":
        lines += [
            f"Entry: ${payload.get('entry', 0):,.2f}",
            f"SL: ${payload.get('stop_loss', 0):,.2f}",
            f"TP: ${payload.get('take_profit', 0):,.2f}",
        ]
    elif payload.get("wait_explanation"):
        lines.append(payload["wait_explanation"][:200])

    patterns = payload.get("candle_patterns") or []
    if patterns:
        lines.append("Candles: " + ", ".join(patterns[:4]))

    return "\n".join(lines)


def send_telegram_alert(payload: dict, force: bool = False) -> bool:
    """Send Telegram message on new action (or if force=True)."""
    global _last_sent_action

    if not _enabled():
        return False

    action = payload.get("action", "WAIT")
    if not force and action == _last_sent_action:
        return False

    text = format_alert(payload)
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"

    try:
        r = requests.post(
            url,
            json={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        r.raise_for_status()
        _last_sent_action = action
        logger.info("Telegram alert sent: %s", action)
        return True
    except Exception as exc:
        logger.error("Telegram alert failed: %s", exc)
        return False
