"""
Professional BTCUSDT signal engine.

Combines: EMA trend, RSI, volume, ATR, structure, candles, news, risk levels.
Outputs: STRONG BUY | BUY | WAIT | SELL | STRONG SELL
"""

from __future__ import annotations

import pandas as pd

import config
from backtest import record_signal
from candle_patterns import is_bearish_reversal, is_bullish_reversal, summarize_row
from market_structure import summarize_structure
from models import TradingSignal
from news_sentiment import analyze_news, news_aligns_with_action, news_conflict
from risk_levels import compute_trade_levels


def _f(row: pd.Series, key: str, default: float = 0.0) -> float:
    v = row.get(key, default)
    return default if pd.isna(v) else float(v)


def _b(row: pd.Series, key: str) -> bool:
    return bool(row.get(key, False))


def _volume_spike(row: pd.Series) -> bool:
    return _f(row, "volume_ratio") >= config.VOLUME_SPIKE_MULTIPLIER


def _score_side(row: pd.Series, side: str, structure: dict, candle: dict) -> tuple[float, dict[str, bool]]:
    """Weighted checklist for bull or bear side."""
    rsi = _f(row, "rsi")
    trend_str = _f(row, "trend_strength")

    if side == "bull":
        checks = {
            "EMA uptrend": _b(row, "trend_bull"),
            "RSI zone": config.RSI_BULL_MIN <= rsi <= config.RSI_BULL_MAX,
            "Volume": _volume_spike(row),
            "Trend strength": trend_str >= config.TREND_STRENGTH_MIN,
            "Structure": structure["market_state"] in (
                "trend_continuation_bull",
                "bull_pullback_retest",
                "oversold_bounce_setup",
                "panic_dump_oversold",
            ),
            "Candle confirms": candle["confirms_buy"],
            "No fake trap": not _b(row, "fake_breakout") or row.get("fake_trap_type") == "bear_trap",
        }
        weights = [
            config.WEIGHT_EMA,
            config.WEIGHT_RSI,
            config.WEIGHT_VOLUME,
            config.WEIGHT_TREND,
            config.WEIGHT_STRUCTURE,
            config.WEIGHT_CANDLE,
            config.WEIGHT_NO_FAKE,
        ]
        strength = candle["bull_score"]
    else:
        checks = {
            "EMA downtrend": _b(row, "trend_bear"),
            "RSI zone": config.RSI_BEAR_MIN <= rsi <= config.RSI_BEAR_MAX,
            "Volume": _volume_spike(row),
            "Trend strength": trend_str >= config.TREND_STRENGTH_MIN,
            "Structure": structure["market_state"] in (
                "trend_continuation_bear",
                "bear_pullback_retest",
                "overbought_rejection_setup",
                "overbought_extension",
            ),
            "Candle confirms": candle["confirms_sell"],
            "No fake trap": not _b(row, "fake_breakout") or row.get("fake_trap_type") == "bull_trap",
        }
        weights = [
            config.WEIGHT_EMA,
            config.WEIGHT_RSI,
            config.WEIGHT_VOLUME,
            config.WEIGHT_TREND,
            config.WEIGHT_STRUCTURE,
            config.WEIGHT_CANDLE,
            config.WEIGHT_NO_FAKE,
        ]
        strength = candle["bear_score"]

    earned = sum(w for c, w in zip(checks.values(), weights) if c)
    base = earned / sum(weights) * 100

    candle_bonus = min(12, (strength / config.PATTERN_SCORE_MAX) * 12)
    if checks.get("Candle confirms"):
        base += candle_bonus
    elif strength >= 30:
        base -= 6

    return round(min(100, max(0, base)), 1), checks


def _apply_news(score: float, action_side: str, news: dict) -> tuple[float, bool]:
    sentiment = news["sentiment"]
    aligned = news_aligns_with_action(sentiment, action_side)
    conflict = news_conflict(sentiment, action_side)
    if conflict:
        score = max(0, score - config.NEWS_CONFLICT_PENALTY)
    elif aligned and sentiment != "neutral":
        score = min(100, score + config.WEIGHT_NEWS)
    return score, conflict


