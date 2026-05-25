# BTCUSDT Crypto Signal Bot

A beginner-friendly Python bot that reads **BTCUSDT** on Binance (15-minute candles) and prints **BUY**, **SELL**, or **WAIT** signals with confidence %, entry, stop loss, and take profit.

> **Disclaimer:** For education only. Not financial advice. Never trade with money you cannot afford to lose.

## Strategy (simple overview)

| Step | What it checks |
|------|----------------|
| 1 | **EMA 20 vs EMA 50** — trend direction |
| 2 | **RSI** — momentum confirmation |
| 3 | **Volume spike** — unusual activity vs 20-candle average |
| 4 | **Fake breakout** — price fakes above/below support then reverses |
| 5 | **Score** → signal + confidence % + trade levels |

**BUY** when EMA + RSI are bullish **and** (volume spike **or** bear trap).  
**SELL** when EMA + RSI are bearish **and** (volume spike **or** bull trap).  
Otherwise **WAIT**.

## Project structure

```
trading-bot1/
├── main.py              # Entry point + web server (Railway)
├── config.py            # All settings in one place
├── bot/
│   ├── data_fetcher.py  # Binance candle download
│   ├── indicators.py    # EMA, RSI, volume average
│   ├── fake_breakout.py # Bull/bear trap detection
│   ├── strategy.py      # Signal logic + levels
│   └── display.py       # Console output
├── requirements.txt
├── Procfile             # Railway start command
└── railway.toml         # Railway health check
```

## Run locally

```bash
cd trading-bot1
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python main.py
```

Open:

- http://localhost:8080/health
- http://localhost:8080/signal

Optional: copy `.env.example` to `.env` and change `SCAN_INTERVAL_SECONDS`.

## Deploy on Railway

1. Push this folder to GitHub.
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub**.
3. Select the repo. Railway detects Python automatically.
4. No API key needed (public Binance data).
5. Optional variables:
   - `SCAN_INTERVAL_SECONDS=300`
   - `BINANCE_BASE_URL=https://api.binance.com`
6. Deploy. Visit your app URL + `/signal` for JSON output.

## API endpoints

| Route | Description |
|-------|-------------|
| `/` | Bot info + latest signal |
| `/health` | Health check (Railway) |
| `/signal` | Latest signal JSON |

## Tune settings

Edit `config.py`:

- `EMA_FAST`, `EMA_SLOW`, `RSI_PERIOD`
- `VOLUME_SPIKE_MULTIPLIER`
- `STOP_LOSS_PERCENT`, `TAKE_PROFIT_RR`
