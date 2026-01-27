#!/usr/bin/env python3
"""
Complete F401 cleanup - convert availability checks and remove unused imports
"""

import subprocess
import sys
import re


def get_f401_violations():
    """Get detailed F401 violations."""
    result = subprocess.run(['ruff', 'check', '.', '--select', 'F401'], capture_output=True, text=True)
    
    violations = []
    lines = result.stdout.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i]
        if ':' in line and 'F401' in line and 'imported but unused' in line:
            parts = line.split(':')
            if len(parts) >= 3:
                try:
                    file_path = parts[0]
                    line_number = int(parts[1])
                    
                    # Extract import name
                    import_match = re.search(r'`([^`]+)` imported but unused', line)
                    if import_match:
                        import_name = import_match.group(1)
                        
                        # Check if it suggests importlib.util.find_spec
                        suggests_importlib = 'consider using `importlib.util.find_spec`' in line
                        
                        # Get context lines
                        context = []
                        for j in range(i+1, min(i+10, len(lines))):
                            if lines[j].strip() and not lines[j].startswith(' '):
                                break
                            context.append(lines[j])
                        
                        violations.append({
                            'file': file_path,
                            'line': line_number,
                            'import': import_name,
                            'suggests_importlib': suggests_importlib,
                            'context': '\n'.join(context)
                        })
                except ValueError:
                    pass
        i += 1
    
    return violations


def analyze_import_context(file_path, line_number):
    """Analyze the context around an import to determine its purpose."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if line_number > len(lines):
            return None, []
        
        context = {
            'is_availability_check': False,
            'is_test_import': False,
            'has_try_except': False,
            'has_assert': False,
            'module_name': None,
            'import_line': lines[line_number - 1].strip()
        }
        
        # Check lines around the import
        start_line = max(0, line_number - 5)
        end_line = min(len(lines), line_number + 10)
        
        context_lines = lines[start_line:end_line]
        context_text = ''.join(context_lines).lower()
        
        # Detect patterns
        context['has_try_except'] = 'try:' in context_text and ('except importerror' in context_text or 'except modulenotfounderror' in context_text)
        context['has_assert'] = 'assert true' in context_text or 'assert false' in context_text
        context['is_test_import'] = 'test that' in context_text or 'check' in context_text
        context['is_availability_check'] = context['has_try_except'] and ('available' in context_text or 'import' in context_text)
        
        # Extract module name
        import_line = lines[line_number - 1]
        if 'from ' in import_line and 'import ' in import_line:
            module_match = re.search(r'from\s+([^\s]+)\s+import', import_line)
            if module_match:
                context['module_name'] = module_match.group(1)
        elif 'import ' in import_line:
            module_match = re.search(r'import\s+([^\s]+)', import_line)
            if module_match:
                context['module_name'] = module_match.group(1).split(' as ')[0]
        
        return context, context_lines
        
    except Exception as e:
        print(f"Error analyzing {file_path}:{line_number}: {e}")
        return None, []


def convert_availability_check_to_importlib(file_path, line_number, import_name, module_name):
    """Convert try/except import pattern to importlib.util.find_spec."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Find the try/except block
        try_line = None
        except_line = None
        
        # Look backwards and forwards for try/except
        for i in range(max(0, line_number - 10), min(len(lines), line_number + 10)):
            line = lines[i].strip().lower()
            if line.startswith('try:'):
                try_line = i
            elif 'except importerror' in line or 'except modulenotfounderror' in line:
                except_line = i
        
        if try_line is not None and except_line is not None:
            # Replace the pattern
            indent = ' ' * (len(lines[line_number - 1]) - len(lines[line_number - 1].lstrip()))
            
            # Create importlib.util.find_spec check
            if module_name:
                new_lines = []
                
                # Add importlib import if not present
                has_importlib = any('import importlib.util' in line for line in lines[:try_line])
                if not has_importlib:
                    new_lines.append(f"{indent}import importlib.util\n")
                
                # Replace try/except block with find_spec check
                new_lines.append(f"{indent}if importlib.util.find_spec('{module_name}'):\n")
                
                # Add the content from try block (usually just assert True or setting a flag)
                for i in range(try_line + 1, except_line):
                    if 'from ' in lines[i] or 'import ' in lines[i]:
                        continue  # Skip the import line
                    new_lines.append(lines[i])
                
                # Add else block for the except case
                new_lines.append(f"{indent}else:\n")
                for i in range(except_line + 1, len(lines)):
                    if lines[i].strip() and len(lines[i]) - len(lines[i].lstrip()) <= len(indent):
                        break  # End of except block
                    new_lines.append(lines[i])
                
                # Replace the entire try/except block
                new_content = lines[:try_line] + new_lines
                
                # Add remaining lines after except block
                after_except = except_line + 1
                while after_except < len(lines) and (not lines[after_except].strip() or len(lines[after_except]) - len(lines[after_except].lstrip()) > len(indent)):
                    after_except += 1
                
                new_content.extend(lines[after_except:])
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_content)
                
                return True, "Converted to importlib.util.find_spec"
        
        return False, "Could not locate try/except pattern"
        
    except Exception as e:
        return False, f"Conversion failed: {e}"


