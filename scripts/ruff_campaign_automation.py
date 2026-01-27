#!/usr/bin/env python3
"""
Ruff Campaign Automation - Integrated Workflow

Combines campaign success detection with automated gate verification
to provide seamless P0 campaign completion and CI testing.
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

# Import campaign success detection functions
sys.path.append(str(Path(__file__).parent))
try:
    from detect_campaign_success import (
        calculate_campaign_metrics,
        generate_success_notification,
        generate_success_report,
        get_current_p0_status,
        load_campaign_baseline,
        save_success_artifacts,
    )
except ImportError as e:
    print(f"❌ Error importing campaign success detection: {e}")
    print("Ensure detect_campaign_success.py is in the same directory")
    sys.exit(1)


def run_command(cmd: list, cwd: str | None = None) -> tuple[int, str, str]:
    """Run shell command and return exit code, stdout, stderr"""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, cwd=cwd
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)


def check_gate_verification_available() -> bool:
    """Check if gate verification script is available"""
    script_dir = Path(__file__).parent
    gate_script = script_dir / "verify_ruff_gate.sh"

    if not gate_script.exists():
        print(f"⚠️ Gate verification script not found: {gate_script}")
        return False

    if not gate_script.is_file():
        print(f"⚠️ Gate verification script is not a file: {gate_script}")
        return False

    # Check if script is executable
    if not gate_script.stat().st_mode & 0o111:
        print(f"⚠️ Making gate verification script executable: {gate_script}")
        gate_script.chmod(gate_script.stat().st_mode | 0o111)

    return True


def run_campaign_success_detection() -> dict:
    """Run campaign success detection and return results"""
    print("🔍 Phase 1: Campaign Success Detection")
    print("=" * 50)

    # Get current status
    print("📊 Analyzing current P0 violation status...")
    current_status = get_current_p0_status()

    # Load baseline
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

    return {
        "current_status": current_status,
        "baseline_data": baseline_data,
        "metrics": metrics,
        "success_report": success_report,
        "notification": notification,
        "artifacts": artifacts
    }


def run_gate_verification() -> dict:
    """Run gate verification and return results"""
    print("\n🔍 Phase 2: CI Gate Verification")
    print("=" * 50)

    script_dir = Path(__file__).parent
    gate_script = script_dir / "verify_ruff_gate.sh"

    print(f"🚀 Executing gate verification: {gate_script}")

    # Run the gate verification script
    exit_code, stdout, stderr = run_command([str(gate_script)], cwd=str(script_dir.parent))

    # Parse results
    verification_result = {
        "exit_code": exit_code,
        "success": exit_code == 0,
        "stdout": stdout,
        "stderr": stderr,
        "timestamp": datetime.now().isoformat()
    }

    # Try to find and load the verification evidence
    evidence_dir = script_dir.parent / "evidence" / "gate_verification"
    if evidence_dir.exists():
        # Look for the most recent verification file
        verification_files = list(evidence_dir.glob("verification_*.json"))
        if verification_files:
            latest_file = max(verification_files, key=lambda f: f.stat().st_mtime)
            try:
                with open(latest_file) as f:
                    evidence_data = json.load(f)
                verification_result["evidence"] = evidence_data
                verification_result["evidence_file"] = str(latest_file)
            except Exception as e:
                print(f"⚠️ Could not load verification evidence: {e}")

    return verification_result


def save_integrated_automation_report(
    success_detection: dict,
    gate_verification: dict
) -> str:
    """Save comprehensive automation workflow report"""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    evidence_dir = Path("evidence/automation_workflow")
    evidence_dir.mkdir(parents=True, exist_ok=True)

    report_file = evidence_dir / f"integrated_workflow_report_{timestamp}.md"

    # Determine overall success
    campaign_success = success_detection["metrics"]["campaign_success"]
    gate_success = gate_verification["success"]
    overall_success = campaign_success and gate_success

    # Generate comprehensive report
    report_content = f"""# 🤖 Ruff Campaign Automation - Integrated Workflow Report

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}
**Workflow Status:** {'✅ COMPLETE SUCCESS' if overall_success else '⚠️ PARTIAL SUCCESS' if campaign_success else '❌ CAMPAIGN IN PROGRESS'}
**Automation Version:** Integrated P0 Campaign + Gate Verification

## 🎯 Automation Summary

### Overall Results
- **Campaign Success Detection:** {'✅ SUCCESS' if campaign_success else '🔄 IN PROGRESS'}
- **CI Gate Verification:** {'✅ SUCCESS' if gate_success else '❌ FAILED' if gate_verification['exit_code'] != 2 else '⏰ TIMEOUT'}
- **Workflow Integration:** {'✅ SEAMLESS' if overall_success else '⚠️ PARTIAL'}

## 📊 Phase 1: Campaign Success Detection

### P0 Violation Status
- **Current P0 violations:** {success_detection['current_status'].get('p0_total', 'unknown')}
- **Syntax errors:** {success_detection['current_status'].get('syntax_errors', 'unknown')}
- **Other critical violations:** {success_detection['current_status'].get('other_critical', 'unknown')}
- **Campaign success:** {'✅ YES' if campaign_success else '❌ NO'}

