"""
Advanced Malicious Code Detection System
Detects and prevents execution of malicious Python code patterns
"""

import ast
import re
import sys
from typing import Dict, List, Set, Tuple, Any
from dataclasses import dataclass
from enum import Enum

from app.errors import SecurityError
from app.utils.logging_utils import log_warning, log_info


class ThreatLevel(Enum):
    """Threat severity levels"""
    LOW = "low"
    MEDIUM = "medium" 
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SecurityThreat:
    """Represents a detected security threat"""
    level: ThreatLevel
    category: str
    description: str
    line_number: int
    code_snippet: str
    mitigation: str


class MaliciousCodeDetector:
    """
    Advanced malicious code detection using multiple analysis techniques:
    1. Static AST analysis for dangerous patterns
    2. String pattern matching for obfuscated code
    3. Import and module usage validation
    4. Resource usage pattern detection
    5. Behavioral pattern analysis
    """
    
    def __init__(self):
        self.threats_found = []
        self._init_detection_patterns()
    
    def _init_detection_patterns(self):
        """Initialize detection patterns and rules"""
        
        # Critical system access patterns
        self.critical_imports = {
            'os', 'sys', 'subprocess', 'shutil', 'tempfile',
            'socket', 'urllib', 'requests', 'httpx', 'aiohttp',
            'threading', 'multiprocessing', 'asyncio.subprocess',
            'ctypes', 'ffi', 'cffi', '__builtin__', 'builtins',
            'importlib', 'pkgutil', 'runpy', 'imp'
        }
        
        # Dangerous function calls
        self.dangerous_functions = {
            'exec', 'eval', 'compile', '__import__', 'getattr',
            'setattr', 'delattr', 'hasattr', 'globals', 'locals', 'vars',
            'open', 'file', 'input', 'raw_input',
            'exit', 'quit', 'reload', 'help'
        }
        
        # System manipulation patterns
        self.system_patterns = [
            # File system access
            r'open\s*\(\s*["\'][^"\']*(?:/etc/|/proc/|/sys/|/dev/)',
            r'with\s+open\s*\(\s*["\'][^"\']*(?:/etc/|/proc/|/sys/)',
            r'\.write\s*\(\s*["\'][^"\']*(?:rm\s+-rf|del\s+|format\s+)',
            
            # Network access
            r'socket\s*\.\s*socket\s*\(',
            r'urllib\.request\.|requests\.get|httpx\.|aiohttp\.',
            r'http[s]?://[^\s"\')]+',
            
            # Process execution
            r'subprocess\.|os\.system|os\.popen|os\.exec',
            r'Popen\s*\(|call\s*\(|run\s*\(',
            
            # Dynamic code execution
            r'exec\s*\(\s*["\']|eval\s*\(\s*["\']',
            r'compile\s*\(\s*["\'].*["\'].*exec',
            r'__import__\s*\(\s*["\']',
            
            # Memory/resource manipulation
            r'ctypes\.|ffi\.|cffi\.',
            r'mmap\.|memoryview\(',
            r'gc\.|weakref\.',
            
            # Obfuscation patterns
            r'chr\s*\(\s*\d+\s*\)|ord\s*\(',
            r'base64\.|codecs\.|binascii\.',
            r'\.decode\s*\(\s*["\']|\.encode\s*\(\s*["\']',
            
            # Anti-analysis patterns
            r'try\s*:\s*.*except\s*:\s*pass',
            r'while\s+True\s*:\s*pass',
            r'for\s+.*in\s+range\s*\(\s*999',
        ]
        
        # Crypto/encoding suspicious patterns
        self.crypto_patterns = [
            r'hashlib\.|hmac\.|secrets\.',
            r'Crypto\.|cryptography\.',
            r'base64\.|base32\.|base16\.',
            r'zlib\.|gzip\.|bz2\.|lzma\.'
        ]
        
        # Suspicious variable names (common in malware)
        self.suspicious_names = {
            'payload', 'shellcode', 'exploit', 'backdoor', 'trojan',
            'virus', 'malware', 'rootkit', 'keylog', 'stealer',
            'rat', 'bot', 'zombie', 'dropper', 'loader',
            'obfuscate', 'deobfuscate', 'decrypt', 'decode'
        }
        
        # Dangerous string literals
        self.dangerous_strings = [
            '/etc/passwd', '/etc/shadow', '/root/', '~/.ssh/',
            'cmd.exe', 'powershell.exe', '/bin/sh', '/bin/bash',
            'rm -rf', 'del /f', 'format c:', 'dd if=',
            'curl ', 'wget ', 'nc -l', 'netcat',
            'CREATE USER', 'DROP TABLE', 'DELETE FROM'
        ]
    
    def analyze_code(self, code: str, filename: str = "<string>") -> List[SecurityThreat]:
        """
        Comprehensive malicious code analysis
        
        Args:
            code: Python source code to analyze
            filename: Name of the file being analyzed
            
        Returns:
            List of detected security threats
        """
        self.threats_found = []
        
        try:
            # 1. Syntax validation and AST analysis
            self._analyze_ast(code, filename)
            
            # 2. String pattern analysis
            self._analyze_string_patterns(code)
            
            # 3. Import analysis
            self._analyze_imports(code)
            
            # 4. Function call analysis
            self._analyze_function_calls(code)
            
            # 5. Variable name analysis
            self._analyze_variable_names(code)
            
            # 6. Code structure analysis
            self._analyze_code_structure(code)
            
            # 7. Obfuscation detection
            self._detect_obfuscation(code)
            
            # 8. Resource usage analysis
            self._analyze_resource_usage(code)
            
        except SyntaxError as e:
            self.threats_found.append(SecurityThreat(
                level=ThreatLevel.HIGH,
                category="syntax_error",
                description=f"Syntax error in code: {e}",
                line_number=getattr(e, 'lineno', 0),
                code_snippet=getattr(e, 'text', ''),
                mitigation="Fix syntax errors before execution"
            ))
        
        return self.threats_found
    
    def _analyze_ast(self, code: str, filename: str):
        """Analyze code using Abstract Syntax Tree"""
        try:
            tree = ast.parse(code, filename=filename)
            
            for node in ast.walk(tree):
                self._check_ast_node(node)
                
        except SyntaxError:
            raise  # Re-raise syntax errors
        except Exception as e:
            self.threats_found.append(SecurityThreat(
                level=ThreatLevel.MEDIUM,
                category="ast_analysis_error",
                description=f"AST analysis failed: {e}",
                line_number=0,
                code_snippet="",
                mitigation="Code structure may be malformed"
            ))
    
    def _check_ast_node(self, node: ast.AST):
        """Check individual AST node for threats"""
        line_no = getattr(node, 'lineno', 0)
        
        # Import statements
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            self._check_import_node(node, line_no)
        
        # Function calls
        elif isinstance(node, ast.Call):
            self._check_call_node(node, line_no)
        
        # Attribute access
        elif isinstance(node, ast.Attribute):
            self._check_attribute_node(node, line_no)
        
        # String literals
        elif isinstance(node, ast.Str):
            self._check_string_literal(node, line_no)
        
        # Variable assignments
        elif isinstance(node, ast.Assign):
            self._check_assignment_node(node, line_no)
        
        # Exception handling
        elif isinstance(node, ast.ExceptHandler):
            self._check_exception_handler(node, line_no)
        
        # Loop constructs
        elif isinstance(node, (ast.While, ast.For)):
            self._check_loop_node(node, line_no)
    
    def _check_import_node(self, node: ast.AST, line_no: int):
        """Check import statements for dangerous modules"""
        modules = []
        
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules = [node.module]
        
        for module in modules:
            base_module = module.split('.')[0]
            if base_module in self.critical_imports:
                self.threats_found.append(SecurityThreat(
                    level=ThreatLevel.CRITICAL,
                    category="dangerous_import",
                    description=f"Import of dangerous module: {module}",
                    line_number=line_no,
                    code_snippet=f"import {module}",
                    mitigation=f"Remove import of {module} or use safe alternatives"
                ))
    
    def _check_call_node(self, node: ast.Call, line_no: int):
        """Check function calls for dangerous functions"""
        func_name = ""
        
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        
        if func_name in self.dangerous_functions:
            self.threats_found.append(SecurityThreat(
                level=ThreatLevel.HIGH,
                category="dangerous_function",
                description=f"Call to dangerous function: {func_name}",
                line_number=line_no,
                code_snippet=f"{func_name}(...)",
                mitigation=f"Remove call to {func_name} or use safe alternatives"
            ))
        
        # Check for exec/eval with variables
        if func_name in ['exec', 'eval'] and node.args:
            arg = node.args[0]
            if not isinstance(arg, ast.Str):  # Not a string literal
                self.threats_found.append(SecurityThreat(
                    level=ThreatLevel.CRITICAL,
                    category="dynamic_code_execution",
                    description=f"Dynamic code execution with variables: {func_name}",
                    line_number=line_no,
                    code_snippet=f"{func_name}(variable)",
                    mitigation="Never execute code from variables"
                ))
    
    def _check_attribute_node(self, node: ast.Attribute, line_no: int):
        """Check attribute access for dangerous patterns"""
        # Check for __class__.__bases__ type manipulation
        if node.attr in ['__class__', '__bases__', '__subclasses__', '__mro__']:
            self.threats_found.append(SecurityThreat(
                level=ThreatLevel.HIGH,
                category="type_manipulation",
                description=f"Access to dangerous attribute: {node.attr}",
                line_number=line_no,
                code_snippet=f"obj.{node.attr}",
                mitigation=f"Remove access to {node.attr}"
            ))
    
    def _check_string_literal(self, node: ast.Str, line_no: int):
        """Check string literals for dangerous content"""
        if hasattr(node, 's'):  # Python < 3.8
            value = node.s
        elif hasattr(node, 'value'):  # Python >= 3.8
            value = node.value
        else:
            return
        
        for dangerous_string in self.dangerous_strings:
            if dangerous_string in value.lower():
                self.threats_found.append(SecurityThreat(
                    level=ThreatLevel.HIGH,
                    category="dangerous_string",
                    description=f"Dangerous string literal: {dangerous_string}",
                    line_number=line_no,
                    code_snippet=f'"{value[:50]}..."',
                    mitigation=f"Remove reference to {dangerous_string}"
                ))
    
    def _check_assignment_node(self, node: ast.Assign, line_no: int):
        """Check variable assignments for suspicious patterns"""
        for target in node.targets:
            if isinstance(target, ast.Name):
                var_name = target.id.lower()
                if var_name in self.suspicious_names:
                    self.threats_found.append(SecurityThreat(
                        level=ThreatLevel.MEDIUM,
                        category="suspicious_variable",
                        description=f"Suspicious variable name: {target.id}",
                        line_number=line_no,
                        code_snippet=f"{target.id} = ...",
                        mitigation=f"Rename variable {target.id} to something less suspicious"
                    ))
    
    def _check_exception_handler(self, node: ast.ExceptHandler, line_no: int):
        """Check exception handlers for malicious patterns"""
        # Bare except clauses that hide errors
        if node.type is None:
            # Check if it just passes
            if (len(node.body) == 1 and 
                isinstance(node.body[0], ast.Pass)):
                self.threats_found.append(SecurityThreat(
                    level=ThreatLevel.MEDIUM,
                    category="error_hiding",
                    description="Bare except clause that hides all errors",
                    line_number=line_no,
                    code_snippet="bare except with silent handler",
                    mitigation="Catch specific exceptions and handle appropriately"
                ))
    
    def _check_loop_node(self, node: ast.AST, line_no: int):
        """Check loops for potential infinite loops or resource exhaustion"""
        if isinstance(node, ast.While):
            # Check for while True without break
            if (isinstance(node.test, ast.NameConstant) and 
                node.test.value is True):
                has_break = any(isinstance(n, ast.Break) for n in ast.walk(node))
                if not has_break:
                    self.threats_found.append(SecurityThreat(
                        level=ThreatLevel.HIGH,
                        category="infinite_loop",
                        description="Potential infinite loop: while True without break",
                        line_number=line_no,
                        code_snippet="while True: ...",
                        mitigation="Add break condition or use finite loop"
                    ))
    
    def _analyze_string_patterns(self, code: str):
        """Analyze string patterns for malicious content"""
        lines = code.split('\n')
        
        for line_no, line in enumerate(lines, 1):
            line_lower = line.lower()
            
            # Check system patterns
            for pattern in self.system_patterns:
                matches = re.finditer(pattern, line, re.IGNORECASE)
                for match in matches:
                    self.threats_found.append(SecurityThreat(
                        level=ThreatLevel.HIGH,
                        category="system_access_pattern",
                        description=f"Suspicious system access pattern: {pattern[:50]}",
                        line_number=line_no,
                        code_snippet=line.strip()[:100],
                        mitigation="Remove system access patterns"
                    ))
            
            # Check crypto patterns (medium threat - could be legitimate)
            for pattern in self.crypto_patterns:
                matches = re.finditer(pattern, line, re.IGNORECASE)
                for match in matches:
                    self.threats_found.append(SecurityThreat(
                        level=ThreatLevel.MEDIUM,
                        category="crypto_usage",
                        description=f"Cryptographic library usage: {pattern}",
                        line_number=line_no,
                        code_snippet=line.strip()[:100],
                        mitigation="Verify cryptographic usage is legitimate"
                    ))
    
    def _analyze_imports(self, code: str):
        """Detailed import analysis"""
        lines = code.split('\n')
        
        for line_no, line in enumerate(lines, 1):
            line_stripped = line.strip()
            
            # Dynamic imports
            if re.search(r'__import__\s*\(', line):
                self.threats_found.append(SecurityThreat(
                    level=ThreatLevel.HIGH,
                    category="dynamic_import",
                    description="Dynamic import using __import__",
                    line_number=line_no,
                    code_snippet=line_stripped,
                    mitigation="Use static imports only"
                ))
            
            # Importlib usage
            if 'importlib' in line and ('import_module' in line or 'reload' in line):
                self.threats_found.append(SecurityThreat(
                    level=ThreatLevel.HIGH,
                    category="dynamic_import",
                    description="Dynamic module loading with importlib",
                    line_number=line_no,
                    code_snippet=line_stripped,
                    mitigation="Avoid dynamic module loading"
                ))
    
    def _analyze_function_calls(self, code: str):
        """Analyze function calls for suspicious patterns"""
        lines = code.split('\n')
        
        for line_no, line in enumerate(lines, 1):
            # Chain function calls that could be used for obfuscation
            if line.count('(') > 5:  # Too many nested calls
                self.threats_found.append(SecurityThreat(
                    level=ThreatLevel.MEDIUM,
                    category="complex_call_chain",
                    description="Overly complex function call chain",
                    line_number=line_no,
                    code_snippet=line.strip()[:100],
                    mitigation="Simplify function call chain"
                ))
    
    def _analyze_variable_names(self, code: str):
        """Analyze variable names for suspicious patterns"""
        # Find all variable names using regex
        var_pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*='
        matches = re.finditer(var_pattern, code)
        
        for match in matches:
            var_name = match.group(1).lower()
            if var_name in self.suspicious_names:
                line_no = code[:match.start()].count('\n') + 1
                self.threats_found.append(SecurityThreat(
                    level=ThreatLevel.MEDIUM,
                    category="suspicious_variable",
                    description=f"Suspicious variable name: {match.group(1)}",
                    line_number=line_no,
                    code_snippet=f"{match.group(1)} = ...",
                    mitigation=f"Rename variable {match.group(1)}"
                ))
    
    def _analyze_code_structure(self, code: str):
        """Analyze overall code structure"""
        lines = code.split('\n')
        non_empty_lines = [line for line in lines if line.strip()]
        
        # Too many lines
        if len(non_empty_lines) > 500:
            self.threats_found.append(SecurityThreat(
                level=ThreatLevel.MEDIUM,
                category="code_size",
                description=f"Code too large: {len(non_empty_lines)} lines",
                line_number=0,
                code_snippet="",
                mitigation="Reduce code size or split into smaller functions"
            ))
        
        # Too many imports
        import_count = sum(1 for line in lines if line.strip().startswith(('import ', 'from ')))
        if import_count > 20:
            self.threats_found.append(SecurityThreat(
                level=ThreatLevel.MEDIUM,
                category="excessive_imports",
                description=f"Too many imports: {import_count}",
                line_number=0,
                code_snippet="",
                mitigation="Reduce number of imports"
            ))
    
    def _detect_obfuscation(self, code: str):
        """Detect code obfuscation techniques"""
        lines = code.split('\n')
        
        for line_no, line in enumerate(lines, 1):
            line_stripped = line.strip()
            
            # Base64 patterns
            if re.search(r'[A-Za-z0-9+/]{20,}={0,2}', line_stripped):
                self.threats_found.append(SecurityThreat(
                    level=ThreatLevel.HIGH,
                    category="base64_obfuscation",
                    description="Potential Base64 encoded content",
                    line_number=line_no,
                    code_snippet=line_stripped[:100],
                    mitigation="Decode and verify content is safe"
                ))
            
            # Hex patterns
            if re.search(r'\\x[0-9a-fA-F]{2}', line_stripped):
                self.threats_found.append(SecurityThreat(
                    level=ThreatLevel.MEDIUM,
                    category="hex_obfuscation", 
                    description="Hex-encoded strings detected",
                    line_number=line_no,
                    code_snippet=line_stripped[:100],
                    mitigation="Decode hex strings and verify content"
                ))
            
            # Unicode obfuscation
            if re.search(r'\\u[0-9a-fA-F]{4}', line_stripped):
                self.threats_found.append(SecurityThreat(
                    level=ThreatLevel.MEDIUM,
                    category="unicode_obfuscation",
                    description="Unicode escape sequences detected",
                    line_number=line_no,
                    code_snippet=line_stripped[:100],
                    mitigation="Decode Unicode sequences and verify content"
                ))
    
    def _analyze_resource_usage(self, code: str):
        """Analyze patterns that could lead to resource exhaustion"""
        lines = code.split('\n')
        
        for line_no, line in enumerate(lines, 1):
            # Large list/dict creations
            if re.search(r'range\s*\(\s*\d{6,}', line):  # range(1000000+)
                self.threats_found.append(SecurityThreat(
                    level=ThreatLevel.HIGH,
                    category="memory_exhaustion",
                    description="Large range that could exhaust memory",
                    line_number=line_no,
                    code_snippet=line.strip(),
                    mitigation="Reduce range size or use generators"
                ))
            
            # Recursive functions without base case
            if 'def ' in line and line.strip().split('(')[0].split()[-1] in line:
                func_name = line.strip().split('(')[0].split()[-1]
                # Simple check - this could be improved
                self.threats_found.append(SecurityThreat(
                    level=ThreatLevel.LOW,
                    category="potential_recursion",
                    description=f"Potential recursive function: {func_name}",
                    line_number=line_no,
                    code_snippet=line.strip(),
                    mitigation="Ensure recursion has proper base case and depth limit"
                ))
    
    def get_threat_summary(self) -> Dict[str, Any]:
        """Get summary of detected threats"""
        if not self.threats_found:
            return {
                "total_threats": 0,
                "threat_levels": {},
                "categories": {},
                "is_safe": True,
                "max_threat_level": None
            }
        
        threat_levels = {}
        categories = {}
        max_level = ThreatLevel.LOW
        
        for threat in self.threats_found:
            # Count by level
            level_str = threat.level.value
            threat_levels[level_str] = threat_levels.get(level_str, 0) + 1
            
            # Count by category
            categories[threat.category] = categories.get(threat.category, 0) + 1
            
            # Track max threat level
            if threat.level.value == "critical":
                max_level = ThreatLevel.CRITICAL
            elif threat.level.value == "high" and max_level != ThreatLevel.CRITICAL:
                max_level = ThreatLevel.HIGH
            elif threat.level.value == "medium" and max_level not in [ThreatLevel.CRITICAL, ThreatLevel.HIGH]:
                max_level = ThreatLevel.MEDIUM
        
        return {
            "total_threats": len(self.threats_found),
            "threat_levels": threat_levels,
            "categories": categories,
            "is_safe": max_level not in [ThreatLevel.CRITICAL, ThreatLevel.HIGH],
            "max_threat_level": max_level.value,
            "threats": [
                {
                    "level": threat.level.value,
                    "category": threat.category,
                    "description": threat.description,
                    "line_number": threat.line_number,
                    "mitigation": threat.mitigation
                }
                for threat in self.threats_found
            ]
        }


