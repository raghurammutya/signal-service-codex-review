#!/usr/bin/env python3
"""
PythonSDK Data Client - Phase 1 Migration

SDK_002: Implement Internal Token Resolution
- Market data requests using instrument_key
- Internal token resolution for broker data feeds
- Registry-based metadata enrichment
"""

import asyncio
import logging
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import pandas as pd

from app.sdk.instrument_client import InstrumentClient, create_instrument_client

logger = logging.getLogger(__name__)

class TimeFrame(Enum):
    """Supported timeframes for historical data"""
    MINUTE_1 = "1minute"
    MINUTE_5 = "5minute"
    MINUTE_15 = "15minute"
    HOUR_1 = "1hour"
    DAY_1 = "day"
    WEEK_1 = "week"
    MONTH_1 = "month"

class DataType(Enum):
    """Types of market data"""
    OHLCV = "ohlcv"
    QUOTES = "quotes"
    TRADES = "trades"
    ORDERBOOK = "orderbook"

@dataclass
class MarketData:
    """Market data with instrument metadata enrichment"""
    instrument_key: str
    symbol: str
    exchange: str
    data_type: DataType
    timeframe: TimeFrame | None = None
    timestamp: datetime = None
    data: dict | pd.DataFrame | None = None
    # Registry-enriched metadata
    sector: str | None = None
    market_cap: float | None = None
    # Internal broker information - not exposed
    _source_broker: str | None = None
    _broker_token: str | None = None

