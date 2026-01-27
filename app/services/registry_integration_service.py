#!/usr/bin/env python3
"""
Registry Integration Service

Manages the integration between signal service and instrument registry.
Implements event processing, cache management, and shadow mode testing.

Phase 3: Signal & Algo Engine Registry Integration
Session 5A: Event consumer implementation with config service integration
"""

import asyncio
import contextlib
import logging
import random
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from ..clients.instrument_registry_client import (
    create_registry_client,
    handle_registry_event,
)
from .registry_metrics import (
    get_registry_metrics,
    record_cache_invalidation_batch,
    record_registry_api_call,
    record_registry_event,
    record_shadow_mode_result,
    update_integration_health,
)

logger = logging.getLogger(__name__)

class IntegrationMode(Enum):
    DISABLED = "disabled"
    SHADOW = "shadow"
    ACTIVE = "active"

@dataclass
class ShadowModeResult:
    """Result of shadow mode comparison"""
    timestamp: str
    query: str
    registry_result: dict | None
    legacy_result: dict | None
    results_match: bool
    registry_latency_ms: float
    legacy_latency_ms: float
    error: str | None = None

class RegistryIntegrationService:
    """Main service for registry integration"""

    def __init__(self, signal_service_context):
        self.signal_service_context = signal_service_context
        self.registry_client = create_registry_client()
        self.mode = IntegrationMode.SHADOW  # Start in shadow mode
        self.shadow_results: list[ShadowModeResult] = []
        self.max_shadow_results = 1000  # Keep last 1000 results
        self.event_consumer_task = None
        self.is_running = False

        # Metrics
        self.metrics = {
            "events_processed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "registry_calls": 0,
            "registry_errors": 0,
            "fallback_activations": 0
        }

    async def start(self):
        """Start the registry integration service"""
        logger.info("Starting registry integration service...")
        self.is_running = True

        # Start event consumer
        if self.event_consumer_task is None:
            self.event_consumer_task = asyncio.create_task(
                self._consume_registry_events()
            )

        # Validate registry connection
        health = await self.registry_client.health_check()
        if health.get("registry_healthy"):
            logger.info("✅ Registry integration started successfully")
        else:
            logger.warning(f"⚠️  Registry health check failed: {health.get('error')}")

        return True

    async def stop(self):
        """Stop the registry integration service"""
        logger.info("Stopping registry integration service...")
        self.is_running = False

        if self.event_consumer_task:
            self.event_consumer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.event_consumer_task

        await self.registry_client.close()
        logger.info("Registry integration service stopped")

    async def _consume_registry_events(self):
        """Consume events from instrument registry"""
        event_types = [
            "instrument.updated",
            "chain.rebalance",
            "subscription.profile.changed"
        ]

        logger.info(f"Starting registry event consumption for: {event_types}")

        try:
            async for event in self.registry_client.consume_events(event_types):
                if not self.is_running:
                    break

                await self._process_registry_event(event)
                self.metrics["events_processed"] += 1

        except Exception as e:
            logger.error(f"Event consumption error: {e}")
            if self.is_running:
                # Retry after delay
                await asyncio.sleep(5)
                if self.is_running:
                    self.event_consumer_task = asyncio.create_task(
                        self._consume_registry_events()
                    )

    async def _process_registry_event(self, event: dict[str, Any]):
        """Process incoming registry events"""
        event_type = event.get("event_type", "unknown")
        start_time = time.time()

        try:
            # Use the signal service event handler
            await handle_registry_event(event, self.signal_service_context)

            # Additional registry-specific processing
            if event_type == "instrument.updated":
                await self._handle_instrument_update(event)
            elif event_type == "chain.rebalance":
                await self._handle_chain_rebalance(event)
            elif event_type == "subscription.profile.changed":
                await self._handle_subscription_change(event)

            # Record successful event processing
            processing_time = time.time() - start_time
            record_registry_event(event_type, processing_time, success=True)

        except Exception as e:
            logger.error(f"Error processing registry event: {e}")
            processing_time = time.time() - start_time
            record_registry_event(event_type, processing_time, success=False)

            # Record the error
            metrics_collector = get_registry_metrics()
            metrics_collector.record_error(
                error_type="event_processing",
                component="registry_integration",
                severity="error"
            )

    async def _handle_instrument_update(self, event: dict[str, Any]):
        """Handle instrument update events"""
        instrument_data = event.get("data", {})
        instrument_id = instrument_data.get("instrument_id")

        if instrument_id:
            logger.debug(f"Processing instrument update: {instrument_id}")

            # Invalidate signal caches for this instrument
            await self._invalidate_signal_caches(instrument_id)

            # Trigger Greeks recalculation if needed
            await self._trigger_greeks_recalculation(instrument_id)

    async def _handle_chain_rebalance(self, event: dict[str, Any]):
        """Handle option chain rebalance events"""
        chain_data = event.get("data", {})
        underlying = chain_data.get("underlying")

        if underlying:
            logger.debug(f"Processing chain rebalance: {underlying}")

            # Invalidate option chain related caches
            await self._invalidate_chain_caches(underlying)

            # Update moneyness calculations
            await self._update_moneyness_data(underlying)

    async def _handle_subscription_change(self, event: dict[str, Any]):
        """Handle subscription profile change events"""
        subscription_data = event.get("data", {})
        user_id = subscription_data.get("user_id")

        if user_id:
            logger.debug(f"Processing subscription change: {user_id}")

            # Update user subscription preferences
            await self._update_user_subscription_preferences(user_id, subscription_data)

    async def _invalidate_signal_caches(self, instrument_id: str):
        """Invalidate signal service caches for instrument"""
        logger.info(f"Invalidating signal caches for instrument: {instrument_id}")

        try:
            # Get Redis manager for cache operations
            from ..services.signal_redis_manager import RedisClusterManager
            from ..utils.redis import get_redis_client

            redis_client = get_redis_client()
            RedisClusterManager(redis_client)

            # Cache key patterns used by signal service
            cache_patterns = [
                f"greeks:{instrument_id}:*",          # Greeks calculations
                f"indicators:{instrument_id}:*",      # Technical indicators
                f"moneyness:{instrument_id}:*",       # Moneyness calculations
                f"chain_data:{instrument_id}:*",      # Option chain data
                f"historical:{instrument_id}:*",      # Historical data cache
                f"realtime:{instrument_id}:*",        # Real-time data cache
                f"premium:{instrument_id}:*",         # Premium/discount calculations
                f"volatility:{instrument_id}:*"       # Volatility data
            ]

            invalidated_count = 0
            for pattern in cache_patterns:
                try:
                    # Get keys matching pattern
                    keys = await redis_client.keys(pattern)
                    if keys:
                        # Delete matching keys
                        await redis_client.delete(*keys)
                        invalidated_count += len(keys)
                        logger.debug(f"Invalidated {len(keys)} keys for pattern: {pattern}")
                except Exception as e:
                    logger.error(f"Failed to invalidate cache pattern {pattern}: {e}")

            logger.info(f"Invalidated {invalidated_count} cache entries for instrument: {instrument_id}")

            # Record cache invalidation metrics
            record_cache_invalidation_batch("instrument", invalidated_count, success=True)
            self.metrics["cache_invalidations"] = self.metrics.get("cache_invalidations", 0) + invalidated_count

        except Exception as e:
            logger.error(f"Cache invalidation failed for instrument {instrument_id}: {e}")
            # Don't fail the event processing if cache invalidation fails
            self.metrics["cache_invalidation_errors"] = self.metrics.get("cache_invalidation_errors", 0) + 1

    async def _trigger_greeks_recalculation(self, instrument_id: str):
        """Trigger Greeks recalculation for updated instrument"""
        logger.info(f"Triggering Greeks recalculation for instrument: {instrument_id}")

        try:
            # Import signal service Greeks calculation components
            from ..services.greeks_calculation_engine import GreeksCalculationEngine
            from ..services.signal_redis_manager import RedisClusterManager
            from ..utils.redis import get_redis_client

            # Get current market data for the instrument
            redis_client = get_redis_client()
            redis_manager = RedisClusterManager(redis_client)

            # Get instrument market data
            market_data_key = f"market_data:{instrument_id}"
            market_data_str = await redis_manager.get_value(market_data_key)

            if market_data_str:
                import json
                market_data = json.loads(market_data_str)

                # Initialize Greeks engine
                greeks_engine = GreeksCalculationEngine()

                # Extract option parameters
                spot_price = market_data.get("spot_price")
                strike_price = market_data.get("strike_price")
                time_to_expiry = market_data.get("time_to_expiry")
                volatility = market_data.get("volatility")
                risk_free_rate = market_data.get("risk_free_rate", 0.05)
                option_type = market_data.get("option_type", "call")

                if all([spot_price, strike_price, time_to_expiry, volatility]):
                    # Calculate Greeks
                    greeks_result = await greeks_engine.calculate_greeks(
                        spot_price=float(spot_price),
                        strike_price=float(strike_price),
                        time_to_expiry=float(time_to_expiry),
                        volatility=float(volatility),
                        risk_free_rate=float(risk_free_rate),
                        option_type=option_type.lower()
                    )

                    # Store updated Greeks in cache
                    greeks_key = f"greeks:{instrument_id}:latest"
                    greeks_data = {
                        "timestamp": datetime.now().isoformat(),
                        "instrument_id": instrument_id,
                        "greeks": greeks_result,
                        "market_data": market_data
                    }

                    await redis_manager.store_with_expiry(
                        greeks_key,
                        json.dumps(greeks_data),
                        ttl=300  # 5 minute cache
                    )

                    logger.info(f"Greeks recalculated and cached for instrument: {instrument_id}")
                    self.metrics["greeks_recalculations"] = self.metrics.get("greeks_recalculations", 0) + 1

                else:
                    logger.warning(f"Insufficient market data for Greeks calculation: {instrument_id}")
            else:
                logger.warning(f"No market data found for instrument: {instrument_id}")

        except Exception as e:
            logger.error(f"Greeks recalculation failed for instrument {instrument_id}: {e}")
            self.metrics["greeks_calculation_errors"] = self.metrics.get("greeks_calculation_errors", 0) + 1

    async def _invalidate_chain_caches(self, underlying: str):
        """Invalidate option chain related caches"""
        logger.info(f"Invalidating option chain caches for underlying: {underlying}")

        try:
            from ..utils.redis import get_redis_client
            redis_client = get_redis_client()

            # Cache patterns for option chains
            chain_patterns = [
                f"chain:{underlying}:*",              # Full option chain data
                f"strikes:{underlying}:*",            # Strike price data
                f"expiries:{underlying}:*",           # Expiration data
                f"moneyness:{underlying}:*",          # Moneyness calculations
                f"oi:{underlying}:*",                 # Open interest data
                f"volume:{underlying}:*",             # Volume data
                f"chain_greeks:{underlying}:*"        # Chain-level Greeks
            ]

            invalidated_count = 0
            for pattern in chain_patterns:
                try:
                    keys = await redis_client.keys(pattern)
                    if keys:
                        await redis_client.delete(*keys)
                        invalidated_count += len(keys)
                        logger.debug(f"Invalidated {len(keys)} chain cache keys for pattern: {pattern}")
                except Exception as e:
                    logger.error(f"Failed to invalidate chain cache pattern {pattern}: {e}")

            logger.info(f"Invalidated {invalidated_count} chain cache entries for underlying: {underlying}")
            self.metrics["chain_cache_invalidations"] = self.metrics.get("chain_cache_invalidations", 0) + invalidated_count

        except Exception as e:
            logger.error(f"Chain cache invalidation failed for underlying {underlying}: {e}")
            self.metrics["chain_invalidation_errors"] = self.metrics.get("chain_invalidation_errors", 0) + 1

    async def _update_moneyness_data(self, underlying: str):
        """Update moneyness calculations for rebalanced chain"""
        logger.info(f"Updating moneyness data for underlying: {underlying}")

        try:
            # Import moneyness calculator
            import json

            from ..services.moneyness_calculator_local import MoneynessCalculator
            from ..utils.redis import get_redis_client

            redis_client = get_redis_client()
            moneyness_calc = MoneynessCalculator()

            # Get current spot price for underlying
            spot_key = f"spot_price:{underlying}"
            spot_price_str = await redis_client.get(spot_key)

            if spot_price_str:
                spot_price = float(spot_price_str)

                # Get option chain data for recalculation
                chain_key = f"raw_chain:{underlying}"
                chain_data_str = await redis_client.get(chain_key)

                if chain_data_str:
                    chain_data = json.loads(chain_data_str)

                    # Recalculate moneyness for all strikes
                    updated_moneyness = {}
                    for strike_str, _option_data in chain_data.items():
                        strike_price = float(strike_str)
                        moneyness = await moneyness_calc.calculate_moneyness(spot_price, strike_price)

                        updated_moneyness[strike_str] = {
                            "moneyness": moneyness,
                            "strike_price": strike_price,
                            "spot_price": spot_price,
                            "timestamp": datetime.now().isoformat()
                        }

                    # Store updated moneyness data
                    moneyness_key = f"moneyness:{underlying}:latest"
                    await redis_client.setex(
                        moneyness_key,
                        300,  # 5 minute cache
                        json.dumps(updated_moneyness)
                    )

                    logger.info(f"Updated moneyness for {len(updated_moneyness)} strikes for {underlying}")
                    self.metrics["moneyness_updates"] = self.metrics.get("moneyness_updates", 0) + len(updated_moneyness)

                else:
                    logger.warning(f"No chain data found for underlying: {underlying}")
            else:
                logger.warning(f"No spot price found for underlying: {underlying}")

        except Exception as e:
            logger.error(f"Moneyness update failed for underlying {underlying}: {e}")
            self.metrics["moneyness_update_errors"] = self.metrics.get("moneyness_update_errors", 0) + 1

    async def _update_user_subscription_preferences(self, user_id: str, subscription_data: dict):
        """Update user subscription preferences"""
        logger.info(f"Updating subscription preferences for user: {user_id}")

        try:
            import json

            from ..utils.redis import get_redis_client

            redis_client = get_redis_client()

            # Update user subscription cache
            subscription_key = f"user_subscription:{user_id}"
            preference_data = {
                "user_id": user_id,
                "subscription_data": subscription_data,
                "updated_at": datetime.now().isoformat(),
                "source": "registry_integration"
            }

            await redis_client.setex(
                subscription_key,
                3600,  # 1 hour cache
                json.dumps(preference_data)
            )

            # Invalidate user-specific caches that depend on subscription
            user_cache_patterns = [
                f"user_signals:{user_id}:*",          # User-specific signals
                f"user_portfolio:{user_id}:*",        # Portfolio data
                f"user_preferences:{user_id}:*",      # Preference cache
                f"subscription_limits:{user_id}:*"    # Subscription limits
            ]

            invalidated_count = 0
            for pattern in user_cache_patterns:
                try:
                    keys = await redis_client.keys(pattern)
                    if keys:
                        await redis_client.delete(*keys)
                        invalidated_count += len(keys)
                except Exception as e:
                    logger.error(f"Failed to invalidate user cache pattern {pattern}: {e}")

            logger.info(f"Updated subscription preferences and invalidated {invalidated_count} cache entries for user: {user_id}")
            self.metrics["subscription_updates"] = self.metrics.get("subscription_updates", 0) + 1
            self.metrics["user_cache_invalidations"] = self.metrics.get("user_cache_invalidations", 0) + invalidated_count

        except Exception as e:
            logger.error(f"Subscription preference update failed for user {user_id}: {e}")
            self.metrics["subscription_update_errors"] = self.metrics.get("subscription_update_errors", 0) + 1

    async def search_instruments_with_fallback(self, query: str, limit: int = 50) -> dict[str, Any]:
        """Search instruments with registry integration and fallback"""
        start_time = time.time()
        self.metrics["registry_calls"] += 1

        if self.mode == IntegrationMode.DISABLED:
            # Use legacy search only
            result = await self._legacy_instrument_search(query, limit)
            record_registry_api_call("search_instruments", time.time() - start_time, success=True)
            return result

        if self.mode == IntegrationMode.SHADOW:
            # Shadow mode: call both and compare
            return await self._shadow_search_comparison(query, limit)

        if self.mode == IntegrationMode.ACTIVE:
            # Use registry with fallback to legacy
            try:
                result = await self.registry_client.search_instruments(query, limit)
                record_registry_api_call("search_instruments", time.time() - start_time, success=True)
                self.metrics["cache_hits"] += 1
                return result
            except Exception as e:
                logger.warning(f"Registry search failed, using fallback: {e}")

                # Record failure and fallback metrics
                record_registry_api_call("search_instruments", time.time() - start_time, success=False)
                self.metrics["registry_errors"] += 1
                self.metrics["fallback_activations"] += 1

                # Record fallback activation
                metrics_collector = get_registry_metrics()
                metrics_collector.record_fallback_activation("legacy_search", str(e))

                # Check if we should auto-switch to shadow mode due to repeated failures
                if self.metrics["registry_errors"] > 10:
                    logger.warning("Multiple registry failures detected, considering mode switch")
                    await self._consider_mode_switch("registry_failures")

                return await self._legacy_instrument_search(query, limit)

        return {"instruments": [], "error": "Invalid integration mode"}

    async def _shadow_search_comparison(self, query: str, limit: int) -> dict[str, Any]:
        """Perform shadow mode comparison between registry and legacy search"""

        # Sample requests based on configuration
        if random.random() > 0.1:  # 10% sampling rate
            # Use legacy search without comparison
            return await self._legacy_instrument_search(query, limit)

        logger.debug(f"Shadow mode comparison for query: {query}")

        # Run both searches concurrently
        registry_start = time.time()
        legacy_start = time.time()

        try:
            # Start both searches
            registry_task = asyncio.create_task(
                self.registry_client.search_instruments(query, limit)
            )
            legacy_task = asyncio.create_task(
                self._legacy_instrument_search(query, limit)
            )

            # Wait for both with timeout
            registry_result = None
            legacy_result = None

            try:
                registry_result = await asyncio.wait_for(registry_task, timeout=5.0)
                registry_latency = (time.time() - registry_start) * 1000
            except TimeoutError:
                registry_result = {"error": "timeout"}
                registry_latency = 5000.0
            except Exception as e:
                registry_result = {"error": str(e)}
                registry_latency = (time.time() - registry_start) * 1000

            try:
                legacy_result = await asyncio.wait_for(legacy_task, timeout=5.0)
                legacy_latency = (time.time() - legacy_start) * 1000
            except TimeoutError:
                legacy_result = {"error": "timeout"}
                legacy_latency = 5000.0
            except Exception as e:
                legacy_result = {"error": str(e)}
                legacy_latency = (time.time() - legacy_start) * 1000

            # Compare results
            results_match = self._compare_search_results(registry_result, legacy_result)

            # Store shadow mode result
            shadow_result = ShadowModeResult(
                timestamp=datetime.now().isoformat(),
                query=query,
                registry_result=registry_result,
                legacy_result=legacy_result,
                results_match=results_match,
                registry_latency_ms=registry_latency,
                legacy_latency_ms=legacy_latency
            )

            self._store_shadow_result(shadow_result)

            # Record shadow mode metrics
            record_shadow_mode_result(
                registry_latency / 1000,  # Convert to seconds
                legacy_latency / 1000,
                results_match
            )

            # Return legacy result for now (shadow mode)
            return legacy_result

        except Exception as e:
            logger.error(f"Shadow mode comparison failed: {e}")
            return await self._legacy_instrument_search(query, limit)

    def _compare_search_results(self, registry_result: dict, legacy_result: dict) -> bool:
        """Compare registry and legacy search results"""
        # Simple comparison - can be enhanced
        registry_instruments = registry_result.get("instruments", [])
        legacy_instruments = legacy_result.get("instruments", [])

        if len(registry_instruments) != len(legacy_instruments):
            return False

        # Compare instrument IDs (basic comparison)
        registry_ids = {inst.get("instrument_id") for inst in registry_instruments}
        legacy_ids = {inst.get("instrument_id") for inst in legacy_instruments}

        return registry_ids == legacy_ids

    def _store_shadow_result(self, result: ShadowModeResult):
        """Store shadow mode comparison result"""
        self.shadow_results.append(result)

        # Keep only recent results
        if len(self.shadow_results) > self.max_shadow_results:
            self.shadow_results.pop(0)

        # Log interesting cases
        if not result.results_match:
            logger.warning(f"Shadow mode mismatch for query: {result.query}")

        if result.registry_latency_ms < result.legacy_latency_ms:
            logger.debug(f"Registry faster by {result.legacy_latency_ms - result.registry_latency_ms:.1f}ms")

    async def _legacy_instrument_search(self, query: str, limit: int) -> dict[str, Any]:
        """Legacy instrument search (placeholder)"""
        # This would integrate with existing signal service search
        logger.debug(f"Legacy search: {query}")

        # Placeholder implementation
        await asyncio.sleep(0.1)  # Simulate search time
        return {
            "instruments": [
                {"instrument_id": f"legacy_{query}_1", "symbol": query},
                {"instrument_id": f"legacy_{query}_2", "symbol": f"{query}_opt"}
            ],
            "total": 2,
            "source": "legacy"
        }

    def get_shadow_mode_summary(self) -> dict[str, Any]:
        """Get summary of shadow mode testing"""
        if not self.shadow_results:
            return {"message": "No shadow mode results available"}

        total_tests = len(self.shadow_results)
        matching_results = sum(1 for r in self.shadow_results if r.results_match)

        registry_times = [r.registry_latency_ms for r in self.shadow_results if r.registry_latency_ms > 0]
        legacy_times = [r.legacy_latency_ms for r in self.shadow_results if r.legacy_latency_ms > 0]

        return {
            "total_comparisons": total_tests,
            "matching_results": matching_results,
            "match_rate": (matching_results / total_tests * 100) if total_tests > 0 else 0,
            "registry_avg_latency_ms": sum(registry_times) / len(registry_times) if registry_times else 0,
            "legacy_avg_latency_ms": sum(legacy_times) / len(legacy_times) if legacy_times else 0,
            "recent_results": [asdict(r) for r in self.shadow_results[-10:]]  # Last 10 results
        }


    def get_metrics(self) -> dict[str, Any]:
        """Get integration service metrics"""
        return {
            **self.metrics,
            "mode": self.mode.value,
            "is_running": self.is_running,
            "shadow_results_count": len(self.shadow_results)
        }

    async def _consider_mode_switch(self, reason: str):
        """Consider automatic mode switching based on conditions"""
        logger.info(f"Evaluating mode switch due to: {reason}")

        current_mode = self.mode

        if reason == "registry_failures":
            # Switch to shadow mode if in active mode with failures
            if current_mode == IntegrationMode.ACTIVE:
                logger.warning("Switching to shadow mode due to registry failures")
                await self.switch_mode(IntegrationMode.SHADOW)

        elif reason == "shadow_mode_success":
            # Consider switching to active mode if shadow mode shows good results
            if current_mode == IntegrationMode.SHADOW:
                shadow_summary = self.get_shadow_mode_summary()
                match_rate = shadow_summary.get("match_rate", 0)
                registry_latency = shadow_summary.get("registry_avg_latency_ms", float('inf'))

                # Switch to active if match rate > 95% and latency < 100ms
                if match_rate > 95 and registry_latency < 100:
                    logger.info("Switching to active mode - shadow mode validation successful")
                    await self.switch_mode(IntegrationMode.ACTIVE)

        elif reason == "circuit_breaker_open":
            # Switch to disabled mode if circuit breaker is persistently open
            if current_mode in [IntegrationMode.ACTIVE, IntegrationMode.SHADOW]:
                logger.error("Switching to disabled mode due to circuit breaker")
                await self.switch_mode(IntegrationMode.DISABLED)

    async def switch_mode(self, new_mode: IntegrationMode, reason: str = "manual"):
        """Switch integration mode with metrics and logging"""
        old_mode = self.mode
        self.mode = new_mode

        logger.info(f"Registry integration mode changed: {old_mode.value} -> {new_mode.value} (reason: {reason})")

        # Record mode switch metrics
        metrics_collector = get_registry_metrics()
        metrics_collector.record_error(
            error_type="mode_switch",
            component="registry_integration",
            severity="info"
        )

        # Clear metrics when switching modes
        if new_mode != old_mode:
            old_metrics = self.metrics.copy()
            self.metrics = dict.fromkeys(self.metrics.keys(), 0)

            # Log final metrics before reset
            logger.info(f"Final metrics before mode switch: {old_metrics}")

        # Update health based on new mode
        healthy = new_mode != IntegrationMode.DISABLED
        update_integration_health(healthy, 100.0 if healthy else 50.0)

# Global registry integration service instance
_registry_service: RegistryIntegrationService | None = None

def get_registry_service(signal_service_context=None) -> RegistryIntegrationService:
    """Get or create registry integration service"""
    global _registry_service

    if _registry_service is None:
        _registry_service = RegistryIntegrationService(signal_service_context)

    return _registry_service

async def initialize_registry_integration(signal_service_context):
    """Initialize registry integration service"""
    service = get_registry_service(signal_service_context)
    await service.start()
    return service

async def shutdown_registry_integration():
    """Shutdown registry integration service"""
    global _registry_service

    if _registry_service:
        await _registry_service.stop()
        _registry_service = None
