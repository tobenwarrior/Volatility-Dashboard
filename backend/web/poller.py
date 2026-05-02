"""
Background polling threads for spot price and multi-tenor volatility data.
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)


def compute_25d_fly(atm_iv, put_iv, call_iv):
    """Compute 25-delta fly using trader premium convention.

    Formula: Fly = 25Δ Call IV + 25Δ Put IV - 2 * ATM IV.
    This is exactly 2x the half-sum convention and matches the trader's
    requested quoting basis for this dashboard.
    """
    if atm_iv is None or put_iv is None or call_iv is None:
        return None
    return call_iv + put_iv - 2 * atm_iv


class Poller:
    """Manages background threads that poll Deribit for price and volatility data."""

    def __init__(self, client, calculator, rr_calculator, history_store,
                 tenors, poll_interval=5, price_interval=1,
                 currency="BTC", index_name="btc_usd",
                 ticker_store=None, subscription_manager=None,
                 ws_spot_stale_seconds=5,
                 rv_calculator=None, perp_name=None,
                 backend_rv_enabled=True):
        self._client = client
        self._calculator = calculator
        self._rr_calculator = rr_calculator
        self._history_store = history_store
        self._tenors = tenors
        self._poll_interval = poll_interval
        self._price_interval = price_interval
        self._currency = currency
        self._index_name = index_name
        self._ticker_store = ticker_store
        self._subscription_manager = subscription_manager
        self._ws_spot_stale = ws_spot_stale_seconds
        self._rv_calculator = rv_calculator
        self._perp_name = perp_name
        self._backend_rv_enabled = backend_rv_enabled

        self._latest_tenor_data = {}
        self._latest_price = {"price": None}
        self._tenor_lock = threading.Lock()
        self._price_lock = threading.Lock()

    def start(self):
        """Launch both daemon polling threads."""
        vol_thread = threading.Thread(target=self._poll_volatility, daemon=True)
        price_thread = threading.Thread(target=self._poll_price, daemon=True)
        vol_thread.start()
        price_thread.start()

    def get_latest_tenor_data(self):
        """Thread-safe read of the latest multi-tenor result."""
        with self._tenor_lock:
            return dict(self._latest_tenor_data)

    def get_latest_price(self):
        """Thread-safe read of the latest spot price."""
        with self._price_lock:
            return dict(self._latest_price)

    def _get_spot_price(self):
        """Get spot price, preferring WebSocket if available and fresh."""
        if self._ticker_store:
            ws_price = self._ticker_store.get_spot_price(self._index_name)
            age = self._ticker_store.get_spot_age_seconds(self._index_name)
            if ws_price is not None and age < self._ws_spot_stale:
                return ws_price
        return self._client.get_spot_price(self._index_name)

    def _compute_rv_results(self):
        """Compute backend RV when enabled.

        Production GCP blocks Binance (HTTP 451), so app.py disables this by
        default and the browser-side Binance path is the RV/carry source.
        """
        if not self._backend_rv_enabled or not self._rv_calculator or not self._perp_name:
            return {}
        try:
            return self._rv_calculator.compute_all_tenors(self._perp_name, self._tenors)
        except Exception:
            logger.exception("RV computation failed for %s", self._currency)
            return {}

    def _poll_volatility(self):
        """Continuously fetch options and compute multi-tenor vol + RR."""
        while True:
            try:
                spot = self._get_spot_price()
                options = self._client.get_options(self._currency)

                # 1. Compute ATM IV for all tenors
                multi = self._calculator.calculate_multi_tenor(
                    spot, options, self._tenors
                )

                # 1b. Update WebSocket subscriptions for RR-relevant tickers
                if self._subscription_manager:
                    self._subscription_manager.update_subscriptions(
                        self._currency, spot,
                        multi["expiry_data"], multi["expiry_days"],
                        multi.get("expiry_refs"),
                    )

                # 2. Compute 25d RR + raw 25d put/call IVs for all tenors.
                # Returns {label: {"rr_25d", "put_25d_iv", "call_25d_iv"}}.
                rr_results = self._rr_calculator.calculate(
                    spot,
                    multi["expiry_data"],
                    multi["expiry_days"],
                    multi["tenor_expiries"],
                    self._currency,
                    multi.get("expiry_refs"),
                )

                # 3. Compute realized volatility
                rv_results = self._compute_rv_results()

                # 4. Get DoD changes from history
                dod_changes = self._history_store.get_dod_changes(self._currency)

                # 5. Assemble tenor list
                tenor_list = []
                for tenor_cfg in self._tenors:
                    label = tenor_cfg["label"]
                    iv_info = multi["tenor_results"].get(label, {})
                    rr_info = rr_results.get(label) or {}
                    dod = dod_changes.get(label, {})

                    atm_iv = iv_info.get("atm_iv")
                    put_iv = rr_info.get("put_25d_iv")
                    call_iv = rr_info.get("call_25d_iv")

                    # 25d butterfly = 25d_call + 25d_put - 2 * ATM
                    # Trader premium convention: exactly 2x the half-sum
                    # convention. Positive = wings expensive relative to ATM.
                    bf_25d = compute_25d_fly(atm_iv, put_iv, call_iv)

                    tenor_list.append({
                        "label": label,
                        "target_days": tenor_cfg["days"],
                        "atm_iv": atm_iv,
                        "rr_25d": rr_info.get("rr_25d"),
                        # Raw 25Δ IVs exposed for frontend tooltip. These are
                        # NOT written to the DB — history.save_snapshot() only
                        # reads atm_iv/rr_25d/rv/bf_25d by name, so adding
                        # these keys is a pure pass-through for the API.
                        "put_25d_iv": put_iv,
                        "call_25d_iv": call_iv,
                        "bf_25d": bf_25d,
                        "rv": rv_results.get(label),
                        "dod_iv_change": dod.get("dod_iv_change"),
                        "dod_rr_change": dod.get("dod_rr_change"),
                        "dod_bf_change": dod.get("dod_bf_change"),
                        "change_hours": dod.get("change_hours"),
                        "method": iv_info.get("method"),
                        "error": iv_info.get("error"),
                    })

                # 6. Save snapshot to history
                self._history_store.save_snapshot(multi["timestamp"], tenor_list, self._currency)

                # 7. Store for API serving
                result = {
                    "timestamp": multi["timestamp"],
                    "spot_price": round(spot, 2),
                    "tenors": tenor_list,
                    "errors": [],
                }
                with self._tenor_lock:
                    self._latest_tenor_data = result

                computed = sum(1 for t in tenor_list if t["atm_iv"] is not None)
                logger.info("[%s] Poll complete: %d/%d tenors computed", self._currency, computed, len(self._tenors))


            except Exception:
                logger.exception("Volatility poll failed")
            time.sleep(self._poll_interval)

    def _poll_price(self):
        """Continuously update spot price, preferring WebSocket data."""
        while True:
            try:
                price = self._get_spot_price()
                with self._price_lock:
                    self._latest_price = {"price": round(price, 2)}
            except Exception:
                pass
            time.sleep(self._price_interval)
