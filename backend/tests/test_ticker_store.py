import time
import unittest
from unittest.mock import patch

from ws.ticker_store import TickerDataStore


class TickerDataStoreFreshnessTest(unittest.TestCase):
    def test_get_ticker_rejects_entries_older_than_max_age(self):
        store = TickerDataStore()
        with patch("ws.ticker_store.time.monotonic", return_value=100.0):
            store.update_ticker("BTC-8MAY26-100-C", delta=0.25, mark_iv=50.0, timestamp=1)

        with patch("ws.ticker_store.time.monotonic", return_value=135.0):
            self.assertIsNone(store.get_ticker("BTC-8MAY26-100-C", max_age_seconds=30.0))

    def test_get_ticker_keeps_fresh_entries(self):
        store = TickerDataStore()
        with patch("ws.ticker_store.time.monotonic", return_value=100.0):
            store.update_ticker("BTC-8MAY26-100-C", delta=0.25, mark_iv=50.0, timestamp=1)

        with patch("ws.ticker_store.time.monotonic", return_value=125.0):
            ticker = store.get_ticker("BTC-8MAY26-100-C", max_age_seconds=30.0)

        self.assertIsNotNone(ticker)
        self.assertEqual(ticker["delta"], 0.25)
        self.assertEqual(ticker["mark_iv"], 50.0)


if __name__ == "__main__":
    unittest.main()
