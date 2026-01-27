"""
Universal Computation Schemas
Pydantic models for universal computation requests and responses
"""
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, validator


class AssetTypeEnum(str, Enum):
    """Supported asset types"""
    EQUITY = "equity"
    FUTURES = "futures"
    OPTIONS = "options"
    INDEX = "index"
    COMMODITY = "commodity"
    CURRENCY = "currency"
    CRYPTO = "crypto"


class ComputationModeEnum(str, Enum):
    """Computation modes"""
    REALTIME = "realtime"
    HISTORICAL = "historical"
    BATCH = "batch"


class TimeframeEnum(str, Enum):
    """Supported timeframes"""
    TICK = "tick"
    MIN_1 = "1m"
    MIN_5 = "5m"
    MIN_15 = "15m"
    MIN_30 = "30m"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1d"
    WEEK_1 = "1w"
    MONTH_1 = "1M"


class ComputationRequest(BaseModel):
    """Single computation request"""
    type: str = Field(..., description="Type of computation (indicator, greeks, moneyness, etc.)")
    name: str | None = Field(None, description="Optional name for the result")
    params: dict[str, Any] = Field(default_factory=dict, description="Computation parameters")

    @validator('type')
    def validate_type(cls, v):
        if not v:
            raise ValueError("Computation type cannot be empty")
        return v.lower()


class UniversalComputeRequest(BaseModel):
    """Universal computation request"""
    asset_type: AssetTypeEnum = Field(..., description="Asset type")
    instrument_key: str = Field(..., description="Universal instrument key")
    computations: list[ComputationRequest] = Field(..., description="List of computations to perform")
    timeframe: TimeframeEnum = Field(TimeframeEnum.MIN_5, description="Timeframe for data")
    mode: ComputationModeEnum = Field(ComputationModeEnum.REALTIME, description="Computation mode")
    context: dict[str, Any] | None = Field(
        default_factory=dict,
        description="Additional context (spot price, risk-free rate, etc.)"
    )

    @validator('computations')
    def validate_computations(cls, v):
        if not v:
            raise ValueError("At least one computation must be specified")
        return v

    @validator('instrument_key')
    def validate_instrument_key(cls, v):
        if not v:
            raise ValueError("Instrument key cannot be empty")
        return v


class ComputationResult(BaseModel):
    """Result of a single computation"""
    name: str
    value: Any | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None
    timestamp: datetime | None = None
    cached: bool | None = False
    execution_time_ms: float | None = None


class UniversalComputeResponse(BaseModel):
    """Universal computation response"""
    instrument_key: str
    asset_type: str
    timestamp: datetime
    computations: dict[str, Any]
    metadata: dict[str, Any]
    execution_time_ms: float

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class BatchComputeRequest(BaseModel):
    """Batch computation request for multiple instruments"""
    instruments: list[str] = Field(..., description="List of instrument keys")
    computations: list[ComputationRequest] = Field(..., description="Computations to perform")
    asset_type: AssetTypeEnum = Field(..., description="Asset type for all instruments")
    timeframe: TimeframeEnum = Field(TimeframeEnum.MIN_5, description="Timeframe for data")
    context: dict[str, Any] | None = Field(
        default_factory=dict,
        description="Global context for all computations"
    )

    @validator('instruments')
    def validate_instruments(cls, v):
        if not v:
            raise ValueError("At least one instrument must be specified")
        if len(v) > 100:  # Reasonable limit
            raise ValueError("Maximum 100 instruments per batch request")
        return v


class BatchComputeResponse(BaseModel):
    """Batch computation response"""
    asset_type: str
    timestamp: datetime
    instruments_processed: int
    successful: int
    failed: int
    results: dict[str, dict[str, Any]]
    errors: dict[str, str] | None = None
    execution_time_ms: float

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ComputationMetadataSchema(BaseModel):
    """Schema for computation metadata"""
    name: str
    description: str
    asset_types: list[str]
    parameters: dict[str, Any]
    returns: dict[str, Any]
    tags: list[str]
    version: str
    examples: list[dict[str, Any]]
    created_at: datetime
    last_updated: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ComputationValidationRequest(BaseModel):
    """Request for computation validation"""
    computation_type: str = Field(..., description="Type of computation to validate")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Parameters to validate")
    asset_type: AssetTypeEnum = Field(..., description="Asset type context")


class ComputationValidationResponse(BaseModel):
    """Response for computation validation"""
    valid: bool
    computation_type: str
    asset_type: str
    errors: list[str] | None = None
    warnings: list[str] | None = None
    validated_parameters: dict[str, Any] | None = None


