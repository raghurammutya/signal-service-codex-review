# Timeframe Aggregation Deployment Guide

## Overview
This guide covers the deployment of TimescaleDB continuous aggregates and custom indicators for the signal service.

## Phase 1: Database Migration (Day 1)

### 1.1 Pre-deployment Checks
```bash
# Check TimescaleDB version (requires 2.0+)
SELECT version();
SELECT extversion FROM pg_extension WHERE extname = 'timescaledb';

# Check existing hypertables
SELECT hypertable_name, chunk_time_interval 
FROM timescaledb_information.hypertables;

# Estimate data size
SELECT 
    pg_size_pretty(pg_total_relation_size('historical_data')) as total_size,
    count(*) as row_count
FROM historical_data;
```

### 1.2 Run Migrations
```bash
# Connect to database
psql -h $DB_HOST -U $DB_USER -d tradingdb

# Run migration scripts in order
\i infrastructure/sql/migrations/V002__create_continuous_aggregates.sql
\i infrastructure/sql/migrations/V003__add_compression_policies.sql

# Verify continuous aggregates
SELECT view_name, refresh_lag 
FROM timescaledb_information.continuous_aggregate_stats;
```

### 1.3 Initial Data Refresh
```sql
-- Manually refresh aggregates for existing data
CALL refresh_continuous_aggregate('ohlcv_5min', 
    NOW() - INTERVAL '7 days', NOW());
CALL refresh_continuous_aggregate('ohlcv_15min', 
    NOW() - INTERVAL '7 days', NOW());
CALL refresh_continuous_aggregate('ohlcv_30min', 
    NOW() - INTERVAL '7 days', NOW());
CALL refresh_continuous_aggregate('ohlcv_1hour', 
    NOW() - INTERVAL '7 days', NOW());
```

## Phase 2: Code Deployment (Day 2)

### 2.1 Update Signal Service
```bash
# Update code
cd services/signal_service

# Install any new dependencies
pip install -r requirements.txt

# Apply configuration updates
# Add to .env or environment:
export ENABLE_HISTORICAL_WRITER=true
export ENABLE_CUSTOM_INDICATORS=true
export TIMESCALEDB_COMPRESSION_AFTER_DAYS=7
export TIMESCALEDB_RETENTION_MONTHS=3
```

### 2.2 Deploy Updated Service
```bash
# Build new image
docker build -t signal_service:v2.0 .

# Rolling update (if using Kubernetes)
kubectl set image deployment/signal-service signal-service=signal_service:v2.0

# Or docker-compose
docker-compose up -d signal_service
```

### 2.3 Verify Deployment
```bash
# Check service health
curl http://localhost:8003/health

# Check new endpoints
curl http://localhost:8003/api/v1/timeframe-aggregation/status

# Monitor logs
docker logs -f signal_service_container
```

## Phase 3: Testing & Validation (Day 3)

### 3.1 Test Custom Indicators
```python
# Test anchored VWAP
curl -X POST http://localhost:8003/api/v1/compute \
  -H "Content-Type: application/json" \
  -d '{
    "instrument_key": "NSE@NIFTY@INDEX",
    "indicators": [{
      "name": "anchored_vwap",
      "parameters": {
        "anchor_datetime": "2024-01-01T09:15:00"
      }
    }]
  }'
```

### 3.2 Verify Historical Data Writing
```sql
-- Check if new data is being written
SELECT 
    date_trunc('minute', time) as minute,
    count(*) as candle_count
FROM historical_data
WHERE time > NOW() - INTERVAL '1 hour'
  AND interval = '1minute'
GROUP BY 1
ORDER BY 1 DESC
LIMIT 10;
```

### 3.3 Test Continuous Aggregates
```sql
-- Query 5-minute data
SELECT * FROM ohlcv_5min
WHERE instrument_key = 'NSE@NIFTY@INDEX'
  AND bucket > NOW() - INTERVAL '1 day'
ORDER BY bucket DESC
LIMIT 20;

-- Compare performance
EXPLAIN ANALYZE
SELECT * FROM ohlcv_15min
WHERE instrument_key = 'NSE@BANKNIFTY@INDEX'
  AND bucket > NOW() - INTERVAL '7 days';
```

## Phase 4: Monitoring Setup (Day 4)

### 4.1 Create Monitoring Dashboard
```sql
-- Create monitoring views
CREATE VIEW aggregation_health AS
SELECT 
    ca.view_name,
    ca.refresh_lag,
    ca.last_refresh,
    ca.next_refresh,
    CASE 
        WHEN refresh_lag > INTERVAL '5 minutes' THEN 'DELAYED'
        WHEN refresh_lag > INTERVAL '2 minutes' THEN 'WARNING'
        ELSE 'HEALTHY'
    END as status
FROM timescaledb_information.continuous_aggregate_stats ca;

-- Compression effectiveness
CREATE VIEW compression_stats AS
SELECT 
    hypertable_name,
    pg_size_pretty(uncompressed_total_bytes) as uncompressed,
    pg_size_pretty(compressed_total_bytes) as compressed,
    compression_ratio || '%' as ratio
FROM timescaledb_information.hypertable_compression_stats;
```

