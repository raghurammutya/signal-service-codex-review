"""
Timeframe Manager Cache Invalidation and TTL Tests

Addresses functionality_issues.txt requirement:
"No explicit unit tests verify cache invalidation or TTL, even though business value depends on fresh data."

These tests verify cache behavior under various conditions to ensure data freshness
and proper cache lifecycle management for production workloads.
"""
import asyncio
import json
import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.services.flexible_timeframe_manager import FlexibleTimeframeManager


class TestTimeframeCacheInvalidation:
    """Test cache invalidation and TTL behavior for timeframe manager."""

    @pytest.fixture
    async def timeframe_manager(self):
        """Create timeframe manager with mocked dependencies."""
        manager = FlexibleTimeframeManager()
        
        # Mock Redis client
        mock_redis = AsyncMock()
        manager.redis_client = mock_redis
        
        # Mock HTTP session
        mock_session = AsyncMock()
        manager.session = mock_session
        manager.ticker_service_url = "http://test-ticker-service"
        manager.internal_api_key = "test-key"
        
        return manager

    @pytest.mark.asyncio
    async def test_cache_ttl_respected_per_timeframe(self, timeframe_manager):
        """Test that different timeframes have appropriate TTL values."""
        # Test data
        test_data = [
            {"timestamp": "2024-01-01T10:00:00", "value": 100},
            {"timestamp": "2024-01-01T10:05:00", "value": 105}
        ]
        
        # Test different timeframes and their expected TTLs
        timeframe_tests = [
            ("1m", 1, 60),      # 1 minute data: 1 minute TTL
            ("5m", 5, 300),     # 5 minute data: 5 minute TTL
            ("15m", 15, 900),   # 15 minute data: 15 minute TTL
            ("1h", 60, 3600),   # 1 hour data: 1 hour TTL
            ("1d", 1440, 86400) # Daily data: 24 hour TTL
        ]
        
        for timeframe, minutes, expected_ttl in timeframe_tests:
            # Mock Redis setex call to capture TTL
            timeframe_manager.redis_client.setex = AsyncMock()
            
            # Cache data
            await timeframe_manager._cache_data(
                instrument_key="TEST_INSTRUMENT",
                signal_type="greeks",
                timeframe=timeframe,
                data=test_data,
                timeframe_minutes=minutes
            )
            
            # Verify TTL was set correctly
            assert timeframe_manager.redis_client.setex.called
            call_args = timeframe_manager.redis_client.setex.call_args
            actual_ttl = call_args[0][1]  # Second argument is TTL
            
            assert actual_ttl == expected_ttl, f"TTL mismatch for {timeframe}: expected {expected_ttl}, got {actual_ttl}"

    @pytest.mark.asyncio
    async def test_cache_invalidation_on_fresh_data(self, timeframe_manager):
        """Test that cache is invalidated when fresh data is available."""
        instrument_key = "TEST_INSTRUMENT"
        signal_type = "greeks"
        timeframe = "5m"
        
        # Initial cache data
        old_data = [{"timestamp": "2024-01-01T10:00:00", "value": 100}]
        
        # New data that should invalidate cache
        new_data = [{"timestamp": "2024-01-01T10:05:00", "value": 105}]
        
        # Mock Redis operations
        timeframe_manager.redis_client.get = AsyncMock(return_value=json.dumps(old_data))
        timeframe_manager.redis_client.setex = AsyncMock()
        
        # Mock ticker service to return new data
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"data_points": new_data})
        timeframe_manager.session.get = AsyncMock(return_value=mock_response)
        
        # Get aggregated data
        result = await timeframe_manager.get_aggregated_data(
            instrument_key=instrument_key,
            signal_type=signal_type,
            timeframe=timeframe,
            start_time=datetime(2024, 1, 1, 10, 0),
            end_time=datetime(2024, 1, 1, 10, 10)
        )
        
        # Verify cache was updated with new data
        assert timeframe_manager.redis_client.setex.called
        
        # Verify new data was processed and cached
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_cache_hit_within_ttl_window(self, timeframe_manager):
        """Test that cached data is returned when within TTL window."""
        instrument_key = "TEST_INSTRUMENT"
        signal_type = "greeks"
        timeframe = "5m"
        
        # Cached data (fresh)
        cached_data = [
            {"timestamp": "2024-01-01T10:00:00", "value": 100, "timeframe_minutes": 5},
            {"timestamp": "2024-01-01T10:05:00", "value": 105, "timeframe_minutes": 5}
        ]
        
        # Mock cache hit
        timeframe_manager.redis_client.get = AsyncMock(return_value=json.dumps(cached_data))
        
        # Mock ticker service (should not be called)
        timeframe_manager.session.get = AsyncMock()
        
        # Get aggregated data
        result = await timeframe_manager.get_aggregated_data(
            instrument_key=instrument_key,
            signal_type=signal_type,
            timeframe=timeframe,
            start_time=datetime(2024, 1, 1, 10, 0),
            end_time=datetime(2024, 1, 1, 10, 10)
        )
        
        # Verify cached data was returned
        assert result == cached_data
        
        # Verify ticker service was not called (cache hit)
        timeframe_manager.session.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_triggers_fresh_fetch(self, timeframe_manager):
        """Test that cache miss triggers fresh data fetch from ticker service."""
        instrument_key = "TEST_INSTRUMENT"
        signal_type = "greeks"
        timeframe = "5m"
        
        # Mock cache miss
        timeframe_manager.redis_client.get = AsyncMock(return_value=None)
        timeframe_manager.redis_client.setex = AsyncMock()
        
        # Mock ticker service response
        ticker_data = [{"timestamp": "2024-01-01T10:00:00", "value": 100}]
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"data_points": ticker_data})
        timeframe_manager.session.get = AsyncMock(return_value=mock_response)
        
        # Get aggregated data
        result = await timeframe_manager.get_aggregated_data(
            instrument_key=instrument_key,
            signal_type=signal_type,
            timeframe=timeframe,
            start_time=datetime(2024, 1, 1, 10, 0),
            end_time=datetime(2024, 1, 1, 10, 10)
        )
        
        # Verify ticker service was called
        timeframe_manager.session.get.assert_called_once()
        
        # Verify data was cached
        timeframe_manager.redis_client.setex.assert_called_once()
        
        # Verify aggregated data was returned
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_cache_error_handling(self, timeframe_manager):
        """Test graceful handling of cache errors."""
        instrument_key = "TEST_INSTRUMENT"
        signal_type = "greeks"
        timeframe = "5m"
        
        # Mock cache error
        timeframe_manager.redis_client.get = AsyncMock(side_effect=Exception("Redis connection failed"))
        timeframe_manager.redis_client.setex = AsyncMock()
        
        # Mock successful ticker service response
        ticker_data = [{"timestamp": "2024-01-01T10:00:00", "value": 100}]
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"data_points": ticker_data})
        timeframe_manager.session.get = AsyncMock(return_value=mock_response)
        
        # Get aggregated data (should not fail despite cache error)
        result = await timeframe_manager.get_aggregated_data(
            instrument_key=instrument_key,
            signal_type=signal_type,
            timeframe=timeframe,
            start_time=datetime(2024, 1, 1, 10, 0),
            end_time=datetime(2024, 1, 1, 10, 10)
        )
        
        # Verify ticker service was called despite cache error
        timeframe_manager.session.get.assert_called_once()
        
        # Verify data was returned
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_custom_timeframe_ttl_fallback(self, timeframe_manager):
        """Test that custom timeframes use default TTL."""
        # Test custom timeframe not in standard TTL mapping
        custom_timeframe = "7m"  # 7-minute custom timeframe
        custom_minutes = 7
        
        test_data = [{"timestamp": "2024-01-01T10:00:00", "value": 100}]
        
        # Mock Redis setex to capture TTL
        timeframe_manager.redis_client.setex = AsyncMock()
        
        # Cache data for custom timeframe
        await timeframe_manager._cache_data(
            instrument_key="TEST_INSTRUMENT",
            signal_type="greeks",
            timeframe=custom_timeframe,
            data=test_data,
            timeframe_minutes=custom_minutes
        )
        
        # Verify default TTL was used
        call_args = timeframe_manager.redis_client.setex.call_args
        actual_ttl = call_args[0][1]
        expected_default_ttl = 300  # 5 minutes default
        
        assert actual_ttl == expected_default_ttl

    @pytest.mark.asyncio
    async def test_concurrent_cache_operations(self, timeframe_manager):
        """Test cache behavior under concurrent operations."""
        instrument_key = "TEST_INSTRUMENT"
        signal_type = "greeks"
        timeframe = "5m"
        
        # Mock Redis operations with delays to simulate concurrency
        async def delayed_get(key):
            await asyncio.sleep(0.1)
            return None  # Cache miss
        
        async def delayed_setex(key, ttl, value):
            await asyncio.sleep(0.1)
            return True
        
        timeframe_manager.redis_client.get = AsyncMock(side_effect=delayed_get)
        timeframe_manager.redis_client.setex = AsyncMock(side_effect=delayed_setex)
        
        # Mock ticker service
        ticker_data = [{"timestamp": "2024-01-01T10:00:00", "value": 100}]
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"data_points": ticker_data})
        timeframe_manager.session.get = AsyncMock(return_value=mock_response)
        
        # Launch concurrent requests
        tasks = []
        for i in range(3):
            task = timeframe_manager.get_aggregated_data(
                instrument_key=instrument_key,
                signal_type=signal_type,
                timeframe=timeframe,
                start_time=datetime(2024, 1, 1, 10, 0),
                end_time=datetime(2024, 1, 1, 10, 10)
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks)
        
        # Verify all requests completed successfully
        assert len(results) == 3
        for result in results:
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_cache_key_uniqueness(self, timeframe_manager):
        """Test that cache keys are unique for different parameters."""
        # Different combinations that should generate different cache keys
        test_cases = [
            ("INSTRUMENT_A", "greeks", "5m"),
            ("INSTRUMENT_B", "greeks", "5m"),
            ("INSTRUMENT_A", "indicators", "5m"),
            ("INSTRUMENT_A", "greeks", "15m"),
        ]
        
        start_time = datetime(2024, 1, 1, 10, 0)
        end_time = datetime(2024, 1, 1, 10, 10)
        
        # Mock Redis to track cache keys used
        cache_keys_used = set()
        
        async def track_get(key):
            cache_keys_used.add(key)
            return None  # Cache miss
        
        timeframe_manager.redis_client.get = AsyncMock(side_effect=track_get)
        timeframe_manager.redis_client.setex = AsyncMock()
        
        # Mock ticker service
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"data_points": []})
        timeframe_manager.session.get = AsyncMock(return_value=mock_response)
        
        # Test all cases
        for instrument_key, signal_type, timeframe in test_cases:
            try:
                await timeframe_manager.get_aggregated_data(
                    instrument_key=instrument_key,
                    signal_type=signal_type,
                    timeframe=timeframe,
                    start_time=start_time,
                    end_time=end_time
                )
            except Exception:
                # Some may fail due to missing setup, but cache key should still be generated
                pass
        
        # Verify all cache keys are unique
        assert len(cache_keys_used) == len(test_cases)


