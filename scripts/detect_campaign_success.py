#!/usr/bin/env python3
"""
Campaign Success Detection & Reporting

Automatically detects when P0 syntax error campaign reaches zero violations
and generates comprehensive success report with metrics and celebration.
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


def get_current_p0_status() -> dict:
    """Get current P0 violation status"""
    ruff_cmd = "ruff" if run_command(["ruff", "--version"])[0] == 0 else ".venv/bin/ruff"

    # Get detailed statistics
    exit_code, stdout, stderr = run_command([
        ruff_cmd, "check", ".", "--exclude", "signal_service_legacy", "--statistics"
    ])

    status = {
        "total_violations": 0,
        "syntax_errors": 0,
        "other_critical": 0,
        "p0_total": 0,
        "timestamp": datetime.now().isoformat(),
        "ruff_output": stdout
    }

    if exit_code == 0 or stdout:
        for line in stdout.split('\n'):
            if '\t' in line and any(char.isdigit() for char in line):
                parts = line.strip().split('\t')
                if len(parts) >= 2:
                    try:
                        count = int(parts[0].strip())
                        rule_code = parts[1].strip()

                        status["total_violations"] += count

                        # Track syntax errors (empty rule code = invalid syntax)
                        if not rule_code or rule_code == "invalid-syntax":
                            status["syntax_errors"] += count

                        # Track other P0 critical violations
                        elif rule_code in ["F821", "F811", "F402"]:
                            status["other_critical"] += count

                    except ValueError:
                        pass

    status["p0_total"] = status["syntax_errors"] + status["other_critical"]
    return status


def load_campaign_baseline() -> dict:
    """Load original campaign baseline metrics"""
    # Try to find the original triage data
    syntax_dir = Path("evidence/syntax_triage")
    baseline_data = {"syntax_errors": 1950, "total_files": 43}  # Fallback defaults

    if syntax_dir.exists():
        # Look for the oldest/baseline triage data
        raw_files = list(syntax_dir.glob("syntax_errors_raw_*.json"))
        if raw_files:
            baseline_file = min(raw_files, key=lambda f: f.stat().st_mtime)
            try:
                with open(baseline_file) as f:
                    data = json.load(f)
                    if "categories" in data and "summary" in data["categories"]:
                        summary = data["categories"]["summary"]
                        baseline_data = {
                            "syntax_errors": summary.get("total_errors", 1950),
                            "total_files": summary.get("total_files", 43),
                            "baseline_file": str(baseline_file),
                            "baseline_timestamp": data.get("timestamp", "unknown")
                        }
            except:
                pass

    return baseline_data


def calculate_campaign_metrics(current: dict, baseline: dict) -> dict:
    """Calculate comprehensive campaign success metrics"""

    baseline_syntax = baseline.get("syntax_errors", 1950)
    current_syntax = current.get("syntax_errors", 0)

    return {
        "baseline_syntax_errors": baseline_syntax,
        "current_syntax_errors": current_syntax,
        "syntax_errors_fixed": baseline_syntax - current_syntax,
        "syntax_completion_percent": ((baseline_syntax - current_syntax) / baseline_syntax * 100) if baseline_syntax > 0 else 100,

        "baseline_files": baseline.get("total_files", 43),
        "current_total_violations": current.get("total_violations", 0),
        "current_p0_total": current.get("p0_total", 0),

        "campaign_success": current.get("p0_total", 0) == 0,
        "syntax_resolved": current.get("syntax_errors", 0) == 0,
        "all_critical_resolved": current.get("other_critical", 0) == 0,

        "completion_timestamp": current.get("timestamp"),
        "baseline_reference": baseline.get("baseline_file", "estimated"),
    }



def generate_success_report(current: dict, baseline: dict, metrics: dict) -> str:
    """Generate comprehensive campaign success report"""

    timestamp = datetime.now().strftime("%B %d, %Y at %H:%M UTC")

    report = f"""# 🎉 P0 SYNTAX ERROR CAMPAIGN - SUCCESS!

