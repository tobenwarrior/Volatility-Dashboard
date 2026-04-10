"""
Background polling threads for spot price and multi-tenor volatility data.
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)


class Poller:
    """Manages background threads that poll Deribit for price and volatility data."""

    def __init__(self, client, calculator, rr_calculator, history_store,
                 tenors, poll_interval=5, price_interval=1,
                 currency="BTC", index_name="btc_usd",
                 ticker_store=None, subscription_manager=None,
                 ws_spot_stale_seconds=5,
                 rv_calculator=None, perp_name=None):
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
                    )

                # 2. Compute 25d RR + raw 25d put/call IVs for all tenors.
                # Returns {label: {"rr_25d", "put_25d_iv", "call_25d_iv"}}.
                rr_results = self._rr_calculator.calculate(
                    spot,
                    multi["expiry_data"],
                    multi["expiry_days"],
                    multi["tenor_expiries"],
                    self._currency,
                )

                # 3. Compute realized volatility
                rv_results = {}
                if self._rv_calculator and self._perp_name:
                    try:
                        rv_results = self._rv_calculator.compute_all_tenors(
                            self._perp_name, self._tenors
                        )
                    except Exception:
                        logger.exception("RV computation failed for %s", self._currency)

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

                    # 25d butterfly = (25d_call + 25d_put) / 2 - ATM
                    # Market convention (Bloomberg/Deribit): measures smile
                    # convexity (kurtosis proxy). Positive = wings expensive
                    # relative to ATM.
                    if atm_iv is not None and put_iv is not None and call_iv is not None:
                        bf_25d = (call_iv + put_iv) / 2 - atm_iv
                    else:
                        bf_25d = None

                    tenor_list.append({
                        "label": label,
                        "target_days": tenor_cfg["days"],
                        "atm_iv": atm_iv,
                        "rr_25d": rr_info.get("rr_25d"),
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
