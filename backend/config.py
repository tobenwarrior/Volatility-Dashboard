"""
Central configuration for the Volatility Estimator.
"""

# ---------------------------------------------------------------------------
# Deribit API
# ---------------------------------------------------------------------------
DERIBIT_BASE = "https://www.deribit.com/api/v2"
INDEX_URL = f"{DERIBIT_BASE}/public/get_index_price"
BOOK_URL = f"{DERIBIT_BASE}/public/get_book_summary_by_currency"
REQUEST_TIMEOUT = 10  # seconds

# ---------------------------------------------------------------------------
# Supported assets
# ---------------------------------------------------------------------------
ASSETS = {
    "BTC": {"index_name": "btc_usd", "currency": "BTC", "perp_name": "BTC-PERPETUAL"},
    "ETH": {"index_name": "eth_usd", "currency": "ETH", "perp_name": "ETH-PERPETUAL"},
}

# ---------------------------------------------------------------------------
# Polling intervals
# ---------------------------------------------------------------------------
POLL_INTERVAL = 60   # seconds — full option chain + vol calc (live dashboard)
PRICE_INTERVAL = 5   # seconds — spot price only (reads WebSocket, no REST cost)
SAVE_INTERVAL = 300  # seconds — how often to persist to in-mem cache + Postgres
                     # (independent of POLL_INTERVAL; tuned so 180d fits the free tier)

# ---------------------------------------------------------------------------
# Volatility calculation
# ---------------------------------------------------------------------------
TARGET_DAYS = 30
MIN_EXPIRY_DAYS = 1  # skip expiries within this window (gamma noise)

# ---------------------------------------------------------------------------
# Multi-tenor configuration
# ---------------------------------------------------------------------------
TENORS = [
    {"label": "1W",   "days": 7},
    {"label": "2W",   "days": 14},
    {"label": "30D",  "days": 30},
    {"label": "60D",  "days": 60},
    {"label": "90D",  "days": 90},
    {"label": "180D", "days": 180},
    {"label": "9M",   "days": 270},
]

# ---------------------------------------------------------------------------
# Risk reversal
# ---------------------------------------------------------------------------
TARGET_DELTA = 0.25
TICKER_CANDIDATES_PER_SIDE = 5  # strikes to subscribe near estimated 25d

# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------
DERIBIT_WS_URL = "wss://www.deribit.com/ws/api/v2"
WS_SPOT_STALE_SECONDS = 5  # fall back to REST if WS spot older than this

# ---------------------------------------------------------------------------
# History database (Postgres via DATABASE_URL env var)
# ---------------------------------------------------------------------------
HISTORY_KEEP_DAYS = 180  # 180D lookback for Vol Compass (trader request)
