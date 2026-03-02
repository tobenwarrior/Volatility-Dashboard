"""
Thread-safe data store for WebSocket-sourced market data.

Bridges the asyncio WebSocket thread and the synchronous polling/Flask threads.
All reads and writes are protected by threading.Lock().
"""

import threading
import time


class TickerDataStore:
    """Stores latest spot prices and option ticker data from WebSocket feeds."""

    def __init__(self):
        self._lock = threading.Lock()
        self._spot_prices = {}       # {index_name: {"price": float, "timestamp": int}}
        self._ticker_data = {}       # {instrument_name: {"delta": float, "mark_iv": float, "timestamp": int}}
        self._spot_updated_at = {}   # {index_name: monotonic time}

    # ---- Writes (called from asyncio WebSocket thread) ----

    def update_spot(self, index_name, price, timestamp):
        """Update spot price from deribit_price_index channel."""
        with self._lock:
            self._spot_prices[index_name] = {
                "price": price,
                "timestamp": timestamp,
            }
            self._spot_updated_at[index_name] = time.monotonic()

    def update_ticker(self, instrument_name, delta, mark_iv, timestamp):
        """Update ticker data from ticker.{instrument}.100ms channel."""
        with self._lock:
            self._ticker_data[instrument_name] = {
                "delta": delta,
                "mark_iv": mark_iv,
                "timestamp": timestamp,
            }

    def clear_tickers(self, instrument_names=None):
        """Remove ticker entries (used when unsubscribing stale instruments)."""
        with self._lock:
            if instrument_names is None:
                self._ticker_data.clear()
            else:
                for name in instrument_names:
                    self._ticker_data.pop(name, None)

    # ---- Reads (called from polling/Flask threads) ----

    def get_spot_price(self, index_name):
        """Return latest spot price, or None if never received."""
        with self._lock:
            entry = self._spot_prices.get(index_name)
            return entry["price"] if entry else None

    def get_spot_age_seconds(self, index_name):
        """Seconds since last spot update (for staleness detection)."""
        with self._lock:
            updated = self._spot_updated_at.get(index_name)
            if updated is None:
                return float("inf")
            return time.monotonic() - updated

    def get_ticker(self, instrument_name):
        """Return latest ticker data dict, or None."""
        with self._lock:
            entry = self._ticker_data.get(instrument_name)
            return dict(entry) if entry else None
