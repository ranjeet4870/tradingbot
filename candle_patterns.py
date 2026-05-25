"""
Advanced candle pattern detection for signal confirmation.

Detects classic price-action structures on OHLCV bars and scores
bullish vs bearish candle bias for the strategy engine.
"""

from __future__ import annotations

import pandas as pd

import config


# --- Candle anatomy helpers ---


def _body(o: float, c: float) -> float:
    return abs(c - o)


def _upper_wick(o: float, h: float, c: float) -> float:
    return h - max(o, c)


def _lower_wick(o: float, l: float, c: float) -> float:
    return min(o, c) - l


def _range(h: float, l: float) -> float:
    return max(h - l, 1e-10)


def _is_bullish(o: float, c: float) -> bool:
    return c > o


def _is_bearish(o: float, c: float) -> bool:
    return c < o


def _row_anatomy(row: pd.Series) -> dict:
    o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
    rng = _range(h, l)
    body = _body(o, c)
    return {
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "range": rng,
        "body": body,
        "body_ratio": body / rng,
        "upper_wick": _upper_wick(o, h, c),
        "lower_wick": _lower_wick(o, l, c),
        "upper_wick_ratio": _upper_wick(o, h, c) / rng,
        "lower_wick_ratio": _lower_wick(o, l, c) / rng,
        "bullish": _is_bullish(o, c),
        "bearish": _is_bearish(o, c),
    }


# --- Single-candle patterns ---


def _is_doji(a: dict) -> bool:
    return a["body_ratio"] <= config.DOJI_BODY_RATIO


def _is_hammer(a: dict) -> bool:
    if a["body_ratio"] > config.HAMMER_MAX_BODY_RATIO:
        return False
    # Long lower wick, small upper wick
    return (
        a["lower_wick_ratio"] >= config.HAMMER_WICK_RATIO
        and a["upper_wick_ratio"] <= config.HAMMER_OPPOSITE_WICK_MAX
    )


def _is_shooting_star(a: dict) -> bool:
    if a["body_ratio"] > config.HAMMER_MAX_BODY_RATIO:
        return False
    return (
        a["upper_wick_ratio"] >= config.HAMMER_WICK_RATIO
        and a["lower_wick_ratio"] <= config.HAMMER_OPPOSITE_WICK_MAX
    )


def _is_strong_breakout_bull(row: pd.Series, a: dict) -> bool:
    swing_high = row.get("swing_high")
    if pd.isna(swing_high):
        return False
    return (
        a["close"] > swing_high * (1 + config.BREAKOUT_PIERCE_PCT)
        and a["body_ratio"] >= config.STRONG_BODY_RATIO
        and a["bullish"]
    )


def _is_strong_breakout_bear(row: pd.Series, a: dict) -> bool:
    swing_low = row.get("swing_low")
    if pd.isna(swing_low):
        return False
    return (
        a["close"] < swing_low * (1 - config.BREAKOUT_PIERCE_PCT)
        and a["body_ratio"] >= config.STRONG_BODY_RATIO
        and a["bearish"]
    )


def _is_bullish_rejection(row: pd.Series, a: dict) -> bool:
    """Long lower wick rejecting support — buyers stepped in."""
    swing_low = row.get("swing_low")
    if pd.isna(swing_low):
        return False
    pierced = a["low"] < swing_low * (1 - config.BREAKOUT_PIERCE_PCT)
    rejected = a["close"] > swing_low and a["lower_wick_ratio"] >= config.REJECTION_WICK_RATIO
    return pierced and rejected


def _is_bearish_rejection(row: pd.Series, a: dict) -> bool:
    """Long upper wick rejecting resistance — sellers stepped in."""
    swing_high = row.get("swing_high")
    if pd.isna(swing_high):
        return False
    pierced = a["high"] > swing_high * (1 + config.BREAKOUT_PIERCE_PCT)
    rejected = a["close"] < swing_high and a["upper_wick_ratio"] >= config.REJECTION_WICK_RATIO
    return pierced and rejected


def _is_liquidity_sweep_bull(row: pd.Series, a: dict) -> bool:
    """
    Liquidity sweep (bullish): wick grabs lows below swing support, close reclaims.
    Classic stop-hunt then reversal.
    """
    swing_low = row.get("swing_low")
    if pd.isna(swing_low):
        return False
    return (
        a["low"] < swing_low * (1 - config.LIQUIDITY_SWEEP_PIERCE_PCT)
        and a["close"] > swing_low
        and a["lower_wick_ratio"] >= config.LIQUIDITY_SWEEP_WICK_RATIO
    )


