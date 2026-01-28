#!/usr/bin/env python3
"""
Ruff Automation Script for signal-service-codex-review

Provides comprehensive linting workflow with evidence generation and CI integration.
Excludes signal_service_legacy and focuses on codex-review sources.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_command(cmd: list[str], capture_output: bool = True) -> tuple[int, str, str]:
    """Run shell command and return exit code, stdout, stderr"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            cwd=Path.cwd(),
            check=False
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)


def setup_ruff_environment() -> bool:
    """Ensure Ruff is available in the environment"""
    print("🔧 Setting up Ruff environment...")

    # Check if ruff is available
    exit_code, _, _ = run_command(["ruff", "--version"])
    if exit_code == 0:
        print("✅ Ruff already available")
        return True

    # Try to activate virtual environment and install
    venv_path = Path(".venv")
    if not venv_path.exists():
        print("📦 Creating virtual environment...")
        exit_code, _, stderr = run_command([sys.executable, "-m", "venv", ".venv"])
        if exit_code != 0:
            print(f"❌ Failed to create virtual environment: {stderr}")
            return False

    print("📦 Installing Ruff...")
    pip_cmd = [".venv/bin/pip", "install", "ruff"] if sys.platform != "win32" else [".venv\\Scripts\\pip", "install", "ruff"]
    exit_code, _, stderr = run_command(pip_cmd)

    if exit_code != 0:
        print(f"❌ Failed to install Ruff: {stderr}")
        return False

    print("✅ Ruff environment ready")
    return True


def get_ruff_command() -> str:
    """Get the appropriate Ruff command for the environment"""
    # Try activated environment first
    exit_code, _, _ = run_command(["ruff", "--version"])
    if exit_code == 0:
        return "ruff"

    # Try virtual environment
    venv_ruff = ".venv/bin/ruff" if sys.platform != "win32" else ".venv\\Scripts\\ruff"
    if Path(venv_ruff).exists():
        return venv_ruff

    raise RuntimeError("Ruff not found in environment or virtual environment")


def run_ruff_check(fix_mode: bool = False, unsafe_fixes: bool = False) -> dict:
    """Run Ruff check with comprehensive reporting"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        ruff_cmd = get_ruff_command()
    except RuntimeError as e:
        return {"error": str(e), "timestamp": timestamp}

    # Build command
    cmd = [ruff_cmd, "check", ".", "--statistics"]
    if fix_mode:
        cmd.append("--fix")
    if unsafe_fixes:
        cmd.append("--unsafe-fixes")

    print(f"🔍 Running: {' '.join(cmd)}")

    # Run command
    exit_code, stdout, stderr = run_command(cmd)

    # Parse results
    result = {
        "timestamp": timestamp,
        "command": " ".join(cmd),
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "fix_mode": fix_mode,
        "unsafe_fixes": unsafe_fixes
    }

    # Extract statistics
    if "Found" in stdout:
        lines = stdout.strip().split('\n')
        for line in lines:
            if "Found" in line and "errors" in line:
                result["summary"] = line.strip()
                break

    # Extract violation counts
    violations = {}
    for line in stdout.split('\n'):
        if '\t' in line and any(char.isdigit() for char in line):
            parts = line.strip().split('\t')
            if len(parts) >= 2:
                try:
                    count = int(parts[0].strip())
                    rule_code = parts[1].strip() if len(parts) > 1 else "unknown"
                    violations[rule_code] = count
                except ValueError:
                    pass

    result["violations"] = violations
    result["total_violations"] = sum(violations.values())

    return result


def generate_evidence_report(results: list[dict]) -> str:
    """Generate comprehensive evidence report"""
    report = f"""# Ruff Linting Evidence Report

## Summary
**Generated:** {datetime.now().isoformat()}
**Repository:** signal-service-codex-review
**Exclusions:** signal_service_legacy

"""

    if not results:
        report += "❌ **No results to report**\n"
        return report

    # Latest result summary
    latest = results[-1]
    if "error" in latest:
        report += f"❌ **Error:** {latest['error']}\n\n"
        return report

    report += f"""## Latest Scan Results
**Command:** `{latest['command']}`
**Exit Code:** {latest['exit_code']}
**Total Violations:** {latest.get('total_violations', 'Unknown')}

