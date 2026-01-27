#!/usr/bin/env python3
"""
Weekly Syntax Fix Progress Reporter

Generates comprehensive weekly reports on P0 syntax error campaign progress,
including GitHub PR comments, team accountability metrics, and executive summaries.
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    """Run shell command and return exit code, stdout, stderr"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)


def load_historical_progress() -> list[dict]:
    """Load historical progress data points"""
    progress_dir = Path("evidence/syntax_progress")
    if not progress_dir.exists():
        return []

    status_files = list(progress_dir.glob("syntax_status_*.json"))
    historical_data = []

    for file in sorted(status_files, key=lambda f: f.stat().st_mtime):
        try:
            with open(file) as f:
                data = json.load(f)
                historical_data.append(data)
        except:
            continue

    return historical_data


def get_current_status() -> dict:
    """Get current syntax error status"""
    ruff_cmd = "ruff" if run_command(["ruff", "--version"])[0] == 0 else ".venv/bin/ruff"

    exit_code, stdout, stderr = run_command([
        ruff_cmd, "check", ".", "--exclude", "signal_service_legacy", "--statistics"
    ])

    current = {
        "timestamp": datetime.now().isoformat(),
        "total_violations": 0,
        "syntax_errors": 0,
        "other_critical": 0,
        "status": "unknown"
    }

    if exit_code == 0 or stdout:
        for line in stdout.split('\n'):
            if '\t' in line and any(char.isdigit() for char in line):
                parts = line.strip().split('\t')
                if len(parts) >= 2:
                    try:
                        count = int(parts[0].strip())
                        rule_code = parts[1].strip()

                        current["total_violations"] += count

                        if not rule_code or rule_code == "invalid-syntax":
                            current["syntax_errors"] += count
                        elif rule_code in ["F821", "F811", "F402"]:
                            current["other_critical"] += count
                    except ValueError:
                        pass

    # Determine status
    if current["syntax_errors"] == 0 and current["other_critical"] == 0:
        current["status"] = "resolved"
    elif current["syntax_errors"] == 0:
        current["status"] = "syntax_resolved"
    elif current["syntax_errors"] < 100:
        current["status"] = "nearly_resolved"
    else:
        current["status"] = "critical"

    return current


def calculate_weekly_metrics(historical_data: list[dict], current: dict) -> dict:
    """Calculate weekly progress metrics"""

    now = datetime.fromisoformat(current["timestamp"].replace("Z", "+00:00"))
    week_ago = now - timedelta(days=7)

    # Find baseline (oldest data or week ago)
    baseline = None
    for data_point in historical_data:
        point_time = datetime.fromisoformat(data_point["timestamp"].replace("Z", "+00:00"))
        if point_time >= week_ago:
            baseline = data_point
            break

    if not baseline and historical_data:
        baseline = historical_data[0]  # Use oldest available data

    if not baseline:
        return {"error": "No baseline data available"}

    baseline_syntax = baseline.get("current_status", {}).get("syntax_count", 0)
    current_syntax = current.get("syntax_errors", 0)

    return {
        "baseline_syntax": baseline_syntax,
        "current_syntax": current_syntax,
        "syntax_fixed": baseline_syntax - current_syntax,
        "syntax_percent_complete": ((baseline_syntax - current_syntax) / baseline_syntax * 100) if baseline_syntax > 0 else 100,
        "days_elapsed": (now - datetime.fromisoformat(baseline["timestamp"].replace("Z", "+00:00"))).days,
        "daily_fix_rate": (baseline_syntax - current_syntax) / max(1, (now - datetime.fromisoformat(baseline["timestamp"].replace("Z", "+00:00"))).days),
        "projected_completion": "Complete" if current_syntax == 0 else f"{current_syntax / max(1, (baseline_syntax - current_syntax) / max(1, (now - datetime.fromisoformat(baseline['timestamp'].replace('Z', '+00:00'))).days)):.0f} days at current rate"
    }



