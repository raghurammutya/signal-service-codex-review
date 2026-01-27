#!/usr/bin/env python3
"""
Fix E402 violations by moving module imports to the top of files
"""
import subprocess


def fix_e402_violations():
    """Fix E402 module import not at top violations"""
    result = subprocess.run(
        ['ruff', 'check', '.', '--select=E402'],
        capture_output=True, text=True
    )

    files_to_fix = {}

    for line in result.stdout.split('\n'):
        if ':' in line and 'E402' in line:
            parts = line.split(':')
            if len(parts) >= 2:
                file_path = parts[0]
                line_no = int(parts[1])

                if file_path not in files_to_fix:
                    files_to_fix[file_path] = []
                files_to_fix[file_path].append(line_no)

    fixed_count = 0

    for file_path, line_numbers in files_to_fix.items():
        try:
            with open(file_path) as f:
                lines = f.readlines()

            # Extract imports from middle of file
            imports_to_move = []
            lines_to_remove = []

            for line_no in sorted(line_numbers, reverse=True):
                if line_no <= len(lines):
                    line = lines[line_no - 1].strip()
                    if line.startswith(('import ', 'from ')):
                        imports_to_move.append(line)
                        lines_to_remove.append(line_no - 1)  # Convert to 0-indexed

            # Remove the imports from their current positions
            for idx in sorted(lines_to_remove, reverse=True):
                lines.pop(idx)

            # Find where to insert imports (after docstring and existing imports)
            insert_position = 0
            in_docstring = False
            docstring_char = None

            for i, line in enumerate(lines):
                stripped = line.strip()

                # Handle docstring detection
                if not in_docstring and (stripped.startswith(('"""', "'''"))):
                    docstring_char = stripped[:3]
                    in_docstring = True
                    if stripped.endswith(docstring_char) and len(stripped) > 3:
                        in_docstring = False
                        insert_position = i + 1
                elif in_docstring and stripped.endswith(docstring_char):
                    in_docstring = False
                    insert_position = i + 1
                elif not in_docstring and (stripped.startswith(('import ', 'from '))):
                    insert_position = i + 1
                elif not in_docstring and stripped and not stripped.startswith('#'):
                    break

            # Insert imports at the correct position
            if imports_to_move:
                for import_line in reversed(imports_to_move):
                    lines.insert(insert_position, import_line + '\n')

                with open(file_path, 'w') as f:
                    f.writelines(lines)

                print(f"Fixed {len(imports_to_move)} E402 violations in {file_path}")
                fixed_count += len(imports_to_move)

        except Exception as e:
            print(f"Error fixing {file_path}: {e}")

    print(f"\nFixed {fixed_count} E402 violations total")

if __name__ == '__main__':
    fix_e402_violations()
