#!/usr/bin/env python3
"""
Ruff Violation Triage Script

Categorizes remaining violations by rule type and module to enable systematic
remediation across the signal-service-codex-review repository.
"""

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
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


def get_violation_categories() -> dict[str, dict[str, str]]:
    """Define violation categories for systematic triage"""
    return {
        "critical": {
            "F821": "undefined-name",
            "F401": "unused-import",
            "E999": "syntax-error",
            "F811": "redefined-while-unused",
            "F402": "import-shadowed-by-loop-var"
        },
        "imports": {
            "I001": "unsorted-imports",
            "F401": "unused-import",
            "UP035": "deprecated-import",
            "E402": "module-import-not-at-top-of-file"
        },
        "typing": {
            "UP006": "non-pep585-annotation",
            "UP007": "non-pep604-annotation-union",
            "UP045": "non-pep604-annotation-optional",
            "UP041": "timeout-error-alias",
            "UP024": "os-error-alias"
        },
        "formatting": {
            "W291": "trailing-whitespace",
            "W292": "missing-newline-at-end-of-file",
            "W293": "blank-line-with-whitespace",
            "W605": "invalid-escape-sequence"
        },
        "complexity": {
            "SIM117": "multiple-with-statements",
            "SIM102": "collapsible-if",
            "SIM103": "needless-bool",
            "SIM105": "suppressible-exception",
            "SIM108": "if-else-block-instead-of-if-exp",
            "C401": "unnecessary-generator-set"
        },
        "error_handling": {
            "B904": "raise-without-from-inside-except",
            "B905": "zip-without-explicit-strict",
            "B017": "assert-raises-exception",
            "E722": "bare-except",
            "B011": "assert-false"
        },
        "code_quality": {
            "RET504": "unnecessary-assign",
            "RET505": "superfluous-else-return",
            "RET503": "implicit-return",
            "B007": "unused-loop-control-variable",
            "F841": "unused-variable",
            "PIE810": "multiple-starts-ends-with"
        },
        "style": {
            "N805": "invalid-first-argument-name-for-method",
            "E712": "true-false-comparison",
            "E721": "type-comparison",
            "E741": "ambiguous-variable-name",
            "N818": "error-suffix-on-exception-name"
        }
    }


def analyze_violations_by_rule(ruff_cmd: str) -> dict[str, int]:
    """Get violation counts by rule using Ruff statistics"""
    cmd = [ruff_cmd, "check", ".", "--statistics", "--exclude", "signal_service_legacy"]
    exit_code, stdout, stderr = run_command(cmd)

    violations = {}
    for line in stdout.split('\n'):
        if '\t' in line and any(char.isdigit() for char in line):
            parts = line.strip().split('\t')
            if len(parts) >= 2:
                try:
                    count = int(parts[0].strip())
                    rule_code = parts[1].strip()
                    violations[rule_code] = count
                except ValueError:
                    pass

    return violations


def analyze_violations_by_file(ruff_cmd: str) -> dict[str, list[dict]]:
    """Get detailed violations by file"""
    cmd = [ruff_cmd, "check", ".", "--output-format", "json", "--exclude", "signal_service_legacy"]
    exit_code, stdout, stderr = run_command(cmd)

    if exit_code != 0 and not stdout:
        print(f"Warning: Ruff command failed: {stderr}")
        return {}

    try:
        violations_raw = json.loads(stdout) if stdout else []
    except json.JSONDecodeError:
        print(f"Warning: Could not parse JSON output: {stdout[:200]}...")
        return {}

    violations_by_file = defaultdict(list)
    for violation in violations_raw:
        filename = violation.get("filename", "unknown")
        violations_by_file[filename].append(violation)

    return dict(violations_by_file)