def scan_for_malicious_code(code: str, filename: str = "<string>") -> Dict[str, Any]:
    """
    Convenience function to scan code for malicious patterns
    
    Args:
        code: Python source code to scan
        filename: Optional filename for better error reporting
        
    Returns:
        Threat analysis summary
        
    Raises:
        SecurityError: If critical threats are found
    """
    detector = MaliciousCodeDetector()
    threats = detector.analyze_code(code, filename)
    summary = detector.get_threat_summary()
    
    # Block execution if critical or high threats found
    if not summary["is_safe"]:
        critical_threats = [t for t in threats if t.level in [ThreatLevel.CRITICAL, ThreatLevel.HIGH]]
        threat_descriptions = [f"Line {t.line_number}: {t.description}" for t in critical_threats[:3]]
        
        raise SecurityError(
            f"Malicious code detected - {len(critical_threats)} critical/high threats found:\n" +
            "\n".join(threat_descriptions) +
            ("\n... and more" if len(critical_threats) > 3 else "")
        )
    
    # Log medium/low threats for monitoring
    if summary["total_threats"] > 0:
        log_warning(f"Code analysis found {summary['total_threats']} potential security issues")
        for threat in threats[:5]:  # Log first 5
            log_info(f"Security issue: {threat.description} (Line {threat.line_number})")
    
    return summary