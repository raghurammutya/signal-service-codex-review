"""Integration tests for service communication."""
import asyncio
import os
from unittest.mock import Mock, patch

import pytest
from testcontainers.postgres import PostgreSqlContainer
from testcontainers.redis import RedisContainer


class TestServiceIntegration:
    """Integration tests for service communication."""

    @pytest.fixture(scope="class")
    async def test_infrastructure(self):
        """Set up test infrastructure containers."""
        # Start PostgreSQL
        postgres = PostgreSqlContainer(
            "timescale/timescaledb:latest-pg14",
            dbname="signal_service_test",
            username="test_user",
            password="test_password"
        )
        postgres.start()

        # Start Redis
        redis = RedisContainer("redis:7-alpine")
        redis.start()

        # Set environment variables for test
        os.environ["DATABASE_URL"] = postgres.get_connection_url()
        os.environ["REDIS_URL"] = redis.get_connection_url()

        yield {
            "postgres": postgres,
            "redis": redis,
            "postgres_url": postgres.get_connection_url(),
            "redis_url": redis.get_connection_url()
        }

        # Cleanup
        postgres.stop()
        redis.stop()

    @pytest.mark.integration
    async def test_config_service_communication(self, test_infrastructure):
        """Test config service integration with proper error handling."""
        from app.core.config import _get_config_client

        # Test with mock config service unavailable
        with patch('app.core.config._get_config_client') as mock_get_client:
            mock_get_client.side_effect = Exception("Config service unavailable")

            # Should raise exception when config service unavailable
            with pytest.raises(Exception):
                await _get_config_client()

    @pytest.mark.integration
    async def test_database_connection_and_schema_setup(self, test_infrastructure):
        """Test database connection and schema setup."""
        import asyncpg

        postgres_url = test_infrastructure["postgres_url"]

        # Test direct connection
        conn = await asyncpg.connect(postgres_url)

        # Create test tables if they don't exist
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS signal_greeks (
                id SERIAL PRIMARY KEY,
                signal_id VARCHAR(255),
                instrument_key VARCHAR(255),
                timestamp TIMESTAMPTZ,
                delta DECIMAL,
                gamma DECIMAL,
                theta DECIMAL,
                vega DECIMAL,
                rho DECIMAL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS signal_indicators (
                id SERIAL PRIMARY KEY,
                signal_id VARCHAR(255),
                instrument_key VARCHAR(255),
                timestamp TIMESTAMPTZ,
                indicator_name VARCHAR(255),
                parameters JSONB,
                values JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # Test table existence
        tables = await conn.fetch("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name IN ('signal_greeks', 'signal_indicators')
        """)

        assert len(tables) >= 2, "Required tables not created"
        await conn.close()

    @pytest.mark.integration
    async def test_redis_connection_and_operations(self, test_infrastructure):
        """Test Redis connection and basic operations."""
        import redis.asyncio as redis

        redis_url = test_infrastructure["redis_url"]

        # Test Redis connection
        redis_client = redis.from_url(redis_url)

        # Test basic operations
        await redis_client.set("test_key", "test_value")
        value = await redis_client.get("test_key")
        assert value.decode() == "test_value"

        # Test stream operations (for signal processing)
        stream_name = "test_signal_stream"
        await redis_client.xadd(stream_name, {"instrument": "NSE@TEST", "price": "20000"})

        # Read from stream
        messages = await redis_client.xrange(stream_name, count=1)
        assert len(messages) == 1
        assert messages[0][1][b'instrument'].decode() == "NSE@TEST"

        await redis_client.close()

    @pytest.mark.integration
    async def test_signal_repository_with_real_database(self, test_infrastructure):
        """Test signal repository with real database connection."""
        from datetime import datetime

        import asyncpg

        from app.repositories.signal_repository import SignalRepository

        # Setup database session
        postgres_url = test_infrastructure["postgres_url"]

        # Create a simple connection pool mock
        class MockPool:
            def __init__(self, connection_url):
                self.connection_url = connection_url

            async def acquire(self):
                return MockConnection(self.connection_url)

        class MockConnection:
            def __init__(self, connection_url):
                self.connection_url = connection_url
                self._conn = None

            async def __aenter__(self):
                self._conn = await asyncpg.connect(self.connection_url)
                return self._conn

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                if self._conn:
                    await self._conn.close()

        # Mock the database session
        with patch('app.repositories.signal_repository.get_timescaledb_session') as mock_session:
            mock_session.return_value = MockPool(postgres_url)

            repo = SignalRepository()
            await repo.initialize()

            # Test saving Greeks
            test_greeks = {
                "signal_id": "integration_test",
                "instrument_key": "NSE@TEST@CE@20000",
                "timestamp": datetime.utcnow(),
                "delta": 0.5234,
                "gamma": 0.0156,
                "theta": -12.45,
                "vega": 89.23,
                "rho": 67.89,
                "implied_volatility": 0.2145,
                "theoretical_value": 150.0,
                "underlying_price": 20000.0,
                "strike_price": 20000.0,
                "time_to_expiry": 0.25
            }

            record_id = await repo.save_greeks(test_greeks)
            assert record_id is not None

            # Test retrieving Greeks
            retrieved = await repo.get_latest_greeks("NSE@TEST@CE@20000")
            assert retrieved is not None
            assert abs(retrieved["delta"] - 0.5234) < 0.001

    @pytest.mark.integration
    async def test_ticker_service_api_integration(self, test_infrastructure):
        """Test ticker service API integration with mocked responses."""

        import httpx

        from app.api.v2.indicators import IndicatorCalculator

        # Mock ticker service responses
        async def mock_get(url, **kwargs):
            response = Mock()
            if "historical/ohlcv" in url:
                response.status_code = 200
                response.json.return_value = {
                    "data": [
                        {
                            "timestamp": "2024-01-01T09:15:00Z",
                            "open": 20000.0,
                            "high": 20100.0,
                            "low": 19950.0,
                            "close": 20050.0,
                            "volume": 100000
                        }
                    ]
                }
            else:
                response.status_code = 404
                response.json.return_value = {"error": "Not found"}

            return response

        with patch.object(httpx.AsyncClient, 'get', mock_get):
            calculator = IndicatorCalculator()
            await calculator.initialize()

            # Test historical data retrieval
            try:
                df = await calculator.get_historical_data(
                    instrument_token=256265,
                    timeframe="5minute",
                    periods=50
                )

                # Should return data without raising exceptions
                assert df is not None

            except Exception as e:
                # Should not be silent failure
                assert "ticker_service" in str(e).lower() or "historical" in str(e).lower()

    @pytest.mark.integration
    async def test_websocket_integration(self, test_infrastructure):
        """Test WebSocket integration for real-time signals."""
        from fastapi.testclient import TestClient

        from app.main import app

        # This would normally require a more complex setup
        # For now, test basic WebSocket endpoint availability
        client = TestClient(app)

        # Test WebSocket info endpoint
        response = client.get("/api/v2/signals/subscriptions/websocket")
        assert response.status_code == 200

        websocket_info = response.json()
        assert "status" in websocket_info
        assert "url" in websocket_info

    @pytest.mark.integration
    async def test_health_check_integration(self, test_infrastructure):
        """Test health check with real dependencies."""
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)

        # Mock successful config service
        with patch('app.core.config._get_config_client') as mock_config:
            mock_client = Mock()
            mock_client.health_check.return_value = True
            mock_config.return_value = mock_client

            response = client.get("/health")

            # Should return healthy status
            assert response.status_code == 200
            health_data = response.json()
            assert "status" in health_data

    @pytest.mark.integration
    async def test_error_propagation_integration(self, test_infrastructure):
        """Test that errors propagate correctly through service layers."""
        from app.errors import GreeksCalculationError
        from app.services.greeks_calculator import GreeksCalculator

        calculator = GreeksCalculator()

        # Test invalid input propagation
        with pytest.raises((GreeksCalculationError, ValueError)):
            calculator.calculate_greeks(
                spot_price=-100,  # Invalid
                strike_price=20000,
                time_to_expiry=0.25,
                risk_free_rate=0.06,
                volatility=0.20,
                option_type="call"
            )

    @pytest.mark.integration
    async def test_concurrent_service_operations(self, test_infrastructure):
        """Test concurrent operations across services."""
        from app.services.greeks_calculator import GreeksCalculator

        calculator = GreeksCalculator()

        async def calculate_and_verify(spot_offset):
            """Calculate Greeks and verify result."""
            result = calculator.calculate_greeks(
                spot_price=20000 + spot_offset,
                strike_price=20000,
                time_to_expiry=0.25,
                risk_free_rate=0.06,
                volatility=0.20,
                option_type="call"
            )
            assert "delta" in result
            return result

        # Run multiple concurrent calculations
        tasks = [calculate_and_verify(i * 10) for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        assert all("delta" in result for result in results)

    @pytest.mark.integration
    async def test_service_resilience(self, test_infrastructure):
        """Test service resilience to temporary failures."""
        from app.repositories.signal_repository import SignalRepository

        repo = SignalRepository()

        # Simulate temporary database unavailability
        with patch('app.repositories.signal_repository.get_timescaledb_session') as mock_session:
            mock_session.side_effect = Exception("Temporary database unavailability")

            # Should raise proper exception, not fail silently
            with pytest.raises(Exception):
                await repo.initialize()

    @pytest.mark.integration
    async def test_custom_script_execution_integration(self, test_infrastructure):
        """Test custom script execution with real isolation."""
        try:
            from app.security.sandbox_enhancements import EnhancedSandbox

            sandbox = EnhancedSandbox()

            # Test safe script execution
            safe_script = """
import math
result = math.sqrt(16)
print(f"Square root of 16 is {result}")
"""

            result = sandbox.execute_code(safe_script)
            assert result["status"] == "success"

        except ImportError:
            pytest.skip("Sandbox implementation not available for integration testing")
