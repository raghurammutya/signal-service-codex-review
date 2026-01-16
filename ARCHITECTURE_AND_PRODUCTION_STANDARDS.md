# StocksBlitz Architecture and Production Standards

**Version**: 2.0.0  
**Last Updated**: 2026-01-16  
**Status**: MANDATORY FOR ALL DEVELOPMENT AND PRODUCTION  
**Sources**: Merged from Architecture Principles (27 principles) + Master Compliance Checklist (10 production standards)

---

> **CRITICAL**: This document defines the **non-negotiable architectural and production standards** for the StocksBlitz platform. Every Claude session, developer, and operational change MUST adhere to these standards.

**Before starting ANY work, Claude MUST acknowledge these standards by stating:**
> "I have reviewed the Architecture and Production Standards and will adhere to all requirements, especially: config_service usage, API versioning, JWT validation via api-gateway, single-route-per-functionality, and production security standards."

---

# PART I: DEVELOPMENT ARCHITECTURE PRINCIPLES

## 1. Config Service is MANDATORY

**Rule**: ALL services MUST use config_service. No exceptions.

```python
# CORRECT - Service requires config_service
from common.config_service.client import ConfigClient

config = ConfigClient()
db_url = config.get_secret("DATABASE_URL", environment="prod")

# WRONG - Service starts without config_service
if config_service_available:
    # ... use config service
else:
    # FALLBACK TO DEFAULTS - THIS IS FORBIDDEN
    db_url = "postgresql://localhost/db"  # NEVER DO THIS
```

**Implementation Requirements**:
- Services MUST fail to start if config_service is unavailable
- `CONFIG_SERVICE_ENABLED=false` or `USE_CONFIG_SERVICE=false` flags are FORBIDDEN
- No hardcoded fallback values for any secrets or configuration
- Health checks MUST verify config_service connectivity

**Acceptable Failure Modes**:
```python
# Service startup - CORRECT behavior
try:
    config = ConfigClient()
    config.validate_connection()
except ConfigServiceUnavailable as e:
    logger.critical("Config service unavailable - refusing to start")
    sys.exit(1)  # FAIL FAST - DO NOT FALLBACK
```

## 2. All Secrets and Configuration in Config Service Only

**Rule**: Environment variables, parameters, and credentials MUST reside ONLY in config_service.

**Allowed Bootstrap Environment Variables**:
- `STOCKSBLITZ_CONFIG_API_KEY` - Config service authentication key
- `CONFIG_SERVICE_URL` - Config service endpoint URL
- `ENVIRONMENT` - Environment identifier (prod/staging/dev)

**FORBIDDEN in Code**:
- Database URLs/credentials
- API keys (internal or external)
- JWT secrets
- Encryption keys
- Service URLs (must be from config or service discovery)
- Redis URLs/credentials
- Any value that differs between environments

## 3. API Versioning is Mandatory

**Rule**: ALL API endpoints MUST include version prefix.

**Standard Format**: `/api/v{version}/{resource}`

```python
# CORRECT
@router.get("/api/v1/users/{user_id}")
@router.post("/api/v1/orders")
@router.get("/api/v2/positions")  # New version

# WRONG - No versioning
@router.get("/users/{user_id}")   # FORBIDDEN
@router.post("/orders")           # FORBIDDEN
```

## 4. Silent Fallbacks MUST Be Identified and Eliminated

**Rule**: Any silent fallback behavior when reading from config_service is a BUG.

```python
# FORBIDDEN - Silent fallback
db_url = config.get("DATABASE_URL") or "postgresql://localhost/db"
db_url = config.get("DATABASE_URL", default="postgresql://localhost/db")

# CORRECT - Explicit failure
db_url = config.get_required("DATABASE_URL")  # Raises if not found
```

## 5. Naming Standards are Non-Negotiable

**Rule**: All infrastructure follows the StocksBlitz Naming Standards.