def _classify_action(side: str, score: float) -> str:
    if side == "bull":
        if score >= config.CONFIDENCE_STRONG:
            return "STRONG BUY"
        if score >= config.CONFIDENCE_TRADE:
            return "BUY"
    else:
        if score >= config.CONFIDENCE_STRONG:
            return "STRONG SELL"
        if score >= config.CONFIDENCE_TRADE:
            return "SELL"
    return "WAIT"


def _wait_explanation(
    row: pd.Series,
    structure: dict,
    bull_score: float,
    bear_score: float,
    blocks: list[str],
) -> str:
    rsi = _f(row, "rsi")
    parts: list[str] = []

    if rsi < config.RSI_EXTREME_OVERSOLD:
        parts.append("Extreme oversold — bounce possible, avoid fresh shorts")
    elif rsi > config.RSI_EXTREME_OVERBOUGHT:
        parts.append("Extreme overbought — avoid fresh longs")
    elif structure["market_state"] == "range_chop":
        parts.append("Choppy range — wait for breakout + retest")
    elif structure["market_state"] == "panic_dump":
        parts.append("Post-dump consolidation — wait for confirmation")
    elif bull_score > bear_score:
        parts.append("Mild bullish bias but setup incomplete")
    elif bear_score > bull_score:
        parts.append("Mild bearish bias but setup incomplete")
    else:
        parts.append("Mixed signals — no edge")

    if structure["late_entry_warning"]:
        parts.append(structure["late_entry_warning"])
    if blocks:
        parts.append(blocks[0])
    return " · ".join(parts[:3])


def _fake_breakout_details(row: pd.Series, candle: dict) -> str:
    if not candle["fake_breakout"]:
        return ""
    trap = candle.get("fake_trap_type", "")
    vol = _f(row, "volume_ratio")
    parts = [f"Trap: {trap}" if trap else "Wick rejection at key level"]
    if vol < config.VOLUME_SPIKE_MULTIPLIER:
        parts.append("breakout lacked volume")
    return " · ".join(parts)


