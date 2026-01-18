# Signal Service Production Release Checklist

## 🎯 Release Process Overview

This checklist ensures a repeatable, auditable, and production-safe release process for the Signal Service. Each step includes verification criteria and rollback procedures.

## 📋 Pre-Release Checklist

### 1. Code Quality & Branch State
- [ ] **Branch Verification**: Confirm on `compliance-violations-fixed` branch
- [ ] **Working Directory**: Ensure git working directory is clean (no uncommitted changes)
- [ ] **Recent Commits**: Verify latest commits include QA pipeline and production readiness features
- [ ] **Merge Conflicts**: Resolve any merge conflicts with target branch

### 2. Development Dependencies
- [ ] **Requirements**: All `requirements-dev.txt` dependencies available
- [ ] **Test Suite**: All test files present and executable
- [ ] **Scripts**: Release automation scripts executable (`scripts/release_production.sh`)
- [ ] **Documentation**: Release notes template available (`docs/release_notes_template.md`)

## 🔍 QA Pipeline Validation

### 3. GitHub Actions Workflow Execution
- [ ] **Trigger Workflow**: Push to `compliance-violations-fixed` to trigger QA pipeline
- [ ] **Monitor Progress**: Watch all 8 stages complete successfully
  - [ ] `lint-hygiene`: Security gates, secret detection, CORS validation
  - [ ] `smoke`: Fast health validation with SLO enforcement
  - [ ] `functional-golden`: Greeks/indicators accuracy with real data
  - [ ] `integration`: Real service contract validation
  - [ ] `security`: Authentication, log redaction, hot reload controls
  - [ ] `db`: TimescaleDB + Redis integration testing
  - [ ] `hot-reload`: Config service validation with security controls
  - [ ] `performance`: Load testing with SLO compliance
  - [ ] `coverage`: ≥95% critical module coverage validation
  - [ ] `acceptance`: Release readiness summary generation

### 4. Artifact Collection & Verification
- [ ] **Download Artifacts**: Collect all GitHub Actions artifacts
  - [ ] `release-readiness-summary` 
  - [ ] `smoke-test-results`
  - [ ] `integration-test-results`
  - [ ] `security-test-results`
  - [ ] `performance-test-results`
  - [ ] `coverage-report`
  - [ ] `contract-matrix`
- [ ] **Release Readiness Score**: Verify score ≥ 95 for automatic approval
- [ ] **Executive Decision**: Confirm `RELEASE_READINESS_SUMMARY.md` states "APPROVED FOR RELEASE"
- [ ] **Critical Issues**: Ensure zero critical issues listed

## 🏷️ Release Tagging & Artifact Bundling

### 5. Automated Release Preparation
- [ ] **Run Release Script**: Execute `./scripts/release_production.sh`
- [ ] **Verify Output**: Confirm script completes without errors
- [ ] **Artifacts Bundle**: Verify `qa-validation-*.tar.gz` created with all artifacts
- [ ] **Release Metadata**: Check `RELEASE_METADATA.json` contains correct information
- [ ] **Tag Creation**: Verify annotated tag created (e.g., `v1.0.0-prod-20260118`)

### 6. Tag Management
- [ ] **Tag Verification**: Confirm tag points to correct commit SHA
- [ ] **Tag Message**: Verify annotated tag contains comprehensive release information
- [ ] **Push Tag**: `git push origin v1.0.0-prod-YYYYMMDD`
- [ ] **GitHub Verification**: Confirm tag visible on GitHub repository

## 🚀 GitHub Release Creation

### 7. Release Drafting
- [ ] **Navigate to Releases**: Go to GitHub repository releases page
- [ ] **Create New Release**: Click "Create a new release"
- [ ] **Select Tag**: Choose the production release tag
- [ ] **Release Title**: Use format "Signal Service v1.0.0-prod-YYYYMMDD"
- [ ] **Use Template**: Copy from `docs/release_notes_template.md`
- [ ] **Fill Placeholders**: Replace all `YYYYMMDD`, `XX`, `COMMIT_SHA_HERE` with actual values

### 8. Artifact Attachment
- [ ] **Upload QA Bundle**: Attach `qa-validation-*.tar.gz`
- [ ] **Upload Metadata**: Attach `RELEASE_METADATA.json`
- [ ] **Verify Checksums**: Include SHA256 checksums in release notes
- [ ] **Test Downloads**: Verify artifacts download correctly

### 9. Release Quality Verification
- [ ] **Release Notes Review**: Ensure all sections completed accurately
- [ ] **Links Verification**: Test all documentation and monitoring links
- [ ] **Executive Summary**: Verify executive summary reflects actual QA results
- [ ] **Security Notes**: Confirm security configurations documented

## 🔄 Branch Management & Protection

### 10. Merge to Main Branch
- [ ] **Create Pull Request**: `compliance-violations-fixed` → `main`
- [ ] **PR Description**: Include release readiness summary and QA results
- [ ] **Required Reviews**: Ensure branch protection rules satisfied
- [ ] **Status Checks**: Verify all required status checks pass
- [ ] **Merge Strategy**: Use "Squash and merge" or "Create merge commit" as per policy

