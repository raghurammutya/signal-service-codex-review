# Signal Service V2 Deployment Checklist

## Pre-Deployment Phase

### Code Readiness
- [ ] All features implemented and tested
- [ ] Code review completed
- [ ] Unit tests passing (>90% coverage)
- [ ] Integration tests passing
- [ ] Performance benchmarks met
- [ ] Security scan completed
- [ ] No critical/high vulnerabilities

### Documentation
- [ ] API documentation updated
- [ ] Architecture diagrams current
- [ ] Runbook created
- [ ] Migration guide published
- [ ] Release notes prepared

### Infrastructure Preparation
- [ ] Kubernetes cluster capacity verified
- [ ] Database migrations tested
- [ ] Redis cluster ready
- [ ] Monitoring dashboards created
- [ ] Alert rules configured
- [ ] Backup procedures verified

### Dependencies
- [ ] Instrument service integration tested
- [ ] Ticker service compatibility verified
- [ ] Subscription service quotas configured
- [ ] Network policies updated
- [ ] Service mesh configuration ready

---

## Deployment Phase

### Step 1: Database Migration (30 minutes)
- [ ] **Backup current database**
  ```bash
  pg_dump -h timescaledb-host -U signal_user -d signal_db > backup_$(date +%Y%m%d_%H%M%S).sql
  ```

- [ ] **Run migration scripts**
  ```bash
  alembic upgrade head
  ```

- [ ] **Verify new tables created**
  ```sql
  SELECT table_name FROM information_schema.tables 
  WHERE table_schema = 'public' 
  AND table_name LIKE 'signal_%';
  ```

- [ ] **Create indexes**
  ```bash
  psql -h timescaledb-host -U signal_user -d signal_db -f create_indexes.sql
  ```

- [ ] **Verify TimescaleDB hypertables**
  ```sql
  SELECT * FROM timescaledb_information.hypertables;
  ```

### Step 2: Configuration Updates (15 minutes)
- [ ] **Update ConfigMaps**
  ```bash
  kubectl apply -f k8s/configmaps/signal-service-config.yaml
  ```

- [ ] **Update Secrets**
  ```bash
  kubectl apply -f k8s/secrets/signal-service-secrets.yaml
  ```

- [ ] **Verify environment variables**
  ```bash
  kubectl describe configmap signal-service-config
  ```

### Step 3: Blue-Green Deployment (45 minutes)
- [ ] **Deploy new version (green)**
  ```bash
  kubectl apply -f k8s/deployments/signal-service-v2-green.yaml
  ```

- [ ] **Wait for pods to be ready**
  ```bash
  kubectl wait --for=condition=ready pod -l app=signal-service,version=v2
  ```

- [ ] **Run smoke tests**
  ```bash
  ./scripts/smoke_tests.sh https://signal-service-green/api/v2
  ```

- [ ] **Route 10% traffic to green**
  ```bash
  kubectl apply -f k8s/virtualservice/signal-service-canary-10.yaml
  ```

- [ ] **Monitor metrics (15 minutes)**
  - [ ] Error rate < 0.1%
  - [ ] Latency p99 < 200ms
  - [ ] CPU usage < 70%
  - [ ] Memory usage < 80%

- [ ] **Route 50% traffic**
  ```bash
  kubectl apply -f k8s/virtualservice/signal-service-canary-50.yaml
  ```

- [ ] **Monitor metrics (15 minutes)**

- [ ] **Route 100% traffic**
  ```bash
  kubectl apply -f k8s/virtualservice/signal-service-canary-100.yaml
  ```

### Step 4: Post-Deployment Verification (30 minutes)
- [ ] **API Health Checks**
  ```bash
  curl https://signal-service/health
  curl https://signal-service/api/v2/status
  ```

- [ ] **Test real-time endpoints**
  ```bash
  # Test Greeks calculation
  curl https://signal-service/api/v2/realtime/greeks/NSE@NIFTY@OPTION@21500@CALL
  
  # Test moneyness endpoint
  curl https://signal-service/api/v2/realtime/moneyness/NIFTY/greeks/ATM
  ```

- [ ] **Test historical endpoints**
  ```bash
  curl "https://signal-service/api/v2/historical/greeks/NSE@NIFTY@OPTION@21500@CALL?from=2024-01-01&to=2024-01-07"
  ```

- [ ] **WebSocket connectivity**
  ```bash
  wscat -c wss://signal-service/api/v2/subscriptions/websocket
  ```

- [ ] **Performance validation**
  ```bash
  k6 run scripts/load_test.js
  ```

### Step 5: Cleanup (15 minutes)
- [ ] **Remove old deployment**
  ```bash
  kubectl delete deployment signal-service-v1
  ```

- [ ] **Update DNS/Service**
  ```bash
  kubectl patch service signal-service -p '{"spec":{"selector":{"version":"v2"}}}'
  ```

- [ ] **Clean up old ConfigMaps**
  ```bash
  kubectl delete configmap signal-service-config-v1
  ```

---

## Rollback Procedures

### Immediate Rollback (5 minutes)
```bash
# Route traffic back to v1
kubectl apply -f k8s/virtualservice/signal-service-v1-only.yaml

# Scale down v2
kubectl scale deployment signal-service-v2 --replicas=0
```

