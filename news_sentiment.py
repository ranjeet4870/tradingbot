"""
Bitcoin news sentiment — free sources + keyword AI-style scoring.

Sources:
  - CryptoCompare news (no key required for basic feed)
  - Alternative.me Fear & Greed Index
  - Optional CryptoPanic if CRYPTOPANIC_TOKEN is set
"""

from __future__ import annotations

import re
import time
from typing import Any

import requests

import config

_CACHE: dict[str, Any] = {"ts": 0, "data": None}

BULLISH_KEYWORDS = [
    "etf approval",
    "etf approved",
    "institutional",
    "accumulation",
    "whale buy",
    "rate cut",
    "dovish",
    "adoption",
    "partnership",
    "bullish",
    "breakout",
    "all-time high",
    "ath",
    "inflow",
    "upgrade",
    "halving",
]
BEARISH_KEYWORDS = [
    "hack",
    "exploit",
    "sec sue",
    "lawsuit",
    "ban",
    "crash",
    "bearish",
    "outflow",
    "liquidation",
    "fed hike",
    "hawkish",
    "fear",
    "recession",
    "sell-off",
    "selloff",
    "dump",
    "fraud",
    "bankruptcy",
    "collapse",
]


def _score_text(text: str) -> float:
    t = text.lower()
    bull = sum(1 for k in BULLISH_KEYWORDS if k in t)
    bear = sum(1 for k in BEARISH_KEYWORDS if k in t)
    if bull == bear == 0:
        return 0.0
    return max(-100.0, min(100.0, (bull - bear) * 22))


def _fetch_fear_greed() -> tuple[float, str]:
    try:
        r = requests.get(config.FEAR_GREED_URL, timeout=12)
        r.raise_for_status()
        item = r.json()["data"][0]
        value = int(item["value"])
        label = item["value_classification"]
        if value >= 60:
            return min(100, (value - 50) * 2), f"Fear & Greed: {value} ({label}) — greed"
        if value <= 40:
            return max(-100, (value - 50) * 2), f"Fear & Greed: {value} ({label}) — fear"
        return 0, f"Fear & Greed: {value} ({label}) — neutral"
    except Exception:
        return 0.0, ""


def _fetch_cryptocompare_headlines(limit: int = 12) -> list[dict]:
    try:
        r = requests.get(
            config.CRYPTOCOMPARE_NEWS_URL,
            params={"lang": "EN", "categories": "BTC,Blockchain,Trading"},
            timeout=12,
        )
        r.raise_for_status()
        articles = r.json().get("Data", [])[:limit]
        out = []
        for a in articles:
            title = a.get("title", "")
            body = a.get("body", "")[:200]
            out.append({"title": title, "text": f"{title} {body}"})
        return out
    except Exception:
        return []


def _fetch_cryptopanic() -> list[dict]:
    if not config.CRYPTOPANIC_TOKEN:
        return []
    try:
        r = requests.get(
            config.CRYPTOPANIC_URL,
            params={
                "auth_token": config.CRYPTOPANIC_TOKEN,
                "currencies": "BTC",
                "filter": "hot",
                "public": "true",
            },
            timeout=12,
        )
        r.raise_for_status()
        return [
            {"title": p.get("title", ""), "text": p.get("title", "")}
            for p in r.json().get("results", [])[:10]
        ]
    except Exception:
        return []


def analyze_news() -> dict:
    """Return sentiment bundle (cached)."""
    now = time.time()
    if _CACHE["data"] and now - _CACHE["ts"] < config.NEWS_CACHE_SECONDS:
        return _CACHE["data"]

    headlines: list[str] = []
    scores: list[float] = []

    fg_score, fg_note = _fetch_fear_greed()
    if fg_note:
        headlines.append(fg_note)
        scores.append(fg_score * 0.35)

    for item in _fetch_cryptocompare_headlines() + _fetch_cryptopanic():
        title = item.get("title", "").strip()
        if not title:
            continue
        headlines.append(title[:120])
        scores.append(_score_text(item.get("text", title)))

    if scores:
        avg = sum(scores) / len(scores)
        if fg_score:
            avg = avg * 0.65 + fg_score * 0.35
    else:
        avg = fg_score

    if avg >= 18:
        sentiment = "bullish"
    elif avg <= -18:
        sentiment = "bearish"
    else:
        sentiment = "neutral"

    result = {
        "sentiment": sentiment,
        "score": round(avg, 1),
        "headlines": headlines[:8],
    }
    _CACHE["ts"] = now
    _CACHE["data"] = result
    return result


def news_aligns_with_action(sentiment: str, action: str) -> bool:
    if action in ("WAIT",):
        return True
    if "BUY" in action:
        return sentiment != "bearish"
    if "SELL" in action:
        return sentiment != "bullish"
    return True


def news_conflict(sentiment: str, action: str) -> bool:
    if action == "WAIT":
        return False
    if "BUY" in action and sentiment == "bearish":
        return True
    if "SELL" in action and sentiment == "bullish":
        return True
    return False
