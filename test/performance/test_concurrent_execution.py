"""
Performance tests for concurrent external function execution
Tests load handling, resource management, and system stability under stress
"""

import asyncio
import random
import time
from datetime import datetime
from unittest.mock import patch

import pytest

from app.schemas.config_schema import ExternalFunctionConfig, TickProcessingContext
from app.services.external_function_executor import ExternalFunctionExecutor


class TestConcurrentExecution:
    """Test concurrent execution performance and limits"""

    @pytest.fixture
    def executor(self):
        """Create executor instance"""
        return ExternalFunctionExecutor()

    @pytest.fixture
    def sample_context(self):
        """Sample processing context"""
        return TickProcessingContext(
            instrument_key="NSE@RELIANCE@EQ",
            timestamp=datetime.now(),
            tick_data={
                "ltp": {"value": 2500.50, "currency": "INR"},
                "high": {"value": 2510.00},
                "low": {"value": 2490.00},
                "open": {"value": 2495.00},
                "volume": 1000000
            },
            aggregated_data={}
        )

    @pytest.fixture
    def fast_function_config(self):
        """Fast executing function config"""
        return ExternalFunctionConfig(
            name="fast_function",
            function_name="calculate_fast",
            function_path="test/fast_function.py",
            file_path="test/fast_function.py",
            parameters={"threshold": 0.05},
            timeout=2,
            memory_limit_mb=32
        )

    @pytest.fixture
    def slow_function_config(self):
        """Slow executing function config"""
        return ExternalFunctionConfig(
            name="slow_function",
            function_name="calculate_slow",
            function_path="test/slow_function.py",
            file_path="test/slow_function.py",
            parameters={"iterations": 1000},
            timeout=5,
            memory_limit_mb=64
        )

    @pytest.fixture
    def fast_function_code(self):
        """Fast executing function code"""
        return '''
def calculate_fast(tick_data, parameters):
    """Fast calculation"""
    threshold = parameters.get('threshold', 0.05)
    price = tick_data['ltp']['value']
    return {
        'signal': 'buy' if price > 2500 else 'sell',
        'price': price,
        'threshold': threshold
    }
'''

    @pytest.fixture
    def slow_function_code(self):
        """Slow executing function code (simulated computation)"""
        return '''
def calculate_slow(tick_data, parameters):
    """Slow calculation with simulated work"""
    iterations = parameters.get('iterations', 100)
    price = tick_data['ltp']['value']

    # Simulate computational work
    result = 0
    for i in range(iterations):
        result += i * 0.001

    return {
        'signal': 'computed',
        'price': price,
        'computation_result': result,
        'iterations': iterations
    }
'''

    # Basic Concurrent Execution Tests

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_concurrent_fast_executions(self, executor, sample_context, fast_function_config, fast_function_code):
        """Test concurrent execution of fast functions"""
        with patch.object(executor, '_load_function_securely', return_value=fast_function_code), patch.object(executor, '_validate_function_config'), patch.object(executor, '_validate_function_code'):
                concurrent_count = 10
                semaphore = asyncio.Semaphore(concurrent_count)

                start_time = time.time()

                tasks = [
                    executor.execute_single_function(
                        fast_function_config, sample_context, semaphore
                    )
                    for _ in range(concurrent_count)
                ]

                results = await asyncio.gather(*tasks, return_exceptions=True)

                execution_time = time.time() - start_time

                # Verify all executed successfully
                successful_results = [r for r in results if not isinstance(r, Exception)]
                assert len(successful_results) == concurrent_count

                # Performance check - should complete within reasonable time
                assert execution_time < 5.0, f"Concurrent execution too slow: {execution_time}s"

                # Verify all results are valid
                for result in successful_results:
                    assert 'signal' in result
                    assert 'price' in result

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_concurrent_execution_with_semaphore_limits(self, executor, sample_context, fast_function_config, fast_function_code):
        """Test semaphore properly limits concurrent executions"""
        with patch.object(executor, '_load_function_securely', return_value=fast_function_code), patch.object(executor, '_validate_function_config'), patch.object(executor, '_validate_function_code'):
                max_concurrent = 3
                total_functions = 10
                semaphore = asyncio.Semaphore(max_concurrent)

                # Track active executions
                active_count = 0
                max_active = 0
                lock = asyncio.Lock()

                async def tracked_execution():
                    nonlocal active_count, max_active

                    async with semaphore:
                        async with lock:
                            active_count += 1
                            max_active = max(max_active, active_count)

                        # Simulate work
                        await asyncio.sleep(0.1)

                        async with lock:
                            active_count -= 1

                start_time = time.time()

                tasks = [tracked_execution() for _ in range(total_functions)]
                await asyncio.gather(*tasks)

                execution_time = time.time() - start_time

                # Verify semaphore limited concurrent executions
                assert max_active <= max_concurrent, f"Semaphore failed: {max_active} > {max_concurrent}"

                # Should take longer due to serialization
                expected_min_time = (total_functions / max_concurrent) * 0.1 * 0.8  # 80% of theoretical minimum
                assert execution_time >= expected_min_time, f"Execution too fast: {execution_time}s < {expected_min_time}s"

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_mixed_speed_concurrent_execution(self, executor, sample_context, fast_function_config, slow_function_config, fast_function_code, slow_function_code):
        """Test concurrent execution with mixed fast/slow functions"""

        def load_function_side_effect(config):
            if config.name == "fast_function":
                return fast_function_code
            return slow_function_code

        with patch.object(executor, '_load_function_securely', side_effect=load_function_side_effect), patch.object(executor, '_validate_function_config'), patch.object(executor, '_validate_function_code'):
                configs = [fast_function_config] * 5 + [slow_function_config] * 3
                random.shuffle(configs)

                semaphore = asyncio.Semaphore(4)

                start_time = time.time()

                tasks = [
                    executor.execute_single_function(config, sample_context, semaphore)
                    for config in configs
                ]

                results = await asyncio.gather(*tasks, return_exceptions=True)

                execution_time = time.time() - start_time

                successful_results = [r for r in results if not isinstance(r, Exception)]
                assert len(successful_results) == len(configs)

                # Should complete within reasonable time (not sum of all slow functions)
                assert execution_time < 8.0, f"Mixed execution too slow: {execution_time}s"

    # Resource Stress Tests

    @pytest.mark.asyncio
    @pytest.mark.stress
    async def test_high_concurrency_stress(self, executor, sample_context, fast_function_config, fast_function_code):
        """Stress test with high concurrency"""
        with patch.object(executor, '_load_function_securely', return_value=fast_function_code), patch.object(executor, '_validate_function_config'), patch.object(executor, '_validate_function_code'):
                concurrent_count = 50
                semaphore = asyncio.Semaphore(concurrent_count)

                start_time = time.time()

                tasks = [
                    executor.execute_single_function(
                        fast_function_config, sample_context, semaphore
                    )
                    for _ in range(concurrent_count)
                ]

                results = await asyncio.gather(*tasks, return_exceptions=True)

                execution_time = time.time() - start_time

                # At least 80% should succeed
                successful_results = [r for r in results if not isinstance(r, Exception)]
                success_rate = len(successful_results) / len(results)
                assert success_rate >= 0.8, f"Low success rate under stress: {success_rate}"

                # Should complete within reasonable time
                assert execution_time < 15.0, f"Stress test too slow: {execution_time}s"

    @pytest.mark.asyncio
    @pytest.mark.stress
    async def test_memory_pressure_handling(self, executor, sample_context):
        """Test handling under memory pressure"""
        # Create memory-intensive function
        memory_intensive_config = ExternalFunctionConfig(
            name="memory_intensive",
            function_name="memory_hog",
            function_path="test/memory_hog.py",
            file_path="test/memory_hog.py",
            parameters={"data_size": 1000},
            timeout=5,
            memory_limit_mb=32  # Small limit to trigger pressure
        )

        memory_intensive_code = '''
def memory_hog(tick_data, parameters):
    """Function that uses significant memory"""
    data_size = parameters.get('data_size', 100)

    # Create large data structure
    large_list = list(range(data_size * 1000))

    return {
        'signal': 'memory_test',
        'data_size': len(large_list),
        'price': tick_data['ltp']['value']
    }
'''

        with patch.object(executor, '_load_function_securely', return_value=memory_intensive_code), patch.object(executor, '_validate_function_config'), patch.object(executor, '_validate_function_code'):
                concurrent_count = 5
                semaphore = asyncio.Semaphore(concurrent_count)

                tasks = [
                    executor.execute_single_function(
                        memory_intensive_config, sample_context, semaphore
                    )
                    for _ in range(concurrent_count)
                ]

                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Some should fail due to memory limits, but system should remain stable
                exceptions = [r for r in results if isinstance(r, Exception)]

                # Verify memory limit errors are properly caught
                memory_errors = [e for e in exceptions if "memory" in str(e).lower()]

                # At least some should fail due to memory pressure
                # This validates that memory limiting is working
                assert len(memory_errors) > 0, "Memory limiting not working"

    # Timeout and Error Handling

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_concurrent_timeout_handling(self, executor, sample_context):
        """Test concurrent timeout handling"""
        timeout_config = ExternalFunctionConfig(
            name="timeout_test",
            function_name="slow_function",
            function_path="test/timeout.py",
            file_path="test/timeout.py",
            parameters={},
            timeout=1,  # Very short timeout
            memory_limit_mb=32
        )

        timeout_code = '''
def slow_function(tick_data, parameters):
    """Function that will timeout"""
    import time
    time.sleep(2)  # Longer than timeout
    return {'signal': 'too_late'}
'''

        with patch.object(executor, '_load_function_securely', return_value=timeout_code), patch.object(executor, '_validate_function_config'), patch.object(executor, '_validate_function_code'):
                concurrent_count = 5
                semaphore = asyncio.Semaphore(concurrent_count)

                start_time = time.time()

                tasks = [
                    executor.execute_single_function(
                        timeout_config, sample_context, semaphore
                    )
                    for _ in range(concurrent_count)
                ]

                results = await asyncio.gather(*tasks, return_exceptions=True)

                execution_time = time.time() - start_time

                # All should fail with timeout
                timeout_exceptions = [r for r in results if isinstance(r, Exception) and "timeout" in str(r).lower()]
                assert len(timeout_exceptions) == concurrent_count

                # Should timeout quickly, not wait for functions to complete
                assert execution_time < 3.0, f"Timeout handling too slow: {execution_time}s"

    # Performance Benchmarks

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_execution_throughput(self, executor, sample_context, fast_function_config, fast_function_code):
        """Benchmark execution throughput"""
        with patch.object(executor, '_load_function_securely', return_value=fast_function_code), patch.object(executor, '_validate_function_config'), patch.object(executor, '_validate_function_code'):
                concurrency_levels = [1, 5, 10, 20]
                throughput_results = {}

                for concurrency in concurrency_levels:
                    semaphore = asyncio.Semaphore(concurrency)
                    execution_count = 20

                    start_time = time.time()

                    tasks = [
                        executor.execute_single_function(
                            fast_function_config, sample_context, semaphore
                        )
                        for _ in range(execution_count)
                    ]

                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    execution_time = time.time() - start_time
                    successful_count = len([r for r in results if not isinstance(r, Exception)])

                    throughput = successful_count / execution_time
                    throughput_results[concurrency] = {
                        'throughput': throughput,
                        'execution_time': execution_time,
                        'success_rate': successful_count / execution_count
                    }

                # Verify throughput increases with concurrency (up to a point)
                assert throughput_results[5]['throughput'] > throughput_results[1]['throughput']

                # Log results for analysis
                print("\nThroughput Benchmark Results:")
                for concurrency, metrics in throughput_results.items():
                    print(f"Concurrency {concurrency}: {metrics['throughput']:.2f} exec/sec, "
                          f"Success: {metrics['success_rate']:.2%}")

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_resource_utilization_monitoring(self, executor, sample_context, fast_function_config, fast_function_code):
        """Monitor resource utilization during concurrent execution"""
        import psutil

        with patch.object(executor, '_load_function_securely', return_value=fast_function_code), patch.object(executor, '_validate_function_config'), patch.object(executor, '_validate_function_code'):
                process = psutil.Process()
                start_memory = process.memory_info().rss / 1024 / 1024  # MB
                process.cpu_percent()

                # Run concurrent executions
                concurrent_count = 15
                semaphore = asyncio.Semaphore(concurrent_count)

                tasks = [
                    executor.execute_single_function(
                        fast_function_config, sample_context, semaphore
                    )
                    for _ in range(concurrent_count)
                ]

                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Check resource usage
                end_memory = process.memory_info().rss / 1024 / 1024  # MB
                end_cpu = process.cpu_percent()

                memory_increase = end_memory - start_memory

                # Memory usage should not increase dramatically
                assert memory_increase < 100, f"Excessive memory usage: {memory_increase}MB"

                # Most executions should succeed
                success_count = len([r for r in results if not isinstance(r, Exception)])
                success_rate = success_count / len(results)
                assert success_rate > 0.9, f"Low success rate: {success_rate}"

                print("\nResource Utilization:")
                print(f"Memory change: {memory_increase:.1f}MB")
                print(f"CPU usage: {end_cpu:.1f}%")
                print(f"Success rate: {success_rate:.2%}")

    # Resilience Tests

    @pytest.mark.asyncio
    @pytest.mark.resilience
    async def test_error_isolation(self, executor, sample_context, fast_function_config, fast_function_code):
        """Test that errors in one function don't affect others"""
        error_config = ExternalFunctionConfig(
            name="error_function",
            function_name="error_function",
            function_path="test/error.py",
            file_path="test/error.py",
            parameters={},
            timeout=5,
            memory_limit_mb=32
        )

        error_code = '''
def error_function(tick_data, parameters):
    """Function that always errors"""
    raise ValueError("Intentional error for testing")
'''

        def load_function_side_effect(config):
            if config.name == "error_function":
                return error_code
            return fast_function_code

        with patch.object(executor, '_load_function_securely', side_effect=load_function_side_effect), patch.object(executor, '_validate_function_config'), patch.object(executor, '_validate_function_code'):
                configs = [fast_function_config] * 5 + [error_config] * 2
                random.shuffle(configs)

                semaphore = asyncio.Semaphore(4)

                tasks = [
                    executor.execute_single_function(config, sample_context, semaphore)
                    for config in configs
                ]

                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Count successes and errors
                successes = [r for r in results if not isinstance(r, Exception)]
                errors = [r for r in results if isinstance(r, Exception)]

                # Verify error isolation - good functions should succeed
                assert len(successes) == 5, f"Good functions failed: {len(successes)}/5"
                assert len(errors) == 2, f"Error functions didn't fail: {len(errors)}/2"

    @pytest.mark.asyncio
    @pytest.mark.resilience
    async def test_system_recovery_after_stress(self, executor, sample_context, fast_function_config, fast_function_code):
        """Test system recovery after stress conditions"""
        with patch.object(executor, '_load_function_securely', return_value=fast_function_code), patch.object(executor, '_validate_function_config'), patch.object(executor, '_validate_function_code'):
                stress_concurrent_count = 30
                stress_semaphore = asyncio.Semaphore(stress_concurrent_count)

                stress_tasks = [
                    executor.execute_single_function(
                        fast_function_config, sample_context, stress_semaphore
                    )
                    for _ in range(stress_concurrent_count)
                ]

                await asyncio.gather(*stress_tasks, return_exceptions=True)

                # Brief recovery period
                await asyncio.sleep(1)

                # Phase 2: Normal load after stress
                normal_concurrent_count = 5
                normal_semaphore = asyncio.Semaphore(normal_concurrent_count)

                start_time = time.time()

                normal_tasks = [
                    executor.execute_single_function(
                        fast_function_config, sample_context, normal_semaphore
                    )
                    for _ in range(normal_concurrent_count)
                ]

                normal_results = await asyncio.gather(*normal_tasks, return_exceptions=True)

                recovery_time = time.time() - start_time

                # Verify system recovered and performs normally
                normal_successes = [r for r in normal_results if not isinstance(r, Exception)]
                normal_success_rate = len(normal_successes) / len(normal_results)

                assert normal_success_rate >= 0.9, f"Poor recovery performance: {normal_success_rate}"
                assert recovery_time < 3.0, f"Slow recovery time: {recovery_time}s"
