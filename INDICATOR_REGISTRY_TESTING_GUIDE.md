# Signal Service Indicator Registry Testing Guide

This guide shows how to test the 277 registered indicators and third-party libraries **without requiring the ticker service**.

## Overview

The Signal Service has a comprehensive indicator registry system that provides unified access to:
- **243 pandas_ta indicators** (moving averages, oscillators, volume indicators, etc.)
- **34 custom indicators** (smart money concepts, patterns, clustering, etc.)
- **Third-party libraries**: findpeaks, trendln, scikit-learn, scipy

## API Endpoints for Registry Testing

### 1. Available Pandas_TA Indicators
**Endpoint:** `GET /api/v2/indicators/available-indicators`

Shows all pandas_ta indicators that are accessible via the API.

```bash
curl -X GET "http://localhost:8003/api/v2/indicators/available-indicators"
```

**Sample Response:**
```json
{
  "success": true,
  "message": "Found 243 available indicators",
  "data": {
    "sma": {
      "parameters": {"length": {"default": 10, "type": "int"}},
      "description": "Simple Moving Average"
    },
    "ema": {
      "parameters": {"length": {"default": 10, "type": "int"}},
      "description": "Exponential Moving Average"
    }
    // ... 241 more indicators
  }
}
```

### 2. Universal Computations Registry
**Endpoint:** `GET /api/v2/universal/computations`

Shows all registered computations across all asset types and libraries.

```bash
curl -X GET "http://localhost:8003/api/v2/universal/computations"
```

**Sample Response:**
```json
{
  "total": 277,
  "computations": [
    {
      "name": "sma",
      "description": "Simple Moving Average",
      "asset_types": ["equity", "futures", "options"],
      "parameters": {
        "period": {"type": "int", "default": 20, "min": 1, "max": 500}
      },
      "tags": ["technical_analysis", "trend"]
    }
    // ... 276 more computations
  ]
}
```

### 3. Registry Health Status
**Endpoint:** `GET /api/v2/universal/health`

Shows the overall health and capabilities of the computation engine.

```bash
curl -X GET "http://localhost:8003/api/v2/universal/health"
```

**Sample Response:**
```json
{
  "status": "healthy",
  "service": "universal_computation_engine",
  "capabilities": {
    "total_computations": 277,
    "asset_coverage": {
      "equity": 277,
      "futures": 250,
      "options": 180
    },
    "supported_assets": ["equity", "futures", "options", "index", "commodity"],
    "computation_types": ["indicator", "greeks", "moneyness", "risk_metrics"]
  }
}
```

### 4. Computation Validation (No Execution)
**Endpoint:** `POST /api/v2/universal/validate`

Validates computations without executing them - perfect for testing registry accessibility.

```bash
curl -X POST "http://localhost:8003/api/v2/universal/validate" \
  -H "Content-Type: application/json" \
  -d '{
    "asset_type": "equity",
    "instrument_key": "TEST@SYMBOL@equity",
    "computations": [
      {"type": "indicator", "params": {"indicator": "sma", "period": 20}},
      {"type": "indicator", "params": {"indicator": "rsi", "period": 14}},
      {"type": "indicator", "params": {"indicator": "macd"}},
      {"type": "indicator", "params": {"indicator": "bbands", "length": 20}}
    ]
  }'
```

**Sample Response:**
```json
{
  "valid": true,
  "errors": null,
  "warnings": null,
  "computations_validated": 4
}
```

### 5. Example Computations by Asset Type
**Endpoint:** `GET /api/v2/universal/examples/{asset_type}`

Shows example computation requests for different asset types.

```bash
curl -X GET "http://localhost:8003/api/v2/universal/examples/equity"
```

### 6. Indicator Cache Statistics
**Endpoint:** `GET /api/v2/indicators/cache/stats`

Shows indicator caching system status and performance.

```bash
curl -X GET "http://localhost:8003/api/v2/indicators/cache/stats"
```

### 7. Worker Affinity Status  
**Endpoint:** `GET /api/v2/indicators/worker-affinity/status`

Shows worker distribution and load balancing status.

```bash
curl -X GET "http://localhost:8003/api/v2/indicators/worker-affinity/status"
```

### 8. Specific Computation Details
**Endpoint:** `GET /api/v2/universal/computations/{computation_name}`

Get detailed information about a specific computation.

```bash
curl -X GET "http://localhost:8003/api/v2/universal/computations/sma"
```

## Testing Third-Party Libraries

### Test All Library Accessibility
You can verify that all third-party libraries are properly accessible through the computation registry:

