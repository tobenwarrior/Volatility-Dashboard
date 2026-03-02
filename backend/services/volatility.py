"""
ATM implied volatility calculator using variance interpolation.

Supports both single-tenor (legacy) and multi-tenor computation.
"""

import math
from datetime import datetime, timedelta, timezone

from models.option import TermInfo, VolatilityResult
from services.parser import parse_instrument_name


class VolatilityCalculator:
    """Computes constant maturity ATM implied volatility via variance interpolation."""

    def __init__(self, target_days=30, min_expiry_days=1):
        self._target_days = target_days
        self._min_expiry_days = min_expiry_days

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def build_expiry_data(self, options, now):
        """Parse raw options into expiry buckets and compute days-to-expiry.

        Args:
            options: Raw list of option dicts from Deribit API.
            now: Current UTC datetime.

        Returns:
            (expiry_data, expiry_days) where:
            - expiry_data: {datetime: {strike: {"C": iv, "P": iv}}}
            - expiry_days: {datetime: float} (only expiries > min_expiry_days)
        """
        expiry_data = {}
        for opt in options:
            iv = opt.get("mark_iv")
            if not iv or iv <= 0:
                continue
            parsed = parse_instrument_name(opt.get("instrument_name", ""))
            if parsed is None:
                continue
            expiry_data.setdefault(parsed.expiry, {}).setdefault(
                parsed.strike, {}
            )[parsed.opt_type] = iv

        expiry_days = {}
        for expiry in expiry_data:
            days = (expiry - now).total_seconds() / 86400.0
            if days <= 0:
                continue  # skip expired options
            if days > self._min_expiry_days:
                expiry_days[expiry] = days

        return expiry_data, expiry_days

    def _interpolate_iv(self, spot, expiry_data, expiry_days, target_days):
        """Compute ATM IV for a single target tenor via variance interpolation.

        Returns:
            dict with "atm_iv", "method", "near_expiry", "next_expiry"
            or dict with "error" key on failure.
        """
        if not expiry_days:
            return {"error": "No valid expiries found"}

        # --- Exact match ---
        for expiry, days in expiry_days.items():
            if abs(days - target_days) < 0.5:
                strike, iv = self._get_atm_iv(expiry_data[expiry], spot)
                if iv is not None:
                    return {
                        "atm_iv": iv,
                        "method": "exact_match",
                        "near_expiry": expiry,
                        "next_expiry": None,
                    }

        # --- Find bracketing expiries ---
        near = {e: d for e, d in expiry_days.items() if d < target_days}
        nxt = {e: d for e, d in expiry_days.items() if d > target_days}

        if not near:
            return {"error": f"No near-term expiry found (<{target_days} days)"}
        if not nxt:
            return {"error": f"No next-term expiry found (>{target_days} days)"}

        t1_expiry = max(near, key=near.get)
        t2_expiry = min(nxt, key=nxt.get)
        t1_days = expiry_days[t1_expiry]
        t2_days = expiry_days[t2_expiry]

        t1_strike, t1_iv = self._get_atm_iv(expiry_data[t1_expiry], spot)
        t2_strike, t2_iv = self._get_atm_iv(expiry_data[t2_expiry], spot)

        if t1_iv is None:
            return {"error": f"No valid IV at near-term expiry {t1_expiry.date()}"}
        if t2_iv is None:
            return {"error": f"No valid IV at next-term expiry {t2_expiry.date()}"}

        # --- Variance interpolation ---
        t1_years = t1_days / 365.25
        t2_years = t2_days / 365.25
        t_target_years = target_days / 365.25

        if abs(t2_years - t1_years) < 1e-10:
            return {"error": "Bracketing expiries too close together"}

        sigma1 = t1_iv / 100.0
        sigma2 = t2_iv / 100.0

        v1 = sigma1 ** 2 * t1_years
        v2 = sigma2 ** 2 * t2_years

        v_target = v1 + (v2 - v1) * (t_target_years - t1_years) / (t2_years - t1_years)

        if v_target <= 0:
            return {"error": "Negative interpolated variance (extreme term structure inversion)"}

        vol = math.sqrt(v_target / t_target_years) * 100.0

        if vol > 500 or vol < 0.01:
            return {"error": f"IV out of reasonable bounds: {vol:.2f}"}

        return {
            "atm_iv": vol,
            "method": "variance_interpolation",
            "near_expiry": t1_expiry,
            "next_expiry": t2_expiry,
        }

    # ------------------------------------------------------------------
    # Multi-tenor API
    # ------------------------------------------------------------------

    def calculate_multi_tenor(self, spot, options, tenors):
        """Compute ATM IV for multiple tenors from a single option chain snapshot.

        Args:
            spot: Current BTC spot price.
            options: Raw list of option dicts from Deribit API.
            tenors: List of dicts with "label" and "days" keys.

        Returns:
            dict with:
            - "timestamp": ISO string
            - "tenor_results": {label: {"atm_iv", "method", "error"}}
            - "tenor_expiries": {label: (near_expiry, next_expiry)} for RR calc
            - "expiry_data": parsed expiry buckets (for RR calc reuse)
            - "expiry_days": {datetime: float}
        """
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        expiry_data, expiry_days = self.build_expiry_data(options, now)

        tenor_results = {}
        tenor_expiries = {}

        for tenor in tenors:
            label = tenor["label"]
            target = tenor["days"]
            result = self._interpolate_iv(spot, expiry_data, expiry_days, target)
            tenor_results[label] = result
            tenor_expiries[label] = (
                result.get("near_expiry"),
                result.get("next_expiry"),
            )

        return {
            "timestamp": ts,
            "tenor_results": tenor_results,
            "tenor_expiries": tenor_expiries,
            "expiry_data": expiry_data,
            "expiry_days": expiry_days,
        }

    # ------------------------------------------------------------------
    # Legacy single-tenor API (unchanged)
    # ------------------------------------------------------------------

    def calculate(self, spot, options):
        """Run the full calculation from raw API option data.

        Args:
            spot: Current BTC spot price.
            options: Raw list of option dicts from Deribit API.

        Returns:
            VolatilityResult on success, or dict with "error" key on failure.
        """
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        target_date = (now + timedelta(days=self._target_days)).strftime("%Y-%m-%d")

        expiry_data, expiry_days = self.build_expiry_data(options, now)

        if not expiry_days:
            return {"error": "No valid expiries found", "timestamp": ts}

        # --- Exact match ---
        for expiry, days in expiry_days.items():
            if abs(days - self._target_days) < 0.5:
                strike, iv = self._get_atm_iv(expiry_data[expiry], spot)
                if iv is not None:
                    return VolatilityResult(
                        timestamp=ts,
                        target_date=target_date,
                        spot_price=spot,
                        near_term=TermInfo(days, iv, expiry.strftime("%Y-%m-%d"), strike),
                        next_term=None,
                        estimated_30d_vol=iv,
                        method="exact_match",
                    ).to_dict()

        near = {e: d for e, d in expiry_days.items() if d < self._target_days}
        nxt = {e: d for e, d in expiry_days.items() if d > self._target_days}

        if not near:
            return {"error": "No near-term expiry found (1-30 days)", "timestamp": ts}
        if not nxt:
            return {"error": "No next-term expiry found (>30 days)", "timestamp": ts}

        t1_expiry = max(near, key=near.get)
        t2_expiry = min(nxt, key=nxt.get)
        t1_days = expiry_days[t1_expiry]
        t2_days = expiry_days[t2_expiry]

        t1_strike, t1_iv = self._get_atm_iv(expiry_data[t1_expiry], spot)
        t2_strike, t2_iv = self._get_atm_iv(expiry_data[t2_expiry], spot)

        if t1_iv is None:
            return {"error": f"No valid IV at near-term expiry {t1_expiry.date()}", "timestamp": ts}
        if t2_iv is None:
            return {"error": f"No valid IV at next-term expiry {t2_expiry.date()}", "timestamp": ts}

        t1_years = t1_days / 365.25
        t2_years = t2_days / 365.25
        t30_years = self._target_days / 365.25

        if abs(t2_years - t1_years) < 1e-10:
            return {"error": "Bracketing expiries too close together", "timestamp": ts}

        sigma1 = t1_iv / 100.0
        sigma2 = t2_iv / 100.0

        v1 = sigma1 ** 2 * t1_years
        v2 = sigma2 ** 2 * t2_years

        v30 = v1 + (v2 - v1) * (t30_years - t1_years) / (t2_years - t1_years)

        if v30 <= 0:
            return {"error": "Negative interpolated variance", "timestamp": ts}

        vol_30d = math.sqrt(v30 / t30_years) * 100.0

        if vol_30d > 500 or vol_30d < 0.01:
            return {"error": f"IV out of reasonable bounds: {vol_30d:.2f}", "timestamp": ts}

        return VolatilityResult(
            timestamp=ts,
            target_date=target_date,
            spot_price=spot,
            near_term=TermInfo(t1_days, t1_iv, t1_expiry.strftime("%Y-%m-%d"), t1_strike),
            next_term=TermInfo(t2_days, t2_iv, t2_expiry.strftime("%Y-%m-%d"), t2_strike),
            estimated_30d_vol=vol_30d,
            method="variance_interpolation",
        ).to_dict()

    @staticmethod
    def _strike_iv(ivs):
        """Average valid call/put IVs for a single strike."""
        call_iv = ivs.get("C")
        put_iv = ivs.get("P")
        valid = [v for v in (call_iv, put_iv) if v is not None and v > 0]
        return sum(valid) / len(valid) if valid else None

    def _get_atm_iv(self, strikes_data, spot):
        """Compute ATM IV by interpolating between the two nearest strikes.

        When spot sits between two strikes, a pure closest-strike approach
        flips discretely as spot crosses the midpoint, causing chart jitter.
        Instead, linearly interpolate IV between the two nearest strikes
        weighted by distance to spot.
        """
        sorted_strikes = sorted(strikes_data.keys(), key=lambda s: abs(s - spot))

        # Collect the two nearest strikes with valid IV
        candidates = []
        for strike in sorted_strikes:
            iv = self._strike_iv(strikes_data[strike])
            if iv is not None:
                candidates.append((strike, iv))
                if len(candidates) == 2:
                    break

        if not candidates:
            return None, None
        if len(candidates) == 1:
            return candidates[0]

        s1, iv1 = candidates[0]
        s2, iv2 = candidates[1]

        # If spot is exactly on a strike, just use that strike
        if s1 == spot:
            return s1, iv1

        # Linear interpolation weighted by inverse distance
        d1 = abs(spot - s1)
        d2 = abs(spot - s2)
        total = d1 + d2
        w1 = 1.0 - d1 / total  # closer strike gets more weight
        w2 = 1.0 - d2 / total
        iv = w1 * iv1 + w2 * iv2

        return s1, iv
