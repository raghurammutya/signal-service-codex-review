# Release Readiness Criteria

## Overview

This document defines the release readiness criteria and decision matrix for Signal Service deployments. The QA pipeline automatically generates a release readiness summary that determines go/no-go decisions for production deployments.

## Release Decision Matrix

### ✅ **APPROVED FOR RELEASE** (Readiness Score ≥95)
**Criteria**: All quality gates passed, zero critical issues
- Test success rate ≥95% 
- Critical module coverage ≥95%
- All SLOs met (health ≤100ms, metrics ≤150ms, core APIs ≤500ms, historical ≤700ms)
- All security gates passed
- Contract compliance ≥95%
- Zero critical issues

**Action**: Immediate production deployment approved

### ⚠️ **CONDITIONAL APPROVAL** (Readiness Score 85-94)
**Criteria**: Most quality gates passed, ≤1 critical issue
- Test success rate ≥90%
- Critical module coverage ≥90%
- Most SLOs met (≥4/5 endpoint classes)
- Security gates mostly passed
- Contract compliance ≥90%
- ≤1 critical issue

**Action**: Manual review required, consider phased rollout

### ❌ **NOT READY FOR RELEASE** (Readiness Score <85)
**Criteria**: Quality gates failed, >1 critical issue
- Test success rate <90%
- Critical module coverage <90%
- SLO violations
- Security failures
- Contract compliance <90%
- >1 critical issues

**Action**: Do not deploy, resolve issues and re-run QA

---

## Quality Gate Scoring

### Test Execution (25 points)
- **25 points**: 100% test success rate
- **20 points**: 95-99% success rate  
- **15 points**: 90-94% success rate
- **10 points**: 85-89% success rate
- **0 points**: <85% success rate

### Coverage Analysis (20 points)
- **20 points**: ≥95% line coverage on critical modules
- **16 points**: 90-94% coverage
- **12 points**: 85-89% coverage
- **8 points**: 80-84% coverage
- **0 points**: <80% coverage

### SLO Compliance (25 points)
- **25 points**: All SLOs met
- **20 points**: 4/5 endpoint classes meet SLOs
- **15 points**: 3/5 endpoint classes meet SLOs
- **10 points**: 2/5 endpoint classes meet SLOs
- **0 points**: <2/5 endpoint classes meet SLOs

### Security Gates (15 points)
- **15 points**: All security gates passed
- **10 points**: Minor security issues only
- **5 points**: Moderate security issues
- **0 points**: Critical security failures

### Contract Compliance (15 points)
- **15 points**: ≥95% contract compliance
- **12 points**: 90-94% compliance
- **9 points**: 85-89% compliance
- **6 points**: 80-84% compliance
- **0 points**: <80% compliance

---

## SLO Targets

### Performance SLAs (p95 latency)
- **Health endpoints**: ≤100ms, error rate ≤0.1%
- **Metrics scrape**: ≤150ms, error rate ≤0.2%  
- **Core APIs**: ≤500ms, error rate ≤0.5%
- **Historical fetch**: ≤700ms, error rate ≤1%

### Backpressure Thresholds
- **CPU**: trigger at 85% sustained >30s
- **Memory**: trigger at 85% RSS
- **Queue depth**: warn at 1,000, shed at 2,000
- **Resource pools**: 80% warn, 95% reject

---

## Security Requirements

### Zero-Tolerance Gates
- **No hardcoded secrets/API keys** in code/tests/docs
- **No external URLs** hardcoded in production code
- **CORS wildcard prevention** (*origins blocked)
- **Hot reload disabled by default** (ENABLE_HOT_RELOAD=false)
- **Authentication enforcement** on all admin endpoints

### Security Validation
- **Log redaction**: All sensitive data patterns redacted
- **Auth protection**: Unauthorized access blocked (401/403)
- **CORS configuration**: Secure origins only, no wildcards
- **Input validation**: Directory traversal blocked
- **Method restrictions**: Inappropriate HTTP methods blocked

---

## Critical Issues (Automatic NO-GO)

### Blocking Issues
- **Test failures** in smoke/security stages
- **SLO violations** exceeding thresholds by >20%
- **Security gate failures** (auth bypass, secret exposure)
- **Coverage drop** below 80% on critical modules
- **Contract failures** affecting >10% of integrations

### Non-Blocking Issues (Review Required)
- **Performance degradation** within 10% of SLO
- **Coverage drop** 90-95% on non-critical modules
- **Minor security issues** (missing headers, etc.)
- **Contract issues** affecting <5% of integrations

---

## Artifact Requirements

### Must Have (All Stages)
- **Test results** (JUnit XML format)
- **Coverage reports** (HTML + XML)
- **Contract matrix** (service integration status)
- **Performance logs** (SLO validation data)
- **Security validation** (gate pass/fail status)

### Pipeline Metadata
- **Run ID and commit SHA**
- **Branch and actor information**
- **Timestamp and environment**
- **Artifact manifest**

---

## Release Process Integration

### Automated Actions
1. **QA Pipeline** executes all 8 stages
2. **Release Readiness Summary** generated automatically
3. **Artifacts archived** with timestamped bundle
4. **Release decision** surfaced with clear GO/NO-GO

### Manual Review Points
- **Conditional approval** requires team lead sign-off
- **Security issues** require security team review
- **Performance degradation** requires architecture review
- **Contract changes** require service owner approval

### Post-Release Validation
- **Day 0/1 monitoring** per post-deploy runbook
- **SLO tracking** for 48 hours post-deployment
- **Issue correlation** with release readiness score
- **Process improvement** based on production outcomes

---

## Escalation Matrix

### GO Decision (Score ≥95)
- **Action**: Deploy immediately
- **Notification**: Standard deployment notifications
- **Monitoring**: Standard post-deploy validation

### CONDITIONAL Decision (Score 85-94)  
- **Action**: Manual review by team lead
- **Notification**: Team lead + on-call engineer
- **Monitoring**: Enhanced post-deploy monitoring

### NO-GO Decision (Score <85)
- **Action**: Block deployment, investigate issues  
- **Notification**: Team lead + engineering manager
- **Monitoring**: Full development team review

### Critical Security Issues
- **Action**: Immediate escalation to security team
- **Notification**: Security team + engineering leadership
- **Monitoring**: Security incident response procedures

---

## Continuous Improvement

### Monthly Review
- **Release readiness trends** analysis
- **Quality gate effectiveness** review  
- **SLO threshold adjustment** based on data
- **Process refinement** based on feedback

### Quarterly Assessment
- **Release criteria validation** against production outcomes
- **Quality metrics correlation** with customer impact
- **Tool and process updates** 
- **Team training and education**

**Last Updated**: 2026-01-18  
**Next Review**: 2026-02-18  
**Owner**: Engineering Team  
**Approver**: Engineering Manager