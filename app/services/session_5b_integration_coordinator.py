#!/usr/bin/env python3
"""
Session 5B Integration Coordinator

Coordinates all enhanced cache invalidation components for registry event triggers:
- Enhanced Cache Invalidation Service
- Greeks Cache Manager
- Technical Indicator Cache Coordinator
- Moneyness Cache Refresh Service
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .enhanced_cache_invalidation_service import (
    InvalidationRequest,
    InvalidationType,
    get_enhanced_cache_service,
)
from .greeks_cache_manager import create_greeks_cache_manager
from .moneyness_cache_refresh_service import create_moneyness_refresh_service
from .session_5b_sla_monitoring import (
    record_coordination_sla,
)
from .technical_indicator_cache_coordinator import create_technical_indicator_cache_coordinator

logger = logging.getLogger(__name__)

class CoordinationPriority(Enum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"

@dataclass
class CoordinationRequest:
    """Request for coordinated cache operations"""
    event_type: str
    instrument_id: str | None = None
    underlying: str | None = None
    user_id: str | None = None
    market_data: dict[str, Any] | None = None
    priority: CoordinationPriority = CoordinationPriority.NORMAL
    metadata: dict[str, Any] | None = None

class Session5BCacheCoordinator:
    """Coordinates all Session 5B cache invalidation and refresh services"""

    def __init__(self, redis_client):
        self.redis_client = redis_client

        # Initialize all cache services
        self.enhanced_cache_service = get_enhanced_cache_service(redis_client)
        self.greeks_cache_manager = create_greeks_cache_manager(redis_client)
        self.indicator_coordinator = create_technical_indicator_cache_coordinator(redis_client)
        self.moneyness_refresh_service = create_moneyness_refresh_service(redis_client)

        # Coordination statistics
        self.coordination_stats = {
            "total_coordinations": 0,
            "successful_coordinations": 0,
            "failed_coordinations": 0,
            "avg_coordination_time_ms": 0.0,
            "service_performance": {
                "enhanced_cache": {"calls": 0, "success": 0, "avg_time_ms": 0.0},
                "greeks_cache": {"calls": 0, "success": 0, "avg_time_ms": 0.0},
                "indicator_cache": {"calls": 0, "success": 0, "avg_time_ms": 0.0},
                "moneyness_cache": {"calls": 0, "success": 0, "avg_time_ms": 0.0}
            }
        }

    async def coordinate_instrument_update(self, instrument_id: str, market_data: dict[str, Any]) -> dict[str, Any]:
        """Coordinate all cache services for instrument update"""

        logger.info(f"Coordinating instrument update caches for: {instrument_id}")

        coordination_start = time.time()
        result = {
            "instrument_id": instrument_id,
            "coordination_type": "instrument_update",
            "services_coordinated": [],
            "coordination_success": False,
            "performance": {},
            "service_results": {}
        }

        try:
            # Create coordination request
            request = CoordinationRequest(
                event_type="instrument.updated",
                instrument_id=instrument_id,
                market_data=market_data,
                priority=CoordinationPriority.HIGH
            )

            # Execute coordinated cache operations
            coordination_tasks = [
                self._coordinate_enhanced_cache_invalidation(request),
                self._coordinate_greeks_cache_management(request),
                self._coordinate_indicator_cache_coordination(request),
                self._coordinate_moneyness_cache_refresh(request)
            ]

            # Execute all coordinations concurrently
            coordination_results = await asyncio.gather(
                *coordination_tasks, return_exceptions=True
            )

            # Process results
            service_names = [
                "enhanced_cache_invalidation",
                "greeks_cache_management",
                "indicator_cache_coordination",
                "moneyness_cache_refresh"
            ]

            successful_services = []
            for i, coordination_result in enumerate(coordination_results):
                service_name = service_names[i]

                if isinstance(coordination_result, Exception):
                    logger.error(f"Service {service_name} coordination failed: {coordination_result}")
                    result["service_results"][service_name] = {"success": False, "error": str(coordination_result)}
                else:
                    result["service_results"][service_name] = coordination_result
                    if coordination_result.get("success", False):
                        successful_services.append(service_name)

            # Update coordination statistics
            result["services_coordinated"] = successful_services
            result["coordination_success"] = len(successful_services) > 0

            coordination_time = (time.time() - coordination_start) * 1000
            result["performance"] = {
                "total_coordination_time_ms": coordination_time,
                "services_attempted": len(service_names),
                "services_successful": len(successful_services),
                "success_rate": len(successful_services) / len(service_names) * 100
            }

            # Record coordination SLA metrics
            record_coordination_sla(
                coordination_type="instrument_update",
                services_count=len(service_names),
                latency_seconds=coordination_time / 1000
            )

            # Update global stats
            self.coordination_stats["total_coordinations"] += 1
            if result["coordination_success"]:
                self.coordination_stats["successful_coordinations"] += 1
            else:
                self.coordination_stats["failed_coordinations"] += 1

            # Update average coordination time
            self._update_average_time("coordination", coordination_time)

            logger.info(f"Instrument update coordination completed for {instrument_id}: {len(successful_services)}/{len(service_names)} services successful")

            return result

        except Exception as e:
            logger.error(f"Instrument update coordination failed for {instrument_id}: {e}")
            result["error"] = str(e)
            result["performance"]["total_coordination_time_ms"] = (time.time() - coordination_start) * 1000
            self.coordination_stats["failed_coordinations"] += 1
            return result

    async def coordinate_chain_rebalance(self, underlying: str, rebalance_data: dict[str, Any]) -> dict[str, Any]:
        """Coordinate all cache services for chain rebalance"""

        logger.info(f"Coordinating chain rebalance caches for: {underlying}")

        coordination_start = time.time()
        result = {
            "underlying": underlying,
            "coordination_type": "chain_rebalance",
            "services_coordinated": [],
            "coordination_success": False,
            "performance": {},
            "service_results": {}
        }

        try:
            # Create coordination request
            request = CoordinationRequest(
                event_type="chain.rebalance",
                underlying=underlying,
                market_data=rebalance_data,
                priority=CoordinationPriority.HIGH,
                metadata={"rebalance_data": rebalance_data}
            )

            # Chain rebalance coordination (some services handle this differently)
            coordination_tasks = [
                self._coordinate_enhanced_cache_chain_invalidation(request),
                self._coordinate_greeks_chain_rebalance(request),
                self._coordinate_indicators_chain_rebalance(request),
                self._coordinate_moneyness_chain_refresh(request)
            ]

            coordination_results = await asyncio.gather(
                *coordination_tasks, return_exceptions=True
            )

            # Process chain rebalance results
            service_names = [
                "enhanced_cache_chain_invalidation",
                "greeks_chain_rebalance",
                "indicators_chain_rebalance",
                "moneyness_chain_refresh"
            ]

            successful_services = []
            total_instruments_affected = 0

            for i, coordination_result in enumerate(coordination_results):
                service_name = service_names[i]

                if isinstance(coordination_result, Exception):
                    logger.error(f"Chain service {service_name} coordination failed: {coordination_result}")
                    result["service_results"][service_name] = {"success": False, "error": str(coordination_result)}
                else:
                    result["service_results"][service_name] = coordination_result
                    if coordination_result.get("success", False):
                        successful_services.append(service_name)
                        # Accumulate instruments affected across services
                        total_instruments_affected += coordination_result.get("instruments_processed", 0)

            result["services_coordinated"] = successful_services
            result["coordination_success"] = len(successful_services) > 0
            result["total_instruments_affected"] = total_instruments_affected

            coordination_time = (time.time() - coordination_start) * 1000
            result["performance"] = {
                "total_coordination_time_ms": coordination_time,
                "services_attempted": len(service_names),
                "services_successful": len(successful_services),
                "success_rate": len(successful_services) / len(service_names) * 100,
                "instruments_per_second": total_instruments_affected / max(1, coordination_time / 1000)
            }

            # Update coordination statistics
            self.coordination_stats["total_coordinations"] += 1
            if result["coordination_success"]:
                self.coordination_stats["successful_coordinations"] += 1
            else:
                self.coordination_stats["failed_coordinations"] += 1

            self._update_average_time("coordination", coordination_time)

            logger.info(f"Chain rebalance coordination completed for {underlying}: {total_instruments_affected} instruments affected")

            return result

        except Exception as e:
            logger.error(f"Chain rebalance coordination failed for {underlying}: {e}")
            result["error"] = str(e)
            result["performance"]["total_coordination_time_ms"] = (time.time() - coordination_start) * 1000
            self.coordination_stats["failed_coordinations"] += 1
            return result

    async def coordinate_subscription_change(self, user_id: str, subscription_data: dict[str, Any]) -> dict[str, Any]:
        """Coordinate cache invalidation for user subscription changes"""

        logger.info(f"Coordinating subscription change caches for user: {user_id}")

        coordination_start = time.time()
        result = {
            "user_id": user_id,
            "coordination_type": "subscription_change",
            "services_coordinated": [],
            "coordination_success": False,
            "performance": {}
        }

        try:
            # Create coordination request
            CoordinationRequest(
                event_type="subscription.profile.changed",
                user_id=user_id,
                market_data=subscription_data,
                priority=CoordinationPriority.NORMAL
            )

            # Only enhanced cache service handles user subscription changes directly
            invalidation_request = InvalidationRequest(
                invalidation_type=InvalidationType.SUBSCRIPTION_CHANGE,
                user_id=user_id,
                reason="subscription_profile_changed"
            )

            invalidation_result = await self.enhanced_cache_service.invalidate_cache(invalidation_request)

            if invalidation_result.success:
                result["services_coordinated"] = ["enhanced_cache_invalidation"]
                result["coordination_success"] = True
                result["invalidated_keys"] = invalidation_result.invalidated_keys

            coordination_time = (time.time() - coordination_start) * 1000
            result["performance"] = {
                "total_coordination_time_ms": coordination_time,
                "invalidation_time_ms": invalidation_result.duration_ms
            }

            self.coordination_stats["total_coordinations"] += 1
            if result["coordination_success"]:
                self.coordination_stats["successful_coordinations"] += 1
            else:
                self.coordination_stats["failed_coordinations"] += 1

            return result

        except Exception as e:
            logger.error(f"Subscription change coordination failed for user {user_id}: {e}")
            result["error"] = str(e)
            result["performance"]["total_coordination_time_ms"] = (time.time() - coordination_start) * 1000
            self.coordination_stats["failed_coordinations"] += 1
            return result

    async def _coordinate_enhanced_cache_invalidation(self, request: CoordinationRequest) -> dict[str, Any]:
        """Coordinate enhanced cache invalidation service"""

        start_time = time.time()
        service_stats = self.coordination_stats["service_performance"]["enhanced_cache"]
        service_stats["calls"] += 1

        try:
            invalidation_request = InvalidationRequest(
                invalidation_type=InvalidationType.INSTRUMENT_UPDATE,
                instrument_id=request.instrument_id,
                reason=request.event_type,
                selective=True
            )

            invalidation_result = await self.enhanced_cache_service.invalidate_cache(invalidation_request)

            duration = (time.time() - start_time) * 1000

            if invalidation_result.success:
                service_stats["success"] += 1
                self._update_service_average_time("enhanced_cache", duration)

                return {
                    "success": True,
                    "service": "enhanced_cache_invalidation",
                    "invalidated_keys": invalidation_result.invalidated_keys,
                    "cache_types_affected": invalidation_result.cache_types_affected,
                    "duration_ms": duration
                }
            return {
                "success": False,
                "service": "enhanced_cache_invalidation",
                "error": invalidation_result.error,
                "duration_ms": duration
            }

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            logger.error(f"Enhanced cache invalidation coordination failed: {e}")
            return {
                "success": False,
                "service": "enhanced_cache_invalidation",
                "error": str(e),
                "duration_ms": duration
            }

    async def _coordinate_greeks_cache_management(self, request: CoordinationRequest) -> dict[str, Any]:
        """Coordinate Greeks cache management"""

        start_time = time.time()
        service_stats = self.coordination_stats["service_performance"]["greeks_cache"]
        service_stats["calls"] += 1

        try:
            greeks_result = await self.greeks_cache_manager.handle_instrument_update(
                request.instrument_id, request.market_data
            )

            duration = (time.time() - start_time) * 1000

            if greeks_result.get("cached_greeks_updated", False):
                service_stats["success"] += 1
                self._update_service_average_time("greeks_cache", duration)

            return {
                "success": greeks_result.get("recalculation_triggered", False),
                "service": "greeks_cache_management",
                "cache_invalidated": greeks_result.get("cache_invalidated", False),
                "greeks_updated": greeks_result.get("cached_greeks_updated", False),
                "performance": greeks_result.get("performance", {}),
                "duration_ms": duration
            }

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            logger.error(f"Greeks cache management coordination failed: {e}")
            return {
                "success": False,
                "service": "greeks_cache_management",
                "error": str(e),
                "duration_ms": duration
            }

    async def _coordinate_indicator_cache_coordination(self, request: CoordinationRequest) -> dict[str, Any]:
        """Coordinate technical indicator cache coordination"""

        start_time = time.time()
        service_stats = self.coordination_stats["service_performance"]["indicator_cache"]
        service_stats["calls"] += 1

        try:
            indicator_result = await self.indicator_coordinator.handle_instrument_market_data_update(
                request.instrument_id, request.market_data
            )

            duration = (time.time() - start_time) * 1000

            if indicator_result.get("coordination_success", False):
                service_stats["success"] += 1
                self._update_service_average_time("indicator_cache", duration)

            return {
                "success": indicator_result.get("coordination_success", False),
                "service": "indicator_cache_coordination",
                "indicators_invalidated": indicator_result.get("indicators_invalidated", []),
                "indicators_recalculated": indicator_result.get("indicators_recalculated", []),
                "performance": indicator_result.get("performance", {}),
                "duration_ms": duration
            }

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            logger.error(f"Indicator cache coordination failed: {e}")
            return {
                "success": False,
                "service": "indicator_cache_coordination",
                "error": str(e),
                "duration_ms": duration
            }

    async def _coordinate_moneyness_cache_refresh(self, request: CoordinationRequest) -> dict[str, Any]:
        """Coordinate moneyness cache refresh"""

        start_time = time.time()
        service_stats = self.coordination_stats["service_performance"]["moneyness_cache"]
        service_stats["calls"] += 1

        try:
            # Extract spot price from market data
            current_spot = request.market_data.get("spot_price") if request.market_data else None
            previous_spot = request.market_data.get("previous_spot_price") if request.market_data else None

            if current_spot:
                # Get underlying from instrument_id (simple extraction)
                underlying = request.instrument_id.split(':')[1] if ':' in request.instrument_id else request.instrument_id

                moneyness_result = await self.moneyness_refresh_service.handle_spot_price_update(
                    underlying, float(current_spot), float(previous_spot) if previous_spot else None
                )

                duration = (time.time() - start_time) * 1000

                if moneyness_result.get("refresh_success", False):
                    service_stats["success"] += 1
                    self._update_service_average_time("moneyness_cache", duration)

                return {
                    "success": moneyness_result.get("refresh_success", False),
                    "service": "moneyness_cache_refresh",
                    "refresh_type": moneyness_result.get("refresh_type", "none"),
                    "strikes_refreshed": moneyness_result.get("strikes_refreshed", 0),
                    "performance": moneyness_result.get("performance", {}),
                    "duration_ms": duration
                }
            return {
                "success": False,
                "service": "moneyness_cache_refresh",
                "error": "No spot price in market data",
                "duration_ms": (time.time() - start_time) * 1000
            }

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            logger.error(f"Moneyness cache refresh coordination failed: {e}")
            return {
                "success": False,
                "service": "moneyness_cache_refresh",
                "error": str(e),
                "duration_ms": duration
            }

    async def _coordinate_enhanced_cache_chain_invalidation(self, request: CoordinationRequest) -> dict[str, Any]:
        """Coordinate enhanced cache invalidation for chain rebalance"""

        try:
            invalidation_request = InvalidationRequest(
                invalidation_type=InvalidationType.CHAIN_REBALANCE,
                underlying=request.underlying,
                reason="chain_rebalance"
            )

            result = await self.enhanced_cache_service.invalidate_cache(invalidation_request)

            return {
                "success": result.success,
                "service": "enhanced_cache_chain_invalidation",
                "invalidated_keys": result.invalidated_keys,
                "cache_types_affected": result.cache_types_affected,
                "instruments_processed": 1  # Chain-level operation
            }

        except Exception as e:
            return {"success": False, "service": "enhanced_cache_chain_invalidation", "error": str(e)}

    async def _coordinate_greeks_chain_rebalance(self, request: CoordinationRequest) -> dict[str, Any]:
        """Coordinate Greeks cache for chain rebalance"""

        try:
            result = await self.greeks_cache_manager.handle_chain_rebalance(
                request.underlying, request.market_data
            )

            return {
                "success": result.get("bulk_recalculation", False),
                "service": "greeks_chain_rebalance",
                "affected_instruments": result.get("affected_instruments", []),
                "instruments_processed": len(result.get("affected_instruments", [])),
                "performance": result.get("performance", {})
            }

        except Exception as e:
            return {"success": False, "service": "greeks_chain_rebalance", "error": str(e)}

    async def _coordinate_indicators_chain_rebalance(self, request: CoordinationRequest) -> dict[str, Any]:
        """Coordinate indicators for chain rebalance"""

        try:
            result = await self.indicator_coordinator.handle_chain_rebalance_indicators(
                request.underlying, request.market_data
            )

            return {
                "success": result.get("success", False),
                "service": "indicators_chain_rebalance",
                "instruments_processed": result.get("instruments_processed", 0),
                "indicators_coordinated": result.get("indicators_coordinated", 0)
            }

        except Exception as e:
            return {"success": False, "service": "indicators_chain_rebalance", "error": str(e)}

    async def _coordinate_moneyness_chain_refresh(self, request: CoordinationRequest) -> dict[str, Any]:
        """Coordinate moneyness refresh for chain rebalance"""

        try:
            result = await self.moneyness_refresh_service.handle_chain_rebalance_refresh(
                request.underlying, request.market_data
            )

            return {
                "success": result.get("refresh_success", False),
                "service": "moneyness_chain_refresh",
                "instruments_processed": 1,  # Chain-level operation
                "strikes_refreshed": result.get("strikes_refreshed", 0),
                "expiries_refreshed": result.get("expiries_refreshed", 0)
            }

        except Exception as e:
            return {"success": False, "service": "moneyness_chain_refresh", "error": str(e)}

    def _update_average_time(self, metric_type: str, duration_ms: float):
        """Update average time metrics"""

        current_avg = self.coordination_stats["avg_coordination_time_ms"]
        total_coordinations = max(1, self.coordination_stats["total_coordinations"])

        self.coordination_stats["avg_coordination_time_ms"] = (
            (current_avg * (total_coordinations - 1) + duration_ms) / total_coordinations
        )

    def _update_service_average_time(self, service: str, duration_ms: float):
        """Update service-specific average time"""

        service_stats = self.coordination_stats["service_performance"][service]
        current_avg = service_stats["avg_time_ms"]
        total_calls = max(1, service_stats["calls"])

        service_stats["avg_time_ms"] = (
            (current_avg * (total_calls - 1) + duration_ms) / total_calls
        )

    def get_coordination_statistics(self) -> dict[str, Any]:
        """Get comprehensive coordination statistics"""

        stats = self.coordination_stats.copy()

        # Add derived metrics
        if stats["total_coordinations"] > 0:
            stats["success_rate"] = stats["successful_coordinations"] / stats["total_coordinations"] * 100
            stats["failure_rate"] = stats["failed_coordinations"] / stats["total_coordinations"] * 100

        # Add individual service performance
        for _service, service_stats in stats["service_performance"].items():
            if service_stats["calls"] > 0:
                service_stats["success_rate"] = service_stats["success"] / service_stats["calls"] * 100

        return stats

# Global coordinator instance
_session_5b_coordinator: Session5BCacheCoordinator | None = None

def get_session_5b_coordinator(redis_client=None) -> Session5BCacheCoordinator:
    """Get or create Session 5B cache coordinator"""
    global _session_5b_coordinator

    if _session_5b_coordinator is None:
        if redis_client is None:
            from ..utils.redis import get_redis_client
            redis_client = get_redis_client()

        _session_5b_coordinator = Session5BCacheCoordinator(redis_client)
        logger.info("Session 5B Cache Coordinator initialized")

    return _session_5b_coordinator
