#!/usr/bin/env python3
"""
Precise SIM117 Violation Fixer

This script fixes each SIM117 violation individually using exact line matching
and replacement to avoid syntax errors.
"""

def fix_sdk_signal_listing():
    """Fix tests/test_sdk_signal_listing.py violations precisely"""
    file_path = "tests/test_sdk_signal_listing.py"

    with open(file_path) as f:
        lines = f.readlines()

    # Fix violation 1: Lines 86-90 (3 nested with statements)
    for i, line in enumerate(lines):
        if i == 85 and "with patch('app.core.auth.get_current_user_from_gateway'" in line:
            # Replace lines 85-90 with merged version
            indent = "        "
            new_lines = [
                f"{indent}with (\n",
                f"{indent}    patch('app.core.auth.get_current_user_from_gateway', return_value={{'user_id': 'user-123'}}),\n",
                f"{indent}    patch('app.services.marketplace_client.MarketplaceClient.get_user_subscriptions', return_value=mock_marketplace_subscriptions),\n",
                f"{indent}    patch('algo_engine.app.services.personal_script_service.PersonalScriptService.list_scripts', return_value=mock_personal_signals)\n",
                f"{indent}):\n"
            ]
            lines[85:90] = new_lines
            break

    # Fix violation 2: Lines around 206-208 (2 nested with statements)
    for i, line in enumerate(lines):
        if "async def test_marketplace_integration_failure" in line:
            # Find the with statements
            for j in range(i, min(i + 10, len(lines))):
                if "with patch('app.core.auth.get_current_user_from_gateway'" in lines[j]:
                    indent = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
                    new_lines = [
                        f"{indent}with (\n",
                        f"{indent}    patch('app.core.auth.get_current_user_from_gateway', return_value={{'user_id': 'user-123'}}),\n",
                        f"{indent}    patch('app.services.marketplace_client.MarketplaceClient.get_user_subscriptions', side_effect=Exception(\"Marketplace service unavailable\"))\n",
                        f"{indent}):\n"
                    ]
                    lines[j:j+3] = new_lines
                    break
            break

    # Fix violation 3: Lines around 235-237 (2 nested with statements)
    for i, line in enumerate(lines):
        if "async def test_personal_signals_integration_failure" in line:
            # Find the with statements
            for j in range(i, min(i + 10, len(lines))):
                if "with patch('app.core.auth.get_current_user_from_gateway'" in lines[j]:
                    indent = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
                    new_lines = [
                        f"{indent}with (\n",
                        f"{indent}    patch('app.core.auth.get_current_user_from_gateway', return_value={{'user_id': 'user-123'}}),\n",
                        f"{indent}    patch('algo_engine.app.services.personal_script_service.PersonalScriptService.list_scripts', side_effect=Exception(\"MinIO unavailable\"))\n",
                        f"{indent}):\n"
                    ]
                    lines[j:j+3] = new_lines
                    break
            break

    # Fix violation 4: Lines around 274-280 (verify_execution_token - multiline return_value)
    for i, line in enumerate(lines):
        if "async def test_validate_valid_token" in line:
            # Find the with statements
            for j in range(i, min(i + 15, len(lines))):
                if "with patch('app.core.auth.get_current_user_from_gateway'" in lines[j]:
                    indent = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
                    new_lines = [
                        f"{indent}with (\n",
                        f"{indent}    patch('app.core.auth.get_current_user_from_gateway', return_value={{'user_id': 'user-123'}}),\n",
                        f"{indent}    patch('app.services.marketplace_client.MarketplaceClient.verify_execution_token', return_value={{\n",
                        f"{indent}        \"is_valid\": True,\n",
                        f"{indent}        \"subscription_id\": \"sub-123\",\n",
                        f"{indent}        \"expires_at\": \"2024-12-31T23:59:59Z\"\n",
                        f"{indent}    }})\n",
                        f"{indent}):\n"
                    ]
                    # Find end of the nested with structure (should be around 7 lines)
                    end_idx = j + 7
                    lines[j:end_idx] = new_lines
                    break
            break

    # Fix violation 5: Lines around 309-311 (simple verify_execution_token)
    for i, line in enumerate(lines):
        if "async def test_validate_invalid_token" in line:
            # Find the with statements
            for j in range(i, min(i + 10, len(lines))):
                if "with patch('app.core.auth.get_current_user_from_gateway'" in lines[j]:
                    indent = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
                    new_lines = [
                        f"{indent}with (\n",
                        f"{indent}    patch('app.core.auth.get_current_user_from_gateway', return_value={{'user_id': 'user-123'}}),\n",
                        f"{indent}    patch('app.services.marketplace_client.MarketplaceClient.verify_execution_token', return_value={{\"is_valid\": False}})\n",
                        f"{indent}):\n"
                    ]
                    lines[j:j+3] = new_lines
                    break
            break

    with open(file_path, 'w') as f:
        f.writelines(lines)

    print(f"Fixed {file_path}")

def fix_signal_execution():
    """Fix tests/test_signal_execution.py violation"""
    file_path = "tests/test_signal_execution.py"

    with open(file_path) as f:
        lines = f.readlines()

    # Find and fix the patch.object nested with pattern around line 238
    for i, line in enumerate(lines):
        if "with patch.object(" in line and "SignalExecutor" in line and i > 230:  # Make sure we're in the right area
            indent = line[:len(line) - len(line.lstrip())]

            # Find the end of the first patch.object
            end_first_patch = i
            while end_first_patch < len(lines) and not lines[end_first_patch].strip().endswith('):'):
                end_first_patch += 1

            # Find the nested with patch.object
            nested_start = end_first_patch + 1
            while nested_start < len(lines) and "with patch.object(SignalExecutor, 'publish_to_redis'" not in lines[nested_start]:
                nested_start += 1

            if nested_start < len(lines):
                # Create merged version
                new_lines = [
                    f"{indent}with (\n",
                    f"{indent}    patch.object(\n",
                    f"{indent}        SignalExecutor,\n",
                    f"{indent}        'fetch_marketplace_script',\n",
                    f"{indent}        return_value={{\n",
                    f"{indent}            \"content\": sample_script,\n",
                    f"{indent}            \"metadata\": {{}},\n",
                    f"{indent}            \"product_id\": \"prod-123\"\n",
                    f"{indent}        }}\n",
                    f"{indent}    ),\n",
                    f"{indent}    patch.object(SignalExecutor, 'publish_to_redis', return_value=True)\n",
                    f"{indent}):\n"
                ]

                # Replace the original lines
                lines[i:nested_start + 1] = new_lines
                break

    with open(file_path, 'w') as f:
        f.writelines(lines)

    print(f"Fixed {file_path}")

def main():
    """Run precise fixes"""
    print("Applying precise SIM117 fixes...")

    fix_sdk_signal_listing()
    fix_signal_execution()

    print("Precise fixes completed!")

if __name__ == "__main__":
    main()
