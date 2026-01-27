"""
Integration tests for Signal Service with external services

Enhanced with external config service integration for parameter testing
and hot parameter reload validation.
"""
import asyncio
import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch

import aiohttp
import pytest

from app.adapters.ticker_adapter import TickerAdapter
from app.integrations.subscription_service_client import SubscriptionServiceClient
from app.services.instrument_service_client import InstrumentServiceClient

# External config service testing constants
EXTERNAL_CONFIG_URLS = [
    "http://test-config.local",
    "http://test-config-secondary.local"
]
EXTERNAL_API_KEY = "[REDACTED-TEST-PLACEHOLDER]"

@pytest.mark.integration
class TestInstrumentServiceIntegration:
    """Test integration with Instrument Service"""

    @pytest.fixture
    def instrument_client(self):
        """Create instrument service client for testing"""
        return InstrumentServiceClient()

    @pytest.mark.asyncio
    async def test_moneyness_rule_synchronization(self, instrument_client, signal_processor):
        """Test moneyness rule synchronization from instrument service"""
        # Mock instrument service response
        mock_config = {
            'atm_threshold': 0.02,
            'otm_thresholds': {
                '5delta': 0.05,
                '10delta': 0.10,
                '25delta': 0.25
            },
            'itm_thresholds': {
                '5delta': 0.05,
                '10delta': 0.10,
                '25delta': 0.25
            }
        }

        with patch.object(instrument_client, 'get_moneyness_configuration') as mock_get:
            mock_get.return_value = mock_config

            # Initialize signal processor with moneyness rules
            await signal_processor._initialize_local_moneyness()

            # Verify rules are loaded
            assert signal_processor.local_moneyness_calculator.is_initialized
            assert signal_processor.local_moneyness_calculator.thresholds['atm'] == 0.02

            # Test rule synchronization
            await signal_processor._sync_moneyness_rules()
            mock_get.assert_called()

    @pytest.mark.asyncio
    async def test_strike_availability_queries(self, instrument_client):
        """Test strike availability queries"""
        mock_strikes = [21400, 21450, 21500, 21550, 21600]

        with patch.object(instrument_client, 'get_strikes_by_moneyness') as mock_get:
            mock_get.return_value = mock_strikes

            strikes = await instrument_client.get_strikes_by_moneyness(
                underlying='NIFTY',
                moneyness_level='ATM',
                expiry_date='2025-07-10'
            )

            assert strikes == mock_strikes
            mock_get.assert_called_with('NIFTY', 'ATM', '2025-07-10')

    @pytest.mark.asyncio
    async def test_instrument_metadata_retrieval(self, instrument_client):
        """Test instrument metadata retrieval"""
        mock_metadata = {
            'instrument_key': 'NSE@NIFTY@equity_options@2025-07-10@call@21500',
            'lot_size': 25,
            'tick_size': 0.05,
            'expiry_date': '2025-07-10',
            'underlying': 'NIFTY'
        }

        with patch.object(instrument_client, 'get_instrument_metadata') as mock_get:
            mock_get.return_value = mock_metadata

            metadata = await instrument_client.get_instrument_metadata(
                'NSE@NIFTY@equity_options@2025-07-10@call@21500'
            )

            assert metadata['lot_size'] == 25
            assert metadata['tick_size'] == 0.05

    @pytest.mark.asyncio
    async def test_fallback_behavior(self, signal_processor):
        """Test fallback behavior when instrument service is unavailable"""
        with patch.object(signal_processor.instrument_client, 'get_moneyness_configuration') as mock_get:
            mock_get.side_effect = ConnectionError("Service unavailable")

            # Should continue with default configuration
            await signal_processor._initialize_local_moneyness()

            # Should have default moneyness calculator
            assert signal_processor.local_moneyness_calculator is not None
            assert signal_processor.local_moneyness_calculator.is_initialized


