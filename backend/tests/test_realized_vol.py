import math
import sys
import types
import unittest
from unittest.mock import Mock, patch

# server modules may import optional dependencies in local test environments
supabase_stub = types.ModuleType("supabase")
supabase_stub.create_client = lambda *args, **kwargs: object()
sys.modules.setdefault("supabase", supabase_stub)

from services import realized_vol
from services.realized_vol import RealizedVolCalculator


class RealizedVolConventionTest(unittest.TestCase):
    def test_current_rv_uses_binance_spot_completed_hourly_candles_and_second_moment(self):
        now_ms = 200 * 3600_000
        closes = [100.0]
        for i in range(24):
            closes.append(closes[-1] * (1.01 if i % 2 == 0 else 0.99))
        completed = [
            [now_ms - (25 - i) * 3600_000, str(closes[i - 1] if i else closes[0]), "0", "0", str(close), "0", now_ms - (24 - i) * 3600_000 - 1]
            for i, close in enumerate(closes)
        ]
        open_candle = [now_ms - 1000, str(closes[-1]), "0", "0", "1000", "0", now_ms + 3600_000]
        response = Mock()
        response.json.return_value = completed + [open_candle]
        response.raise_for_status.return_value = None

        with patch.object(realized_vol._time, "time", return_value=now_ms / 1000), \
             patch.object(realized_vol.requests, "get", return_value=response) as get:
            calc = RealizedVolCalculator()
            result = calc.compute_all_tenors("BTC-PERPETUAL", [{"label": "1D", "days": 1}])

        get.assert_called_once()
        url = get.call_args.args[0]
        self.assertEqual(url, "https://api.binance.com/api/v3/klines")
        self.assertEqual(get.call_args.kwargs["params"]["symbol"], "BTCUSDT")
        returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
        expected = math.sqrt(sum(r * r for r in returns) / len(returns)) * math.sqrt(8760) * 100
        self.assertAlmostEqual(result["1D"], round(expected, 4), places=4)

    def test_rolling_rv_uses_same_second_moment_convention(self):
        now_ms = 300 * 3600_000
        closes = [100.0]
        for i in range(26):
            closes.append(closes[-1] * (1.01 if i % 2 == 0 else 0.99))
        raw = [
            [now_ms - (27 - i) * 3600_000, str(closes[i - 1] if i else closes[0]), "0", "0", str(close), "0", now_ms - (26 - i) * 3600_000 - 1]
            for i, close in enumerate(closes)
        ]
        response = Mock()
        response.json.return_value = raw
        response.raise_for_status.return_value = None

        with patch.object(realized_vol._time, "time", return_value=now_ms / 1000), \
             patch.object(realized_vol.requests, "get", return_value=response):
            calc = RealizedVolCalculator()
            series = calc.get_rolling_series("BTC-PERPETUAL", 1)

        self.assertEqual(len(series), 3)
        returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, 25)]
        expected_first = math.sqrt(sum(r * r for r in returns) / len(returns)) * math.sqrt(8760) * 100
        first_ts = raw[24][0] // 3600000 * 3600
        self.assertIn(first_ts, series)
        self.assertAlmostEqual(series[first_ts], round(expected_first, 4), places=4)
    def test_current_rv_keeps_short_tenors_when_long_tenors_lack_data(self):
        now_ms = 500 * 3600_000
        closes = [100.0]
        for i in range(24):
            closes.append(closes[-1] * 1.001)
        raw = [
            [now_ms - (25 - i) * 3600_000, str(closes[i - 1] if i else closes[0]), "0", "0", str(close), "0", now_ms - (24 - i) * 3600_000 - 1]
            for i, close in enumerate(closes)
        ]
        response = Mock()
        response.json.return_value = raw
        response.raise_for_status.return_value = None

        with patch.object(realized_vol._time, "time", return_value=now_ms / 1000), \
             patch.object(realized_vol.requests, "get", return_value=response):
            calc = RealizedVolCalculator()
            result = calc.compute_all_tenors(
                "BTC-PERPETUAL",
                [{"label": "1D", "days": 1}, {"label": "180D", "days": 180}],
            )

        self.assertIsNotNone(result["1D"])
        self.assertIsNone(result["180D"])
    def test_fetch_binance_1h_paginates_when_more_than_one_spot_request_needed(self):
        now_ms = 10_000 * 3600_000

        def candle(open_hour, close):
            open_ms = open_hour * 3600_000
            return [open_ms, str(close), "0", "0", str(close), "0", open_ms + 3600_000 - 1]

        older = [candle(i, 100 + i) for i in range(500)]
        latest = [candle(i, 100 + i) for i in range(500, 1500)]
        responses = []
        for batch in (latest, older):
            response = Mock()
            response.json.return_value = batch
            response.raise_for_status.return_value = None
            responses.append(response)

        with patch.object(realized_vol._time, "time", return_value=now_ms / 1000), \
             patch.object(realized_vol.requests, "get", side_effect=responses) as get:
            candles = realized_vol._fetch_binance_1h("BTCUSDT", limit=1500)

        self.assertEqual(len(candles), 1500)
        self.assertEqual(candles[0]["time_ms"], older[0][0])
        self.assertEqual(candles[-1]["time_ms"], latest[-1][0])
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args_list[0].kwargs["params"]["limit"], 1000)
        self.assertEqual(get.call_args_list[1].kwargs["params"]["limit"], 500)


if __name__ == "__main__":
    unittest.main()