def analyze(df: pd.DataFrame) -> TradingSignal:
    row = df.iloc[-1]
    price = _f(row, "close")
    candle = summarize_row(row)
    structure = summarize_structure(row)
    news = analyze_news()

    bull_score, bull_checks = _score_side(row, "bull", structure, candle)
    bear_score, bear_checks = _score_side(row, "bear", structure, candle)

    bull_score, bull_news_conflict = _apply_news(bull_score, "BUY", news)
    bear_score, bear_news_conflict = _apply_news(bear_score, "SELL", news)

    blocks: list[str] = []
    block_sell_rev = _f(row, "rsi") < config.RSI_OVERSOLD and is_bullish_reversal(row)
    block_buy_rev = _f(row, "rsi") > config.RSI_OVERBOUGHT and is_bearish_reversal(row)

    if block_sell_rev:
        blocks.append("Blocked SELL — oversold + bullish reversal candle")
    if block_buy_rev:
        blocks.append("Blocked BUY — overbought + bearish reversal candle")

    if _f(row, "rsi") < config.RSI_EXTREME_OVERSOLD and not structure["strong_bear_continuation"]:
        blocks.append("Extreme oversold — no fresh SELL without continuation")
        bear_score = min(bear_score, config.CONFIDENCE_TRADE - 5)

    if _f(row, "rsi") > config.RSI_EXTREME_OVERBOUGHT and not structure["strong_bull_continuation"]:
        blocks.append("Extreme overbought — no fresh BUY without continuation")
        bull_score = min(bull_score, config.CONFIDENCE_TRADE - 5)

    if structure["block_late_sell"]:
        blocks.append("Late entry — do not chase dump")
        bear_score = min(bear_score, 55)

    if structure["block_late_buy"]:
        blocks.append("Late entry — do not chase pump")
        bull_score = min(bull_score, 55)

    can_bull = (
        bull_score >= config.CONFIDENCE_TRADE
        and bull_score > bear_score + 5
        and bull_checks["Candle confirms"]
        and not block_buy_rev
        and not structure["block_late_buy"]
    )
    can_bear = (
        bear_score >= config.CONFIDENCE_TRADE
        and bear_score > bull_score + 5
        and bear_checks["Candle confirms"]
        and not block_sell_rev
        and not structure["block_late_sell"]
    )

    action = "WAIT"
    confidence = max(bull_score, bear_score)
    checks = bull_checks
    news_conf = bull_news_conflict or bear_news_conflict

    if can_bull:
        action = _classify_action("bull", bull_score)
        confidence = bull_score
        checks = bull_checks
        news_conf = bull_news_conflict
    elif can_bear:
        action = _classify_action("bear", bear_score)
        confidence = bear_score
        checks = bear_checks
        news_conf = bear_news_conflict

    if news_conf and action != "WAIT":
        if confidence < config.CONFIDENCE_STRONG:
            action = "WAIT"
            blocks.append(f"News ({news['sentiment']}) conflicts with chart — standing aside")

    wait_explanation = ""
    if action == "WAIT":
        wait_explanation = _wait_explanation(row, structure, bull_score, bear_score, blocks)
        entry = stop_loss = take_profit = rr = None
    else:
        entry, stop_loss, take_profit, rr = compute_trade_levels(row, action, price)

    reasons: list[str] = []
    for name, ok in checks.items():
        reasons.append(f"{name}: {'✓' if ok else '✗'}")
    if candle["reason"]:
        reasons.append(f"Candles: {candle['reason']}")
    if structure["market_state"]:
        reasons.append(f"Market: {structure['market_state'].replace('_', ' ')}")
    if news["headlines"]:
        reasons.append(f"News: {news['sentiment']} ({news['score']:+.0f})")
    for b in blocks:
        reasons.append(b)
    if wait_explanation and action == "WAIT":
        reasons.append(wait_explanation)

    reason = f"{action} — " + " | ".join(reasons[:6])

    signal = TradingSignal(
        action=action,
        confidence_pct=round(confidence, 1),
        reason=reason,
        reasons=reasons,
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward=rr,
        price=round(price, 2),
        ema_fast=round(_f(row, "ema_fast"), 2),
        ema_slow=round(_f(row, "ema_slow"), 2),
        rsi=round(_f(row, "rsi"), 2),
        atr=round(_f(row, "atr"), 2),
        atr_pct=round(_f(row, "atr_pct"), 3),
        volume_ratio=round(_f(row, "volume_ratio"), 2),
        trend_strength=round(_f(row, "trend_strength"), 3),
        support=round(_f(row, "support"), 2),
        resistance=round(_f(row, "resistance"), 2),
        swing_high=round(_f(row, "swing_high"), 2),
        swing_low=round(_f(row, "swing_low"), 2),
        market_state=structure["market_state"],
        late_entry_risk=structure["late_entry_risk"],
        late_entry_warning=structure["late_entry_warning"],
        wait_explanation=wait_explanation,
        fake_breakout=candle["fake_breakout"],
        fake_trap_type=candle.get("fake_trap_type", ""),
        fake_breakout_details=_fake_breakout_details(row, candle),
        candle_patterns=candle["patterns"],
        candle_reason=candle["reason"],
        candle_strength=candle["strength"],
        candle_confirms_buy=candle["confirms_buy"],
        candle_confirms_sell=candle["confirms_sell"],
        news_sentiment=news["sentiment"],
        news_score=news["score"],
        news_headlines=news["headlines"],
        news_conflict=news_conf,
        block_buy_reversal=block_buy_rev,
        block_sell_reversal=block_sell_rev,
    )

    record_signal(signal, price)
    return signal


def run_analysis() -> TradingSignal:
    from binance_client import fetch_klines
    from indicators import enrich_dataframe

    df = fetch_klines()
    df = enrich_dataframe(df)
    return analyze(df)
