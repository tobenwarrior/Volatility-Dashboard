import unittest
from datetime import datetime, timezone

from services.risk_reversal import RiskReversalCalculator
from services.parser import format_instrument_name


class FakeTickerStore:
    def __init__(self, tickers):
        self.tickers = tickers

    def get_ticker(self, name, max_age_seconds=None):
        return self.tickers.get(name)


class AgeSensitiveTickerStore:
    def __init__(self, tickers, required_max_age_seconds):
        self.tickers = tickers
        self.required_max_age_seconds = required_max_age_seconds

    def get_ticker(self, name, max_age_seconds=None):
        if max_age_seconds is None or max_age_seconds < self.required_max_age_seconds:
            return None
        return self.tickers.get(name)


class RiskReversalReferencePriceTest(unittest.TestCase):
    def test_ivs_at_expiry_uses_expiry_reference_for_call_put_side_selection(self):
        expiry = datetime(2026, 5, 8, 8, 0, tzinfo=timezone.utc)
        tickers = {
            format_instrument_name("BTC", expiry, 110.0, "P"): {"delta": -0.20, "mark_iv": 44.0},
            format_instrument_name("BTC", expiry, 115.0, "P"): {"delta": -0.30, "mark_iv": 46.0},
            format_instrument_name("BTC", expiry, 125.0, "C"): {"delta": 0.20, "mark_iv": 40.0},
            format_instrument_name("BTC", expiry, 130.0, "C"): {"delta": 0.30, "mark_iv": 42.0},
        }
        calc = RiskReversalCalculator(ticker_store=FakeTickerStore(tickers))
        strikes_data = {
            110.0: {"P": 1.0},
            115.0: {"P": 1.0},
            125.0: {"C": 1.0},
            130.0: {"C": 1.0},
        }

        put_iv, call_iv = calc._ivs_at_expiry(
            spot=100.0,
            expiry=expiry,
            strikes_data=strikes_data,
            currency="BTC",
            reference_price=120.0,
        )

        self.assertAlmostEqual(put_iv, 45.0)
        self.assertAlmostEqual(call_iv, 41.0)

    def test_default_ticker_freshness_window_tolerates_quiet_deribit_wings(self):
        expiry = datetime(2026, 5, 8, 8, 0, tzinfo=timezone.utc)
        tickers = {
            format_instrument_name("BTC", expiry, 90.0, "P"): {"delta": -0.20, "mark_iv": 44.0},
            format_instrument_name("BTC", expiry, 95.0, "P"): {"delta": -0.30, "mark_iv": 46.0},
            format_instrument_name("BTC", expiry, 105.0, "C"): {"delta": 0.20, "mark_iv": 40.0},
            format_instrument_name("BTC", expiry, 110.0, "C"): {"delta": 0.30, "mark_iv": 42.0},
        }
        calc = RiskReversalCalculator(
            ticker_store=AgeSensitiveTickerStore(tickers, required_max_age_seconds=120.0)
        )
        strikes_data = {
            90.0: {"P": 1.0},
            95.0: {"P": 1.0},
            105.0: {"C": 1.0},
            110.0: {"C": 1.0},
        }

        put_iv, call_iv = calc._ivs_at_expiry(
            spot=100.0,
            expiry=expiry,
            strikes_data=strikes_data,
            currency="BTC",
            reference_price=100.0,
        )

        self.assertAlmostEqual(put_iv, 45.0)
        self.assertAlmostEqual(call_iv, 41.0)

    def test_interp_pair_uses_total_variance_across_expiries(self):
        put_iv, call_iv = RiskReversalCalculator._interp_pair(
            near_pair=(30.0, 40.0),
            nxt_pair=(60.0, 70.0),
            t1=30.0,
            t2=90.0,
            target=60.0,
        )

        expected_put = ((0.30 ** 2 * 30.0 + ((0.60 ** 2 * 90.0) - (0.30 ** 2 * 30.0)) * 0.5) / 60.0) ** 0.5 * 100
        expected_call = ((0.40 ** 2 * 30.0 + ((0.70 ** 2 * 90.0) - (0.40 ** 2 * 30.0)) * 0.5) / 60.0) ** 0.5 * 100
        self.assertAlmostEqual(put_iv, expected_put)
        self.assertAlmostEqual(call_iv, expected_call)


if __name__ == "__main__":
    unittest.main()
