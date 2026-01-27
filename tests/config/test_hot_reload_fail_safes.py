"""
Hot Reload Fail-Safe and Observability Tests

SECURITY COMPLIANT tests for circuit breaker, kill switch, schema validation,
rollback mechanisms, and comprehensive observability features.
"""
import asyncio
import os

# Add project root to path for imports
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TestCircuitBreaker:
    """Test circuit breaker implementation for hot reload operations."""

    def test_circuit_breaker_initialization(self):
        """Test circuit breaker proper initialization."""
        from app.core.hot_config import CircuitBreaker, CircuitBreakerState

        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=300)

        assert breaker._failure_threshold == 5
        assert breaker._recovery_timeout == 300
        assert breaker._failure_count == 0
        assert breaker.get_state() == CircuitBreakerState.CLOSED
        assert not breaker.is_open()

    def test_circuit_breaker_failure_threshold(self):
        """Test circuit breaker opens after failure threshold."""
        from app.core.hot_config import CircuitBreaker, CircuitBreakerState

        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

        # Record failures up to threshold
        for _i in range(3):
            breaker.record_failure()

        # Should be open after threshold failures
        assert breaker.get_state() == CircuitBreakerState.OPEN
        assert breaker.is_open()
        assert breaker._failure_count == 3

    def test_circuit_breaker_recovery(self):
        """Test circuit breaker recovery to half-open state."""
        from app.core.hot_config import CircuitBreaker, CircuitBreakerState

        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)  # 1 second timeout

        # Trip the breaker
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.get_state() == CircuitBreakerState.OPEN

        # Mock time passage for recovery
        breaker._next_attempt_time = datetime.now() - timedelta(seconds=2)

        # Should transition to half-open
        assert not breaker.is_open()
        assert breaker.get_state() == CircuitBreakerState.HALF_OPEN

    def test_circuit_breaker_half_open_success(self):
        """Test circuit breaker reset on successful half-open calls."""
        from app.core.hot_config import CircuitBreaker, CircuitBreakerState

        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1, half_open_max_calls=2)

        # Trip and transition to half-open
        breaker.record_failure()
        breaker.record_failure()
        breaker._next_attempt_time = datetime.now() - timedelta(seconds=2)
        breaker.is_open()  # Trigger state update

        # Record successful calls
        breaker.record_success()
        breaker.record_success()

        # Should be closed again
        assert breaker.get_state() == CircuitBreakerState.CLOSED
        assert breaker._failure_count == 0


class TestSchemaValidation:
    """Test parameter schema validation system."""

    @pytest.fixture
    def hot_config(self):
        """Create hot reloadable config for testing."""
        from app.core.hot_config import HotReloadableSignalServiceConfig

        with patch('app.core.hot_config.BaseSignalServiceConfig.__init__') as mock_base_init:
            mock_base_init.return_value = None
            config = HotReloadableSignalServiceConfig()
            config.environment = 'test'  # set environment for validation
            return config

    def test_database_url_validation(self, hot_config):
        """Test database URL schema validation."""
        # Valid URLs
        valid_urls = [
            "postgresql://user:pass@localhost/db",
            "postgresql://user:pass@127.0.0.1:5432/db",
            "postgresql://user:pass@db.internal/database?ssl=true"
        ]

        for url in valid_urls:
            assert hot_config.validate_parameter("DATABASE_URL", url), f"Valid URL rejected: {url}"

        # Invalid URLs
        invalid_urls = [
            "mysql://user:pass@localhost/db",  # Wrong protocol
            "postgresql://localhost/db",       # Missing credentials
            "not-a-url",                      # Not a URL
            ""                                # Empty
        ]

        for url in invalid_urls:
            with pytest.raises(Exception):  # Should raise SchemaValidationError
                hot_config.validate_parameter("DATABASE_URL", url)

    def test_redis_url_validation(self, hot_config):
        """Test Redis URL schema validation."""
        # Valid URLs
        valid_urls = [
            "redis://localhost",
            "redis://localhost:6379",
            "redis://user:pass@localhost:6379",
            "redis://localhost/1"
        ]

        for url in valid_urls:
            assert hot_config.validate_parameter("REDIS_URL", url), f"Valid Redis URL rejected: {url}"

    def test_performance_parameter_validation(self, hot_config):
        """Test performance parameter range validation."""
        # Valid cache TTL
        assert hot_config.validate_parameter("signal_service.cache_ttl_seconds", 300)
        assert hot_config.validate_parameter("signal_service.cache_ttl_seconds", "600")  # String conversion

        # Invalid cache TTL
        with pytest.raises(Exception):  # Below minimum
            hot_config.validate_parameter("signal_service.cache_ttl_seconds", 10)

        with pytest.raises(Exception):  # Above maximum
            hot_config.validate_parameter("signal_service.cache_ttl_seconds", 5000)

    def test_service_url_production_validation(self, hot_config):
        """Test service URL validation in production environment."""
        hot_config.environment = 'production'

        # Valid production URLs (internal only)
        valid_urls = [
            "http://localhost:8080",
            "http://service.local",
            "http://10.0.0.1:8080",
            "http://192.168.1.100:8080"
        ]

        for url in valid_urls:
            assert hot_config.validate_parameter("signal_service.ticker_service_url", url)

        # Invalid production URLs (external)
        hot_config.environment = 'production'
        with pytest.raises(Exception):
            hot_config.validate_parameter("signal_service.ticker_service_url", "http://external.com")

    def test_secret_validation(self, hot_config):
        """Test secret validation requirements."""
        # Valid secrets
        valid_secrets = [
            "very-long-secure-secret-key-12345",
            "another-strong-secret-with-special-chars!@#"
        ]

        for secret in valid_secrets:
            assert hot_config.validate_parameter("GATEWAY_SECRET", secret)

        # Invalid secrets
        invalid_secrets = [
            "short",                    # Too short
            "password",                 # Weak/common
            "test",                     # Weak/common
            "admin"                     # Weak/common
        ]

        for secret in invalid_secrets:
            with pytest.raises(Exception):
                hot_config.validate_parameter("GATEWAY_SECRET", secret)


