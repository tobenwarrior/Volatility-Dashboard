"""
Realized Volatility (RV) calculator.

Uses Binance 1-hour spot candles for high-granularity RV
that updates every hour and closely tracks implied volatility.

RV = sqrt(mean(log_return^2)) * sqrt(8760) * 100
where N = tenor_days * 24 completed hourly returns
"""

import logging
import math
import time as _time
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

BINANCE_KLINE_URL = "https://api.binance.com/api/v3/klines"
PERIODS_PER_YEAR = 8760  # hours in a year
_CACHE_TTL = 300  # 5 minutes

# Map Deribit currency to Binance spot symbol
BINANCE_SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
}


def _fetch_binance_1h(symbol, limit=1500):
    """Fetch up to `limit` completed 1-hour candles from Binance spot."""
    now_ms = int(_time.time() * 1000)
    remaining = max(0, int(limit))
    end_time = now_ms
    candles = []

    while remaining > 0:
        batch_limit = min(remaining, 1000)
        params = {"symbol": symbol, "interval": "1h", "limit": batch_limit, "endTime": end_time}
        resp = requests.get(
            BINANCE_KLINE_URL,
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        # Each candle: [open_time, open, high, low, close, volume, close_time, ...]
        raw = resp.json()
        if not raw:
            break

        batch = []
        for c in raw:
            close_time = int(c[6]) if len(c) > 6 else int(c[0]) + 3600_000 - 1
            if close_time > now_ms:
                continue
            batch.append({"time_ms": int(c[0]), "close": float(c[4])})

        if not batch:
            break
        candles[0:0] = batch
        remaining -= len(batch)
        end_time = batch[0]["time_ms"] - 1
        if len(raw) < batch_limit:
            break

    return candles[-limit:]


class RealizedVolCalculator:
    """Computes RV from Binance 1h perpetual candles."""

    def __init__(self, client=None):
        self._client = client  # kept for backward compat, unused now
        self._cache = {}  # currency -> (timestamp, candles)
        self._rolling_cache = {}  # (currency, tenor_days) -> (timestamp, series)

    def _get_candles(self, currency, limit=1500):
        """Get completed 1h candles with caching."""
        now = _time.time()
        if currency in self._cache:
            cached_time, cached = self._cache[currency]
            if now - cached_time < _CACHE_TTL and len(cached) >= limit:
                return cached[-limit:]

        symbol = BINANCE_SYMBOLS.get(currency)
        if not symbol:
            return []

        try:
            candles = _fetch_binance_1h(symbol, limit=limit)
        except Exception:
            logger.exception("Failed to fetch Binance 1h spot candles for %s", symbol)
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
        if not tenors:
            return {}
        required_candles = max(int(t["days"] * 24) for t in tenors) + 1
        candles = self._get_candles(currency, limit=required_candles)

        closes = [c["close"] for c in candles]
        log_returns = []
        for i in range(1, len(closes)):
            if closes[i] > 0 and closes[i - 1] > 0:
                log_returns.append(math.log(closes[i] / closes[i - 1]))

        results = {}
        for tenor in tenors:
            n = int(tenor["days"] * 24)  # hourly returns needed
            label = tenor["label"]
            if len(log_returns) < n:
                results[label] = None
                continue
            window = log_returns[-n:]
            variance = sum(r * r for r in window) / len(window)
            rv = math.sqrt(variance) * math.sqrt(PERIODS_PER_YEAR) * 100
            results[label] = round(rv, 4)

        return results

    def get_rolling_series(self, perp_name, tenor_days):
        """Compute rolling hourly RV for the given tenor, with caching.

        Returns a dict mapping hour-floored unix timestamp (int) to RV value.
        """
        currency = perp_name.split("-")[0] if perp_name else "BTC"
        cache_key = (currency, tenor_days)
        now = _time.time()

        if cache_key in self._rolling_cache:
            cached_time, cached_data = self._rolling_cache[cache_key]
            if now - cached_time < _CACHE_TTL:
                return cached_data

        n_returns = int(tenor_days * 24)  # hourly returns for the window
        candles = self._get_candles(currency, limit=n_returns + 350)

        if len(candles) < n_returns + 2:
            logger.warning("Not enough candles for %s %dD RV: have %d, need %d",
                           currency, tenor_days, len(candles), n_returns + 2)
            return {}

        closes = [c["close"] for c in candles]
        times = [c["time_ms"] for c in candles]

        log_returns = []
        for i in range(1, len(closes)):
            if closes[i] > 0 and closes[i - 1] > 0:
                log_returns.append(math.log(closes[i] / closes[i - 1]))
            else:
                log_returns.append(0.0)

        # Rolling RV: slide by 1 hour, key by unix timestamp floored to hour
        results = {}
        for end in range(n_returns, len(log_returns) + 1):
            window = log_returns[end - n_returns:end]
            variance = sum(r * r for r in window) / len(window)
            rv = math.sqrt(variance) * math.sqrt(PERIODS_PER_YEAR) * 100
            # Key: candle open time floored to hour (unix seconds)
            hour_ts = times[end] // 3600000 * 3600
            results[hour_ts] = round(rv, 4)

        logger.info("Rolling RV for %s %dD: %d hourly values", currency, tenor_days, len(results))
        self._rolling_cache[cache_key] = (now, results)
        return results
