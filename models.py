"""Data structures for professional trading signals."""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class TradingSignal:
    action: str
    confidence_pct: float
    reason: str
    reasons: list[str] = field(default_factory=list)

    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_reward: Optional[float] = None

    price: float = 0.0
    ema_fast: float = 0.0
    ema_slow: float = 0.0
    rsi: float = 0.0
    atr: float = 0.0
    atr_pct: float = 0.0
    volume_ratio: float = 0.0
    trend_strength: float = 0.0

    support: float = 0.0
    resistance: float = 0.0
    swing_high: float = 0.0
    swing_low: float = 0.0

    market_state: str = "unclear"
    late_entry_risk: bool = False
    late_entry_warning: str = ""
    wait_explanation: str = ""

    fake_breakout: bool = False
    fake_trap_type: str = ""
    fake_breakout_details: str = ""

    candle_patterns: list[str] = field(default_factory=list)
    candle_reason: str = ""
    candle_strength: float = 0.0
    candle_confirms_buy: bool = False
    candle_confirms_sell: bool = False

    news_sentiment: str = "neutral"
    news_score: float = 0.0
    news_headlines: list[str] = field(default_factory=list)
    news_conflict: bool = False

    block_buy_reversal: bool = False
    block_sell_reversal: bool = False

    def to_dict(self) -> dict:
        return asdict(self)
