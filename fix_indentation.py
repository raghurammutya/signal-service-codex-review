#!/usr/bin/env python3
"""
Fix indentation issues caused by SIM117 with statement fixes
"""

import subprocess
import sys


def get_indentation_errors():
    """Get files with indentation syntax errors."""
    result = subprocess.run(
        ['ruff', 'check', '.'],
        capture_output=True, text=True
    )
    
    errors = []
    lines = result.stdout.split('\n')
    
    for line in lines:
        if 'SyntaxError' in line and ('unindent' in line or 'indentation' in line or 'dedent' in line):
            parts = line.split(':')
            if len(parts) >= 3:
                file_path = parts[0]
                if file_path not in errors:
                    errors.append(file_path)
    
    return errors


def fix_file_indentation(file_path):
    """Fix indentation issues in a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split into lines
        lines = content.split('\n')
        fixed_lines = []
        
        for _i, line in enumerate(lines):
            # Look for common patterns that need fixing
            if line.strip():
                # Count leading spaces
                leading_spaces = len(line) - len(line.lstrip())
                
                # Check if this line has excessive indentation (likely from our SIM117 fix)
                if leading_spaces > 20 and 'with ' not in line and 'def ' not in line and 'class ' not in line:
                    # Reduce indentation by 4 spaces
                    new_indent = max(0, leading_spaces - 4)
                    fixed_lines.append(' ' * new_indent + line.lstrip())
                else:
                    fixed_lines.append(line)
            else:
                fixed_lines.append(line)
        
        new_content = '\n'.join(fixed_lines)
        
        if new_content != content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return True
        
        return False
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False


def main():
    print("Fixing indentation errors...")
    
    error_files = get_indentation_errors()
    print(f"Found {len(error_files)} files with indentation errors")
    
    if not error_files:
        print("No indentation errors to fix")
        return 0
    
    fixed_count = 0
    
    for file_path in error_files:
        result = fix_file_indentation(file_path)
        if result:
            print(f"✅ Fixed indentation in {file_path}")
            fixed_count += 1
        else:
            print(f"⚠️ No changes made to {file_path}")
    
    print(f"\n🎯 Summary: Fixed {fixed_count} files")
    
    # Check remaining syntax errors
    remaining = get_indentation_errors()
    print(f"📊 Remaining indentation errors: {len(remaining)}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
