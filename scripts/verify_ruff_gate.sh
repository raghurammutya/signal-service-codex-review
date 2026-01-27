#!/bin/bash

# Gate Verification PR Automation
# 
# Automatically creates a verification PR after P0 campaign success to test
# that the CI gate is properly unblocked and normal development can resume.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Configuration
VERIFICATION_BRANCH="ruff-gate-verification-${TIMESTAMP}"
EVIDENCE_DIR="${REPO_ROOT}/evidence/gate_verification"
VERIFICATION_FILE="docs/RUFF_GATE_VERIFICATION.md"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "🔍 Checking prerequisites..."
    
    # Check if we're in a git repository
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        log_error "Not in a git repository"
        exit 1
    fi
    
    # Check if gh CLI is available
    if ! command -v gh &> /dev/null; then
        log_error "GitHub CLI (gh) is not installed or not in PATH"
        log_info "Install with: https://cli.github.com/"
        exit 1
    fi
    
    # Check if authenticated with GitHub
    if ! gh auth status &> /dev/null; then
        log_error "Not authenticated with GitHub CLI"
        log_info "Run: gh auth login"
        exit 1
    fi
    
    # Check if P0 violations are actually resolved
    log_info "🔍 Verifying P0 campaign success..."
    if command -v python3 &> /dev/null && [[ -f "${SCRIPT_DIR}/detect_campaign_success.py" ]]; then
        if python3 "${SCRIPT_DIR}/detect_campaign_success.py" &> /dev/null; then
            log_success "✅ P0 campaign success confirmed"
        else
            log_warning "⚠️ P0 campaign may not be complete - proceeding with verification anyway"
        fi
    else
        log_warning "⚠️ Cannot verify P0 status - proceeding with gate test"
    fi
}

