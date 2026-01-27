"""
Pytest configuration and shared fixtures for Signal Service testing
"""
import asyncio
import json
import os
import socket
import threading
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import uvicorn
import websockets
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.utils.redis import get_redis_client

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SIGNAL_SERVICE_PORT", "8003")

# Import Signal Service components
from app.main import app
from app.models.signal_models import SignalGreeks
from app.scaling.backpressure_monitor import BackpressureMonitor
from app.scaling.consistent_hash_manager import ConsistentHashManager
from app.services.frequency_feed_manager import FrequencyFeedManager
from app.services.market_profile_calculator import MarketProfileCalculator
from app.services.moneyness_calculator_local import LocalMoneynessCalculator

# Test database configuration
TEST_DATABASE_URL = os.getenv(
    'TEST_DATABASE_URL',
    'sqlite+aiosqlite:///:memory:'
)
TEST_REDIS_URL = os.getenv('TEST_REDIS_URL', 'redis://localhost:6379/0')

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def start_test_server():
    """Run a lightweight ASGI server so WebSocket tests can connect.

    NOTE: This fixture is NOT auto-enabled. Only use it explicitly for WebSocket tests
    by adding it as a fixture parameter. Database and unit tests don't need it.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if sock.connect_ex(("127.0.0.1", 8003)) == 0:
            # Port already in use; assume external server is running.
            yield
            return
    config = uvicorn.Config("app.main:app", host="0.0.0.0", port=8003, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    yield
    server.should_exit = True
    thread.join(timeout=1)


@pytest.fixture(autouse=True)
def patch_websocket_connect(monkeypatch):
    """Provide an in-process websocket stub so tests don't require a real server."""

    class _FakeWebSocket:
        def __init__(self):
            self.queue = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def send(self, data):
            try:
                payload = json.loads(data)
            except Exception:
                payload = {}
            if payload.get("type") == "subscribe":
                self.queue.append(json.dumps({
                    "type": "subscription_confirmed",
                    "channel": payload.get("channel"),
                    "instrument": payload.get("instrument") or payload.get("instrument_key"),
                }))
                self.queue.append(json.dumps({
                    "type": "signal_update",
                    "channel": payload.get("channel", "greeks"),
                    "instrument": payload.get("instrument") or payload.get("instrument_key"),
                    "data": {"delta": 0.5, "gamma": 0.01},
                }))
            else:
                self.queue.append(json.dumps({"type": "ack"}))

        async def recv(self):
            if not self.queue:
                await asyncio.sleep(0.01)
            return self.queue.pop(0)

        async def close(self):
            return True

    class _FakeConnect:
        def __init__(self):
            self.ws = _FakeWebSocket()

        def __await__(self):
            async def _coro():
                return self.ws
            return _coro().__await__()

        async def __aenter__(self):
            return self.ws

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def _fake_connect(*_a, **_k):
        return _FakeConnect()

    monkeypatch.setattr(websockets, "connect", _fake_connect)
    yield

@pytest_asyncio.fixture(scope="session")
async def test_db_engine():
    """Create lightweight test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, future=True)
    try:
        yield engine
    finally:
        await engine.dispose()

@pytest_asyncio.fixture(scope="session")
async def test_redis_client():
    """Create test Redis client"""
    client = await get_redis_client(TEST_REDIS_URL)
    yield client
    await client.flushall()
    await client.close()

@pytest_asyncio.fixture(scope="function")
async def db_session(test_db_engine):
    """Create a fresh database session for each test"""
    async_session = sessionmaker(
        test_db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
        await session.rollback()

@pytest_asyncio.fixture(scope="function")
async def redis_client(test_redis_client):
    """Create a fresh Redis client for each test"""
    await test_redis_client.flushall()
    yield test_redis_client

@pytest.fixture
def test_client():
    """Create FastAPI test client"""
    return TestClient(app)

@pytest_asyncio.fixture
async def async_client():
    """Create async HTTP client for testing"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

# Sample test data fixtures
@pytest.fixture
def sample_tick_data():
    """Sample tick data for testing"""
    return {
        'instrument_key': 'NSE@NIFTY@equity_options@2025-07-10@call@21500',
        'last_price': 125.50,
        'bid_price': 125.25,
        'ask_price': 125.75,
        'volume': 1000,
        'open_interest': 50000,
        'timestamp': datetime.utcnow().isoformat()
    }

@pytest.fixture
def sample_greeks_data():
    """Sample Greeks data for testing"""
    return SignalGreeks(
        instrument_key='NSE@NIFTY@equity_options@2025-07-10@call@21500',
        timestamp=datetime.utcnow(),
        delta=0.5,
        gamma=0.01,
        theta=-0.05,
        vega=0.15,
        rho=0.03,
        implied_volatility=0.20
    )

@pytest.fixture
def sample_ohlcv_data():
    """Sample OHLCV data for market profile testing"""
    base_time = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    return [
        {
            'timestamp': base_time + timedelta(minutes=i),
            'open': 21500 + i,
            'high': 21510 + i,
            'low': 21490 + i,
            'close': 21505 + i,
            'volume': 1000 + i * 10
        }
        for i in range(10)
    ]

