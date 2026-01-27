"""
Metrics Service Contract Integration Tests

Tests the metrics service integration and contract compliance to ensure proper
behavior under various conditions including circuit breaker integration,
concurrent load, and Redis export reliability.
"""
import asyncio
import time
from unittest.mock import AsyncMock

import pytest


# Mock Redis for testing
@pytest.fixture
def mock_redis():
    """Mock Redis client for metrics export testing."""
    mock_redis = AsyncMock()
    mock_redis.setex = AsyncMock()
    mock_redis.get = AsyncMock()
    mock_redis.info = AsyncMock(return_value={'keyspace_hits': 100, 'keyspace_misses': 10})
    return mock_redis

@pytest.fixture
def metrics_collector(mock_redis):
    """Create metrics collector with mocked Redis."""
    from app.services.metrics_service import MetricsCollector

    collector = MetricsCollector()
    collector.redis_client = mock_redis
    return collector

class TestMetricsServiceContract:
    """Test metrics service contract compliance and integration."""

    @pytest.mark.integration
    async def test_request_metrics_recording(self, metrics_collector):
        """Test that request metrics are properly recorded and aggregated."""
        # Record multiple requests
        test_requests = [
            ("GET", "/api/v2/signals/realtime", 150.5, 200),
            ("POST", "/api/v2/signals/batch", 320.2, 200),
            ("GET", "/api/v2/indicators", 89.1, 200),
            ("GET", "/api/v2/signals/realtime", 145.8, 500),  # Error case
            ("POST", "/api/v2/signals/batch", 1200.0, 503),  # Slow error
        ]

        for _method, endpoint, duration, status_code in test_requests:
            metrics_collector.record_request(endpoint, duration, status_code)

        # Verify metrics aggregation
        request_rate = metrics_collector.get_request_rate()
        error_rate = metrics_collector.get_error_rate()
        avg_response_time = metrics_collector.get_average_response_time()

        assert request_rate >= 0  # Should have positive request rate
        assert 0 <= error_rate <= 1  # Error rate should be between 0 and 1
        assert avg_response_time > 0  # Should have positive response time

        # Check error rate calculation (2 errors out of 5 requests = 40%)
        assert abs(error_rate - 0.4) < 0.01

    @pytest.mark.integration
    async def test_circuit_breaker_metrics_tracking(self, metrics_collector):
        """Test circuit breaker event tracking and metrics."""
        # Record circuit breaker events
        breaker_events = [
            ("redis_export", "call_failure", {"error": "Connection refused"}),
            ("ticker_service", "call_failure", {"error": "Timeout"}),
            ("ticker_service", "call_failure", {"error": "Service unavailable"}),
            ("ticker_service", "open", {"failure_count": 3}),
            ("redis_export", "call_success", {"retry_count": 1}),
            ("ticker_service", "close", {"success_count": 5})
        ]

        for breaker_type, event, metrics in breaker_events:
            metrics_collector.record_circuit_breaker_event(breaker_type, event, metrics)

        # Verify circuit breaker metrics are tracked
        assert "redis_export" in metrics_collector.circuit_breaker_metrics
        assert "ticker_service" in metrics_collector.circuit_breaker_metrics

        # Check event recording
        redis_events = list(metrics_collector.circuit_breaker_metrics["redis_export"])
        ticker_events = list(metrics_collector.circuit_breaker_metrics["ticker_service"])

        assert len(redis_events) == 2  # failure + success
        assert len(ticker_events) == 4  # 2 failures + open + close

        # Verify event data integrity
        assert redis_events[0]["event"] == "call_failure"
        assert ticker_events[-1]["event"] == "close"

    @pytest.mark.integration
    async def test_greeks_performance_tracking(self, metrics_collector):
        """Test Greeks calculation performance metrics."""
        # Record Greeks calculations
        greeks_calculations = [
            ("delta", 45.2, True),
            ("gamma", 78.5, True),
            ("theta", 23.1, True),
            ("vega", 156.8, False),  # Failure case
            ("delta", 41.7, True),
            ("rho", 89.3, True)
        ]

        for calc_type, duration_ms, success in greeks_calculations:
            metrics_collector.record_greeks_calculation(calc_type, duration_ms, success)

        # Get Greeks performance metrics
        greeks_metrics = metrics_collector.get_greeks_performance_metrics()

        assert greeks_metrics["total_calculations"] == 6
        assert 0.8 <= greeks_metrics["success_rate"] <= 0.9  # 5/6 = 83.3%
        assert greeks_metrics["average_duration_ms"] > 0
        assert greeks_metrics["calculations_per_minute"] >= 0

        # Check breakdown by type
        breakdown = greeks_metrics["breakdown_by_type"]
        assert "delta" in breakdown
        assert "vega" in breakdown

        # Delta should have 2 calculations, both successful
        assert breakdown["delta"]["count"] == 2
        assert breakdown["delta"]["error_rate"] == 0.0

        # Vega should have 1 calculation, 1 failure
        assert breakdown["vega"]["count"] == 1
        assert breakdown["vega"]["error_rate"] == 1.0

    @pytest.mark.integration
    async def test_cache_performance_metrics(self, metrics_collector):
        """Test cache performance tracking."""
        # Record cache operations
        cache_operations = [
            ("historical_data", True),   # Hit
            ("historical_data", True),   # Hit
            ("historical_data", False),  # Miss
            ("moneyness_cache", True),   # Hit
            ("moneyness_cache", False),  # Miss
            ("moneyness_cache", False),  # Miss
        ]

        for cache_type, hit in cache_operations:
            metrics_collector.record_cache_operation(cache_type, hit)

        # Get cache performance metrics
        cache_metrics = metrics_collector.get_cache_performance_metrics()

        assert "historical_data" in cache_metrics
        assert "moneyness_cache" in cache_metrics

        # Historical data: 2 hits, 1 miss = 66.7% hit rate
        historical_metrics = cache_metrics["historical_data"]
        assert abs(historical_metrics["hit_rate"] - 0.667) < 0.01
        assert historical_metrics["total_operations"] == 3

        # Moneyness cache: 1 hit, 2 misses = 33.3% hit rate
        moneyness_metrics = cache_metrics["moneyness_cache"]
        assert abs(moneyness_metrics["hit_rate"] - 0.333) < 0.01
        assert moneyness_metrics["total_operations"] == 3

    @pytest.mark.integration
    async def test_health_score_calculation(self, metrics_collector):
        """Test overall health score calculation based on metrics."""
        # Set up metrics for health score calculation
        test_metrics = [
            ("GET", "/health", 50.0, 200),    # Fast, successful
            ("GET", "/health", 80.0, 200),    # Fast, successful
            ("POST", "/api/signals", 150.0, 200),  # Normal, successful
            ("GET", "/metrics", 500.0, 500),  # Slow, error
            ("GET", "/api/data", 1000.0, 503), # Very slow, error
        ]

        for _method, endpoint, duration, status_code in test_metrics:
            metrics_collector.record_request(endpoint, duration, status_code)

        # Calculate health score
        health_score = metrics_collector.get_health_score()

        # Verify health score structure
        assert "overall" in health_score
        assert "scores" in health_score
        assert "breakdown" in health_score

        # Check component scores
        scores = health_score["scores"]
        assert "error_rate" in scores
        assert "response_time" in scores
        assert "greeks_performance" in scores
        assert "system_resources" in scores

        # Overall score should be between 0 and 100
        overall_score = health_score["overall"]
        assert 0 <= overall_score <= 100

        # With 40% error rate and slow responses, score should be degraded
        assert overall_score < 80  # Should indicate degraded health

    @pytest.mark.integration
    async def test_redis_export_with_circuit_breaker(self, metrics_collector):
        """Test Redis export with circuit breaker integration."""
        # Test successful export
        await metrics_collector.export_metrics_to_redis(300)

        # Verify Redis setex was called
        metrics_collector.redis_client.setex.assert_called()

        # Test export failure and retry logic
        metrics_collector.redis_client.setex.side_effect = [
            Exception("Connection refused"),  # First attempt fails
            Exception("Timeout"),             # Second attempt fails
            None                              # Third attempt succeeds
        ]

        # Should trigger retry logic
        await metrics_collector.export_metrics_to_redis(300)

        # Verify circuit breaker events were recorded
        assert "redis_export" in metrics_collector.circuit_breaker_metrics

        # Check that retries were attempted
        redis_events = list(metrics_collector.circuit_breaker_metrics["redis_export"])
        failure_events = [e for e in redis_events if e["event"] == "call_failure"]
        success_events = [e for e in redis_events if e["event"] == "call_success"]

        assert len(failure_events) >= 1  # At least one failure recorded
        assert len(success_events) >= 1  # Success after retry

    @pytest.mark.integration
    async def test_concurrent_metrics_collection(self, metrics_collector):
        """Test metrics collection under concurrent load."""
        async def record_concurrent_requests():
            """Simulate concurrent request recording."""
            tasks = []
            for i in range(100):
                endpoint = f"/api/test/{i % 10}"
                duration = 50.0 + (i % 200)  # Variable response times
                status_code = 200 if i % 10 != 0 else 500  # 10% error rate

                # Create task for concurrent execution
                task = asyncio.create_task(
                    asyncio.sleep(0.001)  # Simulate async request recording
                )
                tasks.append((task, endpoint, duration, status_code))

            # Wait for all tasks and record metrics
            for task, endpoint, duration, status_code in tasks:
                await task
                metrics_collector.record_request(endpoint, duration, status_code)

        # Run concurrent metrics collection
        start_time = time.time()
        await record_concurrent_requests()
        end_time = time.time()

        # Verify metrics were recorded correctly
        request_rate = metrics_collector.get_request_rate()
        error_rate = metrics_collector.get_error_rate()

        assert request_rate > 0
        assert abs(error_rate - 0.1) < 0.02  # Should be ~10% error rate

        # Performance check - should handle 100 concurrent metrics quickly
        processing_time = end_time - start_time
        assert processing_time < 5.0  # Should complete within 5 seconds


