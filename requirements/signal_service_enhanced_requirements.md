# Signal Service Enhanced Requirements

## Executive Summary
This document outlines the enhanced requirements for the Signal Service to support real-time and historical data sharing for technical indicators, Greeks, and computed functions with flexible timeframe support and moneyness integration.

---

## 1. Functional Requirements

### FR1: Real-time Data Sharing
**ID**: FR1  
**Priority**: High  
**Description**: The service must provide real-time access to computed signals including Greeks, technical indicators, and custom functions.

**Acceptance Criteria**:
1. REST API endpoints return data within 100ms
2. WebSocket connections provide updates within 50ms
3. Support for 10,000+ concurrent connections
4. Standardized JSON response format

**API Endpoints**:
```
GET /api/v2/realtime/greeks/{instrument_key}
GET /api/v2/realtime/indicators/{instrument_key}/{indicator}
GET /api/v2/realtime/moneyness/{underlying}/greeks/{moneyness_level}
WS  /api/v2/subscriptions/websocket
```

### FR2: Historical Data Retrieval
**ID**: FR2  
**Priority**: High  
**Description**: The service must provide historical data for all computed signals with flexible time range queries.

**Acceptance Criteria**:
1. Support date range queries (from/to)
2. Response time < 200ms for queries up to 1 month
3. Support for pagination for large datasets
4. CSV export capability for data analysis

**API Endpoints**:
```
GET /api/v2/historical/greeks/{instrument_key}?from={date}&to={date}
GET /api/v2/historical/indicators/{instrument_key}/{indicator}?from={date}&to={date}
GET /api/v2/historical/moneyness/{underlying}/greeks/{moneyness_level}?from={date}&to={date}
POST /api/v2/historical/export
```

### FR3: Flexible Timeframe Support
**ID**: FR3  
**Priority**: High  
**Description**: Support both standard and custom timeframes for all computations.

**Acceptance Criteria**:
1. Standard timeframes: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M
2. Custom timeframes: Any minute interval up to 1440 (1 day)
3. Dynamic aggregation from base 1-minute data
4. Consistent OHLC values across timeframes

**Examples**:
```
GET /api/v2/realtime/greeks/{instrument_key}?timeframe=5m
GET /api/v2/realtime/greeks/{instrument_key}?timeframe=7m  (custom)
GET /api/v2/realtime/greeks/{instrument_key}?timeframe=13m (custom)
```

### FR4: Moneyness Integration
**ID**: FR4  
**Priority**: High  
**Description**: Integration with instrument_service to provide moneyness-based Greeks and analytics.

**Acceptance Criteria**:
1. Support moneyness levels: ATM, ITM5delta, OTM5delta, OTM10delta, etc.
2. Real-time moneyness to strike mapping
3. Aggregated Greeks by moneyness level
4. ATM IV calculation for any timeframe

**API Examples**:
```
GET /api/v2/realtime/moneyness/NIFTY/greeks/ATM?timeframe=5m
Response: {
  "underlying": "NIFTY",
  "moneyness_level": "ATM",
  "timeframe": "5m",
  "values": {
    "iv": 0.2145,
    "aggregated_greeks": {...}
  }
}
```

### FR5: Greeks Calculation Enhancement
**ID**: FR5  
**Priority**: Medium  
**Description**: Enhanced Greeks calculation with additional metrics.

**New Metrics**:
1. Implied Volatility (IV) for all options
2. IV Rank and IV Percentile
3. Vomma (Volga) - volatility of vega
4. Vanna - sensitivity of delta to volatility
5. Charm - delta decay
6. Color - gamma decay

### FR6: Technical Indicators Library
**ID**: FR6  
**Priority**: Medium  
**Description**: Comprehensive technical indicator support with 50+ indicators.

**Categories**:
1. **Momentum**: RSI, MACD, Stochastic, ROC, Williams %R
2. **Trend**: SMA, EMA, TEMA, KAMA, Ichimoku
3. **Volatility**: ATR, Bollinger Bands, Keltner Channels, Donchian
4. **Volume**: OBV, CMF, MFI, VWAP, Volume Profile
5. **Custom**: Anchored VWAP, Swing High/Low, Market Profile

