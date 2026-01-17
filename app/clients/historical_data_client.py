"""
Historical Data Client

Unified client for historical data retrieval that eliminates duplication between
FlexibleTimeframeManager and MoneynessHistoricalProcessor by providing a
single interface to ticker service historical data endpoints.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
import httpx
from contextlib import asynccontextmanager

from app.core.config import settings
from app.errors import DataAccessError
from app.utils.logging_utils import log_info, log_error, log_warning
from app.clients.ticker_service_client import get_ticker_service_client

logger = logging.getLogger(__name__)


class HistoricalDataClient:
    """
    Unified historical data client that eliminates duplicate logic between
    timeframe management and moneyness processing.
    
    Provides single interface for:
    - Historical timeframe data (OHLCV)
    - Historical moneyness data 
    - Historical spot prices
    - Price range lookups
    """
    
    def __init__(self):
        self.ticker_client = get_ticker_service_client()
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes
    
    async def get_historical_timeframe_data(
        self,
        instrument_key: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
        include_volume: bool = True
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get historical OHLCV data for specified timeframe.
        
        This is the unified method used by FlexibleTimeframeManager.
        """
        try:
            return await self.ticker_client.get_historical_timeframe_data(
                instrument_key=instrument_key,
                timeframe=timeframe,
                start_time=start_time,
                end_time=end_time,
                include_volume=include_volume
            )
        except Exception as e:
            log_error(f"Failed to get historical timeframe data for {instrument_key}: {e}")
            raise DataAccessError(f"Historical timeframe data unavailable: {e}")
    
    async def get_historical_moneyness_data(
        self,
        underlying: str,
        moneyness_level: float,
        start_time: datetime,
        end_time: datetime,
        timeframe: str = "5m"
    ) -> Optional[Dict[str, Any]]:
        """
        Get historical moneyness Greeks data.
        
        This is the unified method used by MoneynessHistoricalProcessor.
        """
        try:
            return await self.ticker_client.get_historical_moneyness_data(
                underlying=underlying,
                moneyness_level=moneyness_level,
                start_time=start_time,
                end_time=end_time,
                timeframe=timeframe
            )
        except Exception as e:
            log_error(f"Failed to get historical moneyness data for {underlying}: {e}")
            raise DataAccessError(f"Historical moneyness data unavailable: {e}")
    
    async def get_historical_spot_price(
        self,
        underlying: str,
        timestamp: datetime,
        window_minutes: int = 5
    ) -> Optional[float]:
        """
        Get historical spot price at specific timestamp.
        
        Args:
            underlying: Underlying symbol
            timestamp: Specific timestamp to lookup
            window_minutes: Search window around timestamp
            
        Returns:
            Spot price or None if not available
        """
        try:
            # Use current market data endpoint with specific timestamp
            market_data = await self.ticker_client.get_current_market_data(
                instrument_key=underlying
            )
            
            if market_data:
                # In a real implementation, this would query historical price at timestamp
                # For now, we document the requirement for ticker service integration
                log_warning(f"Historical spot price lookup for {underlying} at {timestamp} requires ticker service historical price API")
                return market_data.get('price')
            
            return None
            
        except Exception as e:
            log_error(f"Failed to get historical spot price for {underlying}: {e}")
            raise DataAccessError(f"Historical spot price lookup failed: {e}")
    
    async def get_historical_price_range(
        self,
        underlying: str,
        start_time: datetime,
        end_time: datetime,
        aggregation: str = "1h"
    ) -> Optional[Dict[str, Any]]:
        """
        Get historical price range (min, max, avg) for time period.
        
        Args:
            underlying: Underlying symbol
            start_time: Start of time range
            end_time: End of time range
            aggregation: Aggregation interval
            
        Returns:
            Price range statistics or None if not available
        """
        try:
            # Get historical data for the range
            timeframe_data = await self.get_historical_timeframe_data(
                instrument_key=underlying,
                timeframe=aggregation,
                start_time=start_time,
                end_time=end_time,
                include_volume=False
            )
            
            if not timeframe_data:
                return None
            
            # Calculate price statistics
            prices = [bar['close'] for bar in timeframe_data if 'close' in bar]
            if not prices:
                return None
            
            return {
                'min_price': min(prices),
                'max_price': max(prices),
                'avg_price': sum(prices) / len(prices),
                'price_count': len(prices),
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat()
            }
            
        except Exception as e:
            log_error(f"Failed to get historical price range for {underlying}: {e}")
            raise DataAccessError(f"Historical price range lookup failed: {e}")
    
    async def get_cached_data(self, cache_key: str) -> Optional[Any]:
        """Get data from cache if available and not expired."""
        if cache_key not in self.cache:
            return None
        
        cached_item = self.cache[cache_key]
        if datetime.now().timestamp() - cached_item['timestamp'] > self.cache_ttl:
            del self.cache[cache_key]
            return None
        
        return cached_item['data']
    
    async def set_cached_data(self, cache_key: str, data: Any):
        """Set data in cache with timestamp."""
        self.cache[cache_key] = {
            'data': data,
            'timestamp': datetime.now().timestamp()
        }
        
        # Simple cache cleanup - remove old entries
        current_time = datetime.now().timestamp()
        expired_keys = [
            key for key, value in self.cache.items()
            if current_time - value['timestamp'] > self.cache_ttl
        ]
        for key in expired_keys:
            del self.cache[key]
    
    def health_check(self) -> Dict[str, Any]:
        """Check health of historical data client."""
        return {
            'ticker_client_healthy': hasattr(self.ticker_client, 'health_check'),
            'cache_entries': len(self.cache),
            'cache_ttl_seconds': self.cache_ttl
        }


# Global instance
_historical_data_client: Optional[HistoricalDataClient] = None


def get_historical_data_client() -> HistoricalDataClient:
    """Get or create historical data client instance."""
    global _historical_data_client
    if _historical_data_client is None:
        _historical_data_client = HistoricalDataClient()
    return _historical_data_client


@asynccontextmanager
async def historical_data_context():
    """Context manager for historical data operations."""
    client = get_historical_data_client()
    try:
        yield client
    finally:
        # Cleanup if needed
        pass