def categorize_violations(violations_by_rule: dict[str, int]) -> dict[str, dict[str, int]]:
    """Categorize violations by type for systematic remediation"""
    categories = get_violation_categories()
    categorized = defaultdict(lambda: defaultdict(int))
    uncategorized = {}

    for rule_code, count in violations_by_rule.items():
        categorized_rule = False
        for category_name, category_rules in categories.items():
            if rule_code in category_rules:
                categorized[category_name][rule_code] = count
                categorized_rule = True
                break

        if not categorized_rule:
            uncategorized[rule_code] = count

    # Add uncategorized as a separate category
    if uncategorized:
        categorized["uncategorized"] = uncategorized

    return dict(categorized)


def analyze_by_module(violations_by_file: dict[str, list[dict]]) -> dict[str, dict[str, int]]:
    """Analyze violations by module/directory structure"""
    modules = defaultdict(lambda: defaultdict(int))

    for filename, file_violations in violations_by_file.items():
        # Determine module from file path
        path_parts = Path(filename).parts
        if len(path_parts) > 1:
            module = path_parts[0]  # Top-level directory
            if len(path_parts) > 2 and path_parts[0] in ['app', 'tests', 'scripts']:
                module = f"{path_parts[0]}/{path_parts[1]}"  # Subdirectory
        else:
            module = "root"

        for violation in file_violations:
            rule_code = violation.get("code", "unknown")
            modules[module][rule_code] += 1

    return dict(modules)


def generate_triage_report(
    violations_by_rule: dict[str, int],
    categorized_violations: dict[str, dict[str, int]],
    violations_by_module: dict[str, dict[str, int]],
    violations_by_file: dict[str, list[dict]]
) -> str:
    """Generate comprehensive triage report"""

    total_violations = sum(violations_by_rule.values())
    categories = get_violation_categories()

    report = f"""# Ruff Violation Triage Report

## Executive Summary
**Generated:** {datetime.now().isoformat()}
**Total Violations:** {total_violations:,}
**Files Affected:** {len(violations_by_file):,}
**Unique Rule Types:** {len(violations_by_rule)}

## Priority Categories

"""

    # Category breakdown with priority levels
    priority_order = ["critical", "imports", "formatting", "typing", "error_handling", "code_quality", "complexity", "style", "uncategorized"]

    for category in priority_order:
        if category in categorized_violations:
            category_violations = categorized_violations[category]
            category_total = sum(category_violations.values())

            if category == "critical":
                priority_emoji = "🚨"
                priority_text = "P0 - IMMEDIATE"
            elif category in ["imports", "formatting"]:
                priority_emoji = "⚡"
                priority_text = "P1 - HIGH"
            elif category in ["typing", "error_handling"]:
                priority_emoji = "⚠️"
                priority_text = "P2 - MEDIUM"
            else:
                priority_emoji = "📋"
                priority_text = "P3 - LOW"

            report += f"""### {priority_emoji} **{category.title()}** - {priority_text}
**Total:** {category_total:,} violations

"""

            # Top rules in category
            sorted_rules = sorted(category_violations.items(), key=lambda x: x[1], reverse=True)
            for rule_code, count in sorted_rules[:5]:
                rule_name = categories.get(category, {}).get(rule_code, "unknown")
                percentage = (count / total_violations) * 100
                report += f"- **{rule_code}** ({rule_name}): {count:,} ({percentage:.1f}%)\n"

            report += "\n"

    # Module breakdown
    report += """## Module Breakdown

Top modules by violation count:

"""

    module_totals = {module: sum(rules.values()) for module, rules in violations_by_module.items()}
    sorted_modules = sorted(module_totals.items(), key=lambda x: x[1], reverse=True)

    for module, total in sorted_modules[:10]:
        percentage = (total / total_violations) * 100
        report += f"- **{module}**: {total:,} violations ({percentage:.1f}%)\n"

    # Remediation recommendations
    report += """

## Remediation Strategy

### Phase 1: Critical Issues (P0)
Target completion: 1 week
"""

    if "critical" in categorized_violations:
        for rule_code, count in sorted(categorized_violations["critical"].items(), key=lambda x: x[1], reverse=True):
            report += f"- Fix {rule_code}: {count:,} occurrences\n"

    report += """
### Phase 2: Quick Wins (P1)
Target completion: 2 weeks
"""

    for category in ["imports", "formatting"]:
        if category in categorized_violations:
            category_total = sum(categorized_violations[category].values())
            report += f"- {category.title()}: {category_total:,} violations (auto-fixable)\n"

    report += """
### Phase 3: Quality Improvements (P2-P3)
Target completion: 1 month
"""

    for category in ["typing", "error_handling", "code_quality", "complexity", "style"]:
        if category in categorized_violations:
            category_total = sum(categorized_violations[category].values())
            report += f"- {category.title()}: {category_total:,} violations\n"

    # Detailed breakdown by module and rule
    report += """

## Detailed Module Analysis

"""

    for module in sorted_modules[:5]:
        module_name = module[0]
        module_violations = violations_by_module[module_name]
        module_total = sum(module_violations.values())

        report += f"""### {module_name} ({module_total:,} violations)

Top rules:
"""
        sorted_rules = sorted(module_violations.items(), key=lambda x: x[1], reverse=True)
        for rule_code, count in sorted_rules[:5]:
            report += f"- {rule_code}: {count:,}\n"
        report += "\n"

    return report


