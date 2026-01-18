# Signal Service QA Pipeline Setup

## 🎯 Overview

The Signal Service now has a comprehensive 8-stage QA pipeline that automatically runs on every push and pull request, providing production-grade quality gates and release readiness analysis.

## 🔧 Pipeline Stages

### 1. **Lint & Hygiene** (`lint-hygiene`)
- Forbidden URL/secret detection
- CORS wildcard prevention
- Hot reload security validation
- Documentation redaction checks

### 2. **Smoke Tests** (`smoke`)
- Fast health and metrics validation
- SLO compliance verification (p95 ≤ 100ms health, ≤ 150ms metrics)
- Gateway authentication enforcement

### 3. **Functional Golden** (`functional-golden`)
- Greeks/indicators accuracy with real data
- Custom signals end-to-end validation
- Financial calculations correctness

### 4. **Integration Tests** (`integration`)
- Real service contract validation
- External config service integration
- Service dependency health checks
- Contract matrix generation

### 5. **Security Validation** (`security`)
- CORS and authentication enforcement
- Log redaction verification
- Hot reload authorization controls

### 6. **Database Tests** (`db`)
- TimescaleDB + Redis integration
- Database failure mode testing
- Real-service data operations

### 7. **Hot Reload Testing** (`hot-reload`)
- Config service hot reload validation
- Security controls during reload
- Rollback mechanism testing

### 8. **Performance & SLO** (`performance`)
- Load testing with SLO enforcement
- Backpressure handling validation
- Resource constraint testing

### 9. **Coverage Analysis** (`coverage`)
- ≥95% critical module coverage requirement
- Line/branch coverage validation
- Quality gate enforcement

### 10. **Release Readiness** (`acceptance`)
- Executive decision summary generation
- GO/CONDITIONAL/NO-GO recommendations
- Comprehensive artifact collection

## 📊 SLO Targets

### Performance SLAs (p95 latency)
- **Health endpoints**: ≤100ms, error rate ≤0.1%
- **Metrics scrape**: ≤150ms, error rate ≤0.2%  
- **Core APIs**: ≤500ms, error rate ≤0.5%
- **Historical fetch**: ≤700ms, error rate ≤1%

### Quality Gates
- **Test Success Rate**: ≥95%
- **Critical Module Coverage**: ≥95%
- **Security Gates**: All must pass
- **Contract Compliance**: ≥95%

## 🚀 GitHub Secrets Setup

Before the pipeline can run, configure these GitHub repository secrets:

```bash
# Required secrets in GitHub repository settings
CONFIG_SERVICE_URL=http://localhost:8100    # Config service endpoint
INTERNAL_API_KEY=AShhRzWhfXd6IomyzZnE3d...  # Service-to-service auth key
```

## 📋 Usage

### Automatic Execution
The pipeline runs automatically on:
- **Every push** to any branch
- **Every pull request** creation/update
- **Release branch** commits

### Manual Execution
You can also trigger the workflow manually from the GitHub Actions tab.

### Nightly Runs (Optional)
To add scheduled nightly validation, add this to the workflow triggers:

```yaml
on:
  push:
  pull_request:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC
```

## 📈 Release Decision Matrix

### ✅ **APPROVED FOR RELEASE** (Score ≥95)
- All quality gates passed
- Zero critical issues
- Immediate production deployment approved

### ⚠️ **CONDITIONAL APPROVAL** (Score 85-94)  
- Most quality gates passed
- ≤1 critical issue
- Manual review required

### ❌ **NOT READY FOR RELEASE** (Score <85)
- Quality gates failed
- >1 critical issues
- Do not deploy, resolve issues first

## 🔍 Artifacts & Reports

Each pipeline run generates:
- **Test results** (JUnit XML)
- **Coverage reports** (HTML + XML)
- **Contract matrix** (service integration status)
- **Performance logs** (SLO validation data)
- **Release readiness summary** (executive decision)
- **Pipeline metadata** (traceability)

## 🚨 Troubleshooting

### Common Issues

1. **Missing test files**: Pipeline expects test files in standard locations
2. **Service dependencies**: Some tests require real services running
3. **Secrets not configured**: Check GitHub repository secrets
4. **Performance SLA failures**: Adjust load or investigate bottlenecks

### Pipeline Debugging
- Check individual stage logs in GitHub Actions
- Download artifacts for detailed analysis
- Review release readiness summary for specific failures

## 📚 Documentation

- [Release Readiness Criteria](./docs/RELEASE_READINESS_CRITERIA.md)
- [Day 0/1 Operations](./DAY_0_1_OPERATIONS_CHECKLIST.md)
- [Performance Test Details](./tests/performance/test_load_backpressure.py)

## 🎯 Next Steps

1. **Verify pipeline execution** after first push
2. **Add missing test files** if needed
3. **Configure repository secrets** for external services
4. **Review initial release readiness score**
5. **Set up notifications** for pipeline failures

The QA pipeline is now active and will validate every code change against production-grade quality standards!