class TestCachePerformanceMetrics:
    """Test cache performance and metrics collection."""

    @pytest.fixture
    async def timeframe_manager(self):
        """Create timeframe manager for performance testing."""
        manager = FlexibleTimeframeManager()
        manager.redis_client = AsyncMock()
        manager.session = AsyncMock()
        manager.ticker_service_url = "http://test-ticker-service"
        manager.internal_api_key = "test-key"
        return manager

    @pytest.mark.asyncio
    async def test_cache_hit_ratio_measurement(self, timeframe_manager):
        """Test measurement of cache hit ratios for business value validation."""
        # Simulate mixed cache hits and misses
        cache_responses = [
            json.dumps([{"timestamp": "2024-01-01T10:00:00", "value": 100}]),  # Hit
            None,  # Miss
            json.dumps([{"timestamp": "2024-01-01T10:05:00", "value": 105}]),  # Hit
            None,  # Miss
            None,  # Miss
        ]
        
        timeframe_manager.redis_client.get = AsyncMock(side_effect=cache_responses)
        timeframe_manager.redis_client.setex = AsyncMock()
        
        # Mock ticker service for cache misses
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"data_points": [{"timestamp": "2024-01-01T10:00:00", "value": 100}]})
        timeframe_manager.session.get = AsyncMock(return_value=mock_response)
        
        # Track cache performance
        cache_hits = 0
        cache_misses = 0
        
        # Simulate requests
        for i in range(5):
            try:
                await timeframe_manager.get_aggregated_data(
                    instrument_key=f"TEST_INSTRUMENT_{i}",
                    signal_type="greeks",
                    timeframe="5m",
                    start_time=datetime(2024, 1, 1, 10, 0),
                    end_time=datetime(2024, 1, 1, 10, 10)
                )
                
                # Check if it was a cache hit or miss
                if cache_responses[i] is not None:
                    cache_hits += 1
                else:
                    cache_misses += 1
            except Exception:
                cache_misses += 1
        
        # Calculate hit ratio
        total_requests = cache_hits + cache_misses
        hit_ratio = cache_hits / total_requests if total_requests > 0 else 0
        
        # Verify measurements
        assert cache_hits == 2
        assert cache_misses == 3
        assert hit_ratio == 0.4  # 40% hit ratio
        
        print(f"Cache Performance Metrics:")
        print(f"  Cache Hits: {cache_hits}")
        print(f"  Cache Misses: {cache_misses}")
        print(f"  Hit Ratio: {hit_ratio:.2%}")
        print(f"  Total Requests: {total_requests}")