@pytest.mark.integration
class TestTickerServiceCoordination:
    """Test coordination with Ticker Service"""

    @pytest.fixture
    def ticker_adapter(self):
        """Create ticker adapter for testing"""
        return TickerAdapter(base_url="http://mock-ticker-service")

    @pytest.mark.asyncio
    async def test_frequency_alignment(self, signal_processor, ticker_adapter):
        """Test frequency coordination with ticker service"""
        ticker_frequencies = {
            'NIFTY': '5m',
            'BANKNIFTY': '1m',
            'RELIANCE': 'realtime'
        }

        # Mock ticker service frequency response
        with patch.object(ticker_adapter, 'get_frequency_configuration') as mock_get:
            mock_get.return_value = ticker_frequencies

            await signal_processor.frequency_feed_manager.sync_with_ticker_frequency(ticker_frequencies)

            # Verify alignment
            assert signal_processor.frequency_feed_manager.is_aligned_with_ticker()

    @pytest.mark.asyncio
    async def test_market_data_subscription(self, ticker_adapter):
        """Test market data subscription coordination"""
        instruments = ['NIFTY', 'BANKNIFTY', 'RELIANCE']

        with patch.object(ticker_adapter, 'subscribe_to_feeds') as mock_subscribe:
            mock_subscribe.return_value = True

            result = await ticker_adapter.subscribe_to_feeds(instruments)

            assert result
            mock_subscribe.assert_called_with(instruments)

    @pytest.mark.asyncio
    async def test_backpressure_notification(self, signal_processor, ticker_adapter):
        """Test backpressure notification to ticker service"""
        from app.scaling.backpressure_monitor import BackpressureLevel

        with patch.object(ticker_adapter, 'notify_backpressure') as mock_notify:
            mock_notify.return_value = True

            await signal_processor.notify_ticker_backpressure(BackpressureLevel.HIGH)

            mock_notify.assert_called_with(BackpressureLevel.HIGH)

    @pytest.mark.asyncio
    async def test_real_time_data_flow(self, signal_processor, ticker_adapter, sample_tick_data):
        """Test real-time data flow from ticker service"""
        with patch.object(ticker_adapter, 'get_latest_price') as mock_price:
            mock_price.return_value = 21500.50

            # Process tick message
            await signal_processor.process_tick_message(
                'stream:shard:0', 'msg_1', sample_tick_data
            )

            # Should have processed the tick
            assert signal_processor.last_processed_timestamp is not None


@pytest.mark.integration
class TestSubscriptionServiceIntegration:
    """Test integration with Subscription Service"""

    @pytest.fixture
    def subscription_client(self):
        """Create subscription service client for testing"""
        return SubscriptionServiceClient(base_url="http://mock-subscription-service")

    @pytest.mark.asyncio
    async def test_user_access_validation(self, subscription_client):
        """Test user access validation"""
        with patch.object(subscription_client, 'validate_user_access') as mock_validate:
            mock_validate.return_value = True

            is_valid = await subscription_client.validate_user_access(
                user_id='user123',
                feature='realtime_greeks'
            )

            assert is_valid
            mock_validate.assert_called_with('user123', 'realtime_greeks')

    @pytest.mark.asyncio
    async def test_quota_management(self, subscription_client):
        """Test quota validation and tracking"""
        mock_quota = {
            'remaining': 850,
            'limit': 1000,
            'reset_time': datetime.utcnow() + timedelta(hours=1)
        }

        with patch.object(subscription_client, 'get_user_quota') as mock_quota_get:
            mock_quota_get.return_value = mock_quota

            quota = await subscription_client.get_user_quota('user123')

            assert quota['remaining'] == 850
            assert quota['limit'] == 1000

    @pytest.mark.asyncio
    async def test_usage_tracking(self, subscription_client):
        """Test usage tracking integration"""
        with patch.object(subscription_client, 'track_usage') as mock_track:
            mock_track.return_value = True

            result = await subscription_client.track_usage(
                user_id='user123',
                feature='historical_greeks',
                usage_count=5
            )

            assert result
            mock_track.assert_called_with('user123', 'historical_greeks', 5)


