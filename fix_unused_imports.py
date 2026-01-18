#!/usr/bin/env python3
"""
Fix Unused Imports

Automatically removes obvious unused imports to clean up codebase.
"""
import os
import re
import ast
from typing import Set, List, Dict


class UnusedImportFixer:
    """Fixes unused imports in Python files."""
    
    def __init__(self):
        self.fixed_files = []
        self.safety_patterns = [
            # Don't remove these common imports that might be used implicitly
            "logging", "logger", "log", "traceback", 
            "pytest", "mock", "unittest",
            "asyncio", "await", "async",
            "__all__", "__version__"
        ]
    
    def is_import_used(self, import_name: str, content: str, lines: List[str]) -> bool:
        """Check if an import is actually used in the file."""
        
        # Safety check - don't remove certain imports
        if any(pattern in import_name.lower() for pattern in self.safety_patterns):
            return True
        
        # Remove the import line(s) from content for checking
        content_without_imports = []
        for line in lines:
            if not (line.strip().startswith('import ') or line.strip().startswith('from ')):
                content_without_imports.append(line)
        
        check_content = '\n'.join(content_without_imports)
        
        # Check if the imported name appears in the code
        patterns_to_check = [
            rf'\b{re.escape(import_name)}\b',  # Direct usage
            rf'{re.escape(import_name)}\.',    # Method/attribute access
            rf'{re.escape(import_name)}\(',    # Function call
        ]
        
        for pattern in patterns_to_check:
            if re.search(pattern, check_content):
                return True
        
        return False
    
    def fix_file_imports(self, file_path: str) -> bool:
        """Fix unused imports in a single file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            original_content = ''.join(lines)
            new_lines = []
            imports_removed = []
            
            for i, line in enumerate(lines):
                stripped = line.strip()
                
                # Handle simple import statements
                if stripped.startswith('import ') and ' as ' not in stripped:
                    # Extract import name: "import module" -> "module"
                    import_match = re.match(r'import\s+([a-zA-Z_][a-zA-Z0-9_]*)', stripped)
                    if import_match:
                        import_name = import_match.group(1)
                        if not self.is_import_used(import_name, original_content, lines):
                            imports_removed.append(f"import {import_name}")
                            continue  # Skip this line
                
                # Handle from imports (be more conservative)
                elif stripped.startswith('from ') and ' import ' in stripped:
                    # Only remove very obvious unused imports
                    from_match = re.match(r'from\s+[\w.]+\s+import\s+([a-zA-Z_][a-zA-Z0-9_]*)', stripped)
                    if from_match:
                        import_name = from_match.group(1)
                        # Be more conservative with from imports
                        if len(import_name) > 3 and not self.is_import_used(import_name, original_content, lines):
                            # Double-check it's not used in any way
                            if import_name not in original_content.replace(stripped, ''):
                                imports_removed.append(stripped)
                                continue  # Skip this line
                
                new_lines.append(line)
            
            # Only update file if we removed something significant
            if imports_removed and len(imports_removed) >= 2:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                
                self.fixed_files.append({
                    "file": file_path,
                    "imports_removed": imports_removed
                })
                
                print(f"✅ Fixed {file_path}: removed {len(imports_removed)} imports")
                for imp in imports_removed[:3]:  # Show first 3
                    print(f"   - {imp}")
                if len(imports_removed) > 3:
                    print(f"   ... and {len(imports_removed) - 3} more")
                
                return True
            
            return False
            
        except Exception as e:
            print(f"❌ Error fixing {file_path}: {e}")
            return False
    
    def fix_unused_imports(self, max_files: int = 10):
        """Fix unused imports in the most problematic files."""
        print("🧹 Fixing Unused Imports...")
        
        # Target the files with the most unused imports first
        priority_files = [
            "app/services/signal_processing_indicators.py",
            "app/services/external_function_executor.py", 
            "app/services/moneyness_historical_processor.py",
            "app/services/flexible_timeframe_manager.py",
            "app/services/premium_discount_calculator.py",
            "app/services/universal_calculator.py",
            "app/services/pattern_indicators.py",
            "app/services/clustering_indicators.py",
            "app/services/computation_registry.py",
            "app/services/trendline_indicators.py"
        ]
        
        fixed_count = 0
        for file_path in priority_files:
            if fixed_count >= max_files:
                break
                
            if os.path.exists(file_path):
                if self.fix_file_imports(file_path):
                    fixed_count += 1
        
        print(f"\n📊 Import cleanup: {fixed_count} files fixed")
        return fixed_count


def main():
    """Run unused import fixing."""
    fixer = UnusedImportFixer()
    result = fixer.fix_unused_imports(max_files=8)
    
    if result > 0:
        print(f"\n🎉 Successfully cleaned up imports in {result} files")
        return 0
    else:
        print(f"\n⚠️ No significant import cleanup performed")
        return 1


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)