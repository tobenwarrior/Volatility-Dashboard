import sys
import threading
import types
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

# The unit tests exercise cache-only methods and never instantiate a real
# HistoryStore, so provide a tiny psycopg2 stub for local environments that do
# not have production DB dependencies installed.
if "psycopg2" not in sys.modules:
    psycopg2_stub = types.ModuleType("psycopg2")
    psycopg2_pool_stub = types.ModuleType("psycopg2.pool")
    psycopg2_pool_stub.ThreadedConnectionPool = lambda *args, **kwargs: object()
    psycopg2_stub.pool = psycopg2_pool_stub
    sys.modules["psycopg2"] = psycopg2_stub
    sys.modules["psycopg2.pool"] = psycopg2_pool_stub

from services.history import HistoryStore


class HistoryRangeChangesTest(unittest.TestCase):
    def make_store(self, now):
        store = HistoryStore.__new__(HistoryStore)
        store._cache_lock = threading.Lock()
        store._now = lambda: now
        store._cache = {
            ("BTC", "30D"): [
                (now - timedelta(hours=25), 40.0, -5.0, None, 1.0),
                (now - timedelta(hours=7), 42.0, -4.0, None, 1.5),
                (now - timedelta(hours=1), 43.0, -3.0, None, 2.0),
            ],
            ("ETH", "30D"): [
                (now - timedelta(hours=24), 55.0, -2.0, None, 1.2),
            ],
        }
        return store

    def test_get_range_changes_computes_selected_lookback_for_currency(self):
        now = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
        store = self.make_store(now)

        changes = store.get_range_changes(hours=4, currency="BTC")

        self.assertAlmostEqual(changes["30D"]["iv_change"], 1.0)
        self.assertAlmostEqual(changes["30D"]["rr_change"], 1.0)
        self.assertAlmostEqual(changes["30D"]["bf_change"], 0.5)
        self.assertAlmostEqual(changes["30D"]["dod_iv_change"], 1.0)
        self.assertAlmostEqual(changes["30D"]["dod_rr_change"], 1.0)
        self.assertAlmostEqual(changes["30D"]["dod_bf_change"], 0.5)
        self.assertEqual(changes["30D"]["change_hours"], 7.0)
        self.assertNotIn("ETH", changes)

    def test_get_range_changes_uses_live_latest_tenors_when_provided(self):
        now = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
        store = self.make_store(now)

        changes = store.get_range_changes(
            hours=24,
            currency="BTC",
            latest_tenors=[{"label": "30D", "atm_iv": 44.0, "rr_25d": -2.5, "bf_25d": 2.5}],
        )

        self.assertAlmostEqual(changes["30D"]["iv_change"], 4.0)
        self.assertAlmostEqual(changes["30D"]["rr_change"], 2.5)
        self.assertAlmostEqual(changes["30D"]["bf_change"], 1.5)
        self.assertEqual(changes["30D"]["change_hours"], 25.0)

    def test_get_range_changes_returns_nulls_when_no_history_for_range(self):
        now = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
        store = self.make_store(now)

        changes = store.get_range_changes(hours=24, currency="ETH")

        self.assertIsNone(changes["30D"]["iv_change"])
        self.assertIsNone(changes["30D"]["rr_change"])
        self.assertIsNone(changes["30D"]["bf_change"])
        self.assertIsNone(changes["30D"]["change_hours"])


class HistoryStoreInitTest(unittest.TestCase):
    def test_init_runs_retention_cleanup_after_backfill(self):
        calls = []

        def fake_ensure_db(self):
            calls.append("ensure")

        def fake_backfill(self):
            calls.append("backfill")

        def fake_cleanup(self):
            calls.append("cleanup")

        with patch.object(HistoryStore, "_ensure_db", fake_ensure_db), \
             patch.object(HistoryStore, "_backfill_cache", fake_backfill), \
             patch.object(HistoryStore, "cleanup_old", fake_cleanup), \
             patch("services.history.psycopg2.pool.ThreadedConnectionPool", return_value=object()):
            HistoryStore(db_url="postgres://example")

        self.assertEqual(calls, ["ensure", "backfill", "cleanup"])


if __name__ == "__main__":
    unittest.main()
