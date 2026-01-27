"""
Production Circuit Breaker for Greeks Calculations
Prevents cascade failures during high load or API failures
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.errors import GreeksCalculationError
from app.utils.logging_utils import log_info, log_warning

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"        # Normal operation
    OPEN = "open"           # Failing, rejecting requests
    HALF_OPEN = "half_open" # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Production circuit breaker configuration"""
    # Failure thresholds
    failure_threshold: int = 5              # Failures to trip breaker
    failure_rate_threshold: float = 0.5     # 50% failure rate to trip

    # Time windows
    timeout_duration: int = 60              # Seconds breaker stays open
    rolling_window: int = 60                # Seconds for failure rate calculation

    # Recovery settings
    half_open_max_calls: int = 3            # Test calls in half-open state
    slow_call_threshold: float = 5.0        # Seconds to consider "slow"
    slow_call_rate_threshold: float = 0.8   # 80% slow calls to trip

    # Performance thresholds for Greeks calculations
    greeks_timeout: float = 30.0            # Max seconds for Greeks calc
    vectorized_timeout: float = 10.0        # Max seconds for vectorized calc
    individual_timeout: float = 1.0         # Max seconds for individual calc

    # Circuit breaker enabled/disabled
    enabled: bool = True


@dataclass
class CircuitBreakerMetrics:
    """Circuit breaker metrics tracking"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rejected_requests: int = 0
    slow_requests: int = 0

    last_failure_time: float | None = None
    last_success_time: float | None = None
    state_change_time: float = field(default_factory=time.time)

    # Rolling window tracking
    recent_calls: list = field(default_factory=list)

    def failure_rate(self) -> float:
        """Calculate current failure rate"""
        if self.total_requests == 0:
            return 0.0
        return self.failed_requests / self.total_requests

    def slow_call_rate(self) -> float:
        """Calculate slow call rate"""
        if self.total_requests == 0:
            return 0.0
        return self.slow_requests / self.total_requests

    def success_rate(self) -> float:
        """Calculate success rate"""
        return 1.0 - self.failure_rate()


class GreeksCircuitBreaker:
    """
    Production circuit breaker for Greeks calculations.

    Prevents cascade failures and provides graceful degradation:
    - CLOSED: Normal operation, all requests pass through
    - OPEN: Failing, reject requests immediately with cached/fallback values
    - HALF_OPEN: Testing recovery with limited requests
    """

    def __init__(self, config: CircuitBreakerConfig | None = None):
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitBreakerState.CLOSED
        self.metrics = CircuitBreakerMetrics()

        # Fallback cache for circuit breaker scenarios
        self._fallback_cache: dict[str, Any] = {}
        self._cache_ttl = 300  # 5 minutes cache TTL

        log_info(f"Greeks circuit breaker initialized: {self.config}")

    async def execute(
        self,
        func: Callable,
        *args,
        fallback_value: Any | None = None,
        cache_key: str | None = None,
        **kwargs
    ) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to execute (Greeks calculation)
            fallback_value: Value to return if circuit is open
            cache_key: Cache key for fallback values
            *args, **kwargs: Arguments for the function

        Returns:
            Function result or fallback value

        Raises:
            GreeksCalculationError: If circuit breaker is open and no fallback
        """
        if not self.config.enabled:
            # Circuit breaker disabled, execute directly
            return await self._execute_function(func, *args, **kwargs)

        # Check circuit breaker state
        if self.state == CircuitBreakerState.OPEN:
            return await self._handle_open_circuit(fallback_value, cache_key)

        if self.state == CircuitBreakerState.HALF_OPEN:
            return await self._handle_half_open_circuit(func, fallback_value, cache_key, *args, **kwargs)

        # CLOSED state
        return await self._handle_closed_circuit(func, fallback_value, cache_key, *args, **kwargs)

    async def _execute_function(self, func: Callable, *args, **kwargs) -> Any:
        """Execute the function with timeout protection"""
        try:
            # Determine timeout based on function type
            timeout = self._get_function_timeout(func)

            start_time = time.time()

            # Execute with timeout
            result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)

            execution_time = time.time() - start_time
            self._record_call_result(True, execution_time)

            return result

        except TimeoutError:
            execution_time = time.time() - start_time
            self._record_call_result(False, execution_time)
            raise GreeksCalculationError(
                f"Function timeout after {execution_time:.2f}s (limit: {timeout}s)",
                details={"timeout": timeout, "execution_time": execution_time}
            )

        except Exception:
            execution_time = time.time() - start_time if 'start_time' in locals() else 0
            self._record_call_result(False, execution_time)
            raise

    def _get_function_timeout(self, func: Callable) -> float:
        """Get appropriate timeout for function type"""
        func_name = getattr(func, '__name__', str(func))

        if 'vectorized' in func_name.lower():
            return self.config.vectorized_timeout
        if 'bulk' in func_name.lower() or 'chain' in func_name.lower():
            return self.config.greeks_timeout
        return self.config.individual_timeout

    async def _handle_open_circuit(self, fallback_value: Any | None, cache_key: str | None) -> Any:
        """Handle requests when circuit is OPEN"""
        self.metrics.rejected_requests += 1

        # Check if timeout period has elapsed
        if time.time() - self.metrics.state_change_time >= self.config.timeout_duration:
            self._transition_to_half_open()
            raise GreeksCalculationError(
                "Circuit breaker transitioning to half-open, retry request",
                details={"state": "transitioning", "action": "retry"}
            )

        # Try to return fallback value
        if fallback_value is not None:
            log_warning("Circuit breaker OPEN: returning fallback value")
            return fallback_value

        # Try cached value
        if cache_key and cache_key in self._fallback_cache:
            cached_data = self._fallback_cache[cache_key]
            if time.time() - cached_data['timestamp'] < self._cache_ttl:
                log_warning("Circuit breaker OPEN: returning cached value")
                return cached_data['value']

        # No fallback available
        raise GreeksCalculationError(
            "Circuit breaker OPEN: Greeks calculation service temporarily unavailable",
            details={
                "state": "open",
                "failure_rate": self.metrics.failure_rate(),
                "time_until_half_open": self.config.timeout_duration - (time.time() - self.metrics.state_change_time)
            }
        )

    async def _handle_half_open_circuit(
        self,
        func: Callable,
        fallback_value: Any | None,
        cache_key: str | None,
        *args,
        **kwargs
    ) -> Any:
        """Handle requests when circuit is HALF_OPEN"""
        # Limit number of test calls
        if self.metrics.total_requests >= self.config.half_open_max_calls:
            return await self._handle_open_circuit(fallback_value, cache_key)

        try:
            # Attempt the call
            result = await self._execute_function(func, *args, **kwargs)

            # Success - check if we should close circuit
            if self._should_close_circuit():
                self._transition_to_closed()
                log_info("Circuit breaker: Service recovered, transitioning to CLOSED")

            # Cache successful result
            if cache_key:
                self._fallback_cache[cache_key] = {
                    'value': result,
                    'timestamp': time.time()
                }

            return result

        except Exception as e:
            # Failure in half-open state - go back to open
            self._transition_to_open()
            log_warning(f"Circuit breaker: Half-open test failed, returning to OPEN: {e}")

            # Return fallback
            return await self._handle_open_circuit(fallback_value, cache_key)

    async def _handle_closed_circuit(
        self,
        func: Callable,
        fallback_value: Any | None,
        cache_key: str | None,
        *args,
        **kwargs
    ) -> Any:
        """Handle requests when circuit is CLOSED"""
        try:
            result = await self._execute_function(func, *args, **kwargs)

            # Cache successful result
            if cache_key:
                self._fallback_cache[cache_key] = {
                    'value': result,
                    'timestamp': time.time()
                }

            return result

        except Exception:
            # Check if we should open circuit
            if self._should_open_circuit():
                self._transition_to_open()
                log_warning("Circuit breaker: Failure threshold reached, transitioning to OPEN")

            raise  # Re-raise the original exception

    def _record_call_result(self, success: bool, execution_time: float):
        """Record the result of a function call"""
        now = time.time()

        # Update metrics
        self.metrics.total_requests += 1
        if success:
            self.metrics.successful_requests += 1
            self.metrics.last_success_time = now
        else:
            self.metrics.failed_requests += 1
            self.metrics.last_failure_time = now

        # Check for slow calls
        if execution_time >= self.config.slow_call_threshold:
            self.metrics.slow_requests += 1

        # Maintain rolling window of recent calls
        call_record = {
            'timestamp': now,
            'success': success,
            'execution_time': execution_time
        }

        self.metrics.recent_calls.append(call_record)

        # Clean old calls outside rolling window
        cutoff_time = now - self.config.rolling_window
        self.metrics.recent_calls = [
            call for call in self.metrics.recent_calls
            if call['timestamp'] > cutoff_time
        ]

    def _should_open_circuit(self) -> bool:
        """Determine if circuit should transition to OPEN"""
        # Check failure count threshold
        if self.metrics.failed_requests >= self.config.failure_threshold:
            return True

        # Check failure rate in rolling window
        if len(self.metrics.recent_calls) >= 5:  # Minimum sample size
            recent_failures = sum(1 for call in self.metrics.recent_calls if not call['success'])
            failure_rate = recent_failures / len(self.metrics.recent_calls)

            if failure_rate >= self.config.failure_rate_threshold:
                return True

        # Check slow call rate
        if self.metrics.slow_call_rate() >= self.config.slow_call_rate_threshold:
            return True

        return False

    def _should_close_circuit(self) -> bool:
        """Determine if circuit should transition to CLOSED (from HALF_OPEN)"""
        # Need at least some successful calls in half-open state
        if self.metrics.successful_requests >= 2:
            recent_success_rate = self.metrics.success_rate()
            return recent_success_rate >= 0.8  # 80% success rate

        return False

    def _transition_to_open(self):
        """Transition circuit breaker to OPEN state"""
        self.state = CircuitBreakerState.OPEN
        self.metrics.state_change_time = time.time()
        log_warning(f"Circuit breaker transitioned to OPEN: failure_rate={self.metrics.failure_rate():.2f}")

    def _transition_to_half_open(self):
        """Transition circuit breaker to HALF_OPEN state"""
        self.state = CircuitBreakerState.HALF_OPEN
        self.metrics.state_change_time = time.time()
        self.metrics.total_requests = 0  # Reset for half-open testing
        log_info("Circuit breaker transitioned to HALF_OPEN: testing service recovery")

    def _transition_to_closed(self):
        """Transition circuit breaker to CLOSED state"""
        self.state = CircuitBreakerState.CLOSED
        self.metrics.state_change_time = time.time()
        # Reset failure metrics
        self.metrics.failed_requests = 0
        self.metrics.slow_requests = 0
        log_info("Circuit breaker transitioned to CLOSED: service recovered")

    def get_metrics(self) -> dict[str, Any]:
        """Get current circuit breaker metrics"""
        return {
            'state': self.state.value,
            'metrics': {
                'total_requests': self.metrics.total_requests,
                'successful_requests': self.metrics.successful_requests,
                'failed_requests': self.metrics.failed_requests,
                'rejected_requests': self.metrics.rejected_requests,
                'slow_requests': self.metrics.slow_requests,
                'failure_rate': self.metrics.failure_rate(),
                'slow_call_rate': self.metrics.slow_call_rate(),
                'success_rate': self.metrics.success_rate()
            },
            'config': {
                'failure_threshold': self.config.failure_threshold,
                'failure_rate_threshold': self.config.failure_rate_threshold,
                'timeout_duration': self.config.timeout_duration,
                'enabled': self.config.enabled
            },
            'state_info': {
                'current_state': self.state.value,
                'time_in_current_state': time.time() - self.metrics.state_change_time,
                'last_failure_time': self.metrics.last_failure_time,
                'last_success_time': self.metrics.last_success_time
            },
            'cache_info': {
                'cached_fallbacks': len(self._fallback_cache),
                'cache_ttl': self._cache_ttl
            }
        }

    def reset(self):
        """Reset circuit breaker to initial state"""
        self.state = CircuitBreakerState.CLOSED
        self.metrics = CircuitBreakerMetrics()
        self._fallback_cache.clear()
        log_info("Circuit breaker reset to initial state")


