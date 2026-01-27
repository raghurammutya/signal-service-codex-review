#!/usr/bin/env python3
"""
Instrument Registry Client for Signal Service

Phase 3: Signal & Algo Engine Registry Integration
Session 5A: Event consumer implementation with registry integration
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from enum import Enum
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

class CircuitBreakerState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

@dataclass
class RegistryConfig:
    """Configuration for registry integration"""
    event_consumer_url: str = "http://localhost:8901/api/v1/internal/instrument-registry/events/stream"
    subscription_timeout: int = 30
    cache_ttl_seconds: int = 300
    event_batch_size: int = 100
    fallback_enabled: bool = True
    shadow_mode_enabled: bool = False
    comparison_sampling_rate: float = 0.1
    shadow_timeout: int = 5
    event_retry_attempts: int = 3
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 60

class CircuitBreaker:
    """Circuit breaker for registry API calls"""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED

    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        if self.state == CircuitBreakerState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                logger.info("Circuit breaker transitioning to HALF_OPEN")
            else:
                raise Exception("Circuit breaker is OPEN - registry unavailable")

        try:
            result = func(*args, **kwargs)
            if self.state == CircuitBreakerState.HALF_OPEN:
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                logger.info("Circuit breaker reset to CLOSED")
            return result
        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                self.state = CircuitBreakerState.OPEN
                logger.error(f"Circuit breaker OPENED after {self.failure_count} failures")

            raise

class InstrumentRegistryCache:
    """Simple TTL cache for instrument metadata"""

    def __init__(self, default_ttl: int = 300):
        self.cache: dict[str, dict] = {}
        self.default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        """Get cached value if not expired"""
        if key in self.cache:
            entry = self.cache[key]
            if time.time() < entry["expires_at"]:
                return entry["value"]
            del self.cache[key]
        return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Cache value with TTL"""
        ttl = ttl or self.default_ttl
        self.cache[key] = {
            "value": value,
            "expires_at": time.time() + ttl
        }

    def invalidate(self, pattern: str = None) -> None:
        """Invalidate cache entries matching pattern"""
        if pattern:
            keys_to_remove = [k for k in self.cache if pattern in k]
            for key in keys_to_remove:
                del self.cache[key]
                logger.debug(f"Invalidated cache key: {key}")
        else:
            self.cache.clear()
            logger.info("Cleared all cache entries")

