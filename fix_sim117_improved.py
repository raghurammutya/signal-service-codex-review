#!/usr/bin/env python3
"""
Fix SIM117 violations - combine nested with statements
Improved version with better pattern matching and indentation handling
"""

import subprocess
import sys


def get_sim117_violations():
    """Get SIM117 violations from ruff."""
    result = subprocess.run(
        ['ruff', 'check', '.', '--select', 'SIM117'],
        capture_output=True, text=True
    )
    
    violations = []
    lines = result.stdout.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() and ':' in line and 'SIM117' in line:
            parts = line.split(':')
            if len(parts) >= 3:
                file_path = parts[0]
                line_number = int(parts[1])
                violations.append((file_path, line_number))
        i += 1
    
    return violations


def fix_sim117_violation(file_path, line_number):
    """Fix a specific SIM117 violation by combining with statements."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if line_number > len(lines):
            return False
        
        # Find the outer with statement
        outer_with_line_idx = line_number - 1
        outer_line = lines[outer_with_line_idx].rstrip()
        
        # Check if this is actually a with statement
        if 'with ' not in outer_line:
            return False
        
        # Get the indentation of the outer with statement
        outer_indent = len(outer_line) - len(outer_line.lstrip())
        
        # Look for the nested with statement
        nested_with_line_idx = None
        for i in range(outer_with_line_idx + 1, min(len(lines), outer_with_line_idx + 10)):
            line = lines[i].rstrip()
            if line.strip():
                line_indent = len(line) - len(line.lstrip())
                if 'with ' in line and line_indent > outer_indent:
                    nested_with_line_idx = i
                    break
                elif line_indent <= outer_indent and line.strip() and not line.strip().startswith('#'):
                    # Found code at same or lower indent level, no nested with found
                    break
        
        if nested_with_line_idx is None:
            return False
        
        nested_line = lines[nested_with_line_idx].rstrip()
        nested_indent = len(nested_line) - len(nested_line.lstrip())
        
        # Extract the with contexts
        outer_context = outer_line.strip()
        nested_context = nested_line.strip()
        
        # Remove 'with ' from both
        outer_context = outer_context[4:].rstrip(':').rstrip()
        nested_context = nested_context[4:].rstrip(':').rstrip()
        
        # Combine them
        combined_context = f"{outer_context}, {nested_context}"
        
        # Create the new combined with statement
        new_with_line = ' ' * outer_indent + f"with {combined_context}:\n"
        
        # Find the end of the nested with block to determine what to keep
        nested_block_end = nested_with_line_idx + 1
        for i in range(nested_with_line_idx + 1, len(lines)):
            line = lines[i].rstrip()
            if line.strip():
                line_indent = len(line) - len(line.lstrip())
                if line_indent <= nested_indent:
                    nested_block_end = i
                    break
            else:
                # Empty lines continue the block
                continue
        else:
            # Block goes to end of file
            nested_block_end = len(lines)
        
        # Adjust indentation of the nested block content
        adjusted_lines = []
        
        # Add lines before the outer with
        adjusted_lines.extend(lines[:outer_with_line_idx])
        
        # Add the combined with statement
        adjusted_lines.append(new_with_line)
        
        # Add the content of the nested block with adjusted indentation
        indent_reduction = nested_indent - outer_indent
        for i in range(nested_with_line_idx + 1, nested_block_end):
            line = lines[i]
            if line.strip():
                # Reduce indentation
                current_indent = len(line) - len(line.lstrip())
                new_indent = max(0, current_indent - indent_reduction)
                adjusted_lines.append(' ' * new_indent + line.lstrip())
            else:
                adjusted_lines.append(line)
        
        # Add remaining lines
        adjusted_lines.extend(lines[nested_block_end:])
        
        # Write back the modified content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(adjusted_lines)
        
        return True
        
    except Exception as e:
        print(f"Error fixing {file_path}:{line_number} - {e}")
        return False


def main():
    print("Fixing SIM117 violations (nested with statements)...")
    
    violations = get_sim117_violations()
    print(f"Found {len(violations)} SIM117 violations")
    
    if not violations:
        print("No SIM117 violations to fix")
        return 0
    
    fixed_count = 0
    
    # Sort violations by line number (highest first) to avoid line number shifts
    violations.sort(key=lambda x: x[1], reverse=True)
    
    for file_path, line_number in violations:
        result = fix_sim117_violation(file_path, line_number)
        if result:
            print(f"✅ Fixed {file_path}:{line_number} - combined nested with statements")
            fixed_count += 1
        else:
            print(f"⚠️ Could not fix {file_path}:{line_number}")
    
    print(f"\n🎯 Summary: Fixed {fixed_count} SIM117 violations")
    
    # Check remaining violations
    remaining = get_sim117_violations()
    print(f"📊 Remaining SIM117 violations: {len(remaining)}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