class TestRollbackMechanism:
    """Test parameter rollback functionality."""

    @pytest.fixture
    def hot_config(self):
        """Create hot reloadable config for testing."""
        from app.core.hot_config import HotReloadableSignalServiceConfig

        with patch('app.core.hot_config.BaseSignalServiceConfig.__init__') as mock_base_init:
            mock_base_init.return_value = None
            config = HotReloadableSignalServiceConfig()
            config.DATABASE_URL = "postgresql://test:test@localhost/test"
            config.REDIS_URL = "redis://localhost:6379"
            return config

    def test_parameter_rollback_storage(self, hot_config):
        """Test storing parameter values for rollback."""
        original_value = "postgresql://original:value@localhost/db"

        hot_config.store_parameter_rollback("DATABASE_URL", original_value)

        assert "DATABASE_URL" in hot_config._parameter_rollback_history
        assert hot_config._parameter_rollback_history["DATABASE_URL"]["value"] == original_value
        assert "timestamp" in hot_config._parameter_rollback_history["DATABASE_URL"]

    @pytest.mark.asyncio
    async def test_parameter_rollback_execution(self, hot_config):
        """Test executing parameter rollback."""
        original_url = "postgresql://original:value@localhost/db"
        new_url = "postgresql://new:value@localhost/db"

        # Store original value
        hot_config.store_parameter_rollback("DATABASE_URL", original_url)

        # Change to new value
        hot_config.DATABASE_URL = new_url
        assert new_url == hot_config.DATABASE_URL

        # Rollback
        success = await hot_config.rollback_parameter("DATABASE_URL")

        assert success
        assert original_url == hot_config.DATABASE_URL
        assert hot_config._config_stats["rollbacks_triggered"] == 1

    def test_rollback_history_limit(self, hot_config):
        """Test rollback history size limiting."""
        # Add more than the limit (100) parameters
        for i in range(105):
            hot_config.store_parameter_rollback(f"param_{i}", f"value_{i}")

        # Should be limited to 100
        assert len(hot_config._parameter_rollback_history) == 100


