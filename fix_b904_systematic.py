#!/usr/bin/env python3
"""
Systematic B904 fix script - adds 'from e' to raise statements in except blocks
"""
import re
import subprocess


def get_b904_locations():
    """Get all B904 violation locations"""
    result = subprocess.run(
        ['ruff', 'check', '.', '--select=B904'],
        capture_output=True, text=True
    )

    locations = []
    for line in result.stdout.split('\n'):
        if ':' in line and 'B904' in line:
            # Extract file:line format
            match = re.match(r'([^:]+):(\d+):', line)
            if match:
                locations.append((match.group(1), int(match.group(2))))

    return locations

def fix_b904_violation(file_path: str, line_no: int) -> bool:
    """Fix a specific B904 violation"""
    try:
        with open(file_path) as f:
            lines = f.readlines()

        if line_no > len(lines):
            return False

        line = lines[line_no - 1]

        # Only fix if it's a raise statement without 'from'
        if 'raise ' in line and ' from ' not in line:
            # Check if line ends with a closing parenthesis or quote
            stripped = line.rstrip()
            if stripped.endswith((')', '"', "'")):
                # Add ' from e' before the newline
                new_line = stripped + ' from e\n'
                lines[line_no - 1] = new_line

                with open(file_path, 'w') as f:
                    f.writelines(lines)

                return True

    except Exception as e:
        print(f"Error fixing {file_path}:{line_no}: {e}")

    return False

def main():
    """Fix all B904 violations"""
    locations = get_b904_locations()
    print(f"Found {len(locations)} B904 violations")

    fixed_count = 0
    for file_path, line_no in locations:
        if fix_b904_violation(file_path, line_no):
            print(f"Fixed B904: {file_path}:{line_no}")
            fixed_count += 1

    print(f"\nFixed {fixed_count} B904 violations")

    # Check remaining
    remaining_locations = get_b904_locations()
    print(f"Remaining B904 violations: {len(remaining_locations)}")

if __name__ == '__main__':
    main()