def _is_liquidity_sweep_bear(row: pd.Series, a: dict) -> bool:
    swing_high = row.get("swing_high")
    if pd.isna(swing_high):
        return False
    return (
        a["high"] > swing_high * (1 + config.LIQUIDITY_SWEEP_PIERCE_PCT)
        and a["close"] < swing_high
        and a["upper_wick_ratio"] >= config.LIQUIDITY_SWEEP_WICK_RATIO
    )


# --- Two-candle patterns ---


def _is_bullish_engulfing(prev: dict, curr: dict) -> bool:
    if not prev["bearish"] or not curr["bullish"]:
        return False
    return curr["open"] <= prev["close"] and curr["close"] >= prev["open"]


def _is_bearish_engulfing(prev: dict, curr: dict) -> bool:
    if not prev["bullish"] or not curr["bearish"]:
        return False
    return curr["open"] >= prev["close"] and curr["close"] <= prev["open"]


# --- Wick-enhanced fake breakout ---


def detect_fake_breakout_wick(row: pd.Series, a: dict) -> tuple[bool, str]:
    """
  Fake breakout / liquidity grab:
    - Wick pierce + close back inside
    - Weak body breakout without volume
    - Immediate reversal after pierce
    """
    swing_high = row.get("swing_high")
    swing_low = row.get("swing_low")
    if pd.isna(swing_high) or pd.isna(swing_low):
        return False, ""

    pierce = config.BREAKOUT_PIERCE_PCT
    vol_ratio = row.get("volume_ratio")
    low_volume = pd.isna(vol_ratio) or float(vol_ratio) < config.VOLUME_SPIKE_MULTIPLIER
    weak_body = a["body_ratio"] < config.STRONG_BODY_RATIO * 0.85

    if (
        a["high"] > swing_high * (1 + pierce)
        and a["close"] < swing_high
        and a["upper_wick_ratio"] >= config.FAKE_BREAKOUT_WICK_RATIO
    ):
        return True, "bull_trap"

    if (
        a["low"] < swing_low * (1 - pierce)
        and a["close"] > swing_low
        and a["lower_wick_ratio"] >= config.FAKE_BREAKOUT_WICK_RATIO
    ):
        return True, "bear_trap"

    if (
        a["high"] > swing_high * (1 + pierce)
        and a["close"] < swing_high
        and (low_volume or weak_body)
    ):
        return True, "weak_breakout_up"

    if (
        a["low"] < swing_low * (1 - pierce)
        and a["close"] > swing_low
        and (low_volume or weak_body)
    ):
        return True, "weak_breakout_down"

    return False, ""


def _patterns_for_bar(df: pd.DataFrame, idx: int) -> dict:
    """Detect all patterns on bar at index idx (needs prior bar for engulfing)."""
    row = df.iloc[idx]
    a = _row_anatomy(row)

    patterns: list[str] = []
    bull_score = 0.0
    bear_score = 0.0

    def add(name: str, bull: float = 0, bear: float = 0) -> None:
        nonlocal bull_score, bear_score
        patterns.append(name)
        bull_score += bull
        bear_score += bear

    if _is_doji(a):
        add("Doji", 0, 0)

    if _is_hammer(a):
        add("Hammer", config.PATTERN_SCORE_HAMMER, 0)

    if _is_shooting_star(a):
        add("Shooting star", 0, config.PATTERN_SCORE_HAMMER)

    if _is_bullish_rejection(row, a):
        add("Bullish rejection wick", config.PATTERN_SCORE_REJECTION, 0)

    if _is_bearish_rejection(row, a):
        add("Bearish rejection wick", 0, config.PATTERN_SCORE_REJECTION)

    if _is_liquidity_sweep_bull(row, a):
        add("Liquidity sweep (bullish)", config.PATTERN_SCORE_LIQUIDITY, 0)

    if _is_liquidity_sweep_bear(row, a):
        add("Liquidity sweep (bearish)", 0, config.PATTERN_SCORE_LIQUIDITY)

    if _is_strong_breakout_bull(row, a):
        add("Strong bullish breakout", config.PATTERN_SCORE_BREAKOUT, 0)

    if _is_strong_breakout_bear(row, a):
        add("Strong bearish breakout", 0, config.PATTERN_SCORE_BREAKOUT)

    if idx >= 1:
        prev = _row_anatomy(df.iloc[idx - 1])
        if _is_bullish_engulfing(prev, a):
            add("Bullish engulfing", config.PATTERN_SCORE_ENGULFING, 0)
        if _is_bearish_engulfing(prev, a):
            add("Bearish engulfing", 0, config.PATTERN_SCORE_ENGULFING)

    is_fake, trap = detect_fake_breakout_wick(row, a)
    if is_fake:
        patterns.append(f"Fake breakout ({trap})")
        if trap == "bear_trap":
            bull_score += config.PATTERN_SCORE_FAKE_TRAP
        elif trap == "bull_trap":
            bear_score += config.PATTERN_SCORE_FAKE_TRAP

    return {
        "patterns": patterns,
        "bull_score": bull_score,
        "bear_score": bear_score,
        "anatomy": a,
        "fake_breakout": is_fake,
        "fake_trap_type": trap,
    }