### Campaign Metrics
- **Baseline syntax errors:** {success_detection['metrics'].get('baseline_syntax_errors', 'unknown')}
- **Errors fixed:** {success_detection['metrics'].get('syntax_errors_fixed', 'unknown')}
- **Completion percentage:** {success_detection['metrics'].get('syntax_completion_percent', 0):.1f}%

### Generated Artifacts
"""

    # Add artifacts from success detection
    for artifact_type, path in success_detection["artifacts"].items():
        report_content += f"- **{artifact_type.replace('_', ' ').title()}:** `{path}`\n"

    report_content += f"""
## 🔍 Phase 2: CI Gate Verification

### Verification Status
- **Gate verification executed:** {'✅ YES' if 'exit_code' in gate_verification else '❌ FAILED TO START'}
- **CI tests passed:** {'✅ YES' if gate_success else '❌ NO' if gate_verification.get('exit_code', 1) == 1 else '⏰ TIMEOUT'}
- **Exit code:** {gate_verification.get('exit_code', 'N/A')}

### Verification Details
"""

    if "evidence" in gate_verification:
        evidence = gate_verification["evidence"]
        report_content += f"""- **PR URL:** {evidence.get('verification_run', {}).get('pr_url', 'N/A')}
- **Branch:** {evidence.get('verification_run', {}).get('branch', 'N/A')}
- **CI Status:** {evidence.get('results', {}).get('ci_status', 'N/A')}
- **Gate Functional:** {'✅ YES' if evidence.get('results', {}).get('gate_functional', False) else '❌ NO'}
- **Evidence File:** `{gate_verification.get('evidence_file', 'N/A')}`
"""
    else:
        report_content += "- **Evidence:** Not available (verification may have failed to complete)\n"

    if overall_success:
        report_content += f"""
## 🎉 SUCCESS - Campaign & Verification Complete!

### 🏆 Achievement Summary
The P0 syntax error campaign has achieved **complete success** and CI gate functionality has been **verified operational**.

### ✅ Confirmed Results
1. **All P0 violations resolved** - Zero blocking issues remaining
2. **CI pipeline unblocked** - GitHub Actions passing all checks
3. **Gate verification passed** - Automated PR test successful
4. **Development workflow restored** - Teams can proceed normally

### 🚀 Immediate Actions
1. **Celebrate team success** 🎊 - Acknowledge the coordinated effort
2. **Announce to teams** - Development workflow is fully operational
3. **Archive campaign materials** - Preserve evidence and lessons learned
4. **Resume normal work** - All blocking issues eliminated

### 📈 Campaign Impact
- **{success_detection['metrics'].get('syntax_errors_fixed', 0):,} syntax errors eliminated**
- **{success_detection['metrics'].get('baseline_files', 0)} files restored to working state**
- **Entire development organization unblocked**
- **Automated verification confirms infrastructure working**

## 🔮 Post-Campaign Operations

### Ongoing Quality Management
1. **Monitor for regressions** - Watch for new P0 violations
2. **Continue P1/P2 reduction** - Improve overall code quality
3. **Strengthen automation** - Prevent future P0 campaigns
4. **Team process improvements** - Integrate lessons learned

### Infrastructure Maintenance
- **Weekly quality reports** continue via existing automation
- **Violation trend tracking** monitors ongoing code quality
- **Infrastructure health checks** validate Ruff automation
- **Evidence preservation** maintains complete audit trail
"""
    else:
        if campaign_success and not gate_success:
            report_content += """
## ⚠️ Campaign Success but Gate Verification Issues

### Current Status
- **P0 Campaign:** ✅ Successfully completed
- **CI Gate:** ❌ Verification encountered issues

### Investigation Required
1. **Check GitHub Actions logs** - Review CI workflow execution
2. **Manual PR test** - Create test PR to validate CI manually
3. **Infrastructure review** - Verify Ruff automation configuration
4. **Team communication** - Update on verification status

### Next Steps
1. Investigate gate verification failure
2. Test CI pipeline manually
3. Resolve any infrastructure issues
4. Re-run verification once fixed
"""
        else:
            report_content += f"""
## 🔄 Campaign Still in Progress

### Current Status
- **P0 violations remaining:** {success_detection['current_status'].get('p0_total', 'unknown')}
- **Progress:** {success_detection['metrics'].get('syntax_completion_percent', 0):.1f}% complete

### Continue Campaign Execution
1. **Track remaining fixes** - Use progress monitoring tools
2. **Focus on high-impact files** - Prioritize files with most errors
3. **Regular status updates** - Continue weekly reporting
4. **Re-run automation** - Check for success periodically
"""

    report_content += """
## 📋 Workflow Artifacts

### Success Detection Artifacts
"""
    for artifact_type, path in success_detection["artifacts"].items():
        report_content += f"- `{path}`\n"

    if "evidence_file" in gate_verification:
        report_content += f"""
### Gate Verification Artifacts
- `{gate_verification["evidence_file"]}`
"""

    report_content += f"""