### 4.2 Setup Alerts
```yaml
# Prometheus alerts
groups:
  - name: timescaledb_alerts
    rules:
      - alert: ContinuousAggregateDelayed
        expr: timescaledb_continuous_aggregate_lag_seconds > 300
        annotations:
          summary: "Continuous aggregate {{ $labels.view_name }} is delayed"
      
      - alert: HistoricalDataWriterDown
        expr: signal_service_historical_writer_running == 0
        for: 5m
        annotations:
          summary: "Historical data writer is not running"
```

### 4.3 Performance Metrics
```python
# Add to signal service metrics endpoint
async def get_timeframe_metrics():
    return {
        "continuous_aggregates": {
            "5min": await check_aggregate_health("ohlcv_5min"),
            "15min": await check_aggregate_health("ohlcv_15min"),
            "30min": await check_aggregate_health("ohlcv_30min"),
            "1hour": await check_aggregate_health("ohlcv_1hour")
        },
        "cache_stats": app.state.timeframe_cache_manager.get_statistics(),
        "writer_status": {
            "running": app.state.historical_data_writer.running,
            "last_flush": app.state.historical_data_writer.last_flush
        }
    }
```

## Rollback Plan

### If Issues Occur:
```bash
# 1. Disable historical writer
export ENABLE_HISTORICAL_WRITER=false

# 2. Drop continuous aggregates (data remains)
psql -c "DROP MATERIALIZED VIEW IF EXISTS ohlcv_5min CASCADE;"
psql -c "DROP MATERIALIZED VIEW IF EXISTS ohlcv_15min CASCADE;"
psql -c "DROP MATERIALIZED VIEW IF EXISTS ohlcv_30min CASCADE;"
psql -c "DROP MATERIALIZED VIEW IF EXISTS ohlcv_1hour CASCADE;"

# 3. Revert code
git revert <commit-hash>

# 4. Redeploy previous version
kubectl rollout undo deployment/signal-service
```

## Performance Tuning

### 1. Optimize Chunk Size
```sql
-- Check current chunk sizes
SELECT 
    hypertable_name,
    chunk_time_interval
FROM timescaledb_information.hypertables;

-- Adjust if needed (for new chunks)
SELECT set_chunk_time_interval('historical_data', INTERVAL '6 hours');
```

### 2. Index Optimization
```sql
-- Add covering index for common queries
CREATE INDEX idx_historical_data_covering 
ON historical_data (instrument_key, time DESC) 
INCLUDE (open, high, low, close, volume)
WHERE interval = '1minute';
```

### 3. Cache Warmup
```python
# Add to startup routine
async def warmup_caches():
    popular_instruments = [
        "NSE@NIFTY@INDEX",
        "NSE@BANKNIFTY@INDEX",
        "NSE@RELIANCE@EQUITY"
    ]
    
    for instrument in popular_instruments:
        for timeframe in ["5minute", "15minute", "1hour"]:
            await cache_manager.warm_cache(instrument, [timeframe])
```

## Maintenance Tasks

### Daily
- Monitor continuous aggregate lag
- Check compression ratio
- Verify data completeness

### Weekly
- Review cache hit rates
- Optimize slow queries
- Update statistics: `ANALYZE historical_data;`

### Monthly
- Review retention policies
- Check disk usage trends
- Validate backups include continuous aggregates

## Success Metrics

1. **Query Performance**
   - 15-minute data queries < 100ms (target: 50ms)
   - Cache hit rate > 80% (target: 90%)

2. **Storage Efficiency**
   - Compression ratio > 80%
   - Storage growth < 10GB/month for 10k instruments

3. **Data Freshness**
   - Continuous aggregate lag < 2 minutes
   - Historical writer success rate > 99%

4. **System Stability**
   - No OOM errors
   - CPU usage < 70% average
   - Memory usage stable

## Support & Troubleshooting

### Common Issues:

1. **Continuous aggregate not refreshing**
   ```sql
   -- Check policy
   SELECT * FROM timescaledb_information.job_stats 
   WHERE job_id IN (
     SELECT job_id FROM timescaledb_information.continuous_aggregate_stats
   );
   
   -- Manual refresh
   CALL refresh_continuous_aggregate('ohlcv_5min', 
     NOW() - INTERVAL '1 hour', NOW());
   ```

2. **High memory usage**
   ```bash
   # Adjust cache sizes
   export TIMEFRAME_CACHE_MAX_AGE=1800  # 30 minutes
   export MAX_CONCURRENT_AGGREGATIONS=3
   ```

3. **Slow queries**
   ```sql
   -- Update statistics
   ANALYZE historical_data;
   ANALYZE ohlcv_5min;
   
   -- Check query plan
   EXPLAIN (ANALYZE, BUFFERS) <your_query>;
   ```

## Next Steps

1. Add 4-hour and daily continuous aggregates
2. Implement data quality monitoring
3. Create performance benchmarks
4. Add more custom indicators
5. Implement cross-instrument aggregations