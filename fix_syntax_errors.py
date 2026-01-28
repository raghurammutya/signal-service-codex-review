#!/usr/bin/env python3
"""
Fix syntax errors caused by automated SIM102 fixes
"""

import re
import subprocess
import sys


def get_syntax_errors():
    """Get files with syntax errors."""
    result = subprocess.run(
        ['ruff', 'check', '.'],
        capture_output=True, text=True
    )

    error_files = {}
    lines = result.stdout.split('\n')

    for line in lines:
        if 'SyntaxError' in line and ':' in line and not line.strip().startswith('#'):
            parts = line.split(':')
            if len(parts) >= 3:
                try:
                    file_path = parts[0]
                    line_number = int(parts[1])
                    error_msg = ':'.join(parts[3:]).strip()

                    if file_path not in error_files:
                        error_files[file_path] = []
                    error_files[file_path].append((line_number, error_msg))
                except ValueError:
                    # Skip lines that don't have proper line numbers
                    continue

    return error_files


def fix_common_syntax_patterns(content):
    """Fix common syntax error patterns from SIM102 automation."""

    # Pattern 1: "if if" (duplicate if keywords)
    content = re.sub(r'\bif\s+if\b', 'if', content)

    # Pattern 2: "and and" (duplicate and keywords)
    content = re.sub(r'\band\s+and\b', 'and', content)

    # Pattern 3: "or or" (duplicate or keywords)
    content = re.sub(r'\bor\s+or\b', 'or', content)

    # Pattern 4: "as e as e" (duplicate exception binding)
    content = re.sub(r'\bas\s+(\w+)\s+as\s+\1\b', r'as \1', content)

    # Pattern 5: Fix malformed with statements "with c with"
    content = re.sub(r'\bwith\s+\w+\s+with\b', 'with', content)

    # Pattern 6: Fix empty conditions in for loops "for skip in [:"
    content = re.sub(r'for\s+\w+\s+in\s+\[:', 'for skip in [', content)

    # Pattern 7: Fix malformed function calls with missing arguments
    content = re.sub(r'(\w+\([^)]*),\s*:\s*$', r'\1):', content, flags=re.MULTILINE)

    # Pattern 8: Fix trailing commas in with statements
    content = re.sub(r'(\bwith\s+[^:]+),\s*:', r'\1:', content)

    # Pattern 9: Fix malformed patch calls with empty arguments
    return re.sub(r"patch\('([^']+)',\s*,", r"patch('\1',", content)



def fix_indentation_issues(lines):
    """Fix indentation issues from automated combining."""
    fixed_lines = []

    for _i, line in enumerate(lines):
        # Check for excessive indentation (more than 20 spaces)
        if line.strip() and len(line) - len(line.lstrip()) > 20:
            # Reduce to more reasonable indentation
            content = line.lstrip()
            # Use 8 spaces for deeply nested code
            fixed_lines.append('        ' + content)
        else:
            fixed_lines.append(line)

    return fixed_lines


def fix_file_syntax_errors(file_path):
    """Fix syntax errors in a specific file."""
    try:
        print(f"Fixing {file_path}...")

        with open(file_path, encoding='utf-8') as f:
            content = f.read()

        original_content = content

        # Apply common pattern fixes
        content = fix_common_syntax_patterns(content)

        # Fix line-by-line issues
        lines = content.split('\n')
        lines = fix_indentation_issues(lines)

        # Rejoin content
        content = '\n'.join(lines)

        # Write back if changed
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True

        return False

    except Exception as e:
        print(f"Error fixing {file_path}: {e}")
        return False


def main():
    print("🔧 Fixing syntax errors from automation...")

    # Get initial count
    error_files = get_syntax_errors()
    initial_count = sum(len(errors) for errors in error_files.values())
    print(f"Found {initial_count} syntax errors in {len(error_files)} files")

    if not error_files:
        print("No syntax errors found!")
        return 0

    fixed_files = 0

    # Fix each file
    for file_path in error_files:
        if fix_file_syntax_errors(file_path):
            print(f"✅ Fixed syntax errors in {file_path}")
            fixed_files += 1
        else:
            print(f"⚠️ No changes made to {file_path}")

    print(f"\n🎯 Summary: Processed {fixed_files} files")

    # Check remaining errors
    remaining_errors = get_syntax_errors()
    remaining_count = sum(len(errors) for errors in remaining_errors.values())

    print(f"📊 Remaining syntax errors: {remaining_count}")
    print(f"📈 Reduction: {initial_count - remaining_count} errors fixed")

    if remaining_errors:
        print("\n🔍 Remaining error files:")
        for file_path, errors in remaining_errors.items():
            print(f"  - {file_path}: {len(errors)} errors")

    return 0


if __name__ == "__main__":
    sys.exit(main())
