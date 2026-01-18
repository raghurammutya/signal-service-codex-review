# Database Contracts Documentation

**Version**: 1.0  
**Last Updated**: 2026-01-17  
**Status**: ✅ **PRODUCTION CERTIFIED**  

---

## 📋 Overview

This document defines and versions the database contracts that downstream services rely on for the Signal Service. All query patterns, table schemas, and data formats are documented here to ensure contract stability and detect breaking changes.

---

## 🗄️ Database Schema Contracts

### **Core Tables**

#### **signal_greeks** Table Contract
```sql
-- Table: signal_greeks
-- Purpose: Store option Greeks calculations with time-series optimization
-- TimescaleDB: Hypertable partitioned by timestamp

CREATE TABLE signal_greeks (
    id SERIAL PRIMARY KEY,
    signal_id VARCHAR(255) NOT NULL,
    instrument_key VARCHAR(255) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    delta DECIMAL(10,6),
    gamma DECIMAL(10,6),
    theta DECIMAL(10,6),
    vega DECIMAL(10,6),
    rho DECIMAL(10,6),
    implied_volatility DECIMAL(8,6),
    theoretical_value DECIMAL(12,4),
    underlying_price DECIMAL(12,4),
    strike_price DECIMAL(12,4),
    time_to_expiry DECIMAL(8,6),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Required Indexes
CREATE INDEX idx_signal_greeks_instrument_timestamp 
    ON signal_greeks (instrument_key, timestamp DESC);
CREATE INDEX idx_signal_greeks_signal_id 
    ON signal_greeks (signal_id);
```

**Contract Guarantees**:
- ✅ `instrument_key` format: `{EXCHANGE}@{SYMBOL}@{SEGMENT}` (e.g., `NSE@RELIANCE@EQ`)
- ✅ `timestamp` always in UTC timezone
- ✅ Greeks values: 6 decimal precision for delta/gamma/theta/vega/rho
- ✅ Implied volatility: 6 decimal precision (0.000001 to 9.999999)
- ✅ Prices: 4 decimal precision for currency values

#### **signal_indicators** Table Contract  
```sql
-- Table: signal_indicators
-- Purpose: Store technical indicator calculations with flexible JSON parameters
-- TimescaleDB: Hypertable partitioned by timestamp

CREATE TABLE signal_indicators (
    id SERIAL PRIMARY KEY,
    signal_id VARCHAR(255) NOT NULL,
    instrument_key VARCHAR(255) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    indicator_name VARCHAR(255) NOT NULL,
    parameters JSONB,
    values JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Required Indexes
CREATE INDEX idx_signal_indicators_instrument_indicator_timestamp 
    ON signal_indicators (instrument_key, indicator_name, timestamp DESC);
CREATE INDEX idx_signal_indicators_signal_id 
    ON signal_indicators (signal_id);
CREATE INDEX idx_signal_indicators_parameters 
    ON signal_indicators USING GIN (parameters);
```

**Contract Guarantees**:
- ✅ `indicator_name` follows pandas_ta naming convention (e.g., `RSI`, `MACD`, `BBANDS`)
- ✅ `parameters` JSON contains indicator-specific configuration
- ✅ `values` JSON contains computed indicator outputs
- ✅ JSON fields are never null (empty object `{}` for missing data)

#### **signal_moneyness_greeks** Table Contract
```sql
-- Table: signal_moneyness_greeks  
-- Purpose: Store aggregated Greeks by moneyness level
-- TimescaleDB: Hypertable partitioned by timestamp

CREATE TABLE signal_moneyness_greeks (
    id SERIAL PRIMARY KEY,
    underlying_symbol VARCHAR(255) NOT NULL,
    moneyness_level VARCHAR(50) NOT NULL,
    expiry_date DATE,
    timestamp TIMESTAMPTZ NOT NULL,
    spot_price DECIMAL(12,4) NOT NULL,
    
    -- Aggregated Greeks for all options
    all_delta DECIMAL(10,6),
    all_gamma DECIMAL(10,6),
    all_theta DECIMAL(10,6),
    all_vega DECIMAL(10,6),
    all_rho DECIMAL(10,6),
    all_iv DECIMAL(8,6),
    all_count INTEGER,
    
    -- Call options only
    calls_delta DECIMAL(10,6),
    calls_gamma DECIMAL(10,6),
    calls_theta DECIMAL(10,6),
    calls_vega DECIMAL(10,6),
    calls_rho DECIMAL(10,6),
    calls_iv DECIMAL(8,6),
    calls_count INTEGER,
    
    -- Put options only
    puts_delta DECIMAL(10,6),
    puts_gamma DECIMAL(10,6),
    puts_theta DECIMAL(10,6),
    puts_vega DECIMAL(10,6),
    puts_rho DECIMAL(10,6),
    puts_iv DECIMAL(8,6),
    puts_count INTEGER,
    
    -- Strike range information
    min_strike DECIMAL(12,4),
    max_strike DECIMAL(12,4),
    strike_count INTEGER,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Required Indexes
CREATE INDEX idx_moneyness_greeks_symbol_level_timestamp 
    ON signal_moneyness_greeks (underlying_symbol, moneyness_level, timestamp DESC);
```