def enrich_candles(df: pd.DataFrame) -> pd.DataFrame:
    """Add pattern columns for every bar (strategy reads the last row)."""
    out = df.copy()
    n = len(out)

    pattern_lists: list[list] = []
    bull_scores: list[float] = []
    bear_scores: list[float] = []
    fake_flags: list[bool] = []
    fake_types: list[str] = []
    confirms_buy: list[bool] = []
    confirms_sell: list[bool] = []
    reasons: list[str] = []

    for i in range(n):
        if i < 1:
            pattern_lists.append([])
            bull_scores.append(0.0)
            bear_scores.append(0.0)
            fake_flags.append(False)
            fake_types.append("")
            confirms_buy.append(False)
            confirms_sell.append(False)
            reasons.append("")
            continue

        p = _patterns_for_bar(out, i)
        pattern_lists.append(p["patterns"])
        bull_scores.append(p["bull_score"])
        bear_scores.append(p["bear_score"])
        fake_flags.append(p["fake_breakout"])
        fake_types.append(p["fake_trap_type"])

        bullish_patterns = {
            "Bullish engulfing",
            "Hammer",
            "Strong bullish breakout",
            "Bullish rejection wick",
            "Liquidity sweep (bullish)",
        }
        bearish_patterns = {
            "Bearish engulfing",
            "Shooting star",
            "Strong bearish breakout",
            "Bearish rejection wick",
            "Liquidity sweep (bearish)",
        }
        names = set(p["patterns"])
        cb = bool(names & bullish_patterns) or (
            p["bull_score"] > p["bear_score"] and p["bull_score"] >= config.MIN_CANDLE_SCORE_CONFIRM
        )
        cs = bool(names & bearish_patterns) or (
            p["bear_score"] > p["bull_score"] and p["bear_score"] >= config.MIN_CANDLE_SCORE_CONFIRM
        )
        confirms_buy.append(cb)
        confirms_sell.append(cs)

        if p["patterns"]:
            reasons.append("; ".join(p["patterns"]))
        else:
            reasons.append("No significant candle pattern")

    out["candle_patterns"] = pattern_lists
    out["candle_bull_score"] = bull_scores
    out["candle_bear_score"] = bear_scores
    out["fake_breakout"] = fake_flags
    out["fake_trap_type"] = fake_types
    out["candle_confirms_buy"] = confirms_buy
    out["candle_confirms_sell"] = confirms_sell
    out["candle_reason"] = reasons

    return out


def summarize_row(row: pd.Series) -> dict:
    """Convenience bundle for strategy on the latest bar."""
    patterns = row.get("candle_patterns") or []
    if isinstance(patterns, float) and pd.isna(patterns):
        patterns = []

    bull = float(row.get("candle_bull_score", 0) or 0)
    bear = float(row.get("candle_bear_score", 0) or 0)
    max_score = config.PATTERN_SCORE_MAX
    strength = round(min(100.0, max(bull, bear) / max_score * 100), 1)

    return {
        "patterns": list(patterns),
        "reason": str(row.get("candle_reason", "")),
        "bull_score": bull,
        "bear_score": bear,
        "strength": strength,
        "confirms_buy": bool(row.get("candle_confirms_buy", False)),
        "confirms_sell": bool(row.get("candle_confirms_sell", False)),
        "fake_breakout": bool(row.get("fake_breakout", False)),
        "fake_trap_type": str(row.get("fake_trap_type", "") or ""),
    }


def is_bullish_reversal(row: pd.Series) -> bool:
    """Any pattern suggesting upside reversal (used with oversold RSI block)."""
    names = set(row.get("candle_patterns") or [])
    reversal = {
        "Bullish engulfing",
        "Hammer",
        "Bullish rejection wick",
        "Liquidity sweep (bullish)",
    }
    if names & reversal:
        return True
    if row.get("fake_trap_type") == "bear_trap":
        return True
    return False


def is_bearish_reversal(row: pd.Series) -> bool:
    names = set(row.get("candle_patterns") or [])
    reversal = {
        "Bearish engulfing",
        "Shooting star",
        "Bearish rejection wick",
        "Liquidity sweep (bearish)",
    }
    if names & reversal:
        return True
    if row.get("fake_trap_type") == "bull_trap":
        return True
    return False
