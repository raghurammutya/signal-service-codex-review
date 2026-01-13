# Timeframe Aggregation Implementation Plan

## Overview
Implement TimescaleDB continuous aggregates and custom indicators (anchored VWAP) for the signal service to support complex trading strategies.

## Phase 1: TimescaleDB Optimization (Day 1-2)

### 1.1 Create Migration for Continuous Aggregates

```sql
-- File: infrastructure/sql/migrations/V002__create_continuous_aggregates.sql

-- 5-minute continuous aggregate
CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_5min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minutes', time) AS bucket,
    instrument_key,
    first(open, time) as open,
    max(high) as high,
    min(low) as low,
    last(close, time) as close,
    sum(volume) as volume
FROM historical_data
WHERE interval = '1minute'
GROUP BY bucket, instrument_key
WITH NO DATA;

-- 15-minute continuous aggregate
CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_15min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('15 minutes', time) AS bucket,
    instrument_key,
    first(open, time) as open,
    max(high) as high,
    min(low) as low,
    last(close, time) as close,
    sum(volume) as volume
FROM historical_data
WHERE interval = '1minute'
GROUP BY bucket, instrument_key
WITH NO DATA;

-- 30-minute continuous aggregate
CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_30min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('30 minutes', time) AS bucket,
    instrument_key,
    first(open, time) as open,
    max(high) as high,
    min(low) as low,
    last(close, time) as close,
    sum(volume) as volume
FROM historical_data
WHERE interval = '1minute'
GROUP BY bucket, instrument_key
WITH NO DATA;

-- 1-hour continuous aggregate
CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_1hour
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    instrument_key,
    first(open, time) as open,
    max(high) as high,
    min(low) as low,
    last(close, time) as close,
    sum(volume) as volume
FROM historical_data
WHERE interval = '1minute'
GROUP BY bucket, instrument_key
WITH NO DATA;

-- Add refresh policies
SELECT add_continuous_aggregate_policy('ohlcv_5min',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute'
);

SELECT add_continuous_aggregate_policy('ohlcv_15min',
    start_offset => INTERVAL '2 hours',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes'
);

SELECT add_continuous_aggregate_policy('ohlcv_30min',
    start_offset => INTERVAL '4 hours',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '10 minutes'
);

SELECT add_continuous_aggregate_policy('ohlcv_1hour',
    start_offset => INTERVAL '8 hours',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '15 minutes'
);
```

### 1.2 Add Compression and Retention Policies

```sql
-- File: infrastructure/sql/migrations/V003__add_compression_policies.sql

-- Enable compression on historical_data
ALTER TABLE historical_data SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'instrument_key,interval',
    timescaledb.compress_orderby = 'time DESC'
);

-- Compress data older than 7 days
SELECT add_compression_policy('historical_data', INTERVAL '7 days');

-- Add compression to continuous aggregates
ALTER MATERIALIZED VIEW ohlcv_5min SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'instrument_key'
);

ALTER MATERIALIZED VIEW ohlcv_15min SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'instrument_key'
);

ALTER MATERIALIZED VIEW ohlcv_30min SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'instrument_key'
);

ALTER MATERIALIZED VIEW ohlcv_1hour SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'instrument_key'
);

-- Compress aggregates after 30 days
SELECT add_compression_policy('ohlcv_5min', INTERVAL '30 days');
SELECT add_compression_policy('ohlcv_15min', INTERVAL '30 days');
SELECT add_compression_policy('ohlcv_30min', INTERVAL '30 days');
SELECT add_compression_policy('ohlcv_1hour', INTERVAL '30 days');

-- Retention policies
SELECT add_retention_policy('historical_data', INTERVAL '3 months');
SELECT add_retention_policy('ohlcv_5min', INTERVAL '1 year');
SELECT add_retention_policy('ohlcv_15min', INTERVAL '2 years');
SELECT add_retention_policy('ohlcv_30min', INTERVAL '5 years');
SELECT add_retention_policy('ohlcv_1hour', INTERVAL '10 years');
```

## Phase 2: Signal Service Enhancements (Day 3-4)

