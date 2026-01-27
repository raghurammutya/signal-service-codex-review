#!/usr/bin/env python3
"""
Fix F821 violations (undefined names) - specifically for exception handling
"""
import re
import subprocess


def fix_f821_violations():
    """Fix F821 undefined name errors in exception blocks"""
    result = subprocess.run(
        ['ruff', 'check', '.', '--select=F821'],
        capture_output=True, text=True
    )

    patterns = [
        # Pattern: except SomeError: ... from e (missing 'as e')
        (r'(\s+)(except\s+[^:]+):\s*\n(\s+.*from e)', r'\1\2 as e:\n\3'),
        # Pattern: except (Error1, Error2): ... from e (missing 'as e')
        (r'(\s+)(except\s+\([^)]+\)):\s*\n(\s+.*from e)', r'\1\2 as e:\n\3'),
    ]

    fixed_files = set()
    violations = []

    for line in result.stdout.split('\n'):
        if ':' in line and 'F821' in line and 'Undefined name `e`' in line:
            parts = line.split(':')
            if len(parts) >= 2:
                file_path = parts[0]
                line_no = int(parts[1])
                violations.append((file_path, line_no))

    for file_path, _line_no in violations:
        try:
            with open(file_path) as f:
                content = f.read()

            original_content = content

            # Apply regex patterns
            for pattern, replacement in patterns:
                content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

            if content != original_content:
                with open(file_path, 'w') as f:
                    f.write(content)
                fixed_files.add(file_path)

        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    print(f"Fixed F821 violations in {len(fixed_files)} files:")
    for file_path in sorted(fixed_files):
        print(f"  - {file_path}")

if __name__ == '__main__':
    fix_f821_violations()
