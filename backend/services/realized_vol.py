"""
Realized Volatility (RV) calculator.

Uses Binance 1-hour perpetual futures candles for high-granularity RV
that updates every hour and closely tracks implied volatility.

RV = std(log_returns[-N:]) * sqrt(8760) * 100
where N = tenor_days * 24 (hourly returns)
"""

import logging
import math
import time as _time
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

BINANCE_KLINE_URL = "https://fapi.binance.com/fapi/v1/klines"
PERIODS_PER_YEAR = 8760  # hours in a year
_CACHE_TTL = 300  # 5 minutes

# Map Deribit currency to Binance futures symbol
BINANCE_SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
}


def _fetch_binance_1h(symbol, limit=1500):
    """Fetch up to `limit` 1-hour candles from Binance futures."""
    resp = requests.get(
        BINANCE_KLINE_URL,
        params={"symbol": symbol, "interval": "1h", "limit": limit},
        timeout=10,
    )
    resp.raise_for_status()
    # Each candle: [open_time, open, high, low, close, volume, ...]
    raw = resp.json()
    return [{"time_ms": c[0], "close": float(c[4])} for c in raw]


class RealizedVolCalculator:
    """Computes RV from Binance 1h perpetual candles."""

    def __init__(self, client=None):
        self._client = client  # kept for backward compat, unused now
        self._cache = {}  # currency -> (timestamp, candles)
        self._rolling_cache = {}  # (currency, tenor_days) -> (timestamp, series)

    def _get_candles(self, currency):
        """Get 1h candles with caching."""
        now = _time.time()
        if currency in self._cache:
            cached_time, cached = self._cache[currency]
            if now - cached_time < _CACHE_TTL:
                return cached

        symbol = BINANCE_SYMBOLS.get(currency)
        if not symbol:
            return []

        try:
            candles = _fetch_binance_1h(symbol, limit=1500)
        except Exception:
            logger.exception("Failed to fetch Binance 1h candles for %s", symbol)
            return []

        self._cache[currency] = (now, candles)
        return candles

    def compute_all_tenors(self, perp_name, tenors):
        """Compute current RV for each tenor.

        Args:
            perp_name: Unused (kept for backward compat). Currency derived from tenors call context.
            tenors: List of tenor config dicts with "label" and "days".

        Returns:
            Dict mapping tenor label to RV (float) or None on error.
        """
        # Derive currency from perp_name
        currency = perp_name.split("-")[0] if perp_name else "BTC"
        candles = self._get_candles(currency)

        if len(candles) < 50:
            return {t["label"]: None for t in tenors}

        closes = [c["close"] for c in candles]
        log_returns = []
        for i in range(1, len(closes)):
            if closes[i] > 0 and closes[i - 1] > 0:
                log_returns.append(math.log(closes[i] / closes[i - 1]))

        results = {}
        for tenor in tenors:
            n = tenor["days"] * 24  # hourly returns needed
            label = tenor["label"]
            if len(log_returns) < n:
                results[label] = None
                continue
            window = log_returns[-n:]
            mean = sum(window) / len(window)
            variance = sum((r - mean) ** 2 for r in window) / (len(window) - 1)
            rv = math.sqrt(variance) * math.sqrt(PERIODS_PER_YEAR) * 100
            results[label] = round(rv, 4)

        return results

    def get_rolling_series(self, perp_name, tenor_days):
        """Compute rolling hourly RV for the given tenor, with caching.

        Returns a dict mapping "YYYY-MM-DD HH" to RV value — one entry
        per hour so the overlay line updates smoothly.
        """
        currency = perp_name.split("-")[0] if perp_name else "BTC"
        cache_key = (currency, tenor_days)
        now = _time.time()

        if cache_key in self._rolling_cache:
            cached_time, cached_data = self._rolling_cache[cache_key]
            if now - cached_time < _CACHE_TTL:
                return cached_data

        candles = self._get_candles(currency)
        n_returns = tenor_days * 24  # hourly returns for the window

        if len(candles) < n_returns + 2:
            return {}

        closes = [c["close"] for c in candles]
        times = [c["time_ms"] for c in candles]

        log_returns = []
        for i in range(1, len(closes)):
            if closes[i] > 0 and closes[i - 1] > 0:
                log_returns.append(math.log(closes[i] / closes[i - 1]))
            else:
                log_returns.append(0.0)

        # Rolling RV: slide by 1 hour
        results = {}
        for end in range(n_returns, len(log_returns) + 1):
            window = log_returns[end - n_returns:end]
            mean = sum(window) / len(window)
            variance = sum((r - mean) ** 2 for r in window) / (len(window) - 1)
            rv = math.sqrt(variance) * math.sqrt(PERIODS_PER_YEAR) * 100
            # times[end] is the candle that completes this window
            dt = datetime.fromtimestamp(times[end] / 1000, tz=timezone.utc)
            key = dt.strftime("%Y-%m-%d %H")
            results[key] = round(rv, 4)

        self._rolling_cache[cache_key] = (now, results)
        return results
