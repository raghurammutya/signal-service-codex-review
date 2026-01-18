# Infrastructure Coordination Plan for Signal Service Production Validation

## Current Verified Status: 6/15 Issues Resolved ✅

The signal service code improvements are **demonstrably implemented and working**. The remaining validation requires infrastructure coordination with dependent services.

---

## OPTION 1: Production Environment Validation (Recommended)

### Required Service Endpoints
```yaml
services:
  alert_service: "http://alert-service:8085"
  comms_service: "http://comms-service:8086" 
  marketplace_service: "http://marketplace:8087"
  watermark_service: "http://watermark:8088"
  metrics_service: "http://metrics:9090"
  user_service: "http://user-service:8091"
  config_service: "http://config-service:8092"
```

### Required Environment Variables
```bash
# Core Configuration
export ENVIRONMENT="production"
export LOG_LEVEL="INFO"

# Database & Cache
export DATABASE_URL="postgresql://signal_user:password@db:5432/signal_service"
export REDIS_URL="redis://redis:6379/0"

# Security
export JWT_SECRET_KEY="your-production-jwt-secret"
export GATEWAY_SECRET="your-gateway-secret" 
export INTERNAL_API_KEY="your-internal-service-key"
export CORS_ALLOWED_ORIGINS="https://app.yourdomain.com,https://screener.yourdomain.com"

# Service Integration
export ALERT_SERVICE_URL="http://alert-service:8085"
export COMMS_SERVICE_URL="http://comms-service:8086"  
export MARKETPLACE_SERVICE_URL="http://marketplace:8087"
export USER_SERVICE_URL="http://user-service:8091"
export CALENDAR_SERVICE_URL="http://calendar-service:8093"
export MESSAGING_SERVICE_URL="http://messaging-service:8094"

# MinIO Storage
export MINIO_ENDPOINT="http://minio:9000"
export MINIO_ACCESS_KEY="your-minio-access-key"
export MINIO_SECRET_KEY="your-minio-secret-key"

# Timeouts
export SERVICE_INTEGRATION_TIMEOUT="30"
```

### Validation Commands to Run
```bash
# 1. Deployment Safety Validation (Target: 22/22)
python3 scripts/deployment_safety_validation.py --environment=production

# 2. Metrics Service Integration Coverage (Target: 95%+)
python3 -m pytest tests/integration/test_metrics_service.py \
  --cov=app.services.metrics_service \
  --cov-report=term-missing \
  --cov-fail-under=95 -v

# 3. CORS Configuration Validation
python3 -m pytest tests/unit/test_comprehensive_cors_validation.py \
  --cov=common.cors_config --cov-report=term -v

# 4. Service Integration Suite  
python3 -m pytest tests/integration/ \
  --cov=app.clients --cov=app.services \
  --cov-report=html:coverage_reports/integration_coverage \
  --cov-fail-under=90 -v

# 5. Screener Contract Validation
python3 tests/integration/test_screener_service_contract.py

# 6. Watermark Security Validation
python3 -m pytest tests/integration/test_watermark_fail_secure.py -v

# 7. StreamAbuse Protection Validation
python3 -c "
from app.services.stream_abuse_protection import StreamAbuseProtection
# Test fail-closed behavior with marketplace service
"
```

### Expected Results
- **Deployment Safety**: 22/22 checks passing
- **Integration Coverage**: ≥95% on critical service paths
- **CORS Validation**: Environment configuration validated
- **Service Contracts**: All HTTP clients working with retry/timeout
- **Security**: Watermark and entitlement enforcement confirmed

---

## OPTION 2: Comprehensive Mock Infrastructure (Alternative)

If production environment setup is complex, create a self-contained mock infrastructure:

