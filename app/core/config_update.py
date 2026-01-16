"""Configuration updates for timeframe aggregation

ARCHITECTURE COMPLIANCE NOTE:
All configuration values MUST be sourced from config_service exclusively.
NO hardcoded defaults allowed per Architecture Principle #1.

The following configurations should be added to config_service:
"""

# Historical Data Writer (config_service keys)
# ENABLE_HISTORICAL_WRITER (required in config_service)
# HISTORICAL_WRITER_BATCH_SIZE (required in config_service)  
# HISTORICAL_WRITER_FLUSH_INTERVAL (required in config_service)

# TimescaleDB Configuration (config_service keys)
# TIMESCALEDB_CONTINUOUS_AGGREGATES (required in config_service)
# TIMESCALEDB_CHUNK_INTERVAL_HOURS (required in config_service)
# TIMESCALEDB_COMPRESSION_AFTER_DAYS (required in config_service)
# TIMESCALEDB_RETENTION_MONTHS (required in config_service)

# Timeframe Cache Configuration (config_service keys)  
# TIMEFRAME_CACHE_CLEANUP_INTERVAL (required in config_service)
# TIMEFRAME_CACHE_MAX_AGE (required in config_service)
# TIMEFRAME_CACHE_TTL_MAP (required in config_service as JSON)

# Custom Indicators (config_service keys)
# ENABLE_CUSTOM_INDICATORS (required in config_service)
# CUSTOM_INDICATORS_LIST (required in config_service as JSON array)

# Aggregation Configuration (config_service keys)
# ENABLE_ON_DEMAND_AGGREGATION (required in config_service)  
# AGGREGATION_FACTORS (required in config_service as JSON)

# Performance Tuning (config_service keys)
# MAX_CONCURRENT_AGGREGATIONS (required in config_service)
# AGGREGATION_TIMEOUT_SECONDS (required in config_service)
# CACHE_WARMUP_ENABLED (required in config_service)
# CACHE_WARMUP_INSTRUMENTS (required in config_service as JSON array)

# Helper methods to add to the config class
# NOTE: These methods must be implemented to get values from config_service
# with NO hardcoded defaults per Architecture Principle #1

def get_cache_ttl_for_timeframe(self, timeframe: str) -> int:
    """Get cache TTL for a specific timeframe from config_service"""
    # Implementation must get TIMEFRAME_CACHE_TTL_MAP from config_service
    # NO hardcoded defaults allowed
    pass

def get_aggregation_factor(self, source: str, target: str) -> Optional[int]:
    """Get aggregation factor between timeframes from config_service"""  
    # Implementation must get AGGREGATION_FACTORS from config_service
    # NO hardcoded defaults allowed
    pass