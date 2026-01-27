"""
System Crash Prevention for External Function Execution
Prevents code from causing system instability, resource exhaustion, or crashes
"""

import asyncio
import gc
import resource
import signal
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psutil

from app.errors import ExternalFunctionExecutionError
from app.utils.logging_utils import log_error, log_info, log_warning


@dataclass
class ResourceLimits:
    """Resource limits for safe execution"""
    max_memory_mb: int = 64
    max_cpu_seconds: int = 5
    max_wall_time_seconds: int = 10
    max_file_descriptors: int = 10
    max_threads: int = 1
    max_processes: int = 1
    max_stack_size_mb: int = 8


@dataclass
class SystemState:
    """Current system resource state"""
    memory_usage_mb: float
    cpu_percent: float
    active_threads: int
    open_files: int
    load_average: float
    timestamp: datetime


class CrashPrevention:
    """
    Comprehensive crash prevention system for external function execution

    Features:
    1. Resource monitoring and limiting
    2. Runaway process detection and termination
    3. Memory leak prevention
    4. Stack overflow protection
    5. Signal handling for graceful shutdown
    6. System stability monitoring
    """

    def __init__(self):
        self.active_executions = {}  # Track running executions
        self.system_baseline = None  # Baseline system metrics
        self.emergency_stop = threading.Event()
        self.resource_monitor = None
        self.max_concurrent_executions = 10

        # Setup signal handlers for emergency stops
        self._setup_signal_handlers()

        # Get system baseline
        self._establish_baseline()

        log_info("CrashPrevention system initialized")

    def _setup_signal_handlers(self):
        """Setup signal handlers for emergency shutdown"""
        def emergency_handler(signum, frame):
            log_error(f"Emergency signal {signum} received - stopping all executions")
            self.emergency_stop.set()
            self._terminate_all_executions()

        # Setup emergency signals (only in main thread)
        try:
            signal.signal(signal.SIGTERM, emergency_handler)
            signal.signal(signal.SIGINT, emergency_handler)
        except ValueError:
            # Not in main thread, signals won't work
            log_warning("Signal handlers not installed - not in main thread")

    def _establish_baseline(self):
        """Establish baseline system metrics"""
        try:
            process = psutil.Process()
            self.system_baseline = SystemState(
                memory_usage_mb=process.memory_info().rss / 1024 / 1024,
                cpu_percent=process.cpu_percent(),
                active_threads=threading.active_count(),
                open_files=len(process.open_files()),
                load_average=psutil.getloadavg()[0] if hasattr(psutil, 'getloadavg') else 0.0,
                timestamp=datetime.now()
            )
            log_info(f"System baseline established: {self.system_baseline.memory_usage_mb:.1f}MB memory, "
                    f"{self.system_baseline.active_threads} threads")
        except Exception as e:
            log_warning(f"Could not establish system baseline: {e}")
            # Set reasonable defaults
            self.system_baseline = SystemState(
                memory_usage_mb=100.0,
                cpu_percent=5.0,
                active_threads=1,
                open_files=10,
                load_average=0.5,
                timestamp=datetime.now()
            )

    @contextmanager
    def safe_execution_context(
        self,
        execution_id: str,
        limits: ResourceLimits,
        monitor_interval: float = 0.1
    ):
        """
        Create a safe execution context with comprehensive monitoring

        Args:
            execution_id: Unique identifier for this execution
            limits: Resource limits to enforce
            monitor_interval: How often to check resource usage (seconds)
        """
        if len(self.active_executions) >= self.max_concurrent_executions:
            raise ExternalFunctionExecutionError(
                f"Too many concurrent executions: {len(self.active_executions)}"
            )

        # Start monitoring
        monitor_stop_event = threading.Event()
        monitor_thread = threading.Thread(
            target=self._monitor_execution,
            args=(execution_id, limits, monitor_stop_event, monitor_interval)
        )

        try:
            # Set initial resource limits
            self._set_resource_limits(limits)

            # Track execution
            self.active_executions[execution_id] = {
                "start_time": datetime.now(),
                "limits": limits,
                "monitor_thread": monitor_thread,
                "stop_event": monitor_stop_event
            }

            # Start monitoring
            monitor_thread.start()

            log_info(f"Safe execution context started for {execution_id}")

            yield execution_id

        except Exception as e:
            log_error(f"Execution {execution_id} failed: {e}")
            raise

        finally:
            # Stop monitoring
            monitor_stop_event.set()
            if monitor_thread.is_alive():
                monitor_thread.join(timeout=1.0)

            # Cleanup execution tracking
            if execution_id in self.active_executions:
                del self.active_executions[execution_id]

            # Force garbage collection to free memory
            gc.collect()

            log_info(f"Safe execution context ended for {execution_id}")

    def _set_resource_limits(self, limits: ResourceLimits):
        """Set OS-level resource limits"""
        try:
            # Memory limit (virtual memory)
            memory_bytes = limits.max_memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))

            # CPU time limit
            resource.setrlimit(resource.RLIMIT_CPU, (limits.max_cpu_seconds, limits.max_cpu_seconds))

            # Stack size limit
            stack_bytes = limits.max_stack_size_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_STACK, (stack_bytes, stack_bytes))

            # File descriptor limit
            resource.setrlimit(resource.RLIMIT_NOFILE, (limits.max_file_descriptors, limits.max_file_descriptors))

            # Process limit (if available)
            try:
                resource.setrlimit(resource.RLIMIT_NPROC, (limits.max_processes, limits.max_processes))
            except (AttributeError, OSError) as e:
                # RLIMIT_NPROC not available on all systems
                log_info(f"Process limit (RLIMIT_NPROC) not set: {e} (this is normal on some systems)")

            log_info(f"Resource limits set: {limits.max_memory_mb}MB memory, {limits.max_cpu_seconds}s CPU")

        except Exception as e:
            log_warning(f"Could not set all resource limits: {e}")

    def _monitor_execution(
        self,
        execution_id: str,
        limits: ResourceLimits,
        stop_event: threading.Event,
        check_interval: float
    ):
        """Monitor execution for resource violations and system stability"""
        try:
            process = psutil.Process()
            start_time = time.time()

            while not stop_event.is_set() and not self.emergency_stop.is_set():
                try:
                    # Check wall time
                    elapsed_time = time.time() - start_time
                    if elapsed_time > limits.max_wall_time_seconds:
                        self._terminate_execution(execution_id, "Wall time limit exceeded")
                        break

                    # Check memory usage
                    memory_mb = process.memory_info().rss / 1024 / 1024
                    if memory_mb > limits.max_memory_mb:
                        self._terminate_execution(execution_id, f"Memory limit exceeded: {memory_mb:.1f}MB")
                        break

                    # Check CPU usage
                    cpu_percent = process.cpu_percent(interval=None)
                    if cpu_percent > 95.0:  # Sustained high CPU
                        log_warning(f"High CPU usage detected: {cpu_percent:.1f}%")

                    # Check thread count
                    thread_count = threading.active_count()
                    if thread_count > self.system_baseline.active_threads + limits.max_threads + 5:
                        self._terminate_execution(execution_id, f"Too many threads: {thread_count}")
                        break

                    # Check file descriptor count
                    try:
                        open_files = len(process.open_files())
                        if open_files > limits.max_file_descriptors:
                            self._terminate_execution(execution_id, f"Too many open files: {open_files}")
                            break
                    except psutil.AccessDenied:
                        pass  # Can't check on some systems

                    # Check system load
                    if hasattr(psutil, 'getloadavg'):
                        load_avg = psutil.getloadavg()[0]
                        if load_avg > 10.0:  # Very high system load
                            log_warning(f"High system load detected: {load_avg:.2f}")

                    # Check for runaway processes
                    children = process.children(recursive=True)
                    if len(children) > limits.max_processes:
                        self._terminate_execution(execution_id, f"Too many child processes: {len(children)}")
                        break

                    # Check for memory leaks (gradual increase)
                    if elapsed_time > 5.0:  # After 5 seconds
                        current_memory = process.memory_info().rss / 1024 / 1024
                        baseline_memory = self.system_baseline.memory_usage_mb
                        memory_growth = current_memory - baseline_memory

                        if memory_growth > limits.max_memory_mb * 0.8:  # Growing too fast
                            log_warning(f"Potential memory leak: {memory_growth:.1f}MB growth")

                except psutil.NoSuchProcess:
                    # Process ended normally
                    break
                except Exception as e:
                    log_warning(f"Monitoring error for {execution_id}: {e}")

                # Wait before next check
                time.sleep(check_interval)

        except Exception as e:
            log_error(f"Monitor thread failed for {execution_id}: {e}")

    def _terminate_execution(self, execution_id: str, reason: str):
        """Terminate a specific execution"""
        log_error(f"Terminating execution {execution_id}: {reason}")

        if execution_id in self.active_executions:
            execution_info = self.active_executions[execution_id]
            execution_info["stop_event"].set()

            # Try to terminate gracefully first
            try:
                # Send termination signal to current process
                import os
                os.kill(os.getpid(), signal.SIGTERM)
            except Exception as e:
                log_warning(f"Could not send termination signal: {e}")

        # Remove from tracking
        if execution_id in self.active_executions:
            del self.active_executions[execution_id]

    def _terminate_all_executions(self):
        """Emergency termination of all active executions"""
        log_error("Emergency termination of all active executions")

        for execution_id in list(self.active_executions.keys()):
            self._terminate_execution(execution_id, "Emergency stop")

        # Force garbage collection
        gc.collect()

    def check_system_stability(self) -> dict[str, Any]:
        """Check current system stability metrics"""
        try:
            process = psutil.Process()
            current_state = SystemState(
                memory_usage_mb=process.memory_info().rss / 1024 / 1024,
                cpu_percent=process.cpu_percent(),
                active_threads=threading.active_count(),
                open_files=len(process.open_files()) if hasattr(process, 'open_files') else 0,
                load_average=psutil.getloadavg()[0] if hasattr(psutil, 'getloadavg') else 0.0,
                timestamp=datetime.now()
            )

            # Calculate changes from baseline
            memory_change = current_state.memory_usage_mb - self.system_baseline.memory_usage_mb
            thread_change = current_state.active_threads - self.system_baseline.active_threads

            # Determine stability status
            is_stable = True
            issues = []

            if memory_change > 500:  # More than 500MB growth
                is_stable = False
                issues.append(f"High memory usage: +{memory_change:.1f}MB")

            if current_state.cpu_percent > 80:
                is_stable = False
                issues.append(f"High CPU usage: {current_state.cpu_percent:.1f}%")

            if thread_change > 10:
                is_stable = False
                issues.append(f"Too many threads: +{thread_change}")

            if current_state.load_average > 5.0:
                is_stable = False
                issues.append(f"High system load: {current_state.load_average:.2f}")

            return {
                "is_stable": is_stable,
                "issues": issues,
                "current_state": {
                    "memory_mb": current_state.memory_usage_mb,
                    "cpu_percent": current_state.cpu_percent,
                    "threads": current_state.active_threads,
                    "load_average": current_state.load_average
                },
                "baseline_state": {
                    "memory_mb": self.system_baseline.memory_usage_mb,
                    "cpu_percent": self.system_baseline.cpu_percent,
                    "threads": self.system_baseline.active_threads,
                    "load_average": self.system_baseline.load_average
                },
                "active_executions": len(self.active_executions),
                "max_concurrent": self.max_concurrent_executions
            }

        except Exception as e:
            log_error(f"System stability check failed: {e}")
            return {
                "is_stable": False,
                "issues": [f"Stability check failed: {e}"],
                "error": str(e)
            }

    async def execute_with_crash_prevention(
        self,
        func: Callable,
        args: tuple,
        kwargs: dict,
        limits: ResourceLimits,
        execution_id: str | None = None
    ) -> Any:
        """
        Execute a function with comprehensive crash prevention

        Args:
            func: Function to execute
            args: Function arguments
            kwargs: Function keyword arguments
            limits: Resource limits to enforce
            execution_id: Optional execution ID

        Returns:
            Function result

        Raises:
            ExternalFunctionExecutionError: If execution fails or violates limits
        """
        if execution_id is None:
            execution_id = f"exec_{int(time.time() * 1000)}"

        # Check system stability before execution
        stability = self.check_system_stability()
        if not stability["is_stable"]:
            raise ExternalFunctionExecutionError(
                f"System unstable - cannot execute: {', '.join(stability['issues'])}"
            )

        # Check emergency stop
        if self.emergency_stop.is_set():
            raise ExternalFunctionExecutionError("Emergency stop is active")

        try:
            with self.safe_execution_context(execution_id, limits):
                # Create execution timeout
                async def execute_with_timeout():
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(None, func, *args, **kwargs)

                # Execute with timeout
                result = await asyncio.wait_for(
                    execute_with_timeout(),
                    timeout=limits.max_wall_time_seconds
                )

                log_info(f"Execution {execution_id} completed successfully")
                return result

        except TimeoutError:
            raise ExternalFunctionExecutionError(
                f"Execution timed out after {limits.max_wall_time_seconds} seconds"
            )
        except MemoryError:
            raise ExternalFunctionExecutionError("Memory limit exceeded - execution terminated")
        except RecursionError:
            raise ExternalFunctionExecutionError("Stack overflow - recursion limit exceeded")
        except KeyboardInterrupt:
            raise ExternalFunctionExecutionError("Execution interrupted")
        except Exception as e:
            if "limit exceeded" in str(e).lower():
                raise ExternalFunctionExecutionError(f"Resource limit exceeded: {e}")
            raise ExternalFunctionExecutionError(f"Execution failed: {e}")

    def get_execution_metrics(self) -> dict[str, Any]:
        """Get metrics about current executions"""
        current_time = datetime.now()

        execution_metrics = {}
        for exec_id, exec_info in self.active_executions.items():
            duration = (current_time - exec_info["start_time"]).total_seconds()
            execution_metrics[exec_id] = {
                "duration_seconds": duration,
                "limits": {
                    "max_memory_mb": exec_info["limits"].max_memory_mb,
                    "max_cpu_seconds": exec_info["limits"].max_cpu_seconds,
                    "max_wall_time_seconds": exec_info["limits"].max_wall_time_seconds
                }
            }

        return {
            "active_executions": len(self.active_executions),
            "max_concurrent": self.max_concurrent_executions,
            "emergency_stop_active": self.emergency_stop.is_set(),
            "executions": execution_metrics,
            "system_stability": self.check_system_stability()
        }

    def shutdown(self):
        """Clean shutdown of crash prevention system"""
        log_info("Shutting down crash prevention system")

        # Set emergency stop
        self.emergency_stop.set()

        # Terminate all active executions
        self._terminate_all_executions()

        # Wait for cleanup
        time.sleep(1.0)

        # Force final garbage collection
        gc.collect()

        log_info("Crash prevention system shutdown complete")


# Global instance
_crash_prevention = None


def get_crash_prevention() -> CrashPrevention:
    """Get singleton crash prevention instance"""
    global _crash_prevention
    if _crash_prevention is None:
        _crash_prevention = CrashPrevention()
    return _crash_prevention


class StackOverflowProtection:
    """Stack overflow protection for recursive functions"""

    def __init__(self, max_depth: int = 100):
        self.max_depth = max_depth
        self.current_depth = 0

    def __enter__(self):
        self.current_depth += 1
        if self.current_depth > self.max_depth:
            raise RecursionError(f"Stack overflow protection: depth {self.current_depth} exceeds limit {self.max_depth}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.current_depth -= 1


def stack_overflow_protection(max_depth: int = 100):
    """Decorator for stack overflow protection"""
    def decorator(func):
        protection = StackOverflowProtection(max_depth)

        def wrapper(*args, **kwargs):
            with protection:
                return func(*args, **kwargs)

        return wrapper
    return decorator
