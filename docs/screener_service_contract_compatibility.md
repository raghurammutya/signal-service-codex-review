# Screener Service Contract Compatibility

## Overview

This document outlines the integration contract between `signal_service` and the `screener_service` backend, ensuring compatibility for cross-service signal consumption.

## Signal Service API Contract for Screener Integration

### 1. Signal Stream Endpoints

#### GET `/api/v2/signals/stream/available`
**Purpose**: Screener service can discover available signal streams for display

**Request Headers**:
```
Authorization: Bearer <user_token>
X-Internal-API-Key: <service_key>  // For service-to-service calls
```

**Response Format**:
```json
{
  "public": [
    {
      "stream_id": "rsi_divergence",
      "name": "RSI Divergence Signals",
      "description": "Identifies bullish/bearish RSI divergences",
      "instruments": ["AAPL", "MSFT", "GOOGL"],
      "frequency": "1h",
      "availability": "public"
    }
  ],
  "common": [...],
  "marketplace": [...],
  "personal": [...]
}
```

**Contract Guarantees**:
- Always returns valid JSON structure
- `stream_id` is unique and stable across requests
- `instruments` list reflects current user watchlist if authenticated
- Graceful degradation if user watchlist unavailable (returns empty arrays)

#### WebSocket `/api/v2/signals/stream/{stream_id}`
**Purpose**: Real-time signal consumption for screener display

**Connection Headers**:
```
Authorization: Bearer <user_token>
Sec-WebSocket-Protocol: signal-stream-v2
```

**Message Format**:
```json
{
  "signal_id": "sig_1234567890",
  "stream_id": "rsi_divergence", 
  "signal_type": "BULLISH_DIVERGENCE",
  "symbol": "AAPL",
  "instrument_key": "NASDAQ:AAPL",
  "message": "RSI bullish divergence detected",
  "value": 65.23,
  "confidence": 0.87,
  "timestamp": "2025-01-18T10:30:00Z",
  "metadata": {
    "source": "signal_service",
    "strategy_id": "rsi_divergence_v2",
    "timeframe": "1h"
  }
}
```

**Contract Guarantees**:
- Messages always include required fields: `signal_id`, `symbol`, `signal_type`, `timestamp`
- `confidence` is float between 0.0 and 1.0
- `instrument_key` follows format: `{exchange}:{symbol}`
- Connection maintains heartbeat every 30 seconds
- Graceful disconnection with proper close codes

### 2. Historical Signals Endpoint

#### GET `/api/v2/signals/history`
**Purpose**: Screener can fetch historical signals for backtesting/analysis

**Query Parameters**:
```
symbol: string (required) - Stock symbol
timeframe: string - "1m", "5m", "15m", "1h", "1d" (default: "1h")
from_date: ISO string - Start date (default: 24h ago)
to_date: ISO string - End date (default: now)
signal_types: string[] - Filter by signal types
limit: int - Max results (default: 100, max: 1000)
```

**Response Format**:
```json
{
  "signals": [
    {
      "signal_id": "sig_1234567890",
      "signal_type": "BULLISH_DIVERGENCE",
      "symbol": "AAPL",
      "value": 65.23,
      "confidence": 0.87,
      "timestamp": "2025-01-18T10:30:00Z"
    }
  ],
  "pagination": {
    "total": 150,
    "limit": 100,
    "offset": 0,
    "has_more": true
  },
  "metadata": {
    "timeframe": "1h",
    "date_range": {
      "from": "2025-01-17T10:30:00Z",
      "to": "2025-01-18T10:30:00Z"
    }
  }
}
```

### 3. Signal Performance Metrics

#### GET `/api/v2/signals/{signal_id}/performance`
**Purpose**: Screener can display signal success rates and performance data

**Response Format**:
```json
{
  "signal_id": "sig_1234567890",
  "performance_metrics": {
    "success_rate": 0.73,
    "avg_return": 0.025,
    "sharpe_ratio": 1.42,
    "max_drawdown": 0.08,
    "total_signals": 156,
    "profitable_signals": 114
  },
  "timeframe_performance": {
    "1d": {"success_rate": 0.75, "total": 50},
    "7d": {"success_rate": 0.71, "total": 156},
    "30d": {"success_rate": 0.69, "total": 423}
  }
}
```

## Screener Service Integration Requirements

### 1. Authentication & Authorization
- Must include valid user JWT token in Authorization header
- For service-to-service calls, must include X-Internal-API-Key header
- Signal access subject to user subscription tier validation
- Failed auth returns 401 with clear error message

### 2. Rate Limiting
- WebSocket connections: 10 concurrent per user
- API calls: 1000 requests per hour per user
- Bulk operations: 10 concurrent requests max
- Rate limit headers included in all responses:
  ```
  X-RateLimit-Limit: 1000
  X-RateLimit-Remaining: 847
  X-RateLimit-Reset: 1737194400
  ```

