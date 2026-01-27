#!/usr/bin/env python3
"""
Fix E722 (bare except) violations
"""
import subprocess


def fix_bare_except():
    """Fix E722 violations by replacing bare except with except Exception"""
    result = subprocess.run(
        ['ruff', 'check', '.', '--select=E722'],
        capture_output=True, text=True
    )

    violations = []
    for line in result.stdout.split('\n'):
        if ':' in line and 'E722' in line:
            parts = line.split(':')
            if len(parts) >= 3:
                file_path = parts[0]
                line_no = int(parts[1])
                violations.append((file_path, line_no))

    fixed_count = 0
    for file_path, line_no in violations:
        try:
            with open(file_path) as f:
                lines = f.readlines()

            if line_no <= len(lines):
                line = lines[line_no - 1]
                if 'except:' in line:
                    # Replace bare except with except Exception
                    new_line = line.replace('except:', 'except Exception:')
                    lines[line_no - 1] = new_line

                    with open(file_path, 'w') as f:
                        f.writelines(lines)

                    print(f"Fixed E722 in {file_path}:{line_no}")
                    fixed_count += 1

        except Exception as e:
            print(f"Error fixing {file_path}:{line_no}: {e}")

    print(f"\nFixed {fixed_count} E722 violations")

if __name__ == '__main__':
    fix_bare_except()
