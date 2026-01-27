#!/usr/bin/env python3
"""
Selective F401 Unused Import Fix Script
Carefully removes unused imports while preserving availability checks.
"""

import re
import subprocess
import sys


def get_f401_violations():
    """Get all F401 violations from ruff."""
    result = subprocess.run(
        ['ruff', 'check', '--select=F401', '.'],
        capture_output=True, text=True
    )

    violations = []
    lines = result.stdout.split('\n')

    for line in lines:
        if 'F401' in line and ':' in line:
            parts = line.split(':')
            if len(parts) >= 3:
                file_path = parts[0]
                line_num = int(parts[1])
                violations.append((file_path, line_num, line))

    return violations


def is_availability_check(lines, line_idx):
    """Check if this import is part of an availability check pattern."""
    if line_idx >= len(lines):
        return False

    # Look for try/except ImportError pattern
    context_start = max(0, line_idx - 5)
    context_end = min(len(lines), line_idx + 10)
    context = '\n'.join(lines[context_start:context_end])

    # Common patterns for availability checks
    availability_patterns = [
        'try:.*except ImportError',
        'AVAILABLE = True.*except ImportError.*AVAILABLE = False',
        'components\\[.*\\] = "available"',
        'importlib.util.find_spec',
        'consider using.*find_spec.*test for availability'
    ]

    return any(re.search(pattern, context, re.DOTALL | re.IGNORECASE)
               for pattern in availability_patterns)


def fix_unused_import(file_path, line_num, violation_text):
    """Fix a single unused import if safe to do so."""
    try:
        with open(file_path, encoding='utf-8') as f:
            lines = f.readlines()

        if line_num > len(lines):
            return False

        line_idx = line_num - 1

        # Skip availability checks
        if is_availability_check(lines, line_idx):
            return False

        original_line = lines[line_idx]

        # Skip if this is a complex import line
        stripped = original_line.strip()
        if ('(' in stripped and ')' not in stripped) or stripped.endswith(','):
            return False

        # Simple unused import - remove the line
        if stripped.startswith(('import ', 'from ')):
            # Check if removing this line would create syntax issues
            # by looking for multi-line import statements
            if '(' in original_line and ')' not in original_line:
                return False  # Multi-line import, too complex

            # Remove the line
            lines.pop(line_idx)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)

            return True

        return False

    except Exception as e:
        print(f"Error processing {file_path}:{line_num}: {e}")
        return False


def main():
    print("Fixing F401 unused imports (selective)...")

    violations = get_f401_violations()
    print(f"Found {len(violations)} F401 violations")

    if not violations:
        print("No violations to fix")
        return 0

    fixed_count = 0
    skipped_count = 0

    for file_path, line_num, violation_text in violations:
        if 'consider using `importlib.util.find_spec`' in violation_text:
            print(f"  ⚠️ Skipped availability check: {file_path}:{line_num}")
            skipped_count += 1
            continue

        result = fix_unused_import(file_path, line_num, violation_text)
        if result:
            print(f"  ✅ Removed unused import: {file_path}:{line_num}")
            fixed_count += 1
        else:
            print(f"  ⚠️ Skipped complex case: {file_path}:{line_num}")
            skipped_count += 1

    print(f"\n🎯 Summary: Fixed {fixed_count} unused imports, skipped {skipped_count}")

    # Check remaining violations
    remaining = get_f401_violations()
    print(f"📊 Remaining F401 violations: {len(remaining)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