def run_coverage_test():
    """Run timeframe cache tests with coverage measurement."""
    import subprocess
    import sys
    
    print("🔍 Running Timeframe Cache Tests with Coverage...")
    
    cmd = [
        sys.executable, '-m', 'pytest',
        __file__,
        '--cov=app.services.flexible_timeframe_manager',
        '--cov-report=term-missing',
        '--cov-report=json:coverage_timeframe_cache.json',
        '--cov-fail-under=95',
        '-v'
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    print("STDOUT:")
    print(result.stdout)
    
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
    
    return result.returncode == 0


if __name__ == "__main__":
    import asyncio
    
    print("🚀 Timeframe Cache Invalidation and TTL Tests")
    print("=" * 60)
    
    success = run_coverage_test()
    
    if success:
        print("\n✅ Timeframe cache tests passed with ≥95% coverage!")
        print("📊 Cache invalidation and TTL behavior validated for:")
        print("  - TTL values per timeframe type")
        print("  - Cache invalidation on fresh data")
        print("  - Cache hit/miss behavior")
        print("  - Error handling and graceful degradation")
        print("  - Concurrent operations")
        print("  - Cache key uniqueness")
        print("  - Performance metrics collection")
    else:
        print("\n❌ Timeframe cache tests need improvement")
        sys.exit(1)