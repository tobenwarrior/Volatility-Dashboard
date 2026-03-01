"""
Volatility Estimator — Entry Point

Wires together all dependencies and starts the Flask server.
"""

import logging
import os
import socket

from config import (
    DERIBIT_BASE, REQUEST_TIMEOUT, POLL_INTERVAL, PRICE_INTERVAL,
    TARGET_DAYS, TENORS, DB_PATH, TARGET_DELTA, TICKER_CANDIDATES_PER_SIDE,
    ASSETS,
)
from api.client import DeribitClient
from services.volatility import VolatilityCalculator
from services.risk_reversal import RiskReversalCalculator
from services.history import HistoryStore
from web.poller import Poller
from web.server import create_app

BASE_PORT = 5000
PORT_FILE = os.path.join(os.path.dirname(__file__), ".port")


def find_free_port(start=BASE_PORT, attempts=10):
    """Return the first available port starting from *start*."""
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}-{start + attempts - 1}")


# --- Shared dependencies ---
client = DeribitClient(base_url=DERIBIT_BASE, timeout=REQUEST_TIMEOUT)
calculator = VolatilityCalculator(target_days=TARGET_DAYS)
rr_calculator = RiskReversalCalculator(
    client,
    target_delta=TARGET_DELTA,
    candidates_per_side=TICKER_CANDIDATES_PER_SIDE,
)
history_store = HistoryStore(db_path=DB_PATH)

# --- One poller per asset ---
pollers = {}
for currency, asset_cfg in ASSETS.items():
    poller = Poller(
        client, calculator, rr_calculator, history_store,
        TENORS, POLL_INTERVAL, PRICE_INTERVAL,
        currency=currency,
        index_name=asset_cfg["index_name"],
    )
    poller.start()
    pollers[currency] = poller

app = create_app(pollers, history_store)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    port = find_free_port()
    # Write port so the frontend proxy can pick it up
    with open(PORT_FILE, "w") as f:
        f.write(str(port))
    if port != BASE_PORT:
        logging.info("Port %d in use — falling back to %d", BASE_PORT, port)
    app.run(host="0.0.0.0", port=port, debug=False)
