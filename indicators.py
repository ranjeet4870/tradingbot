"""Technical indicators: EMA, RSI, ATR, volume, swings, trend strength, structure flags."""

import numpy as np
import pandas as pd

import config


def add_ema(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema_fast"] = df["close"].ewm(span=config.EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=config.EMA_SLOW, adjust=False).mean()
    return df


def add_rsi(df: pd.DataFrame, period: int = config.RSI_PERIOD) -> pd.DataFrame:
    df = df.copy()
    delta = df["close"].diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)
    avg_gain = gains.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = (100 - (100 / (1 + rs))).fillna(50)
    return df


def add_atr(df: pd.DataFrame, period: int = config.ATR_PERIOD) -> pd.DataFrame:
    df = df.copy()
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr"] = tr.ewm(span=period, adjust=False).mean()
    df["atr_pct"] = (df["atr"] / df["close"]) * 100
    return df


def add_volume_ratio(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    avg_vol = df["volume"].rolling(config.VOLUME_LOOKBACK).mean()
    df["volume_ratio"] = df["volume"] / avg_vol.replace(0, np.nan)
    return df


def add_swing_levels(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["swing_high"] = df["high"].shift(1).rolling(config.SWING_LOOKBACK).max()
    df["swing_low"] = df["low"].shift(1).rolling(config.SWING_LOOKBACK).min()
    df["resistance"] = df["swing_high"]
    df["support"] = df["swing_low"]
    return df


def add_trend_strength(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["trend_strength"] = (
        (df["ema_fast"] - df["ema_slow"]).abs() / df["close"] * 100
    ).fillna(0)
    df["trend_bull"] = df["ema_fast"] > df["ema_slow"]
    df["trend_bear"] = df["ema_fast"] < df["ema_slow"]
    return df


def add_price_structure(df: pd.DataFrame) -> pd.DataFrame:
    """Rolling dump/rally % and distance from EMA for late-entry detection."""
    df = df.copy()
    n = config.PANIC_DUMP_BARS
    df["pct_change_n"] = (df["close"] / df["close"].shift(n) - 1) * 100
    df["ema_dist_pct"] = ((df["close"] - df["ema_fast"]) / df["close"] * 100).fillna(0)
    df["near_ema_retest"] = df["ema_dist_pct"].abs() <= config.RETEST_EMA_TOLERANCE * 100
    return df


def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    from candle_patterns import enrich_candles
    from market_structure import enrich_market_structure

    df = add_ema(df)
    df = add_rsi(df)
    df = add_atr(df)
    df = add_volume_ratio(df)
    df = add_swing_levels(df)
    df = add_trend_strength(df)
    df = add_price_structure(df)
    df = enrich_candles(df)
    df = enrich_market_structure(df)
    return df
