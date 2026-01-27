"""
Enhanced Sandboxing for Custom Python Scripts
Adds additional security layers to the existing RestrictedPython implementation
"""
import asyncio
import logging
import os
import tempfile
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import psutil

import docker
from app.errors import ExternalFunctionExecutionError, SecurityError

logger = logging.getLogger(__name__)
from app.utils.logging_utils import log_exception, log_info, log_warning

if TYPE_CHECKING:
    from app.services.external_function_executor import ExternalFunctionExecutor


class EnhancedSandbox:
    """
    Enhanced sandboxing environment with multiple isolation layers

    Security Layers:
    1. RestrictedPython (existing)
    2. Process isolation with cgroups
    3. Docker container isolation (optional)
    4. Network isolation
    5. File system isolation
    """

    def __init__(self):
        self.docker_available = self._check_docker_availability()
        self.cgroups_available = self._check_cgroups_availability()

        # Enhanced security limits
        self.DEFAULT_LIMITS = {
            'memory_mb': 64,          # 64MB max memory
            'cpu_time_seconds': 5,    # 5 seconds max CPU
            'wall_time_seconds': 10,  # 10 seconds max wall time
            'max_processes': 1,       # Single process only
            'max_file_size': 1024,    # 1KB max file creation
            'network_access': False,  # No network by default
            'file_write_access': False, # No file writes by default
        }

    def _check_docker_availability(self) -> bool:
        """Check if Docker is available for container isolation"""
        try:
            client = docker.from_env()
            client.ping()
            log_info("Docker available for container-based sandboxing")
            return True
        except Exception:
            log_warning("Docker not available - using process-based sandboxing only")
            return False

    def _check_cgroups_availability(self) -> bool:
        """Check if cgroups v2 is available for resource control"""
        try:
            return os.path.exists('/sys/fs/cgroup/cgroup.controllers')
        except Exception:
            return False

    async def execute_script_safe(
        self,
        script_content: str,
        function_name: str,
        input_data: dict[str, Any],
        limits: dict[str, Any] | None = None
    ) -> Any:
        """
        Execute custom script with maximum security isolation

        Args:
            script_content: Python code to execute
            function_name: Name of function to call
            input_data: Data to pass to the function
            limits: Resource limits override

        Returns:
            Function execution result

        Raises:
            SecurityError: If security validation fails
            ExternalFunctionExecutionError: If execution fails
        """
        effective_limits = {**self.DEFAULT_LIMITS, **(limits or {})}

        # Choose isolation method based on availability
        if self.docker_available and effective_limits.get('use_docker', False):
            return await self._execute_in_docker(
                script_content, function_name, input_data, effective_limits
            )
        if self.cgroups_available:
            return await self._execute_with_cgroups(
                script_content, function_name, input_data, effective_limits
            )
        return await self._execute_with_process_limits(
            script_content, function_name, input_data, effective_limits
        )

    async def _execute_in_docker(
        self,
        script_content: str,
        function_name: str,
        input_data: dict[str, Any],
        limits: dict[str, Any]
    ) -> Any:
        """
        Execute script in isolated Docker container
        Maximum security but higher overhead
        """
        try:
            client = docker.from_env()

            # Create temporary directory for script
            with tempfile.TemporaryDirectory() as temp_dir:
                script_path = os.path.join(temp_dir, 'user_script.py')
                runner_path = os.path.join(temp_dir, 'runner.py')
                input_path = os.path.join(temp_dir, 'input.json')
                output_path = os.path.join(temp_dir, 'output.json')

                # Write script and runner
                self._write_script_files(
                    script_content, function_name, input_data,
                    script_path, runner_path, input_path
                )

                # Container configuration
                container_config = {
                    'image': 'python:3.11-alpine',  # Minimal Python image
                    'command': ['python', '/sandbox/runner.py'],
                    'volumes': {temp_dir: {'bind': '/sandbox', 'mode': 'ro'}},
                    'mem_limit': f"{limits['memory_mb']}m",
                    'memswap_limit': f"{limits['memory_mb']}m",  # No swap
                    'cpu_period': 100000,  # 0.1 second
                    'cpu_quota': limits['cpu_time_seconds'] * 1000,  # CPU limit
                    'network_disabled': not limits['network_access'],
                    'read_only': True,  # Read-only filesystem
                    'security_opt': ['no-new-privileges:true'],
                    'cap_drop': ['ALL'],  # Drop all capabilities
                    'user': 'nobody',  # Non-root user
                    'pids_limit': limits['max_processes'],
                }

                # Run container with timeout
                try:
                    container = client.containers.run(
                        detach=True,
                        **container_config
                    )

                    # Wait for completion with timeout
                    result = container.wait(timeout=limits['wall_time_seconds'])

                    # Get logs and cleanup
                    logs = container.logs().decode('utf-8')
                    container.remove(force=True)

                    if result['StatusCode'] != 0:
                        raise ExternalFunctionExecutionError(f"Container execution failed: {logs}")

                    # Read output
                    if os.path.exists(output_path):
                        import json
                        with open(output_path) as f:
                            return json.load(f)
                    else:
                        raise ExternalFunctionExecutionError("No output generated")

                except docker.errors.ContainerError as e:
                    raise ExternalFunctionExecutionError(f"Container error: {e}")
                except Exception as e:
                    raise ExternalFunctionExecutionError(f"Docker execution failed: {e}")

        except Exception as e:
            log_exception(f"Docker sandbox execution failed: {e}")
            raise SecurityError(f"Docker sandbox failed: {e}")

    async def _execute_with_cgroups(
        self,
        script_content: str,
        function_name: str,
        input_data: dict[str, Any],
        limits: dict[str, Any]
    ) -> Any:
        """
        Execute script with cgroups v2 resource control
        Good security with lower overhead than Docker
        """
        try:
            # Create temporary cgroup
            cgroup_name = f"signal_service_sandbox_{int(time.time())}"

            with self._cgroup_context(cgroup_name, limits):
                # Execute in subprocess with cgroup limits
                return await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._execute_in_cgroup,
                    script_content, function_name, input_data,
                    cgroup_name, limits
                )

        except Exception as e:
            log_exception(f"Cgroups sandbox execution failed: {e}")
            raise SecurityError(f"Cgroups sandbox failed: {e}")

    @contextmanager
    def _cgroup_context(self, cgroup_name: str, limits: dict[str, Any]):
        """Context manager for cgroup creation and cleanup"""
        cgroup_path = f"/sys/fs/cgroup/{cgroup_name}"

        try:
            # Create cgroup
            os.makedirs(cgroup_path, exist_ok=True)

            # Set memory limit
            memory_bytes = limits['memory_mb'] * 1024 * 1024
            with open(f"{cgroup_path}/memory.max", 'w') as f:
                f.write(str(memory_bytes))

            # Set CPU limit
            with open(f"{cgroup_path}/cpu.max", 'w') as f:
                cpu_quota = limits['cpu_time_seconds'] * 100000  # microseconds
                f.write(f"{cpu_quota} 100000")

            # Set process limit
            with open(f"{cgroup_path}/pids.max", 'w') as f:
                f.write(str(limits['max_processes']))

            yield cgroup_path

        finally:
            # Cleanup cgroup
            try:
                if os.path.exists(cgroup_path):
                    os.rmdir(cgroup_path)
            except Exception as e:
                log_warning(f"Failed to cleanup cgroup {cgroup_name}: {e}")

    def _execute_in_cgroup(
        self,
        script_content: str,
        function_name: str,
        input_data: dict[str, Any],
        cgroup_name: str,
        limits: dict[str, Any]
    ) -> Any:
        """Execute script in cgroup with resource limits"""
        try:
            # Move current process to cgroup
            cgroup_path = f"/sys/fs/cgroup/{cgroup_name}"
            with open(f"{cgroup_path}/cgroup.procs", 'w') as f:
                f.write(str(os.getpid()))

            # Execute with existing RestrictedPython logic
            from app.schemas.config_schema import ExternalFunctionConfig
            from app.services.external_function_executor import ExternalFunctionExecutor
            executor = ExternalFunctionExecutor()

            # Create proper config from schema
            config = ExternalFunctionConfig(
                name=function_name,
                file_path="<inline>",  # Indicates inline script execution
                function_name=function_name,
                timeout=limits['wall_time_seconds'],
                memory_limit_mb=limits['memory_mb'],
                parameters=input_data
            )

            # Compile and execute
            compiled_code = executor.compile_function_safely(script_content, config)
            execution_context = {'tick_data': input_data, 'parameters': {}}
            execution_context.update(executor.prepare_execution_context(
                execution_context, config
            ))

            # Execute the code
            exec(compiled_code, execution_context)

            if function_name in execution_context:
                function = execution_context[function_name]
                return function(input_data, {})
            raise ExternalFunctionExecutionError(f"Function {function_name} not found")

        except Exception as e:
            raise ExternalFunctionExecutionError(f"Cgroup execution failed: {e}")

    async def _execute_with_process_limits(
        self,
        script_content: str,
        function_name: str,
        input_data: dict[str, Any],
        limits: dict[str, Any]
    ) -> Any:
        """
        Fallback execution with basic process limits
        Uses existing ExternalFunctionExecutor with enhancements
        """
        try:
            # Enhanced process monitoring
            start_time = time.time()

            # Execute with existing infrastructure but monitor more closely
            from app.services.external_function_executor import ExternalFunctionExecutor
            executor = ExternalFunctionExecutor()

            # Create enhanced config
            class EnhancedMockConfig:
                def __init__(self):
                    self.function_name = function_name
                    self.timeout = limits['wall_time_seconds']
                    self.memory_limit_mb = limits['memory_mb']
                    self.parameters = input_data
                    self.function_path = "memory://enhanced_sandbox"

            config = EnhancedMockConfig()

            # Validate and compile
            self._validate_enhanced_script(script_content, limits)
            compiled_code = executor.compile_function_safely(script_content, config)

            # Execute with monitoring
            result = await self._execute_with_monitoring(
                compiled_code, function_name, input_data, limits, executor
            )

            execution_time = time.time() - start_time
            log_info(f"Enhanced sandbox execution completed in {execution_time:.3f}s")

            return result

        except Exception as e:
            log_exception(f"Enhanced process execution failed: {e}")
            raise ExternalFunctionExecutionError(f"Enhanced execution failed: {e}")

    def _validate_enhanced_script(self, script_content: str, limits: dict[str, Any]):
        """Enhanced script validation with additional checks"""
        # Extended prohibited patterns
        enhanced_prohibited = [
            'import threading', 'import multiprocessing', 'import asyncio',
            'import time', 'import random', 'import json', 'import pickle',
            'import base64', 'import zlib', 'import gzip', 'import hashlib',
            'while True:', 'for i in range(999', 'range(10000',
            'sleep(', 'time.', 'os.', 'sys.', '__builtins__',
            'compile(', 'memoryview(', 'bytearray(',
        ]

        script_lower = script_content.lower()
        for pattern in enhanced_prohibited:
            if pattern.lower() in script_lower:
                raise SecurityError(f"Enhanced: Prohibited pattern detected: {pattern}")

        # Check for complexity limits
        lines = script_content.split('\n')
        if len(lines) > 100:
            raise SecurityError("Script too complex: Maximum 100 lines allowed")

        # Check for nested loops (potential for infinite execution)
        indent_levels = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(('for ', 'while ')):
                indent = len(line) - len(line.lstrip())
                indent_levels.append(indent)

                # Check for nested loops
                nested_count = sum(1 for level in indent_levels if level < indent)
                if nested_count >= 2:
                    raise SecurityError("Nested loops not allowed (max depth: 2)")

    async def _execute_with_monitoring(
        self,
        compiled_code: Any,
        function_name: str,
        input_data: dict[str, Any],
        limits: dict[str, Any],
        executor: 'ExternalFunctionExecutor'
    ) -> Any:
        """Execute with real-time resource monitoring"""
        try:
            # Start monitoring process
            monitor_task = asyncio.create_task(
                self._monitor_execution(limits)
            )

            # Execute the function
            try:
                # Prepare restricted execution context
                execution_context = {
                    'tick_data': input_data,
                    'parameters': {},
                    '__builtins__': {
                        'len': len, 'str': str, 'int': int, 'float': float,
                        'min': min, 'max': max, 'abs': abs, 'round': round,
                        'sum': sum, 'sorted': sorted, 'list': list, 'dict': dict
                    }
                }

                # Execute the code
                exec(compiled_code, execution_context)

                # Call the function
                if function_name in execution_context:
                    function = execution_context[function_name]
                    return function(input_data, {})
                raise ExternalFunctionExecutionError(f"Function {function_name} not found")

            finally:
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    # Expected after explicit cancellation - monitor task stopped
                    logger.debug("Monitor task cancelled successfully")

        except Exception as e:
            raise ExternalFunctionExecutionError(f"Monitored execution failed: {e}")

    async def _monitor_execution(self, limits: dict[str, Any]):
        """Monitor resource usage during execution"""
        start_time = time.time()
        process = psutil.Process()

        try:
            while True:
                await asyncio.sleep(0.1)  # Check every 100ms

                # Check wall time
                elapsed = time.time() - start_time
                if elapsed > limits['wall_time_seconds']:
                    raise ExternalFunctionExecutionError(
                        f"Wall time limit exceeded: {elapsed}s > {limits['wall_time_seconds']}s"
                    )

                # Check memory usage
                memory_mb = process.memory_info().rss / (1024 * 1024)
                if memory_mb > limits['memory_mb']:
                    raise ExternalFunctionExecutionError(
                        f"Memory limit exceeded: {memory_mb:.1f}MB > {limits['memory_mb']}MB"
                    )

                # Check process count
                children = process.children(recursive=True)
                if len(children) >= limits['max_processes']:
                    raise ExternalFunctionExecutionError(
                        f"Process limit exceeded: {len(children)} >= {limits['max_processes']}"
                    )

        except asyncio.CancelledError:
            # Monitor task cancelled - execution stopped
            logger.debug("Execution monitor cancelled")

    def _write_script_files(
        self,
        script_content: str,
        function_name: str,
        input_data: dict[str, Any],
        script_path: str,
        runner_path: str,
        input_path: str
    ):
        """Write script files for containerized execution"""
        import json

        # Write user script
        with open(script_path, 'w') as f:
            f.write(script_content)

        # Write input data
        with open(input_path, 'w') as f:
            json.dump(input_data, f)

        # Write runner script
        runner_code = f"""
import json
import sys
sys.path.append('/sandbox')

try:
    # Load user script
    from user_script import {function_name}

    # Load input data
    with open('/sandbox/input.json', 'r') as f:
        input_data = json.load(f)

    # Execute function
    result = {function_name}(input_data, {{}})

    # Write output
    with open('/sandbox/output.json', 'w') as f:
        json.dump(result, f)

except Exception as e:
    # Write error
    with open('/sandbox/output.json', 'w') as f:
        json.dump({{"error": str(e)}}, f)
    sys.exit(1)
"""

        with open(runner_path, 'w') as f:
            f.write(runner_code)

    def get_security_report(self) -> dict[str, Any]:
        """Generate security capabilities report"""
        return {
            "sandbox_layers": {
                "restricted_python": True,
                "process_isolation": True,
                "cgroups_v2": self.cgroups_available,
                "docker_containers": self.docker_available,
            },
            "resource_limits": self.DEFAULT_LIMITS,
            "security_features": {
                "code_validation": True,
                "import_blocking": True,
                "memory_limiting": True,
                "cpu_limiting": True,
                "network_isolation": self.docker_available,
                "filesystem_isolation": True,
                "process_limiting": True,
                "real_time_monitoring": True,
            },
            "recommendations": self._get_security_recommendations()
        }

    def _get_security_recommendations(self) -> list[str]:
        """Get security enhancement recommendations"""
        recommendations = []

        if not self.docker_available:
            recommendations.append("Install Docker for maximum container isolation")

        if not self.cgroups_available:
            recommendations.append("Enable cgroups v2 for better resource control")

        recommendations.extend([
            "Consider network namespace isolation",
            "Implement code signing for function verification",
            "Add audit logging for all executions",
            "Set up alerts for resource limit violations"
        ])

        return recommendations


# Singleton instance
_enhanced_sandbox = None

def get_enhanced_sandbox() -> EnhancedSandbox:
    """Get singleton enhanced sandbox instance"""
    global _enhanced_sandbox
    if _enhanced_sandbox is None:
        _enhanced_sandbox = EnhancedSandbox()
    return _enhanced_sandbox
