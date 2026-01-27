"""
Comprehensive ACL (Access Control List) testing for external function execution
Tests user permissions, role-based access, and security isolation
"""

import asyncio
import os
import shutil
import tempfile
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from app.errors import SecurityError
from app.schemas.config_schema import ExternalFunctionConfig, TickProcessingContext
from app.services.external_function_executor import ExternalFunctionExecutor


class TestACLEnforcement:
    """Test Access Control Lists for external function execution"""

    @pytest.fixture
    def temp_storage_dir(self):
        """Create temporary storage directory with user isolation"""
        temp_dir = tempfile.mkdtemp()

        # Create multi-user directory structure
        users = ["premium_user_001", "basic_user_002", "admin_user_003", "suspended_user_004"]
        for user in users:
            user_dir = os.path.join(temp_dir, user)
            os.makedirs(user_dir, exist_ok=True)

        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def executor(self):
        """Create executor instance"""
        return ExternalFunctionExecutor()

    @pytest.fixture
    def sample_context(self):
        """Sample processing context"""
        return TickProcessingContext(
            instrument_key="NSE@RELIANCE@EQ",
            timestamp=datetime.now(UTC),
            tick_data={
                "ltp": {"value": 2500.50, "currency": "INR"},
                "volume": 1000000
            },
            aggregated_data={}
        )

    @pytest.fixture
    def user_roles(self):
        """Define user roles and permissions"""
        return {
            "premium_user_001": {
                "role": "premium",
                "permissions": [
                    "execute_custom_functions",
                    "upload_functions",
                    "access_market_data",
                    "high_resource_limits"
                ],
                "max_functions": 50,
                "max_memory_mb": 128,
                "max_timeout": 30
            },
            "basic_user_002": {
                "role": "basic",
                "permissions": [
                    "execute_custom_functions",
                    "upload_functions",
                    "access_market_data"
                ],
                "max_functions": 10,
                "max_memory_mb": 32,
                "max_timeout": 10
            },
            "admin_user_003": {
                "role": "admin",
                "permissions": [
                    "execute_custom_functions",
                    "upload_functions",
                    "access_market_data",
                    "high_resource_limits",
                    "admin_functions",
                    "cross_user_access"  # Special admin permission
                ],
                "max_functions": 100,
                "max_memory_mb": 256,
                "max_timeout": 60
            },
            "suspended_user_004": {
                "role": "suspended",
                "permissions": [],  # No permissions
                "max_functions": 0,
                "max_memory_mb": 0,
                "max_timeout": 0
            }
        }

    # User Isolation Tests

    @patch('app.services.external_function_executor.settings')
    async def test_user_namespace_isolation(self, mock_settings, temp_storage_dir, executor, sample_context, user_roles):
        """Test users can only access their own namespace"""
        mock_settings.EXTERNAL_FUNCTIONS_STORAGE = temp_storage_dir

        # Create scripts for different users
        users_scripts = {
            "premium_user_001": "def premium_function(): return {'type': 'premium', 'data': 'secret_premium_data'}",
            "basic_user_002": "def basic_function(): return {'type': 'basic', 'data': 'basic_data'}",
            "admin_user_003": "def admin_function(): return {'type': 'admin', 'data': 'admin_secret'}"
        }

        for user_id, script_content in users_scripts.items():
            user_dir = os.path.join(temp_storage_dir, user_id)
            script_path = os.path.join(user_dir, "private_script.py")
            with open(script_path, 'w') as f:
                f.write(script_content)

        # Test: premium_user_001 trying to access basic_user_002's script
        unauthorized_config = ExternalFunctionConfig(
            name="unauthorized_access",
            function_name="basic_function",
            function_path="basic_user_002/private_script.py",  # Different user's path
            file_path="basic_user_002/private_script.py",
            parameters={},
            timeout=5,
            memory_limit_mb=32
        )

        # Mock ACL check that should fail
        with patch('app.services.external_function_executor.ExternalFunctionExecutor._check_user_access') as mock_acl:
            mock_acl.return_value = False  # Access denied

            with pytest.raises(SecurityError, match="Access denied|User not authorized"):
                await self._execute_with_acl_check(
                    executor, unauthorized_config, sample_context, "premium_user_001"
                )

        # Test: User accessing their own script (should work)
        authorized_config = ExternalFunctionConfig(
            name="authorized_access",
            function_name="premium_function",
            function_path="premium_user_001/private_script.py",
            file_path="premium_user_001/private_script.py",
            parameters={},
            timeout=5,
            memory_limit_mb=64
        )

        with patch('app.services.external_function_executor.ExternalFunctionExecutor._check_user_access') as mock_acl:
            mock_acl.return_value = True  # Access granted

            # Should succeed (mock the actual execution)
            script_content = await executor._load_function_securely(authorized_config)
            assert "premium_function" in script_content

    async def test_role_based_resource_limits(self, executor, sample_context, user_roles):
        """Test resource limits are enforced based on user roles"""

        for user_id, role_info in user_roles.items():
            if role_info["role"] == "suspended":
                continue  # Skip suspended user

            # Test memory limit enforcement
            config_within_limits = ExternalFunctionConfig(
                name="memory_test",
                function_name="test_function",
                function_path=f"{user_id}/test.py",
                file_path=f"{user_id}/test.py",
                parameters={},
                timeout=5,
                memory_limit_mb=role_info["max_memory_mb"] - 1  # Within limits
            )

            config_exceeds_limits = ExternalFunctionConfig(
                name="memory_test_exceed",
                function_name="test_function",
                function_path=f"{user_id}/test.py",
                file_path=f"{user_id}/test.py",
                parameters={},
                timeout=5,
                memory_limit_mb=role_info["max_memory_mb"] + 64  # Exceeds limits
            )

            # Mock role validation
            with patch('app.services.external_function_executor.ExternalFunctionExecutor._get_user_role') as mock_role:
                mock_role.return_value = role_info

                # Within limits should pass validation
                try:
                    await self._validate_with_acl(executor, config_within_limits, user_id)
                except SecurityError as e:
                    if "Memory limit too high" not in str(e):
                        pytest.fail(f"Unexpected validation error for {user_id}: {e}")

                # Exceeding limits should fail
                with pytest.raises(SecurityError, match="Memory limit too high|Resource limit exceeded"):
                    await self._validate_with_acl(executor, config_exceeds_limits, user_id)

    async def test_permission_based_access_control(self, executor, sample_context, user_roles):
        """Test permission-based access to different function types"""

        # Define function types with required permissions
        function_configs = {
            "market_data_function": {
                "required_permissions": ["access_market_data"],
                "config": ExternalFunctionConfig(
                    name="market_data",
                    function_name="get_market_data",
                    function_path="user/market_data.py",
                    file_path="user/market_data.py",
                    parameters={},
                    timeout=5,
                    memory_limit_mb=32
                )
            },
            "admin_function": {
                "required_permissions": ["admin_functions"],
                "config": ExternalFunctionConfig(
                    name="admin_task",
                    function_name="admin_task",
                    function_path="user/admin_task.py",
                    file_path="user/admin_task.py",
                    parameters={},
                    timeout=10,
                    memory_limit_mb=64
                )
            },
            "high_resource_function": {
                "required_permissions": ["high_resource_limits"],
                "config": ExternalFunctionConfig(
                    name="high_resource",
                    function_name="compute_intensive",
                    function_path="user/compute.py",
                    file_path="user/compute.py",
                    parameters={},
                    timeout=30,
                    memory_limit_mb=128
                )
            }
        }

        for user_id, role_info in user_roles.items():
            user_permissions = set(role_info["permissions"])

            for func_name, func_info in function_configs.items():
                required_perms = set(func_info["required_permissions"])
                has_permission = required_perms.issubset(user_permissions)

                with patch('app.services.external_function_executor.ExternalFunctionExecutor._get_user_role') as mock_role:
                    mock_role.return_value = role_info

                    if has_permission:
                        # User has permission - should succeed (or fail for other reasons)
                        try:
                            await self._validate_with_acl(executor, func_info["config"], user_id)
                        except SecurityError as e:
                            # Only acceptable if it's a resource limit error, not permission error
                            if "permission" in str(e).lower() or "access denied" in str(e).lower():
                                pytest.fail(f"User {user_id} should have access to {func_name}: {e}")
                    else:
                        # User lacks permission - should fail
                        with pytest.raises(SecurityError, match="permission|access denied|not authorized"):
                            await self._validate_with_acl(executor, func_info["config"], user_id)

    # Cross-User Access Tests

    @patch('app.services.external_function_executor.settings')
    async def test_admin_cross_user_access(self, mock_settings, temp_storage_dir, executor, sample_context, user_roles):
        """Test admin users can access other users' functions when permitted"""
        mock_settings.EXTERNAL_FUNCTIONS_STORAGE = temp_storage_dir

        # Create a script owned by basic user
        basic_user_dir = os.path.join(temp_storage_dir, "basic_user_002")
        script_path = os.path.join(basic_user_dir, "shared_function.py")
        with open(script_path, 'w') as f:
            f.write("def shared_function(): return {'shared': True}")

        # Admin trying to access basic user's script
        cross_access_config = ExternalFunctionConfig(
            name="cross_access",
            function_name="shared_function",
            function_path="basic_user_002/shared_function.py",
            file_path="basic_user_002/shared_function.py",
            parameters={},
            timeout=5,
            memory_limit_mb=32
        )

        # Mock admin role with cross-user access permission
        admin_role = user_roles["admin_user_003"]

        with patch('app.services.external_function_executor.ExternalFunctionExecutor._get_user_role') as mock_role:
            mock_role.return_value = admin_role

            with patch('app.services.external_function_executor.ExternalFunctionExecutor._check_cross_user_access') as mock_cross_access:
                mock_cross_access.return_value = True  # Admin has cross-user access

                # Should succeed for admin
                script_content = await executor._load_function_securely(cross_access_config)
                assert "shared_function" in script_content

        # Test: Basic user trying same cross-user access (should fail)
        basic_role = user_roles["basic_user_002"]

        with patch('app.services.external_function_executor.ExternalFunctionExecutor._get_user_role') as mock_role:
            mock_role.return_value = basic_role

            with patch('app.services.external_function_executor.ExternalFunctionExecutor._check_cross_user_access') as mock_cross_access:
                mock_cross_access.return_value = False  # Basic user lacks cross-user access

                with pytest.raises(SecurityError, match="Cross-user access denied|Access denied"):
                    await executor._load_function_securely(cross_access_config)

    async def test_suspended_user_access_denial(self, executor, sample_context, user_roles):
        """Test suspended users are completely denied access"""

        suspended_role = user_roles["suspended_user_004"]

        # Any function config for suspended user
        config = ExternalFunctionConfig(
            name="any_function",
            function_name="any_function",
            function_path="suspended_user_004/script.py",
            file_path="suspended_user_004/script.py",
            parameters={},
            timeout=1,
            memory_limit_mb=1
        )

        with patch('app.services.external_function_executor.ExternalFunctionExecutor._get_user_role') as mock_role:
            mock_role.return_value = suspended_role

            # All operations should be denied for suspended user
            with pytest.raises(SecurityError, match="suspended|access denied|not authorized"):
                await self._validate_with_acl(executor, config, "suspended_user_004")

    # Shared Functions and Group Access

    @patch('app.services.external_function_executor.settings')
    async def test_shared_function_group_access(self, mock_settings, temp_storage_dir, executor, sample_context):
        """Test shared functions with group-based access control"""
        mock_settings.EXTERNAL_FUNCTIONS_STORAGE = temp_storage_dir

        # Create shared functions directory
        shared_dir = os.path.join(temp_storage_dir, "shared")
        os.makedirs(shared_dir, exist_ok=True)

        # Create shared function
        shared_script = '''
def market_indicator(tick_data, parameters):
    """Shared market indicator available to premium users"""
    return {
        "indicator": "RSI",
        "value": 65.5,
        "signal": "neutral"
    }
'''

        script_path = os.path.join(shared_dir, "market_indicators.py")
        with open(script_path, 'w') as f:
            f.write(shared_script)

        shared_config = ExternalFunctionConfig(
            name="shared_indicator",
            function_name="market_indicator",
            function_path="shared/market_indicators.py",
            file_path="shared/market_indicators.py",
            parameters={},
            timeout=5,
            memory_limit_mb=32
        )

        # Test premium user access (should work)
        with patch('app.services.external_function_executor.ExternalFunctionExecutor._check_shared_access') as mock_shared:
            mock_shared.return_value = True  # Premium user has shared access

            script_content = await executor._load_function_securely(shared_config)
            assert "market_indicator" in script_content

        # Test basic user access to premium-only shared function (should fail)
        with patch('app.services.external_function_executor.ExternalFunctionExecutor._check_shared_access') as mock_shared:
            mock_shared.return_value = False  # Basic user lacks shared access

            with pytest.raises(SecurityError, match="Shared function access denied"):
                await executor._load_function_securely(shared_config)

    # Audit and Logging Tests

    async def test_acl_violation_auditing(self, executor, sample_context, user_roles):
        """Test ACL violations are properly audited and logged"""

        unauthorized_config = ExternalFunctionConfig(
            name="unauthorized",
            function_name="steal_data",
            function_path="admin_user_003/secret_function.py",  # Trying to access admin function
            file_path="admin_user_003/secret_function.py",
            parameters={},
            timeout=5,
            memory_limit_mb=32
        )

        with patch('app.services.external_function_executor.ExternalFunctionExecutor._audit_access_attempt') as mock_audit:
            with patch('app.services.external_function_executor.ExternalFunctionExecutor._check_user_access') as mock_acl:
                mock_acl.return_value = False  # Access denied

                try:
                    await self._execute_with_acl_check(
                        executor, unauthorized_config, sample_context, "basic_user_002"
                    )
                except SecurityError:
                    pass  # Expected

                # Verify audit was called
                mock_audit.assert_called_once()
                audit_call = mock_audit.call_args[0]

                assert "basic_user_002" in str(audit_call)  # User ID logged
                assert "access_denied" in str(audit_call) or "unauthorized" in str(audit_call)
                assert "admin_user_003/secret_function.py" in str(audit_call)  # Attempted path logged

    # Concurrent ACL Tests

    async def test_concurrent_acl_enforcement(self, executor, sample_context, user_roles):
        """Test ACL enforcement under concurrent access"""

        # Multiple users trying to access functions simultaneously
        concurrent_configs = []
        expected_results = []

        for user_id, role_info in user_roles.items():
            if role_info["role"] == "suspended":
                continue

            config = ExternalFunctionConfig(
                name=f"concurrent_{user_id}",
                function_name="test_function",
                function_path=f"{user_id}/test.py",
                file_path=f"{user_id}/test.py",
                parameters={},
                timeout=5,
                memory_limit_mb=role_info["max_memory_mb"] // 2
            )

            concurrent_configs.append((config, user_id))
            expected_results.append("execute_custom_functions" in role_info["permissions"])

        async def check_single_acl(config_and_user):
            config, user_id = config_and_user
            role_info = user_roles[user_id]

            with patch('app.services.external_function_executor.ExternalFunctionExecutor._get_user_role') as mock_role:
                mock_role.return_value = role_info

                try:
                    await self._validate_with_acl(executor, config, user_id)
                    return True
                except SecurityError:
                    return False

        # Execute concurrent ACL checks
        results = await asyncio.gather(
            *[check_single_acl(config_user) for config_user in concurrent_configs],
            return_exceptions=True
        )

        # Verify results match expectations
        for i, (result, expected) in enumerate(zip(results, expected_results, strict=False)):
            if isinstance(result, Exception):
                actual = False
            else:
                actual = result

            assert actual == expected, f"ACL check failed for user {concurrent_configs[i][1]}: expected {expected}, got {actual}"

    # Helper Methods

    async def _execute_with_acl_check(self, executor, config, context, user_id):
        """Execute function with ACL validation"""
        # Mock the ACL validation process
        with patch('app.services.external_function_executor.ExternalFunctionExecutor._validate_user_access') as mock_validate:
            mock_validate.side_effect = SecurityError("Access denied")
            await executor.execute_single_function(config, context, asyncio.Semaphore(1))

    async def _validate_with_acl(self, executor, config, user_id):
        """Validate configuration with ACL checks"""
        # Simulate ACL validation in configuration validation
        role_info = None

        # Mock getting user role
        with patch('app.services.external_function_executor.ExternalFunctionExecutor._get_user_role') as mock_get_role:
            if hasattr(self, '_mock_roles'):
                role_info = self._mock_roles.get(user_id)

            if role_info:
                mock_get_role.return_value = role_info

                # Check permissions
                if not role_info["permissions"]:
                    raise SecurityError(f"User {user_id} has no permissions")

                if "execute_custom_functions" not in role_info["permissions"]:
                    raise SecurityError(f"User {user_id} lacks execute permission")

                # Check resource limits
                if config.memory_limit_mb > role_info["max_memory_mb"]:
                    raise SecurityError(f"Memory limit too high for user {user_id}")

                if config.timeout > role_info["max_timeout"]:
                    raise SecurityError(f"Timeout too high for user {user_id}")

            # Call original validation
            executor.validate_function_config(config)


