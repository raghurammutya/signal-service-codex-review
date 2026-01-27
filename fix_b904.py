#!/usr/bin/env python3
"""
Systematic B904 exception chaining fix script
"""
import re
import subprocess
from pathlib import Path


def get_b904_violations():
    """Get all B904 violations from ruff"""
    result = subprocess.run(
        ['ruff', 'check', '.', '--select=B904', '--output-format=json'],
        capture_output=True, text=True, cwd=Path(__file__).parent
    )

    if result.returncode == 0:
        return []

    # Parse output to get file locations
    violations = []
    for line in result.stdout.strip().split('\n'):
        if 'B904' in line:
            # Extract file:line info
            match = re.match(r'([^:]+):(\d+):', line)
            if match:
                violations.append((match.group(1), int(match.group(2))))

    return violations

def fix_b904_in_file(file_path: str, line_number: int):
    """Fix B904 violation at specific line in file"""
    try:
        with open(file_path) as f:
            lines = f.readlines()

        if line_number > len(lines):
            return False

        line = lines[line_number - 1]

        # Common B904 patterns and fixes
        patterns = [
            # raise SomeException("message")
            (r'(\s*)(raise\s+\w+\([^)]*\))\s*$', r'\1\2 from e\n'),
            # raise SomeException(f"message {e}")
            (r'(\s*)(raise\s+\w+\(f?"[^"]*"\))\s*$', r'\1\2 from e\n'),
            # raise SomeException(var)
            (r'(\s*)(raise\s+\w+\([^)]+\))\s*$', r'\1\2 from e\n'),
        ]

        fixed = False
        for pattern, replacement in patterns:
            if re.match(pattern, line) and ' from e' not in line and ' from None' not in line:
                new_line = re.sub(pattern, replacement, line)
                lines[line_number - 1] = new_line
                fixed = True
                break

        if fixed:
            with open(file_path, 'w') as f:
                f.writelines(lines)
            return True

    except Exception as e:
        print(f"Error fixing {file_path}:{line_number}: {e}")

    return False

def main():
    """Fix all B904 violations"""
    violations = get_b904_violations()
    print(f"Found {len(violations)} B904 violations")

    fixed_count = 0
    for file_path, line_number in violations:
        if fix_b904_in_file(file_path, line_number):
            print(f"Fixed: {file_path}:{line_number}")
            fixed_count += 1

    print(f"\nFixed {fixed_count} B904 violations")

    # Check remaining violations
    remaining = get_b904_violations()
    print(f"Remaining B904 violations: {len(remaining)}")

if __name__ == '__main__':
    main()
