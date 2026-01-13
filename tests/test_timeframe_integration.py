"""Integration tests for timeframe aggregation"""
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from app.services.historical_data_writer import HistoricalDataWriter
from app.services.timeframe_cache_manager import TimeframeCacheManager, TimeframeCache
from app.services.historical_data_manager import HistoricalDataManager


class TestHistoricalDataWriter:
    
    @pytest.fixture
    async def writer(self):
        """Create a test writer instance"""
        writer = HistoricalDataWriter()
        writer.cluster_manager = Mock()
        writer.cluster_manager.client = AsyncMock()
        return writer
    
    @pytest.mark.asyncio
    async def test_get_active_instruments(self, writer):
        """Test getting active instruments from Redis"""
        # Mock Redis keys response
        writer.cluster_manager.client.keys = AsyncMock(return_value=[
            b'subscription_service:active_subscriptions:NSE@NIFTY@INDEX',
            b'signal_service:active_instruments:NSE@BANKNIFTY@INDEX'
        ])
        
        instruments = await writer._get_active_instruments()
        
        assert len(instruments) == 2
        assert 'NSE@NIFTY@INDEX' in instruments
        assert 'NSE@BANKNIFTY@INDEX' in instruments
    
    @pytest.mark.asyncio
    async def test_aggregate_to_candle(self, writer):
        """Test aggregating ticks to OHLCV candle"""
        ticks = [
            {'price': 100, 'volume': 1000},
            {'price': 102, 'volume': 1500},
            {'price': 98, 'volume': 2000},
            {'price': 101, 'volume': 1200}
        ]
        
        timestamp = datetime.now()
        candle = writer._aggregate_to_candle(ticks, timestamp, 'TEST@SYMBOL')
        
        assert candle is not None
        assert candle['open'] == 100
        assert candle['high'] == 102
        assert candle['low'] == 98
        assert candle['close'] == 101
        assert candle['volume'] == 5700  # Sum of volumes
        assert candle['instrument_key'] == 'TEST@SYMBOL'
        assert candle['interval'] == '1minute'
    
    @pytest.mark.asyncio
    async def test_process_minute_data(self, writer):
        """Test processing minute data"""
        # Mock dependencies
        writer._get_active_instruments = AsyncMock(return_value={'TEST@SYMBOL'})
        writer._get_minute_ticks = AsyncMock(return_value=[
            {'price': 100, 'volume': 1000}
        ])
        writer._write_to_timescale = AsyncMock()
        
        minute = datetime.now().replace(second=0, microsecond=0)
        await writer._process_minute_data(minute)
        
        # Verify write was called
        writer._write_to_timescale.assert_called_once()
        call_args = writer._write_to_timescale.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0]['instrument_key'] == 'TEST@SYMBOL'