class FormulaValidationRequest(BaseModel):
    """Request for formula validation"""
    formula: str = Field(..., description="Formula to validate")
    context_variables: list[str] | None = Field(
        default_factory=list,
        description="Expected context variables"
    )


class FormulaValidationResponse(BaseModel):
    """Response for formula validation"""
    valid: bool
    formula: str
    variables: list[str]
    functions: list[str]
    errors: list[str] | None = None
    warnings: list[str] | None = None


class IndicatorRequest(BaseModel):
    """Request for technical indicator calculation"""
    indicator: str = Field(..., description="Indicator name")
    period: int | None = Field(20, description="Calculation period")
    params: dict[str, Any] | None = Field(
        default_factory=dict,
        description="Additional indicator parameters"
    )


class GreeksRequest(BaseModel):
    """Request for Greeks calculation"""
    model: str = Field("black-scholes", description="Pricing model")
    risk_free_rate: float = Field(0.05, description="Risk-free rate")
    volatility: float | None = Field(None, description="Implied volatility override")


class MoneynessRequest(BaseModel):
    """Request for moneyness calculation"""
    reference: str = Field("spot", description="Reference for moneyness")
    classification: bool = Field(True, description="Include moneyness classification")


class VolatilityRequest(BaseModel):
    """Request for volatility calculation"""
    type: str = Field("historical", description="Type of volatility")
    period: int = Field(20, description="Calculation period")
    annualize: bool = Field(True, description="Annualize the result")


class RiskMetricsRequest(BaseModel):
    """Request for risk metrics calculation"""
    metrics: list[str] = Field(
        default_factory=lambda: ["var", "sharpe", "max_drawdown"],
        description="List of risk metrics to calculate"
    )
    period: int = Field(252, description="Lookback period")
    confidence_level: float = Field(0.95, description="Confidence level for VaR")


class CustomFormulaRequest(BaseModel):
    """Request for custom formula calculation"""
    formula: str = Field(..., description="Mathematical formula")
    context: dict[str, Any] | None = Field(
        default_factory=dict,
        description="Context variables for formula"
    )
    validate_only: bool = Field(False, description="Only validate, don't execute")


class ComputationCapability(BaseModel):
    """Information about computation capabilities"""
    computation_type: str
    supported_assets: list[str]
    required_params: list[str]
    optional_params: list[str]
    description: str
    examples: list[str]


class UniversalHealthResponse(BaseModel):
    """Health check response for universal computation engine"""
    status: str
    service: str
    timestamp: datetime
    capabilities: dict[str, Any]

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ComputationHistory(BaseModel):
    """Historical computation record"""
    request_id: str
    timestamp: datetime
    asset_type: str
    instrument_key: str
    computation_type: str
    parameters: dict[str, Any]
    result: Any | None = None
    error: str | None = None
    execution_time_ms: float
    cached: bool = False

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class StreamingComputationRequest(BaseModel):
    """Request for streaming computation"""
    subscription_id: str = Field(..., description="Unique subscription ID")
    asset_type: AssetTypeEnum = Field(..., description="Asset type")
    instrument_key: str = Field(..., description="Instrument to monitor")
    computations: list[ComputationRequest] = Field(..., description="Computations to perform")
    frequency: str = Field("tick", description="Update frequency")
    conditions: dict[str, Any] | None = Field(
        default_factory=dict,
        description="Conditions for triggering updates"
    )


class StreamingComputationResponse(BaseModel):
    """Response for streaming computation"""
    subscription_id: str
    timestamp: datetime
    instrument_key: str
    asset_type: str
    computations: dict[str, Any]
    sequence_number: int

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ComputationTemplate(BaseModel):
    """Template for common computation patterns"""
    name: str
    description: str
    asset_types: list[str]
    computations: list[ComputationRequest]
    context_template: dict[str, Any]
    examples: list[dict[str, Any]]
    tags: list[str]
    created_by: str
    created_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AssetSpecificContext(BaseModel):
    """Asset-specific context for computations"""
    asset_type: AssetTypeEnum
    required_fields: list[str]
    optional_fields: list[str]
    validation_rules: dict[str, Any]
    default_values: dict[str, Any]


class ComputationError(BaseModel):
    """Standardized error response"""
    error_code: str
    message: str
    details: dict[str, Any] | None = None
    timestamp: datetime
    request_id: str | None = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
