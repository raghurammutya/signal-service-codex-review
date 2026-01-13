"""
Sandbox Configuration and Security Policies
Defines security policies and configuration for different execution environments
"""
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass


class SecurityLevel(Enum):
    """Security levels for custom script execution"""
    MINIMAL = "minimal"      # Basic RestrictedPython only
    STANDARD = "standard"    # Process limits + RestrictedPython  
    HIGH = "high"           # Cgroups + enhanced monitoring
    MAXIMUM = "maximum"     # Docker container isolation


class ExecutionEnvironment(Enum):
    """Execution environment types"""
    DEVELOPMENT = "development"
    TESTING = "testing" 
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass
class SandboxPolicy:
    """Sandbox security policy configuration"""
    security_level: SecurityLevel
    memory_limit_mb: int
    cpu_time_seconds: int
    wall_time_seconds: int
    max_processes: int
    network_access: bool
    file_write_access: bool
    max_script_lines: int
    max_file_size_kb: int
    allowed_imports: List[str]
    monitoring_enabled: bool
    audit_logging: bool


class SandboxConfigManager:
    """Manages sandbox configurations for different environments and use cases"""
    
    # Predefined security policies
    SECURITY_POLICIES = {
        SecurityLevel.MINIMAL: SandboxPolicy(
            security_level=SecurityLevel.MINIMAL,
            memory_limit_mb=32,
            cpu_time_seconds=2, 
            wall_time_seconds=5,
            max_processes=1,
            network_access=False,
            file_write_access=False,
            max_script_lines=50,
            max_file_size_kb=10,
            allowed_imports=['math', 'statistics'],
            monitoring_enabled=False,
            audit_logging=False
        ),
        
        SecurityLevel.STANDARD: SandboxPolicy(
            security_level=SecurityLevel.STANDARD,
            memory_limit_mb=64,
            cpu_time_seconds=5,
            wall_time_seconds=10, 
            max_processes=1,
            network_access=False,
            file_write_access=False,
            max_script_lines=100,
            max_file_size_kb=25,
            allowed_imports=['math', 'statistics', 'datetime'],
            monitoring_enabled=True,
            audit_logging=True
        ),
        
        SecurityLevel.HIGH: SandboxPolicy(
            security_level=SecurityLevel.HIGH,
            memory_limit_mb=128,
            cpu_time_seconds=10,
            wall_time_seconds=20,
            max_processes=1,
            network_access=False,
            file_write_access=False,
            max_script_lines=200,
            max_file_size_kb=50,
            allowed_imports=['math', 'statistics', 'datetime', 'decimal'],
            monitoring_enabled=True,
            audit_logging=True
        ),
        
        SecurityLevel.MAXIMUM: SandboxPolicy(
            security_level=SecurityLevel.MAXIMUM,
            memory_limit_mb=256,
            cpu_time_seconds=15,
            wall_time_seconds=30,
            max_processes=1,
            network_access=False,
            file_write_access=False,
            max_script_lines=500,
            max_file_size_kb=100,
            allowed_imports=['math', 'statistics', 'datetime', 'decimal', 'collections'],
            monitoring_enabled=True,
            audit_logging=True
        )
    }
    
    # Environment-specific defaults
    ENVIRONMENT_DEFAULTS = {
        ExecutionEnvironment.DEVELOPMENT: SecurityLevel.MINIMAL,
        ExecutionEnvironment.TESTING: SecurityLevel.STANDARD,
        ExecutionEnvironment.STAGING: SecurityLevel.HIGH,
        ExecutionEnvironment.PRODUCTION: SecurityLevel.MAXIMUM
    }
    
    def __init__(self, environment: ExecutionEnvironment = ExecutionEnvironment.PRODUCTION):
        self.environment = environment
        self.default_security_level = self.ENVIRONMENT_DEFAULTS[environment]
    
    def get_policy(self, security_level: Optional[SecurityLevel] = None) -> SandboxPolicy:
        """Get sandbox policy for specified security level"""
        level = security_level or self.default_security_level
        return self.SECURITY_POLICIES[level]
    
    def create_custom_policy(
        self,
        base_level: SecurityLevel,
        overrides: Dict[str, Any]
    ) -> SandboxPolicy:
        """Create custom policy based on existing level with overrides"""
        base_policy = self.SECURITY_POLICIES[base_level]
        
        # Create new policy with overrides
        policy_dict = {
            'security_level': base_level,
            'memory_limit_mb': overrides.get('memory_limit_mb', base_policy.memory_limit_mb),
            'cpu_time_seconds': overrides.get('cpu_time_seconds', base_policy.cpu_time_seconds),
            'wall_time_seconds': overrides.get('wall_time_seconds', base_policy.wall_time_seconds),
            'max_processes': overrides.get('max_processes', base_policy.max_processes),
            'network_access': overrides.get('network_access', base_policy.network_access),
            'file_write_access': overrides.get('file_write_access', base_policy.file_write_access),
            'max_script_lines': overrides.get('max_script_lines', base_policy.max_script_lines),
            'max_file_size_kb': overrides.get('max_file_size_kb', base_policy.max_file_size_kb),
            'allowed_imports': overrides.get('allowed_imports', base_policy.allowed_imports.copy()),
            'monitoring_enabled': overrides.get('monitoring_enabled', base_policy.monitoring_enabled),
            'audit_logging': overrides.get('audit_logging', base_policy.audit_logging)
        }
        
        return SandboxPolicy(**policy_dict)
    
    def validate_policy(self, policy: SandboxPolicy) -> List[str]:
        """Validate sandbox policy and return any issues"""
        issues = []
        
        # Check resource limits
        if policy.memory_limit_mb > 512:
            issues.append("Memory limit too high (max: 512MB)")
        
        if policy.cpu_time_seconds > 30:
            issues.append("CPU time limit too high (max: 30s)")
        
        if policy.wall_time_seconds > 60:
            issues.append("Wall time limit too high (max: 60s)")
        
        if policy.max_processes > 1:
            issues.append("Multiple processes not allowed")
        
        if policy.network_access and self.environment == ExecutionEnvironment.PRODUCTION:
            issues.append("Network access not allowed in production")
        
        if policy.file_write_access:
            issues.append("File write access not recommended")
        
        if policy.max_script_lines > 1000:
            issues.append("Script too large (max: 1000 lines)")
        
        # Check imports
        dangerous_imports = ['os', 'sys', 'subprocess', 'socket', 'urllib', 'requests']
        for imp in policy.allowed_imports:
            if imp in dangerous_imports:
                issues.append(f"Dangerous import not allowed: {imp}")
        
        return issues
    
    def get_environment_config(self) -> Dict[str, Any]:
        """Get complete environment configuration"""
        default_policy = self.get_policy()
        
        return {
            'environment': self.environment.value,
            'default_security_level': self.default_security_level.value,
            'default_policy': {
                'memory_limit_mb': default_policy.memory_limit_mb,
                'cpu_time_seconds': default_policy.cpu_time_seconds,
                'wall_time_seconds': default_policy.wall_time_seconds,
                'max_processes': default_policy.max_processes,
                'network_access': default_policy.network_access,
                'file_write_access': default_policy.file_write_access,
                'monitoring_enabled': default_policy.monitoring_enabled,
                'audit_logging': default_policy.audit_logging
            },
            'available_security_levels': [level.value for level in SecurityLevel],
            'policy_validation_enabled': True
        }


