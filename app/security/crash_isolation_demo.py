"""
Crash Isolation Demonstration
Shows how malicious or buggy scripts cannot crash the main signal_service
"""
import asyncio
import time
from typing import Dict, Any
from app.security.sandbox_enhancements import get_enhanced_sandbox
from app.security.sandbox_config import create_sandbox_config
from app.utils.logging_utils import log_info, log_warning, log_exception


class CrashIsolationDemo:
    """Demonstrates crash isolation capabilities"""
    
    def __init__(self):
        self.sandbox = get_enhanced_sandbox()
        self.demo_results = []
    
    async def run_all_demos(self) -> Dict[str, Any]:
        """Run all crash isolation demonstrations"""
        log_info("Starting crash isolation demonstrations...")
        
        demos = [
            ("infinite_loop", self.demo_infinite_loop),
            ("memory_bomb", self.demo_memory_bomb),
            ("malicious_imports", self.demo_malicious_imports),
            ("system_calls", self.demo_system_calls),
            ("process_fork", self.demo_process_fork),
            ("file_access", self.demo_file_access),
            ("network_access", self.demo_network_access),
            ("crash_with_exception", self.demo_crash_exception)
        ]
        
        results = {}
        main_service_healthy = True
        
        for demo_name, demo_func in demos:
            log_info(f"Running demo: {demo_name}")
            
            try:
                start_time = time.time()
                demo_result = await demo_func()
                execution_time = time.time() - start_time
                
                results[demo_name] = {
                    'status': 'completed',
                    'result': demo_result,
                    'execution_time_seconds': execution_time,
                    'main_service_affected': False
                }
                
                # Verify main service is still healthy
                if not self._check_main_service_health():
                    main_service_healthy = False
                    results[demo_name]['main_service_affected'] = True
                    
            except Exception as e:
                log_exception(f"Demo {demo_name} failed: {e}")
                results[demo_name] = {
                    'status': 'failed',
                    'error': str(e),
                    'main_service_affected': False
                }
        
        summary = {
            'total_demos': len(demos),
            'successful_isolations': sum(1 for r in results.values() if not r.get('main_service_affected', True)),
            'main_service_healthy': main_service_healthy,
            'demo_results': results,
            'isolation_effectiveness': 'excellent' if main_service_healthy else 'needs_improvement'
        }
        
        log_info(f"Crash isolation demos completed. Service healthy: {main_service_healthy}")
        return summary
    
    async def demo_infinite_loop(self) -> Dict[str, Any]:
        """Demonstrate infinite loop protection"""
        malicious_script = '''
def infinite_loop_attack(data, params):
    """Attempt to create infinite loop"""
    count = 0
    while True:  # This should be caught by timeout
        count += 1
        if count > 1000000:  # Never reached due to timeout
            break
    return {"count": count}
'''
        
        try:
            config = create_sandbox_config('production', 'free', {
                'wall_time_seconds': 2,  # Very short timeout
                'cpu_time_seconds': 1
            })
            
            result = await self.sandbox.execute_script_safe(
                script_content=malicious_script,
                function_name='infinite_loop_attack',
                input_data={},
                limits=config['policy']
            )
            
            return {
                'blocked': False,
                'result': result,
                'message': 'Infinite loop was not properly blocked!'
            }
            
        except Exception as e:
            return {
                'blocked': True,
                'error_type': type(e).__name__,
                'message': 'Infinite loop properly blocked by timeout',
                'details': str(e)
            }
    
    async def demo_memory_bomb(self) -> Dict[str, Any]:
        """Demonstrate memory exhaustion protection"""
        malicious_script = '''
def memory_bomb_attack(data, params):
    """Attempt to exhaust memory"""
    huge_list = []
    try:
        # Try to allocate 1GB of memory
        for i in range(1000000):
            huge_list.append([0] * 1000)  # Each inner list ~8KB
        return {"allocated": len(huge_list)}
    except:
        return {"failed": True}
'''
        
        try:
            config = create_sandbox_config('production', 'free', {
                'memory_limit_mb': 32,  # Low memory limit
            })
            
            result = await self.sandbox.execute_script_safe(
                script_content=malicious_script,
                function_name='memory_bomb_attack',
                input_data={},
                limits=config['policy']
            )
            
            return {
                'blocked': False,
                'result': result,
                'message': 'Memory bomb was not properly blocked!'
            }
            
        except Exception as e:
            return {
                'blocked': True,
                'error_type': type(e).__name__,
                'message': 'Memory bomb properly blocked by memory limits',
                'details': str(e)
            }
    
    async def demo_malicious_imports(self) -> Dict[str, Any]:
        """Demonstrate malicious import protection"""
        malicious_script = '''
def malicious_imports_attack(data, params):
    """Attempt dangerous imports"""
    try:
        import os  # Should be blocked
        import sys  # Should be blocked
        import subprocess  # Should be blocked
        
        # If we get here, security failed
        return {
            "security_breach": True,
            "os_available": hasattr(os, 'system'),
            "sys_available": hasattr(sys, 'exit'),
        }
    except Exception as e:
        return {"import_blocked": True, "error": str(e)}
'''
        
        try:
            config = create_sandbox_config('production', 'free')
            
            result = await self.sandbox.execute_script_safe(
                script_content=malicious_script,
                function_name='malicious_imports_attack',
                input_data={},
                limits=config['policy']
            )
            
            return {
                'blocked': result.get('import_blocked', False),
                'result': result,
                'message': 'Import blocking test completed'
            }
            
        except Exception as e:
            return {
                'blocked': True,
                'error_type': type(e).__name__,
                'message': 'Malicious imports blocked at compile time',
                'details': str(e)
            }
    
    async def demo_system_calls(self) -> Dict[str, Any]:
        """Demonstrate system call protection"""
        malicious_script = '''
def system_calls_attack(data, params):
    """Attempt system calls"""
    try:
        # Try various ways to execute system commands
        exec("import os; os.system('whoami')")  # Should be blocked
        return {"system_call_success": True}
    except:
        try:
            eval("__import__('subprocess').call(['ls'])")  # Should be blocked
            return {"eval_success": True}
        except:
            return {"all_blocked": True}
'''
        
        try:
            config = create_sandbox_config('production', 'free')
            
            result = await self.sandbox.execute_script_safe(
                script_content=malicious_script,
                function_name='system_calls_attack',
                input_data={},
                limits=config['policy']
            )
            
            return {
                'blocked': result.get('all_blocked', False),
                'result': result,
                'message': 'System calls protection test'
            }
            
        except Exception as e:
            return {
                'blocked': True,
                'error_type': type(e).__name__,
                'message': 'System calls blocked by RestrictedPython',
                'details': str(e)
            }
    
    async def demo_process_fork(self) -> Dict[str, Any]:
        """Demonstrate process forking protection"""
        malicious_script = '''
def process_fork_attack(data, params):
    """Attempt to fork processes"""
    try:
        # This should be caught by validation
        import multiprocessing
        import threading
        
        def worker():
            return "forked"
        
        # Try multiprocessing
        pool = multiprocessing.Pool(10)
        results = pool.map(worker, range(10))
        pool.close()
        
        return {"fork_success": True, "results": results}
    except:
        return {"fork_blocked": True}
'''
        
        try:
            config = create_sandbox_config('production', 'free')
            
            result = await self.sandbox.execute_script_safe(
                script_content=malicious_script,
                function_name='process_fork_attack',
                input_data={},
                limits=config['policy']
            )
            
            return {
                'blocked': result.get('fork_blocked', False),
                'result': result,
                'message': 'Process forking test'
            }
            
        except Exception as e:
            return {
                'blocked': True,
                'error_type': type(e).__name__,
                'message': 'Process forking blocked by validation',
                'details': str(e)
            }
    
    async def demo_file_access(self) -> Dict[str, Any]:
        """Demonstrate file system access protection"""
        malicious_script = '''
def file_access_attack(data, params):
    """Attempt file system access"""
    try:
        # Try to read sensitive files
        with open('/etc/passwd', 'r') as f:
            content = f.read()
        return {"file_read_success": True, "content_length": len(content)}
    except:
        try:
            # Try to write files
            with open('/tmp/malicious_file.txt', 'w') as f:
                f.write("malicious content")
            return {"file_write_success": True}
        except:
            return {"file_access_blocked": True}
'''
        
        try:
            config = create_sandbox_config('production', 'free')
            
            result = await self.sandbox.execute_script_safe(
                script_content=malicious_script,
                function_name='file_access_attack',
                input_data={},
                limits=config['policy']
            )
            
            return {
                'blocked': result.get('file_access_blocked', False),
                'result': result,
                'message': 'File access protection test'
            }
            
        except Exception as e:
            return {
                'blocked': True,
                'error_type': type(e).__name__,
                'message': 'File access blocked by validation',
                'details': str(e)
            }
    
    async def demo_network_access(self) -> Dict[str, Any]:
        """Demonstrate network access protection"""
        malicious_script = '''
def network_access_attack(data, params):
    """Attempt network access"""
    try:
        import socket
        import urllib
        
        # Try socket connection
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('google.com', 80))
        sock.close()
        
        return {"network_success": True}
    except:
        return {"network_blocked": True}
'''
        
        try:
            config = create_sandbox_config('production', 'free')
            
            result = await self.sandbox.execute_script_safe(
                script_content=malicious_script,
                function_name='network_access_attack',
                input_data={},
                limits=config['policy']
            )
            
            return {
                'blocked': result.get('network_blocked', False),
                'result': result,
                'message': 'Network access protection test'
            }
            
        except Exception as e:
            return {
                'blocked': True,
                'error_type': type(e).__name__,
                'message': 'Network access blocked by validation',
                'details': str(e)
            }
    
    async def demo_crash_exception(self) -> Dict[str, Any]:
        """Demonstrate exception handling protection"""
        malicious_script = '''
def crash_exception_attack(data, params):
    """Attempt to crash with exceptions"""
    try:
        # Recursive function to cause stack overflow
        def recursive_crash(n):
            if n > 10000:  # Should hit recursion limit
                return n
            return recursive_crash(n + 1) + recursive_crash(n + 1)
        
        result = recursive_crash(0)
        return {"crash_avoided": True, "result": result}
    except Exception as e:
        return {"exception_handled": True, "error_type": str(type(e).__name__)}
'''
        
        try:
            config = create_sandbox_config('production', 'free')
            
            result = await self.sandbox.execute_script_safe(
                script_content=malicious_script,
                function_name='crash_exception_attack',
                input_data={},
                limits=config['policy']
            )
            
            return {
                'handled_gracefully': True,
                'result': result,
                'message': 'Exception handling test completed'
            }
            
        except Exception as e:
            return {
                'handled_gracefully': True,
                'error_type': type(e).__name__,
                'message': 'Exception properly contained',
                'details': str(e)
            }
    
    def _check_main_service_health(self) -> bool:
        """Check if main service is still healthy after demo"""
        try:
            # Simple health checks
            start_time = time.time()
            
            # CPU check
            import psutil
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Memory check
            memory = psutil.virtual_memory()
            
            # Time check (should be fast)
            check_time = time.time() - start_time
            
            # Service is healthy if:
            # - CPU usage is reasonable
            # - Memory usage is reasonable
            # - Health check completes quickly
            is_healthy = (
                cpu_percent < 90 and
                memory.percent < 90 and
                check_time < 1.0
            )
            
            if is_healthy:
                log_info(f"Main service health check passed: CPU={cpu_percent:.1f}%, Memory={memory.percent:.1f}%")
            else:
                log_warning(f"Main service health check failed: CPU={cpu_percent:.1f}%, Memory={memory.percent:.1f}%")
                
            return is_healthy
            
        except Exception as e:
            log_exception(f"Health check failed: {e}")
            return False


# Example usage
async def run_crash_isolation_demo():
    """Run the complete crash isolation demonstration"""
    demo = CrashIsolationDemo()
    results = await demo.run_all_demos()
    
    print("\\n" + "="*60)
    print("CRASH ISOLATION DEMONSTRATION RESULTS")
    print("="*60)
    
    print(f"Total Demos: {results['total_demos']}")
    print(f"Successful Isolations: {results['successful_isolations']}")
    print(f"Main Service Healthy: {results['main_service_healthy']}")
    print(f"Isolation Effectiveness: {results['isolation_effectiveness']}")
    
    print("\\nDetailed Results:")
    for demo_name, demo_result in results['demo_results'].items():
        status = "✅ PASSED" if demo_result.get('blocked', True) else "❌ FAILED"
        print(f"{status} {demo_name}: {demo_result.get('message', 'N/A')}")
    
    return results


if __name__ == "__main__":
    asyncio.run(run_crash_isolation_demo())