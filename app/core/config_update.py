"""Configuration updates for timeframe aggregation"""

# Add these to the SignalServiceConfig class:

# Historical Data Writer
ENABLE_HISTORICAL_WRITER: bool = Field(default=True, env="ENABLE_HISTORICAL_WRITER")
HISTORICAL_WRITER_BATCH_SIZE: int = Field(default=100, env="HISTORICAL_WRITER_BATCH_SIZE")
HISTORICAL_WRITER_FLUSH_INTERVAL: int = Field(default=60, env="HISTORICAL_WRITER_FLUSH_INTERVAL")

# TimescaleDB Configuration
TIMESCALEDB_CONTINUOUS_AGGREGATES: List[str] = Field(
    default=["ohlcv_5min", "ohlcv_15min", "ohlcv_30min", "ohlcv_1hour"],
    env="TIMESCALEDB_CONTINUOUS_AGGREGATES"
)
TIMESCALEDB_CHUNK_INTERVAL_HOURS: int = Field(default=24, env="TIMESCALEDB_CHUNK_INTERVAL_HOURS")
TIMESCALEDB_COMPRESSION_AFTER_DAYS: int = Field(default=7, env="TIMESCALEDB_COMPRESSION_AFTER_DAYS")
TIMESCALEDB_RETENTION_MONTHS: int = Field(default=3, env="TIMESCALEDB_RETENTION_MONTHS")

# Timeframe Cache Configuration
TIMEFRAME_CACHE_CLEANUP_INTERVAL: int = Field(default=300, env="TIMEFRAME_CACHE_CLEANUP_INTERVAL")  # 5 minutes
TIMEFRAME_CACHE_MAX_AGE: int = Field(default=3600, env="TIMEFRAME_CACHE_MAX_AGE")  # 1 hour
TIMEFRAME_CACHE_TTL_MAP: Dict[str, int] = Field(
    default={
        "1minute": 300,     # 5 minutes
        "5minute": 600,     # 10 minutes
        "15minute": 1800,   # 30 minutes
        "30minute": 3600,   # 1 hour
        "1hour": 7200,      # 2 hours
        "4hour": 14400,     # 4 hours
        "1day": 86400       # 24 hours
    },
    env="TIMEFRAME_CACHE_TTL_MAP"
)

# Custom Indicators
ENABLE_CUSTOM_INDICATORS: bool = Field(default=True, env="ENABLE_CUSTOM_INDICATORS")
CUSTOM_INDICATORS_LIST: List[str] = Field(
    default=["anchored_vwap", "swing_high", "swing_low", "combined_premium", "premium_ratio"],
    env="CUSTOM_INDICATORS_LIST"
)

# Aggregation Configuration
ENABLE_ON_DEMAND_AGGREGATION: bool = Field(default=True, env="ENABLE_ON_DEMAND_AGGREGATION")
AGGREGATION_FACTORS: Dict[str, int] = Field(
    default={
        "1minute_5minute": 5,
        "5minute_15minute": 3,
        "15minute_30minute": 2,
        "30minute_1hour": 2,
        "1hour_4hour": 4,
        "1minute_15minute": 15,
        "1minute_30minute": 30,
        "1minute_1hour": 60
    },
    env="AGGREGATION_FACTORS"
)

# Performance Tuning
MAX_CONCURRENT_AGGREGATIONS: int = Field(default=5, env="MAX_CONCURRENT_AGGREGATIONS")
AGGREGATION_TIMEOUT_SECONDS: int = Field(default=10, env="AGGREGATION_TIMEOUT_SECONDS")
CACHE_WARMUP_ENABLED: bool = Field(default=True, env="CACHE_WARMUP_ENABLED")
CACHE_WARMUP_INSTRUMENTS: List[str] = Field(
    default=["NSE@NIFTY@INDEX", "NSE@BANKNIFTY@INDEX"],
    env="CACHE_WARMUP_INSTRUMENTS"
)

# Helper methods to add to the config class
def get_cache_ttl_for_timeframe(self, timeframe: str) -> int:
    """Get cache TTL for a specific timeframe"""
    return self.TIMEFRAME_CACHE_TTL_MAP.get(timeframe, 3600)

def get_aggregation_factor(self, source: str, target: str) -> Optional[int]:
    """Get aggregation factor between timeframes"""
    key = f"{source}_{target}"
    return self.AGGREGATION_FACTORS.get(key)