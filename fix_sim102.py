#!/usr/bin/env python3
"""
SIM102 Collapsible-if Statement Fix Script
Fix nested if statements that can be combined into a single if using 'and'.
"""

import subprocess
import sys


def get_sim102_violations():
    """Get all SIM102 violations from ruff."""
    result = subprocess.run(
        ['ruff', 'check', '--select=SIM102', '.'],
        capture_output=True, text=True
    )

    violations = []
    lines = result.stdout.split('\n')

    for line in lines:
        if 'SIM102' in line and ':' in line:
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


def fix_nested_if(lines, violation_line_num):
    """Fix nested if statements at the specified line."""
    try:
        # Convert to 0-based index
        line_idx = violation_line_num - 1

        if line_idx >= len(lines):
            return False

        # Find the outer if statement
        outer_if_idx = line_idx

        # Look backwards to find the actual outer if statement
        while outer_if_idx > 0:
            line = lines[outer_if_idx].strip()
            if line.startswith('if ') and ':' in line:
                break
            outer_if_idx -= 1

        if outer_if_idx == 0 and not (lines[0].strip().startswith('if ') and ':' in lines[0]):
            return False

        outer_line = lines[outer_if_idx]
        outer_indent = get_indentation(outer_line)

        # Find the nested if statement
        nested_if_idx = outer_if_idx + 1
        while nested_if_idx < len(lines):
            line = lines[nested_if_idx]
            if line.strip() == '':
                nested_if_idx += 1
                continue

            line_indent = get_indentation(line)
            if line_indent <= outer_indent:
                return False  # No nested if found

            if line.strip().startswith('if ') and ':' in line:
                break

            nested_if_idx += 1

        if nested_if_idx >= len(lines):
            return False

        nested_line = lines[nested_if_idx]
        nested_indent = get_indentation(nested_line)

        # Extract conditions
        outer_condition = outer_line.strip()[3:].rstrip(':').strip()
        nested_condition = nested_line.strip()[3:].rstrip(':').strip()

        # Skip if conditions are too complex
        if (len(outer_condition) > 100 or len(nested_condition) > 100 or
            'and' in outer_condition.lower() or 'or' in outer_condition.lower() or
            'and' in nested_condition.lower() or 'or' in nested_condition.lower()):
            return False

        # Create combined condition
        combined_condition = f"{outer_condition} and {nested_condition}"

        # Create new if statement with outer indentation
        new_if_line = f"{' ' * outer_indent}if {combined_condition}:\n"

        # Find the body of the nested if to preserve
        body_lines = []
        body_idx = nested_if_idx + 1

        while body_idx < len(lines):
            line = lines[body_idx]
            if line.strip() == '':
                body_lines.append(line)
                body_idx += 1
                continue

            line_indent = get_indentation(line)
            if line_indent <= nested_indent:
                break

            # Adjust indentation: remove one level
            new_indent = line_indent - (nested_indent - outer_indent)
            if new_indent < 0:
                new_indent = 0

            body_lines.append(' ' * new_indent + line.lstrip())
            body_idx += 1

        # Replace the lines
        return (
            lines[:outer_if_idx] +
            [new_if_line] +
            body_lines +
            lines[body_idx:]
        )


    except Exception as e:
        print(f"Error fixing nested if at line {violation_line_num}: {e}")
        return False


def main():
    print("Starting SIM102 (collapsible-if) fix...")

    violations = get_sim102_violations()
    print(f"Found {len(violations)} SIM102 violations")

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

        # Sort line numbers in reverse order to fix from bottom up
        line_nums.sort(reverse=True)

        modified = False
        for line_num in line_nums:
            result = fix_nested_if(lines, line_num)
            if result:
                lines = result
                fixed_count += 1
                modified = True
                print(f"  ✅ Fixed nested if at line {line_num}")
            else:
                print(f"  ⚠️ Skipped complex case at line {line_num}")

        if modified:
            if write_file(file_path, lines):
                print(f"  💾 Saved {file_path}")
            else:
                print(f"  ❌ Failed to save {file_path}")

    print(f"\n🎯 Summary: Fixed {fixed_count}/{len(violations)} SIM102 violations")

    # Check remaining violations
    remaining = get_sim102_violations()
    print(f"📊 Remaining SIM102 violations: {len(remaining)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