class InstrumentRegistryClient:
    """Client for instrument registry integration in signal service"""

    def __init__(self, config: RegistryConfig):
        self.config = config
        self.base_url = "http://localhost:8901"
        self.headers = {
            "X-Internal-API-Key": "AShhRzWhfXd6IomyzZnE3d-lCcAvT1L5GDCCZRSXZGsJq7_eAJGxeMi-4AlfTeOc",
            "Content-Type": "application/json"
        }
        self.cache = InstrumentRegistryCache(config.cache_ttl_seconds)
        self.circuit_breaker = CircuitBreaker(
            config.circuit_breaker_threshold,
            config.circuit_breaker_timeout
        )
        self._session = None

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.subscription_timeout)
            self._session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=timeout
            )
        return self._session

    async def close(self):
        """Close client session"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def search_instruments(self, query: str, limit: int = 50) -> dict[str, Any]:
        """Search for instruments with caching"""
        cache_key = f"search:{query}:{limit}"

        # Check cache first
        cached_result = self.cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Cache hit for search: {query}")
            return cached_result

        try:
            session = await self.get_session()

            def make_request():
                return asyncio.create_task(session.get(
                    f"{self.base_url}/api/v1/internal/instrument-registry/search",
                    params={"query": query, "limit": limit}
                ))

            response_task = await asyncio.to_thread(self.circuit_breaker.call, make_request)
            response = await response_task

            if response.status == 200:
                result = await response.json()

                # Cache the result
                self.cache.set(cache_key, result, ttl=60)  # Shorter TTL for search

                logger.debug(f"Search completed: {query} -> {len(result.get('instruments', []))} results")
                return result
            logger.error(f"Search failed: {response.status}")
            return {"instruments": [], "error": f"HTTP {response.status}"}

        except Exception as e:
            logger.error(f"Search error: {e}")
            if self.config.fallback_enabled:
                # Return cached result if available, even if expired
                fallback_result = self.cache.get(cache_key)
                if fallback_result:
                    logger.warning(f"Using fallback cached result for: {query}")
                    return fallback_result

            return {"instruments": [], "error": str(e)}

    async def get_instrument_metadata(self, instrument_ids: list[str]) -> dict[str, Any]:
        """Get bulk instrument metadata with caching"""
        cache_key = f"metadata:{':'.join(sorted(instrument_ids))}"

        # Check cache first
        cached_result = self.cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Cache hit for metadata: {len(instrument_ids)} instruments")
            return cached_result

        try:
            session = await self.get_session()

            payload = {
                "instrument_ids": instrument_ids,
                "include_metadata": True
            }

            def make_request():
                return asyncio.create_task(session.post(
                    f"{self.base_url}/api/v1/internal/instrument-registry/instruments/bulk",
                    json=payload
                ))

            response_task = await asyncio.to_thread(self.circuit_breaker.call, make_request)
            response = await response_task

            if response.status == 200:
                result = await response.json()

                # Cache the result
                self.cache.set(cache_key, result, ttl=self.config.cache_ttl_seconds)

                logger.debug(f"Metadata retrieved: {len(result.get('instruments', []))} instruments")
                return result
            logger.error(f"Metadata retrieval failed: {response.status}")
            return {"instruments": [], "error": f"HTTP {response.status}"}

        except Exception as e:
            logger.error(f"Metadata retrieval error: {e}")
            if self.config.fallback_enabled:
                fallback_result = self.cache.get(cache_key)
                if fallback_result:
                    logger.warning(f"Using fallback cached metadata for {len(instrument_ids)} instruments")
                    return fallback_result

            return {"instruments": [], "error": str(e)}

    async def consume_events(self, event_types: list[str], consumer_id: str = "signal_service_001") -> AsyncGenerator[dict, None]:
        """Consume real-time registry events"""
        logger.info(f"Starting event consumption for: {event_types}")

        subscription_payload = {
            "event_types": event_types,
            "consumer_id": consumer_id,
            "batch_size": self.config.event_batch_size
        }

        session = await self.get_session()

        retry_count = 0
        while retry_count < self.config.event_retry_attempts:
            try:
                async with session.post(
                    self.config.event_consumer_url,
                    json=subscription_payload
                ) as response:

                    if response.status != 200:
                        logger.error(f"Event subscription failed: HTTP {response.status}")
                        retry_count += 1
                        await asyncio.sleep(2 ** retry_count)  # Exponential backoff
                        continue

                    logger.info("Event stream connected successfully")
                    retry_count = 0  # Reset on successful connection

                    async for line in response.content:
                        if line:
                            try:
                                event = json.loads(line.decode().strip())

                                # Process event and invalidate relevant cache
                                await self._process_event(event)

                                yield event

                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to parse event: {e}")
                                continue

            except Exception as e:
                logger.error(f"Event consumption error: {e}")
                retry_count += 1
                if retry_count < self.config.event_retry_attempts:
                    await asyncio.sleep(2 ** retry_count)
                else:
                    logger.error("Max retries exceeded for event consumption")
                    break

    async def _process_event(self, event: dict[str, Any]):
        """Process incoming registry events and invalidate cache"""
        event_type = event.get("event_type")
        event_data = event.get("data", {})

        logger.debug(f"Processing event: {event_type}")

        if event_type == "instrument.updated":
            # Invalidate instrument-specific cache
            instrument_id = event_data.get("instrument_id")
            if instrument_id:
                self.cache.invalidate(instrument_id)
                logger.debug(f"Invalidated cache for instrument: {instrument_id}")

        elif event_type == "subscription.profile.changed":
            # Invalidate subscription-related cache
            user_id = event_data.get("user_id")
            if user_id:
                self.cache.invalidate(f"subscription:{user_id}")
                logger.debug(f"Invalidated subscription cache for user: {user_id}")

        elif event_type == "chain.rebalance":
            # Invalidate option chain cache
            underlying = event_data.get("underlying")
            if underlying:
                self.cache.invalidate(f"chain:{underlying}")
                logger.debug(f"Invalidated chain cache for: {underlying}")

        # Additional event processing can be added here

    async def health_check(self) -> dict[str, Any]:
        """Check registry service health"""
        try:
            session = await self.get_session()

            async with session.get(f"{self.base_url}/health") as response:
                if response.status == 200:
                    health_data = await response.json()
                    return {
                        "registry_healthy": True,
                        "registry_status": health_data.get("status"),
                        "circuit_breaker_state": self.circuit_breaker.state.value,
                        "cache_size": len(self.cache.cache)
                    }
                return {
                    "registry_healthy": False,
                    "error": f"HTTP {response.status}",
                    "circuit_breaker_state": self.circuit_breaker.state.value
                }
        except Exception as e:
            return {
                "registry_healthy": False,
                "error": str(e),
                "circuit_breaker_state": self.circuit_breaker.state.value
            }

# Factory function for creating registry client
def create_registry_client(config_service_client=None) -> InstrumentRegistryClient:
    """Create registry client with configuration from config service"""

    if config_service_client is None:
        from ...common.config_service.client import ConfigServiceError, get_config_client
        try:
            config_service_client = get_config_client(service_name="signal_service")
        except ConfigServiceError as e:
            logger.error(f"Failed to initialize config service client: {e}")
            raise RuntimeError(f"Config service integration required for production: {e}") from e

    try:
        # Get registry service URL from config service
        instrument_registry_url = config_service_client.get_service_url("instrument_registry")
        if not instrument_registry_url:
            raise ConfigServiceError("instrument_registry service URL not found")

        # Build configuration from config service
        config = RegistryConfig(
            event_consumer_url=f"{instrument_registry_url}/api/v1/internal/instrument-registry/events/stream",
            subscription_timeout=int(config_service_client.get_config("SIGNAL_REGISTRY_SUBSCRIPTION_TIMEOUT", required=True)),
            cache_ttl_seconds=int(config_service_client.get_config("SIGNAL_REGISTRY_CACHE_TTL_SECONDS", required=True)),
            event_batch_size=int(config_service_client.get_config("SIGNAL_REGISTRY_EVENT_BATCH_SIZE", required=True)),
            fallback_enabled=config_service_client.get_config("SIGNAL_REGISTRY_FALLBACK_ENABLED", required=True).lower() == "true",
            shadow_mode_enabled=config_service_client.get_config("SIGNAL_REGISTRY_SHADOW_MODE_ENABLED", required=True).lower() == "true",
            comparison_sampling_rate=float(config_service_client.get_config("SIGNAL_REGISTRY_COMPARISON_SAMPLING_RATE", required=True)),
            shadow_timeout=int(config_service_client.get_config("SIGNAL_REGISTRY_SHADOW_TIMEOUT", required=True)),
            event_retry_attempts=int(config_service_client.get_config("SIGNAL_REGISTRY_EVENT_RETRY_ATTEMPTS", required=True)),
            circuit_breaker_threshold=int(config_service_client.get_config("SIGNAL_REGISTRY_CIRCUIT_BREAKER_THRESHOLD", required=True)),
            circuit_breaker_timeout=int(config_service_client.get_config("SIGNAL_REGISTRY_CIRCUIT_BREAKER_TIMEOUT", required=True))
        )

        logger.info(f"Created registry client with config service integration - registry: {instrument_registry_url}")
        return InstrumentRegistryClient(config)

    except ConfigServiceError as e:
        logger.error(f"Failed to load registry configuration from config service: {e}")
        raise RuntimeError(f"Registry configuration missing from config service: {e}") from e
    except (ValueError, TypeError) as e:
        logger.error(f"Invalid configuration values from config service: {e}")
        raise RuntimeError(f"Registry configuration validation failed: {e}") from e

# Event handler example for signal service integration
async def handle_registry_event(event: dict[str, Any], signal_service_context):
    """Example event handler for signal service"""
    event_type = event.get("event_type")
    event_data = event.get("data", {})

    logger.info(f"Signal service processing registry event: {event_type}")

    if event_type == "instrument.updated":
        # Trigger Greeks recalculation
        instrument_id = event_data.get("instrument_id")
        if instrument_id:
            logger.info(f"Triggering Greeks recalculation for {instrument_id}")
            # Signal service specific logic here

    elif event_type == "chain.rebalance":
        # Update option chain data
        underlying = event_data.get("underlying")
        if underlying:
            logger.info(f"Processing chain rebalance for {underlying}")
            # Signal service specific logic here

    elif event_type == "subscription.profile.changed":
        # Update user subscription preferences
        user_id = event_data.get("user_id")
        if user_id:
            logger.info(f"Processing subscription change for user {user_id}")
            # Signal service specific logic here
