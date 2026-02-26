"""
Deribit API client — handles all HTTP communication with the exchange.
"""

import requests


class DeribitClient:
    """Encapsulates all Deribit public API calls."""

    def __init__(self, base_url, timeout=10):
        self._base_url = base_url
        self._timeout = timeout

    def get_spot_price(self):
        """Fetch the current BTC/USD index price."""
        resp = requests.get(
            f"{self._base_url}/public/get_index_price",
            params={"index_name": "btc_usd"},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return float(resp.json()["result"]["index_price"])

    def get_options(self):
        """Fetch all active BTC inverse option book summaries."""
        resp = requests.get(
            f"{self._base_url}/public/get_book_summary_by_currency",
            params={"currency": "BTC", "kind": "option"},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json()["result"]

    def get_ticker(self, instrument_name):
        """Fetch ticker data (including greeks) for a specific instrument."""
        resp = requests.get(
            f"{self._base_url}/public/ticker",
            params={"instrument_name": instrument_name},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json()["result"]