"""

    if 'summary' in latest:
        report += f"**Summary:** {latest['summary']}\n\n"

    # Violation breakdown
    if latest.get('violations'):
        report += "### Top Violations\n"
        sorted_violations = sorted(latest['violations'].items(), key=lambda x: x[1], reverse=True)
        for rule_code, count in sorted_violations[:10]:
            report += f"- **{rule_code}:** {count:,} occurrences\n"
        report += "\n"

    # Historical comparison if multiple runs
    if len(results) > 1:
        previous = results[-2]
        current_total = latest.get('total_violations', 0)
        previous_total = previous.get('total_violations', 0)

        if current_total < previous_total:
            improvement = previous_total - current_total
            report += f"✅ **Improvement:** Reduced violations by {improvement:,}\n\n"
        elif current_total > previous_total:
            regression = current_total - previous_total
            report += f"⚠️ **Regression:** Increased violations by {regression:,}\n\n"
        else:
            report += "📊 **Stable:** No change in violation count\n\n"

    # Detailed command output
    report += f"""### Detailed Output
```
{latest['stdout']}
```

"""

    if latest['stderr']:
        report += f"""### Errors/Warnings
```
{latest['stderr']}
```

"""

    return report


def run_workflow(args):
    """Execute the complete Ruff workflow"""
    print("🚀 Starting Ruff workflow for signal-service-codex-review")

    # Setup environment
    if not setup_ruff_environment():
        print("❌ Failed to setup Ruff environment")
        return 1

    results = []

    # Phase 1: Initial check
    print("\n📋 Phase 1: Initial violation scan")
    initial_result = run_ruff_check(fix_mode=False, unsafe_fixes=False)
    results.append(initial_result)

    if "error" in initial_result:
        print(f"❌ Error in initial check: {initial_result['error']}")
        return 1

    print(f"📊 Found {initial_result.get('total_violations', 'unknown')} violations")

    # Phase 2: Auto-fix (if requested)
    if args.fix:
        print("\n🔧 Phase 2: Applying auto-fixes")
        fix_result = run_ruff_check(fix_mode=True, unsafe_fixes=args.unsafe_fixes)
        results.append(fix_result)

        if "error" not in fix_result:
            print("✅ Auto-fix completed")

            # Phase 3: Final validation
            print("\n✅ Phase 3: Final validation scan")
            final_result = run_ruff_check(fix_mode=False, unsafe_fixes=False)
            results.append(final_result)

            remaining = final_result.get('total_violations', 0)
            print(f"📊 {remaining} violations remaining")
        else:
            print(f"❌ Error in auto-fix: {fix_result['error']}")

    # Generate evidence report
    print("\n📝 Generating evidence report...")
    evidence_report = generate_evidence_report(results)

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    evidence_file = f"ruff_evidence_{timestamp}.md"
    results_file = f"ruff_results_{timestamp}.json"

    with open(evidence_file, 'w') as f:
        f.write(evidence_report)

    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"📋 Evidence report: {evidence_file}")
    print(f"📊 Raw results: {results_file}")

    # Git status check
    print("\n📦 Checking git status...")
    exit_code, stdout, stderr = run_command(["git", "status", "--porcelain"])
    if exit_code == 0 and stdout.strip():
        print("📝 Files modified by Ruff:")
        for line in stdout.strip().split('\n'):
            print(f"  {line}")
        print("\n💡 Run 'git add .' and 'git commit' to save changes")
    else:
        print("✅ No files modified")

    # Final status
    final_violations = results[-1].get('total_violations', 0) if results else 0
    if final_violations == 0:
        print("\n🎉 Repository is Ruff-compliant!")
        return 0
    print(f"\n⚠️  {final_violations} violations remain - see evidence report for details")
    return 0 if args.allow_violations else 1


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Comprehensive Ruff linting workflow for signal-service-codex-review",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_ruff.py                    # Check only
  python scripts/run_ruff.py --fix              # Check and auto-fix
  python scripts/run_ruff.py --fix --unsafe     # Include unsafe fixes
  python scripts/run_ruff.py --ci               # CI mode (fail on violations)
        """
    )

    parser.add_argument(
        "--fix",
        action="store_true",
        help="Apply auto-fixes where possible"
    )

    parser.add_argument(
        "--unsafe-fixes",
        action="store_true",
        help="Apply unsafe fixes (use with --fix)"
    )

    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI mode - fail on remaining violations"
    )

    parser.add_argument(
        "--allow-violations",
        action="store_true",
        help="Exit successfully even with remaining violations"
    )

    args = parser.parse_args()

    # CI mode implies strict checking
    if args.ci:
        args.allow_violations = False

    try:
        exit_code = run_workflow(args)
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏸️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
