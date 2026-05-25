"""
Public OHLCV market data — Railway-safe (no geo-blocked Binance SDK).

Primary: Bybit spot klines (BTCUSDT 15m)
Fallback: CryptoCompare histominute aggregate
Fallback: Kraken OHLC

No API key required.
"""

from __future__ import annotations

import logging

import pandas as pd
import requests

import config

logger = logging.getLogger(__name__)

LAST_DATA_PROVIDER: str = "none"

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "BTCProSignalBot/2.0"})


def _frame_from_rows(rows: list, time_col: int = 0) -> pd.DataFrame:
    """Build standard OHLCV DataFrame indexed by UTC open time."""
    if not rows:
        raise ValueError("No candle data returned")

    df = pd.DataFrame(
        rows,
        columns=["open_time", "open", "high", "low", "close", "volume"],
    )
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)

    if df["open_time"].dtype == object:
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    else:
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)

    df = df.sort_values("open_time")
    df.set_index("open_time", inplace=True)
    return df[["open", "high", "low", "close", "volume"]].tail(config.CANDLE_LIMIT)


def fetch_bybit() -> pd.DataFrame:
    """Bybit v5 public spot klines — works on Railway US/EU."""
    url = f"{config.BYBIT_BASE_URL}/v5/market/kline"
    r = _SESSION.get(
        url,
        params={
            "category": "spot",
            "symbol": config.SYMBOL,
            "interval": config.BYBIT_INTERVAL,
            "limit": config.CANDLE_LIMIT,
        },
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    if body.get("retCode") != 0:
        raise RuntimeError(body.get("retMsg", "Bybit API error"))

    raw = body["result"]["list"]
    # Bybit returns newest first: [start, open, high, low, close, volume, turnover]
    rows = [
        [int(c[0]), c[1], c[2], c[3], c[4], c[5]]
        for c in reversed(raw)
    ]
    return _frame_from_rows(rows)


def fetch_cryptocompare() -> pd.DataFrame:
    """CryptoCompare 15m aggregated minutes — global CDN."""
    r = _SESSION.get(
        config.CRYPTOCOMPARE_OHLC_URL,
        params={
            "fsym": "BTC",
            "tsym": "USDT",
            "limit": config.CANDLE_LIMIT,
            "aggregate": 15,
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json().get("Data", {}).get("Data", [])
    if not data:
        raise ValueError("CryptoCompare returned empty OHLC")

    rows = [
        [
            d["time"] * 1000,
            d["open"],
            d["high"],
            d["low"],
            d["close"],
            d["volumefrom"],
        ]
        for d in reversed(data)
    ]
    return _frame_from_rows(rows)


def fetch_kraken() -> pd.DataFrame:
    """Kraken public OHLC — XBT/USD proxy for BTCUSD."""
    r = _SESSION.get(
        config.KRAKEN_OHLC_URL,
        params={"pair": config.KRAKEN_PAIR, "interval": 15},
        timeout=30,
    )
    r.raise_for_status()
    result = r.json()["result"]
    key = next(k for k in result if k != "last")
    raw = result[key][-config.CANDLE_LIMIT :]
    rows = [[c[0] * 1000, c[1], c[2], c[3], c[4], c[6]] for c in raw]
    return _frame_from_rows(rows)


def get_last_provider() -> str:
    return LAST_DATA_PROVIDER


def fetch_klines() -> pd.DataFrame:
    """
    Fetch BTCUSDT 15m candles using Railway-compatible public APIs.
    """
    global LAST_DATA_PROVIDER
    providers = [
        ("bybit", fetch_bybit),
        ("cryptocompare", fetch_cryptocompare),
        ("kraken", fetch_kraken),
    ]

    # Allow forcing a provider via env
    forced = (config.MARKET_DATA_PROVIDER or "").strip().lower()
    if forced:
        mapping = {name: fn for name, fn in providers}
        if forced in mapping:
            providers = [(forced, mapping[forced])]

    errors: list[str] = []
    for name, fn in providers:
        try:
            df = fn()
            LAST_DATA_PROVIDER = name
            logger.info("Market data loaded from %s (%s rows)", name, len(df))
            return df
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            logger.warning("Provider %s failed: %s", name, exc)

    raise RuntimeError("All market data providers failed — " + "; ".join(errors))