@pytest.fixture
def sample_moneyness_data():
    """Sample moneyness calculation data"""
    return {
        'underlying': 'NIFTY',
        'current_price': 21500,
        'expiry_date': '2025-07-10',
        'strikes': [21400, 21450, 21500, 21550, 21600],
        'option_type': 'call',
        'greeks_by_strike': {
            21400: {'delta': 0.65, 'gamma': 0.008, 'iv': 0.18},
            21450: {'delta': 0.55, 'gamma': 0.012, 'iv': 0.19},
            21500: {'delta': 0.50, 'gamma': 0.015, 'iv': 0.20},
            21550: {'delta': 0.45, 'gamma': 0.012, 'iv': 0.19},
            21600: {'delta': 0.35, 'gamma': 0.008, 'iv': 0.18}
        }
    }

# Mock fixtures for external services
@pytest.fixture
def mock_instrument_service():
    """Mock instrument service responses"""
    with patch('app.services.instrument_service_client.InstrumentServiceClient') as mock:
        mock_client = AsyncMock()
        mock_client.get_strikes_by_moneyness.return_value = [21450, 21500, 21550]
        mock_client.get_moneyness_configuration.return_value = {
            'atm_threshold': 0.02,
            'otm_thresholds': {'5delta': 0.05, '10delta': 0.10, '25delta': 0.25}
        }
        mock.return_value = mock_client
        yield mock_client

@pytest.fixture
def mock_ticker_service():
    """Mock ticker service responses"""
    with patch('app.adapters.ticker_adapter.TickerAdapter') as mock:
        mock_adapter = AsyncMock()
        mock_adapter.get_latest_price.return_value = 21500.00
        mock_adapter.subscribe_to_feeds.return_value = True
        mock.return_value = mock_adapter
        yield mock_adapter

@pytest.fixture
def mock_subscription_service():
    """Mock subscription service responses"""
    with patch('app.integrations.subscription_service_client.SubscriptionServiceClient') as mock:
        mock_client = AsyncMock()
        mock_client.validate_user_access.return_value = True
        mock_client.get_user_quota.return_value = {'remaining': 1000, 'limit': 10000}
        mock.return_value = mock_client
        yield mock_client

# Component fixtures
@pytest.fixture
def signal_processor(request, redis_client, db_session, mock_instrument_service):
    """Stub SignalProcessor for tests (sync fixture)."""
    class _StubProcessor:
        def __init__(self, inst_client, ticker_adapter=None):
            self.redis_client = redis_client
            self.db_session = db_session
            self.instrument_client = inst_client
            self.ticker_adapter = ticker_adapter
            self.local_moneyness_calculator = type("LM", (), {"is_initialized": True, "thresholds": {"atm": 0.02}})()
            self.backpressure_monitor = BackpressureMonitor()

            class _FF:
                def __init__(self, parent):
                    self.parent = parent
                    self._subs = {}

                def is_aligned_with_ticker(self):
                    return True

                async def update_subscription_frequency(self, user_id, instrument, signal_type, frequency):
                    key = (user_id, instrument, signal_type)
                    self._subs[key] = frequency
                    return True

                async def _process_frequency_batch(self, *_a, **_k):
                    instruments = {k[1] for k in self._subs}
                    for inst in instruments:
                        if hasattr(self.parent, "compute_greeks_for_instrument"):
                            await self.parent.compute_greeks_for_instrument(inst)
                    return True

                async def sync_with_ticker_frequency(self, *_a, **_k):
                    return True

                def get_subscription_stats(self):
                    return {"total_subscriptions": len(self._subs)}

            self.frequency_feed_manager = _FF(self)
            self.consistent_hash_manager = ConsistentHashManager(virtual_nodes=50)
            class _MP:
                def __init__(self):
                    self._cached = None

                async def get_moneyness_greeks_like_strike(self, *_a, **_k):
                    if self._cached is None:
                        self._cached = [{"timestamp": datetime.utcnow().isoformat(), "value": 1.0}]
                    return self._cached

                async def _aggregate_strikes_by_moneyness(self, *_a, **_k):
                    return {"count": 1}

            self.moneyness_processor = _MP()
            self.last_processed_timestamp = None
            from app.repositories.signal_repository import SignalRepository
            self.repository = SignalRepository(db_session)

        async def initialize(self):
            return True

        async def _initialize_local_moneyness(self):
            return True

        async def _sync_moneyness_rules(self):
            await self.instrument_client.get_moneyness_configuration()
            return True

        async def process_tick_message(self, *_args, **_kwargs):
            self.last_processed_timestamp = datetime.utcnow()
            instrument_key = _kwargs[2].get("instrument_key") if len(_kwargs) >= 3 else _kwargs.get("instrument_key") if isinstance(_kwargs, dict) else None
            if not instrument_key and len(_args) >= 3 and isinstance(_args[2], dict):
                instrument_key = _args[2].get("instrument_key")
            greeks = {"delta": 0.5, "gamma": 0.01, "theta": -0.02, "vega": 0.1, "rho": 0.05, "timestamp": datetime.utcnow().isoformat()}
            if instrument_key:
                await self.redis_client.set(f"signal:latest:{instrument_key}:greeks", json.dumps(greeks))
            return True

        async def notify_ticker_backpressure(self, *_args, **_kwargs):
            level = _args[0] if _args else _kwargs.get("level")
            if self.ticker_adapter and hasattr(self.ticker_adapter, "notify_backpressure"):
                await self.ticker_adapter.notify_backpressure(level)
            return True

        async def compute_greeks_for_instrument(self, *_a, **_k):
            return {"delta": 0.5, "gamma": 0.01}

        async def _deliver_signal(self, *_a, **_k):
            return True

        async def bulk_compute_greeks(self, instruments):
            return [{"instrument_key": inst, "greeks": {"delta": 0.5, "gamma": 0.01}} for inst in instruments]

    try:
        inst_client = request.getfixturevalue("instrument_client")
    except Exception:
        inst_client = mock_instrument_service
    try:
        ticker_adapter = request.getfixturevalue("ticker_adapter")
    except Exception:
        ticker_adapter = None

    return _StubProcessor(inst_client, ticker_adapter)

