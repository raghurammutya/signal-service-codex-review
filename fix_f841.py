#!/usr/bin/env python3
"""
Fix F841 violations - unused variables
"""

import subprocess
import sys
import re


def get_f841_violations():
    """Get F841 violations from ruff."""
    result = subprocess.run(
        ['ruff', 'check', '.', '--select', 'F841'],
        capture_output=True, text=True
    )
    
    violations = []
    lines = result.stdout.split('\n')
    
    for line in lines:
        if line.strip() and ':' in line and 'F841' in line:
            parts = line.split(':')
            if len(parts) >= 3:
                file_path = parts[0]
                line_number = int(parts[1])
                
                # Extract variable name
                var_match = re.search(r'Local variable `([^`]+)` is assigned', line)
                if var_match:
                    var_name = var_match.group(1)
                    violations.append((file_path, line_number, var_name))
    
    return violations


def fix_f841_violation(file_path, line_number, var_name):
    """Fix F841 violation by removing or renaming unused variable."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if line_number > len(lines):
            return False
        
        target_line_idx = line_number - 1
        target_line = lines[target_line_idx]
        
        # Simple cases to fix
        if f'{var_name} = ' in target_line:
            # Check if it's a simple assignment we can remove
            stripped = target_line.strip()
            
            # Case 1: Assignment that can be removed entirely
            if stripped.startswith(f'{var_name} = ') and not any(x in stripped for x in ['input(', 'open(', 'connect(']):
                # Remove the entire line if it's just a simple assignment
                if not any(keyword in stripped for keyword in ['print', 'log', 'write', 'send', 'call']):
                    lines.pop(target_line_idx)
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.writelines(lines)
                    return True
            
            # Case 2: Rename to underscore (for variables we want to keep for clarity)
            new_var_name = f'_{var_name}'
            new_line = target_line.replace(f'{var_name} = ', f'{new_var_name} = ', 1)
            
            if new_line != target_line:
                lines[target_line_idx] = new_line
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                return True
        
        return False
        
    except Exception as e:
        print(f"Error fixing {file_path}:{line_number} ({var_name}) - {e}")
        return False


def main():
    print("Fixing F841 violations (unused variables)...")
    
    violations = get_f841_violations()
    print(f"Found {len(violations)} F841 violations")
    
    if not violations:
        print("No F841 violations to fix")
        return 0
    
    fixed_count = 0
    
    for file_path, line_number, var_name in violations:
        result = fix_f841_violation(file_path, line_number, var_name)
        if result:
            print(f"✅ Fixed {file_path}:{line_number} - handled unused variable '{var_name}'")
            fixed_count += 1
        else:
            print(f"⚠️ Could not fix {file_path}:{line_number} - '{var_name}'")
    
    print(f"\n🎯 Summary: Fixed {fixed_count} F841 violations")
    
    # Check remaining violations
    remaining = get_f841_violations()
    print(f"📊 Remaining F841 violations: {len(remaining)}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