### FR7: Computed Functions
**ID**: FR7  
**Priority**: Medium  
**Description**: Support for custom computed functions with sandboxed execution.

**Features**:
1. Python function execution with timeout limits
2. Access to market data within functions
3. Function versioning and management
4. Performance metrics per function

### FR8: Data Quality & Validation
**ID**: FR8  
**Priority**: High  
**Description**: Ensure data quality and consistency across all computations.

**Requirements**:
1. Input validation for all data points
2. Outlier detection and handling
3. Data quality scoring (0-1)
4. Missing data interpolation options
5. Computation confidence levels

---

## 2. Non-Functional Requirements

### NFR1: Performance
**ID**: NFR1  
**Priority**: Critical

**Metrics**:
1. Real-time API latency: < 100ms (p99)
2. Historical API latency: < 200ms (p99)
3. WebSocket latency: < 50ms
4. Throughput: 100,000 computations/second
5. Concurrent connections: 10,000+

### NFR2: Scalability
**ID**: NFR2  
**Priority**: High

**Requirements**:
1. Horizontal scaling support
2. Auto-scaling based on load
3. Distributed computation capability
4. Sharded data storage
5. Load balancing across instances

### NFR3: Reliability
**ID**: NFR3  
**Priority**: Critical

**Requirements**:
1. Uptime: 99.9% SLA
2. Circuit breakers for external dependencies
3. Graceful degradation
4. Automatic failover
5. Data consistency guarantees

### NFR4: Security
**ID**: NFR4  
**Priority**: High

**Requirements**:
1. API authentication via JWT
2. Rate limiting per user/API key
3. Input sanitization
4. Encrypted data transmission
5. Audit logging for all operations

### NFR5: Monitoring & Observability
**ID**: NFR5  
**Priority**: High

**Requirements**:
1. Prometheus metrics for all operations
2. Distributed tracing (OpenTelemetry)
3. Real-time dashboards (Grafana)
4. Alert rules for anomalies
5. Performance profiling

---

## 3. Technical Requirements

### TR1: Architecture
**ID**: TR1  
**Priority**: High

**Components**:
1. **API Gateway**: Kong/Nginx for routing
2. **Compute Cluster**: Kubernetes pods for scaling
3. **Cache Layer**: Redis cluster for performance
4. **Time-series DB**: TimescaleDB for historical data
5. **Message Queue**: Redis Streams for real-time data

### TR2: Data Storage
**ID**: TR2  
**Priority**: High

**Requirements**:
1. TimescaleDB for time-series data
2. Redis for caching and real-time data
3. Data retention: 5 years for tick data, indefinite for aggregated
4. Compression for historical data
5. Partitioning by time and instrument

### TR3: Integration Requirements
**ID**: TR3  
**Priority**: High

**Services**:
1. **Instrument Service**: Moneyness calculations and strike mapping
2. **Ticker Service**: Real-time market data
3. **Subscription Service**: User quotas and access control
4. **User Service**: Authentication and authorization

### TR4: Development Standards
**ID**: TR4  
**Priority**: Medium

**Standards**:
1. Python 3.11+ with type hints
2. FastAPI for REST APIs
3. Async/await for all I/O operations
4. Pydantic for data validation
5. pytest for testing (>90% coverage)

---

## 4. API Specifications

### 4.1 Real-time Greeks API
```yaml
endpoint: GET /api/v2/realtime/greeks/{instrument_key}
parameters:
  - name: instrument_key
    type: string
    required: true
    example: "NSE@NIFTY@OPTION@21500@CALL"
  - name: timeframe
    type: string
    required: false
    default: "1m"
    example: "5m"
response:
  200:
    schema:
      type: object
      properties:
        status: string
        data:
          type: object
          properties:
            instrument_key: string
            timestamp: string (ISO 8601)
            timeframe: string
            values:
              type: object
              properties:
                greeks:
                  type: object
                  properties:
                    delta: number
                    gamma: number
                    theta: number
                    vega: number
                    rho: number
                    iv: number
```