### Database Rollback
```bash
# Only if schema changes are incompatible
alembic downgrade -1

# Restore from backup if needed
psql -h timescaledb-host -U signal_user -d signal_db < backup_YYYYMMDD_HHMMSS.sql
```

### Configuration Rollback
```bash
# Revert ConfigMaps
kubectl apply -f k8s/configmaps/signal-service-config-v1-backup.yaml

# Restart pods
kubectl rollout restart deployment signal-service-v1
```

---

## Monitoring Checklist

### Dashboards to Monitor
- [ ] **Service Overview Dashboard**
  - Request rate
  - Error rate
  - Latency percentiles
  - Active connections

- [ ] **Performance Dashboard**
  - Greeks calculation time
  - Cache hit rates
  - Database query performance
  - Memory usage

- [ ] **Business Metrics Dashboard**
  - Computations per second
  - Active subscriptions
  - Moneyness queries
  - User activity

### Key Alerts to Watch
- [ ] High error rate (>1%)
- [ ] High latency (p99 > 500ms)
- [ ] Pod restarts
- [ ] Database connection failures
- [ ] Redis connection issues
- [ ] Memory pressure
- [ ] Disk space warnings

### Log Queries
```sql
-- Error analysis
SELECT timestamp, error_type, count(*) 
FROM logs 
WHERE service='signal-service' 
  AND level='ERROR' 
  AND timestamp > NOW() - INTERVAL '1 hour'
GROUP BY timestamp, error_type;

-- Performance analysis
SELECT endpoint, percentile_disc(0.99) WITHIN GROUP (ORDER BY duration)
FROM api_requests
WHERE service='signal-service'
  AND timestamp > NOW() - INTERVAL '1 hour'
GROUP BY endpoint;
```

---

## Communication Plan

### Pre-Deployment
- [ ] **T-24h**: Send deployment notification to stakeholders
- [ ] **T-2h**: Send reminder with maintenance window
- [ ] **T-30m**: Post in #platform-status channel

### During Deployment
- [ ] **Start**: Post deployment start in #platform-status
- [ ] **Milestones**: Update on major steps completed
- [ ] **Issues**: Immediate notification of any problems

### Post-Deployment
- [ ] **Completion**: Announce successful deployment
- [ ] **Metrics**: Share performance improvements
- [ ] **Documentation**: Share updated API docs link

### Stakeholder Notifications
```
Subject: Signal Service V2 Deployment Complete

The Signal Service has been successfully upgraded to V2.

New Features:
✓ Moneyness-based Greeks (ATM IV, OTM5delta)
✓ Custom timeframe support (any minute interval)
✓ WebSocket streaming for real-time updates
✓ Enhanced historical data API
✓ 50% performance improvement

API Documentation: https://docs.platform.com/signal-service/v2
Migration Guide: https://docs.platform.com/signal-service/migration

Please report any issues to #platform-support
```

---

## Success Criteria

### Technical Metrics
- [ ] All health checks passing
- [ ] Error rate < 0.1%
- [ ] API latency p99 < 200ms
- [ ] WebSocket latency < 50ms
- [ ] Cache hit rate > 80%
- [ ] No memory leaks detected

### Business Metrics
- [ ] All existing integrations working
- [ ] No user-reported issues
- [ ] Performance SLAs met
- [ ] Successful moneyness calculations
- [ ] Custom timeframes working

### Sign-off Required
- [ ] DevOps Lead
- [ ] Service Owner
- [ ] QA Lead
- [ ] Product Manager
- [ ] Security Team

---

## Post-Deployment Tasks

### Day 1
- [ ] Monitor metrics closely
- [ ] Review error logs
- [ ] Gather user feedback
- [ ] Update documentation based on feedback

### Week 1
- [ ] Performance tuning based on real load
- [ ] Optimize cache settings
- [ ] Review resource utilization
- [ ] Plan optimization sprint

### Month 1
- [ ] Analyze usage patterns
- [ ] Plan next enhancements
- [ ] Update capacity planning
- [ ] Conduct retrospective

---

## Emergency Contacts

| Role | Name | Contact |
|------|------|---------|
| Service Owner | TBD | email/phone |
| DevOps Lead | TBD | email/phone |
| Database Admin | TBD | email/phone |
| Security Lead | TBD | email/phone |
| Product Manager | TBD | email/phone |

## Useful Commands

```bash
# View logs
kubectl logs -f -l app=signal-service --tail=100

# Check pod status
kubectl get pods -l app=signal-service -o wide

# Describe pod
kubectl describe pod <pod-name>

# Execute into pod
kubectl exec -it <pod-name> -- /bin/bash

# Check service endpoints
kubectl get endpoints signal-service

# View horizontal pod autoscaler
kubectl get hpa signal-service-hpa

# Check resource usage
kubectl top pods -l app=signal-service
```

---

## Deployment Log

| Time | Action | Status | Notes |
|------|--------|---------|--------|
| | Start deployment | | |
| | Database migration | | |
| | Deploy green | | |
| | Route 10% traffic | | |
| | Route 50% traffic | | |
| | Route 100% traffic | | |
| | Remove blue | | |
| | Deployment complete | | |

---

## Document Control
- **Version**: 1.0
- **Created**: 2024-01-07
- **Last Updated**: 2024-01-07
- **Next Review**: Before next deployment