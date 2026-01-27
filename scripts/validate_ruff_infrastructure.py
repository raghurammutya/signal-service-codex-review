#!/usr/bin/env python3
"""
Ruff Infrastructure Validation Script

Validates the actual Ruff implementation against stated metrics and infrastructure,
providing evidence-based verification of the linting methodology.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    """Run shell command and return exit code, stdout, stderr"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)


def validate_ruff_installation() -> dict:
    """Validate Ruff is properly installed and configured"""
    validation = {"ruff_installation": {}}

    # Check Ruff availability
    exit_code, stdout, stderr = run_command(["ruff", "--version"])
    if exit_code == 0:
        validation["ruff_installation"]["available"] = True
        validation["ruff_installation"]["version"] = stdout.strip()
    else:
        # Try virtual environment
        exit_code, stdout, stderr = run_command([".venv/bin/ruff", "--version"])
        if exit_code == 0:
            validation["ruff_installation"]["available"] = True
            validation["ruff_installation"]["version"] = stdout.strip()
            validation["ruff_installation"]["location"] = "virtual_environment"
        else:
            validation["ruff_installation"]["available"] = False
            validation["ruff_installation"]["error"] = stderr

    return validation


def validate_configuration_files() -> dict:
    """Validate configuration files exist and are properly structured"""
    validation = {"configuration": {}}

    # Check pyproject.toml
    pyproject_path = Path("pyproject.toml")
    if pyproject_path.exists():
        validation["configuration"]["pyproject_toml"] = {"exists": True}
        try:
            with open(pyproject_path) as f:
                content = f.read()
                validation["configuration"]["pyproject_toml"]["has_ruff_config"] = "[tool.ruff" in content
                validation["configuration"]["pyproject_toml"]["excludes_legacy"] = "signal_service_legacy" in content
        except Exception as e:
            validation["configuration"]["pyproject_toml"]["read_error"] = str(e)
    else:
        validation["configuration"]["pyproject_toml"] = {"exists": False}

    # Check .ruffignore
    ruffignore_path = Path(".ruffignore")
    validation["configuration"]["ruffignore"] = {"exists": ruffignore_path.exists()}

    return validation


def get_actual_violation_counts() -> dict:
    """Get actual violation counts from Ruff"""
    validation = {"actual_violations": {}}

    # Get statistics with exclusions
    ruff_cmd = "ruff" if run_command(["ruff", "--version"])[0] == 0 else ".venv/bin/ruff"

    exit_code, stdout, stderr = run_command([
        ruff_cmd, "check", ".", "--exclude", "signal_service_legacy", "--statistics"
    ])

    if exit_code != 0 and not stdout:
        validation["actual_violations"]["error"] = stderr
        return validation

    # Parse statistics
    violations = {}
    total_violations = 0

    for line in stdout.split('\n'):
        if '\t' in line and any(char.isdigit() for char in line):
            parts = line.strip().split('\t')
            if len(parts) >= 2:
                try:
                    count = int(parts[0].strip())
                    rule_code = parts[1].strip() if parts[1].strip() else "invalid-syntax"
                    violations[rule_code] = count
                    total_violations += count
                except ValueError:
                    pass

    # Extract summary line
    for line in stdout.split('\n'):
        if "Found" in line and "errors" in line:
            validation["actual_violations"]["summary"] = line.strip()
            break

    validation["actual_violations"]["by_rule"] = violations
    validation["actual_violations"]["total"] = total_violations

    # Check critical violations (P0)
    p0_rules = ["F821", "F811", "F402"]  # Removed E999 as it's deprecated
    p0_count = sum(violations.get(rule, 0) for rule in p0_rules)
    validation["actual_violations"]["p0_critical"] = p0_count

    # Add invalid-syntax which is critical but not a standard rule code
    invalid_syntax = violations.get("invalid-syntax", 0)
    validation["actual_violations"]["invalid_syntax"] = invalid_syntax
    validation["actual_violations"]["p0_total"] = p0_count + invalid_syntax

    return validation


