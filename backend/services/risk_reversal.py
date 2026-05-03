"""
25-delta risk reversal and butterfly calculator.

For each tenor, finds the 25-delta put IV and 25-delta call IV and returns
both the raw IVs and RR = 25d_call_IV - 25d_put_IV. Callers combine with
ATM IV to derive 25d butterfly = 25d_call + 25d_put - 2 * ATM.
That is the trader premium / full fly package convention; it is exactly
2x the average-wing half-sum convention.

Uses live greeks.delta from Deribit WebSocket ticker data (no API calls).
"""

import logging
import math

from services.parser import format_instrument_name

logger = logging.getLogger(__name__)


class RiskReversalCalculator:
    """Computes 25-delta risk reversal for a set of tenors."""

    def __init__(self, target_delta=0.25, ticker_store=None, ticker_max_age_seconds=300):
        self._target_delta = target_delta
        self._ticker_store = ticker_store
        self._ticker_max_age_seconds = ticker_max_age_seconds

    def calculate(self, spot, expiry_data, expiry_days, tenor_expiries, currency="BTC", expiry_refs=None):
        """Compute 25d RR and raw 25d put/call IVs for each tenor.

        Args:
            spot: Current spot price.
            expiry_data: {expiry_datetime: {strike: {"C": iv, "P": iv}}}.
            expiry_days: {expiry_datetime: days_to_expiry}.
            tenor_expiries: {tenor_label: (near_expiry, next_expiry)}.
            currency: "BTC" or "ETH".
            expiry_refs: Optional {expiry_datetime: underlying/forward reference price}.

        Returns:
            Dict mapping tenor_label to
            {"rr_25d": float|None, "put_25d_iv": float|None, "call_25d_iv": float|None}.
        """
        # Collect all unique expiries we need to process
        expiries_needed = set()
        for near, nxt in tenor_expiries.values():
            if near:
                expiries_needed.add(near)
            if nxt:
                expiries_needed.add(nxt)

        # Compute raw 25d put/call IVs per expiry (cache to avoid duplicate work)
        # Each cache entry: (put_25d_iv, call_25d_iv) or (None, None) if unavailable.
        expiry_cache = {}
        for expiry in expiries_needed:
            if expiry not in expiry_data or expiry not in expiry_days:
                continue
            expiry_cache[expiry] = self._ivs_at_expiry(
                spot, expiry, expiry_data[expiry], currency, (expiry_refs or {}).get(expiry)
            )

        # Interpolate put/call IVs by total variance across bracketing expiries
        # so 25Δ wings use the same constant-maturity basis as ATM IV.
        results = {}
        for label, (near, nxt) in tenor_expiries.items():
            near_pair = expiry_cache.get(near) if near else None
            nxt_pair = expiry_cache.get(nxt) if nxt else None

            put_iv, call_iv = self._interp_pair(
                near_pair, nxt_pair,
                expiry_days.get(near) if near else None,
                expiry_days.get(nxt) if nxt else None,
                self._label_to_days(label),
            )

            rr = call_iv - put_iv if (put_iv is not None and call_iv is not None) else None
            results[label] = {
                "rr_25d": rr,
                "put_25d_iv": put_iv,
                "call_25d_iv": call_iv,
            }

        return results

    @staticmethod
    def _interp_pair(near_pair, nxt_pair, t1, t2, target):
        """Interpolate a (put_iv, call_iv) pair between two expiries.

        Uses total variance interpolation for each wing. Falls back to
        whichever side has data if the other is missing.
        """
        def _interp(a, b):
            if a is None or b is None:
                return a if a is not None else b
            if target is None or t1 is None or t2 is None or t2 == t1 or target <= 0:
                return a
            w = (target - t1) / (t2 - t1)
            sigma1 = a / 100.0
            sigma2 = b / 100.0
            v1 = sigma1 ** 2 * t1
            v2 = sigma2 ** 2 * t2
            v_target = v1 + w * (v2 - v1)
            if v_target <= 0:
                return None
            return math.sqrt(v_target / target) * 100.0

        near_put, near_call = near_pair if near_pair else (None, None)
        nxt_put, nxt_call = nxt_pair if nxt_pair else (None, None)

        # If one side entirely missing, use the other side verbatim
        if near_pair is None and nxt_pair is None:
            return None, None
        if near_pair is None:
            return nxt_put, nxt_call
        if nxt_pair is None:
            return near_put, near_call

        return _interp(near_put, nxt_put), _interp(near_call, nxt_call)

    def _ivs_at_expiry(self, spot, expiry, strikes_data, currency="BTC", reference_price=None):
        """Extract 25d put and call IVs for a single expiry using live greeks.

        Reads delta and mark_iv from the TickerDataStore, which is continuously
        updated by the WebSocket client. No API calls.

        Returns:
            (put_25d_iv, call_25d_iv) tuple — either element may be None if a
            side cannot be bracketed to the target delta.
        """
        if self._ticker_store is None:
            return (None, None)

        put_results = []
        call_results = []

        reference = reference_price if reference_price is not None and reference_price > 0 else spot
        for strike, ivs in strikes_data.items():
            if strike < reference and "P" in ivs:
                name = format_instrument_name(currency, expiry, strike, "P")
                ticker = self._ticker_store.get_ticker(name, max_age_seconds=self._ticker_max_age_seconds)
                if ticker and ticker.get("delta") is not None and ticker.get("mark_iv") is not None:
                    put_results.append((abs(ticker["delta"]), ticker["mark_iv"], strike))
            elif strike > reference and "C" in ivs:
                name = format_instrument_name(currency, expiry, strike, "C")
                ticker = self._ticker_store.get_ticker(name, max_age_seconds=self._ticker_max_age_seconds)
                if ticker and ticker.get("delta") is not None and ticker.get("mark_iv") is not None:
                    call_results.append((abs(ticker["delta"]), ticker["mark_iv"], strike))

        put_25d_iv = self._try_bracket(put_results)
        call_25d_iv = self._try_bracket(call_results)
        return (put_25d_iv, call_25d_iv)

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
