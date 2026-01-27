#!/usr/bin/env python3
"""
Manual SIM117 Violation Fixer

This script manually fixes SIM117 violations by processing each file individually
with targeted fixes based on the specific patterns found.
"""

import logging
import re
import subprocess

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ManualSIM117Fixer:
    def __init__(self):
        self.fixes_applied = 0

    def fix_integration_test_file(self):
        """Fix the integration test file - aiohttp pattern."""
        file_path = "tests/integration/test_service_integrations.py"

        try:
            with open(file_path, encoding='utf-8') as f:
                content = f.read()

            # Fix the async with aiohttp pattern
            pattern = r'(\s+)async with aiohttp\.ClientSession\(\) as session:\s*\n\s*# Test health endpoint\s*\n\s*async with session\.get\(\s*\n\s*f"\{base_url\}/health",\s*\n\s*timeout=aiohttp\.ClientTimeout\(total=10\)\s*\n\s*\) as response:'

            replacement = r'\1async with (\n\1    aiohttp.ClientSession() as session,\n\1    session.get(\n\1        f"{base_url}/health",\n\1        timeout=aiohttp.ClientTimeout(total=10)\n\1    ) as response\n\1):'

            new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

            # Also fix the patch.dict pattern
            patch_pattern = r'(\s+)with patch\.dict\(os\.environ, \{\s*\n\s*\'USE_EXTERNAL_CONFIG\': \'true\',\s*\n\s*\'ENVIRONMENT\': \'dev\'\s*\n\s*\}\):\s*\n\s*# Mock config dependencies for testing\s*\n\s*with patch\(\'app\.core\.hot_config\.BaseSignalServiceConfig\.__init__\'\) as mock_base_init:'

            patch_replacement = r'\1with (\n\1    patch.dict(os.environ, {\n\1        "USE_EXTERNAL_CONFIG": "true",\n\1        "ENVIRONMENT": "dev"\n\1    }),\n\1    patch("app.core.hot_config.BaseSignalServiceConfig.__init__") as mock_base_init\n\1):'

            new_content = re.sub(patch_pattern, patch_replacement, new_content, flags=re.MULTILINE)

            if new_content != content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                logger.info(f"Fixed {file_path}")
                self.fixes_applied += 1
                return True
        except Exception as e:
            logger.error(f"Error fixing {file_path}: {e}")
            return False

    def fix_sdk_signal_listing_file(self):
        """Fix SDK signal listing test file."""
        file_path = "tests/test_sdk_signal_listing.py"

        try:
            with open(file_path, encoding='utf-8') as f:
                content = f.read()

            # Pattern 1: Basic nested patch statements
            pattern1 = r'(\s+)with patch\(\'app\.core\.auth\.get_current_user_from_gateway\', return_value=\{"user_id": "user-123"\}\):\s*\n\s+with patch\(\'app\.services\.marketplace_client\.MarketplaceClient\.get_user_subscriptions\',\s*\n\s+return_value=([^)]+)\):'

            replacement1 = r'\1with (\n\1    patch("app.core.auth.get_current_user_from_gateway", return_value={"user_id": "user-123"}),\n\1    patch("app.services.marketplace_client.MarketplaceClient.get_user_subscriptions", return_value=\2)\n\1):'

            content = re.sub(pattern1, replacement1, content, flags=re.MULTILINE | re.DOTALL)

            # Pattern 2: Three nested patches
            pattern2 = r'(\s+)with patch\(\'app\.core\.auth\.get_current_user_from_gateway\', return_value=\{"user_id": "user-123"\}\):\s*\n\s+with patch\(\'app\.services\.marketplace_client\.MarketplaceClient\.get_user_subscriptions\',\s*\n\s+return_value=([^)]+)\):\s*\n\s+with patch\(\'algo_engine\.app\.services\.personal_script_service\.PersonalScriptService\.list_scripts\',\s*\n\s+return_value=([^)]+)\):'

            replacement2 = r'\1with (\n\1    patch("app.core.auth.get_current_user_from_gateway", return_value={"user_id": "user-123"}),\n\1    patch("app.services.marketplace_client.MarketplaceClient.get_user_subscriptions", return_value=\2),\n\1    patch("algo_engine.app.services.personal_script_service.PersonalScriptService.list_scripts", return_value=\3)\n\1):'

            content = re.sub(pattern2, replacement2, content, flags=re.MULTILINE | re.DOTALL)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Fixed {file_path}")
            self.fixes_applied += 1
            return True
        except Exception as e:
            logger.error(f"Error fixing {file_path}: {e}")
            return False

    def fix_signal_version_policy_file(self):
        """Fix signal version policy test file."""
        file_path = "tests/test_signal_version_policy.py"

        try:
            with open(file_path, encoding='utf-8') as f:
                content = f.read()

            # Fix the nested with pattern for patch statements
            # Pattern: with patch(...), with patch(...):
            pattern = r'(\s+)with \(\s*\n\s+patch\(\'app\.core\.auth\.get_current_user_from_gateway\'([^)]+)\),\s*\n\s+patch\(\'app\.services\.marketplace_client\.MarketplaceClient\.get_product_definition\',\s*\n\s+\):\s*\n\s+return_value=([^)]+)\):'

            replacement = r'\1with (\n\1    patch("app.core.auth.get_current_user_from_gateway"\2),\n\1    patch("app.services.marketplace_client.MarketplaceClient.get_product_definition", return_value=\3)\n\1):'

            content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Fixed {file_path}")
            self.fixes_applied += 1
            return True
        except Exception as e:
            logger.error(f"Error fixing {file_path}: {e}")
            return False

    def fix_signal_execution_file(self):
        """Fix signal execution test file."""
        file_path = "tests/test_signal_execution.py"

        try:
            with open(file_path, encoding='utf-8') as f:
                content = f.read()

            # Look for nested with patterns and fix them
            pattern = r'(\s+)with patch\([^:]+\):\s*\n\s+with patch\([^:]+\):'

            def fix_nested_patch(match):
                indent = match.group(1)
                # Extract the full match and parse it properly
                full_match = match.group(0)
                lines = full_match.split('\n')

                # Extract the two patch statements
                first_patch = lines[0].strip().replace('with ', '').rstrip(':')
                second_patch = lines[1].strip().replace('with ', '').rstrip(':')

                return f"{indent}with (\n{indent}    {first_patch},\n{indent}    {second_patch}\n{indent}):"

            new_content = re.sub(pattern, fix_nested_patch, content, flags=re.MULTILINE)

            if new_content != content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                logger.info(f"Fixed {file_path}")
                self.fixes_applied += 1
                return True

            return False
        except Exception as e:
            logger.error(f"Error fixing {file_path}: {e}")
            return False

    def fix_optional_dependencies_file(self):
        """Fix the optional dependencies test file."""
        file_path = "tests/unit/test_optional_dependencies_computation_errors.py"

        try:
            with open(file_path, encoding='utf-8') as f:
                content = f.read()

            # Fix pattern: with patch.dict(...): with patch(...):
            pattern1 = r'(\s+)with patch\.dict\(\'sys\.modules\', \{\'([^\']+)\': None(, \'[^\']+\': None)*\}\):\s*\n\s+with patch\(\'builtins\.__import__\', side_effect=ImportError\("([^"]+)"\)\):'

            def fix_patch_dict_pattern(match):
                indent = match.group(1)
                modules = match.group(0).split('\n')[0].split('with patch.dict')[1].split('):')[0] + ')'
                import_error = match.group(4)

                return f'{indent}with (\n{indent}    patch.dict{modules},\n{indent}    patch("builtins.__import__", side_effect=ImportError("{import_error}"))\n{indent}):'

            content = re.sub(pattern1, fix_patch_dict_pattern, content, flags=re.MULTILINE)

            # Fix the specific logging pattern
            logging_pattern = r'(\s+)with patch\(\'app\.utils\.logging_utils\.log_exception\'\):\s*\n\s+with patch\.dict\(\'sys\.modules\', \{\'findpeaks\': None\}\), patch\(\'builtins\.__import__\', side_effect=ImportError\("findpeaks not available"\)\):'

            logging_replacement = r'\1with (\n\1    patch("app.utils.logging_utils.log_exception"),\n\1    patch.dict("sys.modules", {"findpeaks": None}),\n\1    patch("builtins.__import__", side_effect=ImportError("findpeaks not available"))\n\1):'

            content = re.sub(logging_pattern, logging_replacement, content, flags=re.MULTILINE)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Fixed {file_path}")
            self.fixes_applied += 1
            return True
        except Exception as e:
            logger.error(f"Error fixing {file_path}: {e}")
            return False

    def run_syntax_check(self, file_path):
        """Check if file has valid Python syntax."""
        try:
            result = subprocess.run(['python3', '-m', 'py_compile', file_path], capture_output=True)
            return result.returncode == 0
        except Exception:
            return False

    def run(self):
        """Run all fixes."""
        logger.info("Starting manual SIM117 fixes...")

        # Check initial violations
        result = subprocess.run(['ruff', 'check', '--select=SIM117'], capture_output=True, text=True)
        initial_violations = len([line for line in result.stdout.split('\n') if 'SIM117' in line and not line.startswith(' ')])

        logger.info(f"Initial violations: {initial_violations}")

        # Apply fixes
        fixes = [
            self.fix_integration_test_file,
            self.fix_sdk_signal_listing_file,
            self.fix_signal_version_policy_file,
            self.fix_signal_execution_file,
            self.fix_optional_dependencies_file
        ]

        for fix_func in fixes:
            try:
                fix_func()
            except Exception as e:
                logger.error(f"Error in {fix_func.__name__}: {e}")

        # Check final violations
        result = subprocess.run(['ruff', 'check', '--select=SIM117'], capture_output=True, text=True)
        final_violations = len([line for line in result.stdout.split('\n') if 'SIM117' in line and not line.startswith(' ')])

        logger.info(f"Final violations: {final_violations}")
        logger.info(f"Fixes applied: {self.fixes_applied}")

        success = final_violations == 0
        if success:
            logger.info("🎉 All SIM117 violations eliminated!")
        else:
            logger.warning(f"⚠️ {final_violations} violations remain")

        return success

if __name__ == "__main__":
    fixer = ManualSIM117Fixer()
    success = fixer.run()
    exit(0 if success else 1)
