#!/bin/bash
#
# Phase 0 Token Usage Audit - Execution Script
#
# Orchestrates the complete Phase 0 audit process with automated scanning,
# checklist generation, and progress tracking.
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
RESULTS_DIR="${PROJECT_ROOT}/phase0_results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Create results directory
create_results_directory() {
    log "Creating results directory..."
    mkdir -p "$RESULTS_DIR"
    echo "Phase 0 Token Usage Audit Results - $(date)" > "$RESULTS_DIR/README.md"
    echo "Generated at: $(date)" >> "$RESULTS_DIR/README.md"
    echo "" >> "$RESULTS_DIR/README.md"
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        error "python3 is required but not installed"
        exit 1
    fi
    
    # Check required Python modules
    python3 -c "import ast, re, json, sqlite3, pathlib" 2>/dev/null || {
        error "Required Python modules not available"
        exit 1
    }
    
    # Check if we're in a git repository
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        warning "Not in a git repository - some features may be limited"
    fi
    
    success "Prerequisites check passed"
}

# Run token usage scanner
run_token_scanner() {
    log "Running comprehensive token usage scanner..."
    
    local inventory_file="${RESULTS_DIR}/token_usage_inventory_${TIMESTAMP}.json"
    
    python3 "${SCRIPT_DIR}/phase0_token_usage_scanner.py" \
        --codebase "$PROJECT_ROOT" \
        --output "$inventory_file" > /dev/null
    
    if [ -f "$inventory_file" ]; then
        success "Token usage scan completed: $inventory_file"
        echo "$inventory_file"
    else
        error "Token usage scan failed - no output file generated"
        exit 1
    fi
}

# Generate execution checklist
generate_checklist() {
    local inventory_file="$1"
    log "Generating Phase 0 execution checklist..."
    
    local checklist_file="${RESULTS_DIR}/phase0_execution_checklist_${TIMESTAMP}.json"
    
    python3 "${SCRIPT_DIR}/phase0_checklist_generator.py" \
        --inventory "$inventory_file" \
        --output "$checklist_file" > /dev/null
    
    if [ -f "$checklist_file" ]; then
        success "Execution checklist generated: $checklist_file"
        echo "$checklist_file"
    else
        error "Checklist generation failed"
        exit 1
    fi
}