def generate_executive_summary(current: dict, metrics: dict, historical_data: list[dict]) -> str:
    """Generate executive summary for leadership"""

    timestamp = datetime.now().strftime("%B %d, %Y")
    status_emoji = {
        "resolved": "🟢",
        "syntax_resolved": "🟡",
        "nearly_resolved": "🟡",
        "critical": "🔴",
        "unknown": "⚪"
    }

    status = current.get("status", "unknown")
    emoji = status_emoji.get(status, "⚪")

    summary = f"""# 🚨 P0 Syntax Error Campaign - Weekly Executive Report

**Report Date:** {timestamp}
**Campaign Status:** {emoji} {status.replace('_', ' ').title()}
**Overall Health:** {'✅ DEVELOPMENT UNBLOCKED' if status in ['resolved', 'syntax_resolved'] else '🔴 CI STILL BLOCKED'}

## Executive Summary

"""

    if status == "resolved":
        summary += f"""### 🎉 CAMPAIGN SUCCESS - COMPLETE RESOLUTION

**All P0 blockers resolved!** The development team has successfully eliminated all syntax errors and critical violations. The CI pipeline is now unblocked and normal development can resume.

**Key Achievements:**
- **{metrics.get('syntax_fixed', 0):,} syntax errors** fixed over {metrics.get('days_elapsed', 0)} days
- **{metrics.get('syntax_percent_complete', 100):.1f}% completion** rate achieved
- **Daily fix rate:** {metrics.get('daily_fix_rate', 0):.0f} errors/day
- **Zero P0 violations** remaining
"""

    elif status == "syntax_resolved":
        other_critical = current.get("other_critical", 0)
        summary += f"""### 🟡 SYNTAX CAMPAIGN COMPLETE - MINOR ISSUES REMAIN

**Syntax errors eliminated!** The critical syntax blocking issues have been resolved. {other_critical:,} minor P0 violations remain but may not block CI depending on configuration.

**Progress Achieved:**
- **{metrics.get('syntax_fixed', 0):,} syntax errors** fixed over {metrics.get('days_elapsed', 0)} days
- **{metrics.get('syntax_percent_complete', 100):.1f}% syntax completion** achieved
- **{other_critical:,} remaining P0 issues** (F821, F811, F402)
- **Estimated impact:** CI likely unblocked, verification needed
"""

    elif status == "nearly_resolved":
        syntax_remaining = current.get("syntax_errors", 0)
        summary += f"""### 🟡 CAMPAIGN NEARLY COMPLETE - FINAL PUSH NEEDED

**Significant progress made!** Only {syntax_remaining:,} syntax errors remain. The team is in the final phase of the campaign.

**Progress to Date:**
- **{metrics.get('syntax_fixed', 0):,} syntax errors** fixed over {metrics.get('days_elapsed', 0)} days
- **{metrics.get('syntax_percent_complete', 0):.1f}% completion** achieved
- **{syntax_remaining:,} syntax errors** remaining
- **Projected completion:** {metrics.get('projected_completion', 'Unknown')}
"""

    else:
        syntax_remaining = current.get("syntax_errors", 0)
        summary += f"""### 🔴 CAMPAIGN IN PROGRESS - CONTINUED URGENCY

**Development still blocked.** {syntax_remaining:,} syntax errors continue to prevent CI merges. Continued focus and resources needed.

**Current Status:**
- **{metrics.get('syntax_fixed', 0):,} syntax errors** fixed over {metrics.get('days_elapsed', 0)} days
- **{metrics.get('syntax_percent_complete', 0):.1f}% completion** achieved
- **{syntax_remaining:,} syntax errors** still blocking CI
- **Daily fix rate:** {metrics.get('daily_fix_rate', 0):.0f} errors/day
"""

    # Impact assessment
    summary += """
## Business Impact Assessment

### Development Velocity
"""

    if status in ["resolved", "syntax_resolved"]:
        summary += "✅ **RESTORED** - Teams can resume normal development and deployment cycles"
    elif status == "nearly_resolved":
        summary += "🟡 **IMPROVING** - Most blocking issues resolved, final fixes in progress"
    else:
        summary += f"🔴 **IMPACTED** - All pull requests blocked, {current.get('syntax_errors', 0):,} files cannot be processed"

    summary += f"""

### Resource Allocation
- **Team focus:** {'Maintenance mode' if status == 'resolved' else 'Active campaign execution'}
- **Priority level:** {'P3 - Normal operations' if status == 'resolved' else 'P0 - All hands'}
- **Estimated completion:** {metrics.get('projected_completion', 'Unknown')}

## Recommendations

"""

    if status == "resolved":
        summary += """### ✅ Transition to Maintenance
1. **Enable monitoring** - Set up automated violation tracking
2. **Resume roadmap** - Return to planned development priorities
3. **Post-mortem** - Conduct campaign retrospective for lessons learned
4. **Prevention** - Strengthen pre-commit hooks to prevent regression
"""
    elif status == "syntax_resolved":
        summary += """### 🔍 Verification and Minor Cleanup
1. **Test CI pipeline** - Verify syntax fixes unblocked merges
2. **Address remaining P0s** - Clean up F821, F811, F402 violations
3. **Monitor for regression** - Ensure syntax errors don't return
4. **Document success** - Capture lessons learned from campaign
"""
    elif status == "nearly_resolved":
        summary += f"""### 🎯 Final Push Strategy
1. **Concentrate resources** - Focus all available developers on remaining {current.get('syntax_errors', 0)} errors
2. **Daily standups** - Increase check-in frequency for final sprint
3. **Remove blockers** - Ensure developers have support to complete fixes
4. **Celebrate progress** - Acknowledge {metrics.get('syntax_percent_complete', 0):.0f}% completion achieved
"""
    else:
        summary += """### 🚨 Escalation Required
1. **Resource reallocation** - Consider reassigning developers to syntax fixes
2. **External support** - Bring in additional technical resources if needed
3. **Timeline adjustment** - Reassess completion projections and communicate delays
4. **Process review** - Evaluate if current approach is most effective
"""

    return summary


