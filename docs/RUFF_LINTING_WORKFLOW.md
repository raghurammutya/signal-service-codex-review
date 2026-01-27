# Ruff Linting Workflow - Developer Handbook

## 📋 Overview

This guide provides comprehensive instructions for using Ruff to maintain code quality across the signal-service-codex-review repository, excluding the legacy `signal_service_legacy` tree.

## 🔧 Setup and Configuration

### Prerequisites
- Python 3.11+
- Git repository access
- Virtual environment support

### Installation Methods

#### Method 1: Using Virtual Environment (Recommended)
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate     # Windows

# Install Ruff
pip install ruff
```

#### Method 2: Using System Package Manager
```bash
# Ubuntu/Debian
sudo apt install ruff

# macOS
brew install ruff

# Windows
winget install ruff
```

#### Method 3: Using pipx (Isolated)
```bash
pipx install ruff
```

### Configuration Files

The repository includes comprehensive Ruff configuration:

#### `pyproject.toml` - Main Configuration
```toml
[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4", "ISC", "PIE", "PYI", "RSE", "RET", "SIM", "TCH"]
ignore = ["E501", "E203", "B008", "ISC001"]
extend-ignore = ["N806", "N803"]
exclude = ["signal_service_legacy", "migrations", "*.pb2.py"]

[tool.ruff.lint.per-file-ignores]
"test_*.py" = ["S101", "PLR2004"]
"scripts/*.py" = ["T201", "F401"]
```

#### `.ruffignore` - Additional Exclusions
```
signal_service_legacy/
**/generated/
*.json.large
phase0_token_inventory.json
*backup*.tar.gz
```

## 🚀 Usage Workflows

### Basic Commands

#### Check for violations (no changes)
```bash
ruff check .
```

#### Check with statistics
```bash
ruff check . --statistics
```

#### Auto-fix violations
```bash
ruff check . --fix
```

#### Format code
```bash
ruff format .
```

### Automated Workflow Script

Use the comprehensive automation script for full workflow execution:

```bash
# Check only
python scripts/run_ruff.py

# Check and auto-fix
python scripts/run_ruff.py --fix

# Include unsafe fixes
python scripts/run_ruff.py --fix --unsafe-fixes

# CI mode (fail on violations)
python scripts/run_ruff.py --ci
```

### Target-Specific Commands

#### Focus on specific file types
```bash
ruff check app/ --include="*.py"
ruff check tests/ --statistics
```

#### Exclude legacy components
```bash
ruff check . --exclude signal_service_legacy
```

## 📊 Evidence and Reporting

### Automatic Evidence Generation

The `scripts/run_ruff.py` script automatically generates:

- **Evidence Report**: `ruff_evidence_YYYYMMDD_HHMMSS.md`
- **Raw Results**: `ruff_results_YYYYMMDD_HHMMSS.json`

### Manual Evidence Collection

```bash
# Capture violations with statistics
ruff check . --statistics | tee ruff_scan_$(date +%Y%m%d_%H%M%S).log

# Generate diff after fixes
git diff > ruff_fixes_$(date +%Y%m%d_%H%M%S).diff
```

### Evidence Report Contents

```markdown
# Ruff Linting Evidence Report

## Summary
- **Generated**: 2026-01-27T06:05:00
- **Repository**: signal-service-codex-review
- **Total Violations**: 6,776
- **Command**: ruff check . --statistics

## Top Violations
- **W293**: 3,283 occurrences (blank-line-with-whitespace)
- **invalid-syntax**: 2,144 occurrences
- **W291**: 212 occurrences (trailing-whitespace)

## Improvement
✅ Reduced violations by 25,373 through auto-fixes
```

## 🔄 CI/CD Integration

### GitHub Actions Workflow

The repository includes automated GitHub Actions workflow:

#### `.github/workflows/ruff-lint.yml`
```yaml
name: Ruff Linting

on:
  push:
    branches: [ master, main, develop ]
  pull_request:
    branches: [ master, main ]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    - run: pip install ruff
    - run: ruff check . --exclude signal_service_legacy --statistics --output-format=github
    - run: ruff format . --exclude signal_service_legacy --check --diff
```

### Pre-commit Hooks

#### Option 1: Basic pre-commit hook
```bash
# .git/hooks/pre-commit
#!/bin/sh
ruff check . --exclude signal_service_legacy
if [ $? -ne 0 ]; then
    echo "Ruff linting failed. Run 'ruff check . --fix' to auto-fix."
    exit 1
fi
```

#### Option 2: Auto-fix pre-commit hook
```bash
# .git/hooks/pre-commit
#!/bin/sh
ruff check . --exclude signal_service_legacy --fix
ruff format . --exclude signal_service_legacy
git add -u  # Add fixed files
```

## 🎯 Best Practices

### Development Workflow

1. **Before Committing**
   ```bash
   python scripts/run_ruff.py --fix
   git add .
   git commit -m "Fix linting violations"
   ```

2. **During Code Review**
   ```bash
   ruff check . --diff --exclude signal_service_legacy
   ```

3. **Release Preparation**
   ```bash
   python scripts/run_ruff.py --ci
   ```

### Team Standards

#### Violation Priorities
- **P0**: Syntax errors, undefined names (`F821`, `F401`)
- **P1**: Import sorting, trailing whitespace (`I001`, `W291`)
- **P2**: Code style, deprecated patterns (`UP006`, `RET505`)
- **P3**: Complex refactoring suggestions (`SIM117`, `B904`)

#### Target Metrics
- **Zero P0 violations** before merge
- **<100 P1 violations** per 1000 lines of code
- **Progressive reduction** of P2/P3 violations

### Exclusion Guidelines

#### When to add exclusions:
- Generated code files (`*_pb2.py`, `migrations/`)
- Third-party code (`vendor/`, `external/`)
- Legacy components (`signal_service_legacy/`)

#### When NOT to exclude:
- Core application code
- Test files (use per-file ignores instead)
- Configuration files

## 🔍 Troubleshooting

### Common Issues

#### Environment Problems
```bash
# Issue: "ruff: command not found"
# Solution: Ensure Ruff is installed in active environment
source .venv/bin/activate
pip install ruff

# Issue: "externally-managed-environment"
# Solution: Use virtual environment
python3 -m venv .venv && source .venv/bin/activate
```

#### Configuration Issues
```bash
# Issue: Rules not applying correctly
# Solution: Verify pyproject.toml syntax
ruff check --show-settings

# Issue: Files not excluded
# Solution: Check both pyproject.toml exclude and .ruffignore
ruff check --show-files
```

#### Performance Issues
```bash
# Issue: Slow linting on large repository
# Solution: Use targeted scanning
ruff check app/ tests/ scripts/

# Issue: Out of memory on large files
# Solution: Add large files to .ruffignore
echo "phase0_token_inventory.json" >> .ruffignore
```

### Getting Help

#### Ruff Documentation
```bash
ruff --help
ruff check --help
ruff format --help
```

#### Rule Information
```bash
# Get information about specific rule
ruff rule F401

# Show all enabled rules
ruff linter
```

#### Debug Configuration
```bash
# Show active configuration
ruff check --show-settings .

# Show file discovery
ruff check --show-files .
```

## 🤖 Automation & Campaign Management

### Integrated P0 Campaign Automation

The repository includes comprehensive automation for managing P0 syntax error campaigns:

#### Run Complete Campaign Automation
```bash
# Integrated workflow: success detection + gate verification
python scripts/ruff_campaign_automation.py

# Output provides complete campaign status and next steps
```

#### Campaign Success Detection Only
```bash
# Check if P0 campaign is complete and generate success report
python scripts/detect_campaign_success.py

# Generates success celebration and evidence artifacts
```

#### CI Gate Verification Only
```bash
# Test CI gate functionality after campaign completion
./scripts/verify_ruff_gate.sh

# Creates verification PR, tests CI, and cleans up automatically
```

### Campaign Monitoring Scripts

#### Real-time Progress Tracking
```bash
# Monitor syntax error reduction progress
python scripts/track_syntax_fix_progress.py

# Weekly executive and technical reports  
python scripts/generate_weekly_syntax_report.py
```

#### Infrastructure Health Validation
```bash
# Complete infrastructure validation with evidence
python scripts/validate_ruff_infrastructure.py

# Triage and assignment generation for new campaigns
python scripts/triage_syntax_errors.py
```

### Automation Workflow Benefits

#### For Development Teams
- **Automated success detection** eliminates manual verification
- **CI gate testing** confirms infrastructure is working
- **Evidence preservation** provides complete audit trail
- **Seamless integration** between campaign phases

#### For Management
- **Executive dashboards** with automated success notifications
- **Complete automation** reduces manual coordination overhead
- **Verified CI functionality** confirms development can resume
- **Preserved evidence** for process improvement and auditing

## 📚 Advanced Usage

### Custom Rule Sets

#### Create environment-specific configs
```bash
# Development (lenient)
ruff check . --config pyproject-dev.toml

# Production (strict)
ruff check . --config pyproject-prod.toml
```

#### Override rules temporarily
```bash
# Ignore specific rules for one run
ruff check . --ignore E501,W291

# Add rules for one run
ruff check . --select E,F,W,I,B,C4
```

### Integration with Other Tools

#### With Black (code formatter)
```bash
# Configure to avoid conflicts
# In pyproject.toml:
# ignore = ["ISC001", "E203"]
```

#### With mypy (type checking)
```bash
# Run together in CI
ruff check . && mypy .
```

#### With pytest (testing)
```bash
# Lint tests with relaxed rules
ruff check tests/ --ignore S101,PLR2004
```

## 📝 Exemption Management

### When to Add Exemptions

#### Acceptable Exemption Reasons
- **Generated Code**: `*_pb2.py`, migration files, protobuf generated code
- **Legacy Components**: Large legacy files with >200 violations requiring systematic refactoring
- **Third-party Code**: Vendor code, external libraries integrated into repository
- **Test Data Files**: Large JSON/data files that trigger formatting violations

#### Exemption Process

##### 1. Evaluate Need
```bash
# Check violation count for specific file
ruff check path/to/file.py --statistics

# If >100 violations and fits exemption criteria, proceed
```

##### 2. Add Documented Exemption
```bash
# Add temporary exemption (30-day review)
python scripts/manage_ruff_exemptions.py add "legacy_module/*.py" \
  "Legacy code requiring systematic refactoring" \
  --temporary --assignee "team-lead" --review-date "2026-02-27"

# Add permanent exemption for generated code
python scripts/manage_ruff_exemptions.py add "*_pb2.py" \
  "Generated protobuf code" --rules "E501,W291,F401"
```

##### 3. Track and Review
```bash
# List all exemptions
python scripts/manage_ruff_exemptions.py list

# Review overdue exemptions
python scripts/manage_ruff_exemptions.py review

# Generate exemption report
python scripts/manage_ruff_exemptions.py report
```

### Exemption Categories

#### Temporary Exemptions (30-90 days)
- Legacy files being actively refactored
- Files with complex violations requiring planned remediation
- Modules waiting for architectural changes

#### Permanent Exemptions
- Generated code files (`*_pb2.py`, `*_generated.py`)
- External vendor code
- Large data/configuration files

### Tech Debt Tracking

#### Integration with GitHub Issues
Exemptions automatically create tracking issues:
- **P0 violations**: Immediate GitHub issue creation
- **High violation count**: Trend alert issues
- **Overdue temporary exemptions**: Review reminder issues

#### Exemption Database
All exemptions tracked in `evidence/ruff_exemptions.json`:
```json
{
  "exempt_001": {
    "path_pattern": "legacy_module/*.py",
    "reason": "Legacy code requiring systematic refactoring",
    "temporary": true,
    "review_date": "2026-02-27",
    "assignee": "team-lead",
    "status": "active"
  }
}
```

## 📊 Progress Tracking

### Backlog Management

#### Nightly Tracking
Automated GitHub Action runs nightly to:
- Generate violation statistics
- Update progress trends
- Create issues for critical violations
- Track exemption status

#### Sprint Planning
Use triage reports for sprint planning:
```bash
# Generate current triage
python scripts/triage_ruff_violations.py

# Review generated tasks
cat evidence/ruff_triage/ruff_remediation_tasks_*.md
```

#### Metrics Dashboard
Track key metrics:
- **Total violations**: Target <5000 by sprint end
- **P0 violations**: Must remain at 0
- **P1 violations**: Reduce by 50% per sprint
- **Exemption count**: Keep under 20 active exemptions

### Team Workflow

#### Daily Developer Process
```bash
# Before commit
python scripts/run_ruff.py --fix
git add . && git commit -m "Fix linting violations"

# If violations can't be fixed immediately
python scripts/manage_ruff_exemptions.py add "problematic_file.py" \
  "Requires architectural changes" --temporary --assignee "developer-name"
```

#### Weekly Team Review
1. Review violation trends: `evidence/ruff_backlog/current_status.md`
2. Assign P1/P2 tasks from triage reports
3. Review overdue exemptions
4. Plan systematic fixes for next sprint

## 📝 Maintenance

### Regular Tasks

#### Weekly
- Review violation trends in `evidence/ruff_backlog/`
- Update rule configurations based on team feedback
- Clean old evidence files (>30 days)
- Review exemption candidates

#### Monthly
- Update Ruff version
- Review and adjust exclusions
- Analyze performance metrics
- Generate exemption report

#### Quarterly
- Review team standards and adjust rules
- Update documentation with lessons learned
- Refine CI/CD integration
- Conduct exemption audit

### Monitoring

#### Track metrics over time:
```bash
# Generate trend report
python scripts/run_ruff.py | grep "Total Violations"

# Compare against baseline
ruff check . --statistics > current_violations.txt
diff baseline_violations.txt current_violations.txt
```

## 🚨 URGENT: Syntax Error Fix Campaign

### Critical Status (January 2026)
**BLOCKER**: 1,950 syntax errors in 43 files are blocking ALL CI merges

#### Immediate P0 Actions Required:
```bash
# 1. Identify syntax errors in your module
python scripts/triage_syntax_errors.py

# 2. Fix individual files (example)
python -m py_compile app/services/problematic_file.py  # Shows exact Python errors
ruff check app/services/problematic_file.py           # Shows Ruff perspective

# 3. Validate fixes
python scripts/validate_ruff_infrastructure.py        # Rerun validation
```

#### Top Files Requiring Immediate Attention:
1. `app/services/trendline_indicators.py` (234 errors)
2. `common/storage/database.py` (112 errors)  
3. `app/services/clustering_indicators.py` (111 errors)
4. `app/services/marketplace_client.py` (105 errors)
5. `app/services/watermark_integration.py` (104 errors)

#### Fix Assignment Process:
1. **Check assignment**: `evidence/syntax_triage/syntax_fix_assignments_*.md`
2. **Create GitHub issues**: Use templates from `evidence/syntax_triage/github_issues_*.json`
3. **Track progress**: Rerun validation script after each fix
4. **Verify CI**: Test with small PR once syntax errors < 100

⚠️ **DEADLINE**: 48 hours to unblock development

---

## ✅ Quick Reference

### Essential Commands
```bash
# FIRST: Check if syntax errors are blocking you
python scripts/validate_ruff_infrastructure.py

# Daily development (after syntax errors fixed)
ruff check . --fix && git add .

# Pre-merge check
ruff check . --statistics

# CI validation
python scripts/run_ruff.py --ci

# Format code
ruff format .

# Full workflow
python scripts/run_ruff.py --fix

# Syntax error triage (P0)
python scripts/triage_syntax_errors.py
```

### Key Files
- `pyproject.toml` - Main configuration
- `.ruffignore` - Additional exclusions
- `scripts/run_ruff.py` - Automated workflow
- `.github/workflows/ruff-lint.yml` - CI integration

### Support Resources
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Rule Reference](https://docs.astral.sh/ruff/rules/)
- [Configuration Guide](https://docs.astral.sh/ruff/configuration/)
- Repository Issues: Create GitHub issue for problems