class TestKillSwitch:
    """Test kill switch functionality."""

    @pytest.fixture
    def hot_config(self):
        """Create hot reloadable config for testing."""
        from app.core.hot_config import HotReloadableSignalServiceConfig

        with patch('app.core.hot_config.BaseSignalServiceConfig.__init__') as mock_base_init:
            mock_base_init.return_value = None
            return HotReloadableSignalServiceConfig()

    def test_kill_switch_enable(self, hot_config):
        """Test enabling kill switch."""
        reason = "Test activation"

        assert not hot_config._kill_switch_enabled

        hot_config.enable_kill_switch(reason)

        assert hot_config._kill_switch_enabled
        assert hot_config._config_stats["kill_switch_enabled"]

    def test_kill_switch_disable(self, hot_config):
        """Test disabling kill switch."""
        # Enable first
        hot_config.enable_kill_switch("Test")
        hot_config._config_stats["consecutive_failures"] = 5

        # Disable
        hot_config.disable_kill_switch("Test disable")

        assert not hot_config._kill_switch_enabled
        assert not hot_config._config_stats["kill_switch_enabled"]
        assert hot_config._config_stats["consecutive_failures"] == 0  # Reset

    def test_kill_switch_blocks_validation(self, hot_config):
        """Test kill switch blocks security context validation."""
        hot_config.enable_kill_switch("Test block")

        # Should fail validation due to kill switch
        assert not hot_config._validate_security_context()

    @pytest.mark.asyncio
    async def test_emergency_shutdown(self, hot_config):
        """Test emergency shutdown functionality."""
        # Mock notification client
        mock_client = MagicMock()
        hot_config.notification_client = mock_client

        await hot_config.emergency_shutdown()

        # Should enable kill switch and stop client
        assert hot_config._kill_switch_enabled
        mock_client.stop_listening.assert_called_once()


class TestObservabilityAndMetrics:
    """Test observability and metrics collection."""

    @pytest.fixture
    def hot_config(self):
        """Create hot reloadable config for testing."""
        from app.core.hot_config import HotReloadableSignalServiceConfig

        with patch('app.core.hot_config.BaseSignalServiceConfig.__init__') as mock_base_init:
            mock_base_init.return_value = None
            config = HotReloadableSignalServiceConfig()
            config.notification_client = MagicMock()
            return config

    @pytest.mark.asyncio
    async def test_health_monitoring_comprehensive(self, hot_config):
        """Test comprehensive health monitoring."""
        health_data = await hot_config.get_hot_reload_health()

        # Verify all required health metrics
        required_fields = [
            "hot_reload_enabled",
            "security_context_valid",
            "notification_client_active",
            "handlers_registered",
            "last_validation",
            "statistics",
            "circuit_breaker",
            "fail_safes"
        ]

        for field in required_fields:
            assert field in health_data, f"Missing health field: {field}"

        # Verify circuit breaker metrics
        cb_data = health_data["circuit_breaker"]
        assert "state" in cb_data
        assert "failure_count" in cb_data

        # Verify fail-safe metrics
        fs_data = health_data["fail_safes"]
        assert "kill_switch_enabled" in fs_data
        assert "consecutive_failures" in fs_data
        assert "rollback_history_size" in fs_data

    def test_statistics_tracking(self, hot_config):
        """Test statistics collection and tracking."""
        initial_stats = hot_config._config_stats

        # Verify all required statistics fields
        required_stats = [
            "hot_reloads",
            "successful_reloads",
            "failed_reloads",
            "consecutive_failures",
            "circuit_breaker_trips",
            "schema_validation_errors",
            "rollbacks_triggered"
        ]

        for stat in required_stats:
            assert stat in initial_stats, f"Missing statistic: {stat}"
            assert isinstance(initial_stats[stat], int), f"Statistic {stat} should be integer"

    def test_failure_escalation_tracking(self, hot_config):
        """Test failure escalation and tracking."""
        # Simulate consecutive failures
        hot_config._config_stats["consecutive_failures"] = 8
        hot_config._config_stats["failed_reloads"] = 15

        # Should still validate (below threshold)
        assert hot_config._validate_security_context()

        # Exceed threshold
        hot_config._config_stats["consecutive_failures"] = 12

        # Should trigger kill switch
        assert not hot_config._validate_security_context()
        assert hot_config._kill_switch_enabled


def main():
    """Run hot reload fail-safe tests."""
    import subprocess
    import sys

    print("🔍 Running Hot Reload Fail-Safe Tests...")

    # Run the tests
    result = subprocess.run([
        sys.executable, '-m', 'pytest',
        __file__,
        '-v',
        '--tb=short'
    ], capture_output=True, text=True)

    print("STDOUT:")
    print(result.stdout)

    if result.stderr:
        print("STDERR:")
        print(result.stderr)

    if result.returncode == 0:
        print("✅ Hot reload fail-safe tests passed!")
        print("\n📋 Fail-Safe Components Verified:")
        print("  - Circuit breaker operation and recovery")
        print("  - Schema validation with type checking")
        print("  - Parameter rollback mechanisms")
        print("  - Kill switch controls and emergency shutdown")
        print("  - Comprehensive observability and metrics")
        print("  - Failure escalation and auto-protection")
    else:
        print("❌ Hot reload fail-safe tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
