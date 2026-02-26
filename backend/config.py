"""
Central configuration for the Volatility Estimator.
"""

# ---------------------------------------------------------------------------
# Deribit API
# ---------------------------------------------------------------------------
DERIBIT_BASE = "https://www.deribit.com/api/v2"
INDEX_URL = f"{DERIBIT_BASE}/public/get_index_price"
BOOK_URL = f"{DERIBIT_BASE}/public/get_book_summary_by_currency"
TICKER_URL = f"{DERIBIT_BASE}/public/ticker"
REQUEST_TIMEOUT = 10  # seconds

# ---------------------------------------------------------------------------
# Polling intervals
# ---------------------------------------------------------------------------
POLL_INTERVAL = 5   # seconds — full option chain + vol calc
PRICE_INTERVAL = 1  # seconds — spot price only

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
]

# ---------------------------------------------------------------------------
# Risk reversal
# ---------------------------------------------------------------------------
TARGET_DELTA = 0.25
TICKER_CANDIDATES_PER_SIDE = 5  # strikes to check near estimated 25d

# ---------------------------------------------------------------------------
# History database
# ---------------------------------------------------------------------------
import os as _os
DB_PATH = _os.path.join(_os.path.dirname(__file__), "data", "iv_history.db")
HISTORY_KEEP_DAYS = 14  # enough for 7D chart + T-1 overlay
