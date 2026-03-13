"""
Realized Volatility (RV) calculator.

Computes annualized realized volatility from daily perpetual close prices.
RV = std(log_returns[-N:]) * sqrt(365) * 100
"""

import logging
import math
import time as _time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_CACHE_TTL = 300  # 5 minutes


class RealizedVolCalculator:
    """Fetches daily closes once per call and computes RV for multiple tenors."""

    def __init__(self, client):
        self._client = client
        self._rolling_cache = {}  # (perp_name, tenor_days) -> (timestamp, {date_str: rv})

    def compute_all_tenors(self, perp_name, tenors):
        """Compute realized vol for each tenor from daily candle closes.

        Args:
            perp_name: Instrument name, e.g. "BTC-PERPETUAL".
            tenors: List of tenor config dicts with "label" and "days".

        Returns:
            Dict mapping tenor label to RV (float) or None on error.
        """
        max_days = max(t["days"] for t in tenors) + 5  # small buffer
        try:
            candles = self._client.get_daily_candles(perp_name, days=max_days)
        except Exception:
            logger.exception("Failed to fetch daily candles for %s", perp_name)
            return {t["label"]: None for t in tenors}

        if len(candles) < 3:
            return {t["label"]: None for t in tenors}

        # Compute log returns from close prices
        closes = [c["close"] for c in candles]
        log_returns = []
        for i in range(1, len(closes)):
            if closes[i] > 0 and closes[i - 1] > 0:
                log_returns.append(math.log(closes[i] / closes[i - 1]))

        results = {}
        for tenor in tenors:
            n = tenor["days"]
            label = tenor["label"]
            if len(log_returns) < n:
                results[label] = None
                continue
            window = log_returns[-n:]
            mean = sum(window) / len(window)
            variance = sum((r - mean) ** 2 for r in window) / (len(window) - 1)
            rv = math.sqrt(variance) * math.sqrt(365) * 100
            results[label] = round(rv, 4)

        return results

    def get_rolling_series(self, perp_name, tenor_days):
        """Compute rolling daily RV for the given tenor, with caching.

        Returns a dict mapping date string (YYYY-MM-DD) to RV value.
        Cached for 5 minutes since daily candles only change once per day.
        """
        cache_key = (perp_name, tenor_days)
        now = _time.time()

        if cache_key in self._rolling_cache:
            cached_time, cached_data = self._rolling_cache[cache_key]
            if now - cached_time < _CACHE_TTL:
                return cached_data

        # Fetch enough candles: tenor window + 60 extra days of history
        fetch_days = tenor_days + 60
        try:
            candles = self._client.get_daily_candles(perp_name, days=fetch_days)
        except Exception:
            logger.exception("Failed to fetch daily candles for rolling RV")
            return {}

        if len(candles) < tenor_days + 1:
            return {}

        closes = [c["close"] for c in candles]
        ticks = [c["ticks"] for c in candles]

        # Compute all log returns
        log_returns = []
        for i in range(1, len(closes)):
            if closes[i] > 0 and closes[i - 1] > 0:
                log_returns.append(math.log(closes[i] / closes[i - 1]))
            else:
                log_returns.append(0.0)

        # Rolling RV: for each day d >= tenor_days, compute RV from
        # the preceding tenor_days returns
        results = {}
        for d in range(tenor_days, len(log_returns) + 1):
            window = log_returns[d - tenor_days:d]
            mean = sum(window) / len(window)
            variance = sum((r - mean) ** 2 for r in window) / (len(window) - 1)
            rv = math.sqrt(variance) * math.sqrt(365) * 100
            # ticks[d] corresponds to the candle whose close completes this window
            dt = datetime.fromtimestamp(ticks[d] / 1000, tz=timezone.utc)
            date_str = dt.strftime("%Y-%m-%d")
            results[date_str] = round(rv, 4)

        self._rolling_cache[cache_key] = (now, results)
        return results
