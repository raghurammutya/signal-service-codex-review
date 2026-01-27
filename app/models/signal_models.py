from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class SignalGreeks:
    instrument_key: str
    timestamp: datetime
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    implied_volatility: float = 0.0
    theoretical_value: float = 0.0
    underlying_price: float = 0.0
    strike_price: float = 0.0
    time_to_expiry: float = 0.0
    signal_id: int = 0
    id: int = 0


@dataclass
class SignalIndicators:
    instrument_key: str
    timestamp: datetime
    indicator_name: str
    parameters: dict[str, Any]
    values: dict[str, Any]
    signal_id: int = 0
    id: int = 0


@dataclass
class MoneynessHistory:
    instrument_key: str
    timestamp: datetime
    moneyness_level: str
    value: float
    id: int = 0