**Contract Guarantees**:
- ✅ `moneyness_level` enum: `'DEEP_OTM'`, `'OTM'`, `'ATM'`, `'ITM'`, `'DEEP_ITM'`
- ✅ `underlying_symbol` matches base instrument (e.g., `RELIANCE` for `NSE@RELIANCE@EQ`)
- ✅ Count fields are always non-negative integers
- ✅ All Greeks aggregated using weighted averages by open interest

---

## 📊 Query Contracts for Downstream Services

### **1. Latest Greeks Retrieval**
**Service**: Dashboard Service, Alert Service  
**Contract**: Latest Greeks for instrument visualization

```sql
-- Contract: Get Latest Greeks
SELECT 
    id,
    signal_id,
    instrument_key,
    timestamp,
    delta,
    gamma,
    theta,
    vega,
    rho,
    implied_volatility,
    theoretical_value,
    underlying_price,
    strike_price,
    time_to_expiry
FROM signal_greeks 
WHERE instrument_key = $1 
ORDER BY timestamp DESC 
LIMIT 1;
```

**Response Contract**:
```json
{
  \"id\": 12345,
  \"signal_id\": \"signal_20260117_123456\",
  \"instrument_key\": \"NSE@RELIANCE@EQ\",
  \"timestamp\": \"2026-01-17T10:30:00.000Z\",
  \"delta\": 0.524876,
  \"gamma\": 0.001234,
  \"theta\": -0.045678,
  \"vega\": 0.123456,
  \"rho\": 0.098765,
  \"implied_volatility\": 0.245678,
  \"theoretical_value\": 2543.7500,
  \"underlying_price\": 2540.0000,
  \"strike_price\": 2550.0000,
  \"time_to_expiry\": 0.123456
}
```

### **2. Historical Greeks Aggregation** 
**Service**: Analytics Service, Backtesting Engine  
**Contract**: Time-bucketed historical Greeks data

```sql
-- Contract: Get Aggregated Historical Greeks
SELECT 
    time_bucket($4::interval, timestamp) as bucket,
    instrument_key,
    AVG(delta) as delta,
    AVG(gamma) as gamma,
    AVG(theta) as theta,
    AVG(vega) as vega,
    AVG(rho) as rho,
    AVG(implied_volatility) as implied_volatility,
    AVG(theoretical_value) as theoretical_value,
    AVG(underlying_price) as underlying_price,
    LAST(strike_price, timestamp) as strike_price,
    COUNT(*) as data_points
FROM signal_greeks
WHERE instrument_key = $1
  AND timestamp >= $2
  AND timestamp <= $3
GROUP BY bucket, instrument_key
ORDER BY bucket;
```

**Parameters Contract**:
- `$1`: instrument_key (VARCHAR) - Format: `{EXCHANGE}@{SYMBOL}@{SEGMENT}`
- `$2`: start_time (TIMESTAMPTZ) - UTC timezone required
- `$3`: end_time (TIMESTAMPTZ) - UTC timezone required  
- `$4`: interval (VARCHAR) - TimescaleDB interval (e.g., `'5 minutes'`, `'1 hour'`)

### **3. Latest Indicator Values**
**Service**: Signal Generation Service, Trading Engine  
**Contract**: Latest technical indicator calculations

```sql
-- Contract: Get Latest Indicator
SELECT
    id,
    signal_id,
    instrument_key,
    timestamp,
    indicator_name,
    parameters,
    values
FROM signal_indicators
WHERE instrument_key = $1
  AND indicator_name = $2
ORDER BY timestamp DESC
LIMIT 1;
```

**Response Contract**:
```json
{
  \"id\": 67890,
  \"signal_id\": \"signal_20260117_234567\",
  \"instrument_key\": \"NSE@TCS@EQ\",
  \"timestamp\": \"2026-01-17T11:45:00.000Z\",
  \"indicator_name\": \"RSI\",
  \"parameters\": {
    \"length\": 14,
    \"source\": \"close\"
  },
  \"values\": {
    \"RSI_14\": 65.432
  }
}
```

### **4. Moneyness Greeks Aggregation**
**Service**: Risk Management Service, Portfolio Analytics  
**Contract**: Aggregated Greeks by moneyness levels