def generate_technical_report(current: dict, metrics: dict, historical_data: list[dict]) -> str:
    """Generate detailed technical report for development teams"""

    report = f"""# 📊 Syntax Error Campaign - Technical Progress Report

**Generated:** {datetime.now().isoformat()}
**Current Status:** {current.get('syntax_errors', 0):,} syntax errors, {current.get('other_critical', 0):,} other P0 critical

## Progress Metrics

### Week-over-Week Changes
- **Baseline syntax errors:** {metrics.get('baseline_syntax', 0):,}
- **Current syntax errors:** {current.get('syntax_errors', 0):,}
- **Fixed this period:** {metrics.get('syntax_fixed', 0):,}
- **Completion rate:** {metrics.get('syntax_percent_complete', 0):.1f}%
- **Daily fix rate:** {metrics.get('daily_fix_rate', 0):.1f} errors/day

### Violation Breakdown
"""

    # Add current violation summary from Ruff
    report += """
**Current Ruff Statistics:**
```
"""

    ruff_cmd = "ruff" if run_command(["ruff", "--version"])[0] == 0 else ".venv/bin/ruff"
    exit_code, stdout, stderr = run_command([
        ruff_cmd, "check", ".", "--exclude", "signal_service_legacy", "--statistics"
    ])

    if stdout:
        # Get top 10 violation types
        lines = stdout.strip().split('\n')
        violation_lines = [line for line in lines if '\t' in line and any(c.isdigit() for c in line)][:10]
        for line in violation_lines:
            report += line + "\n"

    report += "```\n"

    # Historical trend
    if len(historical_data) > 1:
        report += "\n### Historical Trend\n"
        for _i, data_point in enumerate(historical_data[-5:]):  # Last 5 data points
            timestamp = datetime.fromisoformat(data_point["timestamp"].replace("Z", "+00:00"))
            syntax_count = data_point.get("current_status", {}).get("syntax_count", 0)
            report += f"- **{timestamp.strftime('%m/%d %H:%M')}**: {syntax_count:,} syntax errors\n"

    # Commands for developers
    report += """
## Developer Commands

### Check Current Status
```bash
# Full validation
python scripts/validate_ruff_infrastructure.py

# Track progress
python scripts/track_syntax_fix_progress.py

# Check specific module
ruff check your_module/ --exclude signal_service_legacy
```

### Fix Individual Files
```bash
# Get detailed Python error
python -m py_compile path/to/file.py

# Check Ruff perspective
ruff check path/to/file.py

# Validate fix
python -c "import ast; ast.parse(open('path/to/file.py').read())"
```

## File-Level Progress

**Top remaining files** (from latest triage):
"""

    # Try to load latest triage data for file-level details
    syntax_dir = Path("evidence/syntax_triage")
    if syntax_dir.exists():
        raw_files = list(syntax_dir.glob("syntax_errors_raw_*.json"))
        if raw_files:
            latest_raw = max(raw_files, key=lambda f: f.stat().st_mtime)
            try:
                with open(latest_raw) as f:
                    triage_data = json.load(f)

                if "syntax_violations" in triage_data:
                    # Count violations by file
                    file_counts = {}
                    for violation in triage_data["syntax_violations"]:
                        filename = violation.get("filename", "unknown")
                        file_counts[filename] = file_counts.get(filename, 0) + 1

                    # Show top files
                    sorted_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                    for filename, count in sorted_files:
                        try:
                            relative_path = str(Path(filename).relative_to(Path.cwd()))
                        except:
                            relative_path = filename
                        report += f"- `{relative_path}`: {count} errors\n"
            except:
                report += "- Unable to load file-level details\n"

    return report