### 2.1 Create Custom Indicators Module

```python
# File: services/signal_service/app/services/custom_indicators.py

import pandas as pd
import pandas_ta as ta
from datetime import datetime
from typing import Optional, List, Dict, Any
import numpy as np

from shared_architecture.utils.logging_utils import log_info, log_exception


class CustomIndicators:
    """Custom technical indicators not available in pandas_ta"""
    
    @staticmethod
    def anchored_vwap(df: pd.DataFrame, 
                     anchor_datetime: str,
                     high_col: str = 'high',
                     low_col: str = 'low', 
                     close_col: str = 'close',
                     volume_col: str = 'volume') -> pd.Series:
        """
        Calculate Anchored VWAP from a specific datetime
        
        Args:
            df: DataFrame with OHLCV data
            anchor_datetime: Datetime string to anchor VWAP calculation
            
        Returns:
            Series with anchored VWAP values
        """
        try:
            # Convert anchor_datetime to pandas datetime
            anchor_dt = pd.to_datetime(anchor_datetime)
            
            # Find anchor index
            if anchor_dt not in df.index:
                # Find nearest timestamp
                idx = df.index.get_indexer([anchor_dt], method='nearest')[0]
            else:
                idx = df.index.get_loc(anchor_dt)
            
            # Initialize result series
            result = pd.Series(index=df.index, dtype=float)
            result[:idx] = np.nan  # No VWAP before anchor
            
            # Calculate from anchor point
            df_subset = df.iloc[idx:]
            
            # Calculate typical price
            typical_price = (df_subset[high_col] + df_subset[low_col] + df_subset[close_col]) / 3
            
            # Calculate cumulative volume-weighted price
            cum_volume = df_subset[volume_col].cumsum()
            cum_vp = (typical_price * df_subset[volume_col]).cumsum()
            
            # Calculate anchored VWAP
            avwap = cum_vp / cum_volume
            
            # Fill result
            result.iloc[idx:] = avwap
            
            return result
            
        except Exception as e:
            log_exception(f"Error calculating anchored VWAP: {e}")
            return pd.Series(index=df.index, dtype=float)
    
    @staticmethod
    def swing_high(df: pd.DataFrame,
                  left_bars: int = 2,
                  right_bars: int = 2,
                  price_col: str = 'high') -> pd.Series:
        """
        Detect swing highs in price data
        
        Args:
            df: DataFrame with price data
            left_bars: Number of bars to left that must be lower
            right_bars: Number of bars to right that must be lower
            price_col: Column to analyze for swings
            
        Returns:
            Series with swing high prices (NaN for non-swing points)
        """
        try:
            result = pd.Series(index=df.index, dtype=float)
            prices = df[price_col].values
            
            for i in range(left_bars, len(prices) - right_bars):
                is_swing_high = True
                current_price = prices[i]
                
                # Check left side
                for j in range(1, left_bars + 1):
                    if prices[i - j] >= current_price:
                        is_swing_high = False
                        break
                
                # Check right side
                if is_swing_high:
                    for j in range(1, right_bars + 1):
                        if prices[i + j] >= current_price:
                            is_swing_high = False
                            break
                
                if is_swing_high:
                    result.iloc[i] = current_price
                else:
                    result.iloc[i] = np.nan
                    
            return result
            
        except Exception as e:
            log_exception(f"Error detecting swing highs: {e}")
            return pd.Series(index=df.index, dtype=float)
    
    @staticmethod
    def swing_low(df: pd.DataFrame,
                 left_bars: int = 2,
                 right_bars: int = 2,
                 price_col: str = 'low') -> pd.Series:
        """
        Detect swing lows in price data
        
        Args:
            df: DataFrame with price data
            left_bars: Number of bars to left that must be higher
            right_bars: Number of bars to right that must be higher
            price_col: Column to analyze for swings
            
        Returns:
            Series with swing low prices (NaN for non-swing points)
        """
        try:
            result = pd.Series(index=df.index, dtype=float)
            prices = df[price_col].values
            
            for i in range(left_bars, len(prices) - right_bars):
                is_swing_low = True
                current_price = prices[i]
                
                # Check left side
                for j in range(1, left_bars + 1):
                    if prices[i - j] <= current_price:
                        is_swing_low = False
                        break
                
                # Check right side
                if is_swing_low:
                    for j in range(1, right_bars + 1):
                        if prices[i + j] <= current_price:
                            is_swing_low = False
                            break
                
                if is_swing_low:
                    result.iloc[i] = current_price
                else:
                    result.iloc[i] = np.nan
                    
            return result
            
        except Exception as e:
            log_exception(f"Error detecting swing lows: {e}")
            return pd.Series(index=df.index, dtype=float)


def register_custom_indicators():
    """Register custom indicators with pandas_ta"""
    try:
        # Register anchored VWAP
        ta.register_custom_indicator(
            name="anchored_vwap",
            function=CustomIndicators.anchored_vwap,
            category="overlap"
        )
        
        # Register swing high
        ta.register_custom_indicator(
            name="swing_high",
            function=CustomIndicators.swing_high,
            category="volatility"
        )
        
        # Register swing low
        ta.register_custom_indicator(
            name="swing_low", 
            function=CustomIndicators.swing_low,
            category="volatility"
        )
        
        log_info("Custom indicators registered successfully")
        
    except Exception as e:
        log_exception(f"Error registering custom indicators: {e}")
```