def remove_unused_import(file_path, line_number, import_name):
    """Remove a genuinely unused import."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if line_number > len(lines):
            return False, "Line out of range"
        
        target_line = lines[line_number - 1]
        
        # Simple case: single import line
        if target_line.strip().startswith(('import ', 'from ')) and ',' not in target_line:
            lines.pop(line_number - 1)
        else:
            # Multi-import line - remove just this import
            new_line = remove_import_from_multi_import(target_line, import_name)
            if new_line and new_line.strip():
                lines[line_number - 1] = new_line
            else:
                lines.pop(line_number - 1)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        return True, "Removed unused import"
        
    except Exception as e:
        return False, f"Removal failed: {e}"


def remove_import_from_multi_import(line, import_name):
    """Remove specific import from a line with multiple imports."""
    if 'from ' in line and 'import ' in line:
        # Handle "from module import a, b, c"
        parts = line.split('import ', 1)
        if len(parts) == 2:
            prefix = parts[0] + 'import '
            imports = [imp.strip() for imp in parts[1].split(',')]
            
            # Remove imports containing the target name
            filtered_imports = [imp for imp in imports if import_name.split('.')[-1] not in imp]
            
            if filtered_imports:
                return prefix + ', '.join(filtered_imports) + '\n'
            else:
                return ''
    
    return line


def main():
    print("🔧 Complete F401 cleanup - converting availability checks and removing unused imports...")
    
    violations = get_f401_violations()
    print(f"Found {len(violations)} F401 violations")
    
    if not violations:
        print("No F401 violations found!")
        return 0
    
    converted_count = 0
    removed_count = 0
    skipped_count = 0
    
    for violation in violations:
        file_path = violation['file']
        line_number = violation['line']
        import_name = violation['import']
        suggests_importlib = violation['suggests_importlib']
        
        print(f"\nProcessing {file_path}:{line_number} - {import_name}")
        
        # Analyze context
        context, context_lines = analyze_import_context(file_path, line_number)
        
        if not context:
            print(f"  ⚠️ Could not analyze context")
            skipped_count += 1
            continue
        
        # Decide action based on context
        if context['is_availability_check'] and suggests_importlib:
            # Convert availability check to importlib.util.find_spec
            success, message = convert_availability_check_to_importlib(
                file_path, line_number, import_name, context['module_name']
            )
            if success:
                print(f"  ✅ Converted: {message}")
                converted_count += 1
            else:
                print(f"  ⚠️ Conversion failed: {message}")
                skipped_count += 1
        
        elif not context['is_availability_check'] and not context['is_test_import']:
            # Remove genuinely unused import
            success, message = remove_unused_import(file_path, line_number, import_name)
            if success:
                print(f"  ✅ Removed: {message}")
                removed_count += 1
            else:
                print(f"  ⚠️ Removal failed: {message}")
                skipped_count += 1
        
        else:
            print(f"  ⚠️ Preserved: {'Test import' if context['is_test_import'] else 'Availability check'}")
            skipped_count += 1
    
    print(f"\n🎯 Summary:")
    print(f"  - Converted to importlib: {converted_count}")
    print(f"  - Removed unused imports: {removed_count}")
    print(f"  - Preserved/skipped: {skipped_count}")
    
    # Check remaining violations
    remaining = get_f401_violations()
    print(f"📊 Remaining F401 violations: {len(remaining)}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())