class TestTimeframeCacheManager:
    
    @pytest.fixture
    async def cache_manager(self):
        """Create a test cache manager"""
        manager = TimeframeCacheManager()
        manager.cluster_manager = Mock()
        manager.cluster_manager.client = AsyncMock()
        return manager
    
    @pytest.mark.asyncio
    async def test_get_or_create_cache(self, cache_manager):
        """Test cache creation and retrieval"""
        cache1 = await cache_manager.get_or_create_cache('TEST@SYMBOL', '5minute')
        cache2 = await cache_manager.get_or_create_cache('TEST@SYMBOL', '5minute')
        
        # Should return same cache instance
        assert cache1 is cache2
        assert cache1.instrument_key == 'TEST@SYMBOL'
        assert cache1.timeframe == '5minute'
    
    @pytest.mark.asyncio
    async def test_subscribe_unsubscribe(self, cache_manager):
        """Test subscription management"""
        await cache_manager.subscribe('TEST@SYMBOL', '5minute')
        
        cache_key = 'TEST@SYMBOL:5minute'
        assert cache_key in cache_manager.cache_registry
        assert cache_manager.cache_registry[cache_key].subscriber_count == 1
        
        # Subscribe again
        await cache_manager.subscribe('TEST@SYMBOL', '5minute')
        assert cache_manager.cache_registry[cache_key].subscriber_count == 2
        
        # Unsubscribe
        await cache_manager.unsubscribe('TEST@SYMBOL', '5minute')
        assert cache_manager.cache_registry[cache_key].subscriber_count == 1
    
    @pytest.mark.asyncio
    async def test_cache_data_flow(self, cache_manager):
        """Test caching and retrieving data"""
        test_data = [
            {'timestamp': '2024-01-01T10:00:00Z', 'open': 100, 'close': 101},
            {'timestamp': '2024-01-01T10:05:00Z', 'open': 101, 'close': 102}
        ]
        
        # Set data
        await cache_manager.set_cached_data('TEST@SYMBOL', '5minute', test_data)
        
        # Get data
        retrieved = await cache_manager.get_cached_data('TEST@SYMBOL', '5minute')
        
        # Should get from local cache (mocked Redis)
        assert retrieved is not None
    
    @pytest.mark.asyncio
    async def test_cleanup_unused_caches(self, cache_manager):
        """Test cache cleanup"""
        # Create cache
        cache = await cache_manager.get_or_create_cache('TEST@SYMBOL', '5minute')
        
        # Set last access to old time
        cache.last_access = datetime.now() - timedelta(hours=2)
        cache.subscriber_count = 0
        
        # Run cleanup
        await cache_manager.cleanup_unused_caches()
        
        # Cache should be removed
        assert 'TEST@SYMBOL:5minute' not in cache_manager.cache_registry


class TestTimeframeCache:
    
    def test_cache_operations(self):
        """Test basic cache operations"""
        cache = TimeframeCache('TEST@SYMBOL', '5minute')
        
        # Test set and get
        asyncio.run(cache.set('test_key', {'data': 'value'}, ttl=60))
        result = asyncio.run(cache.get('test_key'))
        
        assert result is not None
        assert result['value']['data'] == 'value'
        assert cache.hit_count == 1
        assert cache.miss_count == 0
        
        # Test miss
        result = asyncio.run(cache.get('missing_key'))
        assert result is None
        assert cache.miss_count == 1
    
    def test_cache_expiration(self):
        """Test cache expiration"""
        cache = TimeframeCache('TEST@SYMBOL', '5minute')
        
        # Set with immediate expiration
        asyncio.run(cache.set('test_key', {'data': 'value'}, ttl=-1))
        
        # Clear expired
        asyncio.run(cache.clear_expired())
        
        # Should be gone
        result = asyncio.run(cache.get('test_key'))
        assert result is None
    
    def test_cache_statistics(self):
        """Test cache statistics"""
        cache = TimeframeCache('TEST@SYMBOL', '5minute')
        
        # Generate some activity
        asyncio.run(cache.set('key1', 'value1'))
        asyncio.run(cache.set('key2', 'value2'))
        asyncio.run(cache.get('key1'))  # Hit
        asyncio.run(cache.get('key3'))  # Miss
        
        stats = cache.get_stats()
        
        assert stats['instrument_key'] == 'TEST@SYMBOL'
        assert stats['timeframe'] == '5minute'
        assert stats['size'] == 2
        assert stats['hit_count'] == 1
        assert stats['miss_count'] == 1
        assert stats['hit_rate'] == 0.5


@pytest.mark.asyncio
async def test_continuous_aggregate_query():
    """Test querying continuous aggregates"""
    from app.services.historical_data_manager_update import _get_from_timescaledb
    
    # This would need actual database connection for full integration test
    # Here we just test the query construction
    
    # Mock self object
    mock_self = Mock()
    
    with patch('app.services.historical_data_manager_update.get_async_db') as mock_db:
        mock_session = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_session
        
        # Mock query result
        mock_result = Mock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result
        
        try:
            result = await _get_from_timescaledb(mock_self, 'TEST@SYMBOL', '5minute', 20)
        except Exception:
            # Expected to fail without real data
            pass
        
        # Verify continuous aggregate table was queried
        executed_query = mock_session.execute.call_args[0][0]
        assert 'ohlcv_5min' in str(executed_query)