#!/usr/bin/env python3
"""
Fix the remaining 3 SIM117 violations in test_signal_execution.py
"""

def fix_remaining_violations():
    """Fix the last 3 SIM117 violations"""
    file_path = "tests/test_signal_execution.py"

    with open(file_path) as f:
        content = f.read()

    # Fix 1: Lines 238-248 - patch.object nested with statements
    old_pattern1 = """        with patch.object(
            SignalExecutor,
            'fetch_marketplace_script',
            return_value={
                "content": sample_script,
                "metadata": {},
                "product_id": "prod-123"
            }
        ):
            # Mock Redis publish
            with patch.object(SignalExecutor, 'publish_to_redis', return_value=True):"""

    new_pattern1 = """        with (
            patch.object(
                SignalExecutor,
                'fetch_marketplace_script',
                return_value={
                    "content": sample_script,
                    "metadata": {},
                    "product_id": "prod-123"
                }
            ),
            patch.object(SignalExecutor, 'publish_to_redis', return_value=True)
        ):"""

    content = content.replace(old_pattern1, new_pattern1)

    # Fix 2: Lines 276-278 - auth + execute_marketplace_signal
    old_pattern2 = """        with patch('app.core.auth.get_current_user_from_gateway', return_value={"user_id": "123"}):
            # Mock background task
            with patch('app.services.signal_executor.SignalExecutor.execute_marketplace_signal'):"""

    new_pattern2 = """        with (
            patch('app.core.auth.get_current_user_from_gateway', return_value={"user_id": "123"}),
            patch('app.services.signal_executor.SignalExecutor.execute_marketplace_signal')
        ):"""

    content = content.replace(old_pattern2, new_pattern2)

    # Fix 3: Lines 305-307 - auth + execute_personal_signal
    old_pattern3 = """        with patch('app.core.auth.get_current_user_from_gateway', return_value={"user_id": "123"}):
            # Mock background task
            with patch('app.services.signal_executor.SignalExecutor.execute_personal_signal'):"""

    new_pattern3 = """        with (
            patch('app.core.auth.get_current_user_from_gateway', return_value={"user_id": "123"}),
            patch('app.services.signal_executor.SignalExecutor.execute_personal_signal')
        ):"""

    content = content.replace(old_pattern3, new_pattern3)

    with open(file_path, 'w') as f:
        f.write(content)

    print(f"Fixed remaining violations in {file_path}")

if __name__ == "__main__":
    fix_remaining_violations()
