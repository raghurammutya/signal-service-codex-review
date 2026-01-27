"""Configuration schemas for Signal Service"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator


class BaseSchema(BaseModel):
    """Base schema class"""


class FrequencyType(str, Enum):
    """Signal computation frequency types"""
    EVERY_TICK = "every_tick"
    EVERY_SECOND = "every_second"
    EVERY_MINUTE = "every_minute"
    EVERY_INTERVAL = "every_interval"
    ON_CLOSE = "on_close"


class IntervalType(str, Enum):
    """Time interval types"""
    ONE_MINUTE = "1minute"
    FIVE_MINUTE = "5minute"
    FIFTEEN_MINUTE = "15minute"
    THIRTY_MINUTE = "30minute"
    ONE_HOUR = "1hour"
    FOUR_HOUR = "4hour"
    ONE_DAY = "1day"
    ONE_WEEK = "1week"
    ONE_MONTH = "1month"


class TechnicalIndicatorConfig(BaseModel):
    """Configuration for a technical indicator"""
    name: str = Field(..., description="Indicator name (e.g., sma, ema, rsi)")
    parameters: dict[str, Any] = Field(..., description="Indicator parameters")
    output_key: str = Field(..., description="Key to store output in results")

    @validator('name')
    def validate_indicator_name(cls, v):
        """Validate indicator name"""
        valid_indicators = [
            'sma', 'ema', 'rsi', 'macd', 'bb', 'stoch', 'adx', 'atr',
            'cci', 'mfi', 'obv', 'vwap', 'pivot', 'supertrend', 'ichimoku',
            'kama', 'ppo', 'roc', 'willr', 'ultosc', 'mom', 'trix'
        ]
        if v.lower() not in valid_indicators:
            raise ValueError(f'Invalid indicator: {v}. Must be one of {valid_indicators}')
        return v.lower()


class OptionGreeksConfig(BaseModel):
    """Configuration for option Greeks calculation"""
    enabled: bool = Field(False, description="Enable Greeks calculation")
    underlying_symbol: str | None = Field(None, description="Underlying symbol for options")
    risk_free_rate: float = Field(0.06, description="Risk-free rate for calculations", ge=0, le=1)
    calculate: list[str] = Field(
        ['delta', 'gamma', 'theta', 'vega'],
        description="Greeks to calculate"
    )
    use_indvix: bool = Field(True, description="Use INDVIX for volatility")

    @validator('calculate')
    def validate_greeks(cls, v):
        """Validate Greek names"""
        valid_greeks = ['delta', 'gamma', 'theta', 'vega', 'rho']
        for greek in v:
            if greek not in valid_greeks:
                raise ValueError(f'Invalid Greek: {greek}. Must be one of {valid_greeks}')
        return v


class InternalFunctionConfig(BaseModel):
    """Configuration for internal Python functions"""
    name: str = Field(..., description="Function name")
    function_type: str = Field('builtin', description="Function type")
    parameters: dict[str, Any] = Field({}, description="Function parameters")
    timeout: int = Field(5, description="Timeout in seconds", ge=1, le=30)


class ExternalFunctionConfig(BaseModel):
    """Configuration for external Python functions"""
    name: str = Field(..., description="Function name")
    file_path: str = Field(..., description="Path to Python file")
    function_name: str = Field(..., description="Function name in file")
    parameters: dict[str, Any] = Field({}, description="Function parameters")
    timeout: int = Field(5, description="Timeout in seconds", ge=1, le=30)
    memory_limit_mb: int = Field(50, description="Memory limit in MB", ge=10, le=200)


class OutputConfig(BaseModel):
    """Configuration for output settings"""
    publish_to_redis: bool = Field(True, description="Publish results to Redis")
    redis_stream: str | None = Field(None, description="Redis stream for output")
    redis_list: str | None = Field(None, description="Redis list for output")
    store_to_database: bool = Field(False, description="Store results to TimescaleDB")
    webhook_urls: list[str] = Field([], description="Webhook URLs for notifications")
    cache_results: bool = Field(True, description="Cache computation results")
    cache_ttl_seconds: int = Field(300, description="Cache TTL in seconds", ge=60, le=3600)


class SignalConfigData(BaseModel):
    """Complete signal configuration data"""
    version: str = Field('1.0', description="Configuration version")
    instrument_key: str = Field(..., description="Instrument key")
    interval: IntervalType = Field(..., description="Time interval")
    frequency: FrequencyType = Field(..., description="Calculation frequency")

    # Computation configurations
    technical_indicators: list[TechnicalIndicatorConfig] = Field(
        [], description="Technical indicators to compute"
    )
    option_greeks: OptionGreeksConfig | None = Field(
        None, description="Option Greeks configuration"
    )
    internal_functions: list[InternalFunctionConfig] = Field(
        [], description="Internal functions to execute"
    )
    external_functions: list[ExternalFunctionConfig] = Field(
        [], description="External functions to execute"
    )

    # Output configuration
    output: OutputConfig = Field(OutputConfig(), description="Output configuration")

    # Processing options
    parallel_execution: bool = Field(True, description="Execute computations in parallel")
    max_concurrent: int = Field(5, description="Maximum concurrent computations", ge=1, le=20)

    @validator('instrument_key')
    def validate_instrument_key(cls, v):
        """Validate instrument key format - must use ExchangeCode as standard"""
        if not v or len(v) < 3:
            raise ValueError('Instrument key must be at least 3 characters')

        # Validate instrument key format: exchange@symbol@product_type[@expiry][@option_type][@strike]
        parts = v.split('@')
        if len(parts) < 3:
            raise ValueError('Instrument key must have at least exchange@symbol@product_type format')

        # First part should be exchange
        exchange = parts[0].upper()
        valid_exchanges = ['NSE', 'BSE', 'NFO', 'MCX', 'CDS', 'NYSE', 'NASDAQ', 'BINANCE']
        if exchange not in valid_exchanges:
            raise ValueError(f'Invalid exchange: {exchange}. Must be one of {valid_exchanges}')

        return v.upper()


class ConfigurationMessage(BaseModel):
    """Message format for configuration updates"""
    config_json: SignalConfigData = Field(..., description="Configuration data")
    action: str = Field(..., description="Action type (create/update/delete)")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source: str = Field('subscription_manager', description="Source of the configuration")

    @validator('action')
    def validate_action(cls, v):
        """Validate action type"""
        valid_actions = ['create', 'update', 'delete']
        if v not in valid_actions:
            raise ValueError(f'Invalid action: {v}. Must be one of {valid_actions}')
        return v


class ComputationResult(BaseModel):
    """Result of a computation"""
    computation_type: str = Field(..., description="Type of computation")
    instrument_key: str = Field(..., description="Instrument key")
    timestamp: datetime = Field(..., description="Computation timestamp")
    results: dict[str, Any] = Field(..., description="Computation results")
    execution_time_ms: float = Field(..., description="Execution time in milliseconds")
    success: bool = Field(..., description="Whether computation succeeded")
    error: str | None = Field(None, description="Error message if failed")


class TickProcessingContext(BaseModel):
    """Context for tick processing"""
    tick_data: dict[str, Any] = Field(..., description="Original tick data")
    instrument_key: str = Field(..., description="Instrument key")
    timestamp: datetime = Field(..., description="Tick timestamp")
    configurations: list[SignalConfigData] = Field([], description="Active configurations")
    aggregated_data: dict[str, Any] | None = Field(None, description="Aggregated historical data")
    computation_results: list[ComputationResult] = Field([], description="Computation results")


class HealthStatus(BaseModel):
    """Health status response"""
    status: str = Field(..., description="Overall status")
    service: str = Field("signal_service", description="Service name")
    version: str = Field(..., description="Service version")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    checks: dict[str, Any] = Field({}, description="Individual health checks")
    metrics: dict[str, Any] = Field({}, description="Service metrics")