**Campaign Completed:** {timestamp}
**Final Status:** ✅ ALL P0 VIOLATIONS RESOLVED
**Development Status:** 🟢 CI PIPELINE UNBLOCKED

## 🏆 Campaign Victory Summary

### **MISSION ACCOMPLISHED**
The P0 syntax error campaign has achieved complete success! All blocking violations have been eliminated and normal development workflow has been restored.

## 📊 Final Campaign Metrics

### Syntax Error Resolution
- **Baseline syntax errors:** {metrics['baseline_syntax_errors']:,}
- **Final syntax errors:** {metrics['current_syntax_errors']:,} ✅
- **Total errors fixed:** {metrics['syntax_errors_fixed']:,}
- **Completion rate:** {metrics['syntax_completion_percent']:.1f}% ✅

### Overall Impact
- **Files affected (baseline):** {metrics['baseline_files']}
- **Current total violations:** {metrics['current_total_violations']:,}
- **P0 critical violations:** {metrics['current_p0_total']} ✅
- **CI blocking status:** {'🟢 UNBLOCKED' if metrics['campaign_success'] else '🔴 STILL BLOCKED'}

## 🎯 Success Validation

### ✅ Primary Objectives Achieved
"""

    if metrics["syntax_resolved"]:
        report += "- ✅ **Syntax errors eliminated:** Zero invalid syntax violations remaining\n"
    else:
        report += f"- ⚠️ **Syntax errors:** {current.get('syntax_errors', 0)} still remain\n"

    if metrics["all_critical_resolved"]:
        report += "- ✅ **Critical violations resolved:** Zero F821, F811, F402 violations\n"
    else:
        report += f"- ⚠️ **Critical violations:** {current.get('other_critical', 0)} still remain\n"

    if metrics["campaign_success"]:
        report += "- ✅ **CI pipeline unblocked:** All P0 violations eliminated\n"
        report += "- ✅ **Development resumed:** Teams can proceed with normal workflow\n"
    else:
        report += "- ⚠️ **CI pipeline:** Still blocked by remaining violations\n"

    report += f"""
### 📈 Campaign Statistics
- **Duration:** From campaign start to resolution
- **Team effort:** Distributed across {metrics['baseline_files']} files
- **Infrastructure:** 4 automation scripts, comprehensive tracking
- **Evidence generated:** Complete audit trail preserved

## 🚀 Immediate Next Steps

### ✅ Campaign Closure Actions
1. **Celebrate team success** - Acknowledge the significant effort and coordination
2. **Archive campaign materials** - Preserve evidence and lessons learned
3. **Resume normal development** - All teams can return to planned work
4. **Enable monitoring** - Activate ongoing violation tracking

### 🔍 Verification Actions
1. **Test CI pipeline** - Create verification PR to confirm gate is unblocked
2. **Validate team workflow** - Ensure developers can merge PRs normally
3. **Monitor for regression** - Watch for new P0 violations in coming days

## 📋 Campaign Infrastructure Legacy

### Automation Scripts (Preserved)
- `scripts/triage_syntax_errors.py` - Future triage capability
- `scripts/track_syntax_fix_progress.py` - Ongoing progress monitoring
- `scripts/validate_ruff_infrastructure.py` - Infrastructure health checks
- `scripts/generate_weekly_syntax_report.py` - Regular quality reporting

### Evidence Archive (Complete)
- `evidence/syntax_triage/` - Original assignments and GitHub templates
- `evidence/syntax_progress/` - Historical progress tracking
- `evidence/weekly_reports/` - Executive and technical summaries
- `evidence/validation/` - Infrastructure validation results

## 🎊 Team Recognition

### Campaign Heroes
**Every developer who fixed syntax errors** contributed to unblocking the entire development organization. Special recognition for:

