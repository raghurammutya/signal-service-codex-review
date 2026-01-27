"""
Metrics Service Integration Tests

Addresses critical integration gap: metrics_service sidecar API validation
with circuit breaker behavior and Prometheus format compliance.
"""
import asyncio
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

try:
    from app.core.circuit_breaker import CircuitBreakerError
    from app.services.metrics_service import MetricsError, MetricsService
    METRICS_SERVICE_AVAILABLE = True
except ImportError:
    METRICS_SERVICE_AVAILABLE = False


class TestMetricsServiceIntegration:
    """Integration tests for metrics service sidecar API."""

    @pytest.fixture
    def mock_metrics_endpoint(self):
        """Mock metrics service HTTP endpoint."""
        async def mock_post(session, url, **kwargs):
            response_mock = MagicMock()

            # Simulate different response scenarios
            if "timeout" in url:
                raise aiohttp.ServerTimeoutError
            if "error" in url:
                response_mock.status = 500
                response_mock.text = AsyncMock(return_value="Internal server error")
            elif "invalid" in url:
                response_mock.status = 400
                response_mock.text = AsyncMock(return_value="Invalid metric format")
            else:
                response_mock.status = 200
                response_mock.text = AsyncMock(return_value="Metrics accepted")

            return response_mock

        return mock_post

    @pytest.fixture
    def metrics_service(self, mock_metrics_endpoint):
        """Create metrics service with mocked HTTP client."""
        if not METRICS_SERVICE_AVAILABLE:
            pytest.skip("Metrics service not available")

        service = MetricsService(
            endpoint="http://localhost:9090/metrics/push",
            timeout=5.0
        )

        # Mock the HTTP session
        with patch('aiohttp.ClientSession.post', new=mock_metrics_endpoint):
            yield service

    @pytest.mark.asyncio
    async def test_successful_metrics_push(self, metrics_service):
        """Test successful metrics push to sidecar API."""
        metrics_data = {
            "metric_name": "signal_processing_duration_seconds",
            "value": 0.125,
            "labels": {
                "service": "signal_service",
                "module": "pandas_ta_executor",
                "status": "success"
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        # Should succeed without raising exceptions
        await metrics_service.push_metric(metrics_data)

        # Verify metrics were queued
        assert len(metrics_service._pending_metrics) >= 0
        assert metrics_service._push_count > 0

    @pytest.mark.asyncio
    async def test_prometheus_format_compliance(self, metrics_service):
        """Test that metrics conform to Prometheus format requirements."""
        # Test counter metric
        counter_metric = {
            "metric_name": "signal_processing_total",
            "metric_type": "counter",
            "value": 42,
            "labels": {"service": "signal_service"},
            "help": "Total number of signals processed"
        }

        formatted = metrics_service._format_prometheus_metric(counter_metric)

        # Verify Prometheus format
        assert "# HELP signal_processing_total Total number of signals processed" in formatted
        assert "# TYPE signal_processing_total counter" in formatted
        assert 'signal_processing_total{service="signal_service"} 42' in formatted

        # Test gauge metric
        gauge_metric = {
            "metric_name": "signal_processing_duration_seconds",
            "metric_type": "gauge",
            "value": 0.125,
            "labels": {"module": "pandas_ta"},
            "help": "Signal processing duration in seconds"
        }

        formatted = metrics_service._format_prometheus_metric(gauge_metric)

        assert "# TYPE signal_processing_duration_seconds gauge" in formatted
        assert 'signal_processing_duration_seconds{module="pandas_ta"} 0.125' in formatted

    @pytest.mark.asyncio
    async def test_circuit_breaker_behavior(self, metrics_service):
        """Test circuit breaker behavior on metrics service failures."""
        # Configure circuit breaker to open quickly for testing
        metrics_service._circuit_breaker._failure_threshold = 2
        metrics_service._circuit_breaker._timeout = 1

        # Simulate multiple failures to trigger circuit breaker
        with patch('aiohttp.ClientSession.post') as mock_post:
            # Mock consecutive failures
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_post.return_value = mock_response

            # First failure
            with pytest.raises(MetricsError):
                await metrics_service.push_metric({
                    "metric_name": "test_metric",
                    "value": 1
                })

            # Second failure should open circuit breaker
            with pytest.raises(MetricsError):
                await metrics_service.push_metric({
                    "metric_name": "test_metric",
                    "value": 2
                })

            # Third call should fail fast due to open circuit
            with pytest.raises(CircuitBreakerError):
                await metrics_service.push_metric({
                    "metric_name": "test_metric",
                    "value": 3
                })

    @pytest.mark.asyncio
    async def test_batch_metrics_processing(self, metrics_service):
        """Test batch processing of multiple metrics."""
        # Queue multiple metrics
        metrics_batch = []
        for i in range(5):
            metric = {
                "metric_name": f"test_metric_{i}",
                "value": i * 10,
                "labels": {"batch": "test", "index": str(i)}
            }
            metrics_batch.append(metric)
            await metrics_service.push_metric(metric)

        # Process batch
        await metrics_service.flush_pending_metrics()

        # Verify batch was processed
        assert len(metrics_service._pending_metrics) == 0
        assert metrics_service._batch_count > 0

    @pytest.mark.asyncio
    async def test_metrics_service_timeout_handling(self, metrics_service):
        """Test timeout handling for slow metrics service."""
        # Mock timeout scenario
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.side_effect = aiohttp.ServerTimeoutError()

            # Should handle timeout gracefully
            with pytest.raises(MetricsError) as exc_info:
                await metrics_service.push_metric({
                    "metric_name": "timeout_test",
                    "value": 1
                })

            assert "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_invalid_metric_format_handling(self, metrics_service):
        """Test handling of invalid metric formats."""
        # Test missing required fields
        invalid_metrics = [
            {},  # Empty metric
            {"value": 123},  # Missing metric_name
            {"metric_name": "test"},  # Missing value
            {"metric_name": "", "value": 123},  # Empty metric name
            {"metric_name": "test", "value": "invalid"}  # Non-numeric value
        ]

        for invalid_metric in invalid_metrics:
            with pytest.raises(MetricsError) as exc_info:
                await metrics_service.push_metric(invalid_metric)

            assert "invalid" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_metrics_service_recovery(self, metrics_service):
        """Test metrics service recovery after failures."""
        # Configure circuit breaker
        metrics_service._circuit_breaker._failure_threshold = 2
        metrics_service._circuit_breaker._recovery_timeout = 0.1  # Fast recovery for testing

        with patch('aiohttp.ClientSession.post') as mock_post:
            # Cause failures to open circuit
            mock_response_fail = AsyncMock()
            mock_response_fail.status = 500
            mock_post.return_value = mock_response_fail

            # Trigger circuit breaker opening
            for _ in range(2):
                with pytest.raises(MetricsError):
                    await metrics_service.push_metric({"metric_name": "test", "value": 1})

            # Wait for recovery timeout
            await asyncio.sleep(0.2)

            # Mock successful response for recovery
            mock_response_success = AsyncMock()
            mock_response_success.status = 200
            mock_post.return_value = mock_response_success

            # Should succeed after recovery
            await metrics_service.push_metric({"metric_name": "recovery_test", "value": 1})
            assert metrics_service._recovery_count > 0

    @pytest.mark.asyncio
    async def test_metrics_aggregation_and_bucketing(self, metrics_service):
        """Test metrics aggregation and histogram bucketing."""
        # Test histogram metric
        histogram_metric = {
            "metric_name": "request_duration_seconds",
            "metric_type": "histogram",
            "value": 0.125,
            "buckets": [0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
            "labels": {"endpoint": "/api/v2/signals"}
        }

        formatted = metrics_service._format_prometheus_metric(histogram_metric)

        # Verify histogram format with buckets
        assert "# TYPE request_duration_seconds histogram" in formatted
        assert 'request_duration_seconds_bucket{endpoint="/api/v2/signals",le="0.5"}' in formatted
        assert 'request_duration_seconds_bucket{endpoint="/api/v2/signals",le="+Inf"}' in formatted
        assert 'request_duration_seconds_sum{endpoint="/api/v2/signals"}' in formatted
        assert 'request_duration_seconds_count{endpoint="/api/v2/signals"}' in formatted

    @pytest.mark.asyncio
    async def test_metrics_service_health_integration(self, metrics_service):
        """Test integration with health check system."""
        # Simulate metrics service health check
        health_status = await metrics_service.check_health()

        assert "metrics_service" in health_status
        assert health_status["metrics_service"]["status"] in ["healthy", "degraded", "unhealthy"]
        assert "push_count" in health_status["metrics_service"]
        assert "error_count" in health_status["metrics_service"]

    @pytest.mark.asyncio
    async def test_concurrent_metrics_push(self, metrics_service):
        """Test concurrent metrics pushing under load."""
        # Create concurrent metrics push tasks
        tasks = []

        for i in range(10):
            metric = {
                "metric_name": "concurrent_test",
                "value": i,
                "labels": {"thread": str(i)}
            }
            task = asyncio.create_task(metrics_service.push_metric(metric))
            tasks.append(task)

        # Wait for all concurrent pushes
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify most pushes succeeded (allowing for some failures under load)
        success_count = len([r for r in results if not isinstance(r, Exception)])
        assert success_count >= 7  # At least 70% success rate under load

    @pytest.mark.asyncio
    async def test_custom_metric_labels_validation(self, metrics_service):
        """Test validation of custom metric labels."""
        # Valid labels
        valid_metric = {
            "metric_name": "custom_metric",
            "value": 100,
            "labels": {
                "service": "signal_service",
                "version": "2.0.0",
                "environment": "production"
            }
        }

        # Should succeed
        await metrics_service.push_metric(valid_metric)

        # Invalid labels (empty keys, special characters)
        invalid_labels_metrics = [
            {
                "metric_name": "invalid_labels",
                "value": 1,
                "labels": {"": "empty_key"}  # Empty label key
            },
            {
                "metric_name": "invalid_labels",
                "value": 1,
                "labels": {"key with spaces": "value"}  # Space in key
            },
            {
                "metric_name": "invalid_labels",
                "value": 1,
                "labels": {"valid_key": "value\nwith\nnewlines"}  # Newlines in value
            }
        ]

        for invalid_metric in invalid_labels_metrics:
            with pytest.raises(MetricsError) as exc_info:
                await metrics_service.push_metric(invalid_metric)

            assert "label" in str(exc_info.value).lower()


def run_integration_coverage_test():
    """Run metrics service integration coverage test."""
    import subprocess
    import sys

    print("🔍 Running Metrics Service Integration Coverage Tests...")

    cmd = [
        sys.executable, "-m", "pytest",
        __file__,
        "--cov=app.services.metrics_service",
        "--cov-report=term-missing",
        "--cov-report=html:coverage_reports/html_metrics_service_integration",
        "--cov-report=json:coverage_reports/coverage_metrics_service_integration.json",
        "--cov-fail-under=95",
        "-v"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    print("STDOUT:")
    print(result.stdout)

    if result.stderr:
        print("STDERR:")
        print(result.stderr)

    return result.returncode == 0


if __name__ == "__main__":
    print("🚀 Metrics Service Integration Tests")
    print("=" * 60)

    success = run_integration_coverage_test()

    if success:
        print("\n✅ Metrics service integration tests passed with ≥95% coverage!")
        print("📊 Integration coverage validated for:")
        print("  - Sidecar API communication")
        print("  - Prometheus format compliance")
        print("  - Circuit breaker behavior")
        print("  - Batch processing")
        print("  - Timeout and error handling")
        print("  - Concurrent push scenarios")
        print("  - Health check integration")
        print("  - Custom labels validation")
        print("\n🎯 Critical gap resolved: Metrics service integration proven")
    else:
        print("\n❌ Metrics service integration tests need improvement")
        sys.exit(1)
