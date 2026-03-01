"""
25-delta risk reversal calculator.

For each tenor, finds the 25-delta put IV and 25-delta call IV
by querying Deribit ticker for candidate strikes and interpolating.
RR = 25d_call_IV - 25d_put_IV.
"""

import math
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from services.parser import format_instrument_name

logger = logging.getLogger(__name__)


class RiskReversalCalculator:
    """Computes 25-delta risk reversal for a set of tenors."""

    def __init__(self, client, target_delta=0.25, candidates_per_side=3):
        self._client = client
        self._target_delta = target_delta
        self._candidates = candidates_per_side

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
                # Linear interpolation of RR across expiries
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
        """Compute the 25d risk reversal at a single expiry.

        Returns:
            RR as float (25d_call_IV - 25d_put_IV), or None.
        """
        t_years = days / 365.25
        if t_years <= 0:
            return None
        sqrt_t = math.sqrt(t_years)

        # Compute approximate delta for every OTM strike using its own mark_iv.
        # This accounts for the vol smile — much more accurate than estimating
        # a single 25-delta strike from ATM IV.
        put_ranked = []   # (approx_abs_delta, strike)
        call_ranked = []  # (approx_abs_delta, strike)

        for strike, ivs in strikes_data.items():
            if strike < spot and "P" in ivs:
                sigma = ivs["P"] / 100.0
                if sigma > 0:
                    d1 = (math.log(spot / strike) + 0.5 * sigma * sigma * t_years) / (sigma * sqrt_t)
                    abs_delta = self._norm_cdf(-d1)  # put abs delta = N(-d1)
                    put_ranked.append((abs_delta, strike))
            elif strike > spot and "C" in ivs:
                sigma = ivs["C"] / 100.0
                if sigma > 0:
                    d1 = (math.log(spot / strike) + 0.5 * sigma * sigma * t_years) / (sigma * sqrt_t)
                    abs_delta = self._norm_cdf(d1)  # call delta = N(d1)
                    call_ranked.append((abs_delta, strike))

        # Sort all OTM strikes by approx delta closeness to 0.25
        put_ranked.sort(key=lambda x: abs(x[0] - self._target_delta))
        call_ranked.sort(key=lambda x: abs(x[0] - self._target_delta))

        put_all_strikes = [s for _, s in put_ranked]
        call_all_strikes = [s for _, s in call_ranked]

        if not put_all_strikes or not call_all_strikes:
            return None

        # Fetch real deltas in batches, expanding search if we don't bracket 0.25
        put_25d_iv = self._find_25d_iv(expiry, put_all_strikes, "P", currency)
        call_25d_iv = self._find_25d_iv(expiry, call_all_strikes, "C", currency)

        if put_25d_iv is None or call_25d_iv is None:
            return None

        return call_25d_iv - put_25d_iv

    def _find_25d_iv(self, expiry, ranked_strikes, opt_type, currency="BTC"):
        """Fetch real deltas in batches until we bracket 0.25, then interpolate.

        Strikes are pre-sorted by approx delta closeness to 0.25. We fetch
        the first batch; if real deltas don't bracket 0.25 we keep expanding
        through all available strikes until we find it.

        Args:
            expiry: Expiry datetime.
            ranked_strikes: All OTM strikes sorted by approx delta closeness to 0.25.
            opt_type: "C" or "P".
            currency: "BTC" or "ETH".

        Returns:
            Interpolated IV at target delta, or None.
        """
        all_results = []  # (abs_delta, iv, strike)
        batch_size = self._candidates
        batch_idx = 0

        while batch_idx * batch_size < len(ranked_strikes):
            start = batch_idx * batch_size
            batch = ranked_strikes[start:start + batch_size]

            # Fetch tickers in parallel
            new_results = self._fetch_deltas(expiry, batch, opt_type, currency)
            all_results.extend(new_results)

            # Try to bracket 0.25 with everything we have so far
            iv = self._try_bracket(all_results)
            if iv is not None:
                logger.debug(
                    "Expiry %s %s: bracketed 0.25 on batch %d (strikes: %s, deltas: %s)",
                    expiry.strftime("%d%b%y"), opt_type, batch_idx + 1,
                    [r[2] for r in sorted(all_results, key=lambda r: r[0])],
                    [round(r[0], 4) for r in sorted(all_results, key=lambda r: r[0])],
                )
                return iv

            # Log and keep going
            if all_results:
                deltas = sorted([r[0] for r in all_results])
                logger.debug(
                    "Expiry %s %s: batch %d didn't bracket 0.25 (deltas: %s), expanding",
                    expiry.strftime("%d%b%y"), opt_type, batch_idx + 1,
                    [round(d, 4) for d in deltas],
                )

            batch_idx += 1

        # Exhausted all strikes — no bracket exists in the entire chain
        if all_results:
            logger.warning(
                "Expiry %s %s: searched all %d strikes, could not bracket 0.25 (deltas: %s)",
                expiry.strftime("%d%b%y"), opt_type, len(all_results),
                [round(r[0], 4) for r in sorted(all_results, key=lambda r: r[0])],
            )

        return None

    def _fetch_deltas(self, expiry, strikes, opt_type, currency="BTC"):
        """Fetch real delta and IV from Deribit ticker for a set of strikes."""
        results = []
        with ThreadPoolExecutor(max_workers=min(len(strikes), 10)) as pool:
            futures = {}
            for strike in strikes:
                name = format_instrument_name(currency, expiry, strike, opt_type)
                futures[pool.submit(self._safe_get_ticker, name)] = strike

            for future in as_completed(futures):
                strike = futures[future]
                ticker = future.result()
                if ticker is None:
                    continue
                greeks = ticker.get("greeks") or {}
                delta = greeks.get("delta")
                iv = ticker.get("mark_iv")
                if delta is not None and iv is not None:
                    results.append((abs(delta), iv, strike))
        return results

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

    def _safe_get_ticker(self, instrument_name):
        """Fetch ticker with error handling."""
        try:
            return self._client.get_ticker(instrument_name)
        except Exception:
            logger.warning("Ticker fetch failed for %s", instrument_name)
            return None

    @staticmethod
    def _norm_cdf(x):
        """Standard normal CDF using math.erf."""
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    @staticmethod
    def _label_to_days(label):
        """Convert tenor label to days, derived from config."""
        from config import TENORS
        for t in TENORS:
            if t["label"] == label:
                return t["days"]
        return None