# Generate human-readable reports
generate_reports() {
    local inventory_file="$1"
    local checklist_file="$2"
    
    log "Generating human-readable reports..."
    
    # Extract key information from JSON files
    local total_findings=$(jq -r '.summary_statistics.total_findings // 0' "$inventory_file")
    local critical_issues=$(jq -r '.summary_statistics.critical_issues // 0' "$inventory_file")
    local files_affected=$(jq -r '.summary_statistics.files_affected // 0' "$inventory_file")
    local total_tasks=$(jq -r '.all_tasks | length' "$checklist_file")
    local estimated_hours=$(jq -r '[.all_tasks[].estimated_hours] | add' "$checklist_file")
    
    # Generate executive summary
    cat > "${RESULTS_DIR}/executive_summary.md" << EOF
# Phase 0 Token Usage Audit - Executive Summary

**Generated**: $(date)  
**Scope**: Comprehensive instrument_token usage analysis

## Key Findings

- **Total token usage findings**: ${total_findings}
- **Critical issues requiring immediate attention**: ${critical_issues}
- **Files affected**: ${files_affected}
- **Estimated migration effort**: ${estimated_hours} hours across ${total_tasks} tasks

## Migration Priorities

$(jq -r '.migration_priorities[:5][] | "- **\(.service)**: \(.total_findings) findings (\(.critical_findings) critical, priority score: \(.migration_priority))"' "$inventory_file")

## Next Steps

1. Review detailed findings in \`$(basename "$inventory_file")\`
2. Execute Phase 0 tasks using \`$(basename "$checklist_file")\`
3. Complete all critical and high-priority tasks within 1 week
4. Proceed to Phase 1 (SDK & Strategy Migration) upon successful completion

## Success Criteria

$(jq -r '.success_criteria[] | "- \(.)"' "$checklist_file")

EOF

    # Generate daily task breakdown
    cat > "${RESULTS_DIR}/daily_task_breakdown.md" << EOF
# Phase 0 Daily Task Breakdown

$(jq -r '.timeline.daily_schedule | to_entries[] | "## \(.key | gsub("_"; " ") | ascii_upcase)\n\n**Date**: \(.value.date)  \n**Focus**: \(.value.focus)\n\n### Key Tasks\n\(.value.key_tasks[] | "- \(.)")\n\n### Expected Deliverables\n\(.value.deliverables[] | "- \(.)")\n"' "$checklist_file")
EOF

    # Generate task tracking sheet
    cat > "${RESULTS_DIR}/task_tracking.csv" << 'EOF'
Task ID,Title,Service,Priority,Estimated Hours,Status,Assignee,Dependencies,Completion Date
EOF
    
    jq -r '.all_tasks[] | [.task_id, .title, .service, .priority, .estimated_hours, .status, .assignee, (.dependencies | join(";")), ""] | @csv' "$checklist_file" >> "${RESULTS_DIR}/task_tracking.csv"
    
    success "Reports generated in $RESULTS_DIR/"
}

# Validate results
validate_results() {
    log "Validating audit results..."
    
    local validation_errors=0
    
    # Check if inventory file has findings
    local inventory_file="${RESULTS_DIR}/token_usage_inventory_${TIMESTAMP}.json"
    if [ ! -f "$inventory_file" ]; then
        error "Inventory file missing"
        ((validation_errors++))
    else
        local findings_count=$(jq -r '.summary_statistics.total_findings // 0' "$inventory_file")
        if [ "$findings_count" -eq 0 ]; then
            warning "No token usage findings detected - validate scanner configuration"
        else
            success "$findings_count token usage findings identified"
        fi
    fi
    
    # Check if checklist has tasks
    local checklist_file="${RESULTS_DIR}/phase0_execution_checklist_${TIMESTAMP}.json"
    if [ ! -f "$checklist_file" ]; then
        error "Checklist file missing"
        ((validation_errors++))
    else
        local task_count=$(jq -r '.all_tasks | length' "$checklist_file")
        success "$task_count tasks generated for Phase 0 execution"
    fi
    
    # Check if reports were generated
    local required_reports=("executive_summary.md" "daily_task_breakdown.md" "task_tracking.csv")
    for report in "${required_reports[@]}"; do
        if [ ! -f "${RESULTS_DIR}/$report" ]; then
            error "Required report missing: $report"
            ((validation_errors++))
        fi
    done
    
    if [ $validation_errors -eq 0 ]; then
        success "Validation passed - all artifacts generated successfully"
        return 0
    else
        error "$validation_errors validation errors found"
        return 1
    fi
}

# Display results summary
display_summary() {
    echo ""
    echo "🎯 PHASE 0 AUDIT COMPLETE"
    echo "=========================="
    echo ""
    echo "📁 Results Directory: $RESULTS_DIR"
    echo ""
    echo "📋 Generated Artifacts:"
    echo "   • token_usage_inventory_${TIMESTAMP}.json - Complete token usage findings"
    echo "   • phase0_execution_checklist_${TIMESTAMP}.json - Detailed task checklist"
    echo "   • executive_summary.md - High-level findings and priorities"
    echo "   • daily_task_breakdown.md - Day-by-day execution plan"
    echo "   • task_tracking.csv - Task tracking spreadsheet"
    echo ""
    echo "🚀 Next Steps:"
    echo "   1. Review executive summary for key findings"
    echo "   2. Assign tasks using task_tracking.csv"
    echo "   3. Execute Phase 0 tasks according to daily breakdown"
    echo "   4. Track progress and update task statuses"
    echo "   5. Validate completion before proceeding to Phase 1"
    echo ""
}

# Main execution function
main() {
    echo ""
    echo "🔍 PHASE 0 TOKEN USAGE AUDIT"
    echo "============================"
    echo ""
    echo "Building on Phase 3 registry integration success to accelerate"
    echo "instrument_key adoption across all services."
    echo ""
    
    # Execute audit steps
    create_results_directory
    check_prerequisites
    
    inventory_file=$(run_token_scanner)
    checklist_file=$(generate_checklist "$inventory_file")
    
    generate_reports "$inventory_file" "$checklist_file"
    
    if validate_results; then
        display_summary
        
        # Update README with results
        cat >> "$RESULTS_DIR/README.md" << EOF

## Audit Results Summary

- **Inventory File**: $(basename "$inventory_file")
- **Checklist File**: $(basename "$checklist_file") 
- **Total Token Findings**: $(jq -r '.summary_statistics.total_findings // 0' "$inventory_file")
- **Tasks Generated**: $(jq -r '.all_tasks | length' "$checklist_file")
- **Estimated Effort**: $(jq -r '[.all_tasks[].estimated_hours] | add' "$checklist_file") hours

## Files Generated

$(ls -la "$RESULTS_DIR" | grep -v '^d' | awk '{print "- " $9 " (" $5 " bytes)"}')

EOF
        
        success "Phase 0 audit completed successfully!"
        echo ""
        echo "💡 Ready to begin Phase 0 execution using generated checklist"
        exit 0
    else
        error "Phase 0 audit validation failed"
        exit 1
    fi
}

# Handle script interruption
trap 'error "Script interrupted"; exit 130' INT TERM

# Execute main function
main "$@"