def validate_scripts() -> dict:
    """Validate automation scripts exist and are executable"""
    validation = {"scripts": {}}

    scripts_to_check = [
        "scripts/run_ruff.py",
        "scripts/triage_ruff_violations.py",
        "scripts/manage_ruff_exemptions.py"
    ]

    for script in scripts_to_check:
        script_path = Path(script)
        script_name = script_path.name

        validation["scripts"][script_name] = {
            "exists": script_path.exists(),
            "executable": script_path.exists() and script_path.stat().st_mode & 0o111 != 0
        }

        if script_path.exists():
            validation["scripts"][script_name]["size"] = script_path.stat().st_size

    return validation


def validate_ci_workflows() -> dict:
    """Validate CI workflow files exist"""
    validation = {"ci_workflows": {}}

    workflows_to_check = [
        ".github/workflows/ruff-lint.yml",
        ".github/workflows/ruff-backlog-tracker.yml"
    ]

    for workflow in workflows_to_check:
        workflow_path = Path(workflow)
        workflow_name = workflow_path.name

        validation["ci_workflows"][workflow_name] = {"exists": workflow_path.exists()}

        if workflow_path.exists():
            try:
                with open(workflow_path) as f:
                    content = f.read()
                    validation["ci_workflows"][workflow_name]["has_p0_blocking"] = "CRITICAL_VIOLATIONS" in content
                    validation["ci_workflows"][workflow_name]["excludes_legacy"] = "signal_service_legacy" in content
            except Exception as e:
                validation["ci_workflows"][workflow_name]["read_error"] = str(e)

    return validation


def validate_evidence_structure() -> dict:
    """Validate evidence directory structure"""
    validation = {"evidence": {}}

    evidence_dir = Path("evidence")
    validation["evidence"]["base_dir_exists"] = evidence_dir.exists()

    if evidence_dir.exists():
        subdirs = ["ruff_triage", "validation"]
        for subdir in subdirs:
            subdir_path = evidence_dir / subdir
            validation["evidence"][f"{subdir}_exists"] = subdir_path.exists()

            if subdir_path.exists():
                files = list(subdir_path.glob("*"))
                validation["evidence"][f"{subdir}_file_count"] = len(files)

    return validation


def run_triage_validation() -> dict:
    """Run triage script and validate output"""
    validation = {"triage_validation": {}}

    # Run triage script
    exit_code, stdout, stderr = run_command([
        "python", "scripts/triage_ruff_violations.py",
        "--output-dir", "evidence/validation"
    ])

    validation["triage_validation"]["exit_code"] = exit_code
    validation["triage_validation"]["output"] = stdout

    if exit_code == 0:
        # Check for generated files
        validation_dir = Path("evidence/validation")
        if validation_dir.exists():
            generated_files = list(validation_dir.glob("ruff_*"))
            validation["triage_validation"]["generated_files"] = [f.name for f in generated_files]

            # Try to load raw data
            data_files = list(validation_dir.glob("ruff_triage_data_*.json"))
            if data_files:
                try:
                    with open(data_files[0]) as f:
                        triage_data = json.load(f)
                        validation["triage_validation"]["categorized_violations"] = triage_data.get("categorized_violations", {})
                        validation["triage_validation"]["total_from_triage"] = triage_data.get("total_violations", 0)
                except Exception as e:
                    validation["triage_validation"]["data_load_error"] = str(e)
    else:
        validation["triage_validation"]["error"] = stderr

    return validation


def compare_stated_vs_actual(validation_results: dict) -> dict:
    """Compare stated metrics with actual measurements"""
    comparison = {"metric_comparison": {}}

    # Get actual counts
    actual_total = validation_results.get("actual_violations", {}).get("total", 0)
    actual_p0 = validation_results.get("actual_violations", {}).get("p0_total", 0)

    # Get triage counts (if available)
    triage_total = validation_results.get("triage_validation", {}).get("total_from_triage", 0)

    # Compare with stated metrics (from previous reports)
    stated_total = 6891  # From previous reports
    stated_p0 = 79      # From previous reports

    comparison["metric_comparison"]["total_violations"] = {
        "stated": stated_total,
        "actual": actual_total,
        "triage": triage_total,
        "variance": actual_total - stated_total if actual_total > 0 else "unknown"
    }

    comparison["metric_comparison"]["p0_violations"] = {
        "stated": stated_p0,
        "actual": actual_p0,
        "variance": actual_p0 - stated_p0 if actual_p0 > 0 else "unknown"
    }

    return comparison


