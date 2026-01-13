"""
Unit tests for FrequencyFeedManager
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from app.services.frequency_feed_manager import FrequencyFeedManager, FeedFrequency

@pytest.mark.unit
class TestFrequencyFeedManager:
    """Test suite for FrequencyFeedManager"""
    
    @pytest.fixture
    def mock_signal_processor(self):
        """Mock signal processor for testing"""
        processor = AsyncMock()
        processor.compute_greeks_for_instrument.return_value = {
            'delta': 0.5, 'gamma': 0.01, 'theta': -0.05, 'vega': 0.15
        }
        processor.compute_indicators_for_instrument.return_value = {
            'sma_20': 21500, 'rsi_14': 55.5, 'bollinger_upper': 21600
        }
        return processor
    
    @pytest.fixture
    def manager(self, mock_signal_processor):
        """Create FrequencyFeedManager instance"""
        return FrequencyFeedManager(mock_signal_processor)
    
    @pytest.mark.asyncio
    async def test_subscription_management(self, manager):
        """Test subscription frequency management"""
        # Add subscription
        await manager.update_subscription_frequency('user1', 'NIFTY', 'greeks', '5m')
        
        assert FeedFrequency.MINUTE_5 in manager.frequency_subscriptions
        assert ('user1', 'NIFTY', 'greeks') in manager.frequency_subscriptions[FeedFrequency.MINUTE_5]
        
        # Add another subscription to same frequency
        await manager.update_subscription_frequency('user2', 'NIFTY', 'greeks', '5m')
        assert len(manager.frequency_subscriptions[FeedFrequency.MINUTE_5]) == 2
        
        # Add subscription to different frequency
        await manager.update_subscription_frequency('user1', 'NIFTY', 'indicators', '1m')
        assert FeedFrequency.MINUTE_1 in manager.frequency_subscriptions
        assert ('user1', 'NIFTY', 'indicators') in manager.frequency_subscriptions[FeedFrequency.MINUTE_1]
    
    @pytest.mark.asyncio
    async def test_subscription_removal(self, manager):
        """Test subscription removal"""
        # Add subscriptions
        await manager.update_subscription_frequency('user1', 'NIFTY', 'greeks', '5m')
        await manager.update_subscription_frequency('user2', 'NIFTY', 'greeks', '5m')
        
        # Remove one subscription
        await manager.remove_subscription('user1', 'NIFTY', 'greeks')
        
        assert ('user1', 'NIFTY', 'greeks') not in manager.frequency_subscriptions[FeedFrequency.MINUTE_5]
        assert ('user2', 'NIFTY', 'greeks') in manager.frequency_subscriptions[FeedFrequency.MINUTE_5]
        
        # Remove last subscription should clean up frequency
        await manager.remove_subscription('user2', 'NIFTY', 'greeks')
        assert len(manager.frequency_subscriptions.get(FeedFrequency.MINUTE_5, [])) == 0
    
    @pytest.mark.asyncio
    async def test_realtime_vs_frequency_handling(self, manager):
        """Test handling of real-time vs frequency-based subscriptions"""
        # Add real-time subscription
        await manager.update_subscription_frequency('user1', 'NIFTY', 'greeks', 'realtime')
        assert FeedFrequency.REALTIME in manager.frequency_subscriptions
        
        # Add frequency-based subscription for same instrument/signal
        await manager.update_subscription_frequency('user2', 'NIFTY', 'greeks', '5m')
        
        # Both should coexist
        assert len(manager.frequency_subscriptions[FeedFrequency.REALTIME]) == 1
        assert len(manager.frequency_subscriptions[FeedFrequency.MINUTE_5]) == 1
        
        # Real-time should be processed immediately
        assert manager._should_process_realtime('NIFTY', 'greeks')
        
        # Frequency-based should follow schedule
        assert not manager._should_process_frequency(FeedFrequency.MINUTE_5, datetime.utcnow())
    
    @pytest.mark.asyncio
    async def test_batch_processing_optimization(self, manager, mock_signal_processor):
        """Test efficient batch processing"""
        # Add multiple users for same instrument/signal
        await manager.update_subscription_frequency('user1', 'NIFTY', 'greeks', '5m')
        await manager.update_subscription_frequency('user2', 'NIFTY', 'greeks', '5m')
        await manager.update_subscription_frequency('user3', 'BANKNIFTY', 'greeks', '5m')
        
        # Process frequency batch
        with patch.object(manager, '_compute_signal') as mock_compute:
            mock_compute.return_value = {'delta': 0.5}
            
            await manager._process_frequency_batch(FeedFrequency.MINUTE_5)
            
            # Should compute once per unique instrument/signal combination
            assert mock_compute.call_count == 2  # NIFTY and BANKNIFTY
            
            # Verify calls
            call_args = [call[0] for call in mock_compute.call_args_list]
            assert ('NIFTY', 'greeks') in call_args
            assert ('BANKNIFTY', 'greeks') in call_args
    
    @pytest.mark.asyncio
    async def test_frequency_timing(self, manager):
        """Test frequency-based timing logic"""
        now = datetime.utcnow().replace(second=0, microsecond=0)
        
        # Test different frequencies
        test_cases = [
            (FeedFrequency.MINUTE_1, timedelta(minutes=1)),
            (FeedFrequency.MINUTE_5, timedelta(minutes=5)),
            (FeedFrequency.MINUTE_15, timedelta(minutes=15)),
            (FeedFrequency.HOUR_1, timedelta(hours=1))
        ]
        
        for frequency, interval in test_cases:
            # Should process at exact intervals
            assert manager._should_process_frequency(frequency, now)
            
            # Should not process between intervals
            off_time = now + timedelta(seconds=30)
            assert not manager._should_process_frequency(frequency, off_time)
            
            # Should process at next interval
            next_interval = now + interval
            assert manager._should_process_frequency(frequency, next_interval)
    
    @pytest.mark.asyncio
    async def test_subscription_grouping(self, manager):
        """Test subscription grouping for efficient processing"""
        # Add various subscriptions
        subscriptions = [
            ('user1', 'NIFTY', 'greeks'),
            ('user2', 'NIFTY', 'greeks'),
            ('user3', 'NIFTY', 'indicators'),
            ('user4', 'BANKNIFTY', 'greeks')
        ]
        
        for user, instrument, signal in subscriptions:
            await manager.update_subscription_frequency(user, instrument, signal, '5m')
        
        # Test grouping
        grouped = manager._group_subscriptions(manager.frequency_subscriptions[FeedFrequency.MINUTE_5])
        
        assert ('NIFTY', 'greeks') in grouped
        assert ('NIFTY', 'indicators') in grouped
        assert ('BANKNIFTY', 'greeks') in grouped
        
        # NIFTY greeks should have 2 users
        assert len(grouped[('NIFTY', 'greeks')]) == 2
        assert 'user1' in grouped[('NIFTY', 'greeks')]
        assert 'user2' in grouped[('NIFTY', 'greeks')]
    
    @pytest.mark.asyncio
    async def test_ticker_service_coordination(self, manager):
        """Test coordination with ticker_service frequency_manager"""
        ticker_frequencies = {
            'NIFTY': '5m',
            'BANKNIFTY': '1m',
            'RELIANCE': 'realtime'
        }
        
        # Sync with ticker frequencies
        await manager.sync_with_ticker_frequency(ticker_frequencies)
        
        # Should align signal processing with ticker frequencies
        assert manager.ticker_frequencies['NIFTY'] == FeedFrequency.MINUTE_5
        assert manager.ticker_frequencies['BANKNIFTY'] == FeedFrequency.MINUTE_1
        assert manager.ticker_frequencies['RELIANCE'] == FeedFrequency.REALTIME
        
        # Test alignment check
        assert manager.is_aligned_with_ticker()
        
        # Test misalignment detection
        manager.ticker_frequencies['NIFTY'] = FeedFrequency.MINUTE_1
        await manager.update_subscription_frequency('user1', 'NIFTY', 'greeks', '5m')
        
        # Should detect misalignment
        assert not manager._is_frequency_aligned('NIFTY', FeedFrequency.MINUTE_5)
    
    @pytest.mark.asyncio
    async def test_delivery_methods(self, manager):
        """Test different signal delivery methods"""
        with patch.object(manager, '_deliver_via_redis') as mock_redis, \
             patch.object(manager, '_deliver_via_websocket') as mock_ws, \
             patch.object(manager, '_deliver_via_callback') as mock_callback:
            
            signal_data = {'delta': 0.5, 'gamma': 0.01}
            
            # Test Redis delivery
            await manager._deliver_signal('user1', 'NIFTY', 'greeks', signal_data, 'redis')
            mock_redis.assert_called_once_with('user1', 'NIFTY', 'greeks', signal_data)
            
            # Test WebSocket delivery
            await manager._deliver_signal('user2', 'NIFTY', 'greeks', signal_data, 'websocket')
            mock_ws.assert_called_once_with('user2', 'NIFTY', 'greeks', signal_data)
            
            # Test callback delivery
            await manager._deliver_signal('user3', 'NIFTY', 'greeks', signal_data, 'callback')
            mock_callback.assert_called_once_with('user3', 'NIFTY', 'greeks', signal_data)
    
    @pytest.mark.asyncio
    async def test_performance_optimization(self, manager, mock_signal_processor):
        """Test performance optimizations"""
        # Add many subscriptions
        for i in range(100):
            await manager.update_subscription_frequency(f'user{i}', 'NIFTY', 'greeks', '5m')
        
        # Measure processing time
        import time
        start = time.time()
        
        with patch.object(manager, '_compute_signal') as mock_compute:
            mock_compute.return_value = {'delta': 0.5}
            await manager._process_frequency_batch(FeedFrequency.MINUTE_5)
        
        end = time.time()
        processing_time = (end - start) * 1000  # Convert to ms
        
        # Should process efficiently even with many subscribers
        assert processing_time < 100, f"Batch processing took {processing_time:.2f}ms for 100 users"
        
        # Should only compute once despite 100 subscribers
        assert mock_compute.call_count == 1
    
    @pytest.mark.asyncio
    async def test_error_handling(self, manager, mock_signal_processor):
        """Test error handling in frequency processing"""
        await manager.update_subscription_frequency('user1', 'NIFTY', 'greeks', '5m')
        
        # Test signal computation error
        mock_signal_processor.compute_greeks_for_instrument.side_effect = Exception("Computation error")
        
        # Should handle error gracefully
        with patch.object(manager, '_handle_computation_error') as mock_error_handler:
            await manager._process_frequency_batch(FeedFrequency.MINUTE_5)
            mock_error_handler.assert_called()
        
        # Test delivery error
        mock_signal_processor.compute_greeks_for_instrument.side_effect = None
        mock_signal_processor.compute_greeks_for_instrument.return_value = {'delta': 0.5}
        
        with patch.object(manager, '_deliver_signal') as mock_deliver:
            mock_deliver.side_effect = Exception("Delivery error")
            
            # Should continue processing despite delivery error
            await manager._process_frequency_batch(FeedFrequency.MINUTE_5)
            mock_deliver.assert_called()
    
    @pytest.mark.asyncio
    async def test_subscription_stats(self, manager):
        """Test subscription statistics and monitoring"""
        # Add various subscriptions
        await manager.update_subscription_frequency('user1', 'NIFTY', 'greeks', 'realtime')
        await manager.update_subscription_frequency('user2', 'NIFTY', 'greeks', '5m')
        await manager.update_subscription_frequency('user3', 'BANKNIFTY', 'indicators', '1m')
        
        stats = manager.get_subscription_stats()
        
        assert 'total_subscriptions' in stats
        assert 'by_frequency' in stats
        assert 'by_signal_type' in stats
        assert 'by_instrument' in stats
        
        # Verify counts
        assert stats['total_subscriptions'] == 3
        assert stats['by_frequency'][FeedFrequency.REALTIME.value] == 1
        assert stats['by_frequency'][FeedFrequency.MINUTE_5.value] == 1
        assert stats['by_frequency'][FeedFrequency.MINUTE_1.value] == 1
        
        assert stats['by_signal_type']['greeks'] == 2
        assert stats['by_signal_type']['indicators'] == 1
        
        assert stats['by_instrument']['NIFTY'] == 2
        assert stats['by_instrument']['BANKNIFTY'] == 1
    
    @pytest.mark.asyncio
    async def test_concurrent_processing(self, manager, mock_signal_processor):
        """Test concurrent processing of different frequencies"""
        # Set up subscriptions for different frequencies
        await manager.update_subscription_frequency('user1', 'NIFTY', 'greeks', '1m')
        await manager.update_subscription_frequency('user2', 'NIFTY', 'greeks', '5m')
        await manager.update_subscription_frequency('user3', 'NIFTY', 'greeks', '15m')
        
        # Mock computation to track calls
        computation_calls = []
        
        async def mock_compute(instrument, signal_type):
            computation_calls.append((instrument, signal_type, datetime.utcnow()))
            return {'delta': 0.5}
        
        manager._compute_signal = mock_compute
        
        # Process multiple frequencies concurrently
        tasks = [
            manager._process_frequency_batch(FeedFrequency.MINUTE_1),
            manager._process_frequency_batch(FeedFrequency.MINUTE_5),
            manager._process_frequency_batch(FeedFrequency.MINUTE_15)
        ]
        
        await asyncio.gather(*tasks)
        
        # Should have processed all frequencies
        assert len(computation_calls) == 3
        
        # All should be for the same instrument/signal but different times
        for call in computation_calls:
            assert call[0] == 'NIFTY'
            assert call[1] == 'greeks'
    
    @pytest.mark.asyncio
    async def test_memory_management(self, manager):
        """Test memory management for large number of subscriptions"""
        # Add many subscriptions and then remove them
        for i in range(1000):
            await manager.update_subscription_frequency(f'user{i}', f'INSTRUMENT{i%10}', 'greeks', '5m')
        
        # Verify subscriptions are tracked
        total_subs = sum(len(subs) for subs in manager.frequency_subscriptions.values())
        assert total_subs == 1000
        
        # Remove all subscriptions
        for i in range(1000):
            await manager.remove_subscription(f'user{i}', f'INSTRUMENT{i%10}', 'greeks')
        
        # Verify cleanup
        total_subs = sum(len(subs) for subs in manager.frequency_subscriptions.values())
        assert total_subs == 0
        
        # Memory should be released
        assert len(manager.frequency_subscriptions) == 0