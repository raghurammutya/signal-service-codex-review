# Session 5B Operational Runbooks

## Overview

This document provides operational runbooks for Session 5B cache invalidation alerts. These runbooks are directly referenced by AlertManager rules and provide step-by-step troubleshooting procedures for operators.

---

## 🚨 Critical Alerts

### `session_5b_cache_invalidation_sla_violation`

**Alert**: Cache invalidation completion exceeds 30s SLA  
**Severity**: Critical  
**SLA Impact**: Cache invalidation completion time SLA violation  

#### Immediate Response (Within 5 minutes)

1. **Verify Alert Accuracy**
   ```bash
   # Check current invalidation latency
   curl prometheus:9090/api/v1/query?query=histogram_quantile(0.95,rate(session_5b_sla_cache_invalidation_completion_seconds_bucket[5m]))
   
   # Check invalidation volume
   curl prometheus:9090/api/v1/query?query=rate(session_5b_cache_invalidation_volume_total[5m])
   ```

2. **Check Service Health**
   ```bash
   # Verify Session 5B coordinator health
   kubectl get pods -l app=signal-service -o wide
   kubectl logs -l app=signal-service --tail=100 | grep -E "(ERROR|session_5b)"
   
   # Check Redis cluster health
   kubectl get pods -l app=redis-cluster
   redis-cli --cluster check redis-cluster:6379
   ```

3. **Immediate Mitigation**
   ```bash
   # If Redis is overloaded, consider temporary selective invalidation bypass
   kubectl exec -it signal-service-pod -- python -c "
   from app.services.session_5b_sla_monitoring import get_session_5b_sla_monitor
   monitor = get_session_5b_sla_monitor()
   print('Recent violations:', monitor.get_sla_compliance_summary())
   "
   
   # Scale up Redis if needed
   kubectl scale deployment redis-cluster --replicas=6
   ```

#### Investigation Steps

**Step 1: Analyze Invalidation Patterns**
```bash
# Check invalidation volume by service
curl prometheus:9090/api/v1/query?query=rate(session_5b_cache_invalidation_volume_total[5m])

# Check selective vs full invalidation ratios
curl prometheus:9090/api/v1/query?query=rate(session_5b_cache_invalidation_volume_total{selective="true"}[5m])/rate(session_5b_cache_invalidation_volume_total[5m])

# Identify problematic patterns
kubectl logs signal-service-pod | grep "cache_invalidation_completion" | tail -20
```

**Step 2: Check Redis Performance**
```bash
# Redis latency and memory usage
redis-cli --latency-history -i 1
redis-cli info memory | grep used_memory

# Check for key evictions or memory pressure
redis-cli info stats | grep evicted_keys
redis-cli info keyspace
```

**Step 3: Review Batch Sizes**
```bash
# Check current batch configuration
kubectl exec signal-service-pod -- python -c "
from app.services.enhanced_cache_invalidation_service import get_enhanced_cache_service
service = get_enhanced_cache_service()
print(f'Batch size: {service.batch_size}')
print(f'Max concurrent: {service.max_concurrent_batches}')
"
```

#### Resolution Actions

**High Invalidation Volume**:
1. Increase Redis cluster capacity
2. Optimize batch sizes in enhanced_cache_invalidation_service.py
3. Review selective invalidation patterns for efficiency

**Redis Performance Issues**:
1. Scale Redis cluster horizontally
2. Optimize Redis configuration (maxmemory, eviction policies)
3. Consider Redis partitioning by cache type

**Code-Level Issues**:
1. Review cache pattern efficiency in CacheKeyManager
2. Optimize concurrent execution limits
3. Consider implementing cache invalidation prioritization

---

### `session_5b_stale_data_recovery_sla_violation`

**Alert**: Stale data recovery exceeds 5s SLA  
**Severity**: Critical  
**SLA Impact**: Stale data recovery time SLA violation  

#### Immediate Response (Within 2 minutes)

1. **Check Recovery Performance**
   ```bash
   # Check current stale data recovery latency
   curl prometheus:9090/api/v1/query?query=histogram_quantile(0.95,rate(session_5b_cache_recovery_latency_seconds_bucket{recovery_type="stale_data_recovery"}[5m]))
   
   # Check stale data detection rate
   curl prometheus:9090/api/v1/query?query=rate(session_5b_stale_data_detection_total[5m])
   ```