# User tier-based security mapping
USER_TIER_SECURITY = {
    'free': SecurityLevel.MINIMAL,
    'basic': SecurityLevel.STANDARD, 
    'professional': SecurityLevel.HIGH,
    'enterprise': SecurityLevel.MAXIMUM
}


def get_security_level_for_user(user_tier: str) -> SecurityLevel:
    """Get appropriate security level based on user subscription tier"""
    return USER_TIER_SECURITY.get(user_tier.lower(), SecurityLevel.MINIMAL)


def create_sandbox_config(
    environment: str = "production",
    user_tier: str = "free",
    custom_overrides: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create complete sandbox configuration for user request
    
    Args:
        environment: Execution environment (development, testing, staging, production)
        user_tier: User subscription tier (free, basic, professional, enterprise)
        custom_overrides: Custom policy overrides
        
    Returns:
        Complete sandbox configuration
    """
    env = ExecutionEnvironment(environment.lower())
    security_level = get_security_level_for_user(user_tier)
    
    config_manager = SandboxConfigManager(env)
    
    if custom_overrides:
        policy = config_manager.create_custom_policy(security_level, custom_overrides)
        
        # Validate custom policy
        validation_issues = config_manager.validate_policy(policy)
        if validation_issues:
            raise ValueError(f"Policy validation failed: {', '.join(validation_issues)}")
    else:
        policy = config_manager.get_policy(security_level)
    
    return {
        'environment': environment,
        'user_tier': user_tier,
        'security_level': security_level.value,
        'policy': {
            'memory_limit_mb': policy.memory_limit_mb,
            'cpu_time_seconds': policy.cpu_time_seconds,
            'wall_time_seconds': policy.wall_time_seconds,
            'max_processes': policy.max_processes,
            'network_access': policy.network_access,
            'file_write_access': policy.file_write_access,
            'max_script_lines': policy.max_script_lines,
            'max_file_size_kb': policy.max_file_size_kb,
            'allowed_imports': policy.allowed_imports,
            'monitoring_enabled': policy.monitoring_enabled,
            'audit_logging': policy.audit_logging,
            'use_docker': policy.security_level == SecurityLevel.MAXIMUM,
            'use_cgroups': policy.security_level in [SecurityLevel.HIGH, SecurityLevel.MAXIMUM]
        },
        'validation_passed': True,
        'config_version': '1.0'
    }


# Example configurations
EXAMPLE_CONFIGS = {
    'development_basic': create_sandbox_config('development', 'basic'),
    'production_enterprise': create_sandbox_config('production', 'enterprise'),
    'testing_professional': create_sandbox_config('testing', 'professional')
}