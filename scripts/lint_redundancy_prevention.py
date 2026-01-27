#!/usr/bin/env python3
"""
Redundancy Prevention Lint Rule

Prevents duplicate historical data services and unused imports.
"""
import os
import re
from typing import List, Tuple


def check_historical_data_duplication() -> list[str]:
    """Check for duplicate historical data services."""
    violations = []

    # Patterns that should only exist in the unified service
    restricted_patterns = [
        (r'class.*HistoricalDataManager', "Multiple HistoricalDataManager classes found"),
        (r'def get_historical_data_for_indicator', "Multiple indicator data fetchers found"),
        (r'async def.*historical.*ticker', "Multiple ticker service integrations found")
    ]

    for root, dirs, files in os.walk("app"):
        for file in files:
            if file.endswith('.py') and file != 'unified_historical_data_service.py':
                file_path = os.path.join(root, file)
                try:
                    with open(file_path) as f:
                        content = f.read()

                    for pattern, message in restricted_patterns:
                        if re.search(pattern, content, re.IGNORECASE):
                            violations.append(f"{file_path}: {message}")
                except:
                    continue

    return violations


def check_unused_imports() -> list[str]:
    """Check for obvious unused imports."""
    violations = []

    # Simple patterns for obviously unused imports
    unused_patterns = [
        r'^import\s+(os|sys|json|re)\s*$',  # Common imports that might be unused
        r'^from\s+typing\s+import.*$'      # Typing imports often become unused
    ]

    for root, dirs, files in os.walk("app"):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path) as f:
                        lines = f.readlines()

                    for i, line in enumerate(lines):
                        for pattern in unused_patterns:
                            if re.match(pattern, line.strip()):
                                # Simple check: if import name doesn't appear later in file
                                import_match = re.search(r'import\s+(\w+)', line)
                                if import_match:
                                    import_name = import_match.group(1)
                                    file_content = ''.join(lines[i+1:])  # Skip the import line itself
                                    if import_name not in file_content:
                                        violations.append(f"{file_path}:{i+1}: Potentially unused import: {line.strip()}")
                except:
                    continue

    return violations


def main():
    """Run redundancy prevention checks."""
    print("🔍 Redundancy Prevention Lint Check")
    print("=" * 50)

    duplication_violations = check_historical_data_duplication()
    unused_import_violations = check_unused_imports()

    total_violations = len(duplication_violations) + len(unused_import_violations)

    if duplication_violations:
        print("❌ Historical Data Duplication Violations:")
        for violation in duplication_violations:
            print(f"  {violation}")
        print()

    if unused_import_violations:
        print("⚠️ Potential Unused Import Violations:")
        for violation in unused_import_violations[:10]:  # Show first 10
            print(f"  {violation}")
        if len(unused_import_violations) > 10:
            print(f"  ... and {len(unused_import_violations) - 10} more")
        print()

    if total_violations == 0:
        print("✅ No redundancy violations found")
        return 0
    print(f"❌ Found {total_violations} violations")
    return 1


if __name__ == "__main__":
    exit(main())
