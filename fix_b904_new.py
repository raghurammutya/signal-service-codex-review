#!/usr/bin/env python3
"""
B904 Raise-without-from Exception Chaining Fix Script
Fix raise statements inside except blocks to include proper exception chaining.
"""

import re
import subprocess
import sys


def get_b904_violations():
    """Get all B904 violations from ruff."""
    result = subprocess.run(
        ['ruff', 'check', '--select=B904', '.'],
        capture_output=True, text=True
    )

    violations = []
    lines = result.stdout.split('\n')

    for line in lines:
        if 'B904' in line and ':' in line:
            parts = line.split(':')
            if len(parts) >= 3:
                file_path = parts[0]
                line_num = int(parts[1])
                violations.append((file_path, line_num))

    return violations


def read_file(file_path):
    """Read file content."""
    try:
        with open(file_path, encoding='utf-8') as f:
            return f.readlines()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None


def write_file(file_path, lines):
    """Write file content."""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        return True
    except Exception as e:
        print(f"Error writing {file_path}: {e}")
        return False


def get_indentation(line):
    """Get indentation level of a line."""
    return len(line) - len(line.lstrip())


def find_except_variable(lines, except_line_idx):
    """Find the exception variable from the except clause."""
    # Look backwards from the raise to find the except clause
    for i in range(except_line_idx, -1, -1):
        line = lines[i].strip()
        if line.startswith('except '):
            # Parse except clause: except ExceptionType as var:
            match = re.search(r'except\s+[^:]+\s+as\s+(\w+)\s*:', line)
            if match:
                return match.group(1)
            # Also handle: except (Exception1, Exception2) as var:
            match = re.search(r'except\s+\([^)]+\)\s+as\s+(\w+)\s*:', line)
            if match:
                return match.group(1)
    return None


def fix_b904_violation(lines, violation_line_num):
    """Fix B904 violation at the specified line."""
    try:
        # Convert to 0-based index
        line_idx = violation_line_num - 1

        if line_idx >= len(lines):
            return False

        line = lines[line_idx]
        indentation = get_indentation(line)

        # Check if this is a raise statement
        stripped = line.strip()
        if not stripped.startswith('raise '):
            return False

        # Skip if already has exception chaining
        if ' from ' in stripped:
            return False

        # Find the except variable
        except_var = find_except_variable(lines, line_idx)

        if not except_var:
            # No except variable found, use 'from None' for suppression
            new_line = stripped + ' from None'
        else:
            # Use the except variable for chaining
            new_line = stripped + f' from {except_var}'

        # Reconstruct line with original indentation
        lines[line_idx] = ' ' * indentation + new_line + '\n'

        return True

    except Exception as e:
        print(f"Error fixing B904 at line {violation_line_num}: {e}")
        return False


def main():
    print("Starting B904 (raise-without-from) fix...")

    violations = get_b904_violations()
    print(f"Found {len(violations)} B904 violations")

    if not violations:
        print("No violations to fix")
        return 0

    fixed_count = 0
    file_groups = {}

    # Group violations by file
    for file_path, line_num in violations:
        if file_path not in file_groups:
            file_groups[file_path] = []
        file_groups[file_path].append(line_num)

    for file_path, line_nums in file_groups.items():
        print(f"\nProcessing {file_path} ({len(line_nums)} violations)")

        lines = read_file(file_path)
        if lines is None:
            continue

        # Sort line numbers to process from top to bottom
        line_nums.sort()

        modified = False
        for line_num in line_nums:
            result = fix_b904_violation(lines, line_num)
            if result:
                fixed_count += 1
                modified = True
                print(f"  ✅ Fixed B904 at line {line_num}")
            else:
                print(f"  ⚠️ Skipped complex case at line {line_num}")

        if modified:
            if write_file(file_path, lines):
                print(f"  💾 Saved {file_path}")
            else:
                print(f"  ❌ Failed to save {file_path}")

    print(f"\n🎯 Summary: Fixed {fixed_count}/{len(violations)} B904 violations")

    # Check remaining violations
    remaining = get_b904_violations()
    print(f"📊 Remaining B904 violations: {len(remaining)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
