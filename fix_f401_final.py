#!/usr/bin/env python3
"""
Fix F401 violations - remove unused imports
Smart version that handles special cases like availability checks
"""

import re
import subprocess
import sys


def get_f401_violations():
    """Get F401 violations from ruff."""
    result = subprocess.run(
        ['ruff', 'check', '.', '--select', 'F401'],
        capture_output=True, text=True
    )

    violations = []
    lines = result.stdout.split('\n')

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() and ':' in line and 'F401' in line and '[*]' in line:
            # Check if this is a fixable violation (has [*])
            parts = line.split(':')
            if len(parts) >= 3:
                    file_path = parts[0]
                    line_number = int(parts[1])

                    # Extract import name from the message
                    import_match = re.search(r'`([^`]+)` imported but unused', line)
                    if import_match:
                        import_name = import_match.group(1)
                        violations.append((file_path, line_number, import_name))
        i += 1

    return violations


def is_availability_check_context(lines, line_idx):
    """Check if this import is part of an availability check pattern."""
    try:
        # Look for try/except patterns around the import
        context_start = max(0, line_idx - 3)
        context_end = min(len(lines), line_idx + 5)
        context = ''.join(lines[context_start:context_end]).lower()

        # Common availability check patterns
        patterns = [
            'try:',
            'except importerror',
            'except modulenotfounderror',
            'importlib.util.find_spec',
            'availability',
            'available',
            'optional',
        ]

        return any(pattern in context for pattern in patterns)
    except Exception:
        return False


def fix_f401_violation(file_path, line_number, import_name):
    """Fix a specific F401 violation by removing unused import."""
    try:
        with open(file_path, encoding='utf-8') as f:
            lines = f.readlines()

        if line_number > len(lines):
            return False

        target_line_idx = line_number - 1
        target_line = lines[target_line_idx]

        # Check if this is an availability check - don't remove those
        if is_availability_check_context(lines, target_line_idx):
            return False

        # Check if this is a special file that might need imports for type checking
        special_files = ['__init__.py', 'conftest.py', 'test_', 'fix_', 'script']
        if any(special in file_path.lower() for special in special_files) and ('type:' in target_line.lower() or 'typing' in target_line.lower()):
            # Be more careful with special files
            return False

        # Simple case: remove the entire line if it's a single import
        if target_line.strip().startswith(('import ', 'from ')) and import_name in target_line:
            # Check if it's a single import line
            if target_line.count(',') == 0:
                # Remove the entire line
                lines.pop(target_line_idx)

                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                return True
            # Multiple imports on same line - remove just this import
            new_line = remove_import_from_line(target_line, import_name)
            if new_line != target_line:
                lines[target_line_idx] = new_line

                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                return True

        return False

    except Exception as e:
        print(f"Error fixing {file_path}:{line_number} ({import_name}) - {e}")
        return False


def remove_import_from_line(line, import_name):
    """Remove a specific import from a line with multiple imports."""
    # Handle "from module import a, b, c" cases
    if 'from ' in line and 'import ' in line:
        parts = line.split('import ', 1)
        if len(parts) == 2:
            prefix = parts[0] + 'import '
            imports_part = parts[1]

            # Split imports by comma and remove the target
            imports = [imp.strip() for imp in imports_part.split(',')]
            imports = [imp for imp in imports if import_name not in imp]

            if imports:
                new_imports = ', '.join(imports)
                return prefix + new_imports
            # No imports left, remove the entire line
            return ''

    # Handle "import a, b, c" cases
    elif line.strip().startswith('import '):
        imports_part = line.replace('import ', '', 1)
        imports = [imp.strip() for imp in imports_part.split(',')]
        imports = [imp for imp in imports if import_name not in imp]

        if imports:
            new_imports = ', '.join(imports)
            indent = len(line) - len(line.lstrip())
            return ' ' * indent + 'import ' + new_imports
        return ''

    return line


def main():
    print("Fixing F401 violations (unused imports)...")

    violations = get_f401_violations()
    print(f"Found {len(violations)} fixable F401 violations")

    if not violations:
        print("No fixable F401 violations found")
        return 0

    fixed_count = 0
    skipped_count = 0

    for file_path, line_number, import_name in violations:
        result = fix_f401_violation(file_path, line_number, import_name)
        if result:
            print(f"✅ Fixed {file_path}:{line_number} - removed unused import '{import_name}'")
            fixed_count += 1
        else:
            print(f"⚠️ Skipped {file_path}:{line_number} - '{import_name}' (availability check or special case)")
            skipped_count += 1

    print(f"\n🎯 Summary: Fixed {fixed_count} F401 violations, skipped {skipped_count}")

    # Check remaining violations
    remaining = get_f401_violations()
    print(f"📊 Remaining fixable F401 violations: {len(remaining)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
