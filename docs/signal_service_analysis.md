# Signal Service Analysis & Enhancement Plan

## Table of Contents
1. [Current State Analysis](#current-state-analysis)
2. [Requirements & Questions](#requirements--questions)
3. [Design Decisions](#design-decisions)
4. [Implementation Plan](#implementation-plan)
5. [Testing Strategy](#testing-strategy)
6. [Migration Plan](#migration-plan)
7. [Sprint Documentation](#sprint-documentation)

---

## 1. Current State Analysis

### Service Overview
The Signal Service is a sophisticated real-time market data processing engine that computes financial signals including Option Greeks, technical indicators, and custom functions. It operates on a streaming architecture, consuming tick data from Redis Streams and publishing computed results.

### Architecture Components

#### Core Processing Engine
- **SignalProcessor**: Main orchestrator consuming Redis streams
- **ConfigHandler**: Manages dynamic configurations
- **Multiple Computation Engines**: Greeks, Technical Indicators, External Functions

#### Greeks Calculation System
- **GreeksCalculationEngine**: Core mathematical calculations using py_vollib
- **GreeksCalculator**: Historical Greeks with TimescaleDB integration
- **RealTimeGreeksCalculator**: Live Greeks computation from tick data

#### Technical Indicators
- **PandasTAExecutor**: 50+ indicators via pandas_ta library
- **CustomIndicators**: Proprietary indicators (Anchored VWAP, Swing High/Low)
- **IndicatorLibrary**: Registry of available indicators

#### Data Management
- **HistoricalDataManager**: Multi-source data retrieval with fallback
- **TimeframeCacheManager**: Intelligent caching for different timeframes
- **HistoricalDataWriter**: Persistence to TimescaleDB

#### Advanced Features
- **ThresholdMonitor**: Real-time threshold monitoring with alerts
- **DynamicIndicatorClassifier**: ML-based indicator classification
- **BulkComputationEngine**: Batch processing for efficiency
- **AlertManager**: Multi-channel alert delivery

### Current Capabilities
1. **Real-time Processing**: Tick-by-tick computation
2. **Historical Analysis**: Backtesting support
3. **Multi-timeframe**: 1m to 1month intervals
4. **Subscription Management**: Quota and feature access control
5. **Performance Optimization**: Caching, batching, parallel processing

### Identified Gaps
1. **Moneyness Integration**: No current integration with instrument_service
2. **Historical API**: Limited endpoints for historical data retrieval
3. **Timeframe Flexibility**: Fixed intervals, no custom timeframes
4. **Greeks Distribution**: No support for moneyness-based Greeks (ATM IV, OTM5delta)
5. **Data Standardization**: Inconsistent response formats

---

## 2. Requirements & Questions

### Business Requirements

#### A. Real-time Value Sharing
**Current State**: Publishes to Redis streams/lists
**Required Enhancement**: 
- REST API endpoints for real-time data retrieval
- WebSocket support for streaming updates
- Standardized response format

**Questions**:
1. What's the expected latency requirement for real-time data? (<100ms?)
2. Should we support WebSocket subscriptions for continuous updates?
3. What's the expected concurrent connection limit?

#### B. Historical Value Retrieval
**Current State**: Limited historical endpoints
**Required Enhancement**:
- Comprehensive historical API
- Point-in-time queries
- Aggregated data retrieval

**Questions**:
1. How far back should historical data be available? (1 year? 5 years?)
2. What's the expected query response time for historical data?
3. Should we support bulk historical exports?

#### C. Flexible Timeframe Support
**Current State**: Fixed intervals (1m, 5m, 15m, etc.)
**Required Enhancement**:
- Custom timeframe support (e.g., 7m, 13m)
- Dynamic aggregation
- Timeframe conversion

**Questions**:
1. What's the maximum custom timeframe allowed? (1 day?)
2. How should we handle non-standard timeframes in aggregation?
3. Should custom timeframes be cached?

#### D. Moneyness Integration
**Current State**: No integration with instrument_service
**Required Enhancement**:
- Integration with instrument_service moneyness engine
- Moneyness-based Greeks (ATM IV, OTM5delta)
- Strike selection by moneyness

**Questions**:
1. Should moneyness be calculated real-time or use instrument_service?
2. What moneyness levels need support? (ATM, OTM5, OTM10, etc.?)
3. How often should moneyness mappings be refreshed?

### Technical Requirements

1. **Performance**:
   - Real-time computation: <50ms
   - Historical queries: <200ms
   - Batch processing: 1000+ instruments/minute

2. **Scalability**:
   - Support 10,000+ concurrent subscriptions
   - Handle 1M+ ticks/second
   - Horizontal scaling capability

3. **Reliability**:
   - 99.9% uptime
   - Circuit breakers for external dependencies
   - Graceful degradation

4. **Data Quality**:
   - Validation of all inputs
   - Outlier detection
   - Data consistency checks

---

## 3. Design Decisions

### Architecture Enhancements

#### 1. API Layer Enhancement
```python
# New API structure
/api/v2/signals/
├── realtime/
│   ├── greeks/{instrument_key}
│   ├── indicators/{instrument_key}/{indicator}
│   └── moneyness/{underlying}/greeks/{moneyness_level}
├── historical/
│   ├── greeks/{instrument_key}
│   ├── indicators/{instrument_key}/{indicator}
│   └── moneyness/{underlying}/greeks/{moneyness_level}
├── timeframes/
│   ├── standard/{timeframe}
│   └── custom/{minutes}
└── subscriptions/
    ├── websocket
    └── webhooks
```

#### 2. Moneyness Integration Architecture
```python
class MoneynessAwareGreeksCalculator:
    """Enhanced Greeks calculator with moneyness support"""
    
    def __init__(self):
        self.instrument_client = InstrumentServiceClient()
        self.greeks_engine = GreeksCalculationEngine()
        
    async def calculate_moneyness_greeks(
        self,
        underlying: str,
        moneyness_level: str,  # "ATM", "OTM5delta", etc.
        timeframe: str
    ) -> Dict[str, Any]:
        # Get strikes by moneyness
        strikes = await self.instrument_client.get_strikes_by_moneyness(
            underlying, moneyness_level
        )
        
        # Calculate Greeks for identified strikes
        results = await self.greeks_engine.calculate_batch(strikes)
        
        # Aggregate by moneyness level
        return self.aggregate_by_moneyness(results, moneyness_level)
```

#### 3. Timeframe Management System
```python
class FlexibleTimeframeManager:
    """Support for custom timeframes"""
    
    def __init__(self):
        self.standard_timeframes = {
            "1m": 1, "5m": 5, "15m": 15, "30m": 30,
            "1h": 60, "4h": 240, "1d": 1440
        }
        self.cache = TimeframeCacheManager()
        
    async def get_data(
        self,
        instrument_key: str,
        timeframe: str,
        data_type: str  # "greeks", "indicators", etc.
    ) -> List[Dict]:
        if timeframe in self.standard_timeframes:
            return await self.cache.get_cached_data(
                instrument_key, timeframe, data_type
            )
        else:
            # Custom timeframe - aggregate from 1m data
            minutes = self.parse_custom_timeframe(timeframe)
            return await self.aggregate_custom_timeframe(
                instrument_key, minutes, data_type
            )
```

#### 4. Enhanced Data Pipeline
```
Tick Data → SignalProcessor → Computation Engines → Results
                ↓                      ↓
        Moneyness Mapper      Timeframe Aggregator
                ↓                      ↓
        Moneyness Results      Multi-Timeframe Cache
                ↓                      ↓
            Redis/API              Historical DB
```

### Database Schema Enhancements

#### 1. Moneyness Greeks Table
```sql
CREATE TABLE signal_moneyness_greeks (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    underlying_symbol VARCHAR(50) NOT NULL,
    moneyness_level VARCHAR(20) NOT NULL, -- 'ATM', 'OTM5delta', etc.
    timeframe VARCHAR(10) NOT NULL,
    
    -- Aggregated Greeks
    avg_iv DECIMAL(10,6),
    total_delta DECIMAL(12,6),
    total_gamma DECIMAL(12,6),
    total_theta DECIMAL(12,6),
    total_vega DECIMAL(12,6),
    
    -- Strike details
    strikes_included INTEGER,
    primary_strike INTEGER,
    
    -- Metadata
    computation_time_ms INTEGER,
    data_quality_score DECIMAL(3,2),
    
    INDEX idx_moneyness_lookup (underlying_symbol, moneyness_level, timestamp),
    INDEX idx_timeframe (timeframe, timestamp)
);

-- Convert to TimescaleDB hypertable
SELECT create_hypertable('signal_moneyness_greeks', 'timestamp');
```

#### 2. Custom Timeframe Cache
```sql
CREATE TABLE signal_custom_timeframes (
    id BIGSERIAL PRIMARY KEY,
    instrument_key VARCHAR(100) NOT NULL,
    timeframe_minutes INTEGER NOT NULL,
    data_type VARCHAR(50) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    
    -- Aggregated data
    open_value JSONB,
    high_value JSONB,
    low_value JSONB,
    close_value JSONB,
    
    -- Volume weighted values
    vwap_value JSONB,
    
    -- Metadata
    data_points_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(instrument_key, timeframe_minutes, data_type, timestamp)
);
```

### API Response Standardization

#### Standard Response Format
```json
{
    "status": "success",
    "data": {
        "instrument_key": "NSE@NIFTY@OPTION@...",
        "timestamp": "2024-01-07T10:30:00Z",
        "timeframe": "5m",
        "values": {
            "greeks": {
                "delta": 0.5234,
                "gamma": 0.0125,
                "theta": -0.0234,
                "vega": 0.1234,
                "iv": 0.2145
            },
            "indicators": {
                "rsi": 65.23,
                "macd": {
                    "value": 12.34,
                    "signal": 11.23,
                    "histogram": 1.11
                }
            }
        },
        "metadata": {
            "computation_time_ms": 23,
            "data_quality": 0.98,
            "source": "realtime"
        }
    },
    "error": null
}
```

#### Moneyness Response Format
```json
{
    "status": "success",
    "data": {
        "underlying": "NIFTY",
        "moneyness_level": "ATM",
        "timestamp": "2024-01-07T10:30:00Z",
        "timeframe": "5m",
        "values": {
            "iv": 0.2145,
            "aggregated_greeks": {
                "net_delta": 0.0234,
                "net_gamma": 0.0543,
                "net_theta": -125.34,
                "net_vega": 234.56
            },
            "strike_details": {
                "primary_strike": 21500,
                "strikes_included": [21400, 21450, 21500, 21550, 21600],
                "weights": [0.1, 0.2, 0.4, 0.2, 0.1]
            }
        }
    }
}
```

---

## 4. Implementation Plan

### Phase 1: Foundation (Week 1)

#### 1.1 Service Refactoring
- [ ] Consolidate duplicate Greeks calculators
- [ ] Standardize configuration management
- [ ] Implement base classes for computation engines
- [ ] Create unified error handling framework

#### 1.2 Instrument Service Integration
- [ ] Create InstrumentServiceClient in signal_service
- [ ] Implement moneyness mapping cache
- [ ] Add moneyness-aware Greeks calculator
- [ ] Create strike selection by moneyness

#### 1.3 Database Schema Updates
- [ ] Create moneyness Greeks tables
- [ ] Create custom timeframe tables
- [ ] Update existing schemas for new fields
- [ ] Create migration scripts

### Phase 2: Core Features (Week 2)

#### 2.1 Real-time API Implementation
- [ ] Create v2 API endpoints structure
- [ ] Implement real-time Greeks endpoints
- [ ] Implement real-time indicators endpoints
- [ ] Add moneyness-based endpoints

#### 2.2 Historical API Implementation
- [ ] Create historical data retrieval endpoints
- [ ] Implement time-range queries
- [ ] Add aggregation options
- [ ] Implement data export functionality

#### 2.3 Timeframe Flexibility
- [ ] Implement custom timeframe parser
- [ ] Create dynamic aggregation engine
- [ ] Update caching for custom timeframes
- [ ] Add timeframe validation

### Phase 3: Advanced Features (Week 3)

#### 3.1 WebSocket Implementation
- [ ] Create WebSocket endpoint
- [ ] Implement subscription manager
- [ ] Add real-time data streaming
- [ ] Implement connection management

#### 3.2 Performance Optimization
- [ ] Implement intelligent caching
- [ ] Add batch processing optimization
- [ ] Create data compression
- [ ] Implement query optimization

#### 3.3 Monitoring & Observability
- [ ] Add detailed metrics
- [ ] Implement performance tracking
- [ ] Create alerting rules
- [ ] Add distributed tracing

### Phase 4: Testing & Documentation (Week 4)

#### 4.1 Testing Implementation
- [ ] Create unit tests for all components
- [ ] Implement integration tests
- [ ] Add performance benchmarks
- [ ] Create load testing scenarios

#### 4.2 Documentation
- [ ] Create API documentation
- [ ] Write integration guides
- [ ] Document moneyness features
- [ ] Create troubleshooting guide

---

## 5. Testing Strategy

### Unit Testing
```python
# Test moneyness Greeks calculation
async def test_moneyness_greeks_calculation():
    calculator = MoneynessAwareGreeksCalculator()
    
    result = await calculator.calculate_moneyness_greeks(
        underlying="NIFTY",
        moneyness_level="ATM",
        timeframe="5m"
    )
    
    assert "iv" in result["values"]
    assert result["values"]["iv"] > 0
    assert len(result["strike_details"]["strikes_included"]) > 0
```

### Integration Testing
```python
# Test end-to-end data flow
async def test_signal_flow_with_moneyness():
    # Send tick data
    await send_option_tick("NSE@NIFTY@OPTION@21500@CALL")
    
    # Wait for processing
    await asyncio.sleep(0.5)
    
    # Check moneyness Greeks
    response = await get_moneyness_greeks("NIFTY", "ATM", "1m")
    assert response["status"] == "success"
    assert response["data"]["values"]["iv"] > 0
```

### Performance Testing
```python
# Benchmark moneyness calculations
async def benchmark_moneyness_performance():
    start = time.time()
    
    tasks = []
    for _ in range(100):
        task = calculate_moneyness_greeks("NIFTY", "ATM", "5m")
        tasks.append(task)
    
    await asyncio.gather(*tasks)
    
    elapsed = time.time() - start
    assert elapsed < 5.0  # 100 calculations in < 5 seconds
```

### Load Testing
```yaml
# K6 load test configuration
import http from 'k6/http';
import { check } from 'k6';

export let options = {
  stages: [
    { duration: '2m', target: 100 },
    { duration: '5m', target: 500 },
    { duration: '2m', target: 0 },
  ],
};

export default function() {
  let response = http.get('http://signal-service/api/v2/realtime/moneyness/NIFTY/greeks/ATM');
  check(response, {
    'status is 200': (r) => r.status === 200,
    'response time < 200ms': (r) => r.timings.duration < 200,
  });
}
```

---

## 6. Migration Plan

### Pre-Migration Checklist
- [ ] Backup existing data
- [ ] Document current API consumers
- [ ] Create rollback plan
- [ ] Prepare monitoring dashboards

### Migration Steps

#### Step 1: Deploy Enhanced Service (Blue-Green)
1. Deploy new version alongside existing
2. Route 10% traffic to new version
3. Monitor for issues
4. Gradually increase traffic

#### Step 2: Data Migration
1. Create new tables without dropping old
2. Start dual-writing to both schemas
3. Backfill historical data
4. Verify data integrity

#### Step 3: API Migration
1. Deploy v2 endpoints alongside v1
2. Update documentation
3. Notify API consumers
4. Provide migration guide

#### Step 4: Cleanup
1. Monitor v1 API usage
2. Deprecate v1 after 30 days
3. Remove old code
4. Archive old data

### Rollback Plan
1. **Immediate**: Route traffic back to v1
2. **Data**: Stop dual-writing, revert to old schema
3. **Code**: Deploy previous version
4. **Communication**: Notify stakeholders

---

## 7. Sprint Documentation

### Sprint 1: Foundation & Integration
**Goal**: Establish moneyness integration and refactor core components

**Deliverables**:
1. Instrument service integration
2. Moneyness-aware Greeks calculator
3. Database schema updates
4. Basic moneyness endpoints

**Success Metrics**:
- Moneyness Greeks calculation < 100ms
- All existing tests pass
- No regression in performance

### Sprint 2: API Enhancement
**Goal**: Implement comprehensive real-time and historical APIs

**Deliverables**:
1. V2 API endpoints
2. Historical data retrieval
3. Custom timeframe support
4. Response standardization

**Success Metrics**:
- API response time < 200ms
- Support for 20+ custom timeframes
- 100% backward compatibility

### Sprint 3: Advanced Features
**Goal**: Add WebSocket support and performance optimizations

**Deliverables**:
1. WebSocket streaming
2. Advanced caching
3. Batch processing optimization
4. Monitoring enhancements

**Success Metrics**:
- WebSocket latency < 50ms
- 10,000+ concurrent connections
- 90% cache hit rate

### Sprint 4: Production Readiness
**Goal**: Complete testing, documentation, and deployment

**Deliverables**:
1. Comprehensive test suite
2. API documentation
3. Migration execution
4. Performance validation

**Success Metrics**:
- 95% test coverage
- All benchmarks met
- Zero downtime migration
- Complete documentation

---

## Appendices

### A. Configuration Examples
```yaml
# Enhanced signal service configuration
signal_service:
  moneyness:
    enabled: true
    refresh_interval: 300  # 5 minutes
    cache_ttl: 600  # 10 minutes
    levels:
      - ATM
      - OTM5delta
      - OTM10delta
      - ITM5delta
      
  timeframes:
    standard:
      - 1m
      - 5m
      - 15m
      - 30m
      - 1h
    custom:
      enabled: true
      max_minutes: 1440  # 1 day
      cache_custom: true
      
  performance:
    batch_size: 100
    parallel_workers: 10
    cache_size_mb: 1024
    compression: true
```

### B. Example API Calls
```bash
# Get real-time ATM IV for NIFTY
curl http://signal-service/api/v2/realtime/moneyness/NIFTY/greeks/ATM?timeframe=5m

# Get historical Greeks for specific option
curl http://signal-service/api/v2/historical/greeks/NSE@NIFTY@OPTION@21500@CALL?from=2024-01-01&to=2024-01-07&timeframe=15m

# Subscribe to WebSocket updates
wscat -c ws://signal-service/api/v2/subscriptions/websocket \
  -x '{"action":"subscribe","instruments":["NIFTY"],"moneyness":["ATM","OTM5delta"],"timeframe":"1m"}'
```

### C. Performance Benchmarks
| Operation | Current | Target | Achieved |
|-----------|---------|---------|----------|
| Real-time Greeks | 150ms | 50ms | TBD |
| Historical Query | 500ms | 200ms | TBD |
| Moneyness Calculation | N/A | 100ms | TBD |
| WebSocket Latency | N/A | 50ms | TBD |
| Cache Hit Rate | 70% | 90% | TBD |

---

## Document Control
- **Version**: 1.0
- **Date**: 2024-01-07
- **Author**: AI Assistant
- **Status**: Draft for Review
- **Next Review**: After Sprint 1 completion