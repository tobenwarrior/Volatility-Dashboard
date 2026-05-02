import unittest

from web.server import create_app


class FakeHistoryStore:
    def __init__(self):
        self.history_calls = []

    def get_history(self, tenor, hours, currency):
        self.history_calls.append((tenor, hours, currency))
        return []

    def get_range_changes(self, hours=24.0, currency="BTC", latest_tenors=None):
        return {}

    def get_vol_stats(self, hours=None, currency="BTC"):
        return []


class FakePoller:
    def get_latest_tenor_data(self):
        return {"tenors": []}

    def get_latest_price(self):
        return {"price": 0}


class HistoryEndpointLimitTest(unittest.TestCase):
    def setUp(self):
        self.history = FakeHistoryStore()
        app = create_app(
            pollers={"BTC": FakePoller(), "ETH": FakePoller()},
            history_store=self.history,
            tenors=[{"label": "30D", "days": 30}],
        )
        self.client = app.test_client()

    def test_history_allows_configured_180d_retention_window(self):
        resp = self.client.get("/api/history?currency=BTC&tenor=30D&hours=4320")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.history.history_calls[-1], ("30D", 4320.0, "BTC"))

    def test_history_still_clamps_absurd_requests_to_retention_window(self):
        resp = self.client.get("/api/history?currency=ETH&tenor=30D&hours=999999")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.history.history_calls[-1], ("30D", 4320.0, "ETH"))


if __name__ == "__main__":
    unittest.main()
