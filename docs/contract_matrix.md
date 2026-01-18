# Contract Matrix - Service Integration Compliance

| Service          | Endpoint / Path                        | Direction (Call / Called By) | Payload Shape (Req/Resp) | Auth (Headers)                   | Status Codes | Confidence % | Tests / Evidence                     | Notes / Gaps |
|------------------|----------------------------------------|------------------------------|--------------------------|----------------------------------|--------------|-------------:|---------------------------------------|--------------|
| **ticker_service**   | `/api/v1/historical`                     | Call                         | req: `{instrument, start, end, interval}`; resp: `ohlcv[]` | X-Internal-API-Key               | 200,4xx,5xx  |         95% | test_ticker_service_integration.py    | Production validated |
| **ticker_service**   | `/api/v1/realtime`                      | Call                         | req: `{symbols[]}`; resp: `{prices, timestamps}` | X-Internal-API-Key               | 200,4xx,5xx  |         90% | test_ticker_service_integration.py    | WebSocket fallback needed |
| **instrument_srv**   | `/api/v1/instruments/{underlying}/options` | Call                      | resp: `{expiries[], strikes[], chain}` | X-Internal-API-Key               | 200,404,5xx  |         85% | test_ticker_service_integration.py    | Cache invalidation unclear |
| **instrument_srv**   | `/api/v1/instruments/search`            | Call                         | req: `{query, type}`; resp: `instruments[]` | X-Internal-API-Key               | 200,4xx,5xx  |         80% | test_ticker_service_integration.py    | Pagination not tested |
| **marketplace**      | `/api/v1/integration/verify-execution`   | Call                         | req: `{token, stream}`; resp: `{valid, user_id, entitlements}` | X-Internal-API-Key               | 200,401,403  |         88% | test_signal_delivery_service.py       | Rate limiting behavior unclear |
| **marketplace**      | `/api/v1/watermark/validate`            | Call                         | req: `{data, user_id}`; resp: `{valid, watermark_meta}` | X-Internal-API-Key               | 200,401,422  |         75% | test_marketplace_watermarking_fail_secure.py | Fail-secure mode tested |
| **user_service**     | `/api/v1/users/{id}/profile`            | Call                         | resp: `{user_id, tier, preferences}` | X-Internal-API-Key               | 200,404,5xx  |         85% | test_signal_delivery_service.py       | Profile caching strategy |
| **user_service**     | `/api/v1/users/{id}/watchlist`          | Call                         | resp: `{symbols[], custom_lists}` | X-Internal-API-Key               | 200,404,5xx  |         82% | test_signal_delivery_service.py       | Watchlist sync frequency |
| **user_service**     | `/api/v1/users/{id}/entitlements`       | Call                         | resp: `{active_subscriptions[], limits}` | X-Internal-API-Key               | 200,404,5xx  |         90% | test_entitlement_gateway_only_access.py | Entitlement changes propagation |
| **alert_service**    | `/api/v1/alerts/send`                   | Call                         | req: `{user_id, message, channel, priority}`; resp: `{sent, delivery_id}` | X-Internal-API-Key               | 200,4xx,5xx  |         85% | test_service_integrations_coverage.py | Channel fallback logic |
| **alert_service**    | `/api/v1/alerts/delivery-status`        | Call                         | req: `{delivery_id}`; resp: `{status, attempts, last_error}` | X-Internal-API-Key               | 200,404,5xx  |         80% | test_service_integrations_coverage.py | Status polling frequency |
| **comms_service**    | `/api/v1/comms/send`                    | Call                         | req: `{user_id, content, template, medium}`; resp: `{ok, message_id}` | X-Internal-API-Key               | 200,4xx,5xx  |         83% | test_service_integrations_coverage.py | Template validation |
| **comms_service**    | `/api/v1/comms/templates`               | Call                         | resp: `{templates[], categories}` | X-Internal-API-Key               | 200,5xx      |         78% | test_service_integrations_coverage.py | Template versioning |
| **metrics_export**   | `/api/v1/metrics` (Prometheus)          | Called By (Prometheus)       | resp: `text/plain` Prometheus format | none/internal                    | 200          |         92% | test_metrics_service_contract.py      | Need scrape test |
| **screener_service** | `/api/v1/screener/signal-input`         | Called By (screener)         | req: `{signals[], metadata}`; resp: `{processed, filters_applied}` | X-Internal-API-Key               | 200,4xx,5xx  |         70% | test_screener_service_contract.py     | Signal format evolution |
| **algo_engine**      | `/api/v1/personal-scripts`              | Call                         | req: `{user_id}`; resp: `{scripts[], permissions}` | X-Internal-API-Key               | 200,4xx,5xx  |         88% | vectorized/SDK tests                  | Script execution sandboxing |
| **algo_engine**      | `/api/v1/execute-custom`                | Call                         | req: `{script_id, parameters, data}`; resp: `{result, execution_time}` | X-Internal-API-Key               | 200,400,403,5xx |      85% | test_external_function_executor.py   | Timeout handling |
| **gateway**          | All ingress paths                       | Called By (API gateway)      | Varies by endpoint | Gateway headers (X-User-ID, X-Gateway-Secret) | 2xx,401,403  |         95% | CORS/auth tests                       | Rate limiting per user |
| **config_service**   | `/api/v1/config/budget-guards`          | Call                         | resp: `{memory_mb, cpu_percent, concurrent_ops}` | X-Internal-API-Key               | 200,404,5xx  |         90% | test_config_bootstrap.py              | Config hot-reload |
| **config_service**   | `/api/v1/config/circuit-breakers`       | Call                         | resp: `{services: {max_failures, timeout_seconds}}` | X-Internal-API-Key               | 200,404,5xx  |         88% | test_config_coverage_validation.py   | Circuit breaker state sync |
| **redis_cluster**    | Redis protocol                          | Call                         | Various Redis commands | none (internal network)          | Redis responses |      92% | test_database_session_coverage.py    | Cluster failover tested |
| **timescale_db**     | PostgreSQL protocol                     | Call                         | SQL queries for time-series data | Database credentials             | SQL responses |       95% | test_database_failure_modes.py       | Connection pooling |

