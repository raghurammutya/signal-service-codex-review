"""Custom exceptions for Signal Service"""
from typing import Any


class SignalServiceError(Exception):
    """Base exception for Signal Service"""
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class ConfigurationError(SignalServiceError):
    """Configuration-related errors"""


class InvalidConfigurationError(ConfigurationError):
    """Invalid configuration provided"""


class MissingConfigurationError(ConfigurationError):
    """Required configuration is missing"""


class DataAccessError(SignalServiceError):
    """Data access and retrieval errors"""


class SecurityError(SignalServiceError):
    """Security-related errors"""


class WatermarkError(SecurityError):
    """Watermark-related security errors"""


class TimescaleDBConnectionError(DataAccessError):
    """TimescaleDB connection or query errors"""


class RedisConnectionError(DataAccessError):
    """Redis connection or operation errors"""


class DataValidationError(DataAccessError):
    """Data validation errors"""


class ComputationError(SignalServiceError):
    """Computation and processing errors"""


class CalculationError(ComputationError):
    """General calculation errors (alias for ComputationError for backward compatibility)"""


class GreeksCalculationError(ComputationError):
    """Option Greeks calculation errors"""


class UnsupportedModelError(ConfigurationError):
    """Unsupported options pricing model specified in configuration"""


class TechnicalIndicatorError(ComputationError):
    """Technical indicator calculation errors"""


class ExternalFunctionExecutionError(ComputationError):
    """External function execution errors"""


class ExternalServiceError(SignalServiceError):
    """External service communication errors"""


class SubscriptionManagerAPIError(ExternalServiceError):
    """Subscription Manager API errors"""


class TickerServiceError(ExternalServiceError):
    """Ticker Service communication errors"""


class ProcessingTimeoutError(SignalServiceError):
    """Processing timeout errors"""


class ResourceLimitError(SignalServiceError):
    """Resource limit exceeded errors"""


class StreamProcessingError(SignalServiceError):
    """Redis Stream processing errors"""


class SecurityError(SignalServiceError):
    """Security-related errors"""


class RateLimitError(SignalServiceError):
    """Rate limiting errors"""


class CommsServiceError(ExternalServiceError):
    """Communication service operation errors"""
    def __init__(self, message: str, status_code: int | None = None, details: dict[str, Any] | None = None):
        super().__init__(message, details)
        self.status_code = status_code


class CacheConnectionError(DataAccessError):
    """Cache connection errors"""


class WorkerRegistryError(SignalServiceError):
    """Worker registry operation errors"""


class ConsumerError(StreamProcessingError):
    """Message consumption errors"""


class TimeframeAggregationError(ComputationError):
    """Timeframe aggregation errors"""


class DatabaseQueryError(DataAccessError):
    """Database query errors"""


# Error handling utilities
def handle_computation_error(error: Exception, computation_type: str, instrument_key: str) -> ComputationError:
    """Convert generic exceptions to computation errors"""
    if isinstance(error, ComputationError):
        return error

    details = {
        "computation_type": computation_type,
        "instrument_key": instrument_key,
        "original_error": str(error),
        "error_type": type(error).__name__
    }

    if "greeks" in computation_type.lower():
        return GreeksCalculationError(
            f"Greeks calculation failed for {instrument_key}: {str(error)}",
            details
        )
    if "indicator" in computation_type.lower():
        return TechnicalIndicatorError(
            f"Technical indicator calculation failed for {instrument_key}: {str(error)}",
            details
        )
    return ComputationError(
        f"Computation failed for {instrument_key}: {str(error)}",
        details
    )


def handle_data_access_error(error: Exception, operation: str, resource: str) -> DataAccessError:
    """Convert generic exceptions to data access errors"""
    if isinstance(error, DataAccessError):
        return error

    details = {
        "operation": operation,
        "resource": resource,
        "original_error": str(error),
        "error_type": type(error).__name__
    }

    if "redis" in resource.lower():
        return RedisConnectionError(
            f"Redis {operation} failed for {resource}: {str(error)}",
            details
        )
    if "timescale" in resource.lower() or "postgres" in resource.lower():
        return TimescaleDBConnectionError(
            f"TimescaleDB {operation} failed for {resource}: {str(error)}",
            details
        )
    return DataAccessError(
        f"Data access {operation} failed for {resource}: {str(error)}",
        details
    )