| Component | Format | Example |
|-----------|--------|---------|
| Docker Network | `stocksblitz-{environment}` | `stocksblitz-prod` |
| Container | `stocksblitz-{service}-{environment}` | `stocksblitz-backend-prod` |
| Docker Image | `stocksblitz/{service}:{tag}` | `stocksblitz/backend:prod` |
| Volume | `stocksblitz-{purpose}-{environment}` | `stocksblitz-redis-data-prod` |
| Env Variable | `STOCKSBLITZ_{SERVICE}_{VAR}` | `STOCKSBLITZ_BACKEND_PORT` |

**FORBIDDEN Prefixes**:
- `tv-` (legacy TradingView)
- `tradingview-`
- `quantagro-`
- Service names without `stocksblitz-` prefix in production

## 6. Services Start from Docker Compose Only

**Rule**: ALL services in production MUST be started via docker-compose.

```bash
# CORRECT - Using docker-compose
docker-compose -f docker-compose.prod.yml up -d backend
docker-compose -f docker-compose.prod.yml restart user-service

# WRONG - Direct container run
docker run -d stocksblitz/backend  # FORBIDDEN
docker run -e DATABASE_URL=... stocksblitz/backend  # EXTREMELY FORBIDDEN
```

**Exception**: Only `config_service` may run via systemd (chicken-egg problem).

## 7. JWT Validation at API Gateway Only

**Rule**: ALL services MUST trust api-gateway for JWT validation. Services MUST NOT independently validate JWT tokens.

**Architecture**:
```
Frontend → api-gateway (validates JWT) → Backend Services (trust gateway)
                                              ↓
                                    X-User-ID, X-User-Role headers
```

## 8. Single Route: Frontend → Axios → API Gateway → Services

**Rule**: There is ONLY ONE route for frontend to backend communication. This cannot be bypassed.

```
ONLY ALLOWED PATH:
┌──────────┐     ┌─────────┐     ┌─────────────┐     ┌──────────────┐
│ Frontend │ ──→ │ Axios   │ ──→ │ API Gateway │ ──→ │ Backend      │
│ (React)  │     │ Layer   │     │ (Port 80)   │     │ Services     │
└──────────┘     └─────────┘     └─────────────┘     └──────────────┘

FORBIDDEN PATHS:
Frontend ──→ Backend Service (direct)           # FORBIDDEN
Frontend ──→ Database                           # FORBIDDEN
Frontend ──→ Redis                              # FORBIDDEN
```

## 9. One API Per Functionality - No Gaps, No Overlaps

**Rule**: Each functionality MUST have exactly ONE API endpoint across all layers. No duplicates, no missing endpoints.

## 10. Database Schema Ownership

**Rule**: Each service owns specific database schemas. Cross-schema writes are FORBIDDEN.

```sql
-- Schema ownership
public          → Shared/read-only for most services
user_service    → user_service ONLY
order_service   → order_service ONLY
marketplace     → marketplace_service ONLY
```

## 11. Health Checks

**Rule**: Every service MUST implement standardized health endpoints.

```python
# Required endpoints
GET /health           # Overall health status
GET /health/live      # Kubernetes liveness probe
GET /health/ready     # Kubernetes readiness probe
```

## 12. Error Response Format

**Rule**: All APIs MUST return consistent error responses.

```json
{
    "error": {
        "code": "ORDER_NOT_FOUND",
        "message": "Order with ID 12345 not found",
        "details": {},
        "request_id": "req-abc-123"
    }
}
```

## 13. Logging Standards

**Rule**: All services MUST use structured JSON logging.

```python
# CORRECT - Structured logging
logger.info("Order created", extra={
    "order_id": order.id,
    "user_id": user_id,
    "symbol": order.symbol,
    "quantity": order.quantity
})

# WRONG - Unstructured logging
logger.info(f"Created order {order.id} for user {user_id}")  # Hard to parse
```

## 14. No PII in Logs

**Rule**: Personally Identifiable Information MUST NOT appear in logs.

**FORBIDDEN in logs**:
- Email addresses
- Phone numbers  
- Full names
- IP addresses (use hashed version)
- API keys / tokens
- Passwords

## 15. Idempotency