2. **Verify Calculation Engines**
   ```bash
   # Check Greeks calculation engine health
   kubectl logs signal-service-pod | grep "greeks_recalculation" | tail -10
   
   # Check indicator coordination health  
   kubectl logs signal-service-pod | grep "indicator_cache_coordination" | tail -10
   
   # Check moneyness refresh health
   kubectl logs signal-service-pod | grep "moneyness_cache_refresh" | tail -10
   ```

#### Investigation Steps

**Step 1: Identify Stale Data Sources**
```bash
# Check which services are detecting stale data
curl prometheus:9090/api/v1/query?query=increase(session_5b_stale_data_detection_total[10m])

# Check staleness severity distribution
curl prometheus:9090/api/v1/query?query=rate(session_5b_stale_data_detection_total[5m]) by (staleness_severity)
```

**Step 2: Analyze Recovery Components**
```bash
# Check calculation engine performance
kubectl exec signal-service-pod -- python -c "
from app.services.greeks_cache_manager import create_greeks_cache_manager
manager = create_greeks_cache_manager()
print('Performance stats:', manager.get_performance_stats())
"

# Check coordination performance
kubectl exec signal-service-pod -- python -c "
from app.services.session_5b_integration_coordinator import get_session_5b_coordinator
coordinator = get_session_5b_coordinator()
print('Coordination stats:', coordinator.get_coordination_statistics())
"
```

#### Resolution Actions

**Calculation Engine Performance**:
1. Scale calculation services horizontally
2. Optimize vectorized calculation batch sizes
3. Review calculation algorithm efficiency

**Cache Recovery Logic**:
1. Optimize cache warming strategies
2. Review TTL configurations for aggressive expiration
3. Consider pre-computing critical cache entries

---

### `session_5b_coordination_latency_sla_violation`

**Alert**: Coordination latency P95 exceeds 100ms SLA  
**Severity**: Critical  
**SLA Impact**: Coordination latency performance SLA violation  

#### Immediate Response (Within 3 minutes)

1. **Check Coordination Performance**
   ```bash
   # Check current coordination latency
   curl prometheus:9090/api/v1/query?query=histogram_quantile(0.95,rate(session_5b_coordination_latency_seconds_bucket[5m]))
   
   # Check service success rates
   curl prometheus:9090/api/v1/query?query=session_5b:coordination_throughput_5m
   ```

2. **Verify Service Health**
   ```bash
   # Check all cache services are responding
   kubectl exec signal-service-pod -- curl -s localhost:8080/health/session-5b
   
   # Check semaphore and concurrency limits
   kubectl logs signal-service-pod | grep "coordination" | tail -20
   ```

#### Investigation Steps

**Step 1: Analyze Coordination Bottlenecks**
```bash
# Check per-service coordination times
kubectl logs signal-service-pod | grep -E "(greeks_cache_management|indicator_cache_coordination|moneyness_cache_refresh|enhanced_cache_invalidation)" | grep "duration_ms"

# Check concurrent execution patterns
kubectl exec signal-service-pod -- python -c "
from app.services.session_5b_integration_coordinator import get_session_5b_coordinator
coordinator = get_session_5b_coordinator()
stats = coordinator.get_coordination_statistics()
print('Service performance:', stats['service_performance'])
"
```

**Step 2: Identify Slowest Components**
```bash
# Check individual service latencies
curl prometheus:9090/api/v1/query?query=avg(session_5b_coordination_latency_seconds) by (coordination_type)

# Check failure rates
curl prometheus:9090/api/v1/query?query=rate(session_5b_sla_violations_total{violation_type="coordination_latency_extreme"}[5m])
```

#### Resolution Actions

**High Coordination Latency**:
1. Increase semaphore limits for concurrent execution
2. Optimize service-specific coordination logic
3. Consider async optimization for non-critical operations

**Service Bottlenecks**:
1. Scale bottleneck services horizontally
2. Optimize individual service response times
3. Implement timeout and circuit breaker patterns

---

### `session_5b_cache_hit_rate_sla_violation`

**Alert**: Cache hit rate below 95% SLA  
**Severity**: Critical  
**SLA Impact**: Cache efficiency SLA violation  

#### Immediate Response (Within 5 minutes)

1. **Analyze Cache Performance**
   ```bash
   # Check hit rates by service and cache type
   curl prometheus:9090/api/v1/query?query=session_5b_cache_hit_rate
   
   # Check cache miss patterns
   curl prometheus:9090/api/v1/query?query=session_5b_cache_miss_ratio
   ```

