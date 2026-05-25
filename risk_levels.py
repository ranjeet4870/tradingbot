"""ATR + swing-based stop loss and take profit with minimum 1:2 R:R."""

from typing import Optional, Tuple

import pandas as pd

import config


def _clamp_sl_distance(price: float, distance: float) -> float:
    min_d = price * (config.MIN_SL_PCT / 100)
    max_d = price * (config.MAX_SL_PCT / 100)
    return max(min_d, min(max_d, distance))


def compute_trade_levels(
    row: pd.Series, action: str, price: float
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    """
    Returns entry, stop_loss, take_profit, risk_reward.
    WAIT → all None.
    """
    if action == "WAIT" or action not in (
        "BUY",
        "STRONG BUY",
        "SELL",
        "STRONG SELL",
    ):
        return None, None, None, None

    atr = float(row.get("atr", 0) or 0)
    if atr <= 0:
        atr = price * 0.012

    swing_low = row.get("swing_low")
    swing_high = row.get("swing_high")
    entry = round(price, 2)

    is_buy = "BUY" in action

    if is_buy:
        sl_atr = entry - config.ATR_SL_MULTIPLIER * atr
        sl_swing = (
            float(swing_low) * (1 - config.SWING_SL_BUFFER)
            if not pd.isna(swing_low)
            else sl_atr
        )
        stop_loss = max(sl_atr, sl_swing)
        if stop_loss >= entry:
            stop_loss = entry - _clamp_sl_distance(entry, config.ATR_SL_MULTIPLIER * atr)
        risk = entry - stop_loss
        risk = _clamp_sl_distance(entry, risk)
        stop_loss = round(entry - risk, 2)
        take_profit = round(entry + risk * config.MIN_RISK_REWARD, 2)
        tp_atr = entry + config.ATR_TP_MULTIPLIER * atr
        if tp_atr > take_profit:
            take_profit = round(tp_atr, 2)
    else:
        sl_atr = entry + config.ATR_SL_MULTIPLIER * atr
        sl_swing = (
            float(swing_high) * (1 + config.SWING_SL_BUFFER)
            if not pd.isna(swing_high)
            else sl_atr
        )
        stop_loss = min(sl_atr, sl_swing)
        if stop_loss <= entry:
            stop_loss = entry + _clamp_sl_distance(entry, config.ATR_SL_MULTIPLIER * atr)
        risk = stop_loss - entry
        risk = _clamp_sl_distance(entry, risk)
        stop_loss = round(entry + risk, 2)
        take_profit = round(entry - risk * config.MIN_RISK_REWARD, 2)
        tp_atr = entry - config.ATR_TP_MULTIPLIER * atr
        if tp_atr < take_profit:
            take_profit = round(tp_atr, 2)

    rr = abs(take_profit - entry) / abs(entry - stop_loss) if stop_loss != entry else None
    return entry, stop_loss, take_profit, round(rr, 2) if rr else None
