#!/usr/bin/env python3
"""
SIM117 Multiple With Statement Fix Script
Convert nested with statements to a single with statement with multiple contexts.
"""

import subprocess
import sys


def get_sim117_violations():
    """Get all SIM117 violations from ruff."""
    result = subprocess.run(
        ['ruff', 'check', '--select=SIM117', '.'],
        capture_output=True, text=True
    )

    violations = []
    lines = result.stdout.split('\n')

    for line in lines:
        if 'SIM117' in line and ':' in line:
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


def fix_nested_with(lines, violation_line_num):
    """Fix nested with statements at the specified line."""
    try:
        # Convert to 0-based index
        line_idx = violation_line_num - 1

        if line_idx >= len(lines):
            return False

        # Find all consecutive with statements
        with_blocks = []
        current_idx = line_idx

        # Look for the first with statement
        while current_idx > 0:
            line = lines[current_idx].strip()
            if line.startswith('with ') and ':' in line:
                break
            current_idx -= 1

        if not (lines[current_idx].strip().startswith('with ') and ':' in lines[current_idx]):
            return False

        # Collect nested with statements
        start_idx = current_idx
        base_indent = get_indentation(lines[start_idx])

        while current_idx < len(lines):
            line = lines[current_idx]
            line_indent = get_indentation(line)
            stripped = line.strip()

            # Skip empty lines and comments
            if not stripped or stripped.startswith('#'):
                current_idx += 1
                continue

            # Found a with statement at the right indentation level
            if stripped.startswith('with ') and ':' in stripped:
                # Extract the with expression (everything between 'with' and ':')
                with_expr = stripped[4:stripped.rfind(':')].strip()
                with_blocks.append((current_idx, line_indent, with_expr))
                current_idx += 1
                continue

            # Found a non-with statement - this is where the body starts
            break

        # Need at least 2 with statements to combine
        if len(with_blocks) < 2:
            return False

        # Check if indentation increases consistently (nested structure)
        for i in range(1, len(with_blocks)):
            if with_blocks[i][1] <= with_blocks[i-1][1]:
                # Not consistently nested
                return False

        # Extract the body (everything after the last with)
        body_lines = []

        # Find the extent of the body
        with_blocks[-1][1]
        body_indent = None

        while current_idx < len(lines):
            line = lines[current_idx]
            line_indent = get_indentation(line)
            stripped = line.strip()

            # Skip empty lines
            if not stripped:
                body_lines.append(line)
                current_idx += 1
                continue

            # First non-empty line determines body indent
            if body_indent is None:
                body_indent = line_indent

            # If indentation goes back to original level or less, we're done
            if line_indent <= base_indent:
                break

            body_lines.append(line)
            current_idx += 1

        # Combine with expressions
        combined_expressions = [expr for _, _, expr in with_blocks]

        # Create new combined with statement
        combined_with = f"{' ' * base_indent}with {', '.join(combined_expressions)}:\n"

        # Adjust body indentation (reduce by one level)
        adjusted_body = []
        for line in body_lines:
            if line.strip():  # Non-empty line
                current_indent = get_indentation(line)
                new_indent = max(0, current_indent - 4)  # Reduce by one level
                adjusted_body.append(' ' * new_indent + line.lstrip())
            else:
                adjusted_body.append(line)  # Keep empty lines as-is

        # Reconstruct file
        return (
            lines[:start_idx] +  # Before the with blocks
            [combined_with] +    # Combined with statement
            adjusted_body +      # Adjusted body
            lines[current_idx:]  # After the body
        )


    except Exception as e:
        print(f"Error fixing nested with at line {violation_line_num}: {e}")
        return False


def main():
    print("Starting SIM117 (multiple-with-statements) fix...")

    violations = get_sim117_violations()
    print(f"Found {len(violations)} SIM117 violations")

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
            result = fix_nested_with(lines, line_num)
            if result:
                lines = result
                fixed_count += 1
                modified = True
                print(f"  ✅ Fixed nested with at line {line_num}")
            else:
                print(f"  ⚠️ Skipped complex case at line {line_num}")

        if modified:
            if write_file(file_path, lines):
                print(f"  💾 Saved {file_path}")
            else:
                print(f"  ❌ Failed to save {file_path}")

    print(f"\n🎯 Summary: Fixed {fixed_count}/{len(violations)} SIM117 violations")

    # Check remaining violations
    remaining = get_sim117_violations()
    print(f"📊 Remaining SIM117 violations: {len(remaining)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