### 11. Branch Protection Validation
- [ ] **Protection Rules**: Confirm main branch protection enabled
  - [ ] Require pull request reviews
  - [ ] Require status checks (QA workflow)
  - [ ] Require signed commits (if applicable)
  - [ ] Restrict push access
- [ ] **Status Check Requirements**: Ensure `signal-service-qa` workflow required
- [ ] **Administrative Access**: Verify only authorized users can bypass protection

## 📊 Post-Release Operations

### 12. Immediate Deployment Validation (Day 0)
- [ ] **Service Health**: Verify `/health` endpoint responds ≤ 100ms
- [ ] **Metrics Endpoint**: Confirm `/metrics` accessible ≤ 150ms
- [ ] **Config Service**: Validate connectivity to external config service
- [ ] **Database Connectivity**: Ensure TimescaleDB and Redis connections healthy
- [ ] **SLA Compliance**: Monitor first hour for SLA violations

### 13. Monitoring & Alerting Setup
- [ ] **Grafana Dashboards**: Import and verify all monitoring dashboards
- [ ] **Prometheus Alerts**: Activate SLA breach and backpressure alerts
- [ ] **On-Call Integration**: Test alert escalation procedures
- [ ] **Log Aggregation**: Verify log collection and search functionality

### 14. Day 1 Post-Deployment Review
- [ ] **24-Hour Metrics**: Review SLA compliance over full day
- [ ] **Error Rates**: Verify error rates within acceptable thresholds
- [ ] **Performance Trends**: Analyze performance degradation or improvements
- [ ] **Alert Noise**: Validate alert thresholds and reduce false positives

## 📢 Communication & Documentation

### 15. Stakeholder Notification
- [ ] **Executive Summary**: Share release readiness score and decision
- [ ] **Operations Teams**: Notify with deployment artifacts and runbooks
- [ ] **Development Teams**: Share QA results and performance baselines
- [ ] **Security Teams**: Communicate security validation results

### 16. Documentation Updates
- [ ] **Release History**: Update master release documentation
- [ ] **Operational Runbooks**: Ensure Day 0/1 procedures documented
- [ ] **Architecture Updates**: Reflect any architectural changes
- [ ] **Monitoring Guides**: Update monitoring and alerting documentation

## 🔒 Archival & Compliance

### 17. Audit Trail Preservation
- [ ] **QA Artifacts**: Archive complete QA validation bundle
- [ ] **Release Metadata**: Store release metadata with checksums
- [ ] **Deployment Logs**: Capture complete deployment execution logs
- [ ] **Approval Records**: Document all review and approval records

### 18. Compliance Documentation
- [ ] **Quality Gate Evidence**: Archive proof of all quality gate passage
- [ ] **Security Validation**: Preserve security compliance evidence
- [ ] **Performance Baselines**: Document SLA compliance proof
- [ ] **Release Decision**: Archive executive release decision rationale

## 🚨 Emergency Procedures

### 19. Rollback Preparation
- [ ] **Rollback Script**: Verify `automated_rollback.py` tested and ready
- [ ] **Previous Artifacts**: Ensure previous stable release artifacts accessible
- [ ] **Emergency Contacts**: Verify on-call and escalation procedures
- [ ] **RTO Target**: Confirm < 5 minute emergency rollback capability

### 20. Incident Response Readiness
- [ ] **Monitoring Alerts**: All critical alerts configured and tested
- [ ] **Escalation Procedures**: On-call rotation and escalation paths documented
- [ ] **Communication Channels**: Emergency communication channels tested
- [ ] **Runbook Access**: Ensure incident response runbooks accessible

## ✅ Release Completion Verification

### Final Checklist
- [ ] **GitHub Release Published**: Release visible and artifacts downloadable
- [ ] **Main Branch Updated**: PR merged and main branch reflects release
- [ ] **Production Deployment**: Service running with new release tag
- [ ] **Monitoring Active**: All dashboards and alerts operational
- [ ] **Documentation Complete**: All release documentation updated
- [ ] **Stakeholders Notified**: All relevant teams informed of release
- [ ] **Artifacts Archived**: Complete audit trail preserved

### Success Criteria
✅ **QA Pipeline**: All 8 stages passed with score ≥ 95  
✅ **Release Readiness**: Executive approval ("APPROVED FOR RELEASE")  
✅ **Deployment**: Service healthy and SLA compliant  
✅ **Monitoring**: All alerts and dashboards operational  
✅ **Documentation**: Complete audit trail and operational guides  

---

## 📋 Quick Reference Commands

```bash
# Verify current branch and status
git status

# Run release automation
./scripts/release_production.sh

# Push release tag
git push origin v1.0.0-prod-$(date +%Y%m%d)

# Create PR for main branch merge
gh pr create --title "Production Release v1.0.0-prod-$(date +%Y%m%d)" --base main

# Verify deployment health
curl -s http://localhost:8003/health | jq
```

## 🆘 Emergency Contacts

- **On-Call Engineer**: [Contact Information]
- **Release Manager**: [Contact Information]  
- **Security Team**: [Contact Information]
- **Operations Team**: [Contact Information]

---

**📋 This checklist ensures production-safe, auditable, and repeatable releases**  
**🚀 Generated by Signal Service Release Automation**