def generate_github_pr_comment_template(current: dict, metrics: dict) -> str:
    """Generate template for GitHub PR comments"""

    if current.get("syntax_errors", 0) > 0:
        return f"""## 🚨 P0 Syntax Error Alert

**Current status:** {current.get('syntax_errors', 0):,} syntax errors are blocking CI for all PRs.

**This PR cannot be merged** until the P0 syntax error campaign is complete.

### Progress Update
- **Fixed so far:** {metrics.get('syntax_fixed', 0):,} errors ({metrics.get('syntax_percent_complete', 0):.1f}% complete)
- **Estimated completion:** {metrics.get('projected_completion', 'Unknown')}

### How to Help
Check if any files in your PR contain syntax errors:
```bash
# Check your files
ruff check path/to/your/files.py --exclude signal_service_legacy
python -m py_compile path/to/your/files.py
```

Track campaign progress: [Syntax Error Dashboard](evidence/syntax_progress/)

**Status will be updated automatically as fixes are applied.**
"""
    return f"""## ✅ P0 Syntax Errors Resolved

**Good news!** The P0 syntax error campaign has been completed. CI is now unblocked and this PR can proceed through normal review.

### Campaign Results
- **Total fixed:** {metrics.get('syntax_fixed', 0):,} syntax errors
- **Duration:** {metrics.get('days_elapsed', 0)} days
- **Status:** {'🎉 Fully resolved' if current.get('status') == 'resolved' else '🟡 Minor issues remain'}

Normal development workflow has resumed. Thank you for your patience during the campaign.
"""


def main():
    """Generate weekly syntax fix report"""
    print("📊 Generating weekly syntax error campaign report...")

    # Collect data
    print("📋 Loading historical progress data...")
    historical_data = load_historical_progress()

    print("🔍 Getting current status...")
    current_status = get_current_status()

    print("📈 Calculating weekly metrics...")
    metrics = calculate_weekly_metrics(historical_data, current_status)

    if "error" in metrics:
        print(f"⚠️ Warning: {metrics['error']}")
        metrics = {"baseline_syntax": 0, "current_syntax": current_status.get("syntax_errors", 0)}

    # Generate reports
    print("📝 Creating executive summary...")
    executive_summary = generate_executive_summary(current_status, metrics, historical_data)

    print("🔧 Creating technical report...")
    technical_report = generate_technical_report(current_status, metrics, historical_data)

    print("💬 Creating GitHub PR comment template...")
    pr_comment = generate_github_pr_comment_template(current_status, metrics)

    # Save outputs
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    weekly_dir = Path("evidence/weekly_reports")
    weekly_dir.mkdir(parents=True, exist_ok=True)

    # Executive summary
    exec_file = weekly_dir / f"executive_summary_{timestamp}.md"
    with open(exec_file, 'w') as f:
        f.write(executive_summary)

    # Technical report
    tech_file = weekly_dir / f"technical_report_{timestamp}.md"
    with open(tech_file, 'w') as f:
        f.write(technical_report)

    # PR comment template
    pr_file = weekly_dir / f"pr_comment_template_{timestamp}.md"
    with open(pr_file, 'w') as f:
        f.write(pr_comment)

    # Combined report
    combined_file = weekly_dir / f"weekly_syntax_report_{timestamp}.md"
    with open(combined_file, 'w') as f:
        f.write(executive_summary + "\n\n---\n\n" + technical_report)

    # Summary output
    syntax_count = current_status.get("syntax_errors", 0)
    status = current_status.get("status", "unknown")

    print(f"""
✅ Weekly report generation complete!

📊 **Current Status:**
- Syntax errors: {syntax_count:,}
- Campaign status: {status.replace('_', ' ').title()}
- CI Status: {'🟢 UNBLOCKED' if syntax_count == 0 else '🔴 BLOCKED'}

📁 **Reports Generated:**
- Executive summary: {exec_file}
- Technical report: {tech_file}
- PR comment template: {pr_file}
- Combined report: {combined_file}

💡 **Usage:**
- Share executive summary with leadership
- Use technical report for team standups
- Apply PR comment template to blocked PRs
""")

    if syntax_count == 0:
        print("🎉 **CAMPAIGN SUCCESS!** All syntax errors resolved!")
    elif syntax_count < 100:
        print(f"🟡 **NEARLY COMPLETE!** Only {syntax_count} syntax errors remaining!")
    else:
        print(f"🔴 **CONTINUED URGENCY!** {syntax_count} syntax errors still blocking CI!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
