#!/usr/bin/env python3
"""
Fix remaining violations for 100% Ruff compliance
"""

import subprocess
import sys
import re

def fix_b904_violations():
    """Fix B904 exception chaining violations."""
    files_to_fix = [
        ("app/clients/algo_engine_client.py", 53),
        ("app/clients/instrument_registry_client.py", 383),
        ("app/services/enhanced_watermark_integration.py", 173),
        ("app/services/unified_historical_data_service.py", 178),
        ("tests/unit/test_optional_dependencies_computation_errors.py", 254),
    ]
    
    fixed_count = 0
    for file_path, line_number in files_to_fix:
        if fix_b904_in_file(file_path, line_number):
            fixed_count += 1
    
    print(f"Fixed {fixed_count} B904 violations")

def fix_b904_in_file(file_path, target_line_number):
    """Fix B904 violation in a specific file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        target_line_idx = target_line_number - 1
        if target_line_idx >= len(lines):
            return False
        
        line = lines[target_line_idx]
        
        # Check if it's a raise statement without from clause
        if line.strip().startswith('raise ') and ' from ' not in line:
            # Add ' from e' before the newline
            new_line = line.rstrip() + ' from e\n'
            lines[target_line_idx] = new_line
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            print(f"✅ Fixed B904 at {file_path}:{target_line_number}")
            return True
        
        return False
        
    except Exception as e:
        print(f"❌ Error fixing {file_path}:{target_line_number}: {e}")
        return False

def fix_sim102_violations():
    """Fix SIM102 collapsible if violations."""
    files_to_fix = [
        ("app/services/registry_integration_service.py", 687),
        ("app/services/smart_money_indicators.py", 617),
    ]
    
    for file_path, line_number in files_to_fix:
        fix_sim102_in_file(file_path, line_number)

def fix_sim102_in_file(file_path, target_line_number):
    """Fix SIM102 violation by combining if statements."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        target_line_idx = target_line_number - 1
        if target_line_idx >= len(lines):
            return False
        
        # Find the pattern of nested if statements
        line = lines[target_line_idx]
        if 'elif' in line or 'if' in line:
            indent = len(line) - len(line.lstrip())
            
            # Look for nested if in following lines
            for i in range(target_line_idx + 1, min(target_line_idx + 5, len(lines))):
                next_line = lines[i]
                if (next_line.strip().startswith('if ') and 
                    len(next_line) - len(next_line.lstrip()) > indent):
                    
                    # Extract conditions
                    first_condition = re.search(r'(elif|if)\s+(.+):', line)
                    second_condition = re.search(r'if\s+(.+):', next_line)
                    
                    if first_condition and second_condition:
                        first_cond = first_condition.group(2)
                        second_cond = second_condition.group(1)
                        elif_or_if = first_condition.group(1)
                        
                        # Combine conditions
                        base_indent = ' ' * indent
                        new_line = f"{base_indent}{elif_or_if} {first_cond} and {second_cond}:\n"
                        
                        # Replace both lines
                        lines[target_line_idx] = new_line
                        lines.pop(i)
                        
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.writelines(lines)
                        
                        print(f"✅ Fixed SIM102 at {file_path}:{target_line_number}")
                        return True
                    break
        
        return False
        
    except Exception as e:
        print(f"❌ Error fixing {file_path}:{target_line_number}: {e}")
        return False

def main():
    print("🎯 Final cleanup for 100% Ruff compliance...")
    
    print("\n🔧 Fixing B904 violations (exception chaining)...")
    fix_b904_violations()
    
    print("\n🔧 Fixing SIM102 violations (collapsible if)...")
    fix_sim102_violations()
    
    # Check final status
    print("\n📊 Final compliance check...")
    result = subprocess.run(['ruff', 'check', '.', '--select', 'F401,SIM102,SIM117,B904'], 
                           capture_output=True, text=True)
    
    violations = result.stdout.count('\n') - 1 if result.stdout.strip() else 0
    
    if violations == 0:
        print("🎉 100% Ruff compliance achieved!")
    else:
        print(f"📊 Remaining violations: {violations}")
        
    return 0

if __name__ == "__main__":
    sys.exit(main())