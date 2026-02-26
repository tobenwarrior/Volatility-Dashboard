"""
Flask application factory — JSON-only API (no HTML).
"""

from flask import Flask, jsonify, request
from flask_cors import CORS


def create_app(poller, history_store):
    """Create and configure the Flask application.

    Args:
        poller: A Poller instance providing get_latest_tenor_data() and get_latest_price().
        history_store: A HistoryStore instance for querying historical data.
    """
    app = Flask(__name__)
    CORS(app)

    @app.route("/api/tenors")
    def tenors():
        return jsonify(poller.get_latest_tenor_data())

    @app.route("/api/history")
    def history():
        tenor = request.args.get("tenor", "30D")
        valid_tenors = {"1W", "2W", "30D", "60D", "90D", "180D"}
        if tenor not in valid_tenors:
            return jsonify({"error": f"Invalid tenor: {tenor}"}), 400
        try:
            hours = float(request.args.get("hours", "48"))
        except (ValueError, TypeError):
            hours = 48.0
        hours = max(0.01, min(hours, 336.0))
        data = history_store.get_history(tenor, hours)
        return jsonify(data)

    @app.route("/api/data")
    def data():
        """Backwards-compatible endpoint — extracts 30D from multi-tenor data."""
        tenor_data = poller.get_latest_tenor_data()
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
        return jsonify(poller.get_latest_price())

    return app