**Rule**: All mutating operations SHOULD be idempotent where possible.

## 16. Rate Limiting

**Rule**: API Gateway MUST enforce rate limits. Services MAY add additional limits.

```python
# Rate limit tiers
ANONYMOUS: 10 requests/minute
AUTHENTICATED: 100 requests/minute
PREMIUM: 1000 requests/minute
INTERNAL: Unlimited (service-to-service)
```

## 17. Graceful Degradation

**Rule**: Services MUST degrade gracefully, not fail completely.

## 18. Backward Compatibility

**Rule**: API changes MUST be backward compatible within a version.

## 19. File Organization and Documentation Structure

**Rule**: Maintain clear separation between permanent architecture documentation and interim session work.

**`.gitignore` MUST include**:
```gitignore
# Interim session work
sessions/
*_SESSION_*.md
*_INTERIM_*.md
TEMP_*.md
DEBUG_*.md
```

## 20. Browser Automation for Frontend Debugging

**Rule**: Claude MUST use browser automation FIRST before asking for manual intervention. Manual checks are LAST RESORT ONLY.

## 21. Common Service Template

**Rule**: ALL new services MUST use the common service template. Existing services MUST be migrated to the template.

**Template Location**: `common/service_template/`

## 22. Single Internal API Key

**Rule**: Use one shared `INTERNAL_API_KEY` for all service-to-service communication. No per-service API keys.

## 23. Configuration Parameter Deduplication

**Rule**: ALL services MUST eliminate duplicated configuration parameters and use centralized config_service patterns.

## 24. Single INTERNAL_API_KEY Across All Services

**Rule**: ALL service-to-service authentication MUST use the same `INTERNAL_API_KEY`.

**Standard Value**: `AShhRzWhfXd6IomyzZnE3d-lCcAvT1L5GDCCZRSXZGsJq7_eAJGxeMi-4AlfTeOc` (stored in config_service)

## 25. Container Sequence Documentation

**Rule**: ALL services MUST document their startup dependencies and sequence requirements.

**Required File**: `CONTAINER_SEQUENCE.md` in service root directory

## 26. Port Management and Drift Prevention

**Rule**: Port assignments MUST be centralized and drift MUST be prevented through automation.

**Central Port Registry**: `.env.ports` (auto-generated from config_service)

## 27. Service Template Adoption Enforcement

**Rule**: ALL new services MUST use standardized templates from `/templates/service-templates/`.

---

# PART II: PRODUCTION INFRASTRUCTURE STANDARDS

## 28. Multi-Schema Database ACL Enforcement

**Rule**: Database access control lists MUST enforce schema boundaries with zero exceptions.

**Requirements**:
- [ ] Zero direct cross-schema database queries in application code
- [ ] All services access only their owned schemas + public shared tables
- [ ] API delegation latency < 50ms for 95th percentile
- [ ] Zero authentication failures in API delegation
- [ ] Clean schema boundaries enforced by database ACLs
- [ ] Internal API usage properly authenticated
- [ ] Service isolation successfully implemented

## 29. Production Hardware Standards

**Rule**: Production infrastructure MUST meet minimum hardware specifications.

**Server Specifications**:
- [ ] CPU: 8 cores (verify sufficient for load)
- [ ] RAM: 16 GB (verify sufficient for all services)
- [ ] Disk: 150 GB root, 12 GB data mount (check space utilization)
- [ ] Network: Adequate bandwidth for trading operations

**Operating System**:
- [ ] OS updated to latest patches: `sudo apt update && sudo apt upgrade`
- [ ] Kernel security updates applied
- [ ] Unnecessary services disabled
- [ ] Hostname set correctly: `stocksblitz-prod`

**Time Synchronization**:
- [ ] NTP configured and running: `timedatectl status`
- [ ] Timezone set to market timezone (Asia/Kolkata): `timedatectl`
- [ ] Clock drift within acceptable limits

## 30. Security Hardening Mandatory

**Rule**: Production security hardening is non-negotiable.