def generate_validation_report(all_validations: dict) -> str:
    """Generate comprehensive validation report"""

    timestamp = datetime.now().isoformat()

    report = f"""# Ruff Infrastructure Validation Report

**Generated:** {timestamp}
**Purpose:** Validate actual implementation against stated metrics

## Infrastructure Validation

### ✅ Core Components
"""

    # Ruff installation
    ruff_info = all_validations.get("ruff_installation", {})
    if ruff_info.get("available"):
        report += f"- **Ruff Installation**: ✅ {ruff_info.get('version', 'Unknown version')}\n"
    else:
        report += "- **Ruff Installation**: ❌ Not available\n"

    # Configuration
    config_info = all_validations.get("configuration", {})
    pyproject_ok = config_info.get("pyproject_toml", {}).get("exists", False)
    ruff_config_ok = config_info.get("pyproject_toml", {}).get("has_ruff_config", False)
    legacy_excluded = config_info.get("pyproject_toml", {}).get("excludes_legacy", False)

    report += f"- **pyproject.toml**: {'✅' if pyproject_ok else '❌'} Exists, {'✅' if ruff_config_ok else '❌'} Has Ruff config, {'✅' if legacy_excluded else '❌'} Excludes legacy\n"
    report += f"- **.ruffignore**: {'✅' if config_info.get('ruffignore', {}).get('exists') else '❌'} Exists\n"

    # Scripts
    scripts_info = all_validations.get("scripts", {})
    for script_name, script_data in scripts_info.items():
        exists = script_data.get("exists", False)
        executable = script_data.get("executable", False)
        report += f"- **{script_name}**: {'✅' if exists else '❌'} Exists, {'✅' if executable else '❌'} Executable\n"

    # CI Workflows
    ci_info = all_validations.get("ci_workflows", {})
    for workflow_name, workflow_data in ci_info.items():
        exists = workflow_data.get("exists", False)
        has_blocking = workflow_data.get("has_p0_blocking", False)
        report += f"- **{workflow_name}**: {'✅' if exists else '❌'} Exists, {'✅' if has_blocking else '❌'} Has P0 blocking\n"

    # Actual violation counts
    violations_info = all_validations.get("actual_violations", {})
    report += f"""
## Actual Violation Counts

**Summary:** {violations_info.get('summary', 'Unable to determine')}

### Breakdown:
"""

    if "by_rule" in violations_info:
        # Sort by count descending
        sorted_violations = sorted(violations_info["by_rule"].items(), key=lambda x: x[1], reverse=True)
        for rule_code, count in sorted_violations[:10]:  # Top 10
            report += f"- **{rule_code}**: {count:,}\n"

        if len(sorted_violations) > 10:
            remaining = sum(count for _, count in sorted_violations[10:])
            report += f"- **Other rules**: {remaining:,}\n"

    # Critical violations
    p0_total = violations_info.get("p0_total", "Unknown")
    invalid_syntax = violations_info.get("invalid_syntax", 0)
    report += f"""
### Critical (P0) Violations:
- **Total P0**: {p0_total}
- **Invalid syntax**: {invalid_syntax:,}
- **F821 (undefined-name)**: {violations_info.get('by_rule', {}).get('F821', 0)}
- **F811 (redefined-while-unused)**: {violations_info.get('by_rule', {}).get('F811', 0)}
- **F402 (import-shadowed-by-loop-var)**: {violations_info.get('by_rule', {}).get('F402', 0)}
"""

    # Metric comparison
    comparison_info = all_validations.get("metric_comparison", {})
    if "total_violations" in comparison_info:
        total_comp = comparison_info["total_violations"]
        p0_comp = comparison_info["p0_violations"]

        report += f"""
## Metric Validation

### Total Violations:
- **Stated**: {total_comp.get('stated', 'Unknown'):,}
- **Actual**: {total_comp.get('actual', 'Unknown'):,}
- **Triage**: {total_comp.get('triage', 'Unknown'):,}
- **Variance**: {total_comp.get('variance', 'Unknown')}

### P0 Critical Violations:
- **Stated**: {p0_comp.get('stated', 'Unknown')}
- **Actual**: {p0_comp.get('actual', 'Unknown')}
- **Variance**: {p0_comp.get('variance', 'Unknown')}
"""

    # Triage validation
    triage_info = all_validations.get("triage_validation", {})
    if triage_info.get("exit_code") == 0:
        report += f"""
## Triage System Validation

✅ **Triage script executed successfully**
- Generated files: {len(triage_info.get('generated_files', []))}
- Files: {', '.join(triage_info.get('generated_files', [])[:3])}{'...' if len(triage_info.get('generated_files', [])) > 3 else ''}
"""

        if "categorized_violations" in triage_info:
            categories = triage_info["categorized_violations"]
            report += "\n### Violation Categories:\n"
            for category, rules in categories.items():
                total = sum(rules.values()) if isinstance(rules, dict) else 0
                report += f"- **{category.title()}**: {total:,} violations\n"
    else:
        report += f"""
## Triage System Validation

❌ **Triage script failed**
- Exit code: {triage_info.get('exit_code', 'Unknown')}
- Error: {triage_info.get('error', 'Unknown error')}
"""

    # Recommendations
    report += """
## Validation Results Summary

"""

    # Determine overall status
    critical_issues = []

    if not ruff_info.get("available"):
        critical_issues.append("Ruff not available")

    if not pyproject_ok or not ruff_config_ok:
        critical_issues.append("Configuration incomplete")

    if violations_info.get("p0_total", 0) > 0:
        critical_issues.append(f"{violations_info.get('p0_total')} P0 violations block CI")

    if triage_info.get("exit_code", 0) != 0:
        critical_issues.append("Triage system not functional")

    if critical_issues:
        report += "❌ **Status**: Issues found requiring attention\n\n"
        for issue in critical_issues:
            report += f"- {issue}\n"
    else:
        report += "✅ **Status**: Infrastructure validation passed\n"

    report += f"""

## Next Actions

### Immediate:
1. **Fix P0 violations**: {violations_info.get('p0_total', 0)} violations blocking CI
2. **Verify CI workflows**: Test GitHub Actions P0 blocking
3. **Address invalid syntax**: {invalid_syntax:,} syntax errors need manual review

### Monitoring:
- Use `python scripts/triage_ruff_violations.py` for detailed analysis
- Check `evidence/validation/` for generated reports
- Monitor CI workflow logs for P0 blocking effectiveness

**Note**: This validation reflects current local state and may not reflect GitHub Actions execution or live CI behavior.
"""

    return report