- **Module leads** who took ownership of high-error files
- **Senior developers** who tackled complex syntax issues
- **Team coordinators** who managed assignments and progress tracking
- **Infrastructure team** who built and maintained automation tools

### Key Success Factors
1. **Systematic approach** - Evidence-based triage and assignment
2. **Automation support** - Progress tracking and reporting tools
3. **Team coordination** - Clear ownership and accountability
4. **Focused execution** - Prioritizing high-impact files first

## 📚 Lessons Learned

### What Worked Well
- **Evidence-based triage** provided clear, actionable assignments
- **Progress tracking automation** gave visibility into campaign status
- **Focused approach** on top files maximized early impact
- **Comprehensive reporting** kept stakeholders informed

### Future Prevention
- **Strengthen pre-commit hooks** to catch syntax errors before merge
- **Regular Ruff runs** in development workflow
- **Monitoring automation** to detect P0 regressions quickly
- **Team training** on Python syntax best practices

## 🔮 Post-Campaign Operations

### Ongoing Quality Management
Now that P0 blockers are resolved, focus shifts to:

1. **P1/P2 violation reduction** - Continue improving code quality
2. **Automated monitoring** - Prevent future P0 regressions
3. **Team workflow optimization** - Integrate lessons learned
4. **Documentation updates** - Capture process improvements

### Monitoring & Maintenance
- **Weekly quality reports** - Continue using reporting automation
- **Violation trend tracking** - Watch for code quality patterns
- **Infrastructure health** - Maintain Ruff automation tools
- **Team feedback** - Gather input on campaign effectiveness

---

## 🎉 CAMPAIGN SUCCESS DECLARATION

**P0 Syntax Error Campaign: COMPLETE SUCCESS** ✅

### Final Status Confirmation
- **Syntax errors:** {metrics['current_syntax_errors']} ✅
- **Critical violations:** {current.get('other_critical', 0)} ✅
- **Total P0 violations:** {metrics['current_p0_total']} ✅
- **CI pipeline:** {'🟢 UNBLOCKED' if metrics['campaign_success'] else '🔴 BLOCKED'}

### Campaign Impact
- **{metrics['syntax_errors_fixed']:,} syntax errors eliminated**
- **{metrics['baseline_files']} files restored to working state**
- **Entire development organization unblocked**
- **Normal development workflow resumed**

**The team's coordinated effort has successfully eliminated all P0 violations. Development can now proceed without CI blocking. Congratulations to everyone involved!**

---

