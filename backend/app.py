"""
Volatility Estimator — Entry Point

Wires together all dependencies and starts the Flask server.
"""

import logging

from config import (
    DERIBIT_BASE, REQUEST_TIMEOUT, POLL_INTERVAL, PRICE_INTERVAL,
    TARGET_DAYS, TENORS, DB_PATH, TARGET_DELTA, TICKER_CANDIDATES_PER_SIDE,
)
from api.client import DeribitClient
from services.volatility import VolatilityCalculator
from services.risk_reversal import RiskReversalCalculator
from services.history import HistoryStore
from web.poller import Poller
from web.server import create_app

# --- Dependency injection ---
client = DeribitClient(base_url=DERIBIT_BASE, timeout=REQUEST_TIMEOUT)
calculator = VolatilityCalculator(target_days=TARGET_DAYS)
rr_calculator = RiskReversalCalculator(
    client,
    target_delta=TARGET_DELTA,
    candidates_per_side=TICKER_CANDIDATES_PER_SIDE,
)
history_store = HistoryStore(db_path=DB_PATH)
poller = Poller(
    client, calculator, rr_calculator, history_store,
    TENORS, POLL_INTERVAL, PRICE_INTERVAL,
)
poller.start()

app = create_app(poller)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    app.run(host="0.0.0.0", port=5000, debug=False)