# Global circuit breaker instances for different calculation types
_circuit_breakers: dict[str, GreeksCircuitBreaker] = {}


def get_circuit_breaker(breaker_type: str = "default") -> GreeksCircuitBreaker:
    """Get or create circuit breaker instance for specific calculation type"""
    if breaker_type not in _circuit_breakers:
        # Create specialized configurations for different calculation types
        if breaker_type == "vectorized":
            config = CircuitBreakerConfig(
                failure_threshold=3,
                vectorized_timeout=15.0,
                timeout_duration=30
            )
        elif breaker_type == "individual":
            config = CircuitBreakerConfig(
                failure_threshold=10,
                individual_timeout=2.0,
                timeout_duration=60
            )
        elif breaker_type == "bulk":
            config = CircuitBreakerConfig(
                failure_threshold=2,
                greeks_timeout=45.0,
                timeout_duration=45
            )
        else:
            config = CircuitBreakerConfig()

        _circuit_breakers[breaker_type] = GreeksCircuitBreaker(config)
        log_info(f"Created circuit breaker for type: {breaker_type}")

    return _circuit_breakers[breaker_type]


def get_all_circuit_breaker_metrics() -> dict[str, Any]:
    """Get metrics from all circuit breakers"""
    return {
        breaker_type: breaker.get_metrics()
        for breaker_type, breaker in _circuit_breakers.items()
    }


class CircuitBreakerManager:
    """Manager for all circuit breakers in the system"""

    def __init__(self):
        self.breakers = _circuit_breakers

    async def get_status(self) -> dict[str, Any]:
        """Get status of all circuit breakers"""
        status = {}
        for breaker_type, breaker in self.breakers.items():
            metrics = breaker.get_metrics()
            status[breaker_type] = {
                "state": breaker.state.value,
                "failure_count": metrics["failure_count"],
                "success_count": metrics["success_count"],
                "last_failure_time": metrics["last_failure_time"],
                "next_attempt_time": metrics.get("next_attempt_time"),
                "enabled": breaker.config.enabled
            }
        return status

    def get_breaker(self, breaker_type: str):
        """Get specific circuit breaker"""
        return get_circuit_breaker(breaker_type)


# Global instance for singleton pattern
_circuit_breaker_manager = None

def get_circuit_breaker_manager():
    """Get or create singleton circuit breaker manager"""
    global _circuit_breaker_manager
    if _circuit_breaker_manager is None:
        _circuit_breaker_manager = CircuitBreakerManager()
    return _circuit_breaker_manager