### Automation Infrastructure
- **Success Detection:** `scripts/detect_campaign_success.py`
- **Gate Verification:** `scripts/verify_ruff_gate.sh`
- **Integrated Workflow:** `scripts/ruff_campaign_automation.py`
- **Progress Tracking:** `scripts/track_syntax_fix_progress.py`

## 🤖 Automation Summary

**Integrated P0 Campaign Automation: {'✅ COMPLETE SUCCESS' if overall_success else '⚠️ PARTIAL SUCCESS' if campaign_success else '🔄 MONITORING'}**

### Workflow Status
- **Phase 1 (Success Detection):** {'✅ COMPLETE' if campaign_success else '🔄 MONITORING'}
- **Phase 2 (Gate Verification):** {'✅ COMPLETE' if gate_success else '❌ FAILED' if gate_verification.get('exit_code', 1) == 1 else '⏰ TIMEOUT'}
- **Overall Integration:** {'✅ SEAMLESS' if overall_success else 'PARTIAL/FAILED'}

### Evidence Preservation
All automation results, evidence files, and workflow artifacts have been preserved for audit and future reference.

---

**Report Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}
**Automation Status:** {'🎉 MISSION ACCOMPLISHED' if overall_success else '🔄 CAMPAIGN CONTINUES' if not campaign_success else '🔍 INVESTIGATION NEEDED'}
**Next Action:** {'Celebrate and resume normal development' if overall_success else 'Continue campaign execution' if not campaign_success else 'Investigate gate verification issues'}
"""

    # Save the report
    with open(report_file, 'w') as f:
        f.write(report_content)

    return str(report_file)


def main():
    """Main integrated automation workflow"""
    print("🤖 Ruff Campaign Automation - Integrated Workflow")
    print("=" * 60)
    print("Purpose: Automated P0 campaign success detection + CI gate verification")
    print("Phases: 1) Success Detection → 2) Gate Verification")
    print()

    try:
        # Phase 1: Campaign Success Detection
        success_detection = run_campaign_success_detection()
        campaign_success = success_detection["metrics"]["campaign_success"]

        print("\n📊 Phase 1 Results:")
        print(f"   • P0 violations: {success_detection['current_status'].get('p0_total', 'unknown')}")
        print(f"   • Campaign success: {'✅ YES' if campaign_success else '❌ NO'}")
        print(f"   • Progress: {success_detection['metrics'].get('syntax_completion_percent', 0):.1f}%")

        # Phase 2: Gate Verification (only if campaign successful)
        gate_verification = {"success": False, "exit_code": -1}

        if campaign_success:
            print("\n🎉 Campaign success detected! Proceeding to gate verification...")

            if check_gate_verification_available():
                gate_verification = run_gate_verification()

                print("\n📊 Phase 2 Results:")
                print(f"   • Gate verification: {'✅ SUCCESS' if gate_verification['success'] else '❌ FAILED' if gate_verification['exit_code'] == 1 else '⏰ TIMEOUT'}")
                print(f"   • Exit code: {gate_verification['exit_code']}")
            else:
                print("\n⚠️ Gate verification unavailable - skipping Phase 2")
                gate_verification = {
                    "success": False,
                    "exit_code": -2,
                    "error": "Gate verification script not available"
                }
        else:
            print("\n🔄 Campaign still in progress - skipping gate verification")
            print(f"   • Remaining P0 violations: {success_detection['current_status'].get('p0_total', 'unknown')}")

        # Generate integrated report
        print("\n📝 Generating integrated workflow report...")
        report_file = save_integrated_automation_report(success_detection, gate_verification)
        print(f"   • Report saved: {report_file}")

        # Final summary
        print("\n" + "=" * 60)
        print("🤖 INTEGRATED AUTOMATION COMPLETE")
        print("=" * 60)

        if campaign_success and gate_verification["success"]:
            print("🎉 COMPLETE SUCCESS!")
            print("   ✅ P0 campaign completed")
            print("   ✅ CI gate verified working")
            print("   ✅ Development workflow restored")
            print("\n🚀 Next steps:")
            print("   1. Celebrate team success! 🎊")
            print("   2. Announce to development teams")
            print("   3. Archive campaign materials")
            print("   4. Resume normal development")
            return 0

        if campaign_success:
            print("⚠️ PARTIAL SUCCESS")
            print("   ✅ P0 campaign completed")
            print("   ❌ Gate verification issues")
            print("\n🔍 Next steps:")
            print("   1. Investigate CI gate issues")
            print("   2. Test pipeline manually")
            print("   3. Re-run verification")
            return 1

        print("🔄 CAMPAIGN IN PROGRESS")
        print(f"   🔄 {success_detection['metrics'].get('syntax_completion_percent', 0):.1f}% complete")
        print(f"   📊 {success_detection['current_status'].get('p0_total', 'unknown')} P0 violations remaining")
        print("\n💪 Next steps:")
        print("   1. Continue syntax error fixes")
        print("   2. Track progress regularly")
        print("   3. Re-run automation periodically")
        return 2

    except Exception as e:
        print(f"\n❌ Automation workflow error: {e}")
        print("Check logs and infrastructure health")
        return 3


if __name__ == "__main__":
    sys.exit(main())
