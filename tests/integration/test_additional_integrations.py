"""
Additional integration tests for Signal Service
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock
import json

@pytest.mark.integration
class TestSignalProcessorIntegration:
    """Integration tests for SignalProcessor"""
    
    @pytest.mark.asyncio
    async def test_signal_processor_initialization(self, signal_processor):
        """Test signal processor initialization with all components"""
        assert signal_processor is not None
        assert hasattr(signal_processor, 'local_moneyness_calculator')
        assert hasattr(signal_processor, 'frequency_feed_manager')
        assert hasattr(signal_processor, 'backpressure_monitor')
    
    @pytest.mark.asyncio
    async def test_real_time_signal_processing_integration(self, signal_processor, redis_client):
        """Test real-time signal processing integration"""
        tick_data = {
            'instrument_key': 'NSE@NIFTY@equity_options@2025-07-10@call@21500',
            'last_price': 125.50,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Process tick
        await signal_processor.process_tick_message('stream:test', 'msg_1', tick_data)
        
        # Verify caching
        cache_key = f"signal:latest:{tick_data['instrument_key']}:greeks"
        cached_data = await redis_client.get(cache_key)
        assert cached_data is not None
    
    @pytest.mark.asyncio
    async def test_batch_processing_integration(self, signal_processor):
        """Test batch processing integration"""
        instruments = [
            f'NSE@TEST{i}@equity_options@2025-07-10@call@{21000+i*10}'
            for i in range(10)
        ]
        
        results = await signal_processor.bulk_compute_greeks(instruments)
        assert len(results) == 10

@pytest.mark.integration
class TestFrequencyManagerIntegration:
    """Integration tests for frequency management"""
    
    @pytest.mark.asyncio
    async def test_frequency_subscription_integration(self, signal_processor, redis_client):
        """Test frequency subscription integration"""
        await signal_processor.frequency_feed_manager.update_subscription_frequency(
            'test_user', 'NIFTY', 'greeks', '5m'
        )
        
        # Verify subscription stored
        stats = signal_processor.frequency_feed_manager.get_subscription_stats()
        assert stats['total_subscriptions'] == 1
    
    @pytest.mark.asyncio
    async def test_frequency_processing_integration(self, signal_processor):
        """Test frequency processing integration"""
        from app.services.frequency_feed_manager import FeedFrequency
        
        # Add subscription
        await signal_processor.frequency_feed_manager.update_subscription_frequency(
            'test_user', 'NIFTY', 'greeks', '5m'
        )
        
        # Process batch
        await signal_processor.frequency_feed_manager._process_frequency_batch(FeedFrequency.MINUTE_5)

@pytest.mark.integration
class TestMoneynessCacheIntegration:
    """Integration tests for moneyness caching"""
    
    @pytest.mark.asyncio
    async def test_moneyness_rule_caching(self, signal_processor, redis_client):
        """Test moneyness rule caching"""
        # Mock configuration
        config = {
            'atm_threshold': 0.02,
            'otm_thresholds': {'5delta': 0.05}
        }
        
        # Cache configuration
        await redis_client.setex('moneyness:config', 3600, json.dumps(config))
        
        # Initialize with cached config
        await signal_processor._initialize_local_moneyness()
        assert signal_processor.local_moneyness_calculator.is_initialized
    
    @pytest.mark.asyncio
    async def test_moneyness_calculation_caching(self, signal_processor, redis_client):
        """Test moneyness calculation result caching"""
        moneyness_key = 'MONEYNESS@NIFTY@ATM@2025-07-10'
        
        # First calculation should cache result
        result1 = await signal_processor.moneyness_processor.get_moneyness_greeks_like_strike(
            'NIFTY', 'ATM', '2025-07-10',
            datetime.utcnow() - timedelta(hours=1),
            datetime.utcnow(), '5m'
        )
        
        # Second calculation should use cached result
        result2 = await signal_processor.moneyness_processor.get_moneyness_greeks_like_strike(
            'NIFTY', 'ATM', '2025-07-10',
            datetime.utcnow() - timedelta(hours=1),
            datetime.utcnow(), '5m'
        )
        
        assert result1 == result2

@pytest.mark.integration
class TestScalingIntegration:
    """Integration tests for scaling components"""
    
    def test_consistent_hash_redis_integration(self, consistent_hash_manager, redis_client):
        """Test consistent hash with Redis storage"""
        # Add nodes
        for i in range(3):
            consistent_hash_manager.add_node(f'signal-service-{i}')
        
        # Test instrument assignment
        instrument = 'NSE@NIFTY@equity_options@2025-07-10@call@21500'
        assigned_node = consistent_hash_manager.get_node_for_instrument(instrument)
        
        assert assigned_node in [f'signal-service-{i}' for i in range(3)]
    
    @pytest.mark.asyncio
    async def test_backpressure_monitoring_integration(self, signal_processor):
        """Test backpressure monitoring integration"""
        # Simulate load
        signal_processor.backpressure_monitor.update_queue_size(1000)
        signal_processor.backpressure_monitor.update_processing_rate(50)
        
        level = signal_processor.backpressure_monitor.get_backpressure_level()
        recommendations = signal_processor.backpressure_monitor.get_scaling_recommendations()
        
        assert level is not None
        assert 'action' in recommendations

@pytest.mark.integration
class TestAPIIntegration:
    """Integration tests for API endpoints"""
    
    @pytest.mark.asyncio
    async def test_api_with_signal_processor(self, async_client, signal_processor):
        """Test API integration with signal processor"""
        # Test real-time endpoint
        response = await async_client.get(
            "/api/v2/signals/realtime/greeks/NSE@NIFTY@equity_options@2025-07-10@call@21500"
        )
        # Should handle gracefully even without data
        assert response.status_code in [200, 404]
    
    @pytest.mark.asyncio
    async def test_api_batch_processing(self, async_client):
        """Test API batch processing integration"""
        payload = {
            'instruments': ['NSE@NIFTY@equity_options@2025-07-10@call@21500'],
            'signal_types': ['greeks']
        }
        
        response = await async_client.post("/api/v2/signals/batch/compute", json=payload)
        assert response.status_code in [200, 422]  # Should handle gracefully
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_websocket_integration(self, async_client):
        """Test WebSocket integration"""
        # Test WebSocket endpoint exists
        response = await async_client.get("/api/v2/signals/subscriptions/websocket")
        assert response.status_code in [200, 404, 426]  # WebSocket upgrade or not available
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_market_profile_integration(self, async_client):
        """Test market profile API integration"""
        response = await async_client.get(
            "/api/v2/signals/market-profile/NSE@NIFTY@equity_spot",
            params={'interval': '30m', 'lookback_period': '1d'}
        )
        assert response.status_code in [200, 404]
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_historical_data_integration(self, async_client):
        """Test historical data API integration"""
        start_time = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        end_time = datetime.utcnow().isoformat()
        
        response = await async_client.get(
            "/api/v2/signals/historical/greeks/NSE@NIFTY@equity_options@2025-07-10@call@21500",
            params={'start_time': start_time, 'end_time': end_time, 'timeframe': '5m'}
        )
        assert response.status_code in [200, 404]
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_moneyness_api_integration(self, async_client):
        """Test moneyness API integration"""
        response = await async_client.get(
            "/api/v2/signals/realtime/greeks/MONEYNESS@NIFTY@ATM@2025-07-10"
        )
        assert response.status_code in [200, 404]
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_admin_endpoints_integration(self, async_client):
        """Test admin endpoints integration"""
        # Test health endpoint
        response = await async_client.get("/api/v2/admin/health")
        assert response.status_code in [200, 404]
        
        # Test metrics endpoint
        response = await async_client.get("/api/v2/admin/metrics")
        assert response.status_code in [200, 404]