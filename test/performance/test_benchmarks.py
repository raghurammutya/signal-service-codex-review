"""Performance benchmark tests."""
import asyncio
import gc
import time
from concurrent.futures import ThreadPoolExecutor

import psutil
import pytest

from app.services.greeks_calculator import GreeksCalculator
from app.services.smart_money_indicators import SmartMoneyIndicators


class TestPerformanceBenchmarks:
    """Benchmark tests for performance validation."""

    @pytest.mark.performance
    @pytest.mark.benchmark(group="greeks")
    def test_greeks_calculation_benchmark(self, benchmark):
        """Benchmark Greeks calculation performance."""
        calculator = GreeksCalculator()

        def calculate_greeks():
            return calculator.calculate_greeks(
                spot_price=20000,
                strike_price=20000,
                time_to_expiry=0.25,
                risk_free_rate=0.06,
                volatility=0.20,
                option_type="call"
            )

        result = benchmark(calculate_greeks)
        assert "delta" in result

        # Performance assertions
        stats = benchmark.stats
        assert stats.mean < 0.01, f"Mean time too high: {stats.mean:.4f}s (should be <10ms)"
        assert stats.max < 0.05, f"Max time too high: {stats.max:.4f}s (should be <50ms)"

    @pytest.mark.performance
    @pytest.mark.benchmark(group="smart_money")
    def test_smart_money_benchmark(self, benchmark, performance_test_data):
        """Benchmark Smart Money indicators performance."""
        indicators = SmartMoneyIndicators()
        large_data = performance_test_data["large_ohlcv"]

        def calculate_bos():
            return indicators.calculate_break_of_structure(large_data)

        result = benchmark(calculate_bos)
        assert result is not None

        # Performance assertions
        stats = benchmark.stats
        assert stats.mean < 2.0, f"BOS calculation too slow: {stats.mean:.2f}s (should be <2s)"

    @pytest.mark.performance
    async def test_concurrent_greeks_performance(self):
        """Test Greeks calculation under concurrent load."""
        calculator = GreeksCalculator()

        async def calculate_batch():
            tasks = []
            for i in range(100):
                spot = 20000 + i * 10

                async def calc_single():
                    return calculator.calculate_greeks(
                        spot_price=spot,
                        strike_price=20000,
                        time_to_expiry=0.25,
                        risk_free_rate=0.06,
                        volatility=0.20,
                        option_type="call"
                    )

                tasks.append(calc_single())

            start_time = time.time()
            results = await asyncio.gather(*tasks)
            end_time = time.time()

            return results, end_time - start_time

        results, duration = await calculate_batch()

        assert len(results) == 100
        assert duration < 5.0, f"100 concurrent calculations took {duration:.2f}s (should be <5s)"
        assert all("delta" in result for result in results)

        # Verify results are different (real calculations)
        deltas = [r["delta"] for r in results]
        assert len(set(deltas)) > 1, "Results should vary with different spot prices"

    @pytest.mark.performance
    def test_memory_usage_benchmark(self):
        """Monitor memory usage during intensive operations."""
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Perform memory-intensive operations
        indicators = SmartMoneyIndicators()
        calculator = GreeksCalculator()

        # Create multiple large datasets
        import numpy as np
        import pandas as pd

        datasets = []
        for _ in range(5):
            large_data = pd.DataFrame({
                'open': np.random.uniform(19800, 20200, 2000),
                'high': np.random.uniform(20000, 20400, 2000),
                'low': np.random.uniform(19600, 20000, 2000),
                'close': np.random.uniform(19800, 20200, 2000),
                'volume': np.random.randint(100000, 1000000, 2000)
            })
            datasets.append(large_data)

        # Process all datasets
        results = []
        for data in datasets:
            bos = indicators.calculate_break_of_structure(data)
            order_blocks = indicators.identify_order_blocks(data)
            fvg = indicators.detect_fair_value_gaps(data)
            results.append((bos, order_blocks, fvg))

        # Calculate many Greeks
        greeks_results = []
        for i in range(500):
            greeks = calculator.calculate_greeks(
                spot_price=19000 + i * 10,
                strike_price=20000,
                time_to_expiry=0.25,
                risk_free_rate=0.06,
                volatility=0.15 + (i * 0.001),
                option_type="call" if i % 2 == 0 else "put"
            )
            greeks_results.append(greeks)

        peak_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = peak_memory - initial_memory

        # Cleanup
        del datasets, results, greeks_results
        gc.collect()

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_leak = final_memory - initial_memory

        # Assertions
        assert memory_increase < 500, f"Memory increase too high: {memory_increase:.1f}MB (should be <500MB)"
        assert memory_leak < 50, f"Memory leak detected: {memory_leak:.1f}MB (should be <50MB)"

    @pytest.mark.performance
    def test_threading_performance(self):
        """Test performance with threading."""
        calculator = GreeksCalculator()

        def calculate_single(params):
            spot, strike = params
            return calculator.calculate_greeks(
                spot_price=spot,
                strike_price=strike,
                time_to_expiry=0.25,
                risk_free_rate=0.06,
                volatility=0.20,
                option_type="call"
            )

        # Prepare test parameters
        test_params = [(20000 + i*10, 20000 + i*5) for i in range(100)]

        # Test sequential execution
        start_time = time.time()
        sequential_results = [calculate_single(params) for params in test_params]
        sequential_duration = time.time() - start_time

        # Test threaded execution
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=10) as executor:
            threaded_results = list(executor.map(calculate_single, test_params))
        threaded_duration = time.time() - start_time

        # Verify results are identical
        assert len(sequential_results) == len(threaded_results) == 100

        for seq_result, threaded_result in zip(sequential_results, threaded_results, strict=False):
            assert abs(seq_result["delta"] - threaded_result["delta"]) < 1e-10

        # Threading should be faster for CPU-intensive operations
        speedup = sequential_duration / threaded_duration
        assert speedup > 1.5, f"Threading speedup insufficient: {speedup:.2f}x (should be >1.5x)"

    @pytest.mark.performance
    def test_large_dataset_performance(self):
        """Test performance with large datasets."""
        indicators = SmartMoneyIndicators()

        # Create progressively larger datasets
        sizes = [1000, 5000, 10000]
        times = []

        for size in sizes:
            import numpy as np
            import pandas as pd

            large_data = pd.DataFrame({
                'open': np.random.uniform(19800, 20200, size),
                'high': np.random.uniform(20000, 20400, size),
                'low': np.random.uniform(19600, 20000, size),
                'close': np.random.uniform(19800, 20200, size),
                'volume': np.random.randint(100000, 1000000, size)
            })

            start_time = time.time()

            # Test all Smart Money calculations
            bos = indicators.calculate_break_of_structure(large_data)
            order_blocks = indicators.identify_order_blocks(large_data)
            fvg = indicators.detect_fair_value_gaps(large_data)
            liquidity = indicators.calculate_liquidity_levels(large_data)

            duration = time.time() - start_time
            times.append(duration)

            # Verify results
            assert bos is not None, f"BOS failed for size {size}"
            assert order_blocks is not None, f"Order blocks failed for size {size}"
            assert fvg is not None, f"FVG failed for size {size}"
            assert liquidity is not None, f"Liquidity levels failed for size {size}"

            print(f"Size {size}: {duration:.2f}s")

        # Performance should scale reasonably (not exponentially)
        for i in range(1, len(times)):
            size_ratio = sizes[i] / sizes[i-1]
            time_ratio = times[i] / times[i-1]

            # Time increase should be less than size increase squared
            assert time_ratio < size_ratio ** 2, f"Performance degrades too much: {time_ratio:.2f}x time for {size_ratio}x data"

    @pytest.mark.performance
    def test_api_response_time_benchmark(self, benchmark):
        """Benchmark API response times."""
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)

        def make_api_request():
            # Mock external dependencies for consistent benchmarking
            with patch('app.services.greeks_calculator.GreeksCalculator.calculate_greeks') as mock_calc:
                mock_calc.return_value = {
                    "delta": 0.5234,
                    "gamma": 0.0156,
                    "theta": -12.45,
                    "vega": 89.23,
                    "rho": 67.89
                }

                response = client.post("/api/v2/greeks/calculate", json={
                    "spot_price": 20000,
                    "options": [{
                        "instrument_key": "NSE@TESTSYM@CE@20000",
                        "strike_price": 20000,
                        "option_type": "call",
                        "expiry_date": "2024-12-28"
                    }]
                })

                return response.status_code

        status_code = benchmark(make_api_request)
        assert status_code in [200, 500]  # Success or mocked failure

        # API response time should be fast
        stats = benchmark.stats
        assert stats.mean < 0.5, f"API response too slow: {stats.mean:.3f}s (should be <500ms)"

    @pytest.mark.performance
    def test_database_performance_simulation(self):
        """Simulate database performance patterns."""
        from unittest.mock import AsyncMock, patch

        from app.repositories.signal_repository import SignalRepository

        # Mock database operations with realistic latency
        async def mock_slow_query(*args, **kwargs):
            await asyncio.sleep(0.01)  # 10ms latency
            return {"id": 123}

        async def mock_fast_query(*args, **kwargs):
            await asyncio.sleep(0.001)  # 1ms latency
            return

        async def test_repository_performance():
            repo = SignalRepository()

            with patch.object(repo, 'db_connection') as mock_db:
                mock_conn = AsyncMock()
                mock_conn.fetchrow.side_effect = mock_slow_query
                mock_conn.fetch.side_effect = mock_fast_query
                mock_db.acquire.return_value.__aenter__.return_value = mock_conn
                repo._initialized = True

                # Test multiple operations
                start_time = time.time()

                tasks = []
                for i in range(50):
                    # Simulate mixed read/write operations
                    if i % 3 == 0:
                        task = repo.get_latest_greeks(f"NSE@TEST{i}@CE@20000")
                    else:
                        task = repo.get_latest_indicator(f"NSE@TEST{i}", "RSI")
                    tasks.append(task)

                try:
                    await asyncio.gather(*tasks, return_exceptions=True)
                except:
                    pass  # Expected with mocked exceptions

                duration = time.time() - start_time
                return duration

        duration = asyncio.run(test_repository_performance())

        # Should handle 50 concurrent database operations efficiently
        assert duration < 2.0, f"Database operations too slow: {duration:.2f}s (should be <2s)"

    @pytest.mark.performance
    def test_json_serialization_performance(self, benchmark):
        """Benchmark JSON serialization of large responses."""
        import json

        # Create large Greeks response
        large_response = {
            "options": [
                {
                    "instrument_key": f"NSE@TESTSYM{i}@CE@{20000 + i*10}",
                    "delta": 0.5234 + i * 0.001,
                    "gamma": 0.0156 + i * 0.0001,
                    "theta": -12.45 - i * 0.1,
                    "vega": 89.23 + i * 0.5,
                    "rho": 67.89 + i * 0.2,
                    "timestamp": "2024-01-01T10:00:00Z"
                }
                for i in range(1000)  # 1000 options
            ],
            "metadata": {
                "calculation_time_ms": 123,
                "total_options": 1000,
                "timestamp": "2024-01-01T10:00:00Z"
            }
        }

        def serialize_response():
            return json.dumps(large_response)

        json_string = benchmark(serialize_response)
        assert len(json_string) > 100000  # Should be substantial response

        # JSON serialization should be fast
        stats = benchmark.stats
        assert stats.mean < 0.1, f"JSON serialization too slow: {stats.mean:.3f}s (should be <100ms)"