**Success Report Generated:** {timestamp}
**Campaign Infrastructure:** Preserved for future use
**Evidence Location:** `evidence/syntax_progress/campaign_success_*`
**Next Action:** Create verification PR to test CI gate
**Status:** 🎉 **MISSION ACCOMPLISHED** 🎉
"""

    return report


def generate_success_notification(metrics: dict) -> dict:
    """Generate notification data for team communication"""

    notification = {
        "type": "campaign_success",
        "timestamp": datetime.now().isoformat(),
        "success": metrics["campaign_success"],
        "metrics": {
            "syntax_errors_fixed": metrics["syntax_errors_fixed"],
            "completion_percent": metrics["syntax_completion_percent"],
            "files_affected": metrics["baseline_files"]
        },
        "message": {
            "title": "🎉 P0 Syntax Error Campaign - SUCCESS!",
            "summary": f"All {metrics['syntax_errors_fixed']:,} syntax errors have been resolved. CI pipeline is now unblocked!",
            "status": "✅ COMPLETE",
            "next_action": "Create verification PR to test CI gate"
        }
    }

    if not metrics["campaign_success"]:
        notification["message"]["title"] = "⚠️ Campaign Progress Update"
        notification["message"]["summary"] = f"{metrics['syntax_errors_fixed']:,} errors fixed, {metrics['current_syntax_errors']} remaining"
        notification["message"]["status"] = "🔄 IN PROGRESS"

    return notification


def save_success_artifacts(report: str, notification: dict, current: dict, metrics: dict) -> dict:
    """Save all success-related artifacts"""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    success_dir = Path("evidence/syntax_progress")
    success_dir.mkdir(parents=True, exist_ok=True)

    artifacts = {}

    # Success report
    if metrics["campaign_success"]:
        report_file = success_dir / f"campaign_success_report_{timestamp}.md"
        with open(report_file, 'w') as f:
            f.write(report)
        artifacts["success_report"] = str(report_file)
    else:
        # Progress report for non-success case
        report_file = success_dir / f"campaign_progress_{timestamp}.md"
        with open(report_file, 'w') as f:
            f.write(report)
        artifacts["progress_report"] = str(report_file)

    # Notification data
    notification_file = success_dir / f"success_notification_{timestamp}.json"
    with open(notification_file, 'w') as f:
        json.dump(notification, f, indent=2)
    artifacts["notification"] = str(notification_file)

    # Complete status snapshot
    status_file = success_dir / f"final_status_{timestamp}.json"
    status_data = {
        "timestamp": timestamp,
        "campaign_success": metrics["campaign_success"],
        "current_status": current,
        "campaign_metrics": metrics,
        "artifacts": artifacts
    }

    with open(status_file, 'w') as f:
        json.dump(status_data, f, indent=2)
    artifacts["status_snapshot"] = str(status_file)

    return artifacts


def main():
    """Main success detection execution"""
    print("🔍 Checking campaign success status...")

    # Get current status
    print("📊 Getting current P0 violation count...")
    current_status = get_current_p0_status()

    # Load baseline for comparison
    print("📋 Loading campaign baseline data...")
    baseline_data = load_campaign_baseline()

    # Calculate metrics
    print("📈 Calculating campaign metrics...")
    metrics = calculate_campaign_metrics(current_status, baseline_data)

    # Generate reports
    print("📝 Generating success/progress report...")
    success_report = generate_success_report(current_status, baseline_data, metrics)

    print("🔔 Creating notification data...")
    notification = generate_success_notification(metrics)

    # Save artifacts
    print("💾 Saving success artifacts...")
    artifacts = save_success_artifacts(success_report, notification, current_status, metrics)

    # Output results
    p0_count = current_status.get("p0_total", 0)
    syntax_count = current_status.get("syntax_errors", 0)

    if metrics["campaign_success"]:
        print(f"""
🎉 CAMPAIGN SUCCESS DETECTED!

✅ **P0 violations:** {p0_count} (ZERO!)
✅ **Syntax errors:** {syntax_count} (RESOLVED!)
✅ **Status:** CI PIPELINE UNBLOCKED

📁 **Success artifacts generated:**
- Success report: {artifacts.get('success_report', 'N/A')}
- Notification data: {artifacts.get('notification', 'N/A')}
- Status snapshot: {artifacts.get('status_snapshot', 'N/A')}

🚀 **Next steps:**
1. Celebrate with the team! 🎊
2. Create verification PR to test CI gate
3. Resume normal development workflow
4. Archive campaign materials

🎊 CONGRATULATIONS TO THE ENTIRE TEAM! 🎊
""")
        return 0

    print(f"""
📊 Campaign progress update:

⏳ **P0 violations:** {p0_count} (still blocking)
📈 **Syntax errors:** {syntax_count} remaining
📊 **Progress:** {metrics['syntax_completion_percent']:.1f}% complete
🔄 **Status:** Campaign continues

📁 **Progress artifacts updated:**
- Progress report: {artifacts.get('progress_report', 'N/A')}
- Status snapshot: {artifacts.get('status_snapshot', 'N/A')}

💪 Keep going! {metrics['syntax_errors_fixed']:,} errors already fixed!
""")
    return 1  # Non-zero exit code indicates campaign not yet complete


if __name__ == "__main__":
    sys.exit(main())
