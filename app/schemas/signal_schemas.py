"""
Pydantic schemas for Signal Service v2 API
"""
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, validator


class BaseResponse(BaseModel):
    """Base response model for API endpoints"""
    success: bool = True
    message: str | None = None
    data: Any | None = None
    error: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SignalType(str, Enum):
    """Types of signals"""
    GREEKS = "greeks"
    INDICATORS = "indicators"
    MONEYNESS_GREEKS = "moneyness_greeks"


class TimeframeType(str, Enum):
    """Timeframe types"""
    STANDARD = "standard"
    CUSTOM = "custom"


class GreeksData(BaseModel):
    """Greeks values"""
    delta: float | None = Field(None, ge=-1, le=1)
    gamma: float | None = Field(None, ge=0)
    theta: float | None = Field(None)
    vega: float | None = Field(None, ge=0)
    rho: float | None = Field(None)
    implied_volatility: float | None = Field(None, ge=0, le=5, alias="iv")


class GreeksResponse(BaseModel):
    """Response for real-time Greeks"""
    instrument_key: str
    timestamp: datetime
    greeks: GreeksData
    underlying_price: float | None = None
    option_price: float | None = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class IndicatorResponse(BaseModel):
    """Response for real-time indicator"""
    instrument_key: str
    indicator: str
    period: int
    timestamp: datetime
    value: float | dict[str, float]
    metadata: dict[str, Any] | None = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AggregatedGreeks(BaseModel):
    """Aggregated Greeks for moneyness level"""
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    iv: float
    count: int


class MoneynessGreeksData(BaseModel):
    """Moneyness Greeks aggregation"""
    all: AggregatedGreeks | None = None
    calls: AggregatedGreeks | None = None
    puts: AggregatedGreeks | None = None


class MoneynessGreeksResponse(BaseModel):
    """Response for moneyness-based Greeks"""
    underlying: str
    spot_price: float
    moneyness_level: str
    timestamp: datetime
    aggregated_greeks: MoneynessGreeksData
    strikes: dict[str, Any] | None = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class TimeSeriesDataPoint(BaseModel):
    """Single data point in time series"""
    timestamp: datetime
    value: float | dict[str, Any]
    metadata: dict[str, Any] | None = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class HistoricalGreeksResponse(BaseModel):
    """Response for historical Greeks"""
    instrument_key: str
    start_time: datetime
    end_time: datetime
    timeframe: str
    data_points: int
    time_series: list[TimeSeriesDataPoint]

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class HistoricalIndicatorResponse(BaseModel):
    """Response for historical indicator"""
    instrument_key: str
    indicator: str
    period: int
    start_time: datetime
    end_time: datetime
    timeframe: str
    data_points: int
    time_series: list[TimeSeriesDataPoint]

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class HistoricalMoneynessResponse(BaseModel):
    """Response for historical moneyness Greeks"""
    underlying: str
    moneyness_level: str
    start_time: datetime
    end_time: datetime
    timeframe: str
    expiry_date: str | None = None
    data_points: int
    time_series: list[TimeSeriesDataPoint]

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class SubscriptionRequest(BaseModel):
    """WebSocket subscription request"""
    type: Literal["subscribe"] = "subscribe"
    channel: SignalType
    instrument_key: str
    params: dict[str, Any] | None = None


class SubscriptionResponse(BaseModel):
    """WebSocket subscription response"""
    type: Literal["subscription"] = "subscription"
    status: str
    channel: str
    instrument_key: str
    subscription_key: str | None = None
    timestamp: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class WebSocketMessage(BaseModel):
    """Generic WebSocket message"""
    type: str
    timestamp: datetime
    data: dict[str, Any] | None = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class SignalComputeRequest(BaseModel):
    """Request to compute signals"""
    instrument_key: str
    signal_types: list[SignalType]
    params: dict[str, Any] | None = None


class SignalComputeResponse(BaseModel):
    """Response for signal computation"""
    instrument_key: str
    timestamp: datetime
    results: dict[str, Any]
    computation_time_ms: float

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class TimeframeRequest(BaseModel):
    """Request for custom timeframe"""
    timeframe: str

    @validator('timeframe')
    def validate_timeframe(self, v):
        """Validate timeframe format"""
        if v.endswith('m'):
            try:
                minutes = int(v[:-1])
                if not 1 <= minutes <= 1440:
                    raise ValueError("Minutes must be between 1 and 1440")
            except ValueError as e:
                raise ValueError("Invalid minute format") from e
        elif v.endswith('h'):
            try:
                hours = int(v[:-1])
                if not 1 <= hours <= 24:
                    raise ValueError("Hours must be between 1 and 24")
            except ValueError as e:
                raise ValueError("Invalid hour format") from e
        elif v.endswith('d'):
            try:
                days = int(v[:-1])
                if not 1 <= days <= 30:
                    raise ValueError("Days must be between 1 and 30")
            except ValueError as e:
                raise ValueError("Invalid day format") from e
        else:
            raise ValueError("Timeframe must end with 'm', 'h', or 'd'")
        return v


class BatchGreeksRequest(BaseModel):
    """Request for batch Greeks calculation"""
    instrument_keys: list[str] = Field(..., min_items=1, max_items=100)
    compute_moneyness: bool = False


class BatchGreeksResponse(BaseModel):
    """Response for batch Greeks calculation"""
    timestamp: datetime
    results: dict[str, GreeksData]
    errors: dict[str, str] | None = None
    computation_time_ms: float

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# Signal Execution Schemas (Sprint 5A)

class SignalExecutionRequest(BaseModel):
    """Request to execute marketplace signal script"""
    execution_token: str = Field(..., description="Token from marketplace subscription")
    product_id: str = Field(..., description="Marketplace product ID")
    instrument: str = Field(..., description="Instrument to run signal for")
    params: dict[str, Any] | None = Field(None, description="Signal parameters")
    subscription_id: str | None = Field(None, description="Subscription ID for watermarking")


class PersonalSignalExecutionRequest(BaseModel):
    """Request to execute personal signal script"""
    script_id: str = Field(..., description="Personal script ID from MinIO")
    instrument: str = Field(..., description="Instrument to run signal for")
    params: dict[str, Any] | None = Field(None, description="Signal parameters")


class SignalExecutionResponse(BaseModel):
    """Response for signal execution"""
    success: bool
    message: str
    execution_id: str | None = None
    stream_keys: list[str] | None = Field(None, description="Redis stream keys for results")
    error: str | None = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
