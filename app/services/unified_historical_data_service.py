"""
Unified Historical Data Service

Single entry point for all historical data operations, eliminating redundancy.
Consolidates functionality from historical_data_manager_production.py and historical_data_client.py.
"""
import logging
import threading
from collections import defaultdict
from datetime import datetime
from typing import Any

import httpx

from app.clients.ticker_service_client import get_ticker_service_client
from app.errors import DataAccessError
from app.utils.logging_utils import log_error, log_info

logger = logging.getLogger(__name__)


class UnifiedHistoricalDataService:
    """
    Unified historical data service that provides single entry point for:
    - Indicator historical data (replacing historical_data_manager_production)
    - Timeframe/OHLCV data (replacing historical_data_client)
    - Moneyness-specific data
    - Cross-cutting concerns: caching, error handling, rate limiting
    """

    def __init__(self):
        self._cache = {}
        self._cache_locks = defaultdict(threading.Lock)
        self._ticker_client = None

    async def get_ticker_client(self):
        """Get ticker service client with lazy initialization."""
        if self._ticker_client is None:
            self._ticker_client = get_ticker_service_client()
        return self._ticker_client

    # === INDICATOR DATA METHODS (from historical_data_manager_production) ===

    async def get_historical_data_for_indicator(
        self,
        instrument_key: str,
        start_time: datetime,
        end_time: datetime,
        interval: str = "1m"
    ) -> list[dict[str, Any]]:
        """
        Get historical data optimized for indicator calculations.
        Replaces ProductionHistoricalDataManager.get_historical_data_for_indicator()
        """
        cache_key = f"indicator:{instrument_key}:{start_time}:{end_time}:{interval}"

        # Check cache first
        with self._cache_locks[cache_key]:
            if cache_key in self._cache:
                log_info(f"Cache hit for indicator data: {instrument_key}")
                return self._cache[cache_key]

        try:
            client = await self.get_ticker_client()
            data = await self._fetch_from_ticker_service(
                client, instrument_key, start_time, end_time, interval
            )

            # Cache the result
            with self._cache_locks[cache_key]:
                self._cache[cache_key] = data

            log_info(f"Fetched {len(data)} records for indicator {instrument_key}")
            return data

        except Exception as e:
            log_error(f"Failed to fetch indicator data for {instrument_key}: {e}")
            raise DataAccessError(f"Historical data fetch failed: {e}")

    # === TIMEFRAME DATA METHODS (from historical_data_client) ===

    async def get_historical_timeframe_data(
        self,
        instrument_key: str,
        start_time: datetime,
        end_time: datetime,
        timeframe: str = "1m"
    ) -> list[dict[str, Any]]:
        """
        Get OHLCV timeframe data.
        Replaces HistoricalDataClient.get_historical_timeframe_data()
        """
        cache_key = f"timeframe:{instrument_key}:{start_time}:{end_time}:{timeframe}"

        with self._cache_locks[cache_key]:
            if cache_key in self._cache:
                log_info(f"Cache hit for timeframe data: {instrument_key}")
                return self._cache[cache_key]

        try:
            client = await self.get_ticker_client()
            data = await self._fetch_ohlcv_data(
                client, instrument_key, start_time, end_time, timeframe
            )

            with self._cache_locks[cache_key]:
                self._cache[cache_key] = data

            return data

        except Exception as e:
            log_error(f"Failed to fetch timeframe data for {instrument_key}: {e}")
            raise DataAccessError(f"Timeframe data fetch failed: {e}")

    async def get_historical_moneyness_data(
        self,
        underlying: str,
        strike: float,
        expiry: str,
        start_time: datetime,
        end_time: datetime
    ) -> list[dict[str, Any]]:
        """
        Get moneyness-specific historical data.
        """
        cache_key = f"moneyness:{underlying}:{strike}:{expiry}:{start_time}:{end_time}"

        with self._cache_locks[cache_key]:
            if cache_key in self._cache:
                return self._cache[cache_key]

        try:
            # Get underlying price data for moneyness calculations
            underlying_key = f"{underlying}@INDEX" if "@" not in underlying else underlying
            client = await self.get_ticker_client()

            data = await self._fetch_from_ticker_service(
                client, underlying_key, start_time, end_time, "1m"
            )

            # Enhance with moneyness calculations
            enhanced_data = self._calculate_moneyness_metrics(data, strike, expiry)

            with self._cache_locks[cache_key]:
                self._cache[cache_key] = enhanced_data

            return enhanced_data

        except Exception as e:
            log_error(f"Failed to fetch moneyness data for {underlying}: {e}")
            raise DataAccessError(f"Moneyness data fetch failed: {e}")

    # === CORE FETCHING METHODS ===

    async def _fetch_from_ticker_service(
        self,
        client,
        instrument_key: str,
        start_time: datetime,
        end_time: datetime,
        interval: str
    ) -> list[dict[str, Any]]:
        """Core ticker service fetching logic."""
        try:
            response = await client.get_historical_data(
                instrument_key=instrument_key,
                start_time=start_time,
                end_time=end_time,
                interval=interval
            )

            if response.get('success', False):
                return response.get('data', [])
            error_msg = response.get('error', 'Unknown error')
            raise DataAccessError(f"Ticker service error: {error_msg}")

        except httpx.HTTPError as e:
            raise DataAccessError(f"HTTP error fetching from ticker service: {e}")

    async def _fetch_ohlcv_data(
        self,
        client,
        instrument_key: str,
        start_time: datetime,
        end_time: datetime,
        timeframe: str
    ) -> list[dict[str, Any]]:
        """Fetch OHLCV data with specific formatting."""
        raw_data = await self._fetch_from_ticker_service(
            client, instrument_key, start_time, end_time, timeframe
        )

        # Ensure OHLCV format
        ohlcv_data = []
        for record in raw_data:
            ohlcv_data.append({
                'timestamp': record.get('timestamp'),
                'open': float(record.get('open', 0)),
                'high': float(record.get('high', 0)),
                'low': float(record.get('low', 0)),
                'close': float(record.get('close', 0)),
                'volume': int(record.get('volume', 0))
            })

        return ohlcv_data

    def _calculate_moneyness_metrics(
        self,
        price_data: list[dict[str, Any]],
        strike: float,
        expiry: str
    ) -> list[dict[str, Any]]:
        """Calculate moneyness metrics for historical data."""
        enhanced_data = []

        for record in price_data:
            current_price = float(record.get('close', 0))
            moneyness = current_price / strike if strike > 0 else 0

            enhanced_record = record.copy()
            enhanced_record.update({
                'strike': strike,
                'expiry': expiry,
                'moneyness': moneyness,
                'itm': moneyness > 1.0,  # In-the-money for calls
                'distance_from_strike': abs(current_price - strike)
            })

            enhanced_data.append(enhanced_record)

        return enhanced_data

    # === CACHE MANAGEMENT ===

    def clear_cache(self):
        """Clear the internal cache."""
        with threading.Lock():
            self._cache.clear()
            log_info("Historical data cache cleared")

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            'cache_size': len(self._cache),
            'cache_keys': list(self._cache.keys())
        }


# Global service instance
_unified_historical_service = None


def get_unified_historical_service() -> UnifiedHistoricalDataService:
    """Get the global unified historical data service instance."""
    global _unified_historical_service
    if _unified_historical_service is None:
        _unified_historical_service = UnifiedHistoricalDataService()
    return _unified_historical_service


# === BACKWARD COMPATIBILITY ALIASES ===

# For historical_data_manager_production.py compatibility
def get_production_historical_data_manager():
    """Backward compatibility alias."""
    return get_unified_historical_service()

class ProductionHistoricalDataManager:
    """Backward compatibility class."""
    def __init__(self):
        self._service = get_unified_historical_service()

    async def get_historical_data_for_indicator(self, *args, **kwargs):
        return await self._service.get_historical_data_for_indicator(*args, **kwargs)

# For historical_data_client.py compatibility
class HistoricalDataClient:
    """Backward compatibility class."""
    def __init__(self):
        self._service = get_unified_historical_service()

    async def get_historical_timeframe_data(self, *args, **kwargs):
        return await self._service.get_historical_timeframe_data(*args, **kwargs)

    async def get_historical_moneyness_data(self, *args, **kwargs):
        return await self._service.get_historical_moneyness_data(*args, **kwargs)
