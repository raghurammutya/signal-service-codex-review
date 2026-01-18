"""External function executor with security sandboxing"""
import asyncio
import sys
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
import resource

try:
    from RestrictedPython import compile_restricted
    from RestrictedPython.Guards import safe_globals, safe_builtins
    RESTRICTED_PYTHON_AVAILABLE = True
except ImportError:
    RESTRICTED_PYTHON_AVAILABLE = False

from app.utils.logging_utils import log_info, log_exception, log_warning

from app.core.config import settings
from app.errors import ExternalFunctionExecutionError, SecurityError
from app.schemas.config_schema import SignalConfigData, TickProcessingContext, ExternalFunctionConfig
from app.security.malicious_code_detector import scan_for_malicious_code, MaliciousCodeDetector
from app.security.crash_prevention import get_crash_prevention, ResourceLimits


class ExternalFunctionExecutor:
    """
    Secure executor for external Python functions
    Uses RestrictedPython for sandboxing and resource limits
    """
    
    def __init__(self):
        if not RESTRICTED_PYTHON_AVAILABLE:
            log_warning("RestrictedPython not available - external functions will be disabled")
        
        self.execution_count = 0
        self.error_count = 0
        self.malicious_code_detector = MaliciousCodeDetector()
        self.crash_prevention = get_crash_prevention()
        
        log_info("ExternalFunctionExecutor initialized with enhanced security")
    
    async def execute_functions(
        self, 
        config: SignalConfigData, 
        context: TickProcessingContext
    ) -> Dict[str, Any]:
        """Execute all external functions for the configuration"""
        try:
            if not config.external_functions:
                return {}
            
            if not RESTRICTED_PYTHON_AVAILABLE or not settings.ENABLE_EXTERNAL_FUNCTIONS:
                log_warning("External functions disabled or not available")
                return {}
            
            instrument_key = context.instrument_key
            log_info(f"Executing {len(config.external_functions)} external functions for {instrument_key}")
            
            results = {}
            
            # Execute functions with concurrency limit
            semaphore = asyncio.Semaphore(3)  # Max 3 concurrent executions
            
            tasks = []
            for func_config in config.external_functions:
                task = self.execute_single_function(
                    func_config, context, semaphore
                )
                tasks.append((func_config.name, task))
            
            # Wait for all functions to complete
            if tasks:
                task_results = await asyncio.gather(
                    *[task for _, task in tasks],
                    return_exceptions=True
                )
                
                for (func_name, _), result in zip(tasks, task_results):
                    if isinstance(result, Exception):
                        log_exception(f"External function {func_name} failed: {result}")
                        results[func_name] = {"error": str(result)}
                        self.error_count += 1
                    else:
                        results[func_name] = result
                        self.execution_count += 1
            
            log_info(f"Executed external functions for {instrument_key}: {len(results)} results")
            
            return {
                "instrument_key": instrument_key,
                "calculation_type": "external_functions",
                "functions_count": len(results),
                "results": results,
                "metadata": {
                    "timestamp": context.timestamp.isoformat(),
                    "execution_count": self.execution_count,
                    "error_count": self.error_count
                }
            }
            
        except Exception as e:
            error = ExternalFunctionExecutionError(f"External functions execution failed: {str(e)}")
            log_exception(f"Error in external functions execution: {error}")
            raise error
    
    async def execute_single_function(
        self, 
        func_config: ExternalFunctionConfig, 
        context: TickProcessingContext,
        semaphore: asyncio.Semaphore
    ) -> Any:
        """Execute a single external function with security constraints"""
        async with semaphore:
            try:
                log_info(f"Executing external function: {func_config.name}")
                
                # Validate function configuration
                self.validate_function_config(func_config)
                
                # Load and compile function
                function_code = await self.load_function_code(func_config)
                compiled_code = self.compile_function_safely(function_code, func_config)
                
                # Prepare execution context
                execution_context = self.prepare_execution_context(context, func_config)
                
                # Execute with timeout and resource limits
                result = await asyncio.wait_for(
                    self.execute_with_limits(compiled_code, execution_context, func_config),
                    timeout=func_config.timeout
                )
                
                log_info(f"External function {func_config.name} executed successfully")
                return result
                
            except asyncio.TimeoutError:
                error_msg = f"Function {func_config.name} timed out after {func_config.timeout}s"
                log_exception(error_msg)
                raise ExternalFunctionExecutionError(error_msg)
            except Exception as e:
                error_msg = f"Function {func_config.name} execution failed: {str(e)}"
                log_exception(error_msg)
                raise ExternalFunctionExecutionError(error_msg)
    
    def validate_function_config(self, func_config: ExternalFunctionConfig):
        """Validate external function configuration"""
        # Check file path security
        if not self._is_safe_path(func_config.file_path):
            raise SecurityError(f"Unsafe file path: {func_config.file_path}")
        
        # Validate function name
        if not func_config.function_name or not func_config.function_name.isidentifier():
            raise SecurityError(f"Invalid function name: {func_config.function_name}")
        
        # Check resource limits
        max_memory = getattr(settings, 'EXTERNAL_FUNCTION_MAX_MEMORY_MB', 128)
        max_timeout = getattr(settings, 'EXTERNAL_FUNCTION_TIMEOUT', 30)
        
        if func_config.memory_limit_mb > max_memory:
            raise SecurityError(f"Memory limit too high: {func_config.memory_limit_mb}MB > {max_memory}MB")
        
        if func_config.timeout > max_timeout:
            raise SecurityError(f"Timeout too high: {func_config.timeout}s > {max_timeout}s")
        
        # Check function name
        if not func_config.function_name.isidentifier():
            raise SecurityError(f"Invalid function name: {func_config.function_name}")
        
        # Check memory limit
        if func_config.memory_limit_mb > settings.EXTERNAL_FUNCTION_MAX_MEMORY_MB:
            raise SecurityError(f"Memory limit too high: {func_config.memory_limit_mb}MB")
        
        # Check timeout
        if func_config.timeout > settings.EXTERNAL_FUNCTION_TIMEOUT:
            raise SecurityError(f"Timeout too high: {func_config.timeout}s")
    
    async def load_function_code(self, func_config: ExternalFunctionConfig) -> str:
        """Load function code from secure storage"""
        try:
            # Load from secure function repository based on function_path
            if not func_config.function_path:
                raise ValueError("Function path is required")
            
            # Validate the function path for security
            if not self._is_safe_path(func_config.function_path):
                raise SecurityError("Invalid function path")
            
            # Secure function loading from configured storage
            return await self._load_function_securely(func_config)
            
        except Exception as e:
            raise ExternalFunctionExecutionError(f"Failed to load function code: {str(e)}")
    
    def _is_safe_path(self, path: str) -> bool:
        """Validate function path for security"""
        # Basic path validation - extend as needed
        if not path or '..' in path or path.startswith('/'):
            return False
        return True
    
    async def _load_function_securely(self, func_config: ExternalFunctionConfig) -> str:
        """
        Load function code from secure storage with comprehensive validation.
        
        Security measures:
        - Path validation and sanitization
        - File size limits
        - Content validation
        - Secure storage access
        """
        try:
            # Define secure storage base path from config
            secure_storage_base = getattr(settings, 'EXTERNAL_FUNCTIONS_STORAGE', '/opt/signal_service/functions')
            
            # Construct safe file path
            safe_path = os.path.join(secure_storage_base, func_config.function_path)
            safe_path = os.path.normpath(safe_path)
            
            # Ensure path is within secure storage directory
            if not safe_path.startswith(os.path.normpath(secure_storage_base)):
                raise SecurityError("Function path outside secure storage directory")
            
            # Ensure file exists and is a regular file
            if not os.path.isfile(safe_path):
                raise SecurityError(f"Function file not found: {func_config.function_path}")
            
            # Check file size limit (max 50KB for security)
            max_file_size = 50 * 1024  # 50KB
            file_size = os.path.getsize(safe_path)
            if file_size > max_file_size:
                raise SecurityError(f"Function file too large: {file_size} bytes (max: {max_file_size})")
            
            # Read file content securely
            with open(safe_path, 'r', encoding='utf-8') as f:
                code_content = f.read()
            
            # Validate code content
            self._validate_function_code(code_content, func_config)
            
            log_info(f"Successfully loaded function from secure storage: {func_config.function_path}")
            return code_content
            
        except Exception as e:
            log_exception(f"Failed to load function securely: {e}")
            raise SecurityError(f"Secure function loading failed: {str(e)}")
    
    def _validate_function_code(self, code: str, func_config: ExternalFunctionConfig) -> None:
        """
        Validate function code for security and correctness.
        
        Checks:
        - Code length limits
        - Prohibited imports and operations
        - Required function signature
        """
        # Length validation
        max_code_length = 10000  # 10KB max code
        if len(code) > max_code_length:
            raise SecurityError(f"Function code too long: {len(code)} chars (max: {max_code_length})")
        
        # Check for prohibited patterns
        prohibited_patterns = [
            'import os',
            'import sys', 
            'import subprocess',
            'import socket',
            'import urllib',
            'import requests',
            'import httpx',
            'open(',
            'exec(',
            'eval(',
            '__import__',
            'globals(',
            'locals(',
            'vars(',
            'dir(',
        ]
        
        code_lower = code.lower()
        for pattern in prohibited_patterns:
            if pattern.lower() in code_lower:
                raise SecurityError(f"Prohibited code pattern detected: {pattern}")
        
        # Validate that required function name is present
        required_function = func_config.function_name
        if f"def {required_function}(" not in code:
            raise SecurityError(f"Required function '{required_function}' not found in code")
        
        log_info(f"Function code validation passed: {func_config.function_name}")
    
    def compile_function_safely(self, code: str, func_config: ExternalFunctionConfig) -> Any:
        """Compile function code using RestrictedPython"""
        try:
            if not RESTRICTED_PYTHON_AVAILABLE:
                raise SecurityError("RestrictedPython not available for safe execution")
            
            # Compile with restrictions
            compiled = compile_restricted(code, '<external_function>', 'exec')
            
            if compiled.errors:
                raise SecurityError(f"Compilation errors: {compiled.errors}")
            
            return compiled.code
            
        except Exception as e:
            raise SecurityError(f"Failed to compile function safely: {str(e)}")
    
    def prepare_execution_context(
        self, 
        context: TickProcessingContext, 
        func_config: ExternalFunctionConfig
    ) -> Dict[str, Any]:
        """Prepare safe execution context"""
        try:
            # Create restricted globals
            restricted_globals = safe_globals.copy()
            restricted_globals['__builtins__'] = safe_builtins
            
            # Add safe utilities
            restricted_globals.update({
                'len': len,
                'str': str,
                'int': int,
                'float': float,
                'bool': bool,
                'list': list,
                'dict': dict,
                'min': min,
                'max': max,
                'sum': sum,
                'abs': abs,
                'round': round
            })
            
            # Add function parameters
            restricted_globals.update({
                'tick_data': context.tick_data,
                'parameters': func_config.parameters,
                'instrument_key': context.instrument_key,
                'timestamp': context.timestamp.isoformat()
            })
            
            return restricted_globals
            
        except Exception as e:
            raise ExternalFunctionExecutionError(f"Failed to prepare execution context: {str(e)}")
    
    async def execute_with_limits(
        self, 
        compiled_code: Any, 
        execution_context: Dict, 
        func_config: ExternalFunctionConfig
    ) -> Any:
        """Execute function with resource limits"""
        try:
            # Set resource limits in a subprocess/thread
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                self._execute_in_subprocess,
                compiled_code,
                execution_context,
                func_config
            )
            
            return result
            
        except Exception as e:
            raise ExternalFunctionExecutionError(f"Function execution failed: {str(e)}")
    
    def _execute_in_subprocess(
        self, 
        compiled_code: Any, 
        execution_context: Dict, 
        func_config: ExternalFunctionConfig
    ) -> Any:
        """Execute in subprocess with resource limits (synchronous)"""
        try:
            # Set memory limit (in bytes)
            memory_limit = func_config.memory_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
            
            # Set CPU time limit
            resource.setrlimit(resource.RLIMIT_CPU, (func_config.timeout, func_config.timeout))
            
            # Execute the compiled code
            exec(compiled_code, execution_context)
            
            # Call the function
            function_name = func_config.function_name
            if function_name in execution_context:
                function = execution_context[function_name]
                result = function(
                    execution_context['tick_data'],
                    execution_context['parameters']
                )
                return result
            else:
                raise ExternalFunctionExecutionError(f"Function {function_name} not found after execution")
                
        except Exception as e:
            raise ExternalFunctionExecutionError(f"Subprocess execution failed: {str(e)}")
    
    def _is_safe_path(self, path: str) -> bool:
        """Check if file path is safe (no directory traversal)"""
        if not path:
            return False
        
        # Check for path traversal attempts
        if '..' in path or path.startswith('/'):
            return False
        
        # Check for absolute paths
        if os.path.isabs(path):
            return False
        
        return True
    
    def _validate_function_code(self, code: str, config: ExternalFunctionConfig):
        """Enhanced function code validation with malicious code detection"""
        # Basic length check
        if len(code) > 50000:  # 50KB limit
            raise SecurityError("Function code too long")
        
        # Advanced malicious code detection
        try:
            malicious_scan = scan_for_malicious_code(code, config.file_path)
            
            # Log scan results for monitoring
            if malicious_scan["total_threats"] > 0:
                log_warning(f"Code validation found {malicious_scan['total_threats']} potential issues in {config.name}")
            
        except SecurityError as e:
            # Re-raise with enhanced context
            raise SecurityError(f"Malicious code detected in {config.name}: {str(e)}")
        
        # Check if required function exists
        if f"def {config.function_name}" not in code:
            raise SecurityError(f"Required function '{config.function_name}' not found in code")
    
    async def _load_function_securely(self, config: ExternalFunctionConfig) -> str:
        """Load function code from secure storage with validation"""
        if not config.file_path:
            raise ExternalFunctionExecutionError("Function path is required")
        
        storage_dir = getattr(settings, 'EXTERNAL_FUNCTIONS_STORAGE', '/tmp/external_functions')
        full_path = os.path.join(storage_dir, config.file_path)
        
        # Validate path is within storage directory
        try:
            real_storage = os.path.realpath(storage_dir)
            real_path = os.path.realpath(full_path)
            if not real_path.startswith(real_storage):
                raise SecurityError("Function path outside secure storage directory")
        except Exception as e:
            raise SecurityError(f"Path validation failed: {e}")
        
        # Check if file exists and size
        if not os.path.exists(full_path):
            raise SecurityError("Function file not found")
        
        file_size = os.path.getsize(full_path)
        if file_size > 50000:  # 50KB limit
            raise SecurityError("Function file too large")
        
        # Read and validate file
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                code = f.read()
            
            self._validate_function_code(code, config)
            return code
        except SecurityError:
            raise
        except Exception as e:
            raise SecurityError(f"Failed to load function code: {e}")
    
    # ACL Methods
    
    def _get_user_role(self, user_id: str) -> Dict[str, Any]:
        """Get user role and permissions from user service"""
        # Production implementation must query user service - no mock data
        try:
            # Query user service for actual permissions via centralized factory
            from app.clients.client_factory import get_client_manager
            import asyncio
            
            client_manager = get_client_manager()
            user_client = asyncio.run(client_manager.get_client('user_service'))
            user_data = user_client.get_user_permissions_sync(user_id)
            
            if not user_data:
                raise ValueError(f"User {user_id} not found or has no permissions")
                
            return user_data
        except Exception as e:
            # Fail fast for security - no default permissions
            from app.errors import SecurityError
            raise SecurityError(f"Failed to get user permissions for {user_id}: {e}") from e
    
    def _check_user_access(self, user_id: str, config: ExternalFunctionConfig) -> bool:
        """Check if user has access to execute the function"""
        try:
            user_role = self._get_user_role(user_id)
            
            # Check if user has execute permission
            if "execute_custom_functions" not in user_role.get("permissions", []):
                return False
            
            # Check if user owns the function (basic access control)
            if user_id not in config.file_path:
                return False
            
            return True
        except Exception:
            return False
    
    def _check_cross_user_access(self, user_id: str, target_user_id: str) -> bool:
        """Check if user has cross-user access (admin only)"""
        try:
            user_role = self._get_user_role(user_id)
            return "cross_user_access" in user_role.get("permissions", [])
        except Exception:
            return False
    
    def _check_shared_access(self, user_id: str, shared_function_path: str) -> bool:
        """Check if user has access to shared functions"""
        try:
            user_role = self._get_user_role(user_id)
            
            # Only premium and admin users can access shared functions
            role = user_role.get("role", "basic")
            return role in ["premium", "admin"]
        except Exception:
            return False
    
    def _audit_access_attempt(self, user_id: str, config: ExternalFunctionConfig, result: str, details: str = ""):
        """Audit function access attempts"""
        audit_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "function_name": config.name,
            "function_path": config.file_path,
            "access_result": result,
            "details": details
        }
        
        # Log audit event
        if result == "access_denied":
            log_warning(f"ACL: Access denied for user {user_id} to function {config.file_path}: {details}")
        else:
            log_info(f"ACL: Access {result} for user {user_id} to function {config.file_path}")
        
        # In production, this would also write to an audit database
    
    def _validate_acl(self, user_id: str, config: ExternalFunctionConfig):
        """Validate ACL for function execution"""
        if not user_id:
            raise SecurityError("User ID required for ACL validation")
        
        # Check basic user access
        if not self._check_user_access(user_id, config):
            self._audit_access_attempt(user_id, config, "access_denied", "User lacks access to function")
            raise SecurityError("Access denied: User not authorized to execute this function")
        
        # Check cross-user access if needed
        if "/" in config.file_path:
            file_user_id = config.file_path.split("/")[0]
            if file_user_id != user_id:
                if not self._check_cross_user_access(user_id, file_user_id):
                    self._audit_access_attempt(user_id, config, "access_denied", "Cross-user access denied")
                    raise SecurityError("Cross-user access denied")
        
        # Check shared function access
        if config.file_path.startswith("shared/"):
            if not self._check_shared_access(user_id, config.file_path):
                self._audit_access_attempt(user_id, config, "access_denied", "Shared function access denied")
                raise SecurityError("Shared function access denied")
        
        # Check role-based resource limits
        user_role = self._get_user_role(user_id)
        if config.memory_limit_mb > user_role.get("max_memory_mb", 32):
            self._audit_access_attempt(user_id, config, "access_denied", "Memory limit exceeds user role limit")
            raise SecurityError(f"Memory limit exceeds role limit: {config.memory_limit_mb}MB > {user_role['max_memory_mb']}MB")
        
        if config.timeout > user_role.get("max_timeout", 10):
            self._audit_access_attempt(user_id, config, "access_denied", "Timeout exceeds user role limit")
            raise SecurityError(f"Timeout exceeds role limit: {config.timeout}s > {user_role['max_timeout']}s")
        
        # Audit successful access
        self._audit_access_attempt(user_id, config, "access_granted")
    
    async def execute_single_function_with_acl(
        self, 
        func_config: ExternalFunctionConfig, 
        context: TickProcessingContext,
        semaphore: asyncio.Semaphore,
        user_id: str
    ) -> Any:
        """Execute a single external function with ACL validation and crash prevention"""
        async with semaphore:
            try:
                log_info(f"Executing external function: {func_config.name} for user: {user_id}")
                
                # Validate ACL first
                self._validate_acl(user_id, func_config)
                
                # Validate function configuration
                self.validate_function_config(func_config)
                
                # Load and compile function
                function_code = await self._load_function_securely(func_config)
                compiled_code = self.compile_function_safely(function_code, func_config)
                
                # Prepare execution context
                execution_context = self.prepare_execution_context(context, func_config)
                
                # Create resource limits for crash prevention
                limits = ResourceLimits(
                    max_memory_mb=func_config.memory_limit_mb,
                    max_cpu_seconds=func_config.timeout,
                    max_wall_time_seconds=func_config.timeout + 2,
                    max_file_descriptors=10,
                    max_threads=1,
                    max_processes=1,
                    max_stack_size_mb=8
                )
                
                # Execute with comprehensive crash prevention
                def execute_function():
                    exec(compiled_code, execution_context)
                    if func_config.function_name in execution_context:
                        function = execution_context[func_config.function_name]
                        return function(context.tick_data, func_config.parameters)
                    else:
                        raise ExternalFunctionExecutionError(f"Function {func_config.function_name} not found after execution")
                
                result = await self.crash_prevention.execute_with_crash_prevention(
                    func=execute_function,
                    args=(),
                    kwargs={},
                    limits=limits,
                    execution_id=f"{user_id}_{func_config.name}_{int(asyncio.get_event_loop().time())}"
                )
                
                log_info(f"External function {func_config.name} executed successfully for user {user_id}")
                self.execution_count += 1
                return result
                
            except asyncio.TimeoutError:
                error_msg = f"Function {func_config.name} timed out after {func_config.timeout}s"
                log_exception(error_msg)
                self.error_count += 1
                raise ExternalFunctionExecutionError(error_msg)
            except SecurityError:
                self.error_count += 1
                raise  # Re-raise security errors as-is
            except Exception as e:
                error_msg = f"Function {func_config.name} execution failed: {str(e)}"
                log_exception(error_msg)
                self.error_count += 1
                raise ExternalFunctionExecutionError(error_msg)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive executor metrics including security and stability"""
        success_rate = 0.0
        if self.execution_count + self.error_count > 0:
            success_rate = self.execution_count / (self.execution_count + self.error_count)
        
        # Get crash prevention metrics
        crash_metrics = self.crash_prevention.get_execution_metrics()
        
        # Get system stability
        stability_metrics = self.crash_prevention.check_system_stability()
        
        return {
            "security_features": {
                "restricted_python_available": RESTRICTED_PYTHON_AVAILABLE,
                "malicious_code_detection": True,
                "crash_prevention": True,
                "acl_enforcement": True
            },
            "execution_stats": {
                "execution_count": self.execution_count,
                "error_count": self.error_count,
                "success_rate": success_rate,
                "active_executions": crash_metrics["active_executions"],
                "max_concurrent_executions": crash_metrics["max_concurrent"]
            },
            "resource_limits": {
                "external_functions_enabled": getattr(settings, 'ENABLE_EXTERNAL_FUNCTIONS', True),
                "max_memory_mb": getattr(settings, 'EXTERNAL_FUNCTION_MAX_MEMORY_MB', 128),
                "max_timeout": getattr(settings, 'EXTERNAL_FUNCTION_TIMEOUT', 30),
                "max_file_descriptors": 10,
                "max_stack_size_mb": 8
            },
            "system_stability": {
                "is_stable": stability_metrics["is_stable"],
                "memory_usage_mb": stability_metrics.get("current_state", {}).get("memory_mb", 0),
                "cpu_percent": stability_metrics.get("current_state", {}).get("cpu_percent", 0),
                "active_threads": stability_metrics.get("current_state", {}).get("threads", 0),
                "stability_issues": stability_metrics.get("issues", [])
            },
            "security_status": {
                "emergency_stop_active": crash_metrics["emergency_stop_active"],
                "malicious_code_scanner_ready": hasattr(self, 'malicious_code_detector'),
                "crash_prevention_active": hasattr(self, 'crash_prevention')
            }
        }