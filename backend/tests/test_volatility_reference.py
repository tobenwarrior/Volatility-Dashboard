import unittest
from datetime import datetime, timezone

from services.volatility import VolatilityCalculator


class VolatilityReferencePriceTest(unittest.TestCase):
    def test_get_atm_iv_brackets_reference_price_when_different_from_spot(self):
        calc = VolatilityCalculator()
        strikes_data = {
            100.0: {"C": 30.0, "P": 30.0},
            110.0: {"C": 40.0, "P": 40.0},
            120.0: {"C": 60.0, "P": 60.0},
        }

        strike, iv = calc._get_atm_iv(strikes_data, spot=100.0, reference_price=115.0)

        self.assertEqual(strike, 110.0)
        self.assertAlmostEqual(iv, 50.0)

    def test_build_expiry_data_returns_per_expiry_underlying_reference(self):
        calc = VolatilityCalculator(min_expiry_days=0)
        now = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
        options = [
            {
                "instrument_name": "BTC-8MAY26-100-C",
                "mark_iv": 30.0,
                "underlying_price": 114.0,
            },
            {
                "instrument_name": "BTC-8MAY26-110-C",
                "mark_iv": 40.0,
                "underlying_price": 116.0,
            },
        ]

        expiry_data, expiry_days, expiry_refs = calc.build_expiry_data(options, now)

        expiry = next(iter(expiry_data))
        self.assertAlmostEqual(expiry_refs[expiry], 115.0)


if __name__ == "__main__":
    unittest.main()