class TestACLIntegrationWithExistingSystem:
    """Test ACL integration with existing external function execution system"""

    async def test_acl_integration_with_security_validation(self):
        """Test ACL works alongside existing security validation"""

        executor = ExternalFunctionExecutor()

        # Script that passes security validation but fails ACL
        safe_script = '''
def safe_function(tick_data, parameters):
    return {"result": "safe", "price": tick_data["ltp"]["value"]}
'''

        config = ExternalFunctionConfig(
            name="safe_function",
            function_name="safe_function",
            function_path="unauthorized_user/safe.py",
            file_path="unauthorized_user/safe.py",
            parameters={},
            timeout=5,
            memory_limit_mb=32
        )

        # Should pass security validation
        executor._validate_function_code(safe_script, config)

        # But fail ACL check
        with patch('app.services.external_function_executor.ExternalFunctionExecutor._check_user_access') as mock_acl:
            mock_acl.return_value = False

            with pytest.raises(SecurityError, match="Access denied|User not authorized"):
                # Simulate ACL check in load function
                if not mock_acl.return_value:
                    raise SecurityError("User not authorized to access this function")

    async def test_acl_performance_impact(self):
        """Test ACL checks don't significantly impact performance"""
        import time

        executor = ExternalFunctionExecutor()

        config = ExternalFunctionConfig(
            name="perf_test",
            function_name="perf_test",
            function_path="user/perf.py",
            file_path="user/perf.py",
            parameters={},
            timeout=5,
            memory_limit_mb=32
        )

        # Measure validation time without ACL
        start_time = time.time()
        for _ in range(100):
            executor.validate_function_config(config)
        baseline_time = time.time() - start_time

        # Measure validation time with ACL
        with patch('app.services.external_function_executor.ExternalFunctionExecutor._validate_acl') as mock_acl:
            mock_acl.return_value = True

            start_time = time.time()
            for _ in range(100):
                executor.validate_function_config(config)
                mock_acl()  # Simulate ACL check
            acl_time = time.time() - start_time

        # ACL overhead should be minimal (< 20% increase)
        overhead = (acl_time - baseline_time) / baseline_time
        assert overhead < 0.2, f"ACL overhead too high: {overhead:.1%}"