class DataClient:
    """
    Phase 1: instrument_key-first Market Data Client

    All data requests use instrument_key as primary identifier.
    Broker tokens resolved internally via registry integration.
    """

    def __init__(self,
                 instrument_client: InstrumentClient | None = None,
                 default_broker: str = "kite"):
        """
        Initialize Data Client with registry integration

        Args:
            instrument_client: Client for metadata and token resolution
            default_broker: Default broker for market data
        """
        self.instrument_client = instrument_client or create_instrument_client()
        self.default_broker = default_broker
        self._data_cache = {}
        self._cache_ttl = {
            TimeFrame.MINUTE_1: 60,    # 1 minute cache
            TimeFrame.MINUTE_5: 300,   # 5 minute cache
            TimeFrame.DAY_1: 3600,     # 1 hour cache
        }

    async def get_historical_data(self,
                                instrument_key: str,
                                timeframe: TimeFrame,
                                periods: int = 100,
                                broker_id: str | None = None) -> MarketData:
        """
        Get historical OHLCV data using instrument_key

        Args:
            instrument_key: Primary identifier (e.g., "AAPL_NASDAQ_EQUITY")
            timeframe: Data timeframe (1minute, 5minute, day, etc.)
            periods: Number of periods to retrieve
            broker_id: Override default broker for data source

        Returns:
            MarketData: Historical data with enriched metadata
        """
        # Check cache first
        cache_key = f"hist:{instrument_key}:{timeframe.value}:{periods}"
        cached_data = self._get_from_cache(cache_key, timeframe)
        if cached_data is not None:
            logger.debug(f"Cache hit for historical data: {instrument_key}")
            return cached_data

        # Get instrument metadata for enrichment
        metadata = await self.instrument_client.get_instrument_metadata(instrument_key)

        # Resolve broker token internally
        target_broker = broker_id or self.default_broker
        try:
            broker_token = await self.instrument_client.resolve_broker_token(
                instrument_key, target_broker
            )
        except ValueError as e:
            logger.error(f"Token resolution failed for {instrument_key} on {target_broker}: {e}")
            raise RuntimeError(f"Data source unavailable: {e}")

        try:
            # Fetch data from broker using resolved token
            df = await self._fetch_broker_historical_data(
                broker_token=broker_token,
                timeframe=timeframe,
                periods=periods,
                broker_id=target_broker
            )

            # Create enriched market data object
            market_data = MarketData(
                instrument_key=instrument_key,
                symbol=metadata.symbol,
                exchange=metadata.exchange,
                data_type=DataType.OHLCV,
                timeframe=timeframe,
                timestamp=datetime.now(),
                data=df,
                sector=metadata.sector,
                _source_broker=target_broker,
                _broker_token=broker_token  # Internal use only
            )

            # Cache the result
            self._set_cache(cache_key, market_data, timeframe)

            logger.info(f"Historical data retrieved: {instrument_key} ({metadata.symbol}) - {len(df)} periods")
            return market_data

        except Exception as e:
            logger.error(f"Historical data fetch failed for {instrument_key}: {e}")
            raise RuntimeError(f"Data retrieval failed: {e}")

    async def get_real_time_quote(self, instrument_key: str,
                                broker_id: str | None = None) -> MarketData:
        """
        Get real-time quote using instrument_key

        Args:
            instrument_key: Primary identifier
            broker_id: Override default broker

        Returns:
            MarketData: Current quote with metadata
        """
        # Get instrument metadata
        metadata = await self.instrument_client.get_instrument_metadata(instrument_key)

        # Resolve broker token
        target_broker = broker_id or self.default_broker
        broker_token = await self.instrument_client.resolve_broker_token(
            instrument_key, target_broker
        )

        try:
            # Fetch real-time quote from broker
            quote_data = await self._fetch_broker_quote(
                broker_token=broker_token,
                broker_id=target_broker
            )

            market_data = MarketData(
                instrument_key=instrument_key,
                symbol=metadata.symbol,
                exchange=metadata.exchange,
                data_type=DataType.QUOTES,
                timestamp=datetime.now(),
                data=quote_data,
                sector=metadata.sector,
                _source_broker=target_broker,
                _broker_token=broker_token
            )

            logger.debug(f"Real-time quote: {instrument_key} - {quote_data.get('ltp', 'N/A')}")
            return market_data

        except Exception as e:
            logger.error(f"Quote fetch failed for {instrument_key}: {e}")
            raise RuntimeError(f"Quote retrieval failed: {e}")

    async def subscribe_to_stream(self,
                                instrument_keys: list[str],
                                data_types: list[DataType],
                                broker_id: str | None = None) -> AsyncIterable[MarketData]:
        """
        Subscribe to real-time data stream using instrument_keys

        Args:
            instrument_keys: List of primary identifiers
            data_types: Types of data to stream
            broker_id: Override default broker

        Yields:
            MarketData: Real-time data updates with metadata
        """
        target_broker = broker_id or self.default_broker

        # Resolve all tokens and get metadata
        token_mappings = {}
        metadata_cache = {}

        for instrument_key in instrument_keys:
            metadata = await self.instrument_client.get_instrument_metadata(instrument_key)
            broker_token = await self.instrument_client.resolve_broker_token(
                instrument_key, target_broker
            )

            token_mappings[broker_token] = instrument_key
            metadata_cache[instrument_key] = metadata

        logger.info(f"Starting stream for {len(instrument_keys)} instruments on {target_broker}")

        # Start broker stream with resolved tokens
        async for broker_data in self._stream_broker_data(
            list(token_mappings.keys()), data_types, target_broker
        ):
            # Map broker data back to instrument_key
            broker_token = broker_data.get('token')
            if broker_token in token_mappings:
                instrument_key = token_mappings[broker_token]
                metadata = metadata_cache[instrument_key]

                market_data = MarketData(
                    instrument_key=instrument_key,
                    symbol=metadata.symbol,
                    exchange=metadata.exchange,
                    data_type=DataType(broker_data.get('type', 'quotes')),
                    timestamp=datetime.now(),
                    data=broker_data.get('data', {}),
                    sector=metadata.sector,
                    _source_broker=target_broker,
                    _broker_token=broker_token
                )

                yield market_data

    # =============================================================================
    # INTERNAL BROKER DATA FETCHING (TOKEN-BASED)
    # =============================================================================

    async def _fetch_broker_historical_data(self,
                                          broker_token: str,
                                          timeframe: TimeFrame,
                                          periods: int,
                                          broker_id: str) -> pd.DataFrame:
        """
        Internal: Fetch historical data from broker using token

        This method handles broker-specific data fetching using resolved tokens.
        Never exposed in public API.
        """
        logger.debug(f"Fetching historical data: {broker_id} token={broker_token[:8]}***")

        # Simulate broker-specific data fetching
        await asyncio.sleep(0.2)  # Simulate network latency

        # Generate sample OHLCV data
        import numpy as np
        dates = pd.date_range(end=datetime.now(), periods=periods, freq='5T')
        base_price = 100.0

        data = {
            'timestamp': dates,
            'open': base_price + np.random.randn(periods) * 2,
            'high': base_price + np.random.randn(periods) * 2 + 1,
            'low': base_price + np.random.randn(periods) * 2 - 1,
            'close': base_price + np.random.randn(periods) * 2,
            'volume': np.random.randint(1000, 10000, periods)
        }

        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)

        logger.debug(f"Generated {len(df)} historical data points")
        return df

    async def _fetch_broker_quote(self, broker_token: str, broker_id: str) -> dict[str, Any]:
        """Internal: Fetch real-time quote from broker"""
        await asyncio.sleep(0.1)

        # Simulate real-time quote
        import random
        quote = {
            'ltp': round(100 + random.uniform(-5, 5), 2),
            'bid': round(99.5 + random.uniform(-5, 5), 2),
            'ask': round(100.5 + random.uniform(-5, 5), 2),
            'volume': random.randint(10000, 100000),
            'timestamp': datetime.now().isoformat()
        }

        return quote

    async def _stream_broker_data(self,
                                broker_tokens: list[str],
                                data_types: list[DataType],
                                broker_id: str) -> AsyncIterable[dict[str, Any]]:
        """Internal: Stream data from broker using tokens"""
        logger.debug(f"Starting broker stream: {broker_id} with {len(broker_tokens)} tokens")

        # Simulate streaming data
        import random
        while True:
            for token in broker_tokens:
                # Simulate data update
                data = {
                    'token': token,
                    'type': 'quotes',
                    'data': {
                        'ltp': round(100 + random.uniform(-2, 2), 2),
                        'volume': random.randint(100, 1000),
                        'timestamp': datetime.now().isoformat()
                    }
                }
                yield data

            await asyncio.sleep(1)  # 1 second between updates

    # =============================================================================
    # CACHE MANAGEMENT
    # =============================================================================

    def _get_from_cache(self, key: str, timeframe: TimeFrame) -> MarketData | None:
        """Get data from cache if not expired"""
        if key in self._data_cache:
            entry = self._data_cache[key]
            self._cache_ttl.get(timeframe, 300)

            if datetime.now() < entry["expires_at"]:
                return entry["value"]
            del self._data_cache[key]
        return None

    def _set_cache(self, key: str, value: MarketData, timeframe: TimeFrame) -> None:
        """Set data in cache with appropriate TTL"""
        ttl = self._cache_ttl.get(timeframe, 300)
        self._data_cache[key] = {
            "value": value,
            "expires_at": datetime.now() + timedelta(seconds=ttl)
        }

# Factory function
def create_data_client(default_broker: str = "kite") -> DataClient:
    """
    Create data client with registry integration

    Args:
        default_broker: Default broker for market data

    Returns:
        DataClient: Ready-to-use client
    """
    return DataClient(default_broker=default_broker)