### 2.2 Create Historical Data Writer

```python
# File: services/signal_service/app/services/historical_data_writer.py

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Set
import pandas as pd

from shared_architecture.connections.redis_cluster_manager import get_cluster_manager
from shared_architecture.config.redis_cluster_config import format_key
from shared_architecture.utils.logging_utils import log_info, log_exception, log_warning
from shared_architecture.db import get_async_db
from sqlalchemy import text

from app.core.config import settings


class HistoricalDataWriter:
    """
    Bridges real-time tick data to historical storage in TimescaleDB
    Aggregates ticks to 1-minute candles and stores them
    """
    
    def __init__(self):
        self.cluster_manager = None
        self.active_instruments: Set[str] = set()
        self.tick_buffer: Dict[str, List[Dict]] = {}
        self.last_flush = datetime.now()
        
    async def initialize(self):
        """Initialize the writer"""
        self.cluster_manager = await get_cluster_manager()
        log_info("Historical data writer initialized")
        
    async def run(self):
        """Main loop to persist real-time data"""
        await self.initialize()
        
        while True:
            try:
                # Get current minute
                now = datetime.now()
                current_minute = now.replace(second=0, microsecond=0)
                
                # Wait until next minute boundary
                next_minute = current_minute + timedelta(minutes=1)
                sleep_seconds = (next_minute - now).total_seconds()
                
                if sleep_seconds > 0:
                    await asyncio.sleep(sleep_seconds)
                
                # Process data for the completed minute
                await self._process_minute_data(current_minute)
                
            except Exception as e:
                log_exception(f"Error in historical data writer: {e}")
                await asyncio.sleep(5)
    
    async def _process_minute_data(self, minute_timestamp: datetime):
        """Process and store data for a completed minute"""
        try:
            # Get active instruments from subscription service
            active_instruments = await self._get_active_instruments()
            
            if not active_instruments:
                return
            
            # Collect tick data for each instrument
            candles = []
            
            for instrument_key in active_instruments:
                tick_data = await self._get_minute_ticks(instrument_key, minute_timestamp)
                
                if tick_data:
                    candle = self._aggregate_to_candle(tick_data, minute_timestamp)
                    if candle:
                        candle['instrument_key'] = instrument_key
                        candle['interval'] = '1minute'
                        candles.append(candle)
            
            # Batch insert to TimescaleDB
            if candles:
                await self._write_to_timescale(candles)
                log_info(f"Wrote {len(candles)} candles for minute {minute_timestamp}")
                
        except Exception as e:
            log_exception(f"Error processing minute data: {e}")
    
    async def _get_active_instruments(self) -> Set[str]:
        """Get list of actively monitored instruments"""
        try:
            # Get from subscription service tracking
            pattern = format_key("signal_service", "active_instruments", "*")
            keys = await self.cluster_manager.client.keys(pattern)
            
            instruments = set()
            for key in keys:
                instrument = key.split(":")[-1]
                instruments.add(instrument)
                
            return instruments
            
        except Exception as e:
            log_warning(f"Error getting active instruments: {e}")
            return set()
    
    async def _get_minute_ticks(self, instrument_key: str, minute: datetime) -> List[Dict]:
        """Get all ticks for an instrument in a specific minute"""
        try:
            # Read from ticker stream
            stream_key = format_key("ticker_service", "ticker_stream", symbol=instrument_key)
            
            # Calculate time range for the minute
            start_time = minute
            end_time = minute + timedelta(minutes=1)
            
            # Convert to milliseconds for Redis
            start_ms = int(start_time.timestamp() * 1000)
            end_ms = int(end_time.timestamp() * 1000)
            
            # Read entries in time range
            entries = await self.cluster_manager.client.xrange(
                stream_key,
                min=start_ms,
                max=end_ms
            )
            
            ticks = []
            for entry_id, data in entries:
                tick = {
                    'timestamp': entry_id,
                    'price': float(data.get(b'price', 0)),
                    'volume': int(data.get(b'volume', 0))
                }
                ticks.append(tick)
                
            return ticks
            
        except Exception as e:
            log_warning(f"Error getting ticks for {instrument_key}: {e}")
            return []
    
    def _aggregate_to_candle(self, ticks: List[Dict], timestamp: datetime) -> Optional[Dict]:
        """Aggregate tick data to OHLCV candle"""
        if not ticks:
            return None
            
        try:
            prices = [tick['price'] for tick in ticks if tick['price'] > 0]
            volumes = [tick['volume'] for tick in ticks]
            
            if not prices:
                return None
                
            return {
                'time': timestamp,
                'open': prices[0],
                'high': max(prices),
                'low': min(prices),
                'close': prices[-1],
                'volume': sum(volumes)
            }
            
        except Exception as e:
            log_warning(f"Error aggregating candle: {e}")
            return None
    
    async def _write_to_timescale(self, candles: List[Dict]):
        """Write candles to TimescaleDB"""
        async with get_async_db() as db:
            try:
                # Prepare batch insert
                values = []
                for candle in candles:
                    values.append({
                        'time': candle['time'],
                        'instrument_key': candle['instrument_key'],
                        'interval': candle['interval'],
                        'open': candle['open'],
                        'high': candle['high'],
                        'low': candle['low'],
                        'close': candle['close'],
                        'volume': candle['volume'],
                        'source': 'signal_service'
                    })
                
                # Batch insert with ON CONFLICT
                stmt = text("""
                    INSERT INTO historical_data 
                    (time, instrument_key, interval, open, high, low, close, volume, source)
                    VALUES (:time, :instrument_key, :interval, :open, :high, :low, :close, :volume, :source)
                    ON CONFLICT (time, instrument_key, interval) 
                    DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        volume = EXCLUDED.volume,
                        source = EXCLUDED.source
                """)
                
                for value in values:
                    await db.execute(stmt, value)
                    
                await db.commit()
                
            except Exception as e:
                await db.rollback()
                log_exception(f"Error writing to TimescaleDB: {e}")
```

