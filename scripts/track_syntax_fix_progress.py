#!/usr/bin/env python3
"""
Syntax Fix Progress Tracker

Monitors progress on P0 syntax error fixes and generates status updates.
Integrates with GitHub issue creation and team accountability.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    """Run shell command and return exit code, stdout, stderr"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)


def get_current_syntax_count() -> dict:
    """Get current count of syntax-related violations"""
    ruff_cmd = "ruff" if run_command(["ruff", "--version"])[0] == 0 else ".venv/bin/ruff"

    # Get statistics
    exit_code, stdout, stderr = run_command([
        ruff_cmd, "check", ".", "--exclude", "signal_service_legacy", "--statistics"
    ])

    result = {"total_violations": 0, "syntax_count": 0, "other_critical": 0}

    if exit_code == 0 or stdout:
        for line in stdout.split('\n'):
            if '\t' in line and any(char.isdigit() for char in line):
                parts = line.strip().split('\t')
                if len(parts) >= 2:
                    try:
                        count = int(parts[0].strip())
                        rule_code = parts[1].strip()

                        result["total_violations"] += count

                        # Count syntax-related issues
                        if not rule_code or rule_code == "invalid-syntax":
                            result["syntax_count"] += count
                        elif rule_code in ["F821", "F811", "F402"]:  # Other P0 critical
                            result["other_critical"] += count

                    except ValueError:
                        pass

    return result


def load_baseline_data() -> dict:
    """Load baseline syntax error data for comparison"""
    # Look for the most recent triage data
    syntax_dir = Path("evidence/syntax_triage")
    if not syntax_dir.exists():
        return {}

    raw_files = list(syntax_dir.glob("syntax_errors_raw_*.json"))
    if not raw_files:
        return {}

    # Get most recent file
    latest_file = max(raw_files, key=lambda f: f.stat().st_mtime)

    try:
        with open(latest_file) as f:
            return json.load(f)
    except:
        return {}


def generate_progress_report(current: dict, baseline: dict) -> str:
    """Generate progress report comparing current vs baseline"""

    timestamp = datetime.now().isoformat()

    # Extract baseline metrics
    baseline_syntax = 0
    baseline_files = 0

    if baseline and "categories" in baseline:
        baseline_syntax = baseline["categories"]["summary"].get("total_errors", 0)
        baseline_files = baseline["categories"]["summary"].get("total_files", 0)

        # Estimate baseline total from raw violations
        if "syntax_violations" in baseline:
            len(baseline["syntax_violations"])

    # Current metrics
    current_syntax = current.get("syntax_count", 0)
    current_total = current.get("total_violations", 0)
    current_critical = current.get("other_critical", 0)

    # Calculate progress
    syntax_progress = baseline_syntax - current_syntax if baseline_syntax > 0 else 0
    syntax_percent_fixed = (syntax_progress / baseline_syntax * 100) if baseline_syntax > 0 else 0

    report = f"""# 🚨 Syntax Error Fix Progress Report

**Generated:** {timestamp}
**Status:** {'🔥 CRITICAL - CI BLOCKED' if current_syntax > 100 else '⚠️ In Progress' if current_syntax > 0 else '✅ RESOLVED'}

## Progress Summary

### Syntax Errors (P0 Critical)
"""

    if baseline_syntax > 0:
        report += f"""- **Baseline**: {baseline_syntax:,} syntax errors in {baseline_files} files
- **Current**: {current_syntax:,} syntax errors
- **Fixed**: {syntax_progress:,} ({syntax_percent_fixed:.1f}%)
- **Remaining**: {current_syntax:,}
"""
    else:
        report += f"- **Current**: {current_syntax:,} syntax errors\n"

    report += f"""
### Overall Status
- **Total violations**: {current_total:,}
- **Other P0 critical**: {current_critical:,} (F821, F811, F402)
- **CI Status**: {'🔴 BLOCKED' if current_syntax > 0 or current_critical > 0 else '🟢 PASSING'}

## Impact Assessment

"""

    if current_syntax > 0:
        report += f"""### 🔴 CI STILL BLOCKED
- **{current_syntax:,} syntax errors** are preventing all merges
- **Immediate action required** - these cannot be auto-fixed
- **Development frozen** until syntax issues resolved

### Priority Actions:
1. **Focus on syntax errors first** - other violations can wait
2. **Use individual file validation**: `python -m py_compile filename.py`
3. **Test fixes incrementally** - don't batch too many changes
"""
    elif current_critical > 0:
        report += f"""### ⚠️ MINOR P0 ISSUES REMAIN
- **Syntax errors resolved!** ✅
- **{current_critical:,} other P0 violations** still need fixes (F821, F811, F402)
- **CI may still block** depending on configuration

### Next Actions:
1. **Fix undefined names (F821)** - likely the biggest blocker
2. **Clean up import shadowing (F402)**
3. **Remove redefined variables (F811)**
"""
    else:
        report += """### 🟢 P0 ISSUES RESOLVED!
- **All syntax errors fixed** ✅
- **All critical violations resolved** ✅
- **CI should now pass** - ready for normal development

### Celebration & Next Steps:
1. **Test CI pipeline** - create small test PR to verify
2. **Resume normal development** - P1/P2 violations can be addressed gradually
3. **Monitor for regressions** - use nightly automation
"""

    # Recommendations based on current state
    if current_syntax > 500:
        urgency = "EMERGENCY"
        timeline = "24 hours"
    elif current_syntax > 100:
        urgency = "HIGH"
        timeline = "48 hours"
    elif current_syntax > 0:
        urgency = "MEDIUM"
        timeline = "1 week"
    else:
        urgency = "LOW"
        timeline = "Ongoing"

    report += f"""
## Recommended Actions

### Urgency Level: {urgency}
### Target Timeline: {timeline}

"""

    if current_syntax > 0:
        report += """### Immediate Tasks:
1. **Run syntax triage**: `python scripts/triage_syntax_errors.py`
2. **Assign ownership**: Use generated assignments in evidence/syntax_triage/
3. **Fix top files first**: Focus on files with >50 errors
4. **Validate progress**: `python scripts/validate_ruff_infrastructure.py`

### Commands for developers:
```bash
# Check your module's syntax errors
ruff check your_module/ --exclude signal_service_legacy

# Fix individual files
python -m py_compile your_module/problematic_file.py

# Validate fixes
python scripts/track_syntax_fix_progress.py
```
"""
    else:
        report += """### Maintenance Tasks:
1. **Set up monitoring**: Enable nightly violation tracking
2. **Address P1/P2 violations**: Use standard Ruff workflow
3. **Prevent regressions**: Ensure pre-commit hooks working

### Commands for ongoing quality:
```bash
# Regular development workflow (now unblocked)
python scripts/run_ruff.py --fix

# Monitor violation trends
python scripts/validate_ruff_infrastructure.py
```
"""

    return report


