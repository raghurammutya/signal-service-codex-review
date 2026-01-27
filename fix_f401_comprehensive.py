#!/usr/bin/env python3
"""
Comprehensive F401 violations fix - smart import cleanup
Preserves availability checks and removes genuine unused imports
"""

import subprocess
import sys
import re


def get_f401_violations():
    """Get F401 violations from ruff."""
    result = subprocess.run(
        ['ruff', 'check', '.', '--select', 'F401'],
        capture_output=True, text=True
    )
    
    violations = []
    lines = result.stdout.split('\n')
    
    for line in lines:
        if line.strip() and ':' in line and 'F401' in line:
            parts = line.split(':')
            if len(parts) >= 3:
                try:
                    file_path = parts[0]
                    line_number = int(parts[1])
                    
                    # Extract import name from the message
                    import_match = re.search(r'`([^`]+)` imported but unused', line)
                    if import_match:
                        import_name = import_match.group(1)
                        
                        # Check if it's an availability check
                        is_availability_check = 'consider using `importlib.util.find_spec`' in line
                        
                        violations.append((file_path, line_number, import_name, is_availability_check))
                except ValueError:
                    continue
    
    return violations


def is_import_in_try_except_block(lines, line_idx):
    """Check if import is in a try/except block for availability checking."""
    # Look backwards for 'try:' and forwards for 'except ImportError:'
    try_found = False
    except_found = False
    
    # Look backwards for try (within 5 lines)
    for i in range(max(0, line_idx - 5), line_idx):
        if 'try:' in lines[i]:
            try_found = True
            break
    
    # Look forwards for except ImportError (within 10 lines)
    for i in range(line_idx + 1, min(len(lines), line_idx + 10)):
        if 'except ImportError' in lines[i] or 'except ModuleNotFoundError' in lines[i]:
            except_found = True
            break
    
    return try_found and except_found


def fix_f401_violation(file_path, line_number, import_name, is_availability_check):
    """Fix F401 violation intelligently."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if line_number > len(lines):
            return False, "Line number out of range"
        
        target_line_idx = line_number - 1
        lines[target_line_idx]
        
        # Check if this is in a try/except block
        in_try_except = is_import_in_try_except_block(lines, target_line_idx)
        
        # Skip availability checks in try/except blocks unless we can convert them
        if in_try_except and is_availability_check:
            # Try to convert to importlib.util.find_spec pattern
            return convert_to_importlib_pattern(file_path, lines, target_line_idx, import_name)
        
        # For genuine unused imports outside try/except, remove them
        if not in_try_except:
            return remove_unused_import(file_path, lines, target_line_idx, import_name)
        
        return False, "Availability check in try/except - preserved"
        
    except Exception as e:
        return False, f"Error: {e}"


def convert_to_importlib_pattern(file_path, lines, line_idx, import_name):
    """Convert try/except import to importlib.util.find_spec pattern."""
    try:
        # This is complex and risky to automate for all cases
        # For now, just skip these complex conversions
        return False, "Complex availability check - skipped"
    except Exception as e:
        return False, f"Conversion failed: {e}"


def remove_unused_import(file_path, lines, line_idx, import_name):
    """Remove genuinely unused import."""
    try:
        target_line = lines[line_idx]
        
        # Check if it's a single import line or part of a multi-import
        if target_line.strip().startswith('import ') and ',' not in target_line:
            # Single import line - remove entirely
            lines.pop(line_idx)
        elif target_line.strip().startswith('from ') and 'import ' in target_line:
            # From import - need to handle carefully
            if ',' in target_line:
                # Multiple imports - remove just this one
                new_line = remove_import_from_line(target_line, import_name)
                if new_line and new_line.strip():
                    lines[line_idx] = new_line
                else:
                    lines.pop(line_idx)
            else:
                # Single from import - remove entirely
                lines.pop(line_idx)
        else:
            return False, "Complex import pattern - skipped"
        
        # Write back the modified content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        return True, "Removed unused import"
        
    except Exception as e:
        return False, f"Removal failed: {e}"


def remove_import_from_line(line, import_name):
    """Remove specific import from a line with multiple imports."""
    if 'from ' in line and 'import ' in line:
        # Split the line at 'import'
        parts = line.split('import ', 1)
        if len(parts) == 2:
            prefix = parts[0] + 'import '
            imports_part = parts[1]
            
            # Split imports and remove the target
            imports = [imp.strip() for imp in imports_part.split(',')]
            imports = [imp for imp in imports if import_name.split('.')[-1] not in imp]
            
            if imports:
                return prefix + ', '.join(imports) + '\n'
            else:
                return ''
    
    return line


def main():
    print("🔧 Comprehensive F401 violations fix...")
    
    violations = get_f401_violations()
    print(f"Found {len(violations)} F401 violations")
    
    if not violations:
        print("No F401 violations to fix")
        return 0
    
    # Categorize violations
    availability_checks = []
    unused_imports = []
    
    for violation in violations:
        file_path, line_number, import_name, is_availability_check = violation
        if is_availability_check:
            availability_checks.append(violation)
        else:
            unused_imports.append(violation)
    
    print(f"  - Availability checks: {len(availability_checks)}")
    print(f"  - Genuine unused imports: {len(unused_imports)}")
    
    fixed_count = 0
    skipped_count = 0
    
    # Fix unused imports first (safer)
    for file_path, line_number, import_name, _ in unused_imports:
        success, message = fix_f401_violation(file_path, line_number, import_name, False)
        if success:
            print(f"✅ Fixed {file_path}:{line_number} - {message}")
            fixed_count += 1
        else:
            print(f"⚠️ Skipped {file_path}:{line_number} - {message}")
            skipped_count += 1
    
    # Handle availability checks more carefully
    for file_path, line_number, import_name, _ in availability_checks:
        success, message = fix_f401_violation(file_path, line_number, import_name, True)
        if success:
            print(f"✅ Fixed {file_path}:{line_number} - {message}")
            fixed_count += 1
        else:
            print(f"⚠️ Skipped {file_path}:{line_number} - {message}")
            skipped_count += 1
    
    print(f"\n🎯 Summary: Fixed {fixed_count} F401 violations, skipped {skipped_count}")
    
    # Check remaining violations
    remaining = get_f401_violations()
    print(f"📊 Remaining F401 violations: {len(remaining)}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
