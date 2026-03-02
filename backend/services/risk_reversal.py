"""
25-delta risk reversal calculator.

For each tenor, finds the 25-delta put IV and 25-delta call IV
and computes RR = 25d_call_IV - 25d_put_IV.

Uses live greeks.delta from Deribit WebSocket ticker data (no API calls).
"""

import logging

from services.parser import format_instrument_name

logger = logging.getLogger(__name__)


class RiskReversalCalculator:
    """Computes 25-delta risk reversal for a set of tenors."""

    def __init__(self, target_delta=0.25, ticker_store=None):
        self._target_delta = target_delta
        self._ticker_store = ticker_store

    def calculate(self, spot, expiry_data, expiry_days, tenor_expiries, currency="BTC"):
        """Compute 25d RR for each tenor.

        Args:
            spot: Current spot price.
            expiry_data: {expiry_datetime: {strike: {"C": iv, "P": iv}}}.
            expiry_days: {expiry_datetime: days_to_expiry}.
            tenor_expiries: {tenor_label: (near_expiry, next_expiry)}.
            currency: "BTC" or "ETH".

        Returns:
            Dict mapping tenor_label to rr_25d float (or None).
        """
        # Collect all unique expiries we need to process
        expiries_needed = set()
        for near, nxt in tenor_expiries.values():
            if near:
                expiries_needed.add(near)
            if nxt:
                expiries_needed.add(nxt)

        # Compute RR per expiry (cache to avoid duplicate work)
        expiry_rr_cache = {}
        for expiry in expiries_needed:
            if expiry not in expiry_data or expiry not in expiry_days:
                continue
            rr = self._rr_at_expiry(
                spot, expiry, expiry_data[expiry], expiry_days[expiry], currency
            )
            expiry_rr_cache[expiry] = rr

        # Interpolate across bracketing expiries per tenor
        results = {}
        for label, (near, nxt) in tenor_expiries.items():
            near_rr = expiry_rr_cache.get(near) if near else None
            nxt_rr = expiry_rr_cache.get(nxt) if nxt else None

            if near_rr is not None and nxt_rr is not None:
                t1 = expiry_days[near]
                t2 = expiry_days[nxt]
                target = self._label_to_days(label)
                if target and t2 != t1:
                    w = (target - t1) / (t2 - t1)
                    results[label] = near_rr + w * (nxt_rr - near_rr)
                else:
                    results[label] = near_rr
            elif near_rr is not None:
                results[label] = near_rr
            elif nxt_rr is not None:
                results[label] = nxt_rr
            else:
                results[label] = None

        return results

    def _rr_at_expiry(self, spot, expiry, strikes_data, days, currency="BTC"):
        """Compute the 25d risk reversal using live greeks.delta from WebSocket.

        Reads delta and mark_iv from the TickerDataStore, which is continuously
        updated by the WebSocket client. No API calls.

        Returns:
            RR as float (25d_call_IV - 25d_put_IV), or None.
        """
        if self._ticker_store is None:
            return None

        put_results = []
        call_results = []

        for strike, ivs in strikes_data.items():
            if strike < spot and "P" in ivs:
                name = format_instrument_name(currency, expiry, strike, "P")
                ticker = self._ticker_store.get_ticker(name)
                if ticker and ticker.get("delta") is not None and ticker.get("mark_iv") is not None:
                    put_results.append((abs(ticker["delta"]), ticker["mark_iv"], strike))
            elif strike > spot and "C" in ivs:
                name = format_instrument_name(currency, expiry, strike, "C")
                ticker = self._ticker_store.get_ticker(name)
                if ticker and ticker.get("delta") is not None and ticker.get("mark_iv") is not None:
                    call_results.append((abs(ticker["delta"]), ticker["mark_iv"], strike))

        put_25d_iv = self._try_bracket(put_results)
        call_25d_iv = self._try_bracket(call_results)

        if put_25d_iv is None or call_25d_iv is None:
            return None

        return call_25d_iv - put_25d_iv

    def _try_bracket(self, results):
        """Try to interpolate to target delta from collected results.

        Returns interpolated IV if bracketed, None otherwise.
        """
        if len(results) < 2:
            return None

        sorted_r = sorted(results, key=lambda r: r[0])
        for i in range(len(sorted_r) - 1):
            d1, iv1, _ = sorted_r[i]
            d2, iv2, _ = sorted_r[i + 1]
            if d1 <= self._target_delta <= d2:
                w = (self._target_delta - d1) / (d2 - d1) if d2 != d1 else 0.5
                return iv1 + w * (iv2 - iv1)

        return None

    @staticmethod
    def _label_to_days(label):
        """Convert tenor label to days, derived from config."""
        from config import TENORS
        for t in TENORS:
            if t["label"] == label:
                return t["days"]
        return None
