"""
Dynamic subscription manager for RR-relevant option tickers.

After each volatility poll cycle, analyzes the expiry_data to determine
which strikes are near the 25-delta boundary, and subscribes to their
ticker channels for live greeks.delta updates.
"""

import math
import logging

from services.parser import format_instrument_name

logger = logging.getLogger(__name__)


class SubscriptionManager:
    """Manages which ticker.{instrument}.100ms channels are subscribed."""

    def __init__(self, ws_client, target_delta=0.25, candidates_per_side=5):
        self._ws = ws_client
        self._target_delta = target_delta
        self._candidates = candidates_per_side
        self._current_subs = {}  # {currency: set(channel_strings)}

    def update_subscriptions(self, currency, spot, expiry_data, expiry_days, expiry_refs=None):
        """Recompute and adjust subscriptions after a poll cycle.

        Uses approximate BS delta ranking to identify which strikes are
        near 25-delta, then subscribes to their ticker channels.

        Args:
            currency: "BTC" or "ETH"
            spot: Current spot price
            expiry_data: {expiry_dt: {strike: {"C": iv, "P": iv}}}
            expiry_days: {expiry_dt: float}
            expiry_refs: Optional {expiry_dt: Deribit underlying/forward reference price}
        """
        needed_channels = set()

        for expiry, strikes_data in expiry_data.items():
            days = expiry_days.get(expiry)
            if days is None or days <= 0:
                continue
            t_years = days / 365.25
            sqrt_t = math.sqrt(t_years)

            put_ranked = []
            call_ranked = []

            reference = (expiry_refs or {}).get(expiry) or spot

            for strike, ivs in strikes_data.items():
                if strike < reference and "P" in ivs:
                    sigma = ivs["P"] / 100.0
                    if sigma > 0:
                        d1 = (math.log(reference / strike) + 0.5 * sigma**2 * t_years) / (sigma * sqrt_t)
                        abs_delta = 0.5 * (1.0 + math.erf(-d1 / math.sqrt(2.0)))
                        put_ranked.append((abs(abs_delta - self._target_delta), strike))
                elif strike > reference and "C" in ivs:
                    sigma = ivs["C"] / 100.0
                    if sigma > 0:
                        d1 = (math.log(reference / strike) + 0.5 * sigma**2 * t_years) / (sigma * sqrt_t)
                        abs_delta = 0.5 * (1.0 + math.erf(d1 / math.sqrt(2.0)))
                        call_ranked.append((abs(abs_delta - self._target_delta), strike))

            put_ranked.sort()
            call_ranked.sort()

            for _, strike in put_ranked[:self._candidates]:
                ch = f"ticker.{format_instrument_name(currency, expiry, strike, 'P')}.100ms"
                needed_channels.add(ch)
            for _, strike in call_ranked[:self._candidates]:
                ch = f"ticker.{format_instrument_name(currency, expiry, strike, 'C')}.100ms"
                needed_channels.add(ch)

        current = self._current_subs.get(currency, set())
        to_add = needed_channels - current
        to_remove = current - needed_channels

        if to_remove:
            self._ws.unsubscribe(to_remove)
            logger.info("[%s] Unsubscribed %d stale ticker channels", currency, len(to_remove))
        if to_add:
            self._ws.subscribe(to_add)
            logger.info("[%s] Subscribed to %d new ticker channels (total: %d)",
                        currency, len(to_add), len(needed_channels))

        self._current_subs[currency] = needed_channels
