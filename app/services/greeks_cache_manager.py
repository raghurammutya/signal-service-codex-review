#!/usr/bin/env python3
"""
Greeks Cache Manager

Session 5B: Greeks-specific cache management with selective invalidation
and optimized recalculation triggers based on registry events.
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
    InvalidationRequest,
    InvalidationType,
    get_enhanced_cache_service,
)

logger = logging.getLogger(__name__)

class GreeksCalculationType(Enum):
    INDIVIDUAL = "individual"
    BULK_CHAIN = "bulk_chain"
    HISTORICAL = "historical"
    SENSITIVITY = "sensitivity"

@dataclass
class GreeksInvalidationContext:
    """Context for Greeks cache invalidation"""
    instrument_id: str | None = None
    underlying: str | None = None
    spot_price: float | None = None
    volatility_change: float | None = None
    time_decay: bool = False
    dividend_update: bool = False
    interest_rate_change: bool = False
    expiry_approaching: bool = False

@dataclass
class GreeksRecalculationRequest:
    """Request for Greeks recalculation"""
    instruments: list[str]
    calculation_type: GreeksCalculationType
    priority: str = "normal"  # high, normal, low
    reason: str = ""
    force_recalc: bool = False
    context: GreeksInvalidationContext = None

class GreeksCacheManager:
    """Manages Greeks cache with selective invalidation and intelligent recalculation"""

    def __init__(self, redis_client, greeks_engine):
        self.redis_client = redis_client
        self.greeks_engine = greeks_engine
        self.cache_service = get_enhanced_cache_service(redis_client)

        # Greeks cache configuration
        self.cache_ttls = {
            "live_greeks": 60,          # 1 minute for live Greeks
            "historical_greeks": 3600,  # 1 hour for historical
            "bulk_greeks": 300,         # 5 minutes for bulk calculations
            "sensitivity_greeks": 1800  # 30 minutes for sensitivity analysis
        }

        # Recalculation thresholds
        self.recalc_thresholds = {
            "spot_price_change_pct": 0.5,      # 0.5% spot price change
            "volatility_change_pct": 5.0,      # 5% volatility change
            "time_to_expiry_days": 7,          # Within 7 days of expiry
            "delta_threshold": 0.05,           # Delta change threshold
            "gamma_threshold": 0.02            # Gamma change threshold
        }

        # Performance metrics
        self.performance_stats = {
            "cache_invalidations": 0,
            "recalculations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "avg_calc_time_ms": 0.0
        }

    async def handle_instrument_update(self, instrument_id: str, market_data: dict[str, Any]) -> dict[str, Any]:
        """Handle instrument update with intelligent Greeks cache management"""
        logger.info(f"Processing Greeks cache update for instrument: {instrument_id}")

        start_time = time.time()
        result = {
            "instrument_id": instrument_id,
            "cache_invalidated": False,
            "recalculation_triggered": False,
            "cached_greeks_updated": False,
            "performance": {}
        }

        try:
            # Get current cached Greeks for comparison
            cached_greeks = await self._get_cached_greeks(instrument_id)

            # Determine if recalculation is needed
            recalc_needed, context = await self._should_recalculate_greeks(
                instrument_id, market_data, cached_greeks
            )

            if recalc_needed:
                # Selective cache invalidation
                await self._selective_greeks_invalidation(instrument_id, context)
                result["cache_invalidated"] = True
                self.performance_stats["cache_invalidations"] += 1

                # Trigger recalculation
                recalc_request = GreeksRecalculationRequest(
                    instruments=[instrument_id],
                    calculation_type=GreeksCalculationType.INDIVIDUAL,
                    priority="high" if context.expiry_approaching else "normal",
                    reason="instrument_update",
                    force_recalc=True,
                    context=context
                )

                greeks_result = await self._recalculate_greeks(recalc_request)
                result["recalculation_triggered"] = True
                result["cached_greeks_updated"] = greeks_result["success"]
                self.performance_stats["recalculations"] += 1

                # Update performance metrics
                result["performance"] = {
                    "recalc_time_ms": greeks_result.get("duration_ms", 0),
                    "keys_invalidated": greeks_result.get("keys_invalidated", 0),
                    "cache_efficiency": await self._calculate_cache_efficiency()
                }
            else:
                logger.debug(f"Greeks recalculation not needed for {instrument_id}")
                self.performance_stats["cache_hits"] += 1

            # Record timing
            total_time = (time.time() - start_time) * 1000
            result["performance"]["total_time_ms"] = total_time

            return result

        except Exception as e:
            logger.error(f"Greeks cache management failed for {instrument_id}: {e}")
            result["error"] = str(e)
            return result

    async def handle_chain_rebalance(self, underlying: str, rebalance_data: dict[str, Any]) -> dict[str, Any]:
        """Handle option chain rebalance with bulk Greeks recalculation"""
        logger.info(f"Processing Greeks cache for chain rebalance: {underlying}")

        start_time = time.time()
        result = {
            "underlying": underlying,
            "affected_instruments": [],
            "bulk_recalculation": False,
            "performance": {}
        }

        try:
            # Get all instruments in the chain
            chain_instruments = await self._get_chain_instruments(underlying)
            result["affected_instruments"] = chain_instruments

            # Bulk cache invalidation for the entire chain
            invalidation_request = InvalidationRequest(
                invalidation_type=InvalidationType.CHAIN_REBALANCE,
                underlying=underlying,
                reason="chain_rebalance",
                selective=True
            )

            invalidation_result = await self.cache_service.invalidate_cache(invalidation_request)

            # Bulk Greeks recalculation for efficiency
            if len(chain_instruments) > 5:  # Use bulk calculation for efficiency
                recalc_request = GreeksRecalculationRequest(
                    instruments=chain_instruments,
                    calculation_type=GreeksCalculationType.BULK_CHAIN,
                    priority="high",
                    reason="chain_rebalance",
                    force_recalc=True
                )

                bulk_result = await self._recalculate_greeks(recalc_request)
                result["bulk_recalculation"] = bulk_result["success"]

                result["performance"] = {
                    "invalidation_time_ms": invalidation_result.duration_ms,
                    "recalc_time_ms": bulk_result.get("duration_ms", 0),
                    "total_instruments": len(chain_instruments),
                    "keys_invalidated": invalidation_result.invalidated_keys
                }
            else:
                # Individual recalculation for small chains
                individual_results = []
                for instrument_id in chain_instruments:
                    recalc_request = GreeksRecalculationRequest(
                        instruments=[instrument_id],
                        calculation_type=GreeksCalculationType.INDIVIDUAL,
                        priority="normal",
                        reason="chain_rebalance"
                    )

                    individual_result = await self._recalculate_greeks(recalc_request)
                    individual_results.append(individual_result)

                result["individual_recalculations"] = len([r for r in individual_results if r["success"]])

            total_time = (time.time() - start_time) * 1000
            result["performance"]["total_time_ms"] = total_time

            return result

        except Exception as e:
            logger.error(f"Chain rebalance Greeks processing failed for {underlying}: {e}")
            result["error"] = str(e)
            return result

    async def _should_recalculate_greeks(self, instrument_id: str, market_data: dict[str, Any], cached_greeks: dict | None) -> tuple[bool, GreeksInvalidationContext]:
        """Intelligent decision on whether Greeks recalculation is needed"""

        context = GreeksInvalidationContext(instrument_id=instrument_id)

        if not cached_greeks:
            # No cached Greeks, recalculation needed
            return True, context

        current_spot = market_data.get("spot_price")
        current_volatility = market_data.get("implied_volatility")
        cached_spot = cached_greeks.get("market_data", {}).get("spot_price")
        cached_volatility = cached_greeks.get("market_data", {}).get("implied_volatility")

        recalc_reasons = []

        # Check spot price change
        if current_spot and cached_spot:
            spot_change_pct = abs(current_spot - cached_spot) / cached_spot * 100
            if spot_change_pct > self.recalc_thresholds["spot_price_change_pct"]:
                recalc_reasons.append(f"spot_change_{spot_change_pct:.2f}%")
                context.spot_price = current_spot

        # Check volatility change
        if current_volatility and cached_volatility:
            vol_change_pct = abs(current_volatility - cached_volatility) / cached_volatility * 100
            if vol_change_pct > self.recalc_thresholds["volatility_change_pct"]:
                recalc_reasons.append(f"volatility_change_{vol_change_pct:.2f}%")
                context.volatility_change = vol_change_pct

        # Check time decay (for options)
        if market_data.get("time_to_expiry"):
            time_to_expiry = market_data["time_to_expiry"]
            if time_to_expiry < self.recalc_thresholds["time_to_expiry_days"]:
                recalc_reasons.append("expiry_approaching")
                context.expiry_approaching = True
                context.time_decay = True

        # Check cache age
        cache_timestamp = cached_greeks.get("timestamp")
        if cache_timestamp:
            cache_age = (datetime.now() - datetime.fromisoformat(cache_timestamp)).total_seconds()
            max_age = self.cache_ttls["live_greeks"]
            if cache_age > max_age:
                recalc_reasons.append("cache_expired")

        # Check for significant delta/gamma changes
        if cached_greeks.get("greeks"):
            current_delta = market_data.get("delta")
            cached_delta = cached_greeks["greeks"].get("delta")

            if current_delta and cached_delta:
                delta_change = abs(current_delta - cached_delta)
                if delta_change > self.recalc_thresholds["delta_threshold"]:
                    recalc_reasons.append(f"delta_change_{delta_change:.3f}")

        recalc_needed = len(recalc_reasons) > 0

        if recalc_needed:
            logger.debug(f"Greeks recalculation needed for {instrument_id}: {', '.join(recalc_reasons)}")

        return recalc_needed, context

    async def _selective_greeks_invalidation(self, instrument_id: str, context: GreeksInvalidationContext):
        """Selective invalidation of Greeks caches based on context"""
        patterns_to_invalidate = []

        # Always invalidate live Greeks
        patterns_to_invalidate.extend([
            f"greeks:{instrument_id}:live",
            f"greeks:{instrument_id}:current"
        ])

        # Conditional invalidation based on context
        if context.volatility_change and context.volatility_change > 10:
            # High volatility change affects sensitivity calculations
            patterns_to_invalidate.extend([
                f"greeks:{instrument_id}:sensitivity:*",
                f"greeks:{instrument_id}:scenarios:*"
            ])

        if context.time_decay or context.expiry_approaching:
            # Time decay affects theta calculations
            patterns_to_invalidate.extend([
                f"greeks:{instrument_id}:theta:*",
                f"greeks:{instrument_id}:time_series:*"
            ])

        if context.spot_price:
            # Spot price change affects delta/gamma
            patterns_to_invalidate.extend([
                f"greeks:{instrument_id}:delta:*",
                f"greeks:{instrument_id}:gamma:*"
            ])

        # Batch invalidation
        for pattern in patterns_to_invalidate:
            try:
                keys = await self.redis_client.keys(pattern)
                if keys:
                    await self.redis_client.delete(*keys)
                    logger.debug(f"Invalidated {len(keys)} keys for pattern: {pattern}")
            except Exception as e:
                logger.error(f"Failed to invalidate pattern {pattern}: {e}")

    async def _recalculate_greeks(self, request: GreeksRecalculationRequest) -> dict[str, Any]:
        """Recalculate Greeks based on request"""
        start_time = time.time()

        try:
            if request.calculation_type == GreeksCalculationType.BULK_CHAIN:
                # Use vectorized calculation for efficiency
                await self._bulk_greeks_calculation(request.instruments)
            else:
                # Individual calculation
                await self._individual_greeks_calculation(request.instruments[0])

            duration_ms = (time.time() - start_time) * 1000

            # Update average calculation time
            current_avg = self.performance_stats["avg_calc_time_ms"]
            total_calcs = self.performance_stats["recalculations"]
            new_avg = (current_avg * total_calcs + duration_ms) / (total_calcs + 1)
            self.performance_stats["avg_calc_time_ms"] = new_avg

            return {
                "success": True,
                "duration_ms": duration_ms,
                "instruments_processed": len(request.instruments),
                "calculation_type": request.calculation_type.value
            }

        except Exception as e:
            logger.error(f"Greeks recalculation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "duration_ms": (time.time() - start_time) * 1000
            }

    async def _bulk_greeks_calculation(self, instrument_ids: list[str]) -> dict[str, Any]:
        """Bulk Greeks calculation using vectorized engine"""
        try:
            # Use the vectorized Greeks engine for bulk calculations
            if hasattr(self.greeks_engine, '_vectorized_engine') and self.greeks_engine._vectorized_engine:
                # Prepare bulk calculation data
                bulk_data = []
                for instrument_id in instrument_ids:
                    market_data = await self._get_market_data(instrument_id)
                    if market_data:
                        bulk_data.append({
                            "instrument_id": instrument_id,
                            "spot_price": market_data.get("spot_price"),
                            "strike_price": market_data.get("strike_price"),
                            "time_to_expiry": market_data.get("time_to_expiry"),
                            "volatility": market_data.get("volatility"),
                            "risk_free_rate": market_data.get("risk_free_rate", 0.05),
                            "option_type": market_data.get("option_type", "call")
                        })

                # Vectorized calculation
                bulk_results = await self.greeks_engine._vectorized_engine.calculate_bulk_greeks(bulk_data)

                # Cache the results
                for instrument_id, greeks in bulk_results.items():
                    await self._cache_greeks_result(instrument_id, greeks, "bulk")

                return {"vectorized": True, "results_count": len(bulk_results)}
            # Fallback to individual calculations
            results = {}
            for instrument_id in instrument_ids:
                result = await self._individual_greeks_calculation(instrument_id)
                results[instrument_id] = result

            return {"vectorized": False, "results_count": len(results)}

        except Exception as e:
            logger.error(f"Bulk Greeks calculation failed: {e}")
            raise

    async def _individual_greeks_calculation(self, instrument_id: str) -> dict[str, Any]:
        """Individual Greeks calculation"""
        try:
            # Get market data
            market_data = await self._get_market_data(instrument_id)
            if not market_data:
                raise ValueError(f"No market data available for {instrument_id}")

            # Calculate Greeks
            greeks_result = await self.greeks_engine.calculate_greeks(
                spot_price=float(market_data["spot_price"]),
                strike_price=float(market_data["strike_price"]),
                time_to_expiry=float(market_data["time_to_expiry"]),
                volatility=float(market_data["volatility"]),
                risk_free_rate=float(market_data.get("risk_free_rate", 0.05)),
                option_type=market_data.get("option_type", "call").lower()
            )

            # Cache the result
            await self._cache_greeks_result(instrument_id, greeks_result, "individual")

            return greeks_result

        except Exception as e:
            logger.error(f"Individual Greeks calculation failed for {instrument_id}: {e}")
            raise

    async def _get_cached_greeks(self, instrument_id: str) -> dict[str, Any] | None:
        """Get cached Greeks for an instrument"""
        try:
            cache_key = f"greeks:{instrument_id}:latest"
            cached_data = await self.redis_client.get(cache_key)

            if cached_data:
                return json.loads(cached_data)

            return None

        except Exception as e:
            logger.error(f"Failed to get cached Greeks for {instrument_id}: {e}")
            return None

    async def _cache_greeks_result(self, instrument_id: str, greeks_result: dict[str, Any], calc_type: str):
        """Cache Greeks calculation result"""
        try:
            cache_data = {
                "timestamp": datetime.now().isoformat(),
                "instrument_id": instrument_id,
                "greeks": greeks_result,
                "calculation_type": calc_type
            }

            # Cache with appropriate TTL based on calculation type
            ttl = self.cache_ttls.get(f"{calc_type}_greeks", self.cache_ttls["live_greeks"])

            cache_keys = [
                f"greeks:{instrument_id}:latest",
                f"greeks:{instrument_id}:{calc_type}",
                f"greeks:{instrument_id}:timestamp:{int(time.time())}"
            ]

            for cache_key in cache_keys:
                await self.redis_client.setex(cache_key, ttl, json.dumps(cache_data))

            logger.debug(f"Cached Greeks result for {instrument_id} with TTL {ttl}s")

        except Exception as e:
            logger.error(f"Failed to cache Greeks result for {instrument_id}: {e}")

    async def _get_market_data(self, instrument_id: str) -> dict[str, Any] | None:
        """Get market data for an instrument"""
        try:
            market_data_key = f"market_data:{instrument_id}:latest"
            market_data_str = await self.redis_client.get(market_data_key)

            if market_data_str:
                return json.loads(market_data_str)

            return None

        except Exception as e:
            logger.error(f"Failed to get market data for {instrument_id}: {e}")
            return None

    async def _get_chain_instruments(self, underlying: str) -> list[str]:
        """Get all instruments in an option chain"""
        try:
            chain_key = f"chain:{underlying}:instruments"
            instruments_data = await self.redis_client.get(chain_key)

            if instruments_data:
                return json.loads(instruments_data)

            # Fallback: scan for instruments matching pattern
            pattern = f"market_data:{underlying}:*"
            keys = await self.redis_client.keys(pattern)
            instruments = [key.split(':')[1] for key in keys if ':' in key]

            return list(set(instruments))

        except Exception as e:
            logger.error(f"Failed to get chain instruments for {underlying}: {e}")
            return []

    async def _calculate_cache_efficiency(self) -> dict[str, float]:
        """Calculate cache efficiency metrics"""
        total_requests = self.performance_stats["cache_hits"] + self.performance_stats["cache_misses"]

        if total_requests == 0:
            return {"hit_rate": 0.0, "miss_rate": 0.0}

        hit_rate = self.performance_stats["cache_hits"] / total_requests
        miss_rate = self.performance_stats["cache_misses"] / total_requests

        return {
            "hit_rate": hit_rate,
            "miss_rate": miss_rate,
            "total_requests": total_requests
        }

    def get_performance_stats(self) -> dict[str, Any]:
        """Get Greeks cache performance statistics"""
        stats = self.performance_stats.copy()
        stats["cache_efficiency"] = asyncio.create_task(self._calculate_cache_efficiency())
        return stats

# Factory function
def create_greeks_cache_manager(redis_client=None, greeks_engine=None):
    """Create Greeks cache manager instance"""
    if redis_client is None:
        from ..utils.redis import get_redis_client
        redis_client = get_redis_client()

    if greeks_engine is None:
        from ..services.greeks_calculation_engine import GreeksCalculationEngine
        greeks_engine = GreeksCalculationEngine()

    return GreeksCacheManager(redis_client, greeks_engine)