**Firewall**:
- [ ] Only required ports exposed: 80, 443, 22 (SSH)
- [ ] All service ports (8xxx) blocked externally
- [ ] Database port (5432) not exposed to internet
- [ ] Redis port (8202) not exposed to internet

**SSH Hardening**:
- [ ] Root login disabled: `PermitRootLogin no`
- [ ] Password authentication disabled: `PasswordAuthentication no`
- [ ] Key-based authentication only
- [ ] SSH port changed from 22 (optional but recommended)
- [ ] Fail2ban configured for SSH

**Container Security**:
- [ ] Containers run as non-root user
- [ ] Read-only filesystems where possible
- [ ] Capabilities dropped: `--cap-drop=ALL`
- [ ] No privileged containers: `--privileged=false`
- [ ] Secrets not in environment variables (use config service)
- [ ] Images scanned for vulnerabilities: `docker scan <image>`
- [ ] No `latest` tag in production (use specific versions)
- [ ] Minimal base images (alpine where possible)

## 31. SSL/HTTPS Production Requirements

**Rule**: HTTPS configuration is mandatory for all external endpoints.

**Requirements**:
- [ ] SSL certificate installed for app.stocksblitz.com
- [ ] Certificate auto-renewal configured (Let's Encrypt)
- [ ] HTTP to HTTPS redirect enabled
- [ ] HSTS header configured
- [ ] TLS 1.2+ only, TLS 1.0/1.1 disabled

**Security Headers**:
- [ ] HSTS: `max-age=31536000; includeSubDomains`
- [ ] CSP: Content Security Policy configured
- [ ] X-Frame-Options: `DENY` or `SAMEORIGIN`
- [ ] X-Content-Type-Options: `nosniff`
- [ ] X-XSS-Protection: `1; mode=block`

## 32. Production CORS Restrictions

**Rule**: CORS configuration MUST be restrictive in production.

**Requirements**:
- [ ] No `localhost` in production CORS
- [ ] No wildcard `*` CORS in production
- [ ] Only whitelisted origins:
  - `https://app.stocksblitz.com`
  - `https://stocksblitz.com`
  - `https://www.stocksblitz.com`

**Verification**:
```bash
curl -H "Origin: https://malicious.com" https://app.stocksblitz.com/api/v1/health
# Should return CORS error, not allow access
```

## 33. Database Production Standards

**Rule**: Database configuration MUST meet production reliability requirements.

**Database Health**:
- [ ] PostgreSQL running: `docker ps | grep postgres`
- [ ] Version: TimescaleDB + PostgreSQL 15
- [ ] Connection limit configured appropriately
- [ ] Max connections not being exceeded

**Database Optimization**:
- [ ] Indexes created on all foreign keys
- [ ] Vacuum and analyze scheduled
- [ ] Connection pooling configured (if using pgBouncer)
- [ ] Query performance analyzed and optimized
- [ ] Slow query log enabled and monitored

**Schema Validation**:
- [ ] All migrations applied: Check migration version
- [ ] Schema matches models in all services
- [ ] Foreign key constraints in place
- [ ] Unique constraints validated

**Multi-Schema Setup**:
- [ ] `public` schema: Shared tables (users, instruments)
- [ ] `user_service` schema: User service tables
- [ ] `order_service` schema: Order service tables (if separated)
- [ ] `marketplace` schema: Marketplace tables (if separated)
- [ ] All models explicitly specify schema: `__table_args__ = {'schema': 'xxx'}`

**Data Quality**:
- [ ] No orphaned records in critical tables
- [ ] Referential integrity validated
- [ ] Test data removed from production database
- [ ] Duplicate records checked and cleaned

## 34. Production Monitoring Requirements

**Rule**: Comprehensive monitoring MUST be implemented for production systems.

**Service Health Monitoring**:
- [ ] Health check endpoints for all services
- [ ] Automated health checks every 30s
- [ ] Alerts on service failure
- [ ] Service dependency graph monitored

**Application Metrics**:
- [ ] Request rate tracked
- [ ] Response time (p50, p95, p99) tracked
- [ ] Error rate tracked
- [ ] Active connections tracked
- [ ] Queue depth tracked (if using queues)

**System Monitoring**:
- [ ] CPU usage monitored
- [ ] Memory usage monitored
- [ ] Disk space monitored (alerts at 80%, 90%)
- [ ] Network I/O monitored
- [ ] IOPS monitored

**Database Monitoring**:
- [ ] Connection count monitored
- [ ] Slow queries logged and alerted
- [ ] Lock contention monitored
- [ ] Replication lag monitored (if using replication)
- [ ] Vacuum operations monitored

**Redis Monitoring**:
- [ ] Memory usage monitored
- [ ] Eviction count tracked
- [ ] Hit rate tracked
- [ ] Connection count monitored
- [ ] Slow operations logged

**Alert Rules**:
- [ ] Service down alert
- [ ] High CPU usage (> 80% for 5 min)
- [ ] High memory usage (> 85%)
- [ ] Disk space low (< 20% free)
- [ ] Database connection failures
- [ ] High error rate (> 1% of requests)
- [ ] Slow response times (p95 > 2s)
- [ ] SSL certificate expiring (< 30 days)

## 35. Backup and Recovery Standards

**Rule**: Backup and disaster recovery procedures MUST be tested and documented.

**Backup Strategy**:
- [ ] Automated daily backups configured
- [ ] Backup retention policy: 30 days minimum
- [ ] Backup location: Off-server storage
- [ ] Backup encryption enabled

**Backup Testing**:
- [ ] Backup restore tested successfully
- [ ] Recovery time objective (RTO) documented: ___ hours
- [ ] Recovery point objective (RPO) documented: ___ hours
- [ ] Backup monitoring and alerts configured

**What's Backed Up**:
- [ ] Database: Daily full backup + WAL archiving
- [ ] Docker volumes: Daily backup
- [ ] Configuration files: Version controlled in Git
- [ ] Secrets: Backed up securely (encrypted)
- [ ] User-uploaded data: S3/object storage

**DR Scenarios Tested**:
- [ ] Database failure recovery
- [ ] Service container failure recovery
- [ ] Complete server failure recovery
- [ ] Data corruption recovery
- [ ] Network outage handling

## 36. Performance Standards Enforcement

**Rule**: Performance requirements MUST be verified and maintained.

**Performance Requirements**:
- [ ] API response times acceptable (p95 < 500ms for reads)
- [ ] Load testing performed with realistic traffic
- [ ] Peak load identified and documented
- [ ] Breaking point identified
- [ ] Auto-scaling strategy defined (if needed)

**Optimization Requirements**:
- [ ] Database queries optimized
- [ ] Indexes on all foreign keys and frequently queried columns
- [ ] Connection pooling configured
- [ ] N+1 query problems resolved
- [ ] EXPLAIN ANALYZE run on critical queries

**Caching Strategy**:
- [ ] Redis caching implemented for frequently accessed data
- [ ] Cache invalidation strategy defined
- [ ] Cache hit rate monitored (target: > 80%)
- [ ] Cache warming on service startup (if needed)

**Load Test Scenarios**:
- [ ] Normal load: ___ concurrent users
- [ ] Peak load: ___ concurrent users
- [ ] Stress test: ___ concurrent users
- [ ] Spike test: Sudden ___ x increase handled

**Scaling Strategy**:
- [ ] Services stateless (can scale horizontally)
- [ ] Load balancer configured (if multi-instance)
- [ ] Session storage external (Redis)
- [ ] File uploads to object storage (not local disk)

## 37. Audit and Compliance Requirements

**Rule**: Audit trails and compliance measures MUST be implemented.

**Audit Trail**:
- [ ] All user actions logged (who, what, when)
- [ ] Trading activity audit trail
- [ ] Administrative actions logged
- [ ] Audit logs tamper-proof (append-only)
- [ ] Audit logs retained for required period

**Data Encryption**:
- [ ] Data encrypted at rest (database, backups)
- [ ] Data encrypted in transit (TLS/SSL)
- [ ] Encryption keys securely managed
- [ ] PII (Personally Identifiable Information) encrypted

**GDPR/Privacy Compliance** (if applicable):
- [ ] Privacy policy published
- [ ] User consent mechanisms in place
- [ ] Data retention policy defined
- [ ] Right to erasure implemented
- [ ] Data portability implemented

**Broker Compliance**:
- [ ] Zerodha terms of service reviewed
- [ ] API usage within rate limits
- [ ] Trading regulations compliance verified
- [ ] Audit logs for trading activities

---

# PART III: OPERATIONAL STANDARDS

## Pre-Deployment Checklist

**Security**:
- [ ] All secrets in config service (not in files)
- [ ] SSL/HTTPS configured with valid certificate
- [ ] Firewall configured (only 80, 443, 22 exposed)
- [ ] No test credentials in production
- [ ] JWT secrets secure and rotated

**Infrastructure**:
- [ ] Daily automated backups configured
- [ ] Backup restore tested
- [ ] Connection pooling configured
- [ ] Indexes on all foreign keys
- [ ] Schema migrations applied

**Monitoring**:
- [ ] Service health monitoring (all 12+ services)
- [ ] Disk space alerts (< 20% free)
- [ ] Memory alerts (> 85% usage)
- [ ] Service down alerts
- [ ] Database connection alerts

**Documentation**:
- [ ] Architecture diagram updated
- [ ] API documentation current
- [ ] Runbook for common issues
- [ ] Deployment procedure documented
- [ ] Configuration documented

**Testing**:
- [ ] Integration tests passing
- [ ] End-to-end user flows tested
- [ ] Performance benchmarks established
- [ ] Error scenarios tested

## Compliance Verification

### Pre-Commit Checklist

Before committing any code, verify:

- [ ] No hardcoded secrets or credentials
- [ ] Config service is used for all configuration
- [ ] API endpoints include version prefix
- [ ] No silent fallbacks in config reading
- [ ] Container/network names follow naming standards
- [ ] No direct JWT validation in backend services
- [ ] Frontend requests go through api-gateway only
- [ ] No duplicate API endpoints for same functionality
- [ ] Database writes only to owned schema
- [ ] Health endpoints implemented

### Architecture Review Questions

1. "Where does this configuration value come from?" → Must be config_service
2. "How is the user authenticated?" → Must be api-gateway JWT validation
3. "Can frontend call this service directly?" → Must be NO
4. "Is there another endpoint that does the same thing?" → Must be NO
5. "What happens if config_service is down?" → Must be "service doesn't start"

## Acknowledgment Statement

**For Claude sessions**, include this at the start of significant work:

> I acknowledge the StocksBlitz Architecture and Production Standards and confirm:
> 1. All configuration will come from config_service only
> 2. No hardcoded secrets or silent fallbacks
> 3. API versioning will be used for all endpoints
> 4. JWT validation happens at api-gateway only
> 5. All frontend requests route through api-gateway
> 6. One API per functionality - no gaps or overlaps
> 7. Services start via docker-compose only
> 8. Naming standards will be followed
> 9. Production security hardening requirements will be met
> 10. Monitoring and backup standards will be implemented
> 11. Only permanent fixes for all issues - no temporary fixes or workarounds
> 12. Design and implement resilient architecture

---

## Related Documents

- `STOCKSBLITZ_NAMING_STANDARDS.md` - Detailed naming conventions
- `CONFIG_SECRETS_MANAGEMENT_ARCHITECTURE.md` - Config service architecture
- `docs/prompts/API_GATEWAY_ARCHITECTURE.md` - API Gateway details
- `docs/prompts/system-overview.md` - System architecture overview
- `CLAUDE.md` - Development environment guide

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2025-12-03 | Architecture Team | Initial Architecture Principles |
| 2.0.0 | 2026-01-16 | System Integration | Merged Architecture + Production Standards |

---

**Template Version**: 2.0.0  
**Merged From**: Architecture Principles (27 principles) + Master Compliance Checklist (10 production standards)  
**Total Standards**: 37 comprehensive architectural and production requirements