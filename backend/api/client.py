"""
Deribit API client — handles all HTTP communication with the exchange.
"""

import requests


class DeribitClient:
    """Encapsulates all Deribit public API calls."""

    def __init__(self, base_url, timeout=10):
        self._base_url = base_url
        self._timeout = timeout

    def get_spot_price(self, index_name="btc_usd"):
        """Fetch the current index price for the given asset."""
        resp = requests.get(
            f"{self._base_url}/public/get_index_price",
            params={"index_name": index_name},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return float(resp.json()["result"]["index_price"])

    def get_options(self, currency="BTC"):
        """Fetch all active inverse option book summaries for the given currency."""
        resp = requests.get(
            f"{self._base_url}/public/get_book_summary_by_currency",
            params={"currency": currency, "kind": "option"},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json()["result"]

    def get_daily_candles(self, instrument, days=180):
        """Fetch daily OHLCV candles for the given instrument.

        Args:
            instrument: e.g. "BTC-PERPETUAL"
            days: Number of days of history to fetch.

        Returns:
            List of candle dicts with "close", "open", "high", "low", "volume", "ticks".
        """
        import time as _time
        now_ms = int(_time.time() * 1000)
        start_ms = now_ms - days * 86400 * 1000
        resp = requests.get(
            f"{self._base_url}/public/get_tradingview_chart_data",
            params={
                "instrument_name": instrument,
                "start_timestamp": start_ms,
                "end_timestamp": now_ms,
                "resolution": "1D",
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        result = resp.json()["result"]
        # result has parallel arrays: ticks, open, high, low, close, volume
        candles = []
        for i in range(len(result["ticks"])):
            candles.append({
                "ticks": result["ticks"][i],
                "open": result["open"][i],
                "high": result["high"][i],
                "low": result["low"][i],
                "close": result["close"][i],
                "volume": result["volume"][i],
            })
        return candles

