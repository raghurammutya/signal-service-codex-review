#!/usr/bin/env python3
"""
Fix B007 violations - unused loop control variables
"""

import re
import subprocess
import sys


def get_b007_violations():
    """Get B007 violations from ruff."""
    result = subprocess.run(
        ['ruff', 'check', '.', '--select', 'B007'],
        capture_output=True, text=True
    )

    violations = []
    lines = result.stdout.split('\n')

    current_file = None
    current_line = None
    current_var = None

    for line in lines:
        if line.strip() and not line.startswith(' ') and ':' in line:
            # File line with violation
            parts = line.split(':')
            if len(parts) >= 4 and 'B007' in line:
                current_file = parts[0]
                current_line = int(parts[1])

                # Extract variable name from the message
                if "Loop control variable" in line:
                    # Look for pattern: Loop control variable `varname` not used
                    match = re.search(r'Loop control variable `([^`]+)` not used', line)
                    if match:
                        current_var = match.group(1)
                        violations.append((current_file, current_line, current_var))

    return violations


def fix_b007_violation(file_path, line_number, variable_name):
    """Fix a specific B007 violation by renaming unused variable."""
    try:
        with open(file_path, encoding='utf-8') as f:
            lines = f.readlines()

        if line_number > len(lines):
            return False

        target_line = lines[line_number - 1]

        # Check if this is a for loop with the specific variable
        if 'for ' in target_line and variable_name in target_line:
            # Replace the variable name with underscore version
            new_var_name = f'_{variable_name}'

            # Use word boundary to avoid partial replacements
            pattern = r'\b' + re.escape(variable_name) + r'\b'

            # Only replace the first occurrence (the loop variable definition)
            new_line = re.sub(pattern, new_var_name, target_line, count=1)

            if new_line != target_line:
                lines[line_number - 1] = new_line

                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(lines)

                return True

        return False

    except Exception as e:
        print(f"Error fixing {file_path}:{line_number} - {e}")
        return False


def main():
    print("Fixing B007 violations (unused loop control variables)...")

    violations = get_b007_violations()
    print(f"Found {len(violations)} B007 violations")

    if not violations:
        print("No B007 violations to fix")
        return 0

    fixed_count = 0

    for file_path, line_number, variable_name in violations:
        result = fix_b007_violation(file_path, line_number, variable_name)
        if result:
            print(f"✅ Fixed {file_path}:{line_number} - renamed '{variable_name}' to '_{variable_name}'")
            fixed_count += 1
        else:
            print(f"⚠️ Could not fix {file_path}:{line_number} - '{variable_name}'")

    print(f"\n🎯 Summary: Fixed {fixed_count} B007 violations")

    # Check remaining violations
    remaining = get_b007_violations()
    print(f"📊 Remaining B007 violations: {len(remaining)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