### 3. Error Handling Contract
- All errors return consistent format:
  ```json
  {
    "error": {
      "code": "STREAM_NOT_FOUND",
      "message": "Signal stream 'invalid_stream' not found",
      "timestamp": "2025-01-18T10:30:00Z",
      "request_id": "req_1234567890"
    }
  }
  ```

### 4. Circuit Breaker Behavior
- When signal_service is overloaded:
  - API calls return 503 Service Unavailable
  - WebSocket connections rejected with 1001 close code
  - Retry-After header indicates when to retry
- Graceful degradation: cached signals returned when available

### 5. Data Consistency Guarantees
- Signal timestamps always in UTC ISO 8601 format
- Numeric values (price, confidence) never null/undefined
- Enum values (signal_type) from documented vocabulary
- Instrument identifiers stable across sessions

## Testing Contract Compliance

### Integration Test Suite
```python
class TestScreenerServiceContract:
    
    async def test_available_streams_contract(self):
        """Test /api/v2/signals/stream/available returns valid structure"""
        response = await client.get("/api/v2/signals/stream/available")
        assert response.status_code == 200
        data = response.json()
        assert "public" in data
        assert "common" in data
        assert "marketplace" in data
        assert "personal" in data
        
        # Validate stream structure
        for stream in data["public"]:
            assert "stream_id" in stream
            assert "name" in stream
            assert "instruments" in stream
            assert isinstance(stream["instruments"], list)
    
    async def test_websocket_signal_format(self):
        """Test WebSocket signals match expected format"""
        async with websockets.connect(ws_url) as websocket:
            message = await websocket.recv()
            signal = json.loads(message)
            
            # Required fields
            required_fields = ["signal_id", "symbol", "signal_type", "timestamp"]
            for field in required_fields:
                assert field in signal
            
            # Data types
            assert isinstance(signal["confidence"], (int, float))
            assert 0.0 <= signal["confidence"] <= 1.0
            
    async def test_historical_signals_pagination(self):
        """Test historical signals API pagination works correctly"""
        response = await client.get("/api/v2/signals/history", params={
            "symbol": "AAPL",
            "limit": 50
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "signals" in data
        assert "pagination" in data
        assert len(data["signals"]) <= 50
```

### Performance Contract Tests
```python
async def test_websocket_connection_limits():
    """Verify connection limits are enforced"""
    connections = []
    try:
        # Attempt 15 connections (over 10 limit)
        for i in range(15):
            ws = await websockets.connect(ws_url)
            connections.append(ws)
        
        # 11th+ connections should be rejected
        assert len([c for c in connections if c.open]) == 10
    finally:
        for ws in connections:
            if ws.open:
                await ws.close()

async def test_rate_limiting_behavior():
    """Verify API rate limiting works correctly"""
    # Make rapid requests to trigger rate limiting
    for i in range(100):
        response = await client.get("/api/v2/signals/stream/available")
        if response.status_code == 429:
            assert "Retry-After" in response.headers
            break
    else:
        pytest.fail("Rate limiting not triggered after 100 requests")
```

## Deployment Checklist for Screener Integration

- [ ] Signal service API endpoints respond within 200ms average
- [ ] WebSocket connections handle 1000+ concurrent users
- [ ] Historical signals API supports date range queries
- [ ] Error responses include actionable error codes
- [ ] Rate limiting configuration matches screener traffic patterns
- [ ] Circuit breaker thresholds tested under load
- [ ] Authentication flow tested with screener service accounts
- [ ] Signal data format validated against screener consumption logic
- [ ] Monitoring alerts configured for integration health
- [ ] Rollback plan documented for integration failures

## Compatibility Matrix

| Screener Version | Signal Service Version | Status | Notes |
|------------------|------------------------|---------|-------|
| v1.0.x | v2.1.x | ✅ Compatible | Full feature support |
| v1.1.x | v2.1.x | ✅ Compatible | Enhanced performance metrics |
| v1.2.x | v2.2.x | 🚧 In Progress | New signal types support |
| v2.0.x | v3.0.x | 📋 Planned | GraphQL migration |

## Breaking Changes Protocol

1. **Advance Notice**: 30 days minimum for breaking changes
2. **Versioned Endpoints**: Maintain v1 compatibility for 6 months
3. **Migration Guide**: Detailed upgrade documentation provided
4. **Staging Testing**: Full integration testing in staging environment
5. **Rollback Ready**: Immediate rollback capability maintained

---

**Last Updated**: 2025-01-18  
**Next Review**: 2025-02-18  
**Maintainer**: Signal Service Team  
**Integration Contact**: screener-team@company.com