def generate_actionable_tasks(categorized_violations: dict[str, dict[str, int]]) -> str:
    """Generate actionable task list for teams"""

    tasks = """# Ruff Remediation Tasks

## Sprint Planning

### Critical Tasks (P0) - Week 1
"""

    if "critical" in categorized_violations:
        for rule_code, count in categorized_violations["critical"].items():
            tasks += f"""
**Task: Fix {rule_code} violations**
- Count: {count:,} occurrences
- Assignee: [TBD]
- Command: `ruff check . --select {rule_code} --exclude signal_service_legacy`
- Status: [ ] Not Started [ ] In Progress [ ] Complete
"""

    tasks += """
### High Priority Tasks (P1) - Week 2-3
"""

    for category in ["imports", "formatting"]:
        if category in categorized_violations:
            category_violations = categorized_violations[category]
            category_total = sum(category_violations.values())
            rule_codes = ",".join(category_violations.keys())

            tasks += f"""
**Task: Fix {category} violations**
- Count: {category_total:,} violations
- Rules: {rule_codes}
- Assignee: [TBD]
- Command: `ruff check . --select {rule_codes} --fix --exclude signal_service_legacy`
- Status: [ ] Not Started [ ] In Progress [ ] Complete
"""

    tasks += """
### Medium Priority Tasks (P2) - Week 4-6
"""

    for category in ["typing", "error_handling"]:
        if category in categorized_violations:
            category_violations = categorized_violations[category]
            category_total = sum(category_violations.values())
            rule_codes = ",".join(category_violations.keys())

            tasks += f"""
**Task: Improve {category}**
- Count: {category_total:,} violations
- Rules: {rule_codes}
- Assignee: [TBD]
- Command: `ruff check . --select {rule_codes} --exclude signal_service_legacy`
- Status: [ ] Not Started [ ] In Progress [ ] Complete
"""

    return tasks


