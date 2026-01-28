#!/usr/bin/env python3
"""
Fix malformed raise statements created by B904 script
"""

import re
import subprocess
import sys


def get_syntax_errors():
    """Get files with syntax errors from ruff."""
    result = subprocess.run(
        ['ruff', 'check', '.'],
        capture_output=True, text=True
    )

    errors = []
    lines = result.stdout.split('\n')

    for line in lines:
        if 'SyntaxError' in line and 'from' in line and ':' in line:
            parts = line.split(':')
            if len(parts) >= 3:
                file_path = parts[0]
                line_num = int(parts[1])
                errors.append((file_path, line_num))

    return list(set(errors))  # Remove duplicates


def fix_malformed_raises(file_path):
    """Fix malformed raise statements in a file."""
    try:
        with open(file_path, encoding='utf-8') as f:
            content = f.read()

        # Pattern to match malformed HTTPException raises
        # raise HTTPException( from e\n            status_code=...
        pattern = r'raise\s+(\w+Exception)\(\s+from\s+(\w+)\s*\n(\s+)'

        def replace_func(match):
            exception_type = match.group(1)
            indent = match.group(3)
            return f'raise {exception_type}(\n{indent}'

        # Fix the malformed pattern
        new_content = re.sub(pattern, replace_func, content)

        # Now fix the missing "from e" at the end
        # Look for patterns like:
        # )
        # followed by except or end of block
        # and add "from e" before the closing )

        lines = new_content.split('\n')
        fixed_lines = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Look for lines that end with just ")"
            if line.strip() == ')' and i > 0:
                # Check if this is part of an HTTPException
                prev_context = '\n'.join(lines[max(0, i-10):i])
                if 'HTTPException(' in prev_context and 'detail=' in prev_context:
                    # Look for the exception variable in except clause
                    except_var = None
                    for j in range(i, max(0, i-15), -1):
                        if 'except' in lines[j] and ' as ' in lines[j]:
                            match = re.search(r'except\s+[^:]+\s+as\s+(\w+)\s*:', lines[j])
                            if match:
                                except_var = match.group(1)
                                break

                    if except_var:
                        line = f'{line[:-1]} from {except_var}'

            fixed_lines.append(line)
            i += 1

        final_content = '\n'.join(fixed_lines)

        if final_content != content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(final_content)
            return True

        return False

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False


def main():
    print("Fixing malformed raise statements...")

    errors = get_syntax_errors()
    print(f"Found {len(errors)} files with syntax errors")

    if not errors:
        print("No syntax errors to fix")
        return 0

    fixed_files = set()

    for file_path, _line_num in errors:
        if file_path not in fixed_files:
            result = fix_malformed_raises(file_path)
            if result:
                print(f"✅ Fixed malformed raises in {file_path}")
                fixed_files.add(file_path)
            else:
                print(f"⚠️ No changes made to {file_path}")

    print(f"\n🎯 Summary: Fixed {len(fixed_files)} files")

    # Check remaining syntax errors
    remaining = get_syntax_errors()
    print(f"📊 Remaining syntax errors: {len(remaining)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