2. **Check Cache Invalidation Frequency**
   ```bash
   # Check if invalidation is too aggressive
   curl prometheus:9090/api/v1/query?query=rate(session_5b_cache_invalidation_volume_total[5m])
   
   # Check selective invalidation efficiency
   curl prometheus:9090/api/v1/query?query=session_5b_selective_invalidation_efficiency
   ```

#### Resolution Actions

**Low Cache Hit Rate**:
1. Review cache TTL configurations
2. Optimize selective invalidation patterns
3. Implement cache warming strategies
4. Consider increasing Redis memory allocation

---

## 📊 Major Alerts

### `session_5b_selective_invalidation_efficiency_low`

**Alert**: Selective invalidation efficiency below 80% SLA  
**Severity**: Major  

#### Investigation Steps

```bash
# Check selective vs full invalidation patterns
curl prometheus:9090/api/v1/query?query=session_5b_selective_invalidation_efficiency by (service, trigger_type)

# Review invalidation patterns
kubectl logs signal-service-pod | grep "selective_invalidation" | tail -20
```

#### Resolution Actions

1. Review CacheKeyManager pattern efficiency
2. Optimize trigger detection logic
3. Consider more granular invalidation patterns

---

### `session_5b_cache_invalidation_volume_high`

**Alert**: Cache invalidation volume unusually high  
**Severity**: Major  

#### Investigation Steps

```bash
# Identify invalidation volume sources
curl prometheus:9090/api/v1/query?query=increase(session_5b_cache_invalidation_volume_total[5m]) by (service, invalidation_type)

# Check for invalidation cascades
kubectl logs signal-service-pod | grep "invalidation" | grep -v "DEBUG" | tail -30
```

#### Resolution Actions

1. Review market data event frequency
2. Optimize invalidation triggers
3. Consider event batching or throttling

---

## 🔧 General Troubleshooting

### Performance Degradation Analysis

1. **Check Resource Utilization**
   ```bash
   kubectl top pods -l app=signal-service
   kubectl describe node signal-service-node
   ```

2. **Review Recent Deployments**
   ```bash
   kubectl rollout history deployment/signal-service
   kubectl get events --sort-by=.metadata.creationTimestamp | tail -20
   ```

3. **Analyze Traffic Patterns**
   ```bash
   curl prometheus:9090/api/v1/query?query=rate(session_5b_coordination_latency_seconds_count[5m])
   curl prometheus:9090/api/v1/query?query=increase(session_5b_cache_invalidation_volume_total[1h])
   ```

### Emergency Procedures

**Circuit Breaker Activation**
```bash
# Activate circuit breaker for problematic service
kubectl exec signal-service-pod -- python -c "
from app.services.session_5b_integration_coordinator import get_session_5b_coordinator
coordinator = get_session_5b_coordinator()
# Manual circuit breaker activation logic here
"
```

**Selective Service Disable**
```bash
# Temporarily disable specific cache service
kubectl scale deployment specific-cache-service --replicas=0
# Update configuration to bypass disabled service
```

**Rollback Procedures**
```bash
# Rollback to previous version
kubectl rollout undo deployment/signal-service

# Verify rollback success
kubectl rollout status deployment/signal-service
curl signal-service:8080/health/session-5b
```

---

## 📞 Escalation Procedures

### Level 1 - Operations Team (0-15 minutes)
- Follow immediate response procedures
- Gather initial telemetry and logs
- Attempt standard resolution actions

### Level 2 - Engineering Team (15-30 minutes)
- Deep dive into service-specific issues
- Code-level analysis and optimization
- Coordinate with infrastructure team for scaling

### Level 3 - Architecture Team (30+ minutes)
- Fundamental design review
- Cross-service impact analysis
- Long-term optimization planning

### Emergency Contacts
- **On-Call Engineer**: `+1-XXX-XXX-XXXX`
- **Engineering Manager**: `+1-XXX-XXX-XXXX`
- **Site Reliability**: `+1-XXX-XXX-XXXX`

---

## 📚 Additional Resources

- **Session 5B Implementation Documentation**: `PHASE_3_SESSION_5B_IMPLEMENTATION_EVIDENCE.md`
- **SLA Monitoring Guide**: `session_5b_sla_monitoring.py`
- **Dashboard Links**:
  - Session 5B SLA Overview: `grafana.company.com/d/session-5b-sla`
  - Cache Performance: `grafana.company.com/d/session-5b-cache`
  - Coordination Metrics: `grafana.company.com/d/session-5b-coordination`

*Last Updated: 2026-01-26*  
*Version: 1.0*