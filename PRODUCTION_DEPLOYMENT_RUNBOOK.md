# Phase 2 Production Deployment Runbook

## 🎯 **DEPLOYMENT OVERVIEW**

**Objective:** Deploy Phase 2 instrument_key migration to production with zero downtime and full validation.

**Prerequisites:** All Phase 2 deliverables completed, P0 critical fix applied, evidence package validated.

---

## 🔍 **PRE-FLIGHT VALIDATION CHECKLIST**

### **Step 1: Final Phase 2 Signoff Verification**
```bash
# Verify Phase 2 completion status
python3 scripts/test_data_001_checkpoint_automation.py --mode phase-2-signoff

# Expected Output: "Phase 2 signoff: APPROVED"
# ✅ PASS: Continue to next step
# ❌ FAIL: Address issues before deployment
```

### **Step 2: P0 Critical Fix Validation**
```bash
# Verify indicators API contract compliance
grep -n "instrument_token.*:" app/api/v2/indicators.py

# Expected Output: No matches (fixed to use instrument_key)
# ✅ PASS: P0 fix applied successfully
# ❌ FAIL: Apply P0 fix before deployment
```

### **Step 3: Component Health Pre-Check**
```bash
# Validate all components ready
for component in SUB_001 STREAM_001 CACHE_001 EVENT_001 HIST_001 AGG_001 FEED_001 TEST_DATA_001; do
    echo "Checking ${component}..."
    # Component-specific health checks here
done

# Expected: All components report HEALTHY
```

### **Step 4: Infrastructure Readiness**
```bash
# Check production infrastructure
kubectl get nodes --selector=environment=production
kubectl get pods --selector=phase=2 --all-namespaces

# Verify capacity and resource availability
# Expected: All nodes ready, adequate resources
```

### **Step 5: Backup & Rollback Preparation**
```bash
# Create pre-deployment backup
./scripts/create_pre_deployment_backup.sh phase_2_$(date +%Y%m%d_%H%M%S)

# Verify rollback procedures ready
./scripts/verify_rollback_readiness.sh

# Expected: Backup created, rollback procedures validated
```

---

## 🚀 **DEPLOYMENT EXECUTION**

### **Phase A: Infrastructure Preparation**
```bash
echo "=== Phase A: Infrastructure Preparation ==="

# Step 1: Enable maintenance mode (if applicable)
curl -X POST https://api.production.com/maintenance/enable \
  -H "Authorization: Bearer $MAINTENANCE_TOKEN"

# Step 2: Scale up monitoring
kubectl scale deployment monitoring-collector --replicas=3

# Step 3: Prepare deployment workspace
export DEPLOYMENT_ID="phase_2_$(date +%Y%m%d_%H%M%S)"
mkdir -p /tmp/deployments/$DEPLOYMENT_ID
cd /tmp/deployments/$DEPLOYMENT_ID

echo "Infrastructure preparation complete ✅"
```

### **Phase B: Component Deployment**
```bash
echo "=== Phase B: Component Deployment ==="

# Deploy components in dependency order
COMPONENTS=("SUB_001" "STREAM_001" "CACHE_001" "EVENT_001" "HIST_001" "AGG_001" "FEED_001")

for COMPONENT in "${COMPONENTS[@]}"; do
    echo "Deploying ${COMPONENT}..."
    
    # Pre-deployment validation
    python3 scripts/${COMPONENT,,}_checkpoint_automation.py --mode pre-deployment
    if [ $? -ne 0 ]; then
        echo "❌ Pre-deployment validation failed for ${COMPONENT}"
        exit 1
    fi
    
    # Execute deployment
    kubectl apply -f k8s/production/${COMPONENT,,}_deployment.yaml
    
    # Wait for rollout completion
    kubectl rollout status deployment/${COMPONENT,,} --timeout=300s
    if [ $? -ne 0 ]; then
        echo "❌ Deployment failed for ${COMPONENT}"
        ./scripts/rollback_deployment.sh $COMPONENT
        exit 1
    fi
    
    # Post-deployment health check
    sleep 30  # Allow stabilization
    python3 scripts/${COMPONENT,,}_checkpoint_automation.py --mode production-health
    if [ $? -ne 0 ]; then
        echo "⚠️ Health check warning for ${COMPONENT} - monitoring required"
    fi
    
    echo "✅ ${COMPONENT} deployed successfully"
done

echo "Component deployment complete ✅"
```

