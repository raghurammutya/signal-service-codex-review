-- Initialize test database schema for signal_service
-- This script sets up the required tables and extensions for testing

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create test schema
CREATE SCHEMA IF NOT EXISTS test_data;

-- Signal Greeks table
CREATE TABLE IF NOT EXISTS signal_greeks (
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

-- Convert to hypertable for time-series optimization
SELECT create_hypertable('signal_greeks', 'timestamp', if_not_exists => TRUE);

-- Signal Indicators table
CREATE TABLE IF NOT EXISTS signal_indicators (
    id SERIAL PRIMARY KEY,
    signal_id VARCHAR(255) NOT NULL,
    instrument_key VARCHAR(255) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    indicator_name VARCHAR(255) NOT NULL,
    parameters JSONB,
    values JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Convert to hypertable
SELECT create_hypertable('signal_indicators', 'timestamp', if_not_exists => TRUE);

-- Custom Timeframe Data table (renamed to match code expectations)
CREATE TABLE IF NOT EXISTS signal_custom_timeframes (
    id SERIAL PRIMARY KEY,
    instrument_key VARCHAR(255) NOT NULL,
    data_type VARCHAR(100) NOT NULL, -- 'greeks', 'indicators', etc.
    timeframe_minutes INTEGER NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Convert to hypertable
SELECT create_hypertable('signal_custom_timeframes', 'timestamp', if_not_exists => TRUE);

-- Moneyness Greeks table (required by signal repository)
CREATE TABLE IF NOT EXISTS signal_moneyness_greeks (
    id SERIAL PRIMARY KEY,
    underlying VARCHAR(50) NOT NULL,
    moneyness_level VARCHAR(20) NOT NULL,
    expiry_date DATE NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    delta DECIMAL(10,6),
    gamma DECIMAL(10,6),
    theta DECIMAL(10,6),
    vega DECIMAL(10,6),
    rho DECIMAL(10,6),
    iv DECIMAL(10,6),
    theoretical_value DECIMAL(15,6),
    option_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Convert to hypertable
SELECT create_hypertable('signal_moneyness_greeks', 'timestamp', if_not_exists => TRUE);

-- Market Data table for Smart Money testing
CREATE TABLE IF NOT EXISTS market_data (
    id SERIAL PRIMARY KEY,
    instrument_key VARCHAR(255) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    open DECIMAL(12,4),
    high DECIMAL(12,4),
    low DECIMAL(12,4),
    close DECIMAL(12,4),
    volume BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Convert to hypertable
SELECT create_hypertable('market_data', 'timestamp', if_not_exists => TRUE);

-- Test Computation Metrics table
CREATE TABLE IF NOT EXISTS computation_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    operation_type VARCHAR(100) NOT NULL,
    duration_ms INTEGER,
    memory_usage_mb DECIMAL(8,2),
    cpu_usage_percent DECIMAL(5,2),
    error_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Convert to hypertable
SELECT create_hypertable('computation_metrics', 'timestamp', if_not_exists => TRUE);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_signal_greeks_instrument_timestamp 
    ON signal_greeks (instrument_key, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signal_greeks_signal_id 
    ON signal_greeks (signal_id);

CREATE INDEX IF NOT EXISTS idx_signal_indicators_instrument_timestamp 
    ON signal_indicators (instrument_key, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signal_indicators_name 
    ON signal_indicators (indicator_name);
CREATE INDEX IF NOT EXISTS idx_signal_indicators_signal_id 
    ON signal_indicators (signal_id);

CREATE INDEX IF NOT EXISTS idx_custom_timeframe_data_key_type_timestamp 
    ON custom_timeframe_data (instrument_key, data_type, timeframe_minutes, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_market_data_instrument_timestamp 
    ON market_data (instrument_key, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_computation_metrics_operation_timestamp 
    ON computation_metrics (operation_type, timestamp DESC);

-- Insert test data for validation
INSERT INTO test_data.sample_instruments AS sample_instruments (instrument_key, symbol, option_type, strike_price, expiry_date) 
SELECT * FROM (VALUES 
    ('NSE@TESTSYM@CE@20000', 'TESTSYM', 'call', 20000, '2024-12-28'),
    ('NSE@TESTSYM@PE@20000', 'TESTSYM', 'put', 20000, '2024-12-28'),
    ('NSE@TESTSYM@CE@19500', 'TESTSYM', 'call', 19500, '2024-12-28'),
    ('NSE@TESTSYM@PE@20500', 'TESTSYM', 'put', 20500, '2024-12-28')
) AS v(instrument_key, symbol, option_type, strike_price, expiry_date)
ON CONFLICT DO NOTHING;

-- Create table for sample instruments first
CREATE TABLE IF NOT EXISTS test_data.sample_instruments (
    id SERIAL PRIMARY KEY,
    instrument_key VARCHAR(255) UNIQUE NOT NULL,
    symbol VARCHAR(100) NOT NULL,
    option_type VARCHAR(10),
    strike_price DECIMAL(12,4),
    expiry_date DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Now insert the test data
INSERT INTO test_data.sample_instruments (instrument_key, symbol, option_type, strike_price, expiry_date) 
VALUES 
    ('NSE@TESTSYM@CE@20000', 'TESTSYM', 'call', 20000, '2024-12-28'),
    ('NSE@TESTSYM@PE@20000', 'TESTSYM', 'put', 20000, '2024-12-28'),
    ('NSE@TESTSYM@CE@19500', 'TESTSYM', 'call', 19500, '2024-12-28'),
    ('NSE@TESTSYM@PE@20500', 'TESTSYM', 'put', 20500, '2024-12-28'),
    ('NSE@EQUITY1', 'EQUITY1', NULL, NULL, NULL),
    ('NSE@EQUITY2', 'EQUITY2', NULL, NULL, NULL)
ON CONFLICT (instrument_key) DO NOTHING;

-- Insert sample market data for Smart Money testing
INSERT INTO market_data (instrument_key, timestamp, open, high, low, close, volume)
SELECT 
    'NSE@TESTSYM',
    timestamp_val,
    20000 + (random() * 400 - 200), -- Random price around 20000
    20000 + (random() * 500 - 100), -- High
    20000 + (random() * 300 - 300), -- Low  
    20000 + (random() * 400 - 200), -- Close
    (50000 + random() * 100000)::BIGINT -- Random volume
FROM generate_series(
    NOW() - INTERVAL '7 days',
    NOW(),
    INTERVAL '5 minutes'
) AS timestamp_val;

-- Grant permissions to test user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO test_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA test_data TO test_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO test_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA test_data TO test_user;
GRANT USAGE ON SCHEMA test_data TO test_user;

-- Create test functions for validation
CREATE OR REPLACE FUNCTION test_data.validate_test_environment()
RETURNS BOOLEAN AS $$
BEGIN
    -- Check if required tables exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'signal_greeks') THEN
        RETURN FALSE;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'signal_indicators') THEN
        RETURN FALSE;
    END IF;
    
    -- Check if test data exists
    IF NOT EXISTS (SELECT 1 FROM test_data.sample_instruments LIMIT 1) THEN
        RETURN FALSE;
    END IF;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Test the validation function
SELECT test_data.validate_test_environment() as test_environment_ready;