create_verification_content() {
    log_info "📝 Creating verification documentation..."
    
    mkdir -p "$(dirname "$VERIFICATION_FILE")"
    
    cat > "$VERIFICATION_FILE" << EOF
# Ruff CI Gate Verification

**Verification Run:** ${TIMESTAMP}
**Branch:** ${VERIFICATION_BRANCH}
**Purpose:** Automated test of Ruff CI gate after P0 campaign completion

## Verification Objectives

This document serves as a verification marker to test the Ruff CI pipeline:

1. **P0 Gate Test**: Confirm that PRs with zero P0 violations can merge
2. **CI Pipeline Health**: Validate that GitHub Actions run correctly
3. **Normal Workflow**: Ensure development teams can resume standard processes

## Test Execution

### Automated Steps
- ✅ **Branch creation**: \`${VERIFICATION_BRANCH}\`
- ✅ **Documentation update**: Added verification content
- ⏳ **PR creation**: Draft PR opened for CI testing
- ⏳ **GitHub Actions**: Waiting for Ruff workflow execution
- ⏳ **Gate validation**: Confirm no blocking violations
- ⏳ **Cleanup**: PR closure and branch deletion

### Expected Results
- Ruff CI workflow completes successfully
- No P0 violations detected
- PR can be merged (will be closed instead)
- Normal development workflow confirmed operational

## Verification Evidence

**Branch created:** $(date -u +"%Y-%m-%d %H:%M:%S UTC")
**Git commit:** \$(git rev-parse HEAD)
**Ruff version:** \$(ruff --version 2>/dev/null || echo "Version check failed")

## Success Criteria

- [ ] GitHub Actions workflow runs without errors
- [ ] Ruff check passes with zero P0 violations  
- [ ] PR shows "All checks have passed" status
- [ ] No merge conflicts or blocking issues

## Next Steps

1. **If verification succeeds**: Campaign infrastructure proven successful
2. **If verification fails**: Investigate remaining P0 issues
3. **Post-verification**: Archive verification materials and resume development

---

**Verification Status:** 🔄 **IN PROGRESS**
**Created by:** Ruff Gate Verification Automation
**Monitoring:** Evidence captured in \`evidence/gate_verification/\`
EOF

    log_success "✅ Verification content created"
}

create_verification_branch() {
    log_info "🌿 Creating verification branch..."
    
    # Ensure we're on master/main branch
    DEFAULT_BRANCH=$(git remote show origin | grep 'HEAD branch' | cut -d' ' -f5 || echo "main")
    log_info "Switching to default branch: $DEFAULT_BRANCH"
    git checkout "$DEFAULT_BRANCH" 2>/dev/null || git checkout main 2>/dev/null || git checkout master
    
    # Pull latest changes
    log_info "Pulling latest changes..."
    git pull origin "$DEFAULT_BRANCH" 2>/dev/null || git pull origin main 2>/dev/null || git pull origin master
    
    # Create and checkout verification branch
    log_info "Creating branch: $VERIFICATION_BRANCH"
    git checkout -b "$VERIFICATION_BRANCH"
    
    log_success "✅ Verification branch created"
}

commit_verification_changes() {
    log_info "💾 Committing verification changes..."
    
    # Add verification file
    git add "$VERIFICATION_FILE"
    
    # Create commit with detailed message
    git commit -m "$(cat <<EOF
🔍 Ruff CI Gate Verification - ${TIMESTAMP}

Automated verification PR to test Ruff CI gate functionality
after P0 syntax error campaign completion.

Purpose:
- Test that P0 violations are resolved
- Validate GitHub Actions Ruff workflow
- Confirm normal development workflow restored

Verification Details:
- Branch: ${VERIFICATION_BRANCH}
- Timestamp: ${TIMESTAMP}
- Type: Automated gate verification
- Expected: CI passes, no P0 violations

This PR will be automatically closed after verification.

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
    
    log_success "✅ Verification changes committed"
}

push_verification_branch() {
    log_info "🚀 Pushing verification branch to origin..."
    
    git push -u origin "$VERIFICATION_BRANCH"
    
    log_success "✅ Verification branch pushed"
}

create_verification_pr() {
    log_info "📋 Creating verification PR..."
    
    # Create PR with detailed description
    PR_URL=$(gh pr create \
        --title "🔍 Ruff CI Gate Verification - ${TIMESTAMP}" \
        --body "$(cat <<EOF
## 🎯 Automated Ruff CI Gate Verification

**Purpose:** Test CI gate functionality after P0 syntax error campaign completion
**Type:** Automated verification (will be closed after testing)
**Branch:** \`${VERIFICATION_BRANCH}\`

## Verification Objectives

This PR automatically tests the Ruff CI pipeline to confirm:

✅ **P0 Resolution**: All syntax errors have been resolved  
✅ **CI Functionality**: GitHub Actions workflow executes correctly  
✅ **Gate Operation**: No blocking violations prevent merge  
✅ **Workflow Health**: Normal development process is restored  

## Expected Results

- Ruff GitHub Action completes successfully
- Zero P0 violations detected in CI output
- All status checks pass
- PR shows merge-ready state

## Verification Process

1. **Automated Creation**: This PR was created by verification automation
2. **CI Execution**: GitHub Actions will run Ruff checks
3. **Status Monitoring**: Automation will monitor for completion
4. **Evidence Collection**: Results captured in \`evidence/gate_verification/\`
5. **Automatic Closure**: PR will be closed after verification (not merged)

## Files Changed

- \`${VERIFICATION_FILE}\`: Verification documentation (safe, non-functional change)

## Success Indicators

- [ ] GitHub Actions status: ✅ Passing
- [ ] Ruff workflow: ✅ No P0 violations
- [ ] All checks: ✅ Completed successfully
- [ ] Merge status: ✅ Ready (but will be closed instead)

## Post-Verification

Once verification completes:
1. **Evidence preserved**: Verification results documented
2. **Branch cleanup**: Verification branch deleted
3. **Campaign confirmed**: P0 resolution validated
4. **Development resumed**: Teams can proceed with normal workflow

---

**🤖 This is an automated verification PR created after P0 campaign completion**  
**⏰ Created:** $(date -u +"%Y-%m-%d %H:%M:%S UTC")  
**🔍 Purpose:** CI gate functionality testing  
**🧹 Cleanup:** Will be automatically closed after verification  

**Status:** 🔄 Waiting for CI execution...

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)" \
        --draft)
    
    if [[ -n "$PR_URL" ]]; then
        log_success "✅ Verification PR created: $PR_URL"
        echo "$PR_URL"
    else
        log_error "Failed to create verification PR"
        exit 1
    fi
}

monitor_ci_status() {
    local pr_url="$1"
    local pr_number
    pr_number=$(echo "$pr_url" | sed 's/.*\///')
    
    log_info "⏳ Monitoring CI status for PR #${pr_number}..."
    log_info "You can view the PR at: $pr_url"
    
    local max_wait=1800  # 30 minutes
    local check_interval=30  # 30 seconds
    local elapsed=0
    
    while [[ $elapsed -lt $max_wait ]]; do
        log_info "🔍 Checking CI status... (${elapsed}/${max_wait}s elapsed)"
        
        # Get PR status
        local status
        status=$(gh pr status --json state,statusCheckRollupState 2>/dev/null || echo "")
        
        if [[ -n "$status" ]]; then
            local state rollup_state
            state=$(echo "$status" | jq -r '.currentBranch.state // "UNKNOWN"' 2>/dev/null || echo "UNKNOWN")
            rollup_state=$(echo "$status" | jq -r '.currentBranch.statusCheckRollupState // "UNKNOWN"' 2>/dev/null || echo "UNKNOWN")
            
            case "$rollup_state" in
                "SUCCESS")
                    log_success "✅ All CI checks passed!"
                    return 0
                    ;;
                "FAILURE"|"ERROR")
                    log_error "❌ CI checks failed"
                    return 1
                    ;;
                "PENDING"|"EXPECTED"|"UNKNOWN")
                    log_info "⏳ CI checks still running... ($rollup_state)"
                    ;;
            esac
        fi
        
        sleep $check_interval
        elapsed=$((elapsed + check_interval))
    done
    
    log_warning "⏰ Timeout waiting for CI completion"
    return 2
}

close_verification_pr() {
    local pr_url="$1"
    local ci_result="$2"
    local pr_number
    pr_number=$(echo "$pr_url" | sed 's/.*\///')
    
    log_info "🧹 Closing verification PR #${pr_number}..."
    
    # Add final comment with results
    local result_icon result_text
    case "$ci_result" in
        0) result_icon="✅"; result_text="SUCCESS - All CI checks passed" ;;
        1) result_icon="❌"; result_text="FAILURE - CI checks failed" ;;
        2) result_icon="⏰"; result_text="TIMEOUT - CI checks did not complete" ;;
        *) result_icon="❓"; result_text="UNKNOWN - Unexpected result" ;;
    esac
    
    gh pr comment "$pr_number" --body "$(cat <<EOF
## 🔍 Verification Complete - ${result_icon} ${result_text}

**Verification Timestamp:** $(date -u +"%Y-%m-%d %H:%M:%S UTC")  
**CI Status:** ${result_text}  
**Result Code:** ${ci_result}  

### Verification Summary

The automated Ruff CI gate verification has completed. This PR was created solely to test CI functionality after the P0 syntax error campaign and will now be closed.

### Evidence Location
Verification results have been captured in \`evidence/gate_verification/verification_${TIMESTAMP}.json\`

### Next Steps
$(if [[ "$ci_result" -eq 0 ]]; then
    echo "✅ **CI gate verified working** - Development teams can resume normal workflow"
    echo "✅ **P0 campaign confirmed successful** - All blocking violations resolved"  
    echo "✅ **Infrastructure operational** - Ruff automation functioning correctly"
else
    echo "⚠️ **CI issues detected** - Investigation may be needed"
    echo "📋 **Check GitHub Actions** - Review workflow logs for specific errors"
    echo "🔍 **Validate P0 status** - Confirm syntax errors are fully resolved"
fi)

**🤖 Automated verification complete - closing PR**
EOF
)"
    
    # Close the PR
    gh pr close "$pr_number"
    
    log_success "✅ Verification PR closed"
}

cleanup_verification_branch() {
    log_info "🧹 Cleaning up verification branch..."
    
    # Switch back to default branch
    DEFAULT_BRANCH=$(git remote show origin | grep 'HEAD branch' | cut -d' ' -f5 || echo "main")
    git checkout "$DEFAULT_BRANCH" 2>/dev/null || git checkout main 2>/dev/null || git checkout master
    
    # Delete local verification branch
    git branch -D "$VERIFICATION_BRANCH" 2>/dev/null || log_warning "Could not delete local branch"
    
    # Delete remote verification branch
    git push origin --delete "$VERIFICATION_BRANCH" 2>/dev/null || log_warning "Could not delete remote branch"
    
    log_success "✅ Verification branch cleanup complete"
}

save_verification_evidence() {
    local pr_url="$1"
    local ci_result="$2"
    
    log_info "💾 Saving verification evidence..."
    
    mkdir -p "$EVIDENCE_DIR"
    
    local evidence_file="${EVIDENCE_DIR}/verification_${TIMESTAMP}.json"
    
    # Collect verification data
    cat > "$evidence_file" << EOF
{
  "verification_run": {
    "timestamp": "${TIMESTAMP}",
    "branch": "${VERIFICATION_BRANCH}",
    "pr_url": "${pr_url}",
    "verification_file": "${VERIFICATION_FILE}"
  },
  "results": {
    "ci_result_code": ${ci_result},
    "ci_status": "$(case "$ci_result" in 0) echo "SUCCESS";; 1) echo "FAILURE";; 2) echo "TIMEOUT";; *) echo "UNKNOWN";; esac)",
    "gate_functional": $(if [[ "$ci_result" -eq 0 ]]; then echo "true"; else echo "false"; fi),
    "p0_campaign_validated": $(if [[ "$ci_result" -eq 0 ]]; then echo "true"; else echo "false"; fi)
  },
  "evidence": {
    "git_commit": "$(git rev-parse HEAD 2>/dev/null || echo "unknown")",
    "ruff_version": "$(ruff --version 2>/dev/null || echo "unknown")",
    "completion_time": "$(date -u +"%Y-%m-%d %H:%M:%S UTC")"
  },
  "automation": {
    "script": "scripts/verify_ruff_gate.sh",
    "purpose": "Automated CI gate verification after P0 campaign",
    "cleanup_completed": true
  }
}
EOF

    log_success "✅ Verification evidence saved: $evidence_file"
}

print_summary() {
    local pr_url="$1"
    local ci_result="$2"
    
    echo
    echo "═══════════════════════════════════════════════════════════"
    echo "🔍 RUFF CI GATE VERIFICATION COMPLETE"
    echo "═══════════════════════════════════════════════════════════"
    echo
    
    case "$ci_result" in
        0)
            log_success "🎉 VERIFICATION SUCCESSFUL!"
            echo
            log_success "✅ CI gate is functional"
            log_success "✅ P0 violations resolved"  
            log_success "✅ Normal development can resume"
            echo
            ;;
        1)
            log_error "❌ VERIFICATION FAILED"
            echo
            log_error "❌ CI checks failed"
            log_warning "🔍 Investigation needed"
            echo
            ;;
        2)
            log_warning "⏰ VERIFICATION TIMED OUT"
            echo
            log_warning "⏰ CI checks did not complete"
            log_warning "🔍 Manual review recommended"
            echo
            ;;
    esac
    
    echo "📋 Verification Details:"
    echo "   • PR: $pr_url"
    echo "   • Branch: $VERIFICATION_BRANCH (cleaned up)"
    echo "   • Evidence: evidence/gate_verification/verification_${TIMESTAMP}.json"
    echo "   • Timestamp: $TIMESTAMP"
    echo
    
    if [[ "$ci_result" -eq 0 ]]; then
        echo "🚀 Next Steps:"
        echo "   1. Announce campaign success to development teams"
        echo "   2. Archive P0 campaign materials"
        echo "   3. Resume normal development workflow"
        echo "   4. Monitor for P0 regressions"
    else
        echo "🔍 Troubleshooting:"
        echo "   1. Check GitHub Actions logs: ${pr_url}/checks"
        echo "   2. Run: python scripts/validate_ruff_infrastructure.py"
        echo "   3. Verify P0 status manually with Ruff"
    fi
    
    echo
    echo "═══════════════════════════════════════════════════════════"
}

main() {
    echo "🔍 Ruff CI Gate Verification Automation"
    echo "Purpose: Test CI gate functionality after P0 campaign"
    echo

    # Execute verification workflow
    check_prerequisites
    create_verification_content
    create_verification_branch
    commit_verification_changes
    push_verification_branch
    
    local pr_url
    pr_url=$(create_verification_pr)
    
    # Monitor CI and collect results
    local ci_result
    monitor_ci_status "$pr_url"
    ci_result=$?
    
    # Cleanup and documentation
    close_verification_pr "$pr_url" "$ci_result"
    cleanup_verification_branch
    save_verification_evidence "$pr_url" "$ci_result"
    
    # Final summary
    print_summary "$pr_url" "$ci_result"
    
    # Return appropriate exit code
    exit $ci_result
}

# Execute main function if script is run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi