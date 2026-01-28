#!/usr/bin/env python3
"""
Surgical SIM117 Violation Fixer

This script applies targeted, precise fixes for each SIM117 violation
using line-by-line analysis and exact replacements.
"""

import logging
import re
import subprocess

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_integration_test():
    """Fix tests/integration/test_service_integrations.py"""
    file_path = "tests/integration/test_service_integrations.py"

    with open(file_path) as f:
        lines = f.readlines()

    # Find and fix the aiohttp nested with pattern
    for i, line in enumerate(lines):
        if "async with aiohttp.ClientSession() as session:" in line:
            # Check if next non-comment line has session.get
            j = i + 1
            while j < len(lines) and (lines[j].strip() == '' or lines[j].strip().startswith('#')):
                j += 1

            if j < len(lines) and "async with session.get(" in lines[j]:
                # Found the pattern, merge them
                indent = line[:len(line) - len(line.lstrip())]

                # Find the end of the session.get call
                end_line = j
                while end_line < len(lines) and ') as response:' not in lines[end_line]:
                    end_line += 1

                if end_line < len(lines):
                    # Extract the session.get parameters
                    get_params = []
                    for k in range(j, end_line + 1):
                        param_line = lines[k].strip()
                        if param_line.startswith('async with session.get('):
                            param_line = param_line.replace('async with session.get(', '').strip()
                        elif param_line.endswith(') as response:'):
                            param_line = param_line.replace(') as response:', '').strip()

                        if param_line:
                            get_params.append(param_line)

                    # Create merged with statement
                    new_lines = [
                        f"{indent}async with (\n",
                        f"{indent}    aiohttp.ClientSession() as session,\n",
                        f"{indent}    session.get(\n"
                    ]

                    for param in get_params:
                        if param.rstrip(','):
                            new_lines.append(f"{indent}        {param}\n")

                    new_lines.extend([
                        f"{indent}    ) as response\n",
                        f"{indent}):\n"
                    ])

                    # Replace the lines
                    lines[i:end_line + 1] = new_lines
                    break

    # Find and fix patch.dict pattern
    for i, line in enumerate(lines):
        if "with patch.dict(os.environ, {" in line:
            # Look for nested patch in next lines
            for j in range(i + 1, min(i + 6, len(lines))):
                if "with patch('app.core.hot_config.BaseSignalServiceConfig.__init__')" in lines[j]:
                    indent = line[:len(line) - len(line.lstrip())]

                    # Replace with merged version
                    new_lines = [
                        f"{indent}with (\n",
                        f"{indent}    patch.dict(os.environ, {{\n",
                        f"{indent}        'USE_EXTERNAL_CONFIG': 'true',\n",
                        f"{indent}        'ENVIRONMENT': 'dev'\n",
                        f"{indent}    }}),\n",
                        f"{indent}    patch('app.core.hot_config.BaseSignalServiceConfig.__init__') as mock_base_init\n",
                        f"{indent}):\n"
                    ]

                    # Find the end of the original structure
                    end_idx = j
                    while end_idx < len(lines) and not lines[end_idx].strip().endswith(':'):
                        end_idx += 1

                    lines[i:end_idx + 1] = new_lines
                    break

    with open(file_path, 'w') as f:
        f.writelines(lines)

    logger.info(f"Fixed {file_path}")

def fix_sdk_signal_listing():
    """Fix tests/test_sdk_signal_listing.py"""
    file_path = "tests/test_sdk_signal_listing.py"

    with open(file_path) as f:
        content = f.read()

    # Pattern 1: Two nested patches
    pattern1 = r"(\s+)with patch\('app\.core\.auth\.get_current_user_from_gateway', return_value=\{\"user_id\": \"user-123\"\}\):\s*\n\s+with patch\('app\.services\.marketplace_client\.MarketplaceClient\.get_user_subscriptions',\s*\n\s+return_value=([^)]+)\):"

    replacement1 = r"\1with (\n\1    patch('app.core.auth.get_current_user_from_gateway', return_value={\"user_id\": \"user-123\"}),\n\1    patch('app.services.marketplace_client.MarketplaceClient.get_user_subscriptions', return_value=\2)\n\1):"

    content = re.sub(pattern1, replacement1, content, flags=re.MULTILINE | re.DOTALL)

    # Pattern 2: Three nested patches
    pattern2 = r"(\s+)with patch\('app\.core\.auth\.get_current_user_from_gateway', return_value=\{\"user_id\": \"user-123\"\}\):\s*\n\s+with patch\('app\.services\.marketplace_client\.MarketplaceClient\.get_user_subscriptions',\s*\n\s+return_value=([^)]+)\):\s*\n\s+with patch\('algo_engine\.app\.services\.personal_script_service\.PersonalScriptService\.list_scripts',\s*\n\s+return_value=([^)]+)\):"

    replacement2 = r"\1with (\n\1    patch('app.core.auth.get_current_user_from_gateway', return_value={\"user_id\": \"user-123\"}),\n\1    patch('app.services.marketplace_client.MarketplaceClient.get_user_subscriptions', return_value=\2),\n\1    patch('algo_engine.app.services.personal_script_service.PersonalScriptService.list_scripts', return_value=\3)\n\1):"

    content = re.sub(pattern2, replacement2, content, flags=re.MULTILINE | re.DOTALL)

    # Pattern 3: verify_execution_token
    pattern3 = r"(\s+)with patch\('app\.core\.auth\.get_current_user_from_gateway', return_value=\{\"user_id\": \"user-123\"\}\):\s*\n\s+with patch\('app\.services\.marketplace_client\.MarketplaceClient\.verify_execution_token',([^:]+)\):"

    replacement3 = r"\1with (\n\1    patch('app.core.auth.get_current_user_from_gateway', return_value={\"user_id\": \"user-123\"}),\n\1    patch('app.services.marketplace_client.MarketplaceClient.verify_execution_token',\2)\n\1):"

    content = re.sub(pattern3, replacement3, content, flags=re.MULTILINE | re.DOTALL)

    with open(file_path, 'w') as f:
        f.write(content)

    logger.info(f"Fixed {file_path}")

