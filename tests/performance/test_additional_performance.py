"""
Additional performance tests for Signal Service
"""
import pytest
import asyncio
import time
import statistics
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

@pytest.mark.performance
class TestCachePerformance:
    """Performance tests for caching operations"""
    
    @pytest.mark.asyncio
    async def test_redis_cache_performance(self, redis_client):
        """Test Redis cache operation performance"""
        operations = 1000
        
        # Test SET performance
        start_time = time.time()
        for i in range(operations):
            await redis_client.setex(f'perf:test:{i}', 300, f'value_{i}')
        set_time = time.time() - start_time
        
        set_ops_per_sec = operations / set_time
        assert set_ops_per_sec > 500, f"Redis SET performance {set_ops_per_sec:.2f} ops/sec too slow"
        
        # Test GET performance
        start_time = time.time()
        for i in range(operations):
            await redis_client.get(f'perf:test:{i}')
        get_time = time.time() - start_time
        
        get_ops_per_sec = operations / get_time
        assert get_ops_per_sec > 1000, f"Redis GET performance {get_ops_per_sec:.2f} ops/sec too slow"
    
    @pytest.mark.asyncio
    async def test_cache_hit_ratio_performance(self, signal_processor, redis_client):
        """Test cache hit ratio under load"""
        instruments = [
            f'NSE@PERF{i}@equity_options@2025-07-10@call@{21000+i}'
            for i in range(50)
        ]
        
        # First pass - populate cache
        for instrument in instruments:
            await signal_processor.compute_greeks_for_instrument(instrument)
        
        # Second pass - measure cache hits
        start_time = time.time()
        for instrument in instruments:
            await signal_processor.compute_greeks_for_instrument(instrument)
        cache_hit_time = time.time() - start_time
        
        # Cache hits should be significantly faster
        avg_cache_hit_time = cache_hit_time / len(instruments) * 1000  # ms
        assert avg_cache_hit_time < 10, f"Cache hit time {avg_cache_hit_time:.2f}ms too slow"

@pytest.mark.performance
class TestMoneynessPeformance:
    """Performance tests for moneyness calculations"""
    
    def test_moneyness_classification_performance(self, moneyness_calculator):
        """Test moneyness classification performance"""
        classifications = 10000
        
        start_time = time.time()
        for i in range(classifications):
            moneyness_calculator.classify_moneyness(21500 + i, 21500, 'call')
        end_time = time.time()
        
        classification_time = end_time - start_time
        classifications_per_sec = classifications / classification_time
        
        assert classifications_per_sec > 50000, f"Moneyness classification rate {classifications_per_sec:.2f} too slow"
    
    @pytest.mark.asyncio
    async def test_moneyness_aggregation_performance(self, signal_processor):
        """Test moneyness aggregation performance"""
        strikes = list(range(21000, 22000, 50))  # 20 strikes
        
        start_time = time.time()
        for _ in range(100):  # 100 aggregations
            await signal_processor.moneyness_processor._aggregate_strikes_by_moneyness(
                'NIFTY', 'ATM', strikes, 21500, 'call'
            )
        end_time = time.time()
        
        aggregation_time = (end_time - start_time) / 100 * 1000  # ms per aggregation
        assert aggregation_time < 50, f"Moneyness aggregation {aggregation_time:.2f}ms too slow"

@pytest.mark.performance
class TestMarketProfilePerformance:
    """Performance tests for market profile calculations"""
    
    @pytest.mark.asyncio
    async def test_volume_profile_performance(self, market_profile_calculator, sample_ohlcv_data):
        """Test volume profile calculation performance"""
        large_dataset = sample_ohlcv_data * 100  # 1000 data points
        
        start_time = time.time()
        for _ in range(10):
            market_profile_calculator._calculate_volume_profile(large_dataset, tick_size=1.0)
        end_time = time.time()
        
        avg_time = (end_time - start_time) / 10 * 1000  # ms per calculation
        assert avg_time < 200, f"Volume profile calculation {avg_time:.2f}ms too slow"
    
    @pytest.mark.asyncio
    async def test_tpo_profile_performance(self, market_profile_calculator, sample_ohlcv_data):
        """Test TPO profile calculation performance"""
        large_dataset = sample_ohlcv_data * 50  # 500 data points
        
        start_time = time.time()
        for _ in range(10):
            market_profile_calculator._calculate_tpo_profile(large_dataset, tick_size=1.0, interval='30m')
        end_time = time.time()
        
        avg_time = (end_time - start_time) / 10 * 1000  # ms per calculation
        assert avg_time < 300, f"TPO profile calculation {avg_time:.2f}ms too slow"

