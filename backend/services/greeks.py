"""
Greeks fetching service for individual options.
"""

from models.option import GreeksData


class GreeksService:
    """Fetches greeks for a specific BTC option via the ticker endpoint."""

    def __init__(self, client):
        self._client = client

    def get_greeks(self, strike, expiry_str, opt_type="P"):
        """Get greeks for a BTC option by strike, expiry, and type.

        Args:
            strike: Strike price (e.g., 62000).
            expiry_str: Expiry in Deribit format (e.g., "27MAR26").
            opt_type: "P" for put, "C" for call.

        Returns:
            GreeksData with delta, gamma, vega, theta, rho, and pricing info.
        """
        instrument = f"BTC-{expiry_str}-{int(strike)}-{opt_type.upper()}"
        ticker = self._client.get_ticker(instrument)
        greeks = ticker.get("greeks", {})
        return GreeksData(
            instrument=instrument,
            delta=greeks.get("delta"),
            gamma=greeks.get("gamma"),
            vega=greeks.get("vega"),
            theta=greeks.get("theta"),
            rho=greeks.get("rho"),
            mark_iv=ticker.get("mark_iv"),
            mark_price=ticker.get("mark_price"),
            underlying_price=ticker.get("underlying_price"),
        )
