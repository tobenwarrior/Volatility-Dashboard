"""
Data models for the Volatility Estimator.
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Optional


@dataclass
class OptionData:
    """A parsed option from the Deribit chain."""
    expiry: datetime
    strike: float
    opt_type: str  # "C" or "P"
    mark_iv: float


@dataclass
class TermInfo:
    """ATM volatility info for a single expiry term."""
    days: float
    iv: float
    expiry: str  # formatted date string
    strike: float

    def to_dict(self):
        return {
            "days": round(self.days, 1),
            "iv": round(self.iv, 2),
            "expiry": self.expiry,
            "strike": self.strike,
        }


@dataclass
class VolatilityResult:
    """Result of a 30-day volatility calculation."""
    timestamp: str
    target_date: str
    spot_price: float
    near_term: Optional[TermInfo]
    next_term: Optional[TermInfo]
    estimated_30d_vol: float
    method: str  # "variance_interpolation" or "exact_match"

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "target_date": self.target_date,
            "spot_price": round(self.spot_price, 2),
            "near_term": self.near_term.to_dict() if self.near_term else None,
            "next_term": self.next_term.to_dict() if self.next_term else None,
            "estimated_30d_vol": round(self.estimated_30d_vol, 2),
            "method": self.method,
        }


@dataclass
class TenorResult:
    """Result for a single tenor in the multi-tenor surface."""
    label: str           # "1W", "2W", "30D", "60D", "90D", "180D"
    target_days: int     # 7, 14, 30, 60, 90, 180
    atm_iv: Optional[float]
    rr_25d: Optional[float]
    dod_iv_change: Optional[float]
    dod_rr_change: Optional[float]
    method: Optional[str]
    error: Optional[str]

    def to_dict(self):
        return {
            "label": self.label,
            "target_days": self.target_days,
            "atm_iv": round(self.atm_iv, 2) if self.atm_iv is not None else None,
            "rr_25d": round(self.rr_25d, 2) if self.rr_25d is not None else None,
            "dod_iv_change": round(self.dod_iv_change, 2) if self.dod_iv_change is not None else None,
            "dod_rr_change": round(self.dod_rr_change, 2) if self.dod_rr_change is not None else None,
            "method": self.method,
            "error": self.error,
        }


@dataclass
class MultiTenorResult:
    """Result of a full multi-tenor volatility surface calculation."""
    timestamp: str
    spot_price: float
    tenors: List[TenorResult]
    errors: List[str]

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "spot_price": round(self.spot_price, 2),
            "tenors": [t.to_dict() for t in self.tenors],
            "errors": self.errors,
        }


@dataclass
class GreeksData:
    """Greeks for a specific option instrument."""
    instrument: str
    delta: Optional[float]
    gamma: Optional[float]
    vega: Optional[float]
    theta: Optional[float]
    rho: Optional[float]
    mark_iv: Optional[float]
    mark_price: Optional[float]
    underlying_price: Optional[float]

    def to_dict(self):
        return asdict(self)
