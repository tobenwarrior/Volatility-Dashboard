"""
Volatility Estimator — Entry Point

Wires together all dependencies and starts the Flask server.
"""

import logging
import os

from config import (
    DERIBIT_BASE, REQUEST_TIMEOUT, POLL_INTERVAL, PRICE_INTERVAL,
    TARGET_DAYS, TENORS, TARGET_DELTA, TICKER_CANDIDATES_PER_SIDE,
    ASSETS, DERIBIT_WS_URL, WS_SPOT_STALE_SECONDS,
)
from api.client import DeribitClient
from services.volatility import VolatilityCalculator
from services.risk_reversal import RiskReversalCalculator
from services.history import HistoryStore
from services.realized_vol import RealizedVolCalculator
from ws.ticker_store import TickerDataStore
from ws.client import DeribitWSClient
from ws.subscription_manager import SubscriptionManager
from web.poller import Poller
from web.server import create_app

BASE_PORT = int(os.environ.get("PORT", 5000))


# --- Shared dependencies ---
client = DeribitClient(base_url=DERIBIT_BASE, timeout=REQUEST_TIMEOUT)
calculator = VolatilityCalculator(target_days=TARGET_DAYS)

# --- WebSocket infrastructure ---
ticker_store = TickerDataStore()
ws_client = DeribitWSClient(ticker_store, url=DERIBIT_WS_URL)
ws_client.start()

# Subscribe to spot price channels for all assets
spot_channels = [f"deribit_price_index.{cfg['index_name']}" for cfg in ASSETS.values()]
ws_client.subscribe(spot_channels)

subscription_manager = SubscriptionManager(
    ws_client,
    target_delta=TARGET_DELTA,
    candidates_per_side=TICKER_CANDIDATES_PER_SIDE,
)

rr_calculator = RiskReversalCalculator(
    target_delta=TARGET_DELTA,
    ticker_store=ticker_store,
)
history_store = HistoryStore()
rv_calculator = RealizedVolCalculator(client)

# --- One poller per asset ---
pollers = {}
for currency, asset_cfg in ASSETS.items():
    poller = Poller(
        client, calculator, rr_calculator, history_store,
        TENORS, POLL_INTERVAL, PRICE_INTERVAL,
        currency=currency,
        index_name=asset_cfg["index_name"],
        ticker_store=ticker_store,
        subscription_manager=subscription_manager,
        ws_spot_stale_seconds=WS_SPOT_STALE_SECONDS,
        rv_calculator=rv_calculator,
        perp_name=asset_cfg["perp_name"],
    )
    poller.start()
    pollers[currency] = poller

app = create_app(pollers, history_store, rv_calculator=rv_calculator, assets=ASSETS, tenors=TENORS)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.info("Starting on port %d", BASE_PORT)
    app.run(host="0.0.0.0", port=BASE_PORT, debug=False)
