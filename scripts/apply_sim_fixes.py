#!/usr/bin/env python3
"""
Targeted SIM Violation Automation Script

Systematically fixes SIM105 (suppressible-exception), SIM102 (collapsible-if),
and B023 (function-uses-loop-variable) violations with safe automation patterns.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def run_ruff_json(select_rules: str) -> list[dict]:
    """Run ruff with JSON output for specified rules."""
    try:
        result = subprocess.run([
            "ruff", "check", ".",
            "--select", select_rules,
            "--format", "json"
        ], capture_output=True, text=True, check=False)

        if result.stdout.strip():
            return json.loads(result.stdout)
        return []
    except Exception as e:
        print(f"Error running ruff: {e}")
        return []

def add_contextlib_import(file_path: str) -> bool:
    """Add contextlib.suppress import if not present."""
    try:
        with open(file_path, encoding='utf-8') as f:
            content = f.read()

        # Check if suppress is already imported
        if 'from contextlib import suppress' in content or 'contextlib.suppress' in content:
            return False

        lines = content.split('\n')
        import_section_end = 0

        # Find the end of import section
        for i, line in enumerate(lines):
            if line.startswith(('import ', 'from ')) or line.strip() == '':
                import_section_end = i
            elif line.strip() and not line.startswith('#'):
                break

        # Insert the import
        if import_section_end > 0:
            # Find the best place to insert (after contextlib imports if any)
            insert_pos = import_section_end + 1
            for i in range(import_section_end + 1):
                if 'contextlib' in lines[i]:
                    insert_pos = i + 1
                    break

            lines.insert(insert_pos, 'from contextlib import suppress')
        else:
            # Insert at the beginning
            lines.insert(0, 'from contextlib import suppress')
            lines.insert(1, '')

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        return True
    except Exception as e:
        print(f"Error adding import to {file_path}: {e}")
        return False

def fix_sim105_violation(file_path: str, line_number: int, violation: dict) -> bool:
    """Fix a specific SIM105 violation by replacing try-except-pass with suppress()."""
    try:
        with open(file_path, encoding='utf-8') as f:
            lines = f.readlines()

        # Convert to 0-based indexing
        start_line = line_number - 1

        # Find the try block
        if start_line >= len(lines) or 'try:' not in lines[start_line]:
            # Search nearby lines for the try block
            for offset in range(-2, 3):
                check_line = start_line + offset
                if 0 <= check_line < len(lines) and 'try:' in lines[check_line]:
                    start_line = check_line
                    break
            else:
                print(f"Could not find try block near line {line_number} in {file_path}")
                return False

        # Extract exception type from the violation message
        message = violation.get('message', '')
        exception_match = re.search(r'contextlib\.suppress\((\w+)\)', message)
        exception_type = exception_match.group(1) if exception_match else 'Exception'

        # Find the try-except-pass block structure
        try_indent = len(lines[start_line]) - len(lines[start_line].lstrip())

        # Find except and pass lines
        except_line = None
        pass_line = None

        for i in range(start_line + 1, min(start_line + 10, len(lines))):
            line = lines[i].strip()
            if line.startswith('except ') and exception_type in line:
                except_line = i
            elif except_line is not None and line == 'pass':
                pass_line = i
                break

        if except_line is None or pass_line is None:
            print(f"Could not find complete try-except-pass block at line {line_number} in {file_path}")
            return False

        # Extract the code inside the try block
        try_content = []
        for i in range(start_line + 1, except_line):
            if lines[i].strip():  # Skip empty lines
                try_content.append(lines[i].rstrip())

        if not try_content:
            print(f"Empty try block at line {line_number} in {file_path}")
            return False

        # Create the replacement with suppress
        indent = ' ' * try_indent
        replacement_lines = [
            f"{indent}with suppress({exception_type}):\n"
        ]

        # Add the try content with proper indentation
        for content_line in try_content:
            if content_line.strip():
                # Add 4 spaces to existing indentation
                replacement_lines.append(content_line.replace(
                    content_line[:try_indent],
                    ' ' * (try_indent + 4), 1
                ) + '\n')

        # Replace the try-except-pass block
        lines[start_line:pass_line + 1] = replacement_lines

        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        print(f"Fixed SIM105 violation at line {line_number} in {file_path}")
        return True

    except Exception as e:
        print(f"Error fixing SIM105 violation in {file_path}:{line_number}: {e}")
        return False

def generate_sim102_report(violations: list[dict]) -> str:
    """Generate a report for SIM102 violations with suggested fixes."""
    report = "## SIM102 (Collapsible-If) Manual Review Report\n\n"
    report += "The following nested if statements can potentially be combined:\n\n"

    for violation in violations:
        file_path = violation['filename']
        line_number = violation['location']['row']
        message = violation['message']

        report += f"### {file_path}:{line_number}\n"
        report += f"**Issue**: {message}\n"
        report += "**Suggestion**: Consider combining nested if statements with `and` operator\n"
        report += "**Review**: Check if combining affects short-circuit evaluation logic\n\n"

    return report

def generate_b023_report(violations: list[dict]) -> str:
    """Generate a report for B023 violations with suggested fixes."""
    report = "## B023 (Function-Uses-Loop-Variable) Manual Review Report\n\n"
    report += "The following functions capture loop variables that may cause unexpected behavior:\n\n"

    for violation in violations:
        file_path = violation['filename']
        line_number = violation['location']['row']
        message = violation['message']

        report += f"### {file_path}:{line_number}\n"
        report += f"**Issue**: {message}\n"
        report += "**Suggestion**: Capture loop variable via default argument: `lambda x=loop_var: ...`\n"
        report += "**Review**: Ensure closure behavior is intended\n\n"

    return report

def main():
    """Main automation script for SIM violations."""
    print("🔧 Starting targeted SIM violation fixes...")

    # Create evidence directory if it doesn't exist
    evidence_dir = Path("evidence")
    evidence_dir.mkdir(exist_ok=True)

    # Get SIM105 violations
    print("📊 Scanning for SIM105 violations...")
    sim105_violations = run_ruff_json("SIM105")

    if sim105_violations:
        print(f"Found {len(sim105_violations)} SIM105 violations")

        # Group by file
        files_to_fix = {}
        for violation in sim105_violations:
            file_path = violation['filename']
            if file_path not in files_to_fix:
                files_to_fix[file_path] = []
            files_to_fix[file_path].append(violation)

        # Fix violations and add imports
        total_fixed = 0
        for file_path, violations in files_to_fix.items():
            print(f"\n🔨 Processing {file_path} ({len(violations)} violations)...")

            # Add contextlib import first
            import_added = add_contextlib_import(file_path)
            if import_added:
                print("  ✅ Added contextlib.suppress import")

            # Fix violations (in reverse order to maintain line numbers)
            violations.sort(key=lambda v: v['location']['row'], reverse=True)

            for violation in violations:
                if fix_sim105_violation(file_path, violation['location']['row'], violation):
                    total_fixed += 1

        print(f"\n✅ Fixed {total_fixed}/{len(sim105_violations)} SIM105 violations")

    # Generate reports for manual review violations
    print("\n📊 Scanning for manual review violations...")

    sim102_violations = run_ruff_json("SIM102")
    b023_violations = run_ruff_json("B023")

    # Generate comprehensive report
    report_content = "# SIM Violations Automation Report\n\n"
    report_content += f"Generated: {os.popen('date').read().strip()}\n\n"

    if sim105_violations:
        report_content += "## SIM105 Results\n"
        report_content += f"- **Automated fixes attempted**: {len(sim105_violations)}\n"
        report_content += f"- **Files modified**: {len(files_to_fix) if 'files_to_fix' in locals() else 0}\n"
        report_content += "- **Status**: Automated processing complete\n"
        report_content += "- **Next step**: Run `ruff check --select SIM105` to verify\n\n"

    if sim102_violations:
        report_content += generate_sim102_report(sim102_violations)

    if b023_violations:
        report_content += generate_b023_report(b023_violations)

    # Save report
    report_path = evidence_dir / "sim-automation-report.md"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)

    print(f"\n📋 Report saved to {report_path}")
    print(f"   - SIM102 violations requiring manual review: {len(sim102_violations)}")
    print(f"   - B023 violations requiring manual review: {len(b023_violations)}")

    # Final verification
    print("\n🧪 Running verification...")
    remaining_sim105 = run_ruff_json("SIM105")
    if remaining_sim105:
        print(f"⚠️  {len(remaining_sim105)} SIM105 violations remain (may need manual review)")
    else:
        print("✅ All SIM105 violations resolved!")

    print("\n🎯 Next steps:")
    print("   1. Review modified files for correctness")
    print("   2. Run: ruff check --select SIM105,SIM102,B023 --statistics")
    print("   3. Review evidence/sim-automation-report.md for manual fixes")
    print("   4. Commit changes when satisfied")

if __name__ == "__main__":
    main()
