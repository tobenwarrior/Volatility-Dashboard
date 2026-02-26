"""
Flask application factory — JSON-only API (no HTML).
"""

from flask import Flask, jsonify
from flask_cors import CORS


def create_app(poller):
    """Create and configure the Flask application.

    Args:
        poller: A Poller instance providing get_latest_tenor_data() and get_latest_price().
    """
    app = Flask(__name__)
    CORS(app)

    @app.route("/api/tenors")
    def tenors():
        return jsonify(poller.get_latest_tenor_data())

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