### 2.3 Update Historical Data Manager

```python
# File: services/signal_service/app/services/historical_data_manager.py
# Add this method to the existing HistoricalDataManager class

async def _get_from_timescaledb(self, symbol: str, timeframe: str, periods: int) -> List[dict]:
    """Get historical data from TimescaleDB including continuous aggregates"""
    
    async with get_async_db() as db:
        try:
            # Map timeframe to table/view
            timeframe_mapping = {
                '1minute': 'historical_data',
                '5minute': 'ohlcv_5min',
                '15minute': 'ohlcv_15min',
                '30minute': 'ohlcv_30min',
                '1hour': 'ohlcv_1hour'
            }
            
            table_name = timeframe_mapping.get(timeframe, 'historical_data')
            
            # Calculate time range
            end_time = datetime.now(timezone.utc)
            
            # Calculate start time based on periods and timeframe
            minutes_per_period = {
                '1minute': 1,
                '5minute': 5,
                '15minute': 15,
                '30minute': 30,
                '1hour': 60
            }
            
            minutes = minutes_per_period.get(timeframe, 1) * periods
            start_time = end_time - timedelta(minutes=minutes)
            
            # Query appropriate table/view
            if table_name == 'historical_data':
                query = text("""
                    SELECT time, open, high, low, close, volume
                    FROM historical_data
                    WHERE instrument_key = :symbol
                    AND interval = :interval
                    AND time >= :start_time
                    AND time <= :end_time
                    ORDER BY time DESC
                    LIMIT :limit
                """)
                
                result = await db.execute(query, {
                    'symbol': symbol,
                    'interval': timeframe,
                    'start_time': start_time,
                    'end_time': end_time,
                    'limit': periods
                })
            else:
                # Query continuous aggregate
                query = text(f"""
                    SELECT bucket as time, open, high, low, close, volume
                    FROM {table_name}
                    WHERE instrument_key = :symbol
                    AND bucket >= :start_time
                    AND bucket <= :end_time
                    ORDER BY bucket DESC
                    LIMIT :limit
                """)
                
                result = await db.execute(query, {
                    'symbol': symbol,
                    'start_time': start_time,
                    'end_time': end_time,
                    'limit': periods
                })
            
            # Convert to list of dicts
            rows = result.fetchall()
            data = []
            
            for row in reversed(rows):  # Reverse to get chronological order
                data.append({
                    'timestamp': row.time.isoformat() + 'Z',
                    'open': float(row.open),
                    'high': float(row.high),
                    'low': float(row.low),
                    'close': float(row.close),
                    'volume': int(row.volume)
                })
            
            log_info(f"Retrieved {len(data)} rows from {table_name} for {symbol}")
            return data
            
        except Exception as e:
            log_exception(f"Failed to query TimescaleDB: {e}")
            raise
```

