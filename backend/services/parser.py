"""
Deribit instrument name parser.
"""

import re
from datetime import datetime, timezone

from models.option import OptionData

_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

_MONTH_NAMES = {v: k for k, v in _MONTHS.items()}

# BTC-6MAR26-70000-C  or  ETH-28MAR25-4000-P
_INSTRUMENT_RE = re.compile(
    r"^(?:BTC|ETH)-(\d{1,2})([A-Z]{3})(\d{2})-(\d+)-([CP])$"
)


def parse_instrument_name(name):
    """Parse a Deribit instrument name into an OptionData (without mark_iv).

    Returns None if the name doesn't match the expected option format.
    Expiry is set to 08:00 UTC (Deribit settlement time).
    """
    m = _INSTRUMENT_RE.match(name)
    if not m:
        return None
    day = int(m.group(1))
    month = _MONTHS.get(m.group(2))
    if month is None:
        return None
    year = 2000 + int(m.group(3))
    strike = float(m.group(4))
    opt_type = m.group(5)
    expiry = datetime(year, month, day, 8, 0, 0, tzinfo=timezone.utc)
    return OptionData(expiry=expiry, strike=strike, opt_type=opt_type, mark_iv=0.0)


def format_instrument_name(currency, expiry_dt, strike, opt_type):
    """Build a Deribit instrument name from components.

    Args:
        currency: "BTC" or "ETH".
        expiry_dt: Expiry as a datetime object.
        strike: Strike price (int or float).
        opt_type: "C" or "P".

    Returns:
        String like "BTC-27MAR26-70000-C" or "ETH-27MAR26-4000-C".
    """
    month_str = _MONTH_NAMES[expiry_dt.month]
    year_str = str(expiry_dt.year % 100)
    return f"{currency}-{expiry_dt.day}{month_str}{year_str}-{int(strike)}-{opt_type}"
