"""
Flask application factory — JSON-only API (no HTML).
"""

from datetime import datetime, timezone
from flask import Flask, jsonify, request
from flask_cors import CORS

VALID_CURRENCIES = {"BTC", "ETH"}


def create_app(pollers, history_store, rv_calculator=None, assets=None, tenors=None):
    """Create and configure the Flask application.

    Args:
        pollers: Dict mapping currency to Poller instance, e.g. {"BTC": ..., "ETH": ...}.
        history_store: A HistoryStore instance for querying historical data.
        rv_calculator: Optional RealizedVolCalculator for rolling RV overlay.
        assets: Optional ASSETS config dict for perp_name lookup.
        tenors: Optional TENORS config list for tenor days lookup.
    """
    app = Flask(__name__)
    CORS(app)

    # Build tenor label -> days lookup
    tenor_days_map = {}
    if tenors:
        tenor_days_map = {t["label"]: t["days"] for t in tenors}

    def _get_currency():
        """Extract and validate currency query param (default BTC)."""
        currency = request.args.get("currency", "BTC").upper()
        if currency not in VALID_CURRENCIES:
            return None
        return currency

    @app.route("/api/tenors")
    def tenors_endpoint():
        currency = _get_currency()
        if currency is None:
            return jsonify({"error": "Invalid currency"}), 400
        return jsonify(pollers[currency].get_latest_tenor_data())

    @app.route("/api/history")
    def history():
        currency = _get_currency()
        if currency is None:
            return jsonify({"error": "Invalid currency"}), 400
        tenor = request.args.get("tenor", "30D")
        valid_tenors = {"1W", "2W", "30D", "60D", "90D", "180D"}
        if tenor not in valid_tenors:
            return jsonify({"error": f"Invalid tenor: {tenor}"}), 400
        try:
            hours = float(request.args.get("hours", "48"))
        except (ValueError, TypeError):
            hours = 48.0
        hours = max(0.01, min(hours, 744.0))
        data = history_store.get_history(tenor, hours, currency)

        # Merge rolling RV time series (hourly) into history points
        if rv_calculator and assets and tenor in tenor_days_map:
            perp_name = assets.get(currency, {}).get("perp_name")
            if perp_name:
                rv_series = rv_calculator.get_rolling_series(
                    perp_name, tenor_days_map[tenor]
                )
                if rv_series:
                    for point in data:
                        dt = datetime.fromtimestamp(point["time"], tz=timezone.utc)
                        hour_key = dt.strftime("%Y-%m-%d %H")
                        rv_val = rv_series.get(hour_key)
                        if rv_val is not None:
                            point["rv"] = rv_val

        return jsonify(data)

    @app.route("/api/vol-stats")
    def vol_stats():
        currency = _get_currency()
        if currency is None:
            return jsonify({"error": "Invalid currency"}), 400
        try:
            hours = float(request.args.get("hours", "0"))
        except (ValueError, TypeError):
            hours = 0
        # 0 means all available data
        data = history_store.get_vol_stats(hours if hours > 0 else None, currency)
        return jsonify(data)

    @app.route("/api/data")
    def data():
        """Backwards-compatible endpoint — extracts 30D from multi-tenor data."""
        currency = _get_currency()
        if currency is None:
            return jsonify({"error": "Invalid currency"}), 400
        tenor_data = pollers[currency].get_latest_tenor_data()
        if not tenor_data or not tenor_data.get("tenors"):
            return jsonify({})
        thirty = next(
            (t for t in tenor_data["tenors"] if t["target_days"] == 30), None
        )
        if thirty and thirty.get("atm_iv") is not None:
            return jsonify({
                "timestamp": tenor_data["timestamp"],
                "spot_price": tenor_data["spot_price"],
                "estimated_30d_vol": thirty["atm_iv"],
                "method": thirty.get("method"),
            })
        return jsonify({})

    @app.route("/api/price")
    def price():
        currency = _get_currency()
        if currency is None:
            return jsonify({"error": "Invalid currency"}), 400
        return jsonify(pollers[currency].get_latest_price())

    return app
