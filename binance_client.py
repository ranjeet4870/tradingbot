"""
Fetch OHLCV candle data from Binance.

Public market data does NOT require API keys.
We only use the Client for reading klines (candlesticks).
"""

import pandas as pd
from binance.client import Client

import config


def create_client() -> Client:
    """
    Create a Binance client.

    If you set BINANCE_API_KEY / BINANCE_API_SECRET in .env,
    they are passed in — but klines work without them.
    """
    if config.BINANCE_API_KEY and config.BINANCE_API_SECRET:
        return Client(config.BINANCE_API_KEY, config.BINANCE_API_SECRET)
    return Client()


def fetch_klines() -> pd.DataFrame:
    """
    Download recent 15m BTCUSDT candles and return a pandas DataFrame.

    Columns:
        open, high, low, close, volume
    Index: candle open time (UTC)
    """
    client = create_client()

    # get_klines returns a list of lists; each inner list is one candle
    raw = client.get_klines(
        symbol=config.SYMBOL,
        interval=config.INTERVAL,
        limit=config.CANDLE_LIMIT,
    )

    df = pd.DataFrame(
        raw,
        columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trades",
            "taker_buy_base",
            "taker_buy_quote",
            "ignore",
        ],
    )

    # Convert string prices to floats
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)

    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df.set_index("open_time", inplace=True)

    # We only need OHLCV for our strategy
    return df[["open", "high", "low", "close", "volume"]]