## Phase 3: Integration and Testing (Day 5)

### 3.1 Update Signal Service Startup

```python
# File: services/signal_service/app/main.py
# Add to startup event

from app.services.custom_indicators import register_custom_indicators
from app.services.historical_data_writer import HistoricalDataWriter

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    try:
        # ... existing code ...
        
        # Register custom indicators
        register_custom_indicators()
        
        # Start historical data writer
        if settings.ENABLE_HISTORICAL_WRITER:
            writer = HistoricalDataWriter()
            asyncio.create_task(writer.run())
            log_info("Historical data writer started")
            
    except Exception as e:
        log_exception(f"Startup error: {e}")
```

### 3.2 Create Tests

```python
# File: services/signal_service/tests/test_custom_indicators.py

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from app.services.custom_indicators import CustomIndicators


class TestCustomIndicators:
    
    def test_anchored_vwap(self):
        """Test anchored VWAP calculation"""
        # Create sample data
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1min')
        df = pd.DataFrame({
            'high': np.random.uniform(100, 102, 100),
            'low': np.random.uniform(98, 100, 100),
            'close': np.random.uniform(99, 101, 100),
            'volume': np.random.randint(1000, 5000, 100)
        }, index=dates)
        
        # Calculate anchored VWAP from middle point
        anchor = dates[50]
        result = CustomIndicators.anchored_vwap(df, anchor.isoformat())
        
        # Verify results
        assert len(result) == 100
        assert pd.isna(result[:50]).all()  # No values before anchor
        assert not pd.isna(result[50:]).any()  # All values after anchor
        
    def test_swing_high_detection(self):
        """Test swing high detection"""
        # Create data with known swing high
        prices = [100, 101, 102, 103, 102, 101, 100]  # Peak at index 3
        df = pd.DataFrame({
            'high': prices
        })
        
        result = CustomIndicators.swing_high(df, left_bars=2, right_bars=2)
        
        # Should detect swing high at index 3
        assert pd.isna(result[0])
        assert pd.isna(result[1])
        assert pd.isna(result[2])
        assert result[3] == 103  # Swing high
        assert pd.isna(result[4])
        
    def test_swing_low_detection(self):
        """Test swing low detection"""
        # Create data with known swing low
        prices = [103, 102, 101, 100, 101, 102, 103]  # Valley at index 3
        df = pd.DataFrame({
            'low': prices
        })
        
        result = CustomIndicators.swing_low(df, left_bars=2, right_bars=2)
        
        # Should detect swing low at index 3
        assert result[3] == 100  # Swing low
```