def create_github_status_update(current: dict, baseline: dict) -> dict:
    """Create GitHub issue status update"""

    current_syntax = current.get("syntax_count", 0)
    baseline_syntax = baseline.get("categories", {}).get("summary", {}).get("total_errors", 0) if baseline else 0

    if current_syntax == 0:
        status = "RESOLVED"
        emoji = "🎉"
        priority = "P3"
    elif current_syntax < 100:
        status = "NEARLY_RESOLVED"
        emoji = "🟡"
        priority = "P1"
    else:
        status = "CRITICAL"
        emoji = "🔴"
        priority = "P0"

    return {
        "title": f"{emoji} Syntax Error Progress: {current_syntax:,} remaining",
        "status": status,
        "priority": priority,
        "metrics": {
            "baseline_errors": baseline_syntax,
            "current_errors": current_syntax,
            "fixed_count": baseline_syntax - current_syntax if baseline_syntax > 0 else 0,
            "percent_complete": ((baseline_syntax - current_syntax) / baseline_syntax * 100) if baseline_syntax > 0 else 100
        },
        "next_actions": "Immediate syntax fix campaign" if current_syntax > 0 else "Resume normal development"
    }


def main():
    """Main progress tracking execution"""
    print("📊 Tracking syntax fix progress...")

    # Get current status
    print("🔍 Checking current violation counts...")
    current_status = get_current_syntax_count()

    # Load baseline for comparison
    print("📋 Loading baseline data...")
    baseline_data = load_baseline_data()

    # Generate reports
    print("📝 Generating progress report...")
    progress_report = generate_progress_report(current_status, baseline_data)

    print("🎫 Creating GitHub status update...")
    github_update = create_github_status_update(current_status, baseline_data)

    # Save outputs
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    progress_dir = Path("evidence/syntax_progress")
    progress_dir.mkdir(parents=True, exist_ok=True)

    # Progress report
    report_file = progress_dir / f"syntax_progress_report_{timestamp}.md"
    with open(report_file, 'w') as f:
        f.write(progress_report)

    # GitHub update
    github_file = progress_dir / f"github_status_update_{timestamp}.json"
    with open(github_file, 'w') as f:
        json.dump(github_update, f, indent=2)

    # Raw status
    status_file = progress_dir / f"syntax_status_{timestamp}.json"
    status_data = {
        "timestamp": timestamp,
        "current_status": current_status,
        "baseline_comparison": baseline_data.get("categories", {}).get("summary", {}) if baseline_data else {},
        "github_update": github_update
    }

    with open(status_file, 'w') as f:
        json.dump(status_data, f, indent=2)

    # Summary output
    current_syntax = current_status.get("syntax_count", 0)
    current_total = current_status.get("total_violations", 0)

    print(f"""
✅ Progress tracking complete!

📊 **Current Status:**
- Syntax errors: {current_syntax:,}
- Total violations: {current_total:,}
- CI Status: {'🔴 BLOCKED' if current_syntax > 0 else '🟢 PASSING'}

📁 **Reports generated:**
- Progress report: {report_file}
- GitHub update: {github_file}
- Status data: {status_file}
""")

    # Status-based messaging
    if current_syntax == 0:
        print("🎉 **CONGRATULATIONS!** All syntax errors resolved - CI should be unblocked!")
    elif current_syntax < 100:
        print(f"🟡 **ALMOST THERE!** Only {current_syntax:,} syntax errors remaining!")
    else:
        print(f"🔴 **URGENT ACTION NEEDED!** {current_syntax:,} syntax errors still blocking CI!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