```sql
-- Contract: Get Moneyness Greeks
SELECT 
    underlying_symbol,
    moneyness_level,
    timestamp,
    spot_price,
    all_delta,
    all_gamma,
    all_theta,
    all_vega,
    all_rho,
    all_iv,
    all_count,
    calls_delta,
    calls_gamma,
    calls_count,
    puts_delta,
    puts_gamma,
    puts_count,
    min_strike,
    max_strike,
    strike_count
FROM signal_moneyness_greeks
WHERE underlying_symbol = $1
  AND timestamp >= $2
  AND timestamp <= $3
ORDER BY timestamp DESC, moneyness_level;
```

---

## 🔧 TimescaleDB-Specific Contracts

### **Continuous Aggregates Support**
**Contract**: All tables support continuous aggregate creation

```sql
-- Example: Continuous Aggregate for Hourly Greeks
CREATE MATERIALIZED VIEW greeks_hourly
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', timestamp) AS bucket,
    instrument_key,
    AVG(delta) as avg_delta,
    AVG(gamma) as avg_gamma,
    AVG(theta) as avg_theta,
    AVG(vega) as avg_vega,
    AVG(rho) as avg_rho,
    COUNT(*) as data_points
FROM signal_greeks
GROUP BY bucket, instrument_key;
```

### **Hypertable Configuration**
**Contract**: All time-series tables are TimescaleDB hypertables

```sql
-- Hypertable conversion contract
SELECT create_hypertable('signal_greeks', 'timestamp', chunk_time_interval => INTERVAL '1 day');
SELECT create_hypertable('signal_indicators', 'timestamp', chunk_time_interval => INTERVAL '1 day');
SELECT create_hypertable('signal_moneyness_greeks', 'timestamp', chunk_time_interval => INTERVAL '1 day');
```

**Guarantees**:
- ✅ 1-day chunk intervals for optimal query performance
- ✅ Automatic partitioning by timestamp
- ✅ Parallel query execution support
- ✅ Compression policies for chunks older than 7 days

### **Retention Policies**
**Contract**: Automated data cleanup based on configurable retention

```sql
-- Default retention policy contract
SELECT add_retention_policy('signal_greeks', INTERVAL '90 days');
SELECT add_retention_policy('signal_indicators', INTERVAL '90 days');
SELECT add_retention_policy('signal_moneyness_greeks', INTERVAL '180 days');
```

---

## 📈 Performance Contracts

### **Query Performance Guarantees**

| Query Type | Max Response Time | Target Throughput |
|------------|------------------|-------------------|
| Latest Greeks Lookup | < 50ms | 1000 req/sec |
| Historical Aggregation (1 day) | < 200ms | 100 req/sec |
| Latest Indicator Lookup | < 30ms | 1500 req/sec |
| Moneyness Aggregation | < 100ms | 500 req/sec |

### **Connection Pool Contracts**
```python
# Production connection pool configuration
POOL_CONFIG = {
    "min_size": 2,
    "max_size": 10,
    "command_timeout": 30,
    "server_settings": {
        "application_name": "signal_service",
        "jit": "off"  # Disable JIT for predictable performance
    }
}
```

**Performance Guarantees**:
- ✅ Pool acquisition timeout: < 5 seconds
- ✅ Connection reuse ratio: > 95%
- ✅ Pool exhaustion alerts at 80% utilization

---

## 🛡️ Data Integrity Contracts

### **Transaction Isolation Levels**
```sql
-- Default isolation level for all transactions
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
```

### **Constraint Contracts**
```sql
-- Critical constraints that must be maintained
ALTER TABLE signal_greeks 
    ADD CONSTRAINT chk_greeks_timestamp_recent 
    CHECK (timestamp >= NOW() - INTERVAL '1 year');

ALTER TABLE signal_indicators 
    ADD CONSTRAINT chk_indicator_name_valid 
    CHECK (indicator_name ~ '^[A-Z][A-Z0-9_]*$');

ALTER TABLE signal_moneyness_greeks 
    ADD CONSTRAINT chk_moneyness_level_valid 
    CHECK (moneyness_level IN ('DEEP_OTM', 'OTM', 'ATM', 'ITM', 'DEEP_ITM'));
```

### **Data Validation Contracts**
```python
# Validation rules for data contracts
VALIDATION_RULES = {
    \"instrument_key\": r\"^[A-Z]+@[A-Z0-9]+@[A-Z]+$\",
    \"signal_id\": r\"^signal_\\d{8}_\\d{6}$\",
    \"delta_range\": (-5.0, 5.0),
    \"gamma_range\": (0.0, 10.0),
    \"implied_volatility_range\": (0.0, 5.0)
}
```

