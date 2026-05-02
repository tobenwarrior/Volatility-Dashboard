import unittest

from web.poller import compute_25d_fly


class ComputeFlyTest(unittest.TestCase):
    def test_uses_trader_premium_convention(self):
        """Fly should be (25d call IV + 25d put IV) - 2 * ATM IV."""
        self.assertEqual(compute_25d_fly(atm_iv=40.0, put_iv=45.0, call_iv=43.0), 8.0)

    def test_returns_none_when_any_input_missing(self):
        self.assertIsNone(compute_25d_fly(atm_iv=None, put_iv=45.0, call_iv=43.0))
        self.assertIsNone(compute_25d_fly(atm_iv=40.0, put_iv=None, call_iv=43.0))
        self.assertIsNone(compute_25d_fly(atm_iv=40.0, put_iv=45.0, call_iv=None))


if __name__ == "__main__":
    unittest.main()
