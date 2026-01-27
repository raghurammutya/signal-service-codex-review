#!/usr/bin/env python3
"""
Enhanced Cache Invalidation Service

Session 5B: Cache invalidation logic with registry event triggers
Provides granular, selective cache invalidation with performance optimization.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

class InvalidationType(Enum):
    INSTRUMENT_UPDATE = "instrument_update"
    CHAIN_REBALANCE = "chain_rebalance"
    SUBSCRIPTION_CHANGE = "subscription_change"
    MARKET_CLOSE = "market_close"
    EXPIRY_ROLLOVER = "expiry_rollover"
    CORPORATE_ACTION = "corporate_action"

@dataclass
class InvalidationRequest:
    """Request for cache invalidation"""
    invalidation_type: InvalidationType
    instrument_id: str | None = None
    underlying: str | None = None
    user_id: str | None = None
    strike_price: float | None = None
    expiry_date: str | None = None
    reason: str = ""
    selective: bool = True
    metadata: dict[str, Any] = None

@dataclass
class InvalidationResult:
    """Result of cache invalidation operation"""
    invalidated_keys: int
    cache_types_affected: list[str]
    duration_ms: float
    success: bool
    error: str | None = None

class CacheKeyManager:
    """Manages cache key patterns and selective invalidation"""

    def __init__(self):
        # Cache key patterns organized by type for selective invalidation
        self.cache_patterns = {
            "greeks": {
                "individual": "greeks:{instrument_id}:*",
                "chain": "greeks:chain:{underlying}:*",
                "bulk": "greeks:bulk:{underlying}:*",
                "historical": "greeks:historical:{instrument_id}:*"
            },
            "indicators": {
                "individual": "indicators:{instrument_id}:*",
                "timeframe": "indicators:{instrument_id}:{timeframe}:*",
                "pattern": "indicators:pattern:{underlying}:*",
                "signal": "indicators:signal:{instrument_id}:*"
            },
            "moneyness": {
                "instrument": "moneyness:{instrument_id}:*",
                "strike": "moneyness:{underlying}:{strike}:*",
                "chain": "moneyness:chain:{underlying}:*",
                "classification": "moneyness:class:{underlying}:*"
            },
            "market_data": {
                "realtime": "market_data:{instrument_id}:realtime",
                "historical": "market_data:{instrument_id}:historical:*",
                "quotes": "market_data:{instrument_id}:quotes:*",
                "depth": "market_data:{instrument_id}:depth"
            },
            "user_data": {
                "signals": "user_signals:{user_id}:*",
                "portfolio": "user_portfolio:{user_id}:*",
                "preferences": "user_preferences:{user_id}:*",
                "subscriptions": "user_subscriptions:{user_id}:*"
            },
            "chain_data": {
                "full_chain": "chain:{underlying}:*",
                "strikes": "strikes:{underlying}:*",
                "expiries": "expiries:{underlying}:*",
                "oi_volume": "oi_volume:{underlying}:*"
            }
        }

    def get_invalidation_patterns(self, request: InvalidationRequest) -> dict[str, list[str]]:
        """Get cache patterns to invalidate based on request type"""
        patterns = {}

        if request.invalidation_type == InvalidationType.INSTRUMENT_UPDATE:
            if request.instrument_id:
                patterns["greeks"] = [
                    self.cache_patterns["greeks"]["individual"].format(instrument_id=request.instrument_id),
                    self.cache_patterns["greeks"]["historical"].format(instrument_id=request.instrument_id)
                ]
                patterns["indicators"] = [
                    self.cache_patterns["indicators"]["individual"].format(instrument_id=request.instrument_id),
                    self.cache_patterns["indicators"]["signal"].format(instrument_id=request.instrument_id)
                ]
                patterns["market_data"] = [
                    self.cache_patterns["market_data"]["realtime"].format(instrument_id=request.instrument_id),
                    self.cache_patterns["market_data"]["quotes"].format(instrument_id=request.instrument_id)
                ]
                patterns["moneyness"] = [
                    self.cache_patterns["moneyness"]["instrument"].format(instrument_id=request.instrument_id)
                ]

        elif request.invalidation_type == InvalidationType.CHAIN_REBALANCE:
            if request.underlying:
                patterns["chain_data"] = [
                    self.cache_patterns["chain_data"]["full_chain"].format(underlying=request.underlying),
                    self.cache_patterns["chain_data"]["strikes"].format(underlying=request.underlying),
                    self.cache_patterns["chain_data"]["oi_volume"].format(underlying=request.underlying)
                ]
                patterns["moneyness"] = [
                    self.cache_patterns["moneyness"]["chain"].format(underlying=request.underlying),
                    self.cache_patterns["moneyness"]["classification"].format(underlying=request.underlying)
                ]
                patterns["greeks"] = [
                    self.cache_patterns["greeks"]["chain"].format(underlying=request.underlying),
                    self.cache_patterns["greeks"]["bulk"].format(underlying=request.underlying)
                ]
                patterns["indicators"] = [
                    self.cache_patterns["indicators"]["pattern"].format(underlying=request.underlying)
                ]

        elif request.invalidation_type == InvalidationType.SUBSCRIPTION_CHANGE:
            if request.user_id:
                patterns["user_data"] = [
                    self.cache_patterns["user_data"]["signals"].format(user_id=request.user_id),
                    self.cache_patterns["user_data"]["portfolio"].format(user_id=request.user_id),
                    self.cache_patterns["user_data"]["preferences"].format(user_id=request.user_id),
                    self.cache_patterns["user_data"]["subscriptions"].format(user_id=request.user_id)
                ]

        elif request.invalidation_type == InvalidationType.EXPIRY_ROLLOVER:
            if request.underlying and request.expiry_date:
                # Invalidate expiry-specific caches
                patterns["chain_data"] = [
                    f"chain:{request.underlying}:{request.expiry_date}:*",
                    f"expiries:{request.underlying}:{request.expiry_date}:*"
                ]
                patterns["greeks"] = [
                    f"greeks:chain:{request.underlying}:{request.expiry_date}:*"
                ]

        return patterns

    def get_selective_patterns(self, request: InvalidationRequest) -> dict[str, list[str]]:
        """Get selective patterns for targeted invalidation"""
        if not request.selective:
            return self.get_invalidation_patterns(request)

        # For selective invalidation, only target specific sub-patterns
        patterns = {}
        base_patterns = self.get_invalidation_patterns(request)

        for cache_type, pattern_list in base_patterns.items():
            selective_patterns = []
            for pattern in pattern_list:
                # Add timestamp-based selectivity
                current_hour = datetime.now().hour
                selective_patterns.extend([
                    f"{pattern}:current",
                    f"{pattern}:h{current_hour}",
                    f"{pattern}:live"
                ])
            patterns[cache_type] = selective_patterns

        return patterns

class EnhancedCacheInvalidationService:
    """Enhanced cache invalidation with selective targeting and performance optimization"""

    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.key_manager = CacheKeyManager()

        # Performance tracking
        self.invalidation_stats = {
            "total_invalidations": 0,
            "total_keys_invalidated": 0,
            "total_time_ms": 0.0,
            "cache_type_stats": {},
            "error_count": 0
        }

        # Batch processing configuration
        self.batch_size = 1000
        self.max_concurrent_batches = 5

    async def invalidate_cache(self, request: InvalidationRequest) -> InvalidationResult:
        """Enhanced cache invalidation with selective targeting"""
        start_time = time.time()
        logger.info(f"Starting cache invalidation: {request.invalidation_type.value}")

        try:
            # Get patterns to invalidate
            invalidation_patterns = self.key_manager.get_selective_patterns(request) if request.selective else self.key_manager.get_invalidation_patterns(request)

            total_invalidated = 0
            cache_types_affected = []

            # Process each cache type concurrently
            invalidation_tasks = []
            for cache_type, patterns in invalidation_patterns.items():
                task = self._invalidate_cache_type(cache_type, patterns, request)
                invalidation_tasks.append(task)

            # Execute invalidations concurrently with semaphore
            semaphore = asyncio.Semaphore(self.max_concurrent_batches)

            async def bounded_invalidation(task):
                async with semaphore:
                    return await task

            results = await asyncio.gather(
                *[bounded_invalidation(task) for task in invalidation_tasks],
                return_exceptions=True
            )

            # Collect results
            for i, result in enumerate(results):
                cache_type = list(invalidation_patterns.keys())[i]

                if isinstance(result, Exception):
                    logger.error(f"Cache invalidation failed for {cache_type}: {result}")
                    continue

                cache_types_affected.append(cache_type)
                total_invalidated += result

                # Update stats
                if cache_type not in self.invalidation_stats["cache_type_stats"]:
                    self.invalidation_stats["cache_type_stats"][cache_type] = {"count": 0, "keys": 0}

                self.invalidation_stats["cache_type_stats"][cache_type]["count"] += 1
                self.invalidation_stats["cache_type_stats"][cache_type]["keys"] += result

            duration_ms = (time.time() - start_time) * 1000

            # Update global stats
            self.invalidation_stats["total_invalidations"] += 1
            self.invalidation_stats["total_keys_invalidated"] += total_invalidated
            self.invalidation_stats["total_time_ms"] += duration_ms

            # Log performance metrics
            logger.info(f"Cache invalidation completed: {total_invalidated} keys in {duration_ms:.1f}ms")

            # Record metrics
            from .registry_metrics import get_registry_metrics
            metrics = get_registry_metrics()
            metrics.record_cache_invalidation("enhanced", total_invalidated, True)

            # Record SLA monitoring metrics
            from .session_5b_sla_monitoring import record_invalidation_sla
            cache_patterns_count = dict(zip(invalidation_patterns.keys(), [r for r in results if not isinstance(r, Exception)], strict=False))
            record_invalidation_sla(
                service="enhanced_cache_invalidation",
                invalidation_type=request.invalidation_type.value,
                selective=request.selective,
                keys_invalidated=total_invalidated,
                duration_seconds=duration_ms / 1000,
                cache_patterns=cache_patterns_count
            )

            return InvalidationResult(
                invalidated_keys=total_invalidated,
                cache_types_affected=cache_types_affected,
                duration_ms=duration_ms,
                success=True
            )

        except Exception as e:
            self.invalidation_stats["error_count"] += 1
            duration_ms = (time.time() - start_time) * 1000

            logger.error(f"Cache invalidation failed: {e}")

            return InvalidationResult(
                invalidated_keys=0,
                cache_types_affected=[],
                duration_ms=duration_ms,
                success=False,
                error=str(e)
            )

    async def _invalidate_cache_type(self, cache_type: str, patterns: list[str], request: InvalidationRequest) -> int:
        """Invalidate caches for a specific cache type"""
        total_invalidated = 0

        for pattern in patterns:
            try:
                # Get keys matching pattern
                keys = await self.redis_client.keys(pattern)

                if keys:
                    # Batch delete for performance
                    invalidated_count = await self._batch_delete_keys(keys)
                    total_invalidated += invalidated_count

                    logger.debug(f"Invalidated {invalidated_count} keys for pattern: {pattern}")

            except Exception as e:
                logger.error(f"Failed to invalidate pattern {pattern}: {e}")
                continue

        return total_invalidated

    async def _batch_delete_keys(self, keys: list[str]) -> int:
        """Delete keys in batches for performance"""
        total_deleted = 0

        # Process keys in batches
        for i in range(0, len(keys), self.batch_size):
            batch = keys[i:i + self.batch_size]

            try:
                deleted_count = await self.redis_client.delete(*batch)
                total_deleted += deleted_count

            except Exception as e:
                logger.error(f"Batch delete failed for {len(batch)} keys: {e}")
                # Try individual deletes as fallback
                for key in batch:
                    try:
                        await self.redis_client.delete(key)
                        total_deleted += 1
                    except:
                        continue

        return total_deleted

    def get_performance_stats(self) -> dict[str, Any]:
        """Get cache invalidation performance statistics"""
        stats = self.invalidation_stats.copy()

        if stats["total_invalidations"] > 0:
            stats["avg_keys_per_invalidation"] = stats["total_keys_invalidated"] / stats["total_invalidations"]
            stats["avg_time_per_invalidation_ms"] = stats["total_time_ms"] / stats["total_invalidations"]
            stats["keys_per_second"] = stats["total_keys_invalidated"] / (stats["total_time_ms"] / 1000) if stats["total_time_ms"] > 0 else 0

        return stats

    async def scheduled_cleanup(self):
        """Scheduled cleanup of expired cache entries"""
        logger.info("Starting scheduled cache cleanup")

        cleanup_patterns = [
            "expired:*",
            "*:temp:*",
            "*:staging:*"
        ]

        InvalidationRequest(
            invalidation_type=InvalidationType.MARKET_CLOSE,
            reason="scheduled_cleanup",
            selective=False
        )

        total_cleaned = 0
        for pattern in cleanup_patterns:
            try:
                keys = await self.redis_client.keys(pattern)
                if keys:
                    cleaned = await self._batch_delete_keys(keys)
                    total_cleaned += cleaned
                    logger.debug(f"Cleaned {cleaned} keys for pattern: {pattern}")
            except Exception as e:
                logger.error(f"Cleanup failed for pattern {pattern}: {e}")

        logger.info(f"Scheduled cleanup completed: {total_cleaned} keys removed")
        return total_cleaned

# Global enhanced cache invalidation service
_enhanced_cache_service: EnhancedCacheInvalidationService | None = None

def get_enhanced_cache_service(redis_client=None) -> EnhancedCacheInvalidationService:
    """Get or create enhanced cache invalidation service"""
    global _enhanced_cache_service

    if _enhanced_cache_service is None:
        if redis_client is None:
            from ..utils.redis import get_redis_client
            redis_client = get_redis_client()

        _enhanced_cache_service = EnhancedCacheInvalidationService(redis_client)
        logger.info("Enhanced cache invalidation service initialized")

    return _enhanced_cache_service

# Convenience functions for common invalidation scenarios
async def invalidate_instrument_cache(instrument_id: str, reason: str = "instrument_update"):
    """Invalidate all caches for a specific instrument"""
    service = get_enhanced_cache_service()
    request = InvalidationRequest(
        invalidation_type=InvalidationType.INSTRUMENT_UPDATE,
        instrument_id=instrument_id,
        reason=reason,
        selective=True
    )
    return await service.invalidate_cache(request)

async def invalidate_chain_cache(underlying: str, reason: str = "chain_rebalance"):
    """Invalidate all caches for an option chain"""
    service = get_enhanced_cache_service()
    request = InvalidationRequest(
        invalidation_type=InvalidationType.CHAIN_REBALANCE,
        underlying=underlying,
        reason=reason,
        selective=True
    )
    return await service.invalidate_cache(request)

async def invalidate_user_cache(user_id: str, reason: str = "subscription_change"):
    """Invalidate all caches for a user"""
    service = get_enhanced_cache_service()
    request = InvalidationRequest(
        invalidation_type=InvalidationType.SUBSCRIPTION_CHANGE,
        user_id=user_id,
        reason=reason,
        selective=True
    )
    return await service.invalidate_cache(request)
