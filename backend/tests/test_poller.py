import unittest
from unittest.mock import Mock

from web.poller import Poller, compute_25d_fly


class ComputeFlyTest(unittest.TestCase):
    def test_uses_trader_premium_convention(self):
        """Fly should be (25d call IV + 25d put IV) - 2 * ATM IV."""
        self.assertEqual(compute_25d_fly(atm_iv=40.0, put_iv=45.0, call_iv=43.0), 8.0)

    def test_returns_none_when_any_input_missing(self):
        self.assertIsNone(compute_25d_fly(atm_iv=None, put_iv=45.0, call_iv=43.0))
        self.assertIsNone(compute_25d_fly(atm_iv=40.0, put_iv=None, call_iv=43.0))
        self.assertIsNone(compute_25d_fly(atm_iv=40.0, put_iv=45.0, call_iv=None))


class PollerRVBackendToggleTest(unittest.TestCase):
    def test_backend_rv_disabled_does_not_call_rv_calculator(self):
        rv_calculator = Mock()
        poller = Poller(
            client=Mock(),
            calculator=Mock(),
            rr_calculator=Mock(),
            history_store=Mock(),
            tenors=[{"label": "1W", "days": 7}],
            rv_calculator=rv_calculator,
            perp_name="BTC-PERPETUAL",
            backend_rv_enabled=False,
        )

        result = poller._compute_rv_results()

        self.assertEqual(result, {})
        rv_calculator.compute_all_tenors.assert_not_called()

    def test_backend_rv_enabled_keeps_existing_compute_path(self):
        rv_calculator = Mock()
        rv_calculator.compute_all_tenors.return_value = {"1W": 30.0}
        poller = Poller(
            client=Mock(),
            calculator=Mock(),
            rr_calculator=Mock(),
            history_store=Mock(),
            tenors=[{"label": "1W", "days": 7}],
            rv_calculator=rv_calculator,
            perp_name="BTC-PERPETUAL",
            backend_rv_enabled=True,
        )

        result = poller._compute_rv_results()

        self.assertEqual(result, {"1W": 30.0})
        rv_calculator.compute_all_tenors.assert_called_once_with(
            "BTC-PERPETUAL", [{"label": "1W", "days": 7}]
        )


if __name__ == "__main__":
    unittest.main()
