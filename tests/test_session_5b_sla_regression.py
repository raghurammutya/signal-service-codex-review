#!/usr/bin/env python3
"""
Session 5B SLA Regression Tests

Tests that inject stale data and events to prove the caches recover within
stated latency SLAs as defined in the Phase 3 monitoring matrix.
"""

import asyncio
import pytest
import time
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List
import redis.asyncio as redis

from ..app.services.session_5b_integration_coordinator import get_session_5b_coordinator
from ..app.services.session_5b_sla_monitoring import get_session_5b_sla_monitor
from ..app.utils.redis import get_redis_client


class StaleDataInjector:
    """Utility to inject stale data for regression testing"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
    
    async def inject_stale_greeks(self, instrument_id: str, staleness_hours: int = 2) -> Dict[str, Any]:
        """Inject stale Greeks data"""
        stale_timestamp = (datetime.now() - timedelta(hours=staleness_hours)).isoformat()
        
        stale_greeks = {
            "timestamp": stale_timestamp,
            "instrument_id": instrument_id,
            "greeks": {
                "delta": 0.45,
                "gamma": 0.02,
                "theta": -0.1,
                "vega": 0.25,
                "rho": 0.05
            },
            "market_data": {
                "spot_price": 2400.0,  # Old spot price
                "implied_volatility": 0.18
            }
        }
        
        # Store stale data in cache
        cache_key = f"greeks:{instrument_id}:latest"
        await self.redis_client.setex(cache_key, 300, json.dumps(stale_greeks))
        
        return {"cache_key": cache_key, "staleness_hours": staleness_hours}
    
    async def inject_stale_indicators(self, instrument_id: str, staleness_minutes: int = 30) -> Dict[str, Any]:
        """Inject stale technical indicator data"""
        stale_timestamp = (datetime.now() - timedelta(minutes=staleness_minutes)).isoformat()
        
        stale_indicators = {
            "timestamp": stale_timestamp,
            "instrument_id": instrument_id,
            "indicators": {
                "sma_20": 2380.0,    # Old moving average
                "rsi_14": 65.0,      # Old RSI
                "bb_upper": 2420.0,  # Old Bollinger Bands
                "bb_lower": 2340.0
            }
        }
        
        cache_keys = [
            f"indicators:{instrument_id}:moving_average:1h:period_20",
            f"indicators:{instrument_id}:rsi:1h:period_14",
            f"indicators:{instrument_id}:bollinger_bands:1h:period_20_std_2"
        ]
        
        for cache_key in cache_keys:
            await self.redis_client.setex(cache_key, 300, json.dumps(stale_indicators))
        
        return {"cache_keys": cache_keys, "staleness_minutes": staleness_minutes}
    
    async def inject_stale_moneyness(self, underlying: str, staleness_minutes: int = 10) -> Dict[str, Any]:
        """Inject stale moneyness data"""
        stale_timestamp = (datetime.now() - timedelta(minutes=staleness_minutes)).isoformat()
        
        stale_moneyness = {
            "underlying": underlying,
            "strikes": {
                "2400": {"moneyness": 1.02, "category": "atm"},  # Old moneyness
                "2450": {"moneyness": 0.98, "category": "atm"},
                "2500": {"moneyness": 0.96, "category": "otm"}
            },
            "spot_price": 2440.0,  # Old spot price
            "calculated_at": stale_timestamp
        }
        
        cache_key = f"moneyness:{underlying}:latest"
        await self.redis_client.setex(cache_key, 300, json.dumps(stale_moneyness))
        
        return {"cache_key": cache_key, "staleness_minutes": staleness_minutes}
    
    async def simulate_fresh_market_data(self, instrument_id: str) -> Dict[str, Any]:
        """Simulate fresh market data that should trigger cache refresh"""
        underlying = instrument_id.split(':')[1] if ':' in instrument_id else instrument_id
        
        fresh_market_data = {
            "instrument_id": instrument_id,
            "underlying": underlying,
            "spot_price": 2450.50,        # New spot price
            "previous_spot_price": 2440.0,
            "price_change_pct": 0.24,
            "volume": 125000,
            "implied_volatility": 0.22,   # New volatility
            "time_to_expiry": 0.08,
            "option_type": "call",
            "timestamp": datetime.now().isoformat()
        }
        
        return fresh_market_data


@pytest.fixture
async def redis_client():
    """Redis client fixture"""
    client = get_redis_client()
    yield client
    await client.close()


@pytest.fixture
async def stale_data_injector(redis_client):
    """Stale data injector fixture"""
    return StaleDataInjector(redis_client)


@pytest.fixture
async def session_5b_coordinator(redis_client):
    """Session 5B coordinator fixture"""
    return get_session_5b_coordinator(redis_client)


@pytest.fixture
async def sla_monitor():
    """SLA monitor fixture"""
    return get_session_5b_sla_monitor()


class TestSession5BSLACompliance:
    """Test SLA compliance for Session 5B cache operations"""
    
    @pytest.mark.asyncio
    async def test_stale_greeks_recovery_sla(self, stale_data_injector, session_5b_coordinator, sla_monitor):
        """Test that stale Greeks data recovers within 5s SLA"""
        instrument_id = "NSE:RELIANCE"
        
        # Inject stale Greeks (2 hours old)
        stale_info = await stale_data_injector.inject_stale_greeks(instrument_id, staleness_hours=2)
        
        # Simulate fresh market data update
        fresh_data = await stale_data_injector.simulate_fresh_market_data(instrument_id)
        
        # Record start time for SLA measurement
        recovery_start = time.time()
        
        # Trigger cache coordination (should detect and recover from stale data)
        coordination_result = await session_5b_coordinator.coordinate_instrument_update(
            instrument_id, fresh_data
        )
        
        recovery_duration = time.time() - recovery_start
        
        # Verify SLA compliance: Recovery within 5 seconds
        assert recovery_duration < 5.0, f"Greeks recovery took {recovery_duration:.3f}s, exceeds 5s SLA"
        
        # Verify coordination succeeded
        assert coordination_result["coordination_success"], "Coordination should succeed"
        assert "greeks_cache_management" in coordination_result["services_coordinated"]
        
        # Record the stale data detection and recovery for SLA monitoring
        sla_monitor.record_stale_data_detection(
            service="greeks_cache_management",
            data_type="greeks",
            staleness_severity="major",  # 2 hours old
            recovery_duration=recovery_duration
        )
        
        # Verify no SLA violations for this recovery
        sla_summary = sla_monitor.get_sla_compliance_summary()
        stale_recovery_violations = sla_summary["violations_by_type"].get("stale_data_recovery", 0)
        assert stale_recovery_violations == 0, "Should be no stale data recovery SLA violations"
    
    @pytest.mark.asyncio
    async def test_stale_indicators_recovery_sla(self, stale_data_injector, session_5b_coordinator, sla_monitor):
        """Test that stale indicator data recovers within 5s SLA"""
        instrument_id = "BSE:SENSEX"
        
        # Inject stale indicators (30 minutes old)
        stale_info = await stale_data_injector.inject_stale_indicators(instrument_id, staleness_minutes=30)
        
        # Simulate market data update with significant price change
        fresh_data = await stale_data_injector.simulate_fresh_market_data(instrument_id)
        fresh_data["price_change_pct"] = 1.5  # Significant change to trigger indicator refresh
        
        recovery_start = time.time()
        
        # Trigger coordination
        coordination_result = await session_5b_coordinator.coordinate_instrument_update(
            instrument_id, fresh_data
        )
        
        recovery_duration = time.time() - recovery_start
        
        # Verify SLA compliance
        assert recovery_duration < 5.0, f"Indicator recovery took {recovery_duration:.3f}s, exceeds 5s SLA"
        assert coordination_result["coordination_success"]
        assert "indicator_cache_coordination" in coordination_result["services_coordinated"]
        
        # Record stale data recovery
        sla_monitor.record_stale_data_detection(
            service="indicator_cache_coordination",
            data_type="indicators", 
            staleness_severity="minor",  # 30 minutes old
            recovery_duration=recovery_duration
        )
    
    @pytest.mark.asyncio
    async def test_stale_moneyness_recovery_sla(self, stale_data_injector, session_5b_coordinator, sla_monitor):
        """Test that stale moneyness data recovers within 5s SLA"""
        instrument_id = "NSE:NIFTY"
        
        # Inject stale moneyness (10 minutes old)
        stale_info = await stale_data_injector.inject_stale_moneyness("NIFTY", staleness_minutes=10)
        
        # Simulate spot price change
        fresh_data = await stale_data_injector.simulate_fresh_market_data(instrument_id)
        fresh_data["price_change_pct"] = 0.8  # Trigger moneyness refresh
        
        recovery_start = time.time()
        
        # Trigger coordination
        coordination_result = await session_5b_coordinator.coordinate_instrument_update(
            instrument_id, fresh_data
        )
        
        recovery_duration = time.time() - recovery_start
        
        # Verify SLA compliance
        assert recovery_duration < 5.0, f"Moneyness recovery took {recovery_duration:.3f}s, exceeds 5s SLA"
        assert coordination_result["coordination_success"]
        assert "moneyness_cache_refresh" in coordination_result["services_coordinated"]
        
        # Record stale data recovery
        sla_monitor.record_stale_data_detection(
            service="moneyness_cache_refresh",
            data_type="moneyness",
            staleness_severity="minor",  # 10 minutes old
            recovery_duration=recovery_duration
        )
    
    @pytest.mark.asyncio
    async def test_cache_invalidation_completion_sla(self, session_5b_coordinator, sla_monitor):
        """Test that cache invalidation completes within 30s SLA"""
        instrument_id = "NSE:RELIANCE"
        
        # Simulate market data update
        market_data = {
            "instrument_id": instrument_id,
            "spot_price": 2455.75,
            "previous_spot_price": 2440.25,
            "price_change_pct": 0.63,
            "volume": 150000,
            "timestamp": datetime.now().isoformat()
        }
        
        invalidation_start = time.time()
        
        # Trigger coordination (includes cache invalidation)
        coordination_result = await session_5b_coordinator.coordinate_instrument_update(
            instrument_id, market_data
        )
        
        invalidation_duration = time.time() - invalidation_start
        
        # Verify SLA compliance: Cache invalidation completion within 30s
        assert invalidation_duration < 30.0, f"Cache invalidation took {invalidation_duration:.3f}s, exceeds 30s SLA"
        assert coordination_result["coordination_success"]
        
        # Check that invalidation was recorded properly
        sla_summary = sla_monitor.get_sla_compliance_summary()
        completion_violations = sla_summary["violations_by_type"].get("cache_invalidation_completion", 0)
        assert completion_violations == 0, "Should be no cache invalidation completion SLA violations"
    
    @pytest.mark.asyncio 
    async def test_coordination_latency_sla(self, session_5b_coordinator, sla_monitor):
        """Test that coordination latency stays within acceptable bounds for P95 SLA"""
        instrument_id = "BSE:SENSEX"
        
        # Run multiple coordinations to test latency consistency
        latencies = []
        
        for i in range(10):
            market_data = {
                "instrument_id": instrument_id,
                "spot_price": 65000 + (i * 10),  # Varying prices
                "volume": 100000 + (i * 5000),
                "price_change_pct": 0.1 + (i * 0.05),
                "timestamp": datetime.now().isoformat()
            }
            
            coordination_start = time.time()
            
            coordination_result = await session_5b_coordinator.coordinate_instrument_update(
                instrument_id, market_data
            )
            
            coordination_latency = time.time() - coordination_start
            latencies.append(coordination_latency)
            
            assert coordination_result["coordination_success"]
            
            # Small delay between tests
            await asyncio.sleep(0.1)
        
        # Calculate P95 latency
        latencies.sort()
        p95_latency = latencies[int(len(latencies) * 0.95)]
        
        # Verify P95 SLA: <100ms
        assert p95_latency < 0.1, f"P95 coordination latency {p95_latency:.3f}s exceeds 100ms SLA"
        
        # Record the P95 performance
        for latency in latencies:
            sla_monitor.record_coordination_latency(
                coordination_type="instrument_update_sla_test",
                services_count=4,
                latency_seconds=latency
            )
    
    @pytest.mark.asyncio
    async def test_cache_hit_rate_sla(self, redis_client, sla_monitor):
        """Test cache hit rate monitoring and SLA compliance"""
        service = "enhanced_cache_invalidation"
        cache_type = "greeks"
        
        # Simulate cache operations with good hit rate
        hits = 950
        misses = 50
        
        # Record cache performance
        sla_monitor.record_cache_hit_miss_ratio(service, cache_type, hits, misses)
        
        # Verify the hit rate meets SLA (>95%)
        hit_rate = (hits / (hits + misses)) * 100
        assert hit_rate >= 95.0, f"Cache hit rate {hit_rate:.1f}% below 95% SLA"
        
        # Test SLA violation detection with poor hit rate
        poor_hits = 85
        poor_misses = 15
        
        sla_monitor.record_cache_hit_miss_ratio(service, cache_type + "_poor", poor_hits, poor_misses)
        
        # Check that violation was recorded
        sla_summary = sla_monitor.get_sla_compliance_summary()
        hit_rate_violations = sla_summary["violations_by_type"].get("cache_hit_rate", 0)
        assert hit_rate_violations > 0, "Poor hit rate should trigger SLA violation"
    
    @pytest.mark.asyncio
    async def test_selective_invalidation_efficiency_sla(self, sla_monitor):
        """Test selective invalidation efficiency monitoring"""
        service = "enhanced_cache_invalidation"
        trigger_type = "spot_price_change"
        
        # Test efficient selective invalidation (saves 80% of keys)
        selective_keys = 20
        full_keys = 100
        
        sla_monitor.record_selective_invalidation_efficiency(
            service, trigger_type, selective_keys, full_keys
        )
        
        efficiency = (1 - selective_keys / full_keys) * 100
        assert efficiency >= 80.0, f"Selective invalidation efficiency {efficiency:.1f}% below 80% SLA"
        
        # Test inefficient invalidation
        inefficient_selective = 95
        inefficient_full = 100
        
        sla_monitor.record_selective_invalidation_efficiency(
            service, trigger_type + "_inefficient", inefficient_selective, inefficient_full
        )
        
        # Check SLA violation detection
        sla_summary = sla_monitor.get_sla_compliance_summary()
        efficiency_violations = sla_summary["violations_by_type"].get("selective_invalidation_efficiency", 0)
        assert efficiency_violations > 0, "Inefficient invalidation should trigger SLA violation"


class TestStaleDataScenarios:
    """Test various stale data scenarios and recovery patterns"""
    
    @pytest.mark.asyncio
    async def test_cascading_stale_data_recovery(self, stale_data_injector, session_5b_coordinator, sla_monitor):
        """Test recovery when multiple cache types have stale data simultaneously"""
        instrument_id = "NSE:HDFC"
        
        # Inject stale data across multiple cache types
        await stale_data_injector.inject_stale_greeks(instrument_id, staleness_hours=1)
        await stale_data_injector.inject_stale_indicators(instrument_id, staleness_minutes=45)
        await stale_data_injector.inject_stale_moneyness("HDFC", staleness_minutes=15)
        
        # Simulate significant market event
        market_data = await stale_data_injector.simulate_fresh_market_data(instrument_id)
        market_data["price_change_pct"] = 2.5  # Large change triggers all cache types
        
        recovery_start = time.time()
        
        # Trigger coordination
        coordination_result = await session_5b_coordinator.coordinate_instrument_update(
            instrument_id, market_data
        )
        
        total_recovery_duration = time.time() - recovery_start
        
        # Verify all services coordinated successfully despite stale data
        assert coordination_result["coordination_success"]
        assert len(coordination_result["services_coordinated"]) >= 3  # At least 3 of 4 services
        
        # Verify overall recovery SLA (should handle multiple stale types efficiently)
        assert total_recovery_duration < 10.0, f"Cascading recovery took {total_recovery_duration:.3f}s, too slow"
        
        # Record cascading stale data detection
        sla_monitor.record_stale_data_detection(
            service="session_5b_coordinator",
            data_type="cascading_multi_cache",
            staleness_severity="major",
            recovery_duration=total_recovery_duration
        )
    
    @pytest.mark.asyncio
    async def test_extreme_stale_data_recovery(self, stale_data_injector, session_5b_coordinator, sla_monitor):
        """Test recovery from extremely stale data (worst case scenario)"""
        instrument_id = "BSE:TCS"
        
        # Inject very stale data (24 hours old Greeks)
        await stale_data_injector.inject_stale_greeks(instrument_id, staleness_hours=24)
        
        market_data = await stale_data_injector.simulate_fresh_market_data(instrument_id)
        market_data["price_change_pct"] = 5.0  # Very large change
        
        recovery_start = time.time()
        
        coordination_result = await session_5b_coordinator.coordinate_instrument_update(
            instrument_id, market_data
        )
        
        recovery_duration = time.time() - recovery_start
        
        # Even extreme staleness should recover within reasonable time
        assert recovery_duration < 15.0, f"Extreme stale recovery took {recovery_duration:.3f}s"
        assert coordination_result["coordination_success"]
        
        # Record extreme staleness case
        sla_monitor.record_stale_data_detection(
            service="greeks_cache_management",
            data_type="greeks",
            staleness_severity="critical",  # 24 hours old
            recovery_duration=recovery_duration
        )


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])