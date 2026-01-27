#!/usr/bin/env python3
"""
Targeted SIM117 fix script based on ruff output
"""

import sys
import re

def fix_patch_dict_patterns():
    """Fix patch.dict + patch combinations."""
    
    files_to_fix = [
        ("tests/unit/test_optional_dependencies_computation_errors.py", 88),
        ("tests/unit/test_optional_dependencies_computation_errors.py", 115), 
        ("tests/unit/test_optional_dependencies_computation_errors.py", 145),
        ("tests/unit/test_optional_dependencies_computation_errors.py", 175),
        ("tests/unit/test_optional_dependencies_computation_errors.py", 240),
    ]
    
    for file_path, line_number in files_to_fix:
        fix_patch_dict_in_file(file_path, line_number)

def fix_patch_dict_in_file(file_path, target_line_number):
    """Fix patch.dict pattern in a specific file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        target_line_idx = target_line_number - 1
        if target_line_idx >= len(lines):
            print(f"Line {target_line_number} not found in {file_path}")
            return False
        
        line = lines[target_line_idx]
        
        # Check if it's a patch.dict pattern
        if "with patch.dict('sys.modules'" in line:
            indent = len(line) - len(line.lstrip())
            next_line_idx = target_line_idx + 1
            
            if next_line_idx < len(lines):
                next_line = lines[next_line_idx]
                
                # Check for nested patch pattern
                if ("with patch('builtins.__import__'" in next_line and
                    len(next_line) - len(next_line.lstrip()) > indent):
                    
                    # Extract the patch.dict part
                    patch_dict_match = re.search(r"with patch\.dict\(([^)]+)\):", line)
                    if patch_dict_match:
                        patch_dict_args = patch_dict_match.group(1)
                    
                    # Extract the patch part from next line
                    patch_match = re.search(r"with (patch\([^:]+)\):", next_line)
                    if patch_match:
                        patch_args = patch_match.group(1)
                        
                        # Create merged with statement
                        base_indent = ' ' * indent
                        new_line = f"{base_indent}with patch.dict({patch_dict_args}), {patch_args}:\n"
                        
                        # Replace both lines with merged line
                        lines[target_line_idx] = new_line
                        lines.pop(next_line_idx)
                        
                        # Adjust indentation of following lines
                        next_indent = len(next_line) - len(next_line.lstrip())
                        reduction = next_indent - indent
                        
                        for i in range(next_line_idx, len(lines)):
                            if not lines[i].strip():
                                continue
                            current_indent = len(lines[i]) - len(lines[i].lstrip())
                            if current_indent > next_indent:
                                new_indent = max(0, current_indent - reduction)
                                lines[i] = ' ' * new_indent + lines[i].lstrip()
                            elif current_indent <= indent:
                                break
                        
                        # Write back
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.writelines(lines)
                        
                        print(f"✅ Fixed patch.dict pattern at {file_path}:{target_line_number}")
                        return True
        
        print(f"⚠️ Pattern not found at {file_path}:{target_line_number}")
        return False
        
    except Exception as e:
        print(f"❌ Error fixing {file_path}:{target_line_number}: {e}")
        return False

def fix_auth_patch_patterns():
    """Fix auth patch patterns in test files."""
    
    files_to_fix = [
        ("tests/test_sdk_signal_listing.py", 86),
        ("tests/test_sdk_signal_listing.py", 202), 
        ("tests/test_sdk_signal_listing.py", 226),
        ("tests/test_sdk_signal_listing.py", 260),
        ("tests/test_sdk_signal_listing.py", 291),
    ]
    
    for file_path, line_number in files_to_fix:
        fix_auth_patch_in_file(file_path, line_number)

def fix_auth_patch_in_file(file_path, target_line_number):
    """Fix auth patch pattern in a specific file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        target_line_idx = target_line_number - 1
        if target_line_idx >= len(lines):
            return False
        
        line = lines[target_line_idx]
        
        # Check if it's an auth patch pattern
        if "with patch('app.core.auth.get_current_user_from_gateway'" in line:
            indent = len(line) - len(line.lstrip())
            
            # Find the nested with statement
            for i in range(target_line_idx + 1, min(target_line_idx + 10, len(lines))):
                next_line = lines[i]
                if ("with patch(" in next_line and 
                    len(next_line) - len(next_line.lstrip()) > indent):
                    
                    # Extract the contexts
                    auth_context = re.search(r"with (patch\([^)]+\))", line)
                    next_context = re.search(r"with (patch\([^)]+(?:,\s*[^)]+)*\))", next_line)
                    
                    if auth_context and next_context:
                        auth_patch = auth_context.group(1)
                        next_patch = next_context.group(1)
                        
                        # Handle multi-line patterns
                        combined_line = line.rstrip()
                        if not combined_line.endswith(':'):
                            combined_line += ':'
                        
                        base_indent = ' ' * indent
                        new_line = f"{base_indent}with {auth_patch}, {next_patch}:\n"
                        
                        # Replace the lines
                        lines[target_line_idx] = new_line
                        lines.pop(i)
                        
                        # Write back
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.writelines(lines)
                        
                        print(f"✅ Fixed auth patch pattern at {file_path}:{target_line_number}")
                        return True
                    break
        
        return False
        
    except Exception as e:
        print(f"❌ Error fixing {file_path}:{target_line_number}: {e}")
        return False

def main():
    print("🎯 Targeted SIM117 fixes...")
    
    print("\n🔧 Fixing patch.dict patterns...")
    fix_patch_dict_patterns()
    
    print("\n🔧 Fixing auth patch patterns...")
    fix_auth_patch_patterns()
    
    print("\n✅ Targeted fixes complete!")
    return 0

if __name__ == "__main__":
    sys.exit(main())