---

## 🔄 Versioning and Change Management

### **Schema Version Contract**
```sql
-- Schema versioning table contract
CREATE TABLE schema_version (
    id SERIAL PRIMARY KEY,
    version VARCHAR(20) NOT NULL,
    applied_at TIMESTAMPTZ DEFAULT NOW(),
    description TEXT
);

-- Current version
INSERT INTO schema_version (version, description) 
VALUES ('1.0.0', 'Initial production schema with TimescaleDB optimization');
```

### **Breaking Change Policy**
**Contract**: All breaking changes require 30-day deprecation notice

1. **Non-Breaking Changes** (immediate deployment allowed):
   - Adding new columns with DEFAULT values
   - Adding new indexes  
   - Adding new tables
   - Adding new stored procedures

2. **Breaking Changes** (requires deprecation period):
   - Removing columns
   - Changing column data types
   - Removing indexes used by downstream services
   - Changing table names
   - Changing constraint definitions

### **Migration Script Contracts**
```sql
-- Migration script template contract
-- Migration: V1.1.0__add_new_indicator_column.sql
-- Description: Add indicator_category column for enhanced categorization
-- Breaking: NO

BEGIN;
  -- Add new column with default
  ALTER TABLE signal_indicators 
    ADD COLUMN indicator_category VARCHAR(50) DEFAULT 'MOMENTUM';
  
  -- Update schema version
  INSERT INTO schema_version (version, description)
  VALUES ('1.1.0', 'Add indicator_category column');
COMMIT;
```

---

## 📊 Monitoring and Alerting Contracts

### **Database Health Metrics Contract**
```python
# Required health metrics for database contract compliance
HEALTH_METRICS = {
    \"connection_pool_utilization\": {
        \"threshold\": 80,  # Alert at 80% pool usage
        \"interval\": \"1m\"
    },
    \"query_duration_p95\": {
        \"threshold\": 100,  # Alert if 95th percentile > 100ms
        \"interval\": \"5m\"
    },
    \"table_size_growth_rate\": {
        \"threshold\": 1000000,  # Alert if table grows > 1M rows/hour
        \"interval\": \"1h\"
    },
    \"failed_query_rate\": {
        \"threshold\": 0.01,  # Alert if error rate > 1%
        \"interval\": \"5m\"  
    }
}
```

### **Automated Contract Validation**
```bash
# Nightly contract validation script
#!/bin/bash
# File: scripts/validate_database_contracts.sh

# Validate schema matches contracts
python scripts/database_zero_gap_validation.py --nightly

# Check query performance contracts
python scripts/query_performance_validation.py --contracts

# Validate data integrity constraints
python scripts/data_integrity_validation.py --full-scan

# Generate contract compliance report
python scripts/contract_compliance_report.py --output coverage_reports/
```

---

## 📋 Contract Testing Framework

### **Automated Contract Tests**
```python
# File: tests/contracts/test_database_contracts.py
class TestDatabaseContracts:
    \"\"\"Automated tests to validate database contracts.\"\"\"
    
    async def test_signal_greeks_schema_contract(self):
        \"\"\"Validate signal_greeks table matches contract specification.\"\"\"
        # Test schema structure, indexes, constraints
        
    async def test_latest_greeks_query_contract(self):
        \"\"\"Validate latest Greeks query response format.\"\"\"
        # Test query format and response structure
        
    async def test_performance_contracts(self):
        \"\"\"Validate query performance meets SLA contracts.\"\"\"
        # Test response times under load
        
    async def test_data_validation_contracts(self):
        \"\"\"Validate data integrity rules are enforced.\"\"\"
        # Test constraint validation and error handling
```

---

## 🚀 Production Deployment Contracts

### **Deployment Validation Checklist**
- ✅ Schema version matches contract specification
- ✅ All required indexes exist and are optimal
- ✅ Connection pool configuration matches contract
- ✅ Performance benchmarks meet SLA requirements
- ✅ Data integrity constraints are enforced
- ✅ Monitoring and alerting rules are active
- ✅ Backup and retention policies are configured

### **Rollback Contracts**
```sql
-- Emergency rollback procedures contract
-- Each deployment must include rollback scripts
-- File: migrations/rollback/V1.1.0_rollback.sql

BEGIN;
  -- Rollback indicator_category column addition
  ALTER TABLE signal_indicators DROP COLUMN IF EXISTS indicator_category;
  
  -- Rollback schema version
  DELETE FROM schema_version WHERE version = '1.1.0';
COMMIT;
```

---

**Document Maintainer**: Database Architecture Team  
**Review Frequency**: Monthly or before major releases  
**Contract Version**: 1.0.0  
**Next Review**: 2026-02-17