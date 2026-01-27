"""Global test configuration and fixtures."""
import asyncio
import os
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, Mock

import numpy as np
import pandas as pd
import pytest
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

# Set test environment
os.environ["ENVIRONMENT"] = "test"
os.environ["PYTEST_CURRENT_TEST"] = "true"

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def test_database():
    """Set up test TimescaleDB container."""
    postgres = PostgresContainer(
        "timescale/timescaledb:latest-pg14",
        dbname="signal_service_test",
        username="test_user",
        password="test_password"
    )

    postgres.start()

    # Setup database schema
    connection_url = postgres.get_connection_url()

    yield {
        "url": connection_url,
        "container": postgres
    }

    postgres.stop()

@pytest.fixture(scope="session")
async def test_redis():
    """Set up test Redis container."""
    redis = RedisContainer("redis:7-alpine")
    redis.start()

    yield {
        "url": redis.get_connection_url(),
        "container": redis
    }

    redis.stop()

@pytest.fixture
def sample_instrument_data():
    """Sample instrument data for testing."""
    return {
        "equity": {
            "instrument_key": "NSE@TESTSYM",
            "symbol": "TESTSYM",
            "exchange": "NSE",
            "instrument_type": "EQ",
            "lot_size": 1,
            "tick_size": 0.05
        },
        "option": {
            "instrument_key": "NSE@TESTSYM@CE@20000",
            "symbol": "TESTSYM",
            "exchange": "NSE",
            "instrument_type": "CE",
            "strike_price": 20000,
            "expiry_date": "2024-12-28",
            "lot_size": 50,
            "tick_size": 0.05
        },
        "future": {
            "instrument_key": "NSE@TESTSYM@FUT@MAR25",
            "symbol": "TESTSYM",
            "exchange": "NSE",
            "instrument_type": "FUT",
            "expiry_date": "2025-03-27",
            "lot_size": 50,
            "tick_size": 0.05
        }
    }

@pytest.fixture
def sample_market_data():
    """Sample market data for testing."""
    dates = pd.date_range('2024-01-01', periods=100, freq='5T')
    base_price = 20000

    # Generate realistic price movement
    price_changes = np.random.normal(0, 0.005, 100)  # 0.5% volatility
    prices = [base_price]

    for change in price_changes[:-1]:
        new_price = prices[-1] * (1 + change)
        prices.append(new_price)

    ohlcv_data = []
    for i, (date, price) in enumerate(zip(dates, prices, strict=False)):
        high = price * (1 + abs(np.random.normal(0, 0.002)))
        low = price * (1 - abs(np.random.normal(0, 0.002)))
        close = low + (high - low) * np.random.random()
        volume = np.random.randint(50000, 200000)

        ohlcv_data.append({
            "timestamp": date.isoformat(),
            "open": round(price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(close, 2),
            "volume": volume
        })

    return pd.DataFrame(ohlcv_data)

@pytest.fixture
def sample_greeks_data():
    """Sample Greeks data for testing."""
    return {
        "delta": 0.5234,
        "gamma": 0.0156,
        "theta": -12.45,
        "vega": 89.23,
        "rho": 67.89,
        "implied_volatility": 0.2145
    }

@pytest.fixture
def sample_tick_data():
    """Sample tick data for testing."""
    return {
        "instrument_key": "NSE@TESTSYM@CE@20000",
        "last_price": 150.50,
        "bid": 150.25,
        "ask": 150.75,
        "volume": 10000,
        "open_interest": 50000,
        "timestamp": datetime.utcnow().isoformat()
    }

@pytest.fixture
def mock_config_service():
    """Mock config service responses."""
    def _mock_get_secret(key: str, required: bool = True):
        secrets = {
            "DATABASE_URL": "postgresql://test_user:test_password@localhost:5432/signal_service_test",
            "REDIS_URL": "redis://localhost:6379",
            "GATEWAY_SECRET": "test_gateway_secret",
            "INTERNAL_API_KEY": "test_internal_api_key"
        }
        return secrets.get(key)

    def _mock_get_config(key: str):
        configs = {
            "PORT": "8003",
            "ENVIRONMENT": "test",
            "CACHE_TTL_SECONDS": "300",
            "MAX_BATCH_SIZE": "100"
        }
        return configs.get(key)

    mock_client = Mock()
    mock_client.get_secret.side_effect = _mock_get_secret
    mock_client.get_config.side_effect = _mock_get_config
    mock_client.health_check.return_value = True

    return mock_client

@pytest.fixture
def mock_ticker_service():
    """Mock ticker service responses."""
    def _mock_historical_data(instrument_token: int, **kwargs):
        # Generate sample historical data
        dates = pd.date_range('2024-01-01', periods=50, freq='5T')
        return pd.DataFrame({
            'timestamp': dates,
            'open': np.random.uniform(19900, 20100, 50),
            'high': np.random.uniform(20000, 20200, 50),
            'low': np.random.uniform(19800, 20000, 50),
            'close': np.random.uniform(19900, 20100, 50),
            'volume': np.random.randint(50000, 200000, 50)
        })

    mock_service = AsyncMock()
    mock_service.get_historical_data.side_effect = _mock_historical_data
    return mock_service

@pytest.fixture
def mock_database_session():
    """Mock database session for unit tests."""
    mock_session = AsyncMock()

    # Mock connection acquisition
    mock_conn = AsyncMock()
    mock_session.acquire.return_value.__aenter__.return_value = mock_conn
    mock_session.acquire.return_value.__aexit__.return_value = None

    return mock_session, mock_conn

@pytest.fixture
def clean_database(test_database):
    """Clean database before each test."""
    # Implementation depends on actual database setup
    # For now, return database info
    return test_database

class TestDataFactory:
    """Factory for generating test data."""

    @staticmethod
    def create_option_data(spot_price: float = 20000, **kwargs) -> dict[str, Any]:
        """Create option data for testing."""
        defaults = {
            "spot_price": spot_price,
            "strike_price": 20000,
            "time_to_expiry": 0.25,  # 3 months
            "risk_free_rate": 0.06,
            "volatility": 0.20,
            "option_type": "call",
            "dividend_yield": 0.0
        }
        defaults.update(kwargs)
        return defaults

    @staticmethod
    def create_instrument_keys(count: int = 10) -> list[str]:
        """Create list of test instrument keys."""
        keys = []
        for i in range(count):
            keys.extend([
                f"NSE@TESTSYM{i}",  # Equity
                f"NSE@TESTSYM{i}@CE@{20000 + i*100}",  # Call option
                f"NSE@TESTSYM{i}@PE@{20000 + i*100}",  # Put option
                f"NSE@TESTSYM{i}@FUT@MAR25"  # Future
            ])
        return keys

@pytest.fixture
def test_data_factory():
    """Test data factory fixture."""
    return TestDataFactory()

# Performance test fixtures
@pytest.fixture
def performance_test_data():
    """Large dataset for performance testing."""
    return {
        "large_ohlcv": pd.DataFrame({
            'open': np.random.uniform(19800, 20200, 10000),
            'high': np.random.uniform(20000, 20400, 10000),
            'low': np.random.uniform(19600, 20000, 10000),
            'close': np.random.uniform(19800, 20200, 10000),
            'volume': np.random.randint(100000, 1000000, 10000)
        }),
        "many_instruments": [f"NSE@TESTSYM{i}@CE@{20000+i*10}" for i in range(1000)]
    }
