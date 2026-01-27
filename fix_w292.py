#!/usr/bin/env python3
"""
Fix W292 violations - missing final newline
"""

import subprocess
import sys


def get_w292_violations():
    """Get W292 violations from ruff."""
    result = subprocess.run(
        ['ruff', 'check', '.', '--select', 'W292'],
        capture_output=True, text=True
    )
    
    violations = []
    lines = result.stdout.split('\n')
    
    for line in lines:
        if line.strip() and ':' in line and 'W292' in line:
            parts = line.split(':')
            if len(parts) >= 3:
                file_path = parts[0]
                violations.append(file_path)
    
    return list(set(violations))  # Remove duplicates


def fix_w292_violation(file_path):
    """Fix W292 violation by adding final newline."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Add newline if file doesn't end with one
        if content and not content.endswith('\n'):
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content + '\n')
            return True
        
        return False
        
    except Exception as e:
        print(f"Error fixing {file_path} - {e}")
        return False


def main():
    print("Fixing W292 violations (missing final newline)...")
    
    violations = get_w292_violations()
    print(f"Found {len(violations)} files with W292 violations")
    
    if not violations:
        print("No W292 violations to fix")
        return 0
    
    fixed_count = 0
    
    for file_path in violations:
        result = fix_w292_violation(file_path)
        if result:
            print(f"✅ Fixed {file_path} - added final newline")
            fixed_count += 1
        else:
            print(f"⚠️ No changes needed for {file_path}")
    
    print(f"\n🎯 Summary: Fixed {fixed_count} W292 violations")
    
    # Check remaining violations
    remaining = get_w292_violations()
    print(f"📊 Remaining W292 violations: {len(remaining)}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