def main():
    """Main validation entry point"""
    print("🔍 Validating Ruff infrastructure...")

    # Run all validations
    all_validations = {}

    print("📋 Checking Ruff installation...")
    all_validations.update(validate_ruff_installation())

    print("⚙️ Validating configuration...")
    all_validations.update(validate_configuration_files())

    print("📊 Getting actual violation counts...")
    all_validations.update(get_actual_violation_counts())

    print("📜 Checking automation scripts...")
    all_validations.update(validate_scripts())

    print("🔄 Validating CI workflows...")
    all_validations.update(validate_ci_workflows())

    print("📂 Checking evidence structure...")
    all_validations.update(validate_evidence_structure())

    print("🎯 Running triage validation...")
    all_validations.update(run_triage_validation())

    print("📈 Comparing stated vs actual metrics...")
    all_validations.update(compare_stated_vs_actual(all_validations))

    # Generate report
    print("📋 Generating validation report...")
    report = generate_validation_report(all_validations)

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Raw data
    raw_file = Path("evidence") / f"ruff_validation_raw_{timestamp}.json"
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    with open(raw_file, 'w') as f:
        json.dump(all_validations, f, indent=2, default=str)

    # Human-readable report
    report_file = Path("evidence") / f"ruff_validation_report_{timestamp}.md"
    with open(report_file, 'w') as f:
        f.write(report)

    print(f"""
✅ Validation complete!

📋 **Summary:**
- Total violations: {all_validations.get('actual_violations', {}).get('total', 'Unknown'):,}
- P0 violations: {all_validations.get('actual_violations', {}).get('p0_total', 'Unknown')}
- Configuration: {'✅' if all_validations.get('configuration', {}).get('pyproject_toml', {}).get('exists') else '❌'}
- Scripts: {sum(1 for s in all_validations.get('scripts', {}).values() if s.get('exists'))}/3 available

📁 **Reports:**
- Validation report: {report_file}
- Raw data: {raw_file}
""")

    # Print key findings
    p0_count = all_validations.get('actual_violations', {}).get('p0_total', 0)
    if p0_count > 0:
        print(f"⚠️ **CRITICAL**: {p0_count} P0 violations found - these should block CI!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