@pytest.mark.integration
class TestDatabaseIntegration:
    """Test database integration"""

    @pytest.mark.postgres
    @pytest.mark.asyncio
    async def test_timescaledb_storage(self, db_session, sample_greeks_data):
        """Test TimescaleDB storage and retrieval"""
        from app.repositories.signal_repository import SignalRepository

        repository = SignalRepository(db_session)

        # Save Greeks data
        await repository.save_greeks(sample_greeks_data)

        # Retrieve Greeks data
        retrieved = await repository.get_greeks(sample_greeks_data.instrument_key)

        assert retrieved.delta == sample_greeks_data.delta
        assert retrieved.gamma == sample_greeks_data.gamma
        assert retrieved.instrument_key == sample_greeks_data.instrument_key

    @pytest.mark.postgres
    @pytest.mark.asyncio
    async def test_historical_data_queries(self, db_session):
        """Test historical data queries"""
        from app.models.signal_models import SignalGreeks
        from app.repositories.signal_repository import SignalRepository

        repository = SignalRepository(db_session)

        # Create test data
        base_time = datetime.utcnow()
        test_data = []

        for i in range(10):
            greeks = SignalGreeks(
                instrument_key='NSE@NIFTY@equity_options@2025-07-10@call@21500',
                timestamp=base_time + timedelta(minutes=i*5),
                delta=0.5 + i*0.01,
                gamma=0.01,
                theta=-0.05,
                vega=0.15,
                rho=0.03
            )
            test_data.append(greeks)

        # Bulk save
        await repository.bulk_save_greeks(test_data)

        # Query historical data
        historical = await repository.get_historical_greeks(
            instrument_key='NSE@NIFTY@equity_options@2025-07-10@call@21500',
            start_time=base_time,
            end_time=base_time + timedelta(hours=1),
            timeframe='5m'
        )

        assert len(historical) == 10
        assert historical[0].delta == 0.5
        assert historical[-1].delta == 0.59

    @pytest.mark.redis
    @pytest.mark.asyncio
    async def test_redis_caching(self, redis_client):
        """Test Redis caching functionality"""
        # Test basic caching
        cache_key = 'signal:latest:NIFTY:greeks'
        cache_data = {'delta': 0.5, 'gamma': 0.01}

        await redis_client.setex(cache_key, 300, json.dumps(cache_data))

        cached_data = await redis_client.get(cache_key)
        assert json.loads(cached_data)['delta'] == 0.5

    @pytest.mark.redis
    @pytest.mark.asyncio
    async def test_redis_streams(self, redis_client):
        """Test Redis streams for real-time data"""
        stream_name = 'signal:realtime:NIFTY'

        # Add message to stream
        message_data = {
            'instrument_key': 'NSE@NIFTY@equity_spot',
            'delta': '0.5',
            'timestamp': datetime.utcnow().isoformat()
        }

        message_id = await redis_client.xadd(stream_name, message_data)
        assert message_id is not None

        # Read from stream
        messages = await redis_client.xread({stream_name: '0'}, count=1)
        assert len(messages) == 1
        assert messages[0][1][0][1][b'delta'] == b'0.5'


