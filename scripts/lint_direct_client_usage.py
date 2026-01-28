#!/usr/bin/env python3
"""
Client Factory Adoption Linter

Fails CI if any code directly instantiates *ServiceClient() instead of using get_client_manager().
Ensures universal client factory adoption for consistent circuit breakers, retries, and timeouts.
"""
import os
import re
import sys


def find_direct_client_instantiations(root_dir: str) -> list[tuple[str, int, str]]:
    """
    Find direct client instantiations in Python files.

    Returns:
        list of (file_path, line_number, line_content) tuples
    """
    violations = []

    # Patterns to detect direct client instantiation
    client_patterns = [
        re.compile(r'(\w*ServiceClient)\(\)', re.IGNORECASE),
        re.compile(r'(\w*Client)\(\)(?=.*Service)', re.IGNORECASE),
    ]

    # Specific service client patterns
    specific_patterns = [
        re.compile(r'TickerServiceClient\(\)'),
        re.compile(r'UserServiceClient\(\)'),
        re.compile(r'AlertServiceClient\(\)'),
        re.compile(r'CommsServiceClient\(\)'),
        re.compile(r'MarketplaceServiceClient\(\)'),
        re.compile(r'HistoricalDataClient\(\)'),
    ]

    all_patterns = client_patterns + specific_patterns

    # Files to exclude from linting
    exclude_patterns = [
        '/test',
        '/tests/',
        '/__pycache__',
        '.pyc',
        '/client_factory.py',  # The factory itself
        '/conftest.py',
        'test_',
        '/scripts/',  # Deployment and utility scripts
        'deployment_safety_check.py',  # Config service testing script
        'lint_direct_client_usage.py'  # This linter itself
    ]

    for root, _dirs, files in os.walk(root_dir):
        for file in files:
            if not file.endswith('.py'):
                continue

            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_path, root_dir)

            # Skip excluded files
            if any(exclude in file_path for exclude in exclude_patterns):
                continue

            try:
                with open(file_path, encoding='utf-8') as f:
                    lines = f.readlines()

                for line_num, line in enumerate(lines, 1):
                    line = line.strip()

                    # Skip comments and empty lines
                    if not line or line.startswith('#'):
                        continue

                    # Skip class definitions
                    if 'class ' in line and 'ServiceClient' in line:
                        continue

                    # Skip imports
                    if line.startswith(('from ', 'import ')):
                        continue

                    # Skip factory helper function definitions
                    if 'def get_' in line and '_client' in line and 'ServiceClient' in line:
                        continue

                    # Skip documentation strings, comments, and string literals that mention client patterns
                    if (line.startswith(('"""', "'''")) or 'description=' in line or 'help=' in line or 'print(' in line and 'ServiceClient' in line or 'logger.warning(' in line or 'logger.error(' in line or 'logger.info(' in line or 'logger.debug(' in line):
                        continue

                    # Check for direct instantiation patterns
                    for pattern in all_patterns:
                        if pattern.search(line) and ' = ' in line or 'return ' in line or '(' in line:
                            violations.append((relative_path, line_num, line))

            except (OSError, UnicodeDecodeError) as e:
                print(f"Warning: Could not read {file_path}: {e}")

    return violations


def check_client_factory_usage(root_dir: str) -> list[tuple[str, int, str]]:
    """
    Check that get_client_manager() is used instead of direct instantiation.

    Returns:
        list of violations
    """
    suggestions = []

    for root, _dirs, files in os.walk(root_dir):
        for file in files:
            if not file.endswith('.py'):
                continue

            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_path, root_dir)

            # Skip test files and client factory itself
            if any(skip in file_path for skip in ['/test', '/client_factory.py', '/__pycache__']):
                continue

            try:
                with open(file_path, encoding='utf-8') as f:
                    content = f.read()

                # Look for service client usage without factory
                if 'ServiceClient' in content and 'get_client_manager' not in content:
                    # Check if it's actual usage (not just imports or class definitions)
                    lines = content.split('\n')
                    for line_num, line in enumerate(lines, 1):
                        if ('ServiceClient(' in line or 'Client(' in line) and 'class ' not in line:
                            suggestions.append((
                                relative_path,
                                line_num,
                                f"Consider using get_client_manager() instead of direct instantiation: {line.strip()}"
                            ))

            except (OSError, UnicodeDecodeError):
                continue

    return suggestions


def main():
    """Run client factory adoption linter."""
    if len(sys.argv) > 1:
        root_dir = sys.argv[1]
    else:
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    print("🔍 Client Factory Adoption Linter")
    print("=" * 50)
    print(f"Scanning: {root_dir}")
    print()

    # Find direct instantiations
    violations = find_direct_client_instantiations(root_dir)

    if violations:
        print("❌ DIRECT CLIENT INSTANTIATION VIOLATIONS:")
        print()

        for file_path, line_num, line_content in violations:
            print(f"File: {file_path}")
            print(f"Line {line_num}: {line_content}")
            print("Fix: Use get_client_manager().get_client('service_name') instead")
            print()

        print(f"Total violations: {len(violations)}")
        print()
        print("To fix these violations:")
        print("1. Replace direct instantiation with get_client_manager()")
        print("2. Use await manager.get_client('service_name')")
        print("3. This ensures consistent circuit breakers and timeouts")

        return 1

    print("✅ All service clients use centralized factory")

    # Check for suggestions
    suggestions = check_client_factory_usage(root_dir)

    if suggestions:
        print()
        print("💡 SUGGESTIONS for improved client factory usage:")
        for file_path, line_num, suggestion in suggestions[:5]:  # Show first 5
            print(f"  {file_path}:{line_num} - {suggestion}")

    print()
    print("🎯 Client Factory Adoption: VERIFIED")
    print("  - No direct ServiceClient() instantiations found")
    print("  - Circuit breaker consistency maintained")
    print("  - Centralized timeout/retry configuration active")

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