```bash
# Test pandas_ta indicators
curl -X POST "http://localhost:8003/api/v2/universal/validate" \
  -H "Content-Type: application/json" \
  -d '{
    "asset_type": "equity", 
    "instrument_key": "TEST@SYMBOL@equity",
    "computations": [
      {"type": "indicator", "params": {"indicator": "sma", "period": 20}},
      {"type": "indicator", "params": {"indicator": "rsi", "period": 14}}, 
      {"type": "indicator", "params": {"indicator": "macd"}},
      {"type": "indicator", "params": {"indicator": "stoch"}},
      {"type": "indicator", "params": {"indicator": "adx"}},
      {"type": "indicator", "params": {"indicator": "cci"}},
      {"type": "indicator", "params": {"indicator": "willr"}},
      {"type": "indicator", "params": {"indicator": "roc"}}
    ]
  }'

# Test custom indicators (smart money, patterns, etc.)
curl -X POST "http://localhost:8003/api/v2/universal/validate" \
  -H "Content-Type: application/json" \
  -d '{
    "asset_type": "equity",
    "instrument_key": "TEST@SYMBOL@equity", 
    "computations": [
      {"type": "break_of_structure", "params": {"swing_length": 10}},
      {"type": "order_block_detection", "params": {"lookback": 20}},
      {"type": "fibonacci_retracements", "params": {"swing_high": 110, "swing_low": 100}},
      {"type": "trendline_detection", "params": {"min_touches": 3}},
      {"type": "peak_valley_analysis", "params": {"prominence": 0.1}}
    ]
  }'
```

## Mock Data Testing

For testing computations without external data dependencies, you can create test scripts that use mock OHLCV data:

```python
import pandas as pd
import numpy as np
import pandas_ta as ta

# Create mock OHLCV data
dates = pd.date_range(start='2023-01-01', periods=100, freq='D')
mock_data = pd.DataFrame({
    'open': np.random.uniform(100, 105, 100),
    'high': np.random.uniform(105, 110, 100), 
    'low': np.random.uniform(95, 100, 100),
    'close': np.random.uniform(100, 105, 100),
    'volume': np.random.randint(1000, 10000, 100)
}, index=dates)

# Test pandas_ta indicators directly
sma_20 = ta.sma(mock_data['close'], length=20)
rsi = ta.rsi(mock_data['close'], length=14)
macd_data = ta.macd(mock_data['close'])

print(f"SMA(20) last value: {sma_20.iloc[-1]}")
print(f"RSI(14) last value: {rsi.iloc[-1]}")
print(f"MACD columns: {list(macd_data.columns)}")
```

## Quick Test Scripts

### Run Registry Endpoint Tests
```bash
# Make the test script executable
chmod +x test_registry_endpoints.py

# Run the endpoint tests
python test_registry_endpoints.py
```

### Run Comprehensive Registry Tests
```bash
# Run full registry validation
python test_indicator_registry_status.py --output registry_test_report.json

# View detailed results
python test_indicator_registry_status.py --verbose
```

## Expected Results

If the indicator registry is working properly, you should see:

1. **243 pandas_ta indicators** available via `/available-indicators`
2. **277 total computations** registered via `/universal/computations`
3. **Healthy status** from `/universal/health`
4. **Successful validation** of indicator requests via `/validate`
5. **No errors** when accessing third-party libraries

## Key Benefits

This testing approach allows you to:

✅ **Verify all 277 indicators are registered** without ticker service  
✅ **Test third-party library accessibility** (pandas_ta, findpeaks, trendln, etc.)  
✅ **Validate computation requests** without execution  
✅ **Check registry health and performance**  
✅ **Test with mock data** for development and testing  
✅ **Monitor cache performance and worker distribution**

## Troubleshooting

If you encounter issues:

1. **Service not running**: Check if the Signal Service is started on port 8003
2. **Registry not initialized**: Check the service logs for indicator registration errors  
3. **Missing libraries**: Verify third-party libraries are installed in the environment
4. **API errors**: Check the service logs for detailed error messages
5. **Validation failures**: Use the `/validate` endpoint to check computation definitions

## File Locations

- **Indicator Registry**: `/app/services/indicator_registry.py`
- **Registry Initialization**: `/app/services/register_indicators.py` 
- **Available Indicators API**: `/app/api/v2/indicators.py`
- **Universal Computations API**: `/app/api/v2/universal.py`
- **Test Scripts**: `test_registry_endpoints.py`, `test_indicator_registry_status.py`