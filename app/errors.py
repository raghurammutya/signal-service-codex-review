"""Custom exceptions for Signal Service"""
from typing import Optional, Any, Dict


class SignalServiceError(Exception):
    """Base exception for Signal Service"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class ConfigurationError(SignalServiceError):
    """Configuration-related errors"""
    pass


class InvalidConfigurationError(ConfigurationError):
    """Invalid configuration provided"""
    pass


class MissingConfigurationError(ConfigurationError):
    """Required configuration is missing"""
    pass


class DataAccessError(SignalServiceError):
    """Data access and retrieval errors"""
    pass


class SecurityError(SignalServiceError):
    """Security-related errors"""
    pass


class WatermarkError(SecurityError):
    """Watermark-related security errors"""
    pass


class TimescaleDBConnectionError(DataAccessError):
    """TimescaleDB connection or query errors"""
    pass


class RedisConnectionError(DataAccessError):
    """Redis connection or operation errors"""
    pass


class DataValidationError(DataAccessError):
    """Data validation errors"""
    pass


class ComputationError(SignalServiceError):
    """Computation and processing errors"""
    pass


class GreeksCalculationError(ComputationError):
    """Option Greeks calculation errors"""
    pass


class UnsupportedModelError(ConfigurationError):
    """Unsupported options pricing model specified in configuration"""
    pass


class TechnicalIndicatorError(ComputationError):
    """Technical indicator calculation errors"""
    pass


class ExternalFunctionExecutionError(ComputationError):
    """External function execution errors"""
    pass


class ExternalServiceError(SignalServiceError):
    """External service communication errors"""
    pass


class SubscriptionManagerAPIError(ExternalServiceError):
    """Subscription Manager API errors"""
    pass


class TickerServiceError(ExternalServiceError):
    """Ticker Service communication errors"""
    pass


class ProcessingTimeoutError(SignalServiceError):
    """Processing timeout errors"""
    pass


class ResourceLimitError(SignalServiceError):
    """Resource limit exceeded errors"""
    pass


class StreamProcessingError(SignalServiceError):
    """Redis Stream processing errors"""
    pass


class SecurityError(SignalServiceError):
    """Security-related errors"""
    pass


class RateLimitError(SignalServiceError):
    """Rate limiting errors"""
    pass


class CommsServiceError(ExternalServiceError):
    """Communication service operation errors"""
    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)
        self.status_code = status_code


class CacheConnectionError(DataAccessError):
    """Cache connection errors"""
    pass


class WorkerRegistryError(SignalServiceError):
    """Worker registry operation errors"""
    pass


class ConsumerError(StreamProcessingError):
    """Message consumption errors"""
    pass


class TimeframeAggregationError(ComputationError):
    """Timeframe aggregation errors"""
    pass


class DatabaseQueryError(DataAccessError):
    """Database query errors"""
    pass


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
    elif "indicator" in computation_type.lower():
        return TechnicalIndicatorError(
            f"Technical indicator calculation failed for {instrument_key}: {str(error)}",
            details
        )
    else:
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
    elif "timescale" in resource.lower() or "postgres" in resource.lower():
        return TimescaleDBConnectionError(
            f"TimescaleDB {operation} failed for {resource}: {str(error)}",
            details
        )
    else:
        return DataAccessError(
            f"Data access {operation} failed for {resource}: {str(error)}",
            details
        )