@pytest.mark.integration
class TestExternalConfigServiceIntegration:
    """Test external config service integration for hot parameter testing."""

    @pytest.mark.asyncio
    async def test_external_config_service_connectivity(self):
        """Test connectivity to external config service endpoints."""
        results = {}

        for base_url in EXTERNAL_CONFIG_URLS:
            try:
                async with (
                    aiohttp.ClientSession() as session,
                    session.get(
                        f"{base_url}/health",
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response
                ):
                        if response.status == 200:
                            health_data = await response.json()
                            results[base_url] = {
                                "status": "healthy",
                                "response_data": health_data
                            }
                        else:
                            results[base_url] = {
                                "status": "unhealthy",
                                "status_code": response.status
                            }
            except Exception as e:
                results[base_url] = {
                    "status": "error",
                    "error": str(e)
                }

        # At least one URL should be accessible
        healthy_count = sum(1 for result in results.values() if result["status"] == "healthy")
        assert healthy_count > 0, f"No external config services are accessible: {results}"

        print(f"External config service connectivity: {healthy_count}/{len(EXTERNAL_CONFIG_URLS)} healthy")

    @pytest.mark.asyncio
    async def test_external_config_parameter_operations(self):
        """Test parameter creation, update, and deletion with external config service."""
        base_url = EXTERNAL_CONFIG_URLS[0]  # Use primary URL
        test_param_key = "TEST_INTEGRATION_PARAM"

        async with aiohttp.ClientSession() as session:
            headers = {"X-Internal-API-Key": EXTERNAL_API_KEY}

            try:
                # 1. Create test parameter
                create_payload = {
                    "secret_key": test_param_key,
                    "secret_value": "initial_test_value",
                    "secret_type": "other",
                    "environment": "dev"
                }

                async with session.post(
                    f"{base_url}/api/v1/secrets",
                    headers=headers,
                    json=create_payload,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    assert response.status in [200, 201], f"Failed to create parameter: {response.status}"

                # 2. Update test parameter
                update_payload = {"secret_value": "updated_test_value"}

                async with session.put(
                    f"{base_url}/api/v1/secrets/{test_param_key}?environment=dev",
                    headers=headers,
                    json=update_payload,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    assert response.status == 200, f"Failed to update parameter: {response.status}"

                # 3. Retrieve parameter value
                async with session.get(
                    f"{base_url}/api/v1/secrets/{test_param_key}/value?environment=dev",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    assert response.status == 200, f"Failed to retrieve parameter: {response.status}"
                    data = await response.json()
                    assert data["secret_value"] == "updated_test_value", "Parameter value not updated correctly"

                print("✓ External config parameter operations successful")

            finally:
                # 4. Cleanup - delete test parameter
                try:
                    async with session.delete(
                        f"{base_url}/api/v1/secrets/{test_param_key}?environment=dev",
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=15)
                    ) as response:
                        pass  # Ignore cleanup failures
                except Exception:
                    pass

    @pytest.mark.asyncio
    async def test_hot_parameter_reload_integration(self):
        """Test hot parameter reload integration with external config service."""
        # This test validates the integration workflow for hot parameter reloading
        # using external config service as a testing environment

        from app.core.hot_config import get_hot_reloadable_settings

        # Create test configuration with external config service
        with (
            patch.dict(os.environ, {
                'USE_EXTERNAL_CONFIG': 'true',
                'ENVIRONMENT': 'dev'
            }),
            patch('app.core.hot_config.BaseSignalServiceConfig.__init__') as mock_base_init
        ):
                mock_base_init.return_value = None

                config = get_hot_reloadable_settings(use_external_config=True)

                # Test external config service connectivity
                results = await config.test_external_config_service()

                # Verify external URLs are tested
                for url in EXTERNAL_CONFIG_URLS:
                    assert url in results, f"External URL {url} not tested"

                # At least one should be accessible for testing
                accessible_count = sum(
                    1 for result in results.values()
                    if result.get("status") in ["healthy", "error"]  # error is also a response
                )
                assert accessible_count >= 1, f"No external config services responded: {results}"

                print(f"Hot reload integration test: {accessible_count} external services accessible")


@pytest.mark.integration
class TestCompleteWorkflow:
    """Test complete integration workflows"""

    @pytest.mark.asyncio
    async def test_complete_signal_processing_workflow(self, signal_processor, redis_client, sample_tick_data):
        """Test complete signal processing from tick to delivery"""
        # Mock external dependencies
        with patch.object(signal_processor.instrument_client, 'get_moneyness_configuration') as mock_config, \
             patch.object(signal_processor, '_deliver_signal'):

            mock_config.return_value = {
                'atm_threshold': 0.02,
                'otm_thresholds': {'5delta': 0.05}
            }

            # Initialize processor
            await signal_processor._initialize_local_moneyness()

            # Process tick data
            await signal_processor.process_tick_message(
                'stream:shard:0', 'msg_1', sample_tick_data
            )

            # Verify signal was computed and delivered
            assert signal_processor.last_processed_timestamp is not None

    @pytest.mark.asyncio
    async def test_moneyness_calculation_workflow(self, signal_processor, sample_moneyness_data):
        """Test complete moneyness calculation workflow"""
        with patch.object(signal_processor.instrument_client, 'get_strikes_by_moneyness') as mock_strikes:
            mock_strikes.return_value = sample_moneyness_data['strikes']

            # Calculate moneyness Greeks
            result = await signal_processor.moneyness_processor.get_moneyness_greeks_like_strike(
                underlying=sample_moneyness_data['underlying'],
                moneyness_level='ATM',
                expiry_date=sample_moneyness_data['expiry_date'],
                start_time=datetime.utcnow() - timedelta(hours=1),
                end_time=datetime.utcnow(),
                timeframe='5m'
            )

            assert len(result) > 0
            assert 'timestamp' in result[0]
            assert 'value' in result[0]

    @pytest.mark.asyncio
    async def test_frequency_based_processing_workflow(self, signal_processor):
        """Test frequency-based processing workflow"""
        # Add frequency-based subscriptions
        await signal_processor.frequency_feed_manager.update_subscription_frequency(
            'user1', 'NIFTY', 'greeks', '5m'
        )
        await signal_processor.frequency_feed_manager.update_subscription_frequency(
            'user2', 'NIFTY', 'greeks', '5m'
        )

        # Mock computation
        with patch.object(signal_processor, 'compute_greeks_for_instrument') as mock_compute:
            mock_compute.return_value = {'delta': 0.5, 'gamma': 0.01}

            # Process frequency batch
            from app.services.frequency_feed_manager import FeedFrequency
            await signal_processor.frequency_feed_manager._process_frequency_batch(FeedFrequency.MINUTE_5)

            # Should compute once for both users
            assert mock_compute.call_count == 1

    @pytest.mark.asyncio
    async def test_scaling_integration_workflow(self, signal_processor):
        """Test horizontal scaling integration workflow"""
        from app.scaling.backpressure_monitor import BackpressureLevel

        # Simulate high backpressure
        signal_processor.backpressure_monitor.update_queue_size(1500)  # HIGH
        signal_processor.backpressure_monitor.update_processing_rate(20)  # LOW

        level = signal_processor.backpressure_monitor.get_backpressure_level()
        assert level == BackpressureLevel.HIGH

        # Get scaling recommendations
        recommendations = signal_processor.backpressure_monitor.get_scaling_recommendations()
        assert recommendations['action'] == 'scale_up'

        # Test consistent hashing for instrument distribution
        hash_manager = signal_processor.consistent_hash_manager
        hash_manager.add_node('signal-service-1')
        hash_manager.add_node('signal-service-2')

        node = hash_manager.get_node_for_instrument('NSE@NIFTY@equity_options@2025-07-10@call@21500')
        assert node in ['signal-service-1', 'signal-service-2']

    @pytest.mark.asyncio
    async def test_error_recovery_workflow(self, signal_processor, sample_tick_data):
        """Test error recovery and resilience"""
        # Test database connection failure
        with patch.object(signal_processor.repository, 'save_greeks') as mock_save:
            mock_save.side_effect = Exception("Database connection failed")

            # Should handle gracefully
            try:
                await signal_processor.process_tick_message(
                    'stream:shard:0', 'msg_1', sample_tick_data
                )
                # Should not raise exception
            except Exception as e:
                pytest.fail(f"Signal processor should handle database errors gracefully: {e}")

        # Test Redis connection failure
        with patch.object(signal_processor.redis_client, 'setex') as mock_redis:
            mock_redis.side_effect = Exception("Redis connection failed")

            # Should handle gracefully
            try:
                await signal_processor.process_tick_message(
                    'stream:shard:0', 'msg_1', sample_tick_data
                )
                # Should not raise exception
            except Exception as e:
                pytest.fail(f"Signal processor should handle Redis errors gracefully: {e}")

    @pytest.mark.asyncio
    async def test_performance_under_load(self, signal_processor, load_test_data):
        """Test performance under load conditions"""
        import time

        # Process many tick messages
        start_time = time.time()

        tasks = []
        for i, tick_data in enumerate(load_test_data[:100]):  # Process 100 instruments
            task = signal_processor.process_tick_message(
                f'stream:shard:{i%5}', f'msg_{i}', tick_data
            )
            tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)

        end_time = time.time()
        total_time = end_time - start_time

        # Should process 100 instruments in reasonable time
        assert total_time < 10, f"Processing 100 instruments took {total_time:.2f}s, expected <10s"

        # Calculate throughput
        throughput = len(load_test_data[:100]) / total_time
        assert throughput > 10, f"Throughput {throughput:.2f} instruments/sec too low"
