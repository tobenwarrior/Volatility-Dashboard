"""
Background polling threads for spot price and multi-tenor volatility data.
"""

import logging
import threading
import time

CHECKPOINT_INTERVAL = 60  # flush WAL to .db every 60 seconds

logger = logging.getLogger(__name__)


class Poller:
    """Manages background threads that poll Deribit for price and volatility data."""

    def __init__(self, client, calculator, rr_calculator, history_store,
                 tenors, poll_interval=5, price_interval=1):
        self._client = client
        self._calculator = calculator
        self._rr_calculator = rr_calculator
        self._history_store = history_store
        self._tenors = tenors
        self._poll_interval = poll_interval
        self._price_interval = price_interval

        self._latest_tenor_data = {}
        self._latest_price = {"price": None}
        self._tenor_lock = threading.Lock()
        self._price_lock = threading.Lock()
        self._polls_since_checkpoint = 0

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

    def _poll_volatility(self):
        """Continuously fetch options and compute multi-tenor vol + RR."""
        while True:
            try:
                spot = self._client.get_spot_price()
                options = self._client.get_options()

                # 1. Compute ATM IV for all tenors
                multi = self._calculator.calculate_multi_tenor(
                    spot, options, self._tenors
                )

                # 2. Compute 25d RR for all tenors
                rr_results = self._rr_calculator.calculate(
                    spot,
                    multi["expiry_data"],
                    multi["expiry_days"],
                    multi["tenor_expiries"],
                )

                # 3. Get DoD changes from history
                dod_changes = self._history_store.get_dod_changes()

                # 4. Assemble tenor list
                tenor_list = []
                for tenor_cfg in self._tenors:
                    label = tenor_cfg["label"]
                    iv_info = multi["tenor_results"].get(label, {})
                    rr = rr_results.get(label)
                    dod = dod_changes.get(label, {})
                    tenor_list.append({
                        "label": label,
                        "target_days": tenor_cfg["days"],
                        "atm_iv": iv_info.get("atm_iv"),
                        "rr_25d": rr,
                        "dod_iv_change": dod.get("dod_iv_change"),
                        "dod_rr_change": dod.get("dod_rr_change"),
                        "change_hours": dod.get("change_hours"),
                        "method": iv_info.get("method"),
                        "error": iv_info.get("error"),
                    })

                # 5. Save snapshot to history
                self._history_store.save_snapshot(multi["timestamp"], tenor_list)

                # 6. Store for API serving
                result = {
                    "timestamp": multi["timestamp"],
                    "spot_price": round(spot, 2),
                    "tenors": tenor_list,
                    "errors": [],
                }
                with self._tenor_lock:
                    self._latest_tenor_data = result

                computed = sum(1 for t in tenor_list if t["atm_iv"] is not None)
                logger.info("Poll complete: %d/%d tenors computed", computed, len(self._tenors))

                # Periodically flush WAL so .db file is always self-contained
                self._polls_since_checkpoint += 1
                if self._polls_since_checkpoint * self._poll_interval >= CHECKPOINT_INTERVAL:
                    self._history_store.checkpoint()
                    self._polls_since_checkpoint = 0

            except Exception:
                logger.exception("Volatility poll failed")
            time.sleep(self._poll_interval)

    def _poll_price(self):
        """Continuously fetch spot price."""
        while True:
            try:
                price = self._client.get_spot_price()
                with self._price_lock:
                    self._latest_price = {"price": round(price, 2)}
            except Exception:
                pass
            time.sleep(self._price_interval)
