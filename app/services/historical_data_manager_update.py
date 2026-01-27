"""
Historical data manager requiring proper TimescaleDB integration.
Production implementation removed to enforce proper database integration.
"""



class HistoricalDataAccessError(Exception):
    """Exception raised when historical data access requires proper implementation"""


async def get_async_db():
    """Database context manager requiring proper TimescaleDB integration."""
    raise HistoricalDataAccessError(
        "Historical data access requires TimescaleDB integration - cannot provide stub database session"
    )


def require_timescale_implementation():
    """Utility function to enforce TimescaleDB implementation requirement"""
    raise HistoricalDataAccessError(
        "TimescaleDB continuous aggregates implementation required for historical data management"
    )


# All historical data methods require proper TimescaleDB implementation
async def get_historical_ohlc(*args, **kwargs):
    """Get historical OHLC data - requires TimescaleDB integration"""
    require_timescale_implementation()


async def get_continuous_aggregate_data(*args, **kwargs):
    """Get continuous aggregate data - requires TimescaleDB integration"""
    require_timescale_implementation()


async def update_historical_indicators(*args, **kwargs):
    """Update historical indicators - requires TimescaleDB integration"""
    require_timescale_implementation()