### 4.2 Moneyness Greeks API
```yaml
endpoint: GET /api/v2/realtime/moneyness/{underlying}/greeks/{moneyness_level}
parameters:
  - name: underlying
    type: string
    required: true
    example: "NIFTY"
  - name: moneyness_level
    type: string
    required: true
    enum: ["ATM", "ITM5delta", "OTM5delta", "OTM10delta"]
  - name: timeframe
    type: string
    required: false
    default: "1m"
response:
  200:
    schema:
      type: object
      properties:
        status: string
        data:
          type: object
          properties:
            underlying: string
            moneyness_level: string
            timestamp: string
            timeframe: string
            values:
              type: object
              properties:
                iv: number
                aggregated_greeks:
                  type: object
                strike_details:
                  type: object
```

### 4.3 WebSocket Subscription
```yaml
endpoint: WS /api/v2/subscriptions/websocket
message_format:
  subscribe:
    action: "subscribe"
    instruments: array[string]
    moneyness_levels: array[string]
    indicators: array[string]
    timeframe: string
  unsubscribe:
    action: "unsubscribe"
    subscription_id: string
  data:
    type: "data"
    subscription_id: string
    timestamp: string
    updates: array[object]
```

---

## 5. Data Models

### 5.1 Greeks Data Model
```python
class GreeksData(BaseModel):
    instrument_key: str
    timestamp: datetime
    timeframe: str
    
    # Standard Greeks
    delta: Optional[float]
    gamma: Optional[float]
    theta: Optional[float]
    vega: Optional[float]
    rho: Optional[float]
    
    # Extended Greeks
    iv: Optional[float]
    vanna: Optional[float]
    charm: Optional[float]
    vomma: Optional[float]
    color: Optional[float]
    
    # Metadata
    underlying_price: float
    strike_price: float
    time_to_expiry: float
    computation_time_ms: int
    data_quality_score: float
```

### 5.2 Moneyness Greeks Model
```python
class MoneynessGreeks(BaseModel):
    underlying: str
    moneyness_level: str
    timestamp: datetime
    timeframe: str
    
    # Aggregated values
    iv: float
    net_delta: float
    net_gamma: float
    net_theta: float
    net_vega: float
    
    # Strike information
    primary_strike: int
    strikes_included: List[int]
    strike_weights: List[float]
    
    # Metadata
    total_volume: int
    total_oi: int
    computation_method: str
```

---

## 6. Implementation Priorities

### Phase 1 (Week 1) - Foundation
1. Instrument service integration
2. Moneyness mapping implementation
3. Database schema updates
4. Basic API structure

### Phase 2 (Week 2) - Core Features
1. Real-time APIs
2. Historical APIs
3. Timeframe flexibility
4. Greeks enhancements

### Phase 3 (Week 3) - Advanced Features
1. WebSocket implementation
2. Custom functions
3. Performance optimization
4. Caching strategies

### Phase 4 (Week 4) - Production Ready
1. Testing suite
2. Documentation
3. Migration execution
4. Performance validation

---

## 7. Success Metrics

### Performance KPIs
1. API response time p99 < 200ms
2. WebSocket latency p99 < 50ms
3. System uptime > 99.9%
4. Cache hit rate > 90%
5. Zero data loss

### Business KPIs
1. Support 10,000+ concurrent users
2. Process 1M+ ticks/second
3. Compute 100K+ Greeks/second
4. Store 5+ years of historical data
5. Enable real-time strategy execution

---

## 8. Risk Mitigation

### Technical Risks
1. **Performance degradation**: Implement caching, optimize queries
2. **Data inconsistency**: Add validation, implement transactions
3. **Service dependencies**: Circuit breakers, fallback mechanisms
4. **Scalability limits**: Horizontal scaling, load distribution

### Business Risks
1. **Data accuracy**: Multiple validation layers
2. **Latency spikes**: Performance monitoring, auto-scaling
3. **Integration failures**: Retry mechanisms, graceful degradation
4. **Cost overruns**: Resource optimization, usage monitoring

---

## Document Control
- **Version**: 1.0
- **Date**: 2024-01-07
- **Status**: Final
- **Review Cycle**: Monthly