def fix_signal_version_policy():
    """Fix tests/test_signal_version_policy.py"""
    file_path = "tests/test_signal_version_policy.py"

    with open(file_path) as f:
        content = f.read()

    # Fix nested patch patterns
    pattern = r"(\s+)with patch\('app\.core\.auth\.get_current_user_from_gateway',\s*\n\s+return_value=([^)]+)\):\s*\n\s+with patch\('app\.services\.marketplace_client\.MarketplaceClient\.get_product_definition',\s*\n\s+return_value=([^)]+)\):"

    replacement = r"\1with (\n\1    patch('app.core.auth.get_current_user_from_gateway', return_value=\2),\n\1    patch('app.services.marketplace_client.MarketplaceClient.get_product_definition', return_value=\3)\n\1):"

    content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)

    with open(file_path, 'w') as f:
        f.write(content)

    logger.info(f"Fixed {file_path}")

def fix_signal_execution():
    """Fix tests/test_signal_execution.py"""
    file_path = "tests/test_signal_execution.py"

    with open(file_path) as f:
        content = f.read()

    # Find nested with patch patterns
    pattern = r"(\s+)with patch\([^:]+\):\s*\n\s+with patch\([^:]+\):"

    def fix_match(match):
        indent = match.group(1)
        full_match = match.group(0)
        lines = full_match.strip().split('\n')

        # Extract patch statements
        patch1 = lines[0].replace('with ', '').rstrip(':').strip()
        patch2 = lines[1].strip().replace('with ', '').rstrip(':').strip()

        return f"{indent}with (\n{indent}    {patch1},\n{indent}    {patch2}\n{indent}):"

    content = re.sub(pattern, fix_match, content, flags=re.MULTILINE)

    with open(file_path, 'w') as f:
        f.write(content)

    logger.info(f"Fixed {file_path}")

def fix_optional_dependencies():
    """Fix tests/unit/test_optional_dependencies_computation_errors.py"""
    file_path = "tests/unit/test_optional_dependencies_computation_errors.py"

    with open(file_path) as f:
        content = f.read()

    # Pattern 1: patch.dict + patch for imports
    pattern1 = r"(\s+)with patch\.dict\('sys\.modules', \{([^}]+)\}\):\s*\n\s+with patch\('builtins\.__import__', side_effect=ImportError\(([^)]+)\)\):"

    replacement1 = r"\1with (\n\1    patch.dict('sys.modules', {\2}),\n\1    patch('builtins.__import__', side_effect=ImportError(\3))\n\1):"

    content = re.sub(pattern1, replacement1, content, flags=re.MULTILINE)

    # Pattern 2: Multiple patches in a loop
    pattern2 = r"(\s+)with patch\.dict\('sys\.modules', \{missing_dep: None\}\):\s*\n\s+with patch\('builtins\.__import__', side_effect=ImportError\(f\"\{missing_dep\} not available\"\)\):"

    replacement2 = r"\1with (\n\1    patch.dict('sys.modules', {missing_dep: None}),\n\1    patch('builtins.__import__', side_effect=ImportError(f\"{missing_dep} not available\"))\n\1):"

    content = re.sub(pattern2, replacement2, content, flags=re.MULTILINE)

    # Pattern 3: logging + patches
    pattern3 = r"(\s+)with patch\('app\.utils\.logging_utils\.log_exception'\):\s*\n\s+with patch\.dict\('sys\.modules', \{'findpeaks': None\}\), patch\('builtins\.__import__', side_effect=ImportError\(\"findpeaks not available\"\)\):"

    replacement3 = r"\1with (\n\1    patch('app.utils.logging_utils.log_exception'),\n\1    patch.dict('sys.modules', {'findpeaks': None}),\n\1    patch('builtins.__import__', side_effect=ImportError(\"findpeaks not available\"))\n\1):"

    content = re.sub(pattern3, replacement3, content, flags=re.MULTILINE)

    with open(file_path, 'w') as f:
        f.write(content)

    logger.info(f"Fixed {file_path}")

def main():
    """Run all fixes"""
    logger.info("Starting surgical SIM117 fixes...")

    # Check initial violations
    result = subprocess.run(['ruff', 'check', '--select=SIM117'], capture_output=True, text=True)
    initial_count = len([line for line in result.stdout.split('\n') if 'SIM117' in line and not line.startswith(' ')])
    logger.info(f"Initial violations: {initial_count}")

    # Apply fixes
    try:
        fix_integration_test()
        fix_sdk_signal_listing()
        fix_signal_version_policy()
        fix_signal_execution()
        fix_optional_dependencies()

        # Check final violations
        result = subprocess.run(['ruff', 'check', '--select=SIM117'], capture_output=True, text=True)
        final_count = len([line for line in result.stdout.split('\n') if 'SIM117' in line and not line.startswith(' ')])

        logger.info(f"Final violations: {final_count}")

        if final_count == 0:
            logger.info("🎉 All SIM117 violations eliminated!")
        else:
            logger.warning(f"⚠️ {final_count} violations remain")
            print(result.stdout)

        return final_count == 0

    except Exception as e:
        logger.error(f"Error: {e}")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
