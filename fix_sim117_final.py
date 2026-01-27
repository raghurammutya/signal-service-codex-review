#!/usr/bin/env python3
"""
Final SIM117 Violation Fixer

This script fixes the remaining 6 SIM117 violations with precise edits.
"""

import re


def fix_remaining_sdk_violations():
    """Fix the remaining SDK signal listing violations"""
    file_path = "tests/test_sdk_signal_listing.py"

    with open(file_path) as f:
        content = f.read()

    # Fix the remaining nested with statements that weren't caught by previous regex

    # Pattern 1: Clean up any remaining auth + marketplace patterns
    content = re.sub(
        r"(\s+)with patch\('app\.core\.auth\.get_current_user_from_gateway', return_value=\{\"user_id\": \"user-123\"\}\):\s*\n\s+with patch\('app\.services\.marketplace_client\.MarketplaceClient\.get_user_subscriptions',([^:]+)\):",
        r"\1with (\n\1    patch('app.core.auth.get_current_user_from_gateway', return_value={\"user_id\": \"user-123\"}),\n\1    patch('app.services.marketplace_client.MarketplaceClient.get_user_subscriptions',\2)\n\1):",
        content,
        flags=re.MULTILINE | re.DOTALL
    )

    # Pattern 2: Auth + personal script service
    content = re.sub(
        r"(\s+)with patch\('app\.core\.auth\.get_current_user_from_gateway', return_value=\{\"user_id\": \"user-123\"\}\):\s*\n\s+with patch\('algo_engine\.app\.services\.personal_script_service\.PersonalScriptService\.list_scripts',([^:]+)\):",
        r"\1with (\n\1    patch('app.core.auth.get_current_user_from_gateway', return_value={\"user_id\": \"user-123\"}),\n\1    patch('algo_engine.app.services.personal_script_service.PersonalScriptService.list_scripts',\2)\n\1):",
        content,
        flags=re.MULTILINE | re.DOTALL
    )

    # Pattern 3: Auth + verify_execution_token (multiline)
    content = re.sub(
        r"(\s+)with patch\('app\.core\.auth\.get_current_user_from_gateway', return_value=\{\"user_id\": \"user-123\"\}\):\s*\n\s+with patch\('app\.services\.marketplace_client\.MarketplaceClient\.verify_execution_token',\s*\n\s+return_value=\{\s*\n([^}]+)\}\):",
        r"\1with (\n\1    patch('app.core.auth.get_current_user_from_gateway', return_value={\"user_id\": \"user-123\"}),\n\1    patch('app.services.marketplace_client.MarketplaceClient.verify_execution_token', return_value={\n\2})\n\1):",
        content,
        flags=re.MULTILINE | re.DOTALL
    )

    # Pattern 4: Simple verify_execution_token
    content = re.sub(
        r"(\s+)with patch\('app\.core\.auth\.get_current_user_from_gateway', return_value=\{\"user_id\": \"user-123\"\}\):\s*\n\s+with patch\('app\.services\.marketplace_client\.MarketplaceClient\.verify_execution_token',\s*\n\s+return_value=\{\"is_valid\": False\}\):",
        r"\1with (\n\1    patch('app.core.auth.get_current_user_from_gateway', return_value={\"user_id\": \"user-123\"}),\n\1    patch('app.services.marketplace_client.MarketplaceClient.verify_execution_token', return_value={\"is_valid\": False})\n\1):",
        content,
        flags=re.MULTILINE | re.DOTALL
    )

    with open(file_path, 'w') as f:
        f.write(content)

    print(f"Fixed {file_path}")

def fix_signal_execution_violation():
    """Fix the signal execution test violation"""
    file_path = "tests/test_signal_execution.py"

    with open(file_path) as f:
        content = f.read()

    # Fix the patch.object nested with pattern
    content = re.sub(
        r"(\s+)with patch\.object\(\s*\n\s+SignalExecutor,\s*\n\s+'fetch_marketplace_script',\s*\n\s+return_value=\{\s*\n([^}]+)\}\s*\n\s+\):\s*\n\s+# Mock Redis publish\s*\n\s+with patch\.object\(SignalExecutor, 'publish_to_redis', return_value=True\):",
        r"\1with (\n\1    patch.object(\n\1        SignalExecutor,\n\1        'fetch_marketplace_script',\n\1        return_value={\n\2}\n\1    ),\n\1    patch.object(SignalExecutor, 'publish_to_redis', return_value=True)\n\1):",
        content,
        flags=re.MULTILINE | re.DOTALL
    )

    with open(file_path, 'w') as f:
        f.write(content)

    print(f"Fixed {file_path}")

def clean_up_formatting():
    """Clean up any formatting issues in the fixed files"""
    files_to_clean = [
        "tests/unit/test_optional_dependencies_computation_errors.py",
        "tests/test_signal_version_policy.py"
    ]

    for file_path in files_to_clean:
        with open(file_path) as f:
            content = f.read()

        # Remove extra blank lines in with statements
        content = re.sub(r'with \(\s*\n\s*\n\s*', 'with (\n    ', content)
        content = re.sub(r',\s*\n\s*\n\s*', ',\n    ', content)
        content = re.sub(r'\n\s*\n\s*\):', '\n):', content)

        with open(file_path, 'w') as f:
            f.write(content)

        print(f"Cleaned up {file_path}")

def main():
    """Run the final fixes"""
    print("Applying final SIM117 fixes...")

    fix_remaining_sdk_violations()
    fix_signal_execution_violation()
    clean_up_formatting()

    print("All fixes applied!")

if __name__ == "__main__":
    main()
