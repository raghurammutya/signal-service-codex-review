"""
Flexible Timeframe Manager
Handles custom timeframe aggregations and caching
"""
import asyncio
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from enum import Enum

import logging
import aiohttp

from app.utils.redis import get_redis_client
from app.core.config import settings

logger = logging.getLogger(__name__)


class TimeframeType(Enum):
    """Supported timeframe types"""
    STANDARD = "standard"  # 1m, 5m, 15m, 30m, 1h, 4h, 1d
    CUSTOM = "custom"      # Any custom minute interval


class FlexibleTimeframeManager:
    """
    Manages flexible timeframe aggregations for signals
    Supports both standard and custom timeframes
    """
    
    # Standard timeframes in minutes
    STANDARD_TIMEFRAMES = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "4h": 240,
        "1d": 1440
    }
    
    def __init__(self):
        self.redis_client = None
        self.ticker_client = None
        self.session = None
        
        # Initialize with unified historical data client
        from app.clients.historical_data_client import get_historical_data_client
        try:
            self.historical_client = get_historical_data_client()
        except Exception as e:
            from app.utils.logging_utils import log_error
            log_error(f"Failed to initialize historical data client: {e}")
            self.historical_client = None
        self._cache_ttl = {
            1: 60,        # 1 minute data: 1 minute TTL
            5: 300,       # 5 minute data: 5 minute TTL  
            15: 900,      # 15 minute data: 15 minute TTL
            30: 1800,     # 30 minute data: 30 minute TTL
            60: 3600,     # 1 hour data: 1 hour TTL
            240: 14400,   # 4 hour data: 4 hour TTL
            1440: 86400   # Daily data: 24 hour TTL
        }
        self._default_ttl = 300  # 5 minutes for custom timeframes
        
    async def initialize(self):
        """Initialize connections"""
        self.redis_client = await get_redis_client()
        
        # Get ticker service configuration from settings
        if not hasattr(settings, 'TICKER_SERVICE_URL'):
            raise ValueError("TICKER_SERVICE_URL not configured - cannot access historical data")
        self.ticker_service_url = settings.TICKER_SERVICE_URL
        
        # Get internal API key for service-to-service communication
        if not hasattr(settings, 'internal_api_key') or not settings.internal_api_key:
            raise ValueError("internal_api_key not configured - cannot authenticate with ticker service")
        self.internal_api_key = settings.internal_api_key
        
        # Initialize HTTP session
        self.session = aiohttp.ClientSession()
        
    def parse_timeframe(self, timeframe: str) -> Tuple[TimeframeType, int]:
        """
        Parse timeframe string to type and minutes
        
        Args:
            timeframe: Timeframe string (e.g., "5m", "7m", "custom_13")
            
        Returns:
            Tuple of (TimeframeType, minutes)
        """
        # Check standard timeframes
        if timeframe in self.STANDARD_TIMEFRAMES:
            return TimeframeType.STANDARD, self.STANDARD_TIMEFRAMES[timeframe]
            
        # Parse custom timeframes
        if timeframe.endswith("m"):
            try:
                minutes = int(timeframe[:-1])
                if 1 <= minutes <= 1440:  # Between 1 minute and 1 day
                    return TimeframeType.CUSTOM, minutes
            except ValueError:
                pass
                
        # Handle "custom_X" format
        if timeframe.startswith("custom_"):
            try:
                minutes = int(timeframe[7:])
                if 1 <= minutes <= 1440:
                    return TimeframeType.CUSTOM, minutes
            except ValueError:
                pass
                
        raise ValueError(f"Invalid timeframe: {timeframe}")
        
    async def get_aggregated_data(
        self,
        instrument_key: str,
        signal_type: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
        fields: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get aggregated signal data for any timeframe
        
        Args:
            instrument_key: Instrument identifier
            signal_type: Type of signal (greeks, indicators, etc.)
            timeframe: Target timeframe
            start_time: Start of time range
            end_time: End of time range
            fields: Optional list of fields to return
            
        Returns:
            List of aggregated data points
        """
        try:
            tf_type, minutes = self.parse_timeframe(timeframe)
            
            # Check cache first
            cached_data = await self._get_cached_data(
                instrument_key, signal_type, timeframe, start_time, end_time
            )
            if cached_data:
                return cached_data
                
            # Get base data (1-minute)
            base_data = await self._get_base_data(
                instrument_key, signal_type, start_time, end_time
            )
            
            if not base_data:
                return []
                
            # Aggregate to target timeframe
            aggregated = self._aggregate_data(base_data, minutes, fields)
            
            # Cache the result
            await self._cache_data(
                instrument_key, signal_type, timeframe, aggregated, minutes
            )
            
            return aggregated
            
        except Exception as e:
            logger.exception("Error getting aggregated data: %s", e)
            from app.errors import TimeframeAggregationError
            raise TimeframeAggregationError(f"Failed to aggregate data: {str(e)}") from e
            
    async def store_custom_timeframe(
        self,
        instrument_key: str,
        signal_type: str,
        timeframe_minutes: int,
        data: List[Dict[str, Any]]
    ):
        """
        Store pre-aggregated custom timeframe data
        
        Args:
            instrument_key: Instrument identifier
            signal_type: Type of signal
            timeframe_minutes: Timeframe in minutes
            data: Aggregated data to store
        """
        try:
            async with self.db_connection.acquire() as conn:
                # Store in custom timeframes table
                for record in data:
                    await conn.execute("""
                        INSERT INTO signal_custom_timeframes (
                            instrument_key, signal_type, timeframe_minutes,
                            timestamp, data, created_at
                        ) VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (instrument_key, signal_type, timeframe_minutes, timestamp)
                        DO UPDATE SET data = $5, updated_at = CURRENT_TIMESTAMP
                    """, 
                    instrument_key, signal_type, timeframe_minutes,
                    record['timestamp'], record, datetime.utcnow()
                    )
                    
            logger.info("Stored %s custom timeframe records", len(data))
            
        except Exception as e:
            logger.exception("Error storing custom timeframe data: %s", e)
            
    async def get_available_timeframes(
        self,
        instrument_key: str,
        signal_type: str
    ) -> List[str]:
        """
        Get list of available timeframes for an instrument
        
        Args:
            instrument_key: Instrument identifier
            signal_type: Type of signal
            
        Returns:
            List of available timeframe strings
        """
        available = list(self.STANDARD_TIMEFRAMES.keys())
        
        try:
            # Check for custom timeframes in database
            async with self.db_connection.acquire() as conn:
                result = await conn.fetch("""
                    SELECT DISTINCT timeframe_minutes
                    FROM signal_custom_timeframes
                    WHERE instrument_key = $1 AND signal_type = $2
                    ORDER BY timeframe_minutes
                """, instrument_key, signal_type)
                
                for row in result:
                    minutes = row['timeframe_minutes']
                    if minutes not in self.STANDARD_TIMEFRAMES.values():
                        available.append(f"{minutes}m")
                        
        except Exception as e:
            logger.error("Error getting available timeframes: %s", e)
            
        return sorted(available, key=lambda x: self._timeframe_to_minutes(x))
        
    def _timeframe_to_minutes(self, timeframe: str) -> int:
        """Convert timeframe string to minutes"""
        try:
            _, minutes = self.parse_timeframe(timeframe)
            return minutes
        except (ValueError, TypeError, AttributeError) as e:
            logger.warning(f"Invalid timeframe format '{timeframe}': {e}")
            return 0
            
    async def _get_base_data(
        self,
        instrument_key: str,
        signal_type: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Get 1-minute base data from ticker_service"""
        try:
            # Route all historical data requests through ticker_service
            if not self.session:
                raise RuntimeError("FlexibleTimeframeManager not initialized - call initialize() first")
            
            # Map signal types to ticker_service endpoints
            endpoint_map = {
                "greeks": "/api/v1/historical/greeks",
                "indicators": "/api/v1/historical/indicators",
                "moneyness_greeks": "/api/v1/historical/moneyness"
            }
            
            endpoint = endpoint_map.get(signal_type)
            if not endpoint:
                raise ValueError(f"Unknown signal type: {signal_type}")
            
            # Make request to ticker_service
            headers = {
                "X-Internal-API-Key": self.internal_api_key,
                "Content-Type": "application/json"
            }
            
            params = {
                "instrument_key": instrument_key,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "timeframe": "1m"  # Get base 1-minute data for aggregation
            }
            
            url = f"{self.ticker_service_url}{endpoint}"
            async with self.session.get(url, headers=headers, params=params, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    # Extract data points from ticker_service response
                    return data.get("data_points", [])
                elif response.status == 404:
                    # No data available for this timeframe
                    return []
                else:
                    error_text = await response.text()
                    logger.error(f"ticker_service request failed: {response.status} - {error_text}")
                    raise RuntimeError(f"ticker_service historical data request failed: {response.status}")
                
        except Exception as e:
            logger.exception("Error getting base data from ticker_service: %s", e)
            from app.errors import ServiceUnavailableError
            raise ServiceUnavailableError(f"Failed to retrieve historical data from ticker_service: {str(e)}") from e
            
    def _aggregate_data(
        self,
        base_data: List[Dict[str, Any]],
        timeframe_minutes: int,
        fields: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Aggregate 1-minute data to target timeframe
        
        Args:
            base_data: 1-minute base data
            timeframe_minutes: Target timeframe in minutes
            fields: Optional list of fields to aggregate
            
        Returns:
            Aggregated data
        """
        if not base_data:
            return []
            
        # Convert to DataFrame for easier aggregation
        df = pd.DataFrame(base_data)
        
        # Set timestamp as index
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        
        # Define aggregation rules
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        
        # Remove ID columns from aggregation
        id_cols = ['id', 'signal_id']
        numeric_cols = [col for col in numeric_cols if col not in id_cols]
        
        if fields:
            numeric_cols = [col for col in numeric_cols if col in fields]
            
        # Create aggregation dictionary
        agg_dict = {}
        for col in numeric_cols:
            if col in ['delta', 'gamma', 'theta', 'vega', 'rho', 'price', 'volume']:
                # For Greeks and prices, use mean
                agg_dict[col] = 'mean'
            elif col in ['high', 'ask']:
                agg_dict[col] = 'max'
            elif col in ['low', 'bid']:
                agg_dict[col] = 'min'
            elif col in ['volume', 'trades']:
                agg_dict[col] = 'sum'
            else:
                # Default to mean
                agg_dict[col] = 'mean'
                
        # Also get open/close values
        if 'value' in df.columns:
            agg_dict['open'] = ('value', 'first')
            agg_dict['close'] = ('value', 'last')
            
        # Resample and aggregate
        resampled = df.resample(f'{timeframe_minutes}T').agg(agg_dict)
        
        # Reset index and format output
        resampled.reset_index(inplace=True)
        
        # Convert back to list of dicts
        result = []
        for _, row in resampled.iterrows():
            record = row.to_dict()
            # Ensure timestamp is ISO format string
            record['timestamp'] = record['timestamp'].isoformat()
            record['timeframe_minutes'] = timeframe_minutes
            result.append(record)
            
        return result
        
    async def _get_cached_data(
        self,
        instrument_key: str,
        signal_type: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime
    ) -> Optional[List[Dict[str, Any]]]:
        """Get data from cache if available"""
        if not self.redis_client:
            return None
            
        try:
            # Create cache key
            cache_key = f"signal:timeframe:{instrument_key}:{signal_type}:{timeframe}:{start_time.timestamp():.0f}:{end_time.timestamp():.0f}"
            
            # Get from cache
            cached = await self.redis_client.get(cache_key)
            if cached:
                import json
                return json.loads(cached)
                
        except Exception as e:
            logger.error("Cache retrieval error: %s", e)
            
        return None
        
    async def _cache_data(
        self,
        instrument_key: str,
        signal_type: str,
        timeframe: str,
        data: List[Dict[str, Any]],
        timeframe_minutes: int
    ):
        """Cache aggregated data"""
        if not self.redis_client or not data:
            return
            
        try:
            # Get TTL for this timeframe
            ttl = self._cache_ttl.get(timeframe_minutes, self._default_ttl)
            
            # Create cache key using latest timestamp
            latest_timestamp = max(d['timestamp'] for d in data)
            cache_key = f"signal:timeframe:{instrument_key}:{signal_type}:{timeframe}:latest"
            
            # Store in cache
            import json
            await self.redis_client.setex(
                cache_key,
                ttl,
                json.dumps(data)
            )
            
        except Exception as e:
            logger.error("Cache storage error: %s", e)
            
    async def close(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def cleanup_old_data(self, retention_days: int = 30):
        """
        Clean up old custom timeframe data - delegated to ticker_service
        
        Args:
            retention_days: Number of days to retain data
        """
        try:
            # Request ticker_service to clean up old historical data
            if not self.session:
                logger.warning("FlexibleTimeframeManager not initialized - cannot cleanup old data")
                return
            
            headers = {
                "X-Internal-API-Key": self.internal_api_key,
                "Content-Type": "application/json"
            }
            
            params = {"retention_days": retention_days}
            
            url = f"{self.ticker_service_url}/api/v1/internal/cleanup/historical"
            async with self.session.post(url, headers=headers, json=params, timeout=60) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info("ticker_service cleaned up old data: %s", result.get("message", "Success"))
                else:
                    error_text = await response.text()
                    logger.error(f"ticker_service cleanup failed: {response.status} - {error_text}")
                
        except Exception as e:
            logger.exception("Error requesting data cleanup from ticker_service: %s", e)
