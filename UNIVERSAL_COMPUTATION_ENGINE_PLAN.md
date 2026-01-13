# Universal Computation Engine Enhancement Plan

## Current State Analysis

The Signal Service already has:
1. **Technical Indicators**: Using pandas_ta with dynamic indicator support
2. **Greeks Calculation**: For options (Delta, Gamma, Theta, Vega, Rho)
3. **Moneyness Calculations**: For options classification
4. **Real-time Processing**: Redis streams consumption
5. **Batch Processing**: Bulk computation capabilities
6. **Custom Indicators**: Support for user-defined indicators
7. **Caching**: Indicator result caching
8. **Horizontal Scaling**: Worker affinity management

## Enhancement Requirements

### 1. Universal Asset Support
- **Current**: Primarily focused on options
- **Enhancement**: Support all asset types:
  - Equities (stocks)
  - Futures
  - Options
  - Indices
  - Commodities
  - Currencies

### 2. Dynamic Indicator Computation
- **Current**: Limited to predefined indicators
- **Enhancement**: 
  - Runtime indicator definition
  - Custom formula support
  - Multi-asset correlation indicators
  - Cross-timeframe indicators

### 3. Enhanced Moneyness Calculations
- **Current**: Options-only moneyness
- **Enhancement**:
  - Futures moneyness (time to expiry based)
  - Equity moneyness (relative to moving averages)
  - Multi-dimensional moneyness

### 4. Stateless Calculator
- **Current**: Some state management for caching
- **Enhancement**:
  - Pure computation functions
  - External state management
  - Distributed computation support

### 5. Universal Computation Endpoints
- **Current**: Separate endpoints for different calculations
- **Enhancement**:
  - Unified computation endpoint
  - Asset-agnostic calculations
  - Flexible response formats

## Implementation Plan

### Phase 1: Core Infrastructure
1. Create universal computation interface
2. Add asset type detection and routing
3. Implement computation registry pattern
4. Add dynamic computation pipeline

### Phase 2: Asset-Specific Enhancements
1. Extend Greeks to futures (DV01, basis risk)
2. Add equity-specific indicators
3. Implement cross-asset correlations
4. Add commodity-specific calculations

### Phase 3: API Enhancements
1. Create unified computation endpoint
2. Add computation templates
3. Implement computation chaining
4. Add result transformation pipeline

### Phase 4: Integration
1. Historical Data Service integration
2. Real-time computation triggers
3. Batch enrichment support
4. Performance optimization

## File Structure

```
signal_service/
├── app/
│   ├── api/
│   │   └── v2/
│   │       ├── universal.py          # New: Universal computation endpoint
│   │       └── templates.py          # New: Computation templates
│   ├── services/
│   │   ├── universal_calculator.py   # New: Main computation engine
│   │   ├── asset_calculators/       # New: Asset-specific calculators
│   │   │   ├── equity_calculator.py
│   │   │   ├── futures_calculator.py
│   │   │   ├── options_calculator.py
│   │   │   └── index_calculator.py
│   │   ├── computation_registry.py   # New: Dynamic computation registry
│   │   └── formula_engine.py        # New: Custom formula processor
│   └── schemas/
│       └── universal_schemas.py      # New: Universal computation schemas
```

## API Design

### Universal Computation Endpoint
```
POST /api/v2/signals/compute
{
    "asset_type": "equity|futures|options|index",
    "instrument_key": "NSE@RELIANCE@equity",
    "computations": [
        {
            "type": "indicator",
            "name": "sma",
            "params": {"period": 20}
        },
        {
            "type": "greeks",
            "params": {"model": "black-scholes"}
        },
        {
            "type": "moneyness",
            "params": {"reference": "spot"}
        },
        {
            "type": "custom",
            "formula": "(close - sma20) / sma20 * 100",
            "params": {"sma20": {"type": "sma", "period": 20}}
        }
    ],
    "timeframe": "5m",
    "mode": "realtime|historical|batch"
}
```

### Response Format
```json
{
    "instrument_key": "NSE@RELIANCE@equity",
    "asset_type": "equity",
    "timestamp": "2025-01-17T10:00:00Z",
    "computations": {
        "sma": {
            "value": 2450.50,
            "metadata": {"period": 20}
        },
        "greeks": {
            "delta": 0.65,
            "gamma": 0.02,
            "metadata": {"model": "black-scholes"}
        },
        "moneyness": {
            "level": "ATM",
            "ratio": 1.02,
            "metadata": {"reference": "spot"}
        },
        "custom": {
            "value": 2.5,
            "metadata": {"formula": "(close - sma20) / sma20 * 100"}
        }
    },
    "execution_time_ms": 15
}
```