class TestMetricsServiceReliability:
    """Test metrics service reliability and error handling."""

    @pytest.mark.integration
    async def test_redis_unavailable_graceful_handling(self, metrics_collector):
        """Test graceful handling when Redis is unavailable."""
        # Simulate Redis being unavailable
        metrics_collector.redis_client = None

        # Should not raise exceptions
        try:
            await metrics_collector.export_metrics_to_redis(300)
            # Should handle gracefully without Redis
        except Exception as e:
            pytest.fail(f"Should handle Redis unavailability gracefully: {e}")

        # Metrics collection should still work
        metrics_collector.record_request("/test", 100.0, 200)

        request_rate = metrics_collector.get_request_rate()
        assert request_rate >= 0

    @pytest.mark.integration
    async def test_metrics_data_integrity_under_load(self, metrics_collector):
        """Test data integrity under high load conditions."""
        # Record large number of metrics rapidly
        for i in range(1000):
            endpoint = "/load-test"
            duration = 100.0 + (i % 50)
            status_code = 200 if i % 20 != 0 else 500  # 5% error rate

            metrics_collector.record_request(endpoint, duration, status_code)

            # Also record Greeks calculations
            if i % 10 == 0:
                metrics_collector.record_greeks_calculation("delta", 45.0, True)

        # Verify data integrity
        error_rate = metrics_collector.get_error_rate()
        avg_response_time = metrics_collector.get_average_response_time()
        greeks_metrics = metrics_collector.get_greeks_performance_metrics()

        # Error rate should be approximately 5%
        assert abs(error_rate - 0.05) < 0.01

        # Response time should be reasonable
        assert 100 <= avg_response_time <= 150

        # Greeks calculations should be tracked
        assert greeks_metrics["total_calculations"] == 100  # Every 10th request


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
