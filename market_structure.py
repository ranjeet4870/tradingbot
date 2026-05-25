"""Market structure: panic dumps, bounces, late entries, continuation vs reversal."""

import pandas as pd

import config


def _row_float(row: pd.Series, key: str, default: float = 0.0) -> float:
    val = row.get(key, default)
    if pd.isna(val):
        return default
    return float(val)


def detect_structure_row(df: pd.DataFrame, idx: int) -> dict:
    row = df.iloc[idx]
    rsi = _row_float(row, "rsi", 50)
    pct_n = _row_float(row, "pct_change_n", 0)
    trend_bull = bool(row.get("trend_bull", False))
    trend_bear = bool(row.get("trend_bear", False))
    vol_spike = _row_float(row, "volume_ratio", 0) >= config.VOLUME_SPIKE_MULTIPLIER
    near_retest = bool(row.get("near_ema_retest", False))

    panic_dump = pct_n <= -config.PANIC_DUMP_PCT
    sharp_rally = pct_n >= config.PANIC_DUMP_PCT
    oversold = rsi < config.RSI_EXTREME_OVERSOLD
    overbought = rsi > config.RSI_EXTREME_OVERBOUGHT

    late_sell = oversold and panic_dump and trend_bear
    late_buy = overbought and sharp_rally and trend_bull
    chasing_dump_sell = panic_dump and rsi < config.LATE_ENTRY_RSI_OVERSOLD
    chasing_pump_buy = sharp_rally and rsi > config.LATE_ENTRY_RSI_OVERBOUGHT

    if panic_dump and oversold:
        state = "panic_dump_oversold"
    elif panic_dump:
        state = "panic_dump"
    elif sharp_rally and overbought:
        state = "overbought_extension"
    elif oversold and bool(row.get("candle_confirms_buy", False)):
        state = "oversold_bounce_setup"
    elif overbought and bool(row.get("candle_confirms_sell", False)):
        state = "overbought_rejection_setup"
    elif trend_bull and vol_spike:
        state = "trend_continuation_bull"
    elif trend_bear and vol_spike:
        state = "trend_continuation_bear"
    elif near_retest and trend_bull:
        state = "bull_pullback_retest"
    elif near_retest and trend_bear:
        state = "bear_pullback_retest"
    elif abs(pct_n) < 0.6:
        state = "range_chop"
    else:
        state = "unclear"

    warnings: list[str] = []
    if late_sell:
        warnings.append("Late SELL risk — oversold after sharp dump")
    if late_buy:
        warnings.append("Late BUY risk — overbought after sharp rally")
    if chasing_dump_sell:
        warnings.append("Avoid chasing dump — wait for retest/bounce confirmation")
    if chasing_pump_buy:
        warnings.append("Avoid chasing pump — wait for pullback confirmation")
    if state == "range_chop":
        warnings.append("Choppy range — low edge until breakout confirms")

    strong_bear_continuation = (
        trend_bear
        and vol_spike
        and rsi > config.RSI_EXTREME_OVERSOLD
        and pct_n < -0.8
        and not bool(row.get("candle_confirms_buy", False))
    )
    strong_bull_continuation = (
        trend_bull
        and vol_spike
        and rsi < config.RSI_EXTREME_OVERBOUGHT
        and pct_n > 0.8
        and not bool(row.get("candle_confirms_sell", False))
    )

    return {
        "market_state": state,
        "late_entry_risk": late_sell or late_buy or chasing_dump_sell or chasing_pump_buy,
        "late_entry_warning": "; ".join(warnings) if warnings else "",
        "block_late_sell": chasing_dump_sell and not strong_bear_continuation,
        "block_late_buy": chasing_pump_buy and not strong_bull_continuation,
        "strong_bear_continuation": strong_bear_continuation,
        "strong_bull_continuation": strong_bull_continuation,
        "pullback_retest": near_retest,
    }


def enrich_market_structure(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    states, late_flags, warnings, block_sell, block_buy = [], [], [], [], []
    strong_bear, strong_bull = [], []

    for i in range(len(out)):
        if i < config.PANIC_DUMP_BARS:
            states.append("warming_up")
            late_flags.append(False)
            warnings.append("")
            block_sell.append(False)
            block_buy.append(False)
            strong_bear.append(False)
            strong_bull.append(False)
            continue
        s = detect_structure_row(out, i)
        states.append(s["market_state"])
        late_flags.append(s["late_entry_risk"])
        warnings.append(s["late_entry_warning"])
        block_sell.append(s["block_late_sell"])
        block_buy.append(s["block_late_buy"])
        strong_bear.append(s["strong_bear_continuation"])
        strong_bull.append(s["strong_bull_continuation"])

    out["market_state"] = states
    out["late_entry_risk"] = late_flags
    out["late_entry_warning"] = warnings
    out["block_late_sell"] = block_sell
    out["block_late_buy"] = block_buy
    out["strong_bear_continuation"] = strong_bear
    out["strong_bull_continuation"] = strong_bull
    return out


def summarize_structure(row: pd.Series) -> dict:
    return {
        "market_state": str(row.get("market_state", "unclear")),
        "late_entry_risk": bool(row.get("late_entry_risk", False)),
        "late_entry_warning": str(row.get("late_entry_warning", "") or ""),
        "block_late_sell": bool(row.get("block_late_sell", False)),
        "block_late_buy": bool(row.get("block_late_buy", False)),
        "strong_bear_continuation": bool(row.get("strong_bear_continuation", False)),
        "strong_bull_continuation": bool(row.get("strong_bull_continuation", False)),
    }