@pytest.mark.performance
class TestScalingPerformance:
    """Performance tests for scaling components"""
    
    def test_hash_ring_performance_large_scale(self):
        """Test hash ring performance with large scale"""
        from app.scaling.consistent_hash_manager import ConsistentHashManager
        
        hash_manager = ConsistentHashManager(virtual_nodes=500)  # Large scale
        
        # Add many nodes
        for i in range(50):
            hash_manager.add_node(f'signal-service-{i}')
        
        # Test lookup performance
        instruments = [f'NSE@SCALE{i}@equity_spot' for i in range(10000)]
        
        start_time = time.time()
        for instrument in instruments:
            hash_manager.get_node_for_instrument(instrument)
        end_time = time.time()
        
        lookup_time = end_time - start_time
        lookups_per_sec = len(instruments) / lookup_time
        
        assert lookups_per_sec > 5000, f"Hash lookup rate {lookups_per_sec:.2f} too slow at scale"
    
    @pytest.mark.asyncio
    async def test_backpressure_monitoring_performance(self):
        """Test backpressure monitoring performance"""
        from app.scaling.backpressure_monitor import BackpressureMonitor
        
        monitor = BackpressureMonitor()
        monitor.recommendation_cooldown = 0
        
        # Test rapid updates
        updates = 10000
        start_time = time.time()
        
        for i in range(updates):
            monitor.update_metrics(
                "pod-1",
                {
                    "queue_depth": 1000 + i % 500,
                    "p99_latency": 1200.0,
                    "cpu_usage": 0.5,
                    "memory_usage": 0.6,
                    "error_rate": 0.01
                }
            )
            monitor.get_scaling_recommendation(current_pods=2)
        
        end_time = time.time()
        update_time = end_time - start_time
        updates_per_sec = updates / update_time
        
        assert updates_per_sec > 5000, f"Backpressure monitoring rate {updates_per_sec:.2f} too slow"

@pytest.mark.performance  
class TestConcurrencyPerformance:
    """Performance tests for concurrent operations"""
    
    @pytest.mark.asyncio
    async def test_concurrent_signal_computation(self, signal_processor):
        """Test concurrent signal computation performance"""
        concurrent_tasks = 500
        
        async def compute_signal(i):
            return await signal_processor.compute_greeks_for_instrument(
                f'NSE@CONCURRENT{i}@equity_options@2025-07-10@call@{21000+i}'
            )
        
        start_time = time.time()
        tasks = [compute_signal(i) for i in range(concurrent_tasks)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()
        
        total_time = end_time - start_time
        successful_tasks = len([r for r in results if not isinstance(r, Exception)])
        throughput = successful_tasks / total_time
        
        assert throughput > 50, f"Concurrent computation throughput {throughput:.2f} ops/sec too low"
        assert successful_tasks / concurrent_tasks > 0.9, "Too many failed concurrent operations"
    
    @pytest.mark.asyncio
    async def test_frequency_processing_concurrency(self, signal_processor):
        """Test frequency processing concurrency"""
        from app.services.frequency_feed_manager import FeedFrequency
        
        # Add many subscriptions
        for i in range(100):
            await signal_processor.frequency_feed_manager.update_subscription_frequency(
                f'user_{i}', f'INSTRUMENT_{i%10}', 'greeks', '5m'
            )
        
        # Process concurrently
        start_time = time.time()
        tasks = [
            signal_processor.frequency_feed_manager._process_frequency_batch(FeedFrequency.MINUTE_5)
            for _ in range(10)  # 10 concurrent batch processes
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()
        
        processing_time = end_time - start_time
        assert processing_time < 5, f"Concurrent frequency processing took {processing_time:.2f}s"

@pytest.mark.performance
class TestMemoryPerformance:
    """Performance tests for memory usage"""
    
    @pytest.mark.asyncio
    async def test_memory_efficiency(self, signal_processor):
        """Test memory efficiency under load"""
        import psutil
        import gc
        
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Process many signals
        for batch in range(10):
            instruments = [f'NSE@MEM{i}@equity_options@2025-07-10@call@{21000+i}' 
                          for i in range(100)]
            
            for instrument in instruments:
                await signal_processor.compute_greeks_for_instrument(instrument)
            
            # Force garbage collection
            gc.collect()
        
        final_memory = process.memory_info().rss / 1024 / 1024
        memory_increase = final_memory - initial_memory
        
        assert memory_increase < 500, f"Memory increase {memory_increase:.2f}MB too high"
    
    @pytest.mark.asyncio
    async def test_cache_memory_management(self, redis_client):
        """Test cache memory management"""
        # Fill cache with data
        for i in range(1000):
            await redis_client.setex(f'cache:test:{i}', 300, f'data_{i}' * 100)
        
        # Memory should be managed efficiently
        info = await redis_client.info('memory')
        used_memory_mb = info.get('used_memory', 0) / 1024 / 1024
        
        assert used_memory_mb < 100, f"Redis memory usage {used_memory_mb:.2f}MB too high"