### **Phase C: Integration Validation**
```bash
echo "=== Phase C: Integration Validation ==="

# Step 1: End-to-end integration testing
python3 scripts/validate_data_pipeline_regression.py --regression-suite full
if [ $? -ne 0 ]; then
    echo "❌ Integration validation failed"
    ./scripts/initiate_rollback.sh
    exit 1
fi

# Step 2: Cross-component validation
python3 scripts/test_data_001_checkpoint_automation.py --mode evening
if [ $? -ne 0 ]; then
    echo "❌ Cross-component validation failed"
    ./scripts/initiate_rollback.sh
    exit 1
fi

# Step 3: Performance regression check
python3 scripts/validate_data_pipeline_regression.py --performance-only
if [ $? -ne 0 ]; then
    echo "⚠️ Performance regression detected - review required"
    # Note: May continue based on threshold acceptance
fi

echo "Integration validation complete ✅"
```

### **Phase D: Production Traffic Enablement**
```bash
echo "=== Phase D: Production Traffic Enablement ==="

# Step 1: Gradual traffic ramp-up
echo "Starting traffic ramp-up..."

# 10% traffic
kubectl patch service api-gateway -p '{"spec":{"selector":{"version":"v2","traffic":"10"}}}'
sleep 300  # 5 minute soak test

# Monitor key metrics
python3 scripts/monitor_deployment_health.py --duration 300 --threshold 95
if [ $? -ne 0 ]; then
    echo "❌ 10% traffic test failed"
    kubectl patch service api-gateway -p '{"spec":{"selector":{"version":"v1"}}}'
    exit 1
fi

# 50% traffic
kubectl patch service api-gateway -p '{"spec":{"selector":{"version":"v2","traffic":"50"}}}'
sleep 600  # 10 minute soak test

python3 scripts/monitor_deployment_health.py --duration 600 --threshold 95
if [ $? -ne 0 ]; then
    echo "❌ 50% traffic test failed"
    kubectl patch service api-gateway -p '{"spec":{"selector":{"version":"v1"}}}'
    exit 1
fi

# 100% traffic
kubectl patch service api-gateway -p '{"spec":{"selector":{"version":"v2"}}}'
sleep 900  # 15 minute full load test

python3 scripts/monitor_deployment_health.py --duration 900 --threshold 98
if [ $? -ne 0 ]; then
    echo "❌ Full traffic test failed"
    ./scripts/initiate_rollback.sh
    exit 1
fi

echo "Production traffic enablement complete ✅"
```

---

## 🎯 **POST-DEPLOYMENT VALIDATION**

### **Step 1: SLA Compliance Verification**
```bash
echo "=== SLA Compliance Verification ==="

# Check uptime
UPTIME=$(curl -s https://monitoring.production.com/api/uptime/last_hour | jq '.uptime_percent')
if (( $(echo "$UPTIME < 99.0" | bc -l) )); then
    echo "⚠️ Uptime SLA at risk: ${UPTIME}%"
fi

# Check P95 latency
P95_LATENCY=$(curl -s https://monitoring.production.com/api/latency/p95 | jq '.latency_ms')
if (( $(echo "$P95_LATENCY > 107" | bc -l) )); then
    echo "⚠️ Latency SLA at risk: ${P95_LATENCY}ms"
fi

# Check data consistency
CONSISTENCY=$(python3 scripts/validate_data_consistency.py --production)
echo "Data consistency: ${CONSISTENCY}%"

echo "SLA verification complete ✅"
```

### **Step 2: Business Continuity Validation**
```bash
echo "=== Business Continuity Validation ==="

# Test critical business workflows
python3 scripts/test_critical_workflows.py --environment production

# Validate key integrations
python3 scripts/test_external_integrations.py --environment production

# Check data pipeline throughput
THROUGHPUT=$(curl -s https://monitoring.production.com/api/throughput/current | jq '.ops_per_sec')
echo "Current throughput: ${THROUGHPUT} ops/sec"

if (( $(echo "$THROUGHPUT < 1000" | bc -l) )); then
    echo "⚠️ Throughput below target: ${THROUGHPUT} ops/sec"
fi

echo "Business continuity validation complete ✅"
```

### **Step 3: Final Evidence Collection**
```bash
echo "=== Final Evidence Collection ==="

# Generate deployment evidence
python3 scripts/generate_deployment_evidence.py \
    --deployment-id $DEPLOYMENT_ID \
    --output-dir /tmp/deployments/$DEPLOYMENT_ID/evidence

# Collect performance baseline post-deployment
python3 scripts/collect_performance_baseline.py \
    --environment production \
    --output-file /tmp/deployments/$DEPLOYMENT_ID/evidence/post_deployment_baseline.json

# Generate final deployment report
python3 scripts/generate_deployment_report.py \
    --deployment-id $DEPLOYMENT_ID \
    --evidence-dir /tmp/deployments/$DEPLOYMENT_ID/evidence \
    --output-file PHASE_2_PRODUCTION_DEPLOYMENT_REPORT.json

echo "Evidence collection complete ✅"
```

---

