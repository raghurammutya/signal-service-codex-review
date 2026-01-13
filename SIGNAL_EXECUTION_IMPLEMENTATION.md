# Signal Script Execution from MinIO - Implementation

## Overview

This document describes the implementation of Item 3: Signal script execution from MinIO (Sprint 5A).

## Implementation Details

### 1. Signal Executor Service (`app/services/signal_executor.py`)

Core service for executing signal scripts with MinIO integration:

**Key Components:**
- **MinIO Integration**: Fetches scripts from marketplace or personal namespaces
- **Sandbox Execution**: Restricted Python environment with allowed APIs only
- **Redis Publishing**: Results published to signal stream contract keys
- **ACL Enforcement**: Personal signals only accessible by owner

**Allowed APIs in Sandbox:**
```python
ALLOWED_MODULES = {
    "math", "statistics", "datetime", "time", "json",
    "collections", "itertools", "functools", "operator"
}
```

**Key Methods:**
- `fetch_marketplace_script()` - Uses execution token to get presigned URL from marketplace
- `fetch_personal_script()` - Direct MinIO fetch with ACL check
- `execute_signal_script()` - Sandboxed execution with timeout
- `publish_to_redis()` - Publishes to stream keys

### 2. API Endpoints (`app/api/v2/signal_execution.py`)

Two endpoints for signal execution:

**Marketplace Signals:**
```
POST /api/v2/signals/execute/marketplace
Body: {
    "execution_token": "token-from-marketplace",
    "product_id": "prod-123",
    "instrument": "NIFTY50",
    "params": {"period": 14},
    "subscription_id": "sub-789"  // For watermarking
}
```

**Personal Signals:**
```
POST /api/v2/signals/execute/personal
Body: {
    "script_id": "signal-456",
    "instrument": "BANKNIFTY",
    "params": {"threshold": 0.5}
}
```

Both endpoints:
- Use background tasks for non-blocking execution
- Return execution ID and stream keys immediately
- Authenticate via API Gateway headers

### 3. Schema Additions (`app/schemas/signal_schemas.py`)

Added request/response schemas:
- `SignalExecutionRequest` - Marketplace signal execution
- `PersonalSignalExecutionRequest` - Personal signal execution  
- `SignalExecutionResponse` - Common response with stream keys

### 4. Main App Integration (`app/main.py`)

Added signal execution router to the FastAPI app for endpoint registration.

## Architecture

```
User Request
     │
     ▼
API Endpoint ──► Background Task
                      │
                      ▼
              Fetch Script from MinIO
              (Marketplace via token OR
               Personal with ACL check)
                      │
                      ▼
              Execute in Sandbox
              (Restricted Python env)
                      │
                      ▼
              Collect emit_signal() calls
                      │
                      ▼
              Publish to Redis Streams
              (Using stream key format)
```

## Security Features

1. **No Inline Code**: All scripts must be fetched from MinIO
2. **Execution Tokens**: Marketplace scripts require valid tokens
3. **ACL Enforcement**: Personal scripts only accessible by owner
4. **Sandboxed Execution**: Limited APIs, no file/network access
5. **Timeout Protection**: Default 30s timeout prevents runaway scripts
6. **Watermarking**: Subscription ID passed through for marketplace signals

## Redis Stream Keys

Generated using `signal_stream_contract.py`:

**Marketplace:**
```
marketplace:{product_id}:{instrument}:{signal_name}:{params}
Example: marketplace:prod-123:NIFTY50:momentum:period-14
```

**Personal:**
```
personal:{user_id}:{script_id}:{instrument}:{params}
Example: personal:user-456:signal-789:BANKNIFTY:fast-12_slow-26
```

## Script Interface

Signal scripts have access to:

**Context Variables:**
```python
context = {
    "instrument": "NIFTY50",
    "params": {"period": 14},
    "product_id": "prod-123",      # Marketplace only
    "user_id": "user-456",          # User executing
    "subscription_id": "sub-789",   # For watermarking
    "timestamp": "2024-01-01T12:00:00Z"
}
```

**Available Functions:**
- `emit_signal(data)` - Emit a signal to be published
- `log(message)` - Log messages
- `get_timestamp()` - Get current ISO timestamp
- `get_unix_timestamp()` - Get Unix timestamp

**Example Script:**
```python
# Calculate RSI signal
def calculate_rsi_signal():
    instrument = context.get('instrument')
    period = context.get('params', {}).get('period', 14)
    
    # Calculation logic here...
    rsi_value = 65.5
    
    emit_signal({
        'name': 'rsi',
        'instrument': instrument,
        'value': rsi_value,
        'overbought': rsi_value > 70,
        'oversold': rsi_value < 30,
        'period': period
    })

calculate_rsi_signal()
```

## Testing

Comprehensive test suite in `test_signal_execution.py`:
- ✅ Marketplace script fetching with token
- ✅ Personal script fetching with ACL
- ✅ Sandbox execution and timeout
- ✅ Error handling
- ✅ Security restrictions
- ✅ Redis publishing
- ✅ API endpoint integration
- ✅ Stream key generation

## Production Considerations

1. **Script Caching**: Consider caching fetched scripts for performance
2. **Rate Limiting**: Add per-user execution limits
3. **Resource Limits**: Monitor memory/CPU usage during execution
4. **Audit Logging**: Log all script executions for compliance
5. **Error Monitoring**: Track script failures and timeouts

## Next Steps

- Item 4: Make SDK signal listing real (integrate with marketplace)
- Item 5: Remove hardcoded billing tiers
- Item 6: Expose author-controlled version policy
- Item 7: Add receive_email support in SDK