### 3.3 Create Integration Test

```python
# File: services/signal_service/tests/test_timeframe_integration.py

import pytest
import asyncio
from datetime import datetime, timedelta

from app.services.historical_data_manager import historical_data_manager
from app.services.pandas_ta_executor import PandasTAExecutor


@pytest.mark.asyncio
async def test_timeframe_aggregation():
    """Test retrieving data from different timeframes"""
    
    # Test getting 15-minute data
    symbol = "NSE@NIFTY@INDEX"
    periods = 20
    
    # Get data from continuous aggregate
    result = await historical_data_manager.get_historical_data_for_indicator(
        symbol=symbol,
        timeframe="15minute",
        periods_required=periods,
        indicator_name="sma"
    )
    
    assert result["success"]
    assert len(result["data"]) >= periods
    assert result["data_quality"] in ["EXCELLENT", "GOOD"]
    
    
@pytest.mark.asyncio
async def test_anchored_vwap_execution():
    """Test executing anchored VWAP indicator"""
    
    # Create executor
    executor = PandasTAExecutor(None)  # Mock redis
    
    # Test config with anchored VWAP
    config = {
        "technical_indicators": [{
            "name": "anchored_vwap",
            "parameters": {
                "anchor_datetime": "2024-01-01T11:00:00"
            },
            "output_key": "avwap"
        }]
    }
    
    # Execute indicator
    # ... test implementation ...
```

## Phase 4: Deployment and Monitoring (Day 6)

### 4.1 Configuration Updates

```yaml
# File: services/signal_service/config/production.yaml

historical_writer:
  enabled: true
  batch_size: 100
  flush_interval: 60  # seconds

timescaledb:
  continuous_aggregates:
    - name: ohlcv_5min
      refresh_interval: 60
    - name: ohlcv_15min
      refresh_interval: 300
    - name: ohlcv_30min
      refresh_interval: 600
    - name: ohlcv_1hour
      refresh_interval: 900
      
custom_indicators:
  enabled: true
  indicators:
    - anchored_vwap
    - swing_high
    - swing_low
```

### 4.2 Monitoring Queries

```sql
-- File: infrastructure/monitoring/timescaledb_health.sql

-- Check continuous aggregate lag
SELECT 
    view_name,
    refresh_lag,
    last_refresh,
    next_refresh
FROM timescaledb_information.continuous_aggregate_stats;

-- Check compression status
SELECT 
    hypertable_name,
    uncompressed_size,
    compressed_size,
    compression_ratio
FROM timescaledb_information.compressed_hypertable_stats;

-- Check data freshness
SELECT 
    instrument_key,
    MAX(time) as latest_data,
    NOW() - MAX(time) as data_lag
FROM historical_data
WHERE time > NOW() - INTERVAL '1 hour'
GROUP BY instrument_key
HAVING NOW() - MAX(time) > INTERVAL '5 minutes';
```

## Success Criteria

1. **Continuous Aggregates**: All 4 timeframes operational with < 1 minute lag
2. **Custom Indicators**: Anchored VWAP and swing detection working
3. **Historical Writer**: Writing 1-minute candles with < 2 minute delay
4. **Storage Efficiency**: 80%+ compression ratio achieved
5. **Query Performance**: 15-minute data queries < 100ms
6. **Test Coverage**: All new code with 80%+ test coverage

## Rollback Plan

1. Disable historical writer via config
2. Drop continuous aggregates (data remains in base table)
3. Revert to fallback strategies in historical_data_manager
4. Remove custom indicator registration

## Next Steps

After successful implementation:
1. Add more custom indicators (pivot points, market profile)
2. Implement 4-hour and daily continuous aggregates
3. Add data quality monitoring dashboard
4. Create performance benchmarks for different query patterns