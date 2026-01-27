"""Simplified historical data writer used in tests."""

import asyncio
import logging
from datetime import datetime

from app.utils.redis import get_redis_client

logger = logging.getLogger(__name__)


class HistoricalDataWriter:
    """Bridges real-time tick data to historical storage (stub)."""

    def __init__(self):
        self.cluster_manager = None
        self.active_instruments: set[str] = set()
        self.tick_buffer: dict[str, list[dict]] = {}
        self.running = False

    async def initialize(self):
        redis_client = await get_redis_client()
        self.cluster_manager = type("Cluster", (), {"client": redis_client})
        logger.info("Historical data writer initialized")

    async def _get_active_instruments(self) -> set[str]:
        """Return active instruments from Redis or in-memory set."""
        instruments: set[str] = set(self.active_instruments)
        try:
            keys = await self.cluster_manager.client.keys("subscription_service:active_subscriptions:*")
            for key in keys:
                key_str = key.decode("utf-8") if isinstance(key, bytes) else str(key)
                parts = key_str.split(":")
                if parts:
                    instruments.add(parts[-1])
        except Exception:
            logger.debug("Falling back to in-memory active instruments")
        return instruments

    async def _get_minute_ticks(self, instrument_key: str, minute: datetime) -> list[dict]:
        """Fetch buffered ticks for the minute (stubbed)."""
        return self.tick_buffer.get(instrument_key, [])

    def _aggregate_to_candle(self, ticks: list[dict], minute: datetime, instrument_key: str) -> dict | None:
        """Aggregate tick list into a simple OHLCV candle."""
        if not ticks:
            return None
        prices = [t.get("price", 0) for t in ticks]
        volumes = [t.get("volume", 0) for t in ticks]
        return {
            "instrument_key": instrument_key,
            "interval": "1minute",
            "timestamp": minute.isoformat(),
            "open": prices[0],
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1],
            "volume": sum(volumes),
        }

    async def _write_to_timescale(self, candles: list[dict]):
        """Stubbed persistence."""
        logger.debug("Pretending to write %s candles", len(candles))

    async def _process_minute_data(self, minute_timestamp: datetime):
        active_instruments = await self._get_active_instruments()
        if not active_instruments:
            return

        candles: list[dict] = []
        for instrument_key in active_instruments:
            ticks = await self._get_minute_ticks(instrument_key, minute_timestamp)
            candle = self._aggregate_to_candle(ticks, minute_timestamp, instrument_key)
            if candle:
                candles.append(candle)

        if candles:
            await self._write_to_timescale(candles)

    async def run(self):
        """Minimal loop for completeness."""
        await self.initialize()
        self.running = True
        while self.running:
            now = datetime.now().replace(second=0, microsecond=0)
            await self._process_minute_data(now)
            await asyncio.sleep(60)

    async def stop(self):
        self.running = False
