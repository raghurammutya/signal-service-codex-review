"""Updated historical data manager methods to use continuous aggregates (stub)."""

from datetime import datetime, timedelta
from typing import List
from sqlalchemy import text


async def get_async_db():
    """Fallback async context manager used in tests."""

    class _DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, *_args, **_kwargs):
            class _Result:
                def fetchall(self):
                    return []

            return _Result()

    return _DummySession()


async def _get_from_timescaledb(self, symbol: str, timeframe: str, periods: int) -> List[dict]:
    """Build a query against continuous aggregates; returns empty results."""
    timeframe_mapping = {
        "1m": ("historical_data", "1minute", 1),
        "1minute": ("historical_data", "1minute", 1),
        "5m": ("ohlcv_5min", None, 5),
        "5minute": ("ohlcv_5min", None, 5),
        "15m": ("ohlcv_15min", None, 15),
        "15minute": ("ohlcv_15min", None, 15),
        "30m": ("ohlcv_30min", None, 30),
        "30minute": ("ohlcv_30min", None, 30),
        "1h": ("ohlcv_1hour", None, 60),
        "1hour": ("ohlcv_1hour", None, 60),
    }

    table_name, interval, minutes_per_period = timeframe_mapping.get(timeframe, ("historical_data", "1minute", 1))

    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=minutes_per_period * periods)

    query = text(
        f"""
        SELECT bucket as time, open, high, low, close, volume
        FROM {table_name}
        WHERE instrument_key = :symbol
        AND bucket >= :start_time
        AND bucket <= :end_time
        ORDER BY bucket DESC
        LIMIT :limit
    """
    )

    async with (await get_async_db()) as db:
        await db.execute(
            query,
            {"symbol": symbol, "start_time": start_time, "end_time": end_time, "limit": periods},
        )

    return []
