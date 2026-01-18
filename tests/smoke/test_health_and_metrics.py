"""
Smoke Tests: Health and Metrics Validation

Fast-fail tests to validate basic service health, metrics export,
and critical endpoint availability before running full test suite.
"""

import pytest
import asyncio
import time
from httpx import AsyncClient
import os


class TestHealthEndpoints:
    """Test basic health and readiness endpoints."""
    
    @pytest.mark.asyncio
    async def test_service_health(self):
        """Test service health endpoint responds correctly."""
        async with AsyncClient(base_url="http://localhost:8003") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "service" in data
            assert data["service"] == "signal_service"
    
    @pytest.mark.asyncio 
    async def test_admin_health_detailed(self):
        """Test detailed admin health status."""
        async with AsyncClient(base_url="http://localhost:8003") as client:
            response = await client.get("/api/v2/admin/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            # Validate component health
            assert "database" in data
            assert "redis" in data
            assert "signal_processor" in data
    
    @pytest.mark.asyncio
    async def test_health_response_time_sla(self):
        """Test health endpoint meets p95 ≤ 100ms SLA."""
        async with AsyncClient(base_url="http://localhost:8003") as client:
            response_times = []
            
            # Sample 20 requests
            for _ in range(20):
                start_time = time.time()
                response = await client.get("/health")
                end_time = time.time()
                
                assert response.status_code == 200
                response_times.append((end_time - start_time) * 1000)  # Convert to ms
            
            # Check p95 SLA
            response_times.sort()
            p95_index = int(0.95 * len(response_times))
            p95_latency = response_times[p95_index]
            
            assert p95_latency <= 100, f"Health endpoint p95 {p95_latency:.2f}ms exceeds 100ms SLA"


class TestMetricsExport:
    """Test Prometheus metrics export and parsing."""
    
    @pytest.mark.asyncio
    async def test_metrics_endpoint_available(self):
        """Test metrics endpoint is available and parseable."""
        async with AsyncClient(base_url="http://localhost:8003") as client:
            response = await client.get("/metrics")
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/plain; charset=utf-8"
    
    @pytest.mark.asyncio
    async def test_metrics_prometheus_format(self):
        """Test metrics are in valid Prometheus format.""" 
        async with AsyncClient(base_url="http://localhost:8003") as client:
            response = await client.get("/metrics")
            assert response.status_code == 200
            
            metrics_text = response.text
            
            # Basic Prometheus format validation
            assert "# HELP" in metrics_text
            assert "# TYPE" in metrics_text
            assert "signal_service_health" in metrics_text
            
            # Validate no syntax errors (basic checks)
            lines = metrics_text.strip().split('\n')
            for line in lines:
                if line.startswith('#'):
                    continue
                if line.strip() == "":
                    continue
                # Should have metric_name value format
                assert ' ' in line, f"Invalid metric line: {line}"
    
    @pytest.mark.asyncio
    async def test_essential_metrics_present(self):
        """Test essential metrics are exported."""
        async with AsyncClient(base_url="http://localhost:8003") as client:
            response = await client.get("/metrics")
            assert response.status_code == 200
            
            metrics_text = response.text
            
            # Essential metrics that should always be present
            essential_metrics = [
                "signal_service_health",
                "signal_service_active_subscriptions"
            ]
            
            for metric in essential_metrics:
                assert metric in metrics_text, f"Essential metric missing: {metric}"
    
    @pytest.mark.asyncio
    async def test_metrics_response_time_sla(self):
        """Test metrics endpoint meets p95 ≤ 150ms SLA."""
        async with AsyncClient(base_url="http://localhost:8003") as client:
            response_times = []
            
            # Sample 20 requests
            for _ in range(20):
                start_time = time.time()
                response = await client.get("/metrics")
                end_time = time.time()
                
                assert response.status_code == 200
                response_times.append((end_time - start_time) * 1000)  # Convert to ms
            
            # Check p95 SLA
            response_times.sort()
            p95_index = int(0.95 * len(response_times))
            p95_latency = response_times[p95_index]
            
            assert p95_latency <= 150, f"Metrics endpoint p95 {p95_latency:.2f}ms exceeds 150ms SLA"


class TestHotReloadSmokeTest:
    """Smoke tests for hot reload system status."""
    
    @pytest.mark.asyncio
    async def test_hot_reload_disabled_by_default(self):
        """Test hot reload is disabled by default."""
        async with AsyncClient(base_url="http://localhost:8003") as client:
            response = await client.get("/api/v2/admin/hot-reload/status")
            assert response.status_code == 200
            data = response.json()
            
            # Hot reload should be disabled by default
            expected_disabled = os.getenv("ENABLE_HOT_RELOAD", "false").lower() == "false"
            if expected_disabled:
                assert data["status"] == "disabled" or data["status"] == "error"
            
            # Statistics should show not initialized by default
            if "statistics" in data:
                stats = data["statistics"]
                assert stats.get("initialized", True) == False
    
    @pytest.mark.asyncio 
    async def test_hot_reload_health_monitoring(self):
        """Test hot reload health monitoring is available."""
        async with AsyncClient(base_url="http://localhost:8003") as client:
            response = await client.get("/api/v2/admin/hot-reload/health")
            assert response.status_code == 200
            data = response.json()
            
            assert "status" in data
            assert "hot_reload_health" in data
            
            # Should have basic health structure
            health = data["hot_reload_health"]
            assert "hot_reload_enabled" in health


class TestServiceStartupValidation:
    """Validate service startup state and configuration."""
    
    def test_environment_variables_set(self):
        """Test required environment variables are configured."""
        required_vars = [
            "ENVIRONMENT",
            "CONFIG_SERVICE_URL", 
            "SERVICE_NAME"
        ]
        
        for var in required_vars:
            value = os.getenv(var)
            assert value is not None, f"Required environment variable {var} not set"
            assert value.strip() != "", f"Required environment variable {var} is empty"
    
    def test_hot_reload_default_configuration(self):
        """Test hot reload defaults to disabled."""
        hot_reload_setting = os.getenv("ENABLE_HOT_RELOAD", "false")
        assert hot_reload_setting.lower() == "false", \
            "Hot reload should be disabled by default in production"
    
    def test_config_service_url_security(self):
        """Test config service URL is localhost only."""
        config_url = os.getenv("CONFIG_SERVICE_URL", "")
        
        # Should be localhost only for security
        assert "localhost" in config_url or "127.0.0.1" in config_url, \
            "Config service URL should be localhost only for security"
        
        # Should not contain external URLs
        forbidden_patterns = ["stocksblitz.in", "5.223.52.98"]
        for pattern in forbidden_patterns:
            assert pattern not in config_url, \
                f"Config service URL contains forbidden external reference: {pattern}"


@pytest.fixture(scope="session")
def service_startup_check():
    """Ensure service is running before tests."""
    import requests
    import time
    
    max_retries = 30
    for attempt in range(max_retries):
        try:
            response = requests.get("http://localhost:8003/health", timeout=5)
            if response.status_code == 200:
                return True
        except (requests.ConnectionError, requests.Timeout):
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            else:
                pytest.fail("Service not available after 60 seconds")
    
    return False


class TestSmokeTestExecution:
    """Meta-test to validate smoke test execution."""
    
    def test_service_availability(self, service_startup_check):
        """Test service is available for testing."""
        assert service_startup_check, "Service must be running for smoke tests"
    
    @pytest.mark.asyncio
    async def test_smoke_test_performance(self):
        """Test smoke tests complete within reasonable time."""
        start_time = time.time()
        
        # Run basic health check
        async with AsyncClient(base_url="http://localhost:8003") as client:
            response = await client.get("/health")
            assert response.status_code == 200
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Smoke tests should be very fast
        assert execution_time < 5.0, f"Smoke test took {execution_time:.2f}s, should be <5s"


if __name__ == "__main__":
    import subprocess
    import sys
    
    print("🚀 Running Signal Service Smoke Tests")
    print("===================================")
    
    result = subprocess.run([
        sys.executable, '-m', 'pytest', 
        __file__, 
        '-v', '--tb=short'
    ], capture_output=True, text=True)
    
    print("STDOUT:")
    print(result.stdout)
    
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
    
    if result.returncode == 0:
        print("✅ Smoke tests passed - service ready for full testing")
    else:
        print("❌ Smoke tests failed - investigate before proceeding")
        sys.exit(1)