"""
Minimal resilience helpers for the signal service.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    expected_exception: tuple[type[Exception], ...] = (Exception,)
    name: str = "circuit_breaker"


class CircuitBreaker:
    """Minimal circuit breaker implementation for async operations."""

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = "CLOSED"
        self.failure_count = 0
        self.last_failure_timestamp: float | None = None

    def _open_circuit(self):
        self.state = "OPEN"
        self.last_failure_timestamp = time.monotonic()
        self.failure_count = 0

    def _reset(self):
        self.state = "CLOSED"
        self.failure_count = 0
        self.last_failure_timestamp = None

    def allows_execution(self) -> bool:
        if self.state == "OPEN":
            if self.last_failure_timestamp and (time.monotonic() - self.last_failure_timestamp) >= self.config.recovery_timeout:
                self.state = "HALF_OPEN"
                return True
            return False
        return True

    def record_failure(self):
        self.failure_count += 1
        if self.failure_count >= self.config.failure_threshold:
            self._open_circuit()

    def record_success(self):
        if self.state in ("HALF_OPEN", "OPEN"):
            self._reset()

    async def call(self, func: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:
        if not self.allows_execution():
            raise RuntimeError(f"Circuit breaker '{self.config.name}' is open")
        try:
            result = await func(*args, **kwargs)
            self.record_success()
            return result
        except self.config.expected_exception as exc:
            self.record_failure()
            raise exc


async def retry_with_exponential_backoff(
    func: Callable[..., Awaitable[Any]],
    *args: Any,
    max_attempts: int = 3,
    initial_delay: float = 0.1,
    max_delay: float = 5.0,
    factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    **kwargs: Any,
) -> Any:
    """Retry an async callable with exponential backoff."""
    attempt = 0
    delay = initial_delay
    while attempt < max_attempts:
        try:
            return await func(*args, **kwargs)
        except exceptions:
            attempt += 1
            if attempt >= max_attempts:
                raise
            await asyncio.sleep(min(delay, max_delay))
            delay = min(delay * factor, max_delay)
    return None
