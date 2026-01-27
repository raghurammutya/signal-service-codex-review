"""
Performance and load tests for Signal Service

Enhanced with external config service integration for testing
performance under dynamic configuration scenarios.
"""
import asyncio
import contextlib
import json
import os
import statistics
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import aiohttp
import psutil
import pytest


@pytest.mark.performance
class TestSignalProcessingPerformance:
    """Performance tests for signal processing"""

    @pytest.mark.asyncio
    async def test_single_signal_computation_latency(self, signal_processor):
        """Test single signal computation meets latency requirements (<50ms)"""
        latencies = []

        for _ in range(100):
            start = time.time()
            await signal_processor.compute_greeks_for_instrument(
                'NSE@NIFTY@equity_options@2025-07-10@call@21500'
            )
            end = time.time()
            latencies.append((end - start) * 1000)  # Convert to ms

        avg_latency = statistics.mean(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18]  # 95th percentile

        assert avg_latency < 50, f"Average latency {avg_latency:.2f}ms exceeds 50ms requirement"
        assert p95_latency < 100, f"95th percentile latency {p95_latency:.2f}ms exceeds 100ms requirement"

        print(f"Signal computation - Avg: {avg_latency:.2f}ms, P95: {p95_latency:.2f}ms")

    @pytest.mark.asyncio
    async def test_concurrent_signal_processing(self, signal_processor):
        """Test concurrent signal processing performance"""
        instruments = [
            f'NSE@TEST{i}@equity_options@2025-07-10@call@{21000 + i*10}'
            for i in range(100)
        ]

        start_time = time.time()

        # Process all instruments concurrently
        tasks = [
            signal_processor.compute_greeks_for_instrument(instrument)
            for instrument in instruments
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        end_time = time.time()
        total_time = end_time - start_time

        # Check for errors
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"Found {len(errors)} errors in concurrent processing"

        # Performance assertions
        throughput = len(instruments) / total_time
        assert throughput > 50, f"Throughput {throughput:.2f} signals/sec too low"
        assert total_time < 5, f"Processing 100 instruments took {total_time:.2f}s, expected <5s"

        print(f"Concurrent processing - {throughput:.2f} signals/sec in {total_time:.2f}s")

    @pytest.mark.asyncio
    async def test_bulk_computation_performance(self, signal_processor, load_test_data):
        """Test bulk computation performance"""
        batch_sizes = [10, 50, 100, 500, 1000]

        for batch_size in batch_sizes:
            instruments = [item['instrument_key'] for item in load_test_data[:batch_size]]

            start_time = time.time()

            # Batch process instruments
            results = await signal_processor.bulk_compute_greeks(instruments)

            end_time = time.time()
            batch_time = end_time - start_time

            # Performance requirements
            per_instrument_time = batch_time / batch_size * 1000  # ms per instrument
            assert per_instrument_time < 10, f"Batch size {batch_size}: {per_instrument_time:.2f}ms per instrument too slow"

            # Should complete all computations
            assert len(results) == batch_size

            print(f"Batch size {batch_size}: {per_instrument_time:.2f}ms per instrument")

    @pytest.mark.asyncio
    async def test_memory_usage_under_load(self, signal_processor, load_test_data):
        """Test memory usage under sustained load"""
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Process sustained load
        for batch in range(10):  # 10 batches of 100 instruments each
            instruments = [
                item['instrument_key']
                for item in load_test_data[batch*100:(batch+1)*100]
            ]

            tasks = [
                signal_processor.compute_greeks_for_instrument(instrument)
                for instrument in instruments
            ]
            await asyncio.gather(*tasks)

            # Check memory after each batch
            current_memory = process.memory_info().rss / 1024 / 1024
            memory_increase = current_memory - initial_memory

            # Memory should not grow excessively
            assert current_memory < 4096, f"Memory usage {current_memory:.2f}MB exceeds 4GB limit"
            assert memory_increase < 1024, f"Memory increase {memory_increase:.2f}MB too high"

        final_memory = process.memory_info().rss / 1024 / 1024
        print(f"Memory usage - Initial: {initial_memory:.2f}MB, Final: {final_memory:.2f}MB")


@pytest.mark.performance
class TestAPIPerformance:
    """Performance tests for API endpoints"""

    @pytest.mark.asyncio
    async def test_realtime_api_response_time(self, async_client):
        """Test real-time API response time"""
        endpoint = "/api/v2/signals/realtime/greeks/NSE@NIFTY@equity_options@2025-07-10@call@21500"
        response_times = []

        for _ in range(50):
            start = time.time()
            response = await async_client.get(endpoint)
            end = time.time()

            assert response.status_code == 200
            response_times.append((end - start) * 1000)  # Convert to ms

        avg_response_time = statistics.mean(response_times)
        p95_response_time = statistics.quantiles(response_times, n=20)[18]

        assert avg_response_time < 100, f"Average API response time {avg_response_time:.2f}ms too slow"
        assert p95_response_time < 200, f"95th percentile response time {p95_response_time:.2f}ms too slow"

        print(f"API response time - Avg: {avg_response_time:.2f}ms, P95: {p95_response_time:.2f}ms")

    @pytest.mark.asyncio
    async def test_historical_data_query_performance(self, async_client):
        """Test historical data query performance"""
        endpoint = "/api/v2/signals/historical/greeks/NSE@NIFTY@equity_options@2025-07-10@call@21500"
        params = {
            'start_time': (datetime.utcnow() - timedelta(days=7)).isoformat(),
            'end_time': datetime.utcnow().isoformat(),
            'timeframe': '5m'
        }

        start = time.time()
        response = await async_client.get(endpoint, params=params)
        end = time.time()

        assert response.status_code == 200
        query_time = (end - start) * 1000

        assert query_time < 2000, f"Historical query took {query_time:.2f}ms, expected <2000ms"

        # Verify response data
        data = response.json()
        assert 'time_series' in data
        assert len(data['time_series']) > 0

        print(f"Historical query time: {query_time:.2f}ms")

    @pytest.mark.asyncio
    async def test_batch_api_performance(self, async_client):
        """Test batch API performance"""
        instruments = [
            f'NSE@TEST{i}@equity_options@2025-07-10@call@{21000 + i*10}'
            for i in range(100)
        ]

        payload = {
            'instruments': instruments,
            'signal_types': ['greeks', 'indicators']
        }

        start = time.time()
        response = await async_client.post("/api/v2/signals/batch/compute", json=payload)
        end = time.time()

        assert response.status_code == 200
        batch_time = (end - start) * 1000

        # Should process 100 instruments in reasonable time
        assert batch_time < 5000, f"Batch processing took {batch_time:.2f}ms, expected <5000ms"

        data = response.json()
        assert len(data['results']) == 100

        print(f"Batch API time: {batch_time:.2f}ms for 100 instruments")

    @pytest.mark.asyncio
    async def test_concurrent_api_requests(self, async_client):
        """Test concurrent API request handling"""
        endpoint = "/api/v2/signals/realtime/greeks/NSE@NIFTY@equity_options@2025-07-10@call@21500"

        async def make_request():
            response = await async_client.get(endpoint)
            return response.status_code == 200

        # Make 100 concurrent requests
        start_time = time.time()
        tasks = [make_request() for _ in range(100)]
        results = await asyncio.gather(*tasks)
        end_time = time.time()

        total_time = end_time - start_time
        success_rate = sum(results) / len(results)

        assert success_rate > 0.95, f"Success rate {success_rate:.2%} too low"
        assert total_time < 10, f"100 concurrent requests took {total_time:.2f}s"

        requests_per_second = len(results) / total_time
        print(f"Concurrent API - {requests_per_second:.2f} requests/sec, {success_rate:.2%} success")


@pytest.mark.performance
class TestWebSocketPerformance:
    """Performance tests for WebSocket connections"""

    @pytest.mark.asyncio
    async def test_websocket_connection_capacity(self):
        """Test WebSocket connection capacity"""
        import websockets

        connections = []
        max_connections = 1000

        try:
            # Establish connections
            for i in range(max_connections):
                try:
                    ws = await websockets.connect(
                        f"ws://localhost:8003/api/v2/signals/subscriptions/websocket?client_id=client_{i}"
                    )
                    connections.append(ws)
                except Exception as e:
                    print(f"Failed to establish connection {i}: {e}")
                    break

            established_connections = len(connections)
            assert established_connections >= 1000, f"Only established {established_connections} connections"

            # Test message broadcasting
            start_time = time.time()

            # Send subscription message to all connections
            for ws in connections[:100]:  # Test with first 100
                await ws.send(json.dumps({
                    'type': 'subscribe',
                    'channel': 'greeks',
                    'instrument': 'NIFTY'
                }))

            broadcast_time = time.time() - start_time
            assert broadcast_time < 1, f"Broadcasting to 100 connections took {broadcast_time:.2f}s"

            print(f"WebSocket capacity - {established_connections} connections, broadcast: {broadcast_time:.2f}s")

        finally:
            # Cleanup connections
            for ws in connections:
                with contextlib.suppress(Exception):
                    await ws.close()

    @pytest.mark.asyncio
    async def test_websocket_message_throughput(self):
        """Test WebSocket message throughput"""
        import websockets

        # Establish single connection
        ws = await websockets.connect(
            "ws://localhost:8003/api/v2/signals/subscriptions/websocket?client_id=test_client"
        )

        try:
            # Subscribe to channel
            await ws.send(json.dumps({
                'type': 'subscribe',
                'channel': 'greeks',
                'instrument': 'NIFTY'
            }))

            # Measure message throughput
            message_count = 1000
            start_time = time.time()

            # Send many messages
            for i in range(message_count):
                await ws.send(json.dumps({
                    'type': 'data',
                    'sequence': i,
                    'timestamp': time.time()
                }))

            end_time = time.time()
            throughput_time = end_time - start_time

            messages_per_second = message_count / throughput_time
            assert messages_per_second > 100, f"Message throughput {messages_per_second:.2f} msg/sec too low"

            print(f"WebSocket throughput: {messages_per_second:.2f} messages/sec")

        finally:
            await ws.close()


@pytest.mark.performance
class TestDatabasePerformance:
    """Performance tests for database operations"""

    @pytest.mark.postgres
    @pytest.mark.asyncio
    async def test_bulk_insert_performance(self, db_session):
        """Test bulk insert performance"""
        from app.models.signal_models import SignalGreeks
        from app.repositories.signal_repository import SignalRepository

        repository = SignalRepository(db_session)

        # Create test data
        bulk_sizes = [100, 500, 1000, 5000]

        for bulk_size in bulk_sizes:
            records = []
            for i in range(bulk_size):
                records.append(SignalGreeks(
                    instrument_key=f'NSE@TEST{i}@equity_options@2025-07-10@call@{21000+i}',
                    timestamp=datetime.utcnow(),
                    delta=0.5,
                    gamma=0.01,
                    theta=-0.05,
                    vega=0.15,
                    rho=0.03
                ))

            start_time = time.time()
            await repository.bulk_save_greeks(records)
            end_time = time.time()

            insert_time = end_time - start_time
            records_per_second = bulk_size / insert_time

            # Performance requirements
            assert records_per_second > 1000, f"Bulk insert rate {records_per_second:.2f} records/sec too slow"

            print(f"Bulk insert {bulk_size} records: {records_per_second:.2f} records/sec")

    @pytest.mark.postgres
    @pytest.mark.asyncio
    async def test_complex_query_performance(self, db_session):
        """Test complex query performance"""
        from app.repositories.signal_repository import SignalRepository

        repository = SignalRepository(db_session)

        # Test time-series aggregation query
        start_time = time.time()

        await repository.get_aggregated_greeks(
            instruments=['NSE@NIFTY@equity_options@2025-07-10@call@21500'],
            start_time=datetime.utcnow() - timedelta(days=30),
            end_time=datetime.utcnow(),
            aggregation_interval='1h'
        )

        end_time = time.time()
        query_time = (end_time - start_time) * 1000  # Convert to ms

        assert query_time < 2000, f"Complex query took {query_time:.2f}ms, expected <2000ms"

        print(f"Complex query time: {query_time:.2f}ms")

    @pytest.mark.redis
    @pytest.mark.asyncio
    async def test_redis_performance(self, redis_client):
        """Test Redis performance"""
        # Test basic operations
        operations = 10000

        # Test SET operations
        start_time = time.time()
        for i in range(operations):
            await redis_client.setex(f'test:key:{i}', 300, f'value_{i}')
        set_time = time.time() - start_time

        set_ops_per_sec = operations / set_time
        assert set_ops_per_sec > 1000, f"Redis SET operations {set_ops_per_sec:.2f} ops/sec too slow"

        # Test GET operations
        start_time = time.time()
        for i in range(operations):
            await redis_client.get(f'test:key:{i}')
        get_time = time.time() - start_time

        get_ops_per_sec = operations / get_time
        assert get_ops_per_sec > 2000, f"Redis GET operations {get_ops_per_sec:.2f} ops/sec too slow"

        print(f"Redis performance - SET: {set_ops_per_sec:.2f} ops/sec, GET: {get_ops_per_sec:.2f} ops/sec")


@pytest.mark.performance
class TestScalingPerformance:
    """Performance tests for scaling components"""

    def test_consistent_hash_performance(self):
        """Test consistent hash performance"""
        from app.scaling.consistent_hash_manager import ConsistentHashManager

        hash_manager = ConsistentHashManager(virtual_nodes=150)

        # Add nodes
        for i in range(10):
            hash_manager.add_node(f'signal-service-{i}')

        # Test lookup performance
        instruments = [f'NSE@TEST{i}@equity_spot' for i in range(10000)]

        start_time = time.time()
        for instrument in instruments:
            hash_manager.get_node_for_instrument(instrument)
        end_time = time.time()

        lookup_time = end_time - start_time
        lookups_per_second = len(instruments) / lookup_time

        assert lookups_per_second > 10000, f"Hash lookup rate {lookups_per_second:.2f} lookups/sec too slow"

        print(f"Consistent hash performance: {lookups_per_second:.2f} lookups/sec")

    @pytest.mark.asyncio
    async def test_backpressure_monitoring_performance(self):
        """Test backpressure monitoring performance"""
        from app.scaling.backpressure_monitor import BackpressureMonitor

        monitor = BackpressureMonitor()
        monitor.recommendation_cooldown = 0

        # Test metric update performance
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
        updates_per_second = updates / update_time

        assert updates_per_second > 1000, f"Backpressure updates {updates_per_second:.2f} updates/sec too slow"

        print(f"Backpressure monitoring: {updates_per_second:.2f} updates/sec")


@pytest.mark.performance
class TestExternalConfigServicePerformance:
    """Performance tests with external config service integration."""

    @pytest.fixture
    def external_config_endpoints(self):
        """External config service endpoints for performance testing."""
        return {
            "primary": "http://test-config.local",
            "secondary": "http://test-config-secondary.local",
            "api_key": "[REDACTED-TEST-PLACEHOLDER]"
        }

    @pytest.mark.asyncio
    async def test_external_config_service_response_time(self, external_config_endpoints):
        """Test external config service response time for performance validation."""
        response_times = []

        for endpoint_name, url in external_config_endpoints.items():
            if endpoint_name == "api_key":  # Skip API key entry
                continue

            try:
                for _ in range(10):  # Test 10 requests per endpoint
                    start_time = time.time()

                    async with aiohttp.ClientSession() as session, session.get(
                        f"{url}/health",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        await response.json()  # Ensure full response processing

                    end_time = time.time()
                    response_times.append((end_time - start_time) * 1000)  # Convert to ms

            except Exception as e:
                print(f"External config service {endpoint_name} unavailable: {e}")
                # Continue testing with available services

        if response_times:
            avg_response_time = statistics.mean(response_times)
            max_response_time = max(response_times)

            # Performance assertions for external config service
            assert avg_response_time < 1000, f"External config service avg response {avg_response_time:.2f}ms too slow"
            assert max_response_time < 5000, f"External config service max response {max_response_time:.2f}ms too slow"

            print(f"External config service performance - Avg: {avg_response_time:.2f}ms, Max: {max_response_time:.2f}ms")
        else:
            print("No external config services available for performance testing")

    @pytest.mark.asyncio
    async def test_concurrent_config_operations_performance(self, external_config_endpoints):
        """Test concurrent configuration operations performance."""
        base_url = external_config_endpoints["primary"]
        api_key = external_config_endpoints["api_key"]

        async def perform_config_operation(operation_id: int):
            """Perform a configuration read operation."""
            try:
                async with aiohttp.ClientSession() as session:
                    headers = {"X-Internal-API-Key": api_key}

                    # Test configuration read operation
                    config_key = f"TEST_CONCURRENT_PARAM_{operation_id}"

                    async with session.get(
                        f"{base_url}/api/v1/config/{config_key}?environment=dev",
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        return response.status in [200, 404]  # Both OK (found/not found)

            except Exception:
                return False  # Operation failed

        # Test concurrent operations
        concurrent_operations = 50
        start_time = time.time()

        tasks = [
            perform_config_operation(i)
            for i in range(concurrent_operations)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        end_time = time.time()
        total_time = end_time - start_time

        successful_operations = sum(
            1 for result in results
            if not isinstance(result, Exception) and result
        )

        if successful_operations > 0:
            ops_per_second = successful_operations / total_time
            success_rate = successful_operations / concurrent_operations

            # Performance assertions
            assert ops_per_second > 5, f"Config ops rate {ops_per_second:.2f} ops/sec too low"
            assert success_rate > 0.5, f"Config ops success rate {success_rate:.2%} too low"

            print(f"Concurrent config operations - {ops_per_second:.2f} ops/sec, {success_rate:.2%} success")
        else:
            print("External config service unavailable for concurrent operations test")

    @pytest.mark.asyncio
    async def test_hot_reload_performance_simulation(self, signal_processor):
        """Test performance impact of hot reload operations during processing."""
        # Simulate hot reload events during signal processing
        from app.core.hot_config import get_hot_reloadable_settings

        # Create test configuration
        with patch.dict(os.environ, {'USE_EXTERNAL_CONFIG': 'false', 'ENVIRONMENT': 'test'}):
            # Mock config dependencies
            with patch('app.core.hot_config.BaseSignalServiceConfig.__init__') as mock_init:
                mock_init.return_value = None
                config = get_hot_reloadable_settings()

                # Mock handler registration
                reload_events = 0

                async def mock_reload_handler(data):
                    nonlocal reload_events
                    reload_events += 1
                    await asyncio.sleep(0.001)  # Simulate reload work

                config.register_hot_reload_handler("test_reload", mock_reload_handler)

                # Test signal processing with simulated hot reloads
                processing_tasks = []
                reload_tasks = []

                start_time = time.time()

                # Start signal processing tasks
                for i in range(100):
                    task = signal_processor.compute_greeks_for_instrument(
                        f'NSE@HOTRELOAD{i}@equity_options@2025-07-10@call@21500'
                    )
                    processing_tasks.append(task)

                # Simulate hot reload events during processing
                for i in range(10):  # 10 reload events
                    reload_task = asyncio.create_task(mock_reload_handler({"test": f"reload_{i}"}))
                    reload_tasks.append(reload_task)

                # Execute all tasks concurrently
                all_results = await asyncio.gather(
                    *processing_tasks, *reload_tasks,
                    return_exceptions=True
                )

                end_time = time.time()
                total_time = end_time - start_time

                # Analyze performance impact
                processing_errors = sum(
                    1 for result in all_results[:100]  # First 100 are processing tasks
                    if isinstance(result, Exception)
                )

                success_rate = (100 - processing_errors) / 100
                processing_throughput = (100 - processing_errors) / total_time

                # Performance assertions
                assert success_rate > 0.95, f"Hot reload degraded processing success rate to {success_rate:.2%}"
                assert processing_throughput > 20, f"Hot reload degraded throughput to {processing_throughput:.2f} ops/sec"

                print(f"Hot reload performance - {reload_events} reloads, {processing_throughput:.2f} ops/sec, {success_rate:.2%} success")


@pytest.mark.performance
class TestStressTests:
    """Stress tests for extreme conditions"""

    @pytest.mark.asyncio
    async def test_extreme_concurrent_load(self, signal_processor):
        """Test extreme concurrent load"""
        # Simulate extreme load with many concurrent operations
        concurrent_operations = 5000

        tasks = []
        start_time = time.time()

        # Create many concurrent tasks
        for i in range(concurrent_operations):
            task = signal_processor.compute_greeks_for_instrument(
                f'NSE@STRESS{i}@equity_options@2025-07-10@call@{20000 + i}'
            )
            tasks.append(task)

        # Execute all tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()

        total_time = end_time - start_time

        # Count successful operations
        successful = len([r for r in results if not isinstance(r, Exception)])
        success_rate = successful / concurrent_operations

        assert success_rate > 0.9, f"Success rate {success_rate:.2%} too low under extreme load"
        assert total_time < 60, f"Extreme load test took {total_time:.2f}s, expected <60s"

        throughput = successful / total_time
        print(f"Extreme load - {throughput:.2f} ops/sec, {success_rate:.2%} success rate")

    @pytest.mark.asyncio
    async def test_memory_stress(self, signal_processor):
        """Test memory stress conditions"""
        import gc

        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024

        # Create memory pressure
        large_datasets = []

        try:
            for iteration in range(100):
                # Create large dataset
                large_data = [
                    {
                        'instrument_key': f'NSE@MEMORY{i}@equity_options@2025-07-10@call@{20000+i}',
                        'greeks': {'delta': 0.5, 'gamma': 0.01, 'theta': -0.05},
                        'timestamp': datetime.utcnow(),
                        'data': 'x' * 1000  # 1KB of data per item
                    }
                    for i in range(1000)  # 1MB per iteration
                ]

                large_datasets.append(large_data)

                # Process some data
                await signal_processor.compute_greeks_for_instrument(
                    f'NSE@MEMORY{iteration}@equity_options@2025-07-10@call@21500'
                )

                current_memory = process.memory_info().rss / 1024 / 1024

                # Memory should not grow uncontrollably
                if current_memory > 8192:  # 8GB limit
                    pytest.fail(f"Memory usage {current_memory:.2f}MB exceeds stress test limit")

                # Force garbage collection periodically
                if iteration % 10 == 0:
                    gc.collect()

            final_memory = process.memory_info().rss / 1024 / 1024
            print(f"Memory stress test - Initial: {initial_memory:.2f}MB, Final: {final_memory:.2f}MB")

        finally:
            # Cleanup
            large_datasets.clear()
            gc.collect()

    @pytest.mark.asyncio
    async def test_sustained_load_endurance(self, signal_processor):
        """Test sustained load over extended period"""
        duration_minutes = 5  # 5-minute endurance test
        end_time = time.time() + (duration_minutes * 60)

        operations_completed = 0
        errors = 0

        while time.time() < end_time:
            try:
                # Continuous processing
                await signal_processor.compute_greeks_for_instrument(
                    f'NSE@ENDURANCE{operations_completed}@equity_options@2025-07-10@call@21500'
                )
                operations_completed += 1

                # Brief pause to avoid overwhelming
                await asyncio.sleep(0.01)

            except Exception:
                errors += 1
                if errors > operations_completed * 0.1:  # More than 10% error rate
                    pytest.fail(f"Error rate too high in endurance test: {errors}/{operations_completed}")

        error_rate = errors / operations_completed if operations_completed > 0 else 1
        ops_per_minute = operations_completed / duration_minutes

        assert error_rate < 0.05, f"Error rate {error_rate:.2%} too high in endurance test"
        assert ops_per_minute > 100, f"Operations per minute {ops_per_minute:.2f} too low"

        print(f"Endurance test - {ops_per_minute:.2f} ops/min, {error_rate:.2%} error rate")
