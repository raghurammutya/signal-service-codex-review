"""
Comprehensive unit tests for ExternalFunctionExecutor
Tests security, MinIO integration, resource limits, and sandbox execution
"""

import asyncio
import os
import shutil
import tempfile
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.errors import ExternalFunctionExecutionError, SecurityError
from app.schemas.config_schema import ExternalFunctionConfig, TickProcessingContext
from app.services.external_function_executor import ExternalFunctionExecutor


class TestExternalFunctionExecutor:
    """Test external function execution with comprehensive security validation"""

    @pytest.fixture
    def executor(self):
        """Create ExternalFunctionExecutor instance"""
        return ExternalFunctionExecutor()

    @pytest.fixture
    def sample_context(self):
        """Sample processing context"""
        return TickProcessingContext(
            instrument_key="NSE@RELIANCE@EQ",
            timestamp=datetime.now(),
            tick_data={
                "ltp": {"value": 2500.50, "currency": "INR"},
                "high": {"value": 2510.00},
                "low": {"value": 2490.00},
                "open": {"value": 2495.00},
                "volume": 1000000
            },
            aggregated_data={}
        )

    @pytest.fixture
    def safe_function_config(self):
        """Safe function configuration for testing"""
        return ExternalFunctionConfig(
            name="test_function",
            function_name="calculate_signal",
            function_path="safe/test_function.py",
            file_path="safe/test_function.py",
            parameters={"threshold": 0.05},
            timeout=5,
            memory_limit_mb=64
        )

    @pytest.fixture
    def sample_safe_code(self):
        """Sample safe Python code for testing"""
        return '''
def calculate_signal(tick_data, parameters):
    """Calculate a simple moving average signal"""
    threshold = parameters.get('threshold', 0.05)
    ltp = tick_data['ltp']['value']

    # Simple calculation
    signal_strength = ltp * threshold

    return {
        'signal': 'buy' if signal_strength > 100 else 'hold',
        'strength': signal_strength,
        'price': ltp
    }
'''

    @pytest.fixture
    def malicious_code(self):
        """Sample malicious code that should be blocked"""
        return '''
import os
import sys

def calculate_signal(tick_data, parameters):
    # Malicious operations
    os.system("rm -rf /")
    exec("print('hacked')")
    return {"hacked": True}
'''

    # Security Validation Tests

    def test_validate_function_config_safe_path(self, executor):
        """Test validation of safe function configuration"""
        safe_config = ExternalFunctionConfig(
            name="test",
            function_name="valid_function",
            function_path="safe/function.py",
            file_path="safe/function.py",
            parameters={},
            timeout=5,
            memory_limit_mb=32
        )

        # Should not raise exception
        executor.validate_function_config(safe_config)

    def test_validate_function_config_unsafe_paths(self, executor):
        """Test validation blocks unsafe file paths"""
        unsafe_configs = [
            # Path traversal attacks
            ExternalFunctionConfig(
                name="test", function_name="test", function_path="../etc/passwd",
                file_path="../etc/passwd", parameters={}, timeout=5, memory_limit_mb=32
            ),
            # Absolute paths
            ExternalFunctionConfig(
                name="test", function_name="test", function_path="/etc/passwd",
                file_path="/etc/passwd", parameters={}, timeout=5, memory_limit_mb=32
            )
        ]

        for config in unsafe_configs:
            with pytest.raises(SecurityError, match="Unsafe file path"):
                executor.validate_function_config(config)

    def test_validate_function_config_invalid_names(self, executor):
        """Test validation blocks invalid function names"""
        invalid_configs = [
            ExternalFunctionConfig(
                name="test", function_name="invalid-name", function_path="safe.py",
                file_path="safe.py", parameters={}, timeout=5, memory_limit_mb=32
            ),
            ExternalFunctionConfig(
                name="test", function_name="123invalid", function_path="safe.py",
                file_path="safe.py", parameters={}, timeout=5, memory_limit_mb=32
            )
        ]

        for config in invalid_configs:
            with pytest.raises(SecurityError, match="Invalid function name"):
                executor.validate_function_config(config)

    @patch('app.services.external_function_executor.settings')
    def test_validate_function_config_resource_limits(self, mock_settings, executor):
        """Test validation enforces resource limits"""
        mock_settings.EXTERNAL_FUNCTION_MAX_MEMORY_MB = 128
        mock_settings.EXTERNAL_FUNCTION_TIMEOUT = 10

        # Memory limit too high
        high_memory_config = ExternalFunctionConfig(
            name="test", function_name="test", function_path="safe.py",
            file_path="safe.py", parameters={}, timeout=5, memory_limit_mb=256
        )

        with pytest.raises(SecurityError, match="Memory limit too high"):
            executor.validate_function_config(high_memory_config)

        # Timeout too high
        high_timeout_config = ExternalFunctionConfig(
            name="test", function_name="test", function_path="safe.py",
            file_path="safe.py", parameters={}, timeout=20, memory_limit_mb=64
        )

        with pytest.raises(SecurityError, match="Timeout too high"):
            executor.validate_function_config(high_timeout_config)

    def test_is_safe_path(self, executor):
        """Test path safety validation"""
        safe_paths = [
            "functions/my_function.py",
            "user123/strategy.py",
            "safe_dir/nested/function.py"
        ]

        unsafe_paths = [
            "../../../etc/passwd",
            "/absolute/path.py",
            "dir/../../../sensitive.py",
            "",
            None
        ]

        for path in safe_paths:
            assert executor._is_safe_path(path), f"Should accept safe path: {path}"

        for path in unsafe_paths:
            assert not executor._is_safe_path(path), f"Should reject unsafe path: {path}"

    def test_validate_function_code_safe(self, executor, safe_function_config, sample_safe_code):
        """Test code validation accepts safe code"""
        # Should not raise exception
        executor._validate_function_code(sample_safe_code, safe_function_config)

    def test_validate_function_code_malicious(self, executor, safe_function_config, malicious_code):
        """Test code validation blocks malicious patterns"""
        with pytest.raises(SecurityError, match="Prohibited code pattern detected"):
            executor._validate_function_code(malicious_code, safe_function_config)

    def test_validate_function_code_prohibited_patterns(self, executor, safe_function_config):
        """Test specific prohibited patterns are blocked"""
        prohibited_codes = [
            "import os\ndef test(): pass",
            "import sys\ndef test(): pass",
            "import subprocess\ndef test(): pass",
            "open('/etc/passwd')\ndef test(): pass",
            "exec('malicious')\ndef test(): pass",
            "eval('dangerous')\ndef test(): pass",
            "__import__('os')\ndef test(): pass"
        ]

        for code in prohibited_codes:
            with pytest.raises(SecurityError, match="Prohibited code pattern detected"):
                executor._validate_function_code(code, safe_function_config)

    def test_validate_function_code_missing_function(self, executor):
        """Test validation requires specific function to be present"""
        config = ExternalFunctionConfig(
            name="test", function_name="missing_function", function_path="safe.py",
            file_path="safe.py", parameters={}, timeout=5, memory_limit_mb=32
        )

        code_without_function = "def other_function(): pass"

        with pytest.raises(SecurityError, match="Required function 'missing_function' not found"):
            executor._validate_function_code(code_without_function, config)

    def test_validate_function_code_too_long(self, executor, safe_function_config):
        """Test code length limits"""
        long_code = "def test(): pass\n" + "# comment\n" * 1000  # Very long code

        with pytest.raises(SecurityError, match="Function code too long"):
            executor._validate_function_code(long_code, safe_function_config)

    # MinIO/Storage Integration Tests

    @pytest.fixture
    def temp_storage_dir(self):
        """Create temporary storage directory for testing"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @patch('app.services.external_function_executor.settings')
    async def test_load_function_securely_success(self, mock_settings, executor, temp_storage_dir, sample_safe_code):
        """Test successful secure function loading"""
        mock_settings.EXTERNAL_FUNCTIONS_STORAGE = temp_storage_dir

        # Create test function file
        function_dir = os.path.join(temp_storage_dir, "user123")
        os.makedirs(function_dir)
        function_file = os.path.join(function_dir, "strategy.py")

        with open(function_file, 'w') as f:
            f.write(sample_safe_code)

        config = ExternalFunctionConfig(
            name="test", function_name="calculate_signal",
            function_path="user123/strategy.py", file_path="user123/strategy.py",
            parameters={}, timeout=5, memory_limit_mb=32
        )

        result = await executor._load_function_securely(config)
        assert result == sample_safe_code

    @patch('app.services.external_function_executor.settings')
    async def test_load_function_securely_path_traversal(self, mock_settings, executor, temp_storage_dir):
        """Test protection against path traversal attacks"""
        mock_settings.EXTERNAL_FUNCTIONS_STORAGE = temp_storage_dir

        config = ExternalFunctionConfig(
            name="test", function_name="test", function_path="../../../etc/passwd",
            file_path="../../../etc/passwd", parameters={}, timeout=5, memory_limit_mb=32
        )

        with pytest.raises(SecurityError, match="Function path outside secure storage directory"):
            await executor._load_function_securely(config)

    @patch('app.services.external_function_executor.settings')
    async def test_load_function_securely_file_not_found(self, mock_settings, executor, temp_storage_dir):
        """Test handling of missing files"""
        mock_settings.EXTERNAL_FUNCTIONS_STORAGE = temp_storage_dir

        config = ExternalFunctionConfig(
            name="test", function_name="test", function_path="nonexistent/file.py",
            file_path="nonexistent/file.py", parameters={}, timeout=5, memory_limit_mb=32
        )

        with pytest.raises(SecurityError, match="Function file not found"):
            await executor._load_function_securely(config)

    @patch('app.services.external_function_executor.settings')
    async def test_load_function_securely_file_too_large(self, mock_settings, executor, temp_storage_dir):
        """Test file size limits"""
        mock_settings.EXTERNAL_FUNCTIONS_STORAGE = temp_storage_dir

        # Create large file (> 50KB)
        function_dir = os.path.join(temp_storage_dir, "user123")
        os.makedirs(function_dir)
        function_file = os.path.join(function_dir, "large_function.py")

        with open(function_file, 'w') as f:
            f.write("# Large file\n" * 5000)  # > 50KB

        config = ExternalFunctionConfig(
            name="test", function_name="test", function_path="user123/large_function.py",
            file_path="user123/large_function.py", parameters={}, timeout=5, memory_limit_mb=32
        )

        with pytest.raises(SecurityError, match="Function file too large"):
            await executor._load_function_securely(config)

    # Compilation and Execution Tests

    @patch('app.services.external_function_executor.RESTRICTED_PYTHON_AVAILABLE', True)
    @patch('app.services.external_function_executor.compile_restricted')
    def test_compile_function_safely_success(self, mock_compile, executor, sample_safe_code):
        """Test successful function compilation"""
        mock_compiled = Mock()
        mock_compiled.errors = []
        mock_compiled.code = compile(sample_safe_code, '<test>', 'exec')
        mock_compile.return_value = mock_compiled

        config = ExternalFunctionConfig(
            name="test", function_name="calculate_signal", function_path="safe.py",
            file_path="safe.py", parameters={}, timeout=5, memory_limit_mb=32
        )

        result = executor.compile_function_safely(sample_safe_code, config)
        assert result is not None
        mock_compile.assert_called_once()

    @patch('app.services.external_function_executor.RESTRICTED_PYTHON_AVAILABLE', True)
    @patch('app.services.external_function_executor.compile_restricted')
    def test_compile_function_safely_compilation_errors(self, mock_compile, executor):
        """Test handling of compilation errors"""
        mock_compiled = Mock()
        mock_compiled.errors = ["Syntax error at line 1"]
        mock_compile.return_value = mock_compiled

        config = ExternalFunctionConfig(
            name="test", function_name="test", function_path="safe.py",
            file_path="safe.py", parameters={}, timeout=5, memory_limit_mb=32
        )

        with pytest.raises(SecurityError, match="Compilation errors"):
            executor.compile_function_safely("invalid python code", config)

    @patch('app.services.external_function_executor.RESTRICTED_PYTHON_AVAILABLE', False)
    def test_compile_function_safely_restricted_python_unavailable(self, executor):
        """Test handling when RestrictedPython is not available"""
        config = ExternalFunctionConfig(
            name="test", function_name="test", function_path="safe.py",
            file_path="safe.py", parameters={}, timeout=5, memory_limit_mb=32
        )

        with pytest.raises(SecurityError, match="RestrictedPython not available"):
            executor.compile_function_safely("def test(): pass", config)

    def test_prepare_execution_context(self, executor, sample_context, safe_function_config):
        """Test execution context preparation"""
        context = executor.prepare_execution_context(sample_context, safe_function_config)

        # Check required globals are present
        assert 'tick_data' in context
        assert 'parameters' in context
        assert 'instrument_key' in context
        assert 'timestamp' in context

        # Check safe builtins
        assert 'len' in context
        assert 'str' in context
        assert 'min' in context
        assert 'max' in context

        # Check data is correct
        assert context['tick_data'] == sample_context.tick_data
        assert context['parameters'] == safe_function_config.parameters
        assert context['instrument_key'] == sample_context.instrument_key

    @patch('app.services.external_function_executor.resource')
    def test_execute_in_subprocess_resource_limits(self, mock_resource, executor):
        """Test resource limits are applied during execution"""
        config = ExternalFunctionConfig(
            name="test", function_name="calculate_signal", function_path="safe.py",
            file_path="safe.py", parameters={}, timeout=5, memory_limit_mb=64
        )

        # Mock successful execution
        compiled_code = compile("def calculate_signal(tick_data, params): return {'result': 'success'}", '<test>', 'exec')
        execution_context = {
            'tick_data': {'ltp': {'value': 100}},
            'parameters': {}
        }

        try:
            executor._execute_in_subprocess(compiled_code, execution_context, config)
        except Exception:
            pass  # Expected to fail due to missing function in context

        # Verify resource limits were set
        expected_memory_limit = 64 * 1024 * 1024  # 64MB in bytes
        mock_resource.setrlimit.assert_any_call(
            mock_resource.RLIMIT_AS,
            (expected_memory_limit, expected_memory_limit)
        )
        mock_resource.setrlimit.assert_any_call(
            mock_resource.RLIMIT_CPU,
            (5, 5)  # timeout seconds
        )

    # Integration Tests

    @pytest.mark.asyncio
    async def test_execute_single_function_timeout(self, executor, sample_context):
        """Test function execution timeout"""
        config = ExternalFunctionConfig(
            name="test", function_name="slow_function", function_path="safe.py",
            file_path="safe.py", parameters={}, timeout=0.1, memory_limit_mb=32  # Very short timeout
        )

        # Mock a slow function
        with patch.object(executor, 'load_function_code', return_value=AsyncMock()), patch.object(executor, 'compile_function_safely'), patch.object(executor, 'prepare_execution_context'), patch.object(executor, 'execute_with_limits',
                                side_effect=asyncio.sleep(1)), pytest.raises(ExternalFunctionExecutionError, match="timed out"):
            await executor.execute_single_function(
                config, sample_context, asyncio.Semaphore(1)
            )

    @pytest.mark.asyncio
    @patch('app.services.external_function_executor.settings')
    async def test_execute_functions_disabled(self, mock_settings, executor, sample_context):
        """Test handling when external functions are disabled"""
        mock_settings.ENABLE_EXTERNAL_FUNCTIONS = False

        config = Mock()
        config.external_functions = [Mock()]

        result = await executor.execute_functions(config, sample_context)
        assert result == {}

    @pytest.mark.asyncio
    @patch('app.services.external_function_executor.RESTRICTED_PYTHON_AVAILABLE', False)
    async def test_execute_functions_restricted_python_unavailable(self, executor, sample_context):
        """Test handling when RestrictedPython is not available"""
        config = Mock()
        config.external_functions = [Mock()]

        result = await executor.execute_functions(config, sample_context)
        assert result == {}

    def test_get_metrics(self, executor):
        """Test metrics reporting"""
        # Initialize some test values
        executor.execution_count = 10
        executor.error_count = 2

        with patch('app.services.external_function_executor.settings') as mock_settings:
            mock_settings.ENABLE_EXTERNAL_FUNCTIONS = True
            mock_settings.EXTERNAL_FUNCTION_MAX_MEMORY_MB = 128
            mock_settings.EXTERNAL_FUNCTION_TIMEOUT = 10

            metrics = executor.get_metrics()

            assert metrics["execution_count"] == 10
            assert metrics["error_count"] == 2
            assert metrics["success_rate"] == 10/12  # 10 successes out of 12 total
            assert metrics["external_functions_enabled"]
            assert metrics["max_memory_mb"] == 128
            assert metrics["max_timeout"] == 10

    # Error Handling Tests

    @pytest.mark.asyncio
    async def test_load_function_code_missing_path(self, executor):
        """Test error handling for missing function path"""
        config = ExternalFunctionConfig(
            name="test", function_name="test", function_path="",
            file_path="", parameters={}, timeout=5, memory_limit_mb=32
        )

        with pytest.raises(ExternalFunctionExecutionError, match="Function path is required"):
            await executor.load_function_code(config)

    @pytest.mark.asyncio
    async def test_execute_single_function_validation_error(self, executor, sample_context):
        """Test handling of validation errors"""
        invalid_config = ExternalFunctionConfig(
            name="test", function_name="123invalid", function_path="../unsafe",
            file_path="../unsafe", parameters={}, timeout=5, memory_limit_mb=32
        )

        with pytest.raises(ExternalFunctionExecutionError):
            await executor.execute_single_function(
                invalid_config, sample_context, asyncio.Semaphore(1)
            )


class TestExternalFunctionSecurityScenarios:
    """Test security scenarios and attack vectors"""

    @pytest.fixture
    def executor(self):
        return ExternalFunctionExecutor()

    def test_sandbox_escape_attempts(self, executor):
        """Test various sandbox escape attempts are blocked"""
        escape_attempts = [
            # File system access
            "def test(): open('/etc/passwd', 'r')",
            "def test(): __import__('os').system('ls')",

            # Process spawning
            "def test(): __import__('subprocess').call(['ls'])",

            # Network access
            "def test(): __import__('socket').socket()",
            "def test(): __import__('urllib').request.urlopen('http://evil.com')",

            # Dynamic execution
            "def test(): exec('import os')",
            "def test(): eval('__import__(\"os\")')",

            # Introspection
            "def test(): globals()",
            "def test(): locals()",
            "def test(): vars()",
        ]

        config = ExternalFunctionConfig(
            name="test", function_name="test", function_path="safe.py",
            file_path="safe.py", parameters={}, timeout=5, memory_limit_mb=32
        )

        for malicious_code in escape_attempts:
            with pytest.raises(SecurityError, match="Prohibited code pattern detected"):
                executor._validate_function_code(malicious_code, config)

    def test_resource_exhaustion_protection(self, executor):
        """Test protection against resource exhaustion attacks"""
        # Code that could cause infinite loops or memory exhaustion
        exhaustion_attempts = [
            # Very long code
            "def test(): pass\n" + "x = 1\n" * 10000,

            # Missing required function (should fail validation)
            "def wrong_name(): pass",
        ]

        config = ExternalFunctionConfig(
            name="test", function_name="test", function_path="safe.py",
            file_path="safe.py", parameters={}, timeout=5, memory_limit_mb=32
        )

        # Test code length limit
        with pytest.raises(SecurityError, match="Function code too long"):
            executor._validate_function_code(exhaustion_attempts[0], config)

        # Test function name requirement
        with pytest.raises(SecurityError, match="Required function 'test' not found"):
            executor._validate_function_code(exhaustion_attempts[1], config)

    @patch('app.services.external_function_executor.settings')
    def test_storage_path_injection(self, mock_settings, executor):
        """Test protection against storage path injection attacks"""
        mock_settings.EXTERNAL_FUNCTIONS_STORAGE = "/secure/storage"

        malicious_paths = [
            "../../../etc/passwd",
            "/etc/passwd",
            "user/../../sensitive.py",
            "user/../admin/secret.py",
            "user\\..\\..\\windows\\system32",  # Windows-style paths
        ]

        for malicious_path in malicious_paths:
            config = ExternalFunctionConfig(
                name="test", function_name="test", function_path=malicious_path,
                file_path=malicious_path, parameters={}, timeout=5, memory_limit_mb=32
            )

            # Should fail validation before even attempting to load
            with pytest.raises(SecurityError):
                executor.validate_function_config(config)