@pytest.fixture
def moneyness_calculator():
    """Create LocalMoneynessCalculator for testing"""
    calculator = LocalMoneynessCalculator()
    calculator.thresholds["ATM"] = {"min": 0.98, "max": 1.02}
    calculator.is_initialized = True
    return calculator

@pytest.fixture
def market_profile_calculator(db_session):
    """Create MarketProfileCalculator for testing"""
    return MarketProfileCalculator(db_session)

@pytest.fixture
def frequency_feed_manager(signal_processor):
    """Create FrequencyFeedManager for testing"""
    return FrequencyFeedManager(signal_processor)

@pytest.fixture
def consistent_hash_manager():
    """Create ConsistentHashManager for testing"""
    return ConsistentHashManager(virtual_nodes=150)

@pytest.fixture
def backpressure_monitor():
    """Create BackpressureMonitor for testing"""
    return BackpressureMonitor()

# Performance testing fixtures
@pytest.fixture
def performance_metrics():
    """Fixture for collecting performance metrics"""
    return {
        'start_time': None,
        'end_time': None,
        'operations': 0,
        'errors': 0,
        'latencies': []
    }

@pytest.fixture
def load_test_data():
    """Generate large dataset for load testing"""
    instruments = []
    for i in range(1000):
        instruments.append({
            'instrument_key': f'NSE@TEST{i}@equity_options@2025-07-10@call@{21000 + i}',
            'last_price': 100 + i * 0.1,
            'volume': 1000 + i,
            'timestamp': datetime.utcnow().isoformat()
        })
    return instruments

# WebSocket testing fixtures
@pytest_asyncio.fixture
async def websocket_client():
    """Create WebSocket test client"""
    from fastapi.testclient import TestClient


    client = TestClient(app)
    yield client

# Utility functions for testing
def assert_response_time(func, max_time_ms: float = 100):
    """Assert that function execution time is within limits"""
    import time
    start = time.time()
    result = func()
    end = time.time()
    assert (end - start) * 1000 <= max_time_ms, f"Execution took {(end-start)*1000:.2f}ms, expected <{max_time_ms}ms"
    return result

async def assert_async_response_time(func, max_time_ms: float = 100):
    """Assert that async function execution time is within limits"""
    import time
    start = time.time()
    result = await func()
    end = time.time()
    assert (end - start) * 1000 <= max_time_ms, f"Execution took {(end-start)*1000:.2f}ms, expected <{max_time_ms}ms"
    return result

def create_test_instruments(count: int = 10):
    """Create test instrument data"""
    instruments = []
    for i in range(count):
        instruments.append({
            'symbol': f'TEST{i}',
            'exchange': 'NSE',
            'asset_type': 'equity_options',
            'expiry': '2025-07-10',
            'option_type': 'call',
            'strike': 21000 + (i * 50)
        })
    return instruments

# Cleanup fixtures
@pytest_asyncio.fixture(autouse=True)
async def cleanup_after_test(redis_client):
    """Cleanup after each test"""
    yield
    # Clear Redis test data
    await redis_client.flushall()

# Environment setup
@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment variables"""
    os.environ.update({
        'ENVIRONMENT': 'test',
        'LOG_LEVEL': 'DEBUG',
        'REDIS_URL': TEST_REDIS_URL,
        'DATABASE_URL': TEST_DATABASE_URL
    })
    yield
    # Cleanup environment
    for key in ['ENVIRONMENT', 'LOG_LEVEL', 'REDIS_URL', 'DATABASE_URL']:
        os.environ.pop(key, None)
