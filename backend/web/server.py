"""
Flask application factory — JSON-only API (no HTML).
"""

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
        try:
            hours = float(request.args.get("hours", "24"))
        except (ValueError, TypeError):
            hours = 24.0
        try:
            from config import HISTORY_KEEP_DAYS
            max_hours = HISTORY_KEEP_DAYS * 24.0
        except Exception:
            max_hours = 4320.0
        hours = max(0.01, min(hours, max_hours))

        # Copy before overlaying range changes so the poller's latest snapshot
        # remains a pure live-data cache. Range selection is a read concern.
        data = pollers[currency].get_latest_tenor_data()
        result = dict(data)
        tenors_payload = [dict(t) for t in data.get("tenors", [])]
        changes = history_store.get_range_changes(hours, currency, latest_tenors=tenors_payload)
        for tenor in tenors_payload:
            change = changes.get(tenor.get("label"), {})
            tenor.update(change)
        result["tenors"] = tenors_payload
        result["change_hours_requested"] = hours
        return jsonify(result)

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
        try:
            from config import HISTORY_KEEP_DAYS
            max_hours = HISTORY_KEEP_DAYS * 24.0
        except Exception:
            max_hours = 4320.0
        hours = max(0.01, min(hours, max_hours))
        data = history_store.get_history(tenor, hours, currency)

        return jsonify(data)

    @app.route("/api/rv-series")
    def rv_series():
        """Return rolling hourly RV time series from Binance 1h candles."""
        currency = _get_currency()
        if currency is None:
            return jsonify({"error": "Invalid currency"}), 400
        tenor = request.args.get("tenor", "30D")
        if tenor not in tenor_days_map:
            return jsonify({"error": f"Invalid tenor: {tenor}"}), 400
        if not rv_calculator or not assets:
            return jsonify([])
        perp_name = assets.get(currency, {}).get("perp_name")
        if not perp_name:
            return jsonify([])
        series = rv_calculator.get_rolling_series(perp_name, tenor_days_map[tenor])
        # Return as sorted list of {time, rv} objects
        result = [{"time": ts, "rv": rv} for ts, rv in sorted(series.items())]
        return jsonify(result)

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
