"""
Production Structured Logging for Signal Service
Provides comprehensive logging with metrics, tracing, and observability
"""

import logging
import json
import time
import traceback
from typing import Dict, Any, Optional, Union
from datetime import datetime, timezone
from contextvars import ContextVar
from functools import wraps
import asyncio
import sys

# Context variables for request tracing
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar('user_id', default=None)
operation_var: ContextVar[Optional[str]] = ContextVar('operation', default=None)


class ProductionJSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging in production.
    Includes request tracing, metrics, and standardized fields.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON"""
        
        # Base log structure
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'service': 'signal_service',
            'version': '2.0.0'
        }
        
        # Add request context if available
        request_id = request_id_var.get()
        if request_id:
            log_entry['request_id'] = request_id
            
        user_id = user_id_var.get()
        if user_id:
            log_entry['user_id'] = user_id
            
        operation = operation_var.get()
        if operation:
            log_entry['operation'] = operation
        
        # Add exception information if present
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': self.formatException(record.exc_info)
            }
        
        # Add extra fields from the record
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 
                          'filename', 'module', 'lineno', 'funcName', 'created', 'msecs',
                          'relativeCreated', 'thread', 'threadName', 'processName',
                          'process', 'getMessage', 'exc_info', 'exc_text', 'stack_info']:
                extra_fields[key] = value
        
        if extra_fields:
            log_entry['extra'] = extra_fields
        
        return json.dumps(log_entry, default=str, separators=(',', ':'))


class PerformanceLogger:
    """
    Logger for performance metrics and Greeks calculation tracking.
    Provides structured metrics for observability and alerting.
    """
    
    def __init__(self):
        self.logger = logging.getLogger('signal_service.performance')
    
    def log_calculation_performance(
        self,
        calculation_type: str,
        operation: str,
        duration_ms: float,
        options_count: int = 1,
        success: bool = True,
        model_name: Optional[str] = None,
        error: Optional[str] = None,
        additional_metrics: Optional[Dict[str, Any]] = None
    ):
        """Log Greeks calculation performance metrics"""
        
        metrics = {
            'metric_type': 'calculation_performance',
            'calculation_type': calculation_type,  # 'vectorized', 'individual', 'bulk'
            'operation': operation,  # 'delta', 'gamma', 'all_greeks', etc.
            'duration_ms': round(duration_ms, 2),
            'options_count': options_count,
            'options_per_second': round(options_count / (duration_ms / 1000), 2) if duration_ms > 0 else 0,
            'success': success,
            'model_name': model_name,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if error:
            metrics['error'] = error
            
        if additional_metrics:
            metrics.update(additional_metrics)
        
        # Log at appropriate level
        if success:
            self.logger.info(
                f"{calculation_type} {operation} completed in {duration_ms:.2f}ms",
                extra=metrics
            )
        else:
            self.logger.warning(
                f"{calculation_type} {operation} failed after {duration_ms:.2f}ms: {error}",
                extra=metrics
            )
    
    def log_circuit_breaker_event(
        self,
        breaker_type: str,
        event_type: str,  # 'opened', 'closed', 'half_open', 'request_rejected'
        metrics: Dict[str, Any]
    ):
        """Log circuit breaker state changes and events"""
        
        log_data = {
            'metric_type': 'circuit_breaker_event',
            'breaker_type': breaker_type,
            'event_type': event_type,
            'breaker_metrics': metrics,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if event_type == 'opened':
            self.logger.error(
                f"Circuit breaker {breaker_type} OPENED due to failures",
                extra=log_data
            )
        elif event_type == 'closed':
            self.logger.info(
                f"Circuit breaker {breaker_type} CLOSED - service recovered",
                extra=log_data
            )
        elif event_type == 'half_open':
            self.logger.warning(
                f"Circuit breaker {breaker_type} testing recovery (HALF_OPEN)",
                extra=log_data
            )
        else:
            self.logger.debug(
                f"Circuit breaker {breaker_type} event: {event_type}",
                extra=log_data
            )
    
    def log_model_configuration_event(
        self,
        event_type: str,  # 'loaded', 'changed', 'validation_error'
        model_name: str,
        parameters: Dict[str, Any],
        error: Optional[str] = None
    ):
        """Log model configuration events"""
        
        log_data = {
            'metric_type': 'model_configuration_event',
            'event_type': event_type,
            'model_name': model_name,
            'parameters': parameters,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if error:
            log_data['error'] = error
        
        if event_type == 'validation_error' or error:
            self.logger.error(
                f"Model configuration {event_type}: {model_name} - {error}",
                extra=log_data
            )
        elif event_type == 'changed':
            self.logger.warning(
                f"Model configuration changed: {model_name}",
                extra=log_data
            )
        else:
            self.logger.info(
                f"Model configuration {event_type}: {model_name}",
                extra=log_data
            )
    
    def log_api_request(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        duration_ms: float,
        user_id: Optional[str] = None,
        request_size: Optional[int] = None,
        response_size: Optional[int] = None
    ):
        """Log API request metrics"""
        
        log_data = {
            'metric_type': 'api_request',
            'endpoint': endpoint,
            'method': method,
            'status_code': status_code,
            'duration_ms': round(duration_ms, 2),
            'user_id': user_id,
            'request_size_bytes': request_size,
            'response_size_bytes': response_size,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if status_code >= 500:
            self.logger.error(
                f"API {method} {endpoint} failed with {status_code} in {duration_ms:.2f}ms",
                extra=log_data
            )
        elif status_code >= 400:
            self.logger.warning(
                f"API {method} {endpoint} client error {status_code} in {duration_ms:.2f}ms",
                extra=log_data
            )
        else:
            self.logger.info(
                f"API {method} {endpoint} success {status_code} in {duration_ms:.2f}ms",
                extra=log_data
            )


class ErrorTracker:
    """
    Tracks and analyzes errors for alerting and debugging.
    Provides error rate calculations and trend analysis.
    """
    
    def __init__(self):
        self.logger = logging.getLogger('signal_service.errors')
        self.error_counts = {}
        self.error_window = 300  # 5 minutes
    
    def log_error(
        self,
        error_type: str,
        error_message: str,
        context: Dict[str, Any],
        exception: Optional[Exception] = None,
        severity: str = 'error'
    ):
        """Log and track errors with context"""
        
        error_data = {
            'metric_type': 'error_event',
            'error_type': error_type,
            'error_message': error_message,
            'severity': severity,
            'context': context,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if exception:
            error_data['exception_type'] = type(exception).__name__
            error_data['exception_traceback'] = traceback.format_exc()
        
        # Track error frequency
        error_key = f"{error_type}:{error_message[:50]}"
        now = time.time()
        
        if error_key not in self.error_counts:
            self.error_counts[error_key] = []
        
        self.error_counts[error_key].append(now)
        
        # Clean old errors outside window
        cutoff = now - self.error_window
        self.error_counts[error_key] = [
            t for t in self.error_counts[error_key] if t > cutoff
        ]
        
        # Add frequency data
        error_data['error_frequency_5min'] = len(self.error_counts[error_key])
        
        # Log at appropriate level
        if severity == 'critical':
            self.logger.critical(f"CRITICAL ERROR: {error_type} - {error_message}", extra=error_data)
        elif severity == 'warning':
            self.logger.warning(f"WARNING: {error_type} - {error_message}", extra=error_data)
        else:
            self.logger.error(f"ERROR: {error_type} - {error_message}", extra=error_data)
    
    def get_error_rate(self, error_type: Optional[str] = None) -> float:
        """Get current error rate for monitoring"""
        now = time.time()
        cutoff = now - self.error_window
        
        total_errors = 0
        for key, timestamps in self.error_counts.items():
            if error_type is None or key.startswith(error_type):
                total_errors += len([t for t in timestamps if t > cutoff])
        
        # This would ideally be compared against total requests
        # For now, return raw error count
        return total_errors


# Global instances
performance_logger = PerformanceLogger()
error_tracker = ErrorTracker()


def setup_production_logging(
    log_level: str = "INFO",
    enable_console: bool = True,
    log_file: Optional[str] = None
):
    """
    Setup production logging configuration.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        enable_console: Whether to log to console
        log_file: Optional file path for logging
    """
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove default handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # JSON formatter for structured logging
    formatter = ProductionJSONFormatter()
    
    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Set specific logger levels
    logging.getLogger('signal_service').setLevel(getattr(logging, log_level.upper()))
    logging.getLogger('signal_service.performance').setLevel(logging.INFO)
    logging.getLogger('signal_service.errors').setLevel(logging.WARNING)
    
    # Suppress noisy third-party loggers
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    logging.info("Production logging configured", extra={
        'log_level': log_level,
        'console_enabled': enable_console,
        'file_logging': log_file is not None
    })


def with_request_context(request_id: str, user_id: Optional[str] = None, operation: Optional[str] = None):
    """Context manager to set request context for logging"""
    
    class RequestContext:
        def __enter__(self):
            request_id_var.set(request_id)
            if user_id:
                user_id_var.set(user_id)
            if operation:
                operation_var.set(operation)
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            request_id_var.set(None)
            user_id_var.set(None)
            operation_var.set(None)
    
    return RequestContext()


def log_performance(calculation_type: str, operation: str = "unknown"):
    """
    Decorator to automatically log function performance.
    
    Args:
        calculation_type: Type of calculation ('vectorized', 'individual', 'bulk')
        operation: Operation being performed ('delta', 'gamma', etc.)
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            success = True
            error = None
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                error = str(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                
                # Try to extract options count from args/kwargs
                options_count = 1
                if 'option_chain_data' in kwargs:
                    options_count = len(kwargs['option_chain_data'])
                elif len(args) > 0 and isinstance(args[0], list):
                    options_count = len(args[0])
                
                performance_logger.log_calculation_performance(
                    calculation_type=calculation_type,
                    operation=operation,
                    duration_ms=duration_ms,
                    options_count=options_count,
                    success=success,
                    error=error
                )
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            success = True
            error = None
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                error = str(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                performance_logger.log_calculation_performance(
                    calculation_type=calculation_type,
                    operation=operation,
                    duration_ms=duration_ms,
                    options_count=1,
                    success=success,
                    error=error
                )
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator


# Convenience functions for common logging patterns
def log_greeks_calculation(
    calculation_type: str,
    operation: str,
    duration_ms: float,
    options_count: int = 1,
    success: bool = True,
    **kwargs
):
    """Convenience function for logging Greeks calculations"""
    performance_logger.log_calculation_performance(
        calculation_type, operation, duration_ms, options_count, success, **kwargs
    )


def log_error(error_type: str, message: str, context: Dict[str, Any], exception: Optional[Exception] = None):
    """Convenience function for error logging"""
    error_tracker.log_error(error_type, message, context, exception)


def log_circuit_breaker(breaker_type: str, event_type: str, metrics: Dict[str, Any]):
    """Convenience function for circuit breaker logging"""
    performance_logger.log_circuit_breaker_event(breaker_type, event_type, metrics)