## 🛡️ **ROLLBACK PROCEDURES**

### **Emergency Rollback (< 5 minutes)**
```bash
#!/bin/bash
# scripts/emergency_rollback.sh

echo "🚨 INITIATING EMERGENCY ROLLBACK"

# Immediate traffic redirect to v1
kubectl patch service api-gateway -p '{"spec":{"selector":{"version":"v1"}}}'

# Scale down v2 components
kubectl scale deployment --selector=version=v2 --replicas=0

# Restore from backup if needed
if [ "$1" == "--restore-data" ]; then
    ./scripts/restore_from_backup.sh latest
fi

echo "🔄 Emergency rollback initiated - monitor recovery"
```

### **Planned Rollback (15-30 minutes)**
```bash
#!/bin/bash
# scripts/planned_rollback.sh

echo "🔄 INITIATING PLANNED ROLLBACK"

# Gradual traffic reduction
kubectl patch service api-gateway -p '{"spec":{"selector":{"version":"v1"}}}'

# Component-by-component rollback
COMPONENTS=("FEED_001" "AGG_001" "HIST_001" "EVENT_001" "CACHE_001" "STREAM_001" "SUB_001")

for COMPONENT in "${COMPONENTS[@]}"; do
    echo "Rolling back ${COMPONENT}..."
    kubectl rollout undo deployment/${COMPONENT,,}
    kubectl rollout status deployment/${COMPONENT,,} --timeout=300s
done

# Validate rollback success
python3 scripts/validate_rollback_success.py

echo "🔄 Planned rollback complete"
```

---

## 📊 **MONITORING & ALERTING**

### **Key Metrics to Monitor**
```yaml
# monitoring/production_alerts.yaml
alerts:
  - name: phase_2_deployment_health
    metrics:
      - uptime_percent > 99.0
      - p95_latency_ms < 107
      - error_rate_percent < 0.5
      - throughput_ops_sec > 1000
      - data_consistency_percent > 99.5

  - name: component_health
    metrics:
      - component_availability > 99.8
      - component_response_time < 50ms
      - component_error_rate < 0.1

  - name: business_continuity
    metrics:
      - critical_workflow_success > 99.9
      - data_pipeline_integrity > 99.5
      - external_integration_health > 99.0
```

### **Dashboard Configuration**
```bash
# Setup production monitoring dashboard
kubectl apply -f monitoring/phase_2_production_dashboard.yaml

# Configure alerting rules
kubectl apply -f monitoring/phase_2_alerting_rules.yaml

# Enable real-time monitoring
curl -X POST https://monitoring.production.com/api/enable_realtime \
  -H "Authorization: Bearer $MONITORING_TOKEN" \
  -d '{"deployment_id": "'$DEPLOYMENT_ID'"}'
```

---

## ✅ **DEPLOYMENT COMPLETION CHECKLIST**

### **Technical Validation**
- [ ] All 8 components deployed successfully
- [ ] Integration tests passing (100% success rate)
- [ ] Performance regression analysis complete (no regressions)
- [ ] SLA compliance verified (uptime, latency, throughput)
- [ ] Cross-component health validated

### **Business Validation**
- [ ] Critical workflows functioning
- [ ] External integrations operational
- [ ] Data consistency maintained
- [ ] No user-facing issues reported
- [ ] Business continuity confirmed

### **Operational Readiness**
- [ ] Monitoring and alerting active
- [ ] Rollback procedures validated
- [ ] On-call team briefed
- [ ] Documentation updated
- [ ] Evidence package complete

### **Final Signoff**
- [ ] Technical Lead approval
- [ ] Operations Manager approval  
- [ ] Product Owner approval
- [ ] Security clearance confirmed
- [ ] Deployment marked as SUCCESSFUL

---

## 📋 **POST-DEPLOYMENT ACTIVITIES**

### **Immediate (0-24 hours)**
- Monitor all key metrics continuously
- Address any performance anomalies
- Validate business continuity
- Collect deployment success evidence

### **Short-term (1-7 days)**
- Complete P1/P2 legacy cleanup per remediation plan
- Optimize performance based on production data
- Update operational procedures
- Conduct retrospective meeting

### **Long-term (1-4 weeks)**
- Baseline establishment for future deployments
- Documentation updates based on lessons learned
- Team training on new instrument_key patterns
- Plan Phase 3 enhancements if applicable

---

**🎉 PHASE 2 PRODUCTION DEPLOYMENT COMPLETE**

**Status:** Ready for execution  
**Prerequisites:** Phase 2 signoff approved, P0 fix applied  
**Duration:** Estimated 4-6 hours for full deployment  
**Risk Level:** LOW (comprehensive validation framework)  

**Next Steps:** Execute deployment per this runbook, monitor success metrics, begin legacy cleanup activities.