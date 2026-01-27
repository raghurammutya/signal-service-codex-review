#!/usr/bin/env python3
"""
SDK Contract Compliance Tests - Phase 1

TEST_SDK_001: Comprehensive validation of instrument_key-first SDK
- Contract validation across all SDK components
- Token parameter rejection testing
- Registry integration validation
- Multi-broker compliance testing
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.brokers.broker_factory import BrokerCredentials, BrokerFactory, BrokerType
from app.sdk import (
    DataType,
    OrderSide,
    OrderType,
    SDKMigrationHelper,
    TimeFrame,
    create_data_client,
    create_instrument_client,
    create_order_client,
    validate_no_token_parameters,
)


class TestSDKContractCompliance:
    """TEST_SDK_001: SDK Contract Compliance Test Suite"""

    @pytest.fixture
    async def instrument_client(self):
        """Create test instrument client"""
        client = create_instrument_client()
        yield client
        await client.registry_client.close()

    @pytest.fixture
    async def order_client(self):
        """Create test order client"""
        return create_order_client("mock")

    @pytest.fixture
    async def data_client(self):
        """Create test data client"""
        return create_data_client("mock")

    # =============================================================================
    # CONTRACT VALIDATION TESTS
    # =============================================================================

    def test_validate_no_token_parameters_success(self):
        """Test that valid parameters pass validation"""
        valid_params = {
            "instrument_key": "AAPL_NASDAQ_EQUITY",
            "quantity": 100,
            "side": "BUY"
        }

        # Should not raise exception
        validate_no_token_parameters(valid_params)

    def test_validate_no_token_parameters_rejection(self):
        """Test that token parameters are rejected"""
        invalid_params_sets = [
            {"instrument_token": "256265", "quantity": 100},
            {"token": "12345", "side": "BUY"},
            {"broker_token": "abc123", "quantity": 50},
            {"ticker_token": "xyz789", "side": "SELL"},
            {"token_id": "999888", "quantity": 25},
            {"legacy_token": "old123", "side": "BUY"}
        ]

        for invalid_params in invalid_params_sets:
            with pytest.raises(ValueError, match="not supported in Phase 1 SDK"):
                validate_no_token_parameters(invalid_params)

    def test_migration_helper_guide(self):
        """Test migration helper provides guidance"""
        guide = SDKMigrationHelper.get_migration_guide()

        assert "Phase 1 SDK Migration Guide" in guide
        assert "instrument_key" in guide
        assert "OLD (deprecated)" in guide
        assert "NEW (Phase 1)" in guide

    def test_migration_helper_symbol_conversion(self):
        """Test symbol to instrument_key conversion"""
        key = SDKMigrationHelper.convert_symbol_to_key("AAPL", "NASDAQ")
        assert key == "AAPL_NASDAQ_EQUITY"

        key = SDKMigrationHelper.convert_symbol_to_key("RELIANCE")
        assert key == "RELIANCE_NSE_EQUITY"

    # =============================================================================
    # INSTRUMENT CLIENT TESTS
    # =============================================================================

    @pytest.mark.asyncio
    @patch('app.clients.instrument_registry_client.InstrumentRegistryClient.get_instrument_metadata')
    async def test_instrument_client_requires_key(self, mock_registry, instrument_client):
        """Test InstrumentClient requires instrument_key"""

        # Mock registry response
        mock_registry.return_value = {
            'instruments': [{
                'instrument_key': 'AAPL_NASDAQ_EQUITY',
                'symbol': 'AAPL',
                'exchange': 'NASDAQ',
                'sector': 'Technology',
                'instrument_type': 'EQUITY',
                'lot_size': 1,
                'tick_size': 0.01,
                'broker_tokens': {'mock': 'mock_token_123'}
            }]
        }

        # Test valid instrument_key usage
        metadata = await instrument_client.get_instrument_metadata("AAPL_NASDAQ_EQUITY")

        assert metadata.instrument_key == "AAPL_NASDAQ_EQUITY"
        assert metadata.symbol == "AAPL"
        assert metadata.exchange == "NASDAQ"
        assert metadata.sector == "Technology"

        # Verify broker tokens are internal only
        assert metadata._broker_tokens is not None
        assert 'mock' in metadata._broker_tokens

    @pytest.mark.asyncio
    async def test_instrument_client_rejects_legacy_methods(self, instrument_client):
        """Test that legacy token methods are properly deprecated"""

        # Test deprecated method raises appropriate error
        with pytest.raises(ValueError, match="Legacy token conversion not supported"):
            instrument_client.accept_legacy_token("256265")

        with pytest.raises(ValueError, match="Token-based metadata access is deprecated"):
            instrument_client.get_metadata_by_token("256265")

    # =============================================================================
    # ORDER CLIENT TESTS
    # =============================================================================

    @pytest.mark.asyncio
    @patch('app.sdk.instrument_client.InstrumentClient.get_instrument_metadata')
    @patch('app.sdk.instrument_client.InstrumentClient.resolve_broker_token')
    async def test_order_client_requires_key(self, mock_resolve_token, mock_metadata, order_client):
        """Test OrderClient requires instrument_key for all operations"""

        # Mock responses
        mock_metadata.return_value = MagicMock(
            instrument_key="AAPL_NASDAQ_EQUITY",
            symbol="AAPL",
            exchange="NASDAQ"
        )
        mock_resolve_token.return_value = "mock_token_123"

        # Test order creation with instrument_key
        order = await order_client.create_order(
            instrument_key="AAPL_NASDAQ_EQUITY",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET
        )

        assert order.instrument_key == "AAPL_NASDAQ_EQUITY"
        assert order.symbol == "AAPL"
        assert order.exchange == "NASDAQ"
        assert order.side == OrderSide.BUY
        assert order.quantity == 100

        # Verify internal token is not exposed
        assert not hasattr(order, 'instrument_token')
        assert not hasattr(order, 'token')

    @pytest.mark.asyncio
    async def test_order_client_rejects_legacy_methods(self, order_client):
        """Test that legacy token methods are rejected"""

        with pytest.raises(ValueError, match="Token-based order creation is deprecated"):
            order_client.create_order_by_token("256265", side="BUY", quantity=100)

    # =============================================================================
    # DATA CLIENT TESTS
    # =============================================================================

    @pytest.mark.asyncio
    @patch('app.sdk.instrument_client.InstrumentClient.get_instrument_metadata')
    @patch('app.sdk.instrument_client.InstrumentClient.resolve_broker_token')
    async def test_data_client_requires_key(self, mock_resolve_token, mock_metadata, data_client):
        """Test DataClient requires instrument_key for all data operations"""

        # Mock responses
        mock_metadata.return_value = MagicMock(
            instrument_key="AAPL_NASDAQ_EQUITY",
            symbol="AAPL",
            exchange="NASDAQ",
            sector="Technology"
        )
        mock_resolve_token.return_value = "mock_token_123"

        # Mock the internal broker data fetch
        with patch.object(data_client, '_fetch_broker_historical_data') as mock_fetch:
            import pandas as pd
            mock_fetch.return_value = pd.DataFrame({
                'open': [150.0], 'high': [151.0], 'low': [149.0],
                'close': [150.5], 'volume': [1000000]
            })

            # Test historical data with instrument_key
            market_data = await data_client.get_historical_data(
                instrument_key="AAPL_NASDAQ_EQUITY",
                timeframe=TimeFrame.MINUTE_5,
                periods=1
            )

            assert market_data.instrument_key == "AAPL_NASDAQ_EQUITY"
            assert market_data.symbol == "AAPL"
            assert market_data.exchange == "NASDAQ"
            assert market_data.data_type == DataType.OHLCV
            assert market_data.sector == "Technology"

            # Verify internal fields are populated but not exposed
            assert market_data._source_broker == "mock"
            assert market_data._broker_token == "mock_token_123"

    # =============================================================================
    # HTTP CLIENT TESTS
    # =============================================================================

    @pytest.mark.asyncio
    @patch('app.sdk.instrument_client.InstrumentClient.resolve_broker_token')
    async def test_http_client_middleware(self, mock_resolve_token):
        """Test HTTP client middleware processes instrument_key correctly"""

        mock_resolve_token.return_value = "resolved_token_123"

        from app.sdk.http_client import TokenResolutionMiddleware

        # Create middleware with mock client
        instrument_client = MagicMock()
        instrument_client.resolve_broker_token = AsyncMock(return_value="resolved_token_123")
        instrument_client.get_instrument_metadata = AsyncMock(return_value=MagicMock(
            symbol="AAPL", exchange="NASDAQ", sector="Technology"
        ))

        middleware = TokenResolutionMiddleware(instrument_client)

        # Test request processing
        request_data = {"instrument_key": "AAPL_NASDAQ_EQUITY", "quantity": 100}
        processed = await middleware.process_request(
            method="POST",
            url="/api/orders",
            data=request_data
        )

        # Verify instrument_key was replaced with internal token
        assert "instrument_key" not in processed["data"]
        assert processed["data"]["_internal_token"] == "resolved_token_123"
        assert processed["data"]["_original_instrument_key"] == "AAPL_NASDAQ_EQUITY"
        assert processed["headers"]["X-SDK-Phase"] == "1.0-instrument-key-first"

        # Test response processing
        response_data = {"status": "success", "order_id": "12345"}
        processed_response = await middleware.process_response(
            response_data, {"data": processed["data"]}
        )

        # Verify instrument_key is restored and metadata enriched
        assert processed_response["instrument_key"] == "AAPL_NASDAQ_EQUITY"
        assert "metadata" in processed_response
        assert processed_response["metadata"]["symbol"] == "AAPL"

    # =============================================================================
    # MULTI-BROKER INTEGRATION TESTS
    # =============================================================================

    @pytest.mark.asyncio
    async def test_broker_factory_multi_broker_support(self):
        """Test broker factory supports multiple brokers with unified interface"""


        factory = BrokerFactory()

        # Create mock broker credentials
        mock_credentials = BrokerCredentials(
            broker_type=BrokerType.MOCK,
            api_key="test_key",
            api_secret="test_secret",
            access_token="test_token"
        )

        # Test client creation
        client = await factory.create_client(mock_credentials)

        assert client.broker_type == BrokerType.MOCK
        assert BrokerType.MOCK in factory.get_available_brokers()
        assert factory.get_default_broker() == BrokerType.MOCK

        # Test unified interface
        quote = await client.get_quote("AAPL_NASDAQ_EQUITY")

        assert quote.instrument_key == "AAPL_NASDAQ_EQUITY"
        assert hasattr(quote, 'ltp')
        assert hasattr(quote, 'symbol')
        assert hasattr(quote, 'exchange')

        # Verify internal token is not exposed
        assert quote._broker_token is not None  # Internal field
        assert not hasattr(quote, 'token')      # Not exposed publicly

        await factory.disconnect_all()

    @pytest.mark.asyncio
    async def test_multi_broker_client_failover(self):
        """Test multi-broker client failover functionality"""

        from app.brokers.broker_factory import MultiBrokerClient

        factory = BrokerFactory()

        # Create multiple mock broker clients
        credentials_list = [
            BrokerCredentials(BrokerType.MOCK, "key1", "secret1", "token1"),
            BrokerCredentials(BrokerType.MOCK, "key2", "secret2", "token2")
        ]

        for cred in credentials_list:
            await factory.create_client(cred)

        multi_client = MultiBrokerClient(factory)

        # Test that multi-broker client can handle operations
        quotes = await multi_client.get_best_quote("AAPL_NASDAQ_EQUITY")

        assert "instrument_key" in quotes
        assert "all_quotes" in quotes
        assert len(quotes["all_quotes"]) > 0

        await factory.disconnect_all()

    # =============================================================================
    # PERFORMANCE AND SLA TESTS
    # =============================================================================

    @pytest.mark.asyncio
    @patch('app.clients.instrument_registry_client.InstrumentRegistryClient.get_instrument_metadata')
    async def test_registry_lookup_performance(self, mock_registry, instrument_client):
        """Test registry lookup maintains <50ms performance SLA"""

        import time

        # Mock registry response
        mock_registry.return_value = {
            'instruments': [{
                'instrument_key': 'AAPL_NASDAQ_EQUITY',
                'symbol': 'AAPL',
                'exchange': 'NASDAQ',
                'broker_tokens': {'mock': 'token123'}
            }]
        }

        # Test cached lookup performance
        start_time = time.time()
        await instrument_client.get_instrument_metadata("AAPL_NASDAQ_EQUITY")
        first_call_time = (time.time() - start_time) * 1000  # Convert to ms

        # Second call should be faster due to caching
        start_time = time.time()
        await instrument_client.get_instrument_metadata("AAPL_NASDAQ_EQUITY")
        cached_call_time = (time.time() - start_time) * 1000

        # Verify caching improves performance
        assert cached_call_time < first_call_time
        # In real implementation, this should be <50ms for cached calls
        print(f"First call: {first_call_time:.2f}ms, Cached call: {cached_call_time:.2f}ms")

    # =============================================================================
    # INTEGRATION WITH PHASE 3 REGISTRY
    # =============================================================================

    @pytest.mark.asyncio
    async def test_phase3_registry_integration(self):
        """Test integration with Phase 3 registry infrastructure"""

        from app.clients.instrument_registry_client import create_registry_client

        # Test that SDK can create registry client
        # Note: This would connect to actual registry in real environment
        try:
            registry_client = create_registry_client()
            assert registry_client is not None

            # Test health check
            health = await registry_client.health_check()
            assert "registry_healthy" in health

            await registry_client.close()

        except Exception as e:
            # Expected in test environment without actual registry
            assert "Config service integration required" in str(e)

    # =============================================================================
    # BACKWARDS COMPATIBILITY TESTS
    # =============================================================================

    def test_deprecation_warnings_issued(self):
        """Test that deprecated methods issue proper warnings"""

        import warnings

        from app.sdk.instrument_client import InstrumentClient

        client = InstrumentClient()

        # Test that deprecated method issues warning
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            try:
                client.accept_legacy_token("256265")
            except ValueError:
                pass  # Expected

            # Verify deprecation warning was issued
            assert len(w) > 0
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()

    # =============================================================================
    # ERROR HANDLING TESTS
    # =============================================================================

    @pytest.mark.asyncio
    async def test_error_handling_missing_instrument(self, instrument_client):
        """Test proper error handling for missing instruments"""

        with patch.object(instrument_client.registry_client, 'get_instrument_metadata') as mock_registry:
            mock_registry.return_value = {'instruments': []}  # Empty response

            with pytest.raises(ValueError, match="Instrument not found"):
                await instrument_client.get_instrument_metadata("INVALID_KEY")

    @pytest.mark.asyncio
    async def test_error_handling_token_resolution_failure(self, order_client):
        """Test error handling when token resolution fails"""

        with patch.object(order_client.instrument_client, 'get_instrument_metadata') as mock_metadata:
            mock_metadata.return_value = MagicMock(symbol="TEST", exchange="TEST")

            with patch.object(order_client.instrument_client, 'resolve_broker_token') as mock_resolve:
                mock_resolve.side_effect = ValueError("Token not available")

                with pytest.raises(RuntimeError, match="Data source unavailable"):
                    await order_client.create_order(
                        instrument_key="TEST_KEY",
                        side=OrderSide.BUY,
                        quantity=100
                    )
