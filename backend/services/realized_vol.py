"""
Realized Volatility (RV) calculator.

Computes annualized realized volatility from daily perpetual close prices.
RV = std(log_returns[-N:]) * sqrt(365) * 100
"""

import logging
import math

logger = logging.getLogger(__name__)


class RealizedVolCalculator:
    """Fetches daily closes once per call and computes RV for multiple tenors."""

    def __init__(self, client):
        self._client = client

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