### Mock Service Implementation
```python
# tests/mocks/service_mock_suite.py
class MockServiceSuite:
    """Faithful mocks for all external services"""
    
    def __init__(self):
        self.alert_service = MockAlertService(port=8085)
        self.comms_service = MockCommsService(port=8086)
        self.marketplace = MockMarketplaceService(port=8087)
        self.watermark = MockWatermarkService(port=8088)
        self.metrics = MockMetricsService(port=9090)
        self.user_service = MockUserService(port=8091)
    
    async def start_all(self):
        """Start all mock services for integration testing"""
        # Start HTTP servers for each mock service
        
    async def stop_all(self):
        """Clean shutdown of all mocks"""
```

### Mock Environment Setup
```bash
# Create mock environment script
cat > setup_mock_environment.sh << 'EOF'
#!/bin/bash
export ENVIRONMENT="development"
export DATABASE_URL="sqlite:///test.db"
export REDIS_URL="redis://localhost:6379/15"
export ALERT_SERVICE_URL="http://localhost:8085"
export COMMS_SERVICE_URL="http://localhost:8086"
# ... mock URLs for all services
EOF

source setup_mock_environment.sh
python3 tests/mocks/service_mock_suite.py --start-all
```

### Benefits of Mock Approach
- ✅ Can run in CI/CD without external dependencies
- ✅ Deterministic test results
- ✅ Version controlled alongside code
- ✅ Faster feedback loop for development

### Drawbacks of Mock Approach  
- ❌ Mock behavior may diverge from real services
- ❌ Additional maintenance burden
- ❌ Cannot catch real integration issues
- ❌ Less confidence in production behavior

---

## TEAM COORDINATION MATRIX

| Team | Service | Required for Issues | Contact Needed |
|------|---------|-------------------|----------------|
| **Alert Team** | alert-service:8085 | #5, #10, #12 | Authentication keys, API contracts |
| **Comms Team** | comms-service:8086 | #5, #10, #12 | SMTP configs, template validation |
| **Marketplace Team** | marketplace:8087 | #10, #14 | Entitlement APIs, subscription tiers |
| **Security Team** | watermark:8088 | #6, #10 | Watermark validation endpoints |
| **Observability Team** | metrics:9090 | #10, #11 | Prometheus format, push gateway |
| **User Team** | user-service:8091 | #8, #10, #13 | Profile APIs, watchlist format |
| **DevOps Team** | Infrastructure | #1, #2, #3, #4, #10 | Environment variables, database setup |

---

## IMMEDIATE NEXT STEPS

### For Code Review Completion:
1. **Choose Infrastructure Path**: Production vs Mocks
2. **Coordinate with Teams**: Get service endpoints and auth keys
3. **Set Environment**: Configure all 17 required environment variables
4. **Execute Validation**: Run full test suite with live/mock services
5. **Generate Reports**: Coverage, deployment safety, integration results

### Timeline Estimate:
- **Production Environment Setup**: 2-3 days (with team coordination)  
- **Mock Infrastructure Development**: 3-5 days (if choosing mock path)
- **Full Validation Execution**: 1 day (once environment is ready)
- **Final Report Generation**: 0.5 days

### Success Criteria for Production Sign-off:
- [ ] **Deployment Safety**: 22/22 validations passing
- [ ] **Integration Coverage**: ≥95% on critical paths  
- [ ] **Service Contracts**: All 6 external service integrations validated
- [ ] **Security Validation**: CORS, watermark, entitlement enforcement confirmed
- [ ] **Performance**: All timeouts and retry mechanisms tested under load

---

## CURRENT CONFIDENCE LEVEL

**Code Quality**: 🟢 **HIGH** - 6/15 issues resolved with verified implementations  
**Integration Readiness**: 🟡 **MEDIUM** - Depends on infrastructure setup  
**Production Deployment**: 🟡 **PENDING** - Awaiting infrastructure validation  

**Recommendation**: Proceed with production environment setup for highest confidence, or develop comprehensive mock suite if production coordination is complex.

---

**Next Action Required**: Choose infrastructure path and coordinate with dependent teams for final validation phase.