## Contract Confidence Scoring

**Confidence % Calculation:**
- **90-100%**: Production validated with comprehensive tests, error handling, and monitoring
- **80-89%**: Well tested with integration tests, some edge cases covered
- **70-79%**: Basic integration tests, limited error scenario coverage  
- **60-69%**: Minimal testing, potential gaps in error handling
- **<60%**: Insufficient validation, requires immediate attention

## Critical Gaps Identified

### High Priority (< 80% confidence):
1. **screener_service** (70%): Signal format evolution not tested
2. **marketplace watermark** (75%): Limited fail-secure validation
3. **comms_service templates** (78%): Template versioning unclear

### Medium Priority (80-85% confidence):
4. **instrument_srv search** (80%): Pagination not tested
5. **alert_service status** (80%): Status polling frequency unclear
6. **user_service watchlist** (82%): Sync frequency unclear
7. **comms_service send** (83%): Template validation gaps

## Test Evidence Files

| Service Integration | Primary Test File | Additional Evidence |
|-------------------|-------------------|-------------------|
| Ticker Service | `test_ticker_service_integration.py` | Historical/realtime data validation |
| Marketplace | `test_signal_delivery_service.py` | Execution verification, watermarking |
| User Services | `test_entitlement_gateway_only_access.py` | Entitlement checks, profile access |
| Alert/Comms | `test_service_integrations_coverage.py` | Delivery status, template usage |
| Metrics Export | `test_metrics_service_contract.py` | Prometheus format compliance |
| Screener | `test_screener_service_contract.py` | Signal input/output validation |
| Algorithm Engine | `test_external_function_executor.py` | Custom script execution |
| Gateway/CORS | CORS/auth integration tests | Authentication, rate limiting |
| Config Service | `test_config_bootstrap.py` | Configuration retrieval, validation |
| Database | `test_database_failure_modes.py` | Connection handling, failover |

## Request/Response Examples

### Ticker Service - Historical Data
```json
// Request
{
  "instrument": "NSE@NIFTY@INDEX", 
  "start": "2024-01-01T09:15:00Z",
  "end": "2024-01-01T15:30:00Z", 
  "interval": "1m"
}

// Response (200)
{
  "success": true,
  "data": [
    {
      "timestamp": "2024-01-01T09:15:00Z",
      "open": 21500.25, "high": 21520.75, 
      "low": 21495.00, "close": 21510.50,
      "volume": 125000
    }
  ]
}

// Error Response (400)
{
  "success": false,
  "error": "Invalid instrument format",
  "code": "INVALID_INSTRUMENT"
}
```

### Marketplace - Execution Verification
```json
// Request
{
  "token": "user_session_token_here",
  "stream": "realtime_signals_v2"
}

// Response (200)
{
  "valid": true,
  "user_id": "user_12345",
  "entitlements": ["premium_signals", "realtime_data"],
  "rate_limits": {"requests_per_minute": 120}
}

// Error Response (403)
{
  "valid": false,
  "error": "Insufficient entitlements",
  "required": ["premium_signals"]
}
```

### Alert Service - Send Alert
```json
// Request
{
  "user_id": "user_12345",
  "message": "NIFTY signal triggered: BUY at 21500",
  "channel": "push_notification",
  "priority": "high"
}

// Response (200)
{
  "sent": true,
  "delivery_id": "alert_67890",
  "estimated_delivery": "2024-01-01T10:30:15Z"
}
```

## Compliance Action Items

### Immediate (< 80% confidence):
1. Add screener service signal format evolution tests
2. Enhance marketplace watermark fail-secure validation  
3. Add comms service template versioning tests
4. Add instrument service pagination test coverage

### Short-term (80-85% confidence):
5. Add alert service delivery status polling tests
6. Add user service watchlist sync frequency tests
7. Add comprehensive template validation for comms service

### Monitoring Enhancements:
8. Add Prometheus scrape format test to CI
9. Add gateway rate limiting per-user validation
10. Add config service hot-reload testing

---
**Last Updated:** 2026-01-18T08:11:00Z  
**Next Review:** Weekly during development, monthly in production  
**Owner:** Signal Service Team