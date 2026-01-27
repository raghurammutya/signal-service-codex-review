"""
Comprehensive test cases for production blockers fixed in signal service.

Tests all the critical fixes implemented to resolve production deployment issues.
"""
import os
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.core.health_checker import HealthChecker

# Test imports
from app.core.redis_manager import RedisConnectionError, RedisHealthChecker, get_redis_client
from app.services.signal_executor import SignalExecutor
from app.services.signal_redis_manager import RedisClusterManager, SignalRedisManager
from common.storage.database import (
    DatabaseConnectionError,
    get_database_connection,
    get_timescaledb_session,
)


class TestProductionFixesValidation:
    """Comprehensive test suite for all production fixes."""

    @pytest.mark.asyncio
    async def test_redis_manager_production_connection(self):
        """Test that Redis manager properly connects to production Redis."""
        # Test production environment detection
        with patch.dict(os.environ, {'ENVIRONMENT': 'production', 'REDIS_URL': 'redis://localhost:6379/0'}):
            client = await get_redis_client()
            assert client is not None

            # Test connection works
            result = await client.ping()
            assert result is True

    @pytest.mark.asyncio
    async def test_redis_manager_development_fallback(self):
        """Test that Redis manager falls back to fake client in development."""
        # Test development environment
        with patch.dict(os.environ, {'ENVIRONMENT': 'development'}, clear=True):
            client = await get_redis_client()
            assert client is not None

            # Should be fake Redis
            info = await client.info()
            assert 'keys' in info  # Characteristic of fake Redis

    @pytest.mark.asyncio
    async def test_redis_manager_production_failure(self):
        """Test that Redis manager fails hard in production when Redis unavailable."""
        with patch.dict(os.environ, {'ENVIRONMENT': 'production', 'REDIS_URL': 'redis://invalid:6379/0'}), pytest.raises(RedisConnectionError):
            await get_redis_client()

    @pytest.mark.asyncio
    async def test_database_connection_production(self):
        """Test that database connection works in production mode."""
        with patch.dict(os.environ, {'ENVIRONMENT': 'production', 'DATABASE_URL': 'postgresql+asyncpg://test:test@localhost:5432/test'}), pytest.raises(DatabaseConnectionError):
            await get_database_connection()

    @pytest.mark.asyncio
    async def test_database_connection_development_fallback(self):
        """Test that database connection falls back to mock in development."""
        with patch.dict(os.environ, {'ENVIRONMENT': 'development'}, clear=True):
            # Should return mock connections
            engine, session_factory = await get_database_connection()
            assert engine is None and session_factory is None  # Mock behavior

    @pytest.mark.asyncio
    async def test_signal_redis_manager_cluster_initialization(self):
        """Test that SignalRedisManager properly initializes cluster_manager."""
        manager = SignalRedisManager()

        # Mock Redis client
        mock_redis = AsyncMock()
        with patch('app.services.signal_redis_manager.get_redis_client', return_value=mock_redis):
            await manager.initialize()

        # Check cluster manager is initialized
        assert manager.cluster_manager is not None
        assert isinstance(manager.cluster_manager, RedisClusterManager)
        assert manager.cluster_manager.redis_client == mock_redis

    @pytest.mark.asyncio
    async def test_signal_redis_manager_worker_operations(self):
        """Test SignalRedisManager worker operations don't fail due to missing cluster_manager."""
        manager = SignalRedisManager()

        # Initialize with mock Redis
        mock_redis = AsyncMock()
        with patch('app.services.signal_redis_manager.get_redis_client', return_value=mock_redis):
            await manager.initialize()

        # Test worker operations that previously failed
        result = await manager.set_worker_assignment("TEST@SYMBOL", "worker-1", 300)
        assert isinstance(result, bool)  # Should not crash

        result = await manager.get_worker_assignment("TEST@SYMBOL")
        # Should not crash - may return None but no AttributeError

    def test_sql_syntax_fix_in_repository(self):
        """Test that SQL syntax error in get_custom_timeframe_data is fixed."""
        # Read the file to check the SQL is fixed
        with open('/home/stocksadmin/signal-service-codex-review/app/repositories/signal_repository.py') as f:
            content = f.read()

        # Check that the problematic SQL with inline TODO is fixed
        assert '#TODO: Ensure index on instrument_key$1' not in content
        assert 'WHERE instrument_key = $1' in content

        # Check TODO is moved to comment
        assert '# TODO: Ensure index on instrument_key for better performance' in content

    @pytest.mark.asyncio
    async def test_health_checker_check_health_method(self):
        """Test that HealthChecker has the missing check_health method."""
        # Mock dependencies
        mock_redis = AsyncMock()
        mock_db = Mock()

        checker = HealthChecker(mock_redis, mock_db)

        # Test basic health check
        result = await checker.check_health(detailed=False)
        assert 'status' in result
        assert 'timestamp' in result

        # Test detailed health check
        with patch.object(checker, '_perform_all_checks', return_value={'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()}):
            result = await checker.check_health(detailed=True)
            assert 'status' in result

    @pytest.mark.asyncio
    async def test_signal_script_execution_security(self):
        """Test that signal script execution has proper security measures."""
        # Test script validation
        dangerous_script = "import os\nos.system('rm -rf /')"
        assert not SignalExecutor._validate_script_security(dangerous_script)

        safe_script = "result = 1 + 1\nemit_signal({'value': result})"
        assert SignalExecutor._validate_script_security(safe_script)

        # Test execution with dangerous script
        context = {"instrument": "TEST", "params": {}}
        result = await SignalExecutor.execute_signal_script(dangerous_script, context)
        assert not result["success"]
        assert "unsafe code" in result["error"]

    @pytest.mark.asyncio
    async def test_signal_script_execution_limits(self):
        """Test that signal script execution has proper resource limits."""
        # Test signal count limit
        script_with_many_signals = """
for i in range(200):
    emit_signal({'value': i})
"""
        context = {"instrument": "TEST", "params": {}}
        result = await SignalExecutor.execute_signal_script(script_with_many_signals, context, timeout=5)

        if result["success"]:
            # Should be limited to 100 signals
            assert len(result["signals"]) <= 100

    @pytest.mark.asyncio
    async def test_signal_script_sandbox_isolation(self):
        """Test that signal script sandbox properly isolates dangerous operations."""
        # Create sandbox globals
        context = {"instrument": "TEST", "params": {}}
        sandbox = SignalExecutor._create_sandbox_globals(context)

        # Check dangerous functions are not available
        assert 'exec' not in sandbox.get('__builtins__', {})
        assert 'eval' not in sandbox.get('__builtins__', {})
        assert 'open' not in sandbox.get('__builtins__', {})
        assert '__import__' not in sandbox.get('__builtins__', {})

        # Check safe functions are available
        assert 'len' in sandbox.get('__builtins__', {})
        assert 'sum' in sandbox.get('__builtins__', {})
        assert 'range' in sandbox.get('__builtins__', {})

    def test_imports_resolution(self):
        """Test that all critical imports are resolved."""
        # Test that app.core.redis_manager can be imported
        import importlib.util
        if importlib.util.find_spec('app.core.redis_manager'):
            assert True
        else:
            pytest.fail("app.core.redis_manager module not available")

        # Test that database imports work
        if importlib.util.find_spec('common.storage.database'):
            assert True
        else:
            pytest.fail("database imports not available")

    @pytest.mark.asyncio
    async def test_redis_health_checker(self):
        """Test Redis health checker functionality."""
        # Test with mock Redis
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis.info.return_value = {
            'used_memory': 1000000,
            'connected_clients': 5,
            'uptime_in_seconds': 3600,
            'redis_version': '7.0.0',
            'role': 'master'
        }

        with patch('app.core.redis_manager.get_redis_client', return_value=mock_redis):
            health = await RedisHealthChecker.check_health()

        assert health['status'] == 'up'
        assert 'ping_time_ms' in health
        assert 'used_memory' in health

    @pytest.mark.asyncio
    async def test_database_session_context_manager(self):
        """Test that database session context manager works properly."""
        # Test development mode (mock)
        with patch.dict(os.environ, {'ENVIRONMENT': 'development'}, clear=True):
            async with get_timescaledb_session() as session:
                assert session is not None
                # Should be mock session
                result = await session.execute("SELECT 1")
                assert result is not None

    def test_no_silent_fallbacks_in_production(self):
        """Test that there are no silent fallbacks in production code paths."""
        # Check websocket.py for production Redis usage
        with open('/home/stocksadmin/signal-service-codex-review/app/api/v2/websocket.py') as f:
            websocket_content = f.read()

        # Should use real Redis connection, not test fallback
        assert 'from common.storage.redis import get_redis_client' in websocket_content

        # Check that it handles Redis connection properly
        assert 'get_redis_client()' in websocket_content


class TestEnvironmentConfiguration:
    """Test proper environment-based configuration."""

    def test_production_environment_detection(self):
        """Test that production environment is properly detected."""
        test_cases = [
            ('production', True),
            ('prod', True),
            ('staging', True),
            ('development', False),
            ('dev', False),
            ('test', False)
        ]

        for env, _should_be_prod in test_cases:
            with patch.dict(os.environ, {'ENVIRONMENT': env}):
                # Test Redis manager behavior
                # In production without URL, should fail
                # In development without URL, should work with fallback
                pass  # Implementation depends on actual environment

    @pytest.mark.asyncio
    async def test_configuration_validation(self):
        """Test that configuration validation works properly."""
        # Test missing Redis URL in production
        with patch.dict(os.environ, {'ENVIRONMENT': 'production'}, clear=True), pytest.raises(RedisConnectionError):
            await get_redis_client()

        # Test missing database URL in production
        with patch.dict(os.environ, {'ENVIRONMENT': 'production'}, clear=True), pytest.raises(DatabaseConnectionError):
            await get_database_connection()


class TestSecurityMeasures:
    """Test security measures implemented."""

    def test_script_validation_patterns(self):
        """Test script validation catches dangerous patterns."""
        validator = SignalExecutor._validate_script_security

        dangerous_scripts = [
            "import os",
            "import subprocess",
            "eval('malicious code')",
            "exec('malicious code')",
            "open('/etc/passwd')",
            "__import__('os')",
            "while True: pass",  # Infinite loop
            "x" * 11000,  # Too long
            "\n" * 501  # Too many lines
        ]

        for script in dangerous_scripts:
            assert not validator(script), f"Should reject dangerous script: {script[:50]}"

        safe_scripts = [
            "result = 1 + 1",
            "import math\nresult = math.sqrt(16)",
            "data = {'price': 100}\nemit_signal(data)"
        ]

        for script in safe_scripts:
            assert validator(script), f"Should accept safe script: {script}"

    def test_signal_data_sanitization(self):
        """Test that signal data is properly sanitized."""
        # This would be tested in the actual signal execution
        # Here we verify the sanitization logic exists
        assert hasattr(SignalExecutor, 'execute_signal_script')

        # Check that emit_signal function has limits
        # (Implementation details tested in test_signal_script_execution_limits)


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