def generate_exemption_candidates(violations_by_file: dict[str, list[dict]]) -> str:
    """Identify files that might be candidates for exemption"""

    exemption_report = """# Potential Exemption Candidates

Files with high violation counts that might warrant exemptions:

"""

    file_violation_counts = {}
    for filename, violations in violations_by_file.items():
        file_violation_counts[filename] = len(violations)

    # Files with >50 violations might be candidates
    high_violation_files = {f: c for f, c in file_violation_counts.items() if c > 50}
    sorted_files = sorted(high_violation_files.items(), key=lambda x: x[1], reverse=True)

    for filename, count in sorted_files[:20]:
        path = Path(filename)

        # Determine if file might be exemption candidate
        exemption_reasons = []
        if "test" in filename.lower():
            exemption_reasons.append("Test file")
        if path.suffix in [".pb2.py", "_pb2.py"]:
            exemption_reasons.append("Generated file")
        if "migration" in filename.lower():
            exemption_reasons.append("Database migration")
        if any(part in ["generated", "vendor", "third_party"] for part in path.parts):
            exemption_reasons.append("Generated/vendor code")
        if count > 100:
            exemption_reasons.append("Extremely high violation count")

        exemption_report += f"""
## {filename}
- **Violations:** {count:,}
- **Potential reasons:** {', '.join(exemption_reasons) if exemption_reasons else 'High violation count'}
- **Action:** {'Recommend .ruffignore' if exemption_reasons else 'Review for systematic fixes'}
"""

    return exemption_report


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Triage Ruff violations for systematic remediation",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "--output-dir",
        default="evidence/ruff_triage",
        help="Output directory for triage reports"
    )

    parser.add_argument(
        "--format",
        choices=["markdown", "json", "csv"],
        default="markdown",
        help="Output format for reports"
    )

    args = parser.parse_args()

    # Ensure output directory exists
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("🔍 Analyzing Ruff violations...")

    try:
        ruff_cmd = get_ruff_command()
    except RuntimeError as e:
        print(f"❌ Error: {e}")
        return 1

    # Analyze violations
    print("📊 Gathering violation statistics...")
    violations_by_rule = analyze_violations_by_rule(ruff_cmd)

    print("📁 Analyzing violations by file...")
    violations_by_file = analyze_violations_by_file(ruff_cmd)

    print("🏗️ Categorizing violations...")
    categorized_violations = categorize_violations(violations_by_rule)

    print("📂 Analyzing by module...")
    violations_by_module = analyze_by_module(violations_by_file)

    # Generate reports
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("📋 Generating triage report...")
    triage_report = generate_triage_report(
        violations_by_rule, categorized_violations, violations_by_module, violations_by_file
    )

    print("✅ Generating task list...")
    task_list = generate_actionable_tasks(categorized_violations)

    print("⚠️ Identifying exemption candidates...")
    exemption_report = generate_exemption_candidates(violations_by_file)

    # Save reports
    triage_file = output_dir / f"ruff_triage_report_{timestamp}.md"
    with open(triage_file, 'w') as f:
        f.write(triage_report)

    tasks_file = output_dir / f"ruff_remediation_tasks_{timestamp}.md"
    with open(tasks_file, 'w') as f:
        f.write(task_list)

    exemption_file = output_dir / f"ruff_exemption_candidates_{timestamp}.md"
    with open(exemption_file, 'w') as f:
        f.write(exemption_report)

    # Raw data
    raw_data_file = output_dir / f"ruff_triage_data_{timestamp}.json"
    raw_data = {
        "timestamp": timestamp,
        "violations_by_rule": violations_by_rule,
        "categorized_violations": categorized_violations,
        "violations_by_module": violations_by_module,
        "total_violations": sum(violations_by_rule.values()),
        "total_files": len(violations_by_file)
    }

    with open(raw_data_file, 'w') as f:
        json.dump(raw_data, f, indent=2)

    # Summary
    total_violations = sum(violations_by_rule.values())
    print(f"""
✅ Triage complete!

📊 **Summary:**
- Total violations: {total_violations:,}
- Files affected: {len(violations_by_file):,}
- Rule types: {len(violations_by_rule)}

📁 **Reports generated:**
- Triage report: {triage_file}
- Task list: {tasks_file}
- Exemption candidates: {exemption_file}
- Raw data: {raw_data_file}

🚀 **Next steps:**
1. Review triage report for prioritization
2. Assign tasks from remediation list
3. Consider exemptions for high-violation files
4. Track progress using raw data metrics
""")

    return 0


if __name__ == "__main__":
    sys.exit(main())
