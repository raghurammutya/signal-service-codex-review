#!/usr/bin/env python3
"""
Technical Indicator Cache Coordinator

Session 5B: Coordinates technical indicator cache management with registry events
and integrates with enhanced cache invalidation system for optimal performance.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .enhanced_cache_invalidation_service import (
    get_enhanced_cache_service,
)

logger = logging.getLogger(__name__)

class IndicatorType(Enum):
    MOVING_AVERAGE = "moving_average"
    RSI = "rsi"
    BOLLINGER_BANDS = "bollinger_bands"
    MACD = "macd"
    STOCHASTIC = "stochastic"
    VOLUME_PROFILE = "volume_profile"
    VOLATILITY = "volatility"
    MOMENTUM = "momentum"

class TimeFrame(Enum):
    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1d"
    WEEK_1 = "1w"

@dataclass
class IndicatorCacheKey:
    """Structured cache key for technical indicators"""
    instrument_id: str
    indicator_type: IndicatorType
    timeframe: TimeFrame
    parameters: dict[str, Any]

    def to_cache_key(self) -> str:
        """Convert to Redis cache key"""
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(self.parameters.items()))
        return f"indicators:{self.instrument_id}:{self.indicator_type.value}:{self.timeframe.value}:{param_str}"

@dataclass
class IndicatorInvalidationContext:
    """Context for technical indicator cache invalidation"""
    instrument_id: str
    price_change_pct: float | None = None
    volume_spike: bool = False
    timeframe_affected: set[TimeFrame] = None
    indicator_types_affected: set[IndicatorType] = None
    recalc_required: bool = True
    historical_data_updated: bool = False

class TechnicalIndicatorCacheCoordinator:
    """Coordinates technical indicator cache management with registry events"""

    def __init__(self, redis_client, indicator_engine):
        self.redis_client = redis_client
        self.indicator_engine = indicator_engine
        self.cache_service = get_enhanced_cache_service(redis_client)

        # Cache TTL configuration by timeframe
        self.cache_ttls = {
            TimeFrame.MINUTE_1: 60,      # 1 minute
            TimeFrame.MINUTE_5: 300,     # 5 minutes
            TimeFrame.MINUTE_15: 900,    # 15 minutes
            TimeFrame.HOUR_1: 3600,      # 1 hour
            TimeFrame.HOUR_4: 14400,     # 4 hours
            TimeFrame.DAY_1: 86400,      # 24 hours
            TimeFrame.WEEK_1: 604800     # 1 week
        }

        # Indicator calculation dependencies
        self.indicator_dependencies = {
            IndicatorType.MOVING_AVERAGE: ["price_history"],
            IndicatorType.RSI: ["price_history", "volume_history"],
            IndicatorType.BOLLINGER_BANDS: ["price_history", "volatility"],
            IndicatorType.MACD: ["price_history"],
            IndicatorType.STOCHASTIC: ["price_history", "high_low_history"],
            IndicatorType.VOLUME_PROFILE: ["volume_history", "price_history"],
            IndicatorType.VOLATILITY: ["price_history", "time_series"],
            IndicatorType.MOMENTUM: ["price_history", "volume_history"]
        }

        # Invalidation thresholds
        self.invalidation_thresholds = {
            "price_change_pct": 1.0,        # 1% price change
            "volume_spike_multiplier": 2.0,   # 2x average volume
            "volatility_change_pct": 10.0,   # 10% volatility change
            "time_decay_minutes": 5           # Age threshold for live indicators
        }

        # Performance metrics
        self.performance_metrics = {
            "cache_invalidations": 0,
            "indicator_recalculations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "coordination_time_ms": 0.0,
            "batch_operations": 0
        }

    async def handle_instrument_market_data_update(self, instrument_id: str, market_data: dict[str, Any]) -> dict[str, Any]:
        """Handle market data update with intelligent indicator cache coordination"""
        logger.info(f"Coordinating indicator cache for market data update: {instrument_id}")

        start_time = time.time()
        result = {
            "instrument_id": instrument_id,
            "indicators_invalidated": [],
            "indicators_recalculated": [],
            "coordination_success": False,
            "performance": {}
        }

        try:
            # Analyze market data changes to determine invalidation scope
            invalidation_context = await self._analyze_market_data_impact(instrument_id, market_data)

            if invalidation_context.recalc_required:
                # Selective indicator cache invalidation
                invalidated_indicators = await self._selective_indicator_invalidation(
                    instrument_id, invalidation_context
                )
                result["indicators_invalidated"] = invalidated_indicators

                # Coordinate indicator recalculation based on priorities
                recalculated_indicators = await self._coordinate_indicator_recalculation(
                    instrument_id, invalidation_context
                )
                result["indicators_recalculated"] = recalculated_indicators

                result["coordination_success"] = True
                self.performance_metrics["cache_invalidations"] += len(invalidated_indicators)
                self.performance_metrics["indicator_recalculations"] += len(recalculated_indicators)
            else:
                logger.debug(f"Market data update doesn't require indicator recalculation: {instrument_id}")

            # Record performance metrics
            coordination_time = (time.time() - start_time) * 1000
            result["performance"] = {
                "coordination_time_ms": coordination_time,
                "invalidation_context": {
                    "price_change_pct": invalidation_context.price_change_pct,
                    "volume_spike": invalidation_context.volume_spike,
                    "timeframes_affected": len(invalidation_context.timeframe_affected or []),
                    "indicators_affected": len(invalidation_context.indicator_types_affected or [])
                }
            }

            self.performance_metrics["coordination_time_ms"] += coordination_time

            return result

        except Exception as e:
            logger.error(f"Indicator cache coordination failed for {instrument_id}: {e}")
            result["error"] = str(e)
            return result

    async def _analyze_market_data_impact(self, instrument_id: str, market_data: dict[str, Any]) -> IndicatorInvalidationContext:
        """Analyze market data to determine indicator cache invalidation scope"""

        context = IndicatorInvalidationContext(
            instrument_id=instrument_id,
            timeframe_affected=set(),
            indicator_types_affected=set()
        )

        try:
            # Get previous market data for comparison
            previous_data = await self._get_previous_market_data(instrument_id)

            if previous_data:
                # Calculate price change percentage
                current_price = float(market_data.get("price", 0))
                previous_price = float(previous_data.get("price", 0))

                if previous_price > 0:
                    price_change_pct = abs(current_price - previous_price) / previous_price * 100
                    context.price_change_pct = price_change_pct

                    # Determine if price change is significant
                    if price_change_pct > self.invalidation_thresholds["price_change_pct"]:
                        context.recalc_required = True

                        # All price-based indicators affected
                        price_sensitive_indicators = [
                            IndicatorType.MOVING_AVERAGE, IndicatorType.RSI,
                            IndicatorType.BOLLINGER_BANDS, IndicatorType.MACD,
                            IndicatorType.MOMENTUM
                        ]
                        context.indicator_types_affected.update(price_sensitive_indicators)

                # Check volume spike
                current_volume = float(market_data.get("volume", 0))
                previous_volume = float(previous_data.get("volume", 0))

                if previous_volume > 0:
                    volume_ratio = current_volume / previous_volume
                    if volume_ratio > self.invalidation_thresholds["volume_spike_multiplier"]:
                        context.volume_spike = True
                        context.recalc_required = True

                        # Volume-sensitive indicators affected
                        volume_sensitive_indicators = [
                            IndicatorType.VOLUME_PROFILE, IndicatorType.RSI,
                            IndicatorType.STOCHASTIC, IndicatorType.MOMENTUM
                        ]
                        context.indicator_types_affected.update(volume_sensitive_indicators)

                # Check volatility changes
                current_volatility = float(market_data.get("implied_volatility", 0))
                previous_volatility = float(previous_data.get("implied_volatility", 0))

                if previous_volatility > 0:
                    vol_change_pct = abs(current_volatility - previous_volatility) / previous_volatility * 100
                    if vol_change_pct > self.invalidation_thresholds["volatility_change_pct"]:
                        context.indicator_types_affected.add(IndicatorType.VOLATILITY)
                        context.indicator_types_affected.add(IndicatorType.BOLLINGER_BANDS)

            # Determine affected timeframes based on change magnitude
            if context.price_change_pct:
                if context.price_change_pct > 0.5:  # Small changes affect short timeframes
                    context.timeframe_affected.update([TimeFrame.MINUTE_1, TimeFrame.MINUTE_5])
                if context.price_change_pct > 1.0:  # Medium changes affect medium timeframes
                    context.timeframe_affected.update([TimeFrame.MINUTE_15, TimeFrame.HOUR_1])
                if context.price_change_pct > 2.0:  # Large changes affect all timeframes
                    context.timeframe_affected.update([TimeFrame.HOUR_4, TimeFrame.DAY_1])
                if context.price_change_pct > 5.0:  # Major changes affect weekly
                    context.timeframe_affected.add(TimeFrame.WEEK_1)

            return context

        except Exception as e:
            logger.error(f"Market data impact analysis failed for {instrument_id}: {e}")
            # Default to minimal recalculation scope
            context.recalc_required = True
            context.timeframe_affected = {TimeFrame.MINUTE_1, TimeFrame.MINUTE_5}
            context.indicator_types_affected = {IndicatorType.MOVING_AVERAGE}
            return context

    async def _selective_indicator_invalidation(self, instrument_id: str, context: IndicatorInvalidationContext) -> list[str]:
        """Perform selective invalidation of indicator caches"""
        invalidated_indicators = []

        try:
            # Build cache patterns for selective invalidation
            cache_patterns = []

            for indicator_type in context.indicator_types_affected:
                for timeframe in context.timeframe_affected:
                    # Pattern for specific indicator + timeframe combinations
                    pattern = f"indicators:{instrument_id}:{indicator_type.value}:{timeframe.value}:*"
                    cache_patterns.append(pattern)

            # If historical data was updated, invalidate longer timeframe indicators
            if context.historical_data_updated:
                for timeframe in [TimeFrame.DAY_1, TimeFrame.WEEK_1]:
                    pattern = f"indicators:{instrument_id}:*:{timeframe.value}:*"
                    cache_patterns.append(pattern)

            # Batch invalidation for performance
            for pattern in cache_patterns:
                try:
                    keys = await self.redis_client.keys(pattern)
                    if keys:
                        await self.redis_client.delete(*keys)
                        invalidated_indicators.extend([key.split(':')[2] for key in keys])
                        logger.debug(f"Invalidated {len(keys)} indicator cache entries for pattern: {pattern}")
                except Exception as e:
                    logger.error(f"Failed to invalidate indicator pattern {pattern}: {e}")

            logger.info(f"Selectively invalidated {len(invalidated_indicators)} indicator cache entries for {instrument_id}")
            return list(set(invalidated_indicators))  # Remove duplicates

        except Exception as e:
            logger.error(f"Selective indicator invalidation failed for {instrument_id}: {e}")
            return []

    async def _coordinate_indicator_recalculation(self, instrument_id: str, context: IndicatorInvalidationContext) -> list[str]:
        """Coordinate indicator recalculation based on priorities and dependencies"""
        recalculated_indicators = []

        try:
            # Prioritize indicator recalculation based on usage and dependencies
            priority_indicators = self._get_indicator_priority_order(context.indicator_types_affected)

            # Batch recalculation for efficiency
            recalc_tasks = []
            for indicator_type in priority_indicators:
                for timeframe in context.timeframe_affected:
                    task = self._recalculate_indicator(
                        instrument_id, indicator_type, timeframe, context
                    )
                    recalc_tasks.append(task)

            # Execute recalculations with concurrency control
            semaphore = asyncio.Semaphore(3)  # Max 3 concurrent calculations

            async def bounded_recalc(task):
                async with semaphore:
                    return await task

            results = await asyncio.gather(
                *[bounded_recalc(task) for task in recalc_tasks],
                return_exceptions=True
            )

            # Collect successful recalculations
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Indicator recalculation failed: {result}")
                    continue

                if result and result.get("success"):
                    indicator_key = result.get("indicator_key", "unknown")
                    recalculated_indicators.append(indicator_key)

            logger.info(f"Recalculated {len(recalculated_indicators)} indicators for {instrument_id}")
            return recalculated_indicators

        except Exception as e:
            logger.error(f"Indicator recalculation coordination failed for {instrument_id}: {e}")
            return []

    async def _recalculate_indicator(self, instrument_id: str, indicator_type: IndicatorType, timeframe: TimeFrame, context: IndicatorInvalidationContext) -> dict[str, Any]:
        """Recalculate specific indicator for instrument and timeframe"""

        start_time = time.time()
        result = {
            "success": False,
            "indicator_key": f"{indicator_type.value}_{timeframe.value}",
            "duration_ms": 0
        }

        try:
            # Get historical data for calculation
            historical_data = await self._get_historical_data(instrument_id, timeframe)

            if not historical_data:
                logger.warning(f"No historical data available for {instrument_id} {timeframe.value}")
                return result

            # Calculate indicator based on type
            calculation_result = await self._calculate_indicator_value(
                indicator_type, historical_data, timeframe
            )

            if calculation_result:
                # Cache the calculated indicator
                cache_key = IndicatorCacheKey(
                    instrument_id=instrument_id,
                    indicator_type=indicator_type,
                    timeframe=timeframe,
                    parameters=calculation_result.get("parameters", {})
                )

                await self._cache_indicator_result(
                    cache_key, calculation_result, timeframe
                )

                result["success"] = True
                result["calculation_result"] = calculation_result

            result["duration_ms"] = (time.time() - start_time) * 1000
            return result

        except Exception as e:
            logger.error(f"Indicator recalculation failed for {instrument_id} {indicator_type.value} {timeframe.value}: {e}")
            result["error"] = str(e)
            result["duration_ms"] = (time.time() - start_time) * 1000
            return result

    async def _calculate_indicator_value(self, indicator_type: IndicatorType, historical_data: list[dict], timeframe: TimeFrame) -> dict[str, Any] | None:
        """Calculate indicator value using indicator engine"""

        try:
            if indicator_type == IndicatorType.MOVING_AVERAGE:
                # Simple Moving Average calculation
                period = self._get_default_period(indicator_type, timeframe)
                prices = [float(d.get("close", 0)) for d in historical_data[-period:]]
                if len(prices) >= period:
                    sma_value = sum(prices) / len(prices)
                    return {
                        "value": sma_value,
                        "type": "sma",
                        "period": period,
                        "parameters": {"period": period},
                        "timestamp": datetime.now().isoformat()
                    }

            elif indicator_type == IndicatorType.RSI:
                # RSI calculation
                period = self._get_default_period(indicator_type, timeframe)
                if hasattr(self.indicator_engine, 'calculate_rsi'):
                    rsi_value = await self.indicator_engine.calculate_rsi(
                        historical_data, period
                    )
                    return {
                        "value": rsi_value,
                        "type": "rsi",
                        "period": period,
                        "parameters": {"period": period},
                        "timestamp": datetime.now().isoformat()
                    }

            elif indicator_type == IndicatorType.BOLLINGER_BANDS:
                # Bollinger Bands calculation
                period = self._get_default_period(indicator_type, timeframe)
                if hasattr(self.indicator_engine, 'calculate_bollinger_bands'):
                    bb_result = await self.indicator_engine.calculate_bollinger_bands(
                        historical_data, period, 2.0  # 2 standard deviations
                    )
                    return {
                        "upper_band": bb_result.get("upper"),
                        "middle_band": bb_result.get("middle"),
                        "lower_band": bb_result.get("lower"),
                        "type": "bollinger_bands",
                        "period": period,
                        "parameters": {"period": period, "std_dev": 2.0},
                        "timestamp": datetime.now().isoformat()
                    }

            # Add more indicator calculations as needed
            logger.warning(f"Indicator calculation not implemented for {indicator_type.value}")
            return None

        except Exception as e:
            logger.error(f"Indicator calculation failed for {indicator_type.value}: {e}")
            return None

    def _get_default_period(self, indicator_type: IndicatorType, timeframe: TimeFrame) -> int:
        """Get default period for indicator based on timeframe"""

        base_periods = {
            IndicatorType.MOVING_AVERAGE: 20,
            IndicatorType.RSI: 14,
            IndicatorType.BOLLINGER_BANDS: 20,
            IndicatorType.MACD: 26,
            IndicatorType.STOCHASTIC: 14
        }

        # Adjust period based on timeframe
        base_period = base_periods.get(indicator_type, 20)

        if timeframe in [TimeFrame.MINUTE_1, TimeFrame.MINUTE_5]:
            return base_period
        if timeframe in [TimeFrame.MINUTE_15, TimeFrame.HOUR_1]:
            return max(10, base_period // 2)
        if timeframe in [TimeFrame.HOUR_4, TimeFrame.DAY_1]:
            return base_period
        if timeframe == TimeFrame.WEEK_1:
            return min(52, base_period * 2)

        return base_period

    def _get_indicator_priority_order(self, indicator_types: set[IndicatorType]) -> list[IndicatorType]:
        """Get indicator recalculation priority order"""

        # Priority order based on usage and dependencies
        priority_order = [
            IndicatorType.MOVING_AVERAGE,    # Most basic, used by others
            IndicatorType.VOLATILITY,        # Used by Bollinger Bands
            IndicatorType.BOLLINGER_BANDS,   # Depends on volatility
            IndicatorType.RSI,               # Standalone momentum indicator
            IndicatorType.MACD,              # Trend following
            IndicatorType.STOCHASTIC,        # Oscillator
            IndicatorType.VOLUME_PROFILE,    # Volume analysis
            IndicatorType.MOMENTUM           # Derived indicators
        ]

        # Return only requested indicators in priority order
        return [ind for ind in priority_order if ind in indicator_types]

    async def _cache_indicator_result(self, cache_key: IndicatorCacheKey, result: dict[str, Any], timeframe: TimeFrame):
        """Cache indicator calculation result"""

        try:
            cache_data = {
                "indicator_result": result,
                "cache_key": cache_key.to_cache_key(),
                "cached_at": datetime.now().isoformat(),
                "timeframe": timeframe.value
            }

            # Get TTL for timeframe
            ttl = self.cache_ttls.get(timeframe, 300)

            # Store in cache
            await self.redis_client.setex(
                cache_key.to_cache_key(),
                ttl,
                json.dumps(cache_data)
            )

            logger.debug(f"Cached indicator result with TTL {ttl}s: {cache_key.to_cache_key()}")

        except Exception as e:
            logger.error(f"Failed to cache indicator result: {e}")

    async def _get_previous_market_data(self, instrument_id: str) -> dict[str, Any] | None:
        """Get previous market data for comparison"""

        try:
            market_data_key = f"market_data:{instrument_id}:previous"
            data_str = await self.redis_client.get(market_data_key)

            if data_str:
                return json.loads(data_str)

            return None

        except Exception as e:
            logger.error(f"Failed to get previous market data for {instrument_id}: {e}")
            return None

    async def _get_historical_data(self, instrument_id: str, timeframe: TimeFrame) -> list[dict[str, Any]]:
        """Get historical data for indicator calculation"""

        try:
            historical_key = f"historical:{instrument_id}:{timeframe.value}"
            data_str = await self.redis_client.get(historical_key)

            if data_str:
                return json.loads(data_str)

            # Fallback: get from historical data service
            logger.warning(f"No cached historical data for {instrument_id} {timeframe.value}")
            return []

        except Exception as e:
            logger.error(f"Failed to get historical data for {instrument_id}: {e}")
            return []

    async def handle_chain_rebalance_indicators(self, underlying: str, rebalance_data: dict[str, Any]) -> dict[str, Any]:
        """Handle option chain rebalance for indicator coordination"""
        logger.info(f"Coordinating indicators for chain rebalance: {underlying}")

        start_time = time.time()
        result = {
            "underlying": underlying,
            "instruments_processed": 0,
            "indicators_coordinated": 0,
            "success": False
        }

        try:
            # Get all instruments in the rebalanced chain
            chain_instruments = await self._get_chain_instruments(underlying)

            if chain_instruments:
                # Coordinate indicators for each instrument in the chain
                coordination_tasks = []
                for instrument_id in chain_instruments:
                    # Create mock market data update for coordination
                    market_data = {"price": 0, "volume": 0, "source": "chain_rebalance"}
                    task = self.handle_instrument_market_data_update(instrument_id, market_data)
                    coordination_tasks.append(task)

                # Execute coordinations concurrently
                coordination_results = await asyncio.gather(
                    *coordination_tasks, return_exceptions=True
                )

                successful_coordinations = [
                    r for r in coordination_results
                    if not isinstance(r, Exception) and r.get("coordination_success")
                ]

                result["instruments_processed"] = len(chain_instruments)
                result["indicators_coordinated"] = sum(
                    len(r.get("indicators_recalculated", []))
                    for r in successful_coordinations
                )
                result["success"] = True

            result["duration_ms"] = (time.time() - start_time) * 1000
            return result

        except Exception as e:
            logger.error(f"Chain rebalance indicator coordination failed for {underlying}: {e}")
            result["error"] = str(e)
            result["duration_ms"] = (time.time() - start_time) * 1000
            return result

    async def _get_chain_instruments(self, underlying: str) -> list[str]:
        """Get all instruments in an option chain"""

        try:
            chain_key = f"chain:{underlying}:instruments"
            instruments_data = await self.redis_client.get(chain_key)

            if instruments_data:
                return json.loads(instruments_data)

            return []

        except Exception as e:
            logger.error(f"Failed to get chain instruments for {underlying}: {e}")
            return []

    def get_performance_metrics(self) -> dict[str, Any]:
        """Get indicator cache coordination performance metrics"""

        metrics = self.performance_metrics.copy()

        # Calculate derived metrics
        total_operations = metrics["cache_invalidations"] + metrics["indicator_recalculations"]
        if total_operations > 0:
            metrics["avg_coordination_time_ms"] = metrics["coordination_time_ms"] / total_operations

        cache_operations = metrics["cache_hits"] + metrics["cache_misses"]
        if cache_operations > 0:
            metrics["cache_hit_rate"] = metrics["cache_hits"] / cache_operations * 100

        return metrics

# Factory function
def create_technical_indicator_cache_coordinator(redis_client=None, indicator_engine=None):
    """Create technical indicator cache coordinator instance"""
    if redis_client is None:
        from ..utils.redis import get_redis_client
        redis_client = get_redis_client()

    if indicator_engine is None:
        from ..services.technical_indicator_engine import TechnicalIndicatorEngine
        indicator_engine = TechnicalIndicatorEngine()

    return TechnicalIndicatorCacheCoordinator(redis_client, indicator_engine)
