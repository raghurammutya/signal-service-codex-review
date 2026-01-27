#!/usr/bin/env python3
"""
Fix SIM102 violations - collapsible if statements
Enhanced version with better pattern recognition
"""

import subprocess
import sys


def get_sim102_violations():
    """Get SIM102 violations from ruff."""
    result = subprocess.run(
        ['ruff', 'check', '.', '--select', 'SIM102'],
        capture_output=True, text=True
    )
    
    violations = []
    lines = result.stdout.split('\n')
    
    for line in lines:
        if line.strip() and ':' in line and 'SIM102' in line:
            parts = line.split(':')
            if len(parts) >= 3:
                file_path = parts[0]
                line_number = int(parts[1])
                violations.append((file_path, line_number))
    
    return violations


def fix_sim102_violation(file_path, line_number):
    """Fix a specific SIM102 violation by combining if statements."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if line_number > len(lines):
            return False
        
        # Find the outer if statement
        outer_if_idx = line_number - 1
        outer_line = lines[outer_if_idx].rstrip()
        
        # Check if this is actually an if statement
        if 'if ' not in outer_line:
            return False
        
        # Get the indentation of the outer if statement
        outer_indent = len(outer_line) - len(outer_line.lstrip())
        
        # Look for the nested if statement (should be the next non-empty non-comment line)
        nested_if_idx = None
        for i in range(outer_if_idx + 1, min(len(lines), outer_if_idx + 5)):
            line = lines[i].rstrip()
            if line.strip() and not line.strip().startswith('#'):
                line_indent = len(line) - len(line.lstrip())
                if 'if ' in line and line_indent > outer_indent:
                    nested_if_idx = i
                    break
                elif line_indent <= outer_indent:
                    # Found code at same or lower indent, no nested if
                    break
        
        if nested_if_idx is None:
            return False
        
        nested_line = lines[nested_if_idx].rstrip()
        
        # Extract conditions from both if statements
        outer_condition = outer_line.strip()
        nested_condition = nested_line.strip()
        
        # Remove 'if ' and trailing ':'
        outer_condition = outer_condition[2:].rstrip(':').strip()
        nested_condition = nested_condition[2:].rstrip(':').strip()
        
        # Combine conditions with 'and'
        combined_condition = f"if {outer_condition} and {nested_condition}:"
        
        # Create the new combined if statement
        new_if_line = ' ' * outer_indent + combined_condition + '\n'
        
        # Find the end of the nested if block
        nested_indent = len(nested_line) - len(nested_line.lstrip())
        nested_block_start = nested_if_idx + 1
        nested_block_end = nested_block_start
        
        # Find where the nested block ends
        for i in range(nested_block_start, len(lines)):
            line = lines[i].rstrip()
            if line.strip():
                line_indent = len(line) - len(line.lstrip())
                if line_indent <= nested_indent:
                    nested_block_end = i
                    break
            # Empty lines continue the block
        else:
            # Block goes to end of file
            nested_block_end = len(lines)
        
        # Build the new file content
        new_lines = []
        
        # Add lines before the outer if
        new_lines.extend(lines[:outer_if_idx])
        
        # Add the combined if statement
        new_lines.append(new_if_line)
        
        # Add the content of the nested block with reduced indentation
        content_indent = nested_indent + 4  # Expected indent for content inside nested if
        new_content_indent = outer_indent + 4  # New indent for content
        
        for i in range(nested_block_start, nested_block_end):
            line = lines[i]
            if line.strip():
                # Adjust indentation
                current_indent = len(line) - len(line.lstrip())
                if current_indent >= content_indent:
                    # This is content inside the nested if block
                    indent_reduction = content_indent - new_content_indent
                    new_indent = max(0, current_indent - indent_reduction)
                    new_lines.append(' ' * new_indent + line.lstrip())
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        
        # Add remaining lines
        new_lines.extend(lines[nested_block_end:])
        
        # Write back the modified content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        
        return True
        
    except Exception as e:
        print(f"Error fixing {file_path}:{line_number} - {e}")
        return False


def main():
    print("Fixing SIM102 violations (collapsible if statements)...")
    
    violations = get_sim102_violations()
    print(f"Found {len(violations)} SIM102 violations")
    
    if not violations:
        print("No SIM102 violations to fix")
        return 0
    
    fixed_count = 0
    
    # Sort violations by line number (highest first) to avoid line number shifts
    violations.sort(key=lambda x: (x[0], x[1]), reverse=True)
    
    for file_path, line_number in violations:
        result = fix_sim102_violation(file_path, line_number)
        if result:
            print(f"✅ Fixed {file_path}:{line_number} - combined nested if statements")
            fixed_count += 1
        else:
            print(f"⚠️ Could not fix {file_path}:{line_number}")
    
    print(f"\n🎯 Summary: Fixed {fixed_count} SIM102 violations")
    
    # Check remaining violations
    remaining = get_sim102_violations()
    print(f"📊 Remaining SIM102 violations: {len(remaining)}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
