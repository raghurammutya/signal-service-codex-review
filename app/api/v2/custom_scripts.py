"""
Custom Scripts API with Enhanced Sandboxing
Provides secure execution of user-submitted Python scripts
"""
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field, validator
import asyncio
import time
from datetime import datetime

from app.security.sandbox_enhancements import get_enhanced_sandbox
from app.security.sandbox_config import (
    create_sandbox_config, 
    SecurityLevel,
    get_security_level_for_user
)
from app.utils.logging_utils import log_info, log_warning, log_exception
from app.errors import SecurityError, ExternalFunctionExecutionError
from app.core.auth.gateway_trust import get_current_user_from_gateway

router = APIRouter(prefix="/custom-scripts", tags=["custom-scripts"])


class ScriptExecutionRequest(BaseModel):
    """Request model for script execution"""
    script_content: str = Field(..., max_length=10000, description="Python script to execute")
    function_name: str = Field(..., pattern=r'^[a-zA-Z_][a-zA-Z0-9_]*$', description="Function name to call")
    input_data: Dict[str, Any] = Field(default_factory=dict, description="Data to pass to function")
    
    # Security configuration
    security_level: Optional[str] = Field(None, description="Override security level")
    user_tier: str = Field("free", description="User subscription tier")
    environment: str = Field("production", description="Execution environment")
    
    # Custom limits (will be validated)
    custom_limits: Optional[Dict[str, Any]] = Field(None, description="Custom resource limits")
    
    @validator('script_content')
    def validate_script_content(cls, v):
        if not v.strip():
            raise ValueError("Script content cannot be empty")
        return v
    
    @validator('security_level')
    def validate_security_level(cls, v):
        if v and v not in ['minimal', 'standard', 'high', 'maximum']:
            raise ValueError("Invalid security level")
        return v


class ScriptExecutionResponse(BaseModel):
    """Response model for script execution"""
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_info: Dict[str, Any]
    security_info: Dict[str, Any]


class ScriptValidationRequest(BaseModel):
    """Request model for script validation"""
    script_content: str
    user_tier: str = "free"
    environment: str = "production"


class ScriptValidationResponse(BaseModel):
    """Response model for script validation"""
    valid: bool
    issues: List[str] = []
    security_level: str
    resource_limits: Dict[str, Any]
    allowed_features: List[str] = []


@router.post("/execute", response_model=ScriptExecutionResponse)
async def execute_script(
    request: ScriptExecutionRequest,
    background_tasks: BackgroundTasks,
    current_user: Dict[str, str] = Depends(get_current_user_from_gateway)
) -> ScriptExecutionResponse:
    """
    Execute custom Python script with enhanced sandboxing
    
    Security Features:
    - RestrictedPython compilation
    - Resource limits (memory, CPU, time)
    - Process isolation
    - Code validation
    - Real-time monitoring
    - Optional container isolation
    """
    execution_start = datetime.utcnow()
    
    try:
        # Get user tier from entitlement service instead of trusting user input
        from app.services.unified_entitlement_service import get_unified_entitlement_service
        entitlement_service = await get_unified_entitlement_service()
        user_data = await entitlement_service._get_user_entitlements(current_user["user_id"])
        actual_user_tier = user_data.get("tier", "free") if user_data else "free"
        
        log_info(f"Executing custom script: function={request.function_name}, tier={actual_user_tier} (verified)")
        
        # Create sandbox configuration using verified tier
        security_level = request.security_level or get_security_level_for_user(actual_user_tier).value
        
        sandbox_config = create_sandbox_config(
            environment=request.environment,
            user_tier=actual_user_tier,  # Use verified tier instead of user input
            custom_overrides=request.custom_limits
        )
        
        log_info(f"Sandbox config: {sandbox_config['security_level']}, limits={sandbox_config['policy']}")
        
        # Get enhanced sandbox
        sandbox = get_enhanced_sandbox()
        
        # Execute script with full security
        result = await sandbox.execute_script_safe(
            script_content=request.script_content,
            function_name=request.function_name,
            input_data=request.input_data,
            limits=sandbox_config['policy']
        )
        
        execution_time = (datetime.utcnow() - execution_start).total_seconds()
        
        # Publish results to signal stream contract if output should behave like indicators
        if request.input_data.get("publish_to_stream", True) and request.input_data.get("instrument_key"):
            background_tasks.add_task(
                _publish_script_results_to_stream,
                result,
                request.function_name,
                request.input_data.get("instrument_key"),
                actual_user_tier,  # Use verified tier instead of user input
                current_user["user_id"]  # Use gateway-authenticated user ID (trusted)
            )
        
        # Log successful execution in background
        background_tasks.add_task(
            _log_execution_audit,
            actual_user_tier,  # Use verified tier instead of user input
            request.function_name,
            execution_time,
            sandbox_config['security_level'],
            success=True
        )
        
        return ScriptExecutionResponse(
            success=True,
            result=result,
            execution_info={
                'execution_time_seconds': execution_time,
                'function_name': request.function_name,
                'input_data_size': len(str(request.input_data)),
                'script_lines': len(request.script_content.split('\\n')),
                'timestamp': execution_start.isoformat()
            },
            security_info={
                'security_level': sandbox_config['security_level'],
                'resource_limits': {
                    'memory_mb': sandbox_config['policy']['memory_limit_mb'],
                    'cpu_seconds': sandbox_config['policy']['cpu_time_seconds'],
                    'wall_seconds': sandbox_config['policy']['wall_time_seconds']
                },
                'isolation_method': _get_isolation_method(sandbox_config['policy']),
                'monitoring_enabled': sandbox_config['policy']['monitoring_enabled']
            }
        )
        
    except SecurityError as e:
        log_warning(f"Script execution blocked by security: {e}")
        
        background_tasks.add_task(
            _log_security_violation,
            request.user_tier,
            request.function_name,
            str(e)
        )
        
        raise HTTPException(
            status_code=403,
            detail=f"Script execution blocked by security policy: {str(e)}"
        )
        
    except ExternalFunctionExecutionError as e:
        log_exception(f"Script execution failed: {e}")
        
        execution_time = (datetime.utcnow() - execution_start).total_seconds()
        background_tasks.add_task(
            _log_execution_audit,
            request.user_tier,
            request.function_name,
            execution_time,
            security_level,
            success=False,
            error=str(e)
        )
        
        return ScriptExecutionResponse(
            success=False,
            error=str(e),
            execution_info={
                'execution_time_seconds': execution_time,
                'function_name': request.function_name,
                'timestamp': execution_start.isoformat()
            },
            security_info={
                'security_level': security_level,
                'execution_blocked': True
            }
        )
        
    except Exception as e:
        log_exception(f"Unexpected error during script execution: {e}")
        
        raise HTTPException(
            status_code=500,
            detail="Internal server error during script execution"
        )


@router.post("/validate", response_model=ScriptValidationResponse)
async def validate_script(request: ScriptValidationRequest) -> ScriptValidationResponse:
    """
    Validate custom Python script without executing it
    
    Returns:
    - Validation status
    - Security issues
    - Resource limits that would be applied
    - Allowed features for user tier
    """
    try:
        # Create sandbox configuration for validation
        sandbox_config = create_sandbox_config(
            environment=request.environment,
            user_tier=request.user_tier
        )
        
        # Get sandbox for validation
        sandbox = get_enhanced_sandbox()
        
        # Validate script
        issues = []
        
        try:
            # Try enhanced validation
            sandbox._validate_enhanced_script(
                request.script_content, 
                sandbox_config['policy']
            )
        except SecurityError as e:
            issues.append(str(e))
        
        # Additional validation checks
        lines = request.script_content.split('\\n')
        if len(lines) > sandbox_config['policy']['max_script_lines']:
            issues.append(f"Too many lines: {len(lines)} > {sandbox_config['policy']['max_script_lines']}")
        
        # Check for required function
        if f"def " not in request.script_content:
            issues.append("No function definition found")
        
        is_valid = len(issues) == 0
        
        return ScriptValidationResponse(
            valid=is_valid,
            issues=issues,
            security_level=sandbox_config['security_level'],
            resource_limits={
                'memory_mb': sandbox_config['policy']['memory_limit_mb'],
                'cpu_seconds': sandbox_config['policy']['cpu_time_seconds'],
                'wall_seconds': sandbox_config['policy']['wall_time_seconds'],
                'max_lines': sandbox_config['policy']['max_script_lines']
            },
            allowed_features=[
                'basic_math',
                'string_operations', 
                'list_operations',
                'conditional_logic',
                'loops',
                'function_definitions'
            ] + sandbox_config['policy']['allowed_imports']
        )
        
    except Exception as e:
        log_exception(f"Script validation failed: {e}")
        
        raise HTTPException(
            status_code=500,
            detail="Script validation failed"
        )


@router.get("/security-info")
async def get_security_info() -> Dict[str, Any]:
    """
    Get information about sandbox security capabilities
    """
    try:
        sandbox = get_enhanced_sandbox()
        security_report = sandbox.get_security_report()
        
        # Add tier-based limits
        tier_limits = {}
        for tier in ['free', 'basic', 'professional', 'enterprise']:
            config = create_sandbox_config('production', tier)
            tier_limits[tier] = {
                'memory_mb': config['policy']['memory_limit_mb'],
                'cpu_seconds': config['policy']['cpu_time_seconds'],
                'wall_seconds': config['policy']['wall_time_seconds'],
                'max_lines': config['policy']['max_script_lines'],
                'security_level': config['security_level']
            }
        
        return {
            'sandbox_capabilities': security_report,
            'tier_limits': tier_limits,
            'supported_environments': ['development', 'testing', 'staging', 'production'],
            'security_levels': ['minimal', 'standard', 'high', 'maximum'],
            'isolation_methods': [
                'restricted_python',
                'process_limits',
                'cgroups_v2',
                'docker_containers'
            ]
        }
        
    except Exception as e:
        log_exception(f"Failed to get security info: {e}")
        raise HTTPException(status_code=500, detail="Failed to get security information")


@router.get("/examples")
async def get_script_examples() -> Dict[str, Any]:
    """
    Get example scripts for different user tiers and use cases
    """
    return {
        'examples': {
            'simple_calculation': {
                'description': 'Basic mathematical calculation',
                'tier': 'free',
                'script': '''def calculate_average(data, params):
    """Calculate average of a list of numbers"""
    if 'numbers' not in data:
        return {'error': 'numbers field required'}
    
    numbers = data['numbers']
    if not numbers:
        return {'error': 'empty numbers list'}
    
    return {
        'average': sum(numbers) / len(numbers),
        'count': len(numbers),
        'sum': sum(numbers)
    }''',
                'example_input': {'numbers': [1, 2, 3, 4, 5]}
            },
            
            'price_analysis': {
                'description': 'Basic price trend analysis',
                'tier': 'basic',
                'script': '''def analyze_price_trend(data, params):
    """Analyze price trend from OHLC data"""
    if 'prices' not in data:
        return {'error': 'prices field required'}
    
    prices = data['prices']
    if len(prices) < 2:
        return {'error': 'need at least 2 prices'}
    
    # Calculate simple trend
    first_price = prices[0]
    last_price = prices[-1]
    change_percent = ((last_price - first_price) / first_price) * 100
    
    # Determine trend
    if change_percent > 5:
        trend = 'strong_up'
    elif change_percent > 1:
        trend = 'up'
    elif change_percent < -5:
        trend = 'strong_down'
    elif change_percent < -1:
        trend = 'down'
    else:
        trend = 'sideways'
    
    return {
        'trend': trend,
        'change_percent': round(change_percent, 2),
        'first_price': first_price,
        'last_price': last_price,
        'price_count': len(prices)
    }''',
                'example_input': {'prices': [100, 102, 105, 103, 108]}
            },
            
            'risk_calculation': {
                'description': 'Advanced risk metrics calculation',
                'tier': 'professional',
                'script': '''def calculate_risk_metrics(data, params):
    """Calculate various risk metrics"""
    import math
    import statistics
    
    if 'returns' not in data:
        return {'error': 'returns field required'}
    
    returns = data['returns']
    if len(returns) < 10:
        return {'error': 'need at least 10 return observations'}
    
    # Calculate metrics
    mean_return = statistics.mean(returns)
    std_dev = statistics.stdev(returns)
    
    # Sharpe ratio (assuming 0 risk-free rate)
    sharpe_ratio = mean_return / std_dev if std_dev > 0 else 0
    
    # Value at Risk (95% confidence)
    sorted_returns = sorted(returns)
    var_95 = sorted_returns[int(len(returns) * 0.05)]
    
    # Maximum drawdown
    cumulative = []
    running_total = 0
    for ret in returns:
        running_total += ret
        cumulative.append(running_total)
    
    max_dd = 0
    peak = cumulative[0]
    for val in cumulative:
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak != 0 else 0
        if dd > max_dd:
            max_dd = dd
    
    return {
        'mean_return': round(mean_return, 4),
        'volatility': round(std_dev, 4),
        'sharpe_ratio': round(sharpe_ratio, 4),
        'var_95': round(var_95, 4),
        'max_drawdown': round(max_dd, 4),
        'observations': len(returns)
    }''',
                'example_input': {'returns': [0.01, -0.02, 0.03, 0.005, -0.015, 0.02, -0.01, 0.025, -0.005, 0.015]}
            }
        },
        'usage_tips': [
            'Start with simple examples and gradually increase complexity',
            'Test scripts with validate endpoint before execution',
            'Use appropriate user tier for required features',
            'Check resource limits for your subscription level',
            'Handle errors gracefully in your scripts'
        ]
    }


# Background task functions
async def _log_execution_audit(
    user_tier: str,
    function_name: str, 
    execution_time: float,
    security_level: str,
    success: bool,
    error: Optional[str] = None
):
    """Log script execution for audit purposes"""
    log_info(
        f"Script execution audit: tier={user_tier}, function={function_name}, "
        f"time={execution_time:.3f}s, security={security_level}, success={success}, "
        f"error={error or 'none'}"
    )
    
    # In production, this would write to audit database
    # await audit_db.log_script_execution(user_tier, function_name, execution_time, security_level, success, error)


async def _log_security_violation(
    user_tier: str,
    function_name: str,
    violation: str
):
    """Log security violation for monitoring"""
    log_warning(
        f"Security violation: tier={user_tier}, function={function_name}, "
        f"violation={violation}"
    )
    
    # In production, this would trigger security alerts
    # await security_monitor.alert_violation(user_tier, function_name, violation)


def _get_isolation_method(policy: Dict[str, Any]) -> str:
    """Determine isolation method based on policy"""
    if policy.get('use_docker', False):
        return 'docker_container'
    elif policy.get('use_cgroups', False):
        return 'cgroups_v2'
    else:
        return 'process_limits'


async def _publish_script_results_to_stream(
    result: Dict[str, Any],
    function_name: str,
    instrument_key: Optional[str],
    user_tier: str,
    user_id: str
):
    """Publish custom script results to signal stream contract like indicators"""
    try:
        if not result or not instrument_key:
            log_warning("Skipping stream publish: missing result data or instrument_key")
            return
        
        # Import here to avoid circular dependencies
        from app.services.signal_delivery_service import get_signal_delivery_service
        from app.services.signal_stream_contract import StreamKeyFormat
        from app.utils.redis import get_redis_client
        
        # Create proper stream key using personal signal format from stream contract
        signal_id = f"custom_script_{function_name}"
        stream_key = StreamKeyFormat.create_personal_key(
            user_id=user_id,
            signal_id=signal_id,
            instrument=instrument_key,
            params={"function": function_name}
        )
        
        # Create signal data matching indicator format
        signal_data = {
            "signal_id": f"{signal_id}_{int(time.time())}",
            "signal_type": "personal",  # Use correct signal type from stream contract
            "instrument_key": instrument_key,
            "function_name": function_name,
            "result": result,
            "timestamp": datetime.utcnow().isoformat(),
            "source": "custom_script_execution",
            "user_tier": user_tier,
            "user_id": user_id
        }
        
        # Publish to Redis streams using proper stream key format
        redis_client = await get_redis_client()
        
        await redis_client.xadd(
            stream_key,
            signal_data
        )
        
        # Deliver to the script owner only (not system-wide broadcast)
        delivery_service = get_signal_delivery_service()
        
        # Create delivery config for personal custom signal
        delivery_config = {
            "channels": ["ui", "webhook"],  # Default channels for custom signals
            "priority": "medium",
            "metadata": {
                "signal_origin": "custom_script",
                "function_name": function_name,
                "personal_signal": True
            }
        }
        
        # Deliver to the script owner only
        delivery_result = await delivery_service.deliver_signal(
            user_id=user_id,  # Deliver to script owner, not system
            signal_data=signal_data,
            delivery_config=delivery_config
        )
        
        log_info(f"Published custom script results to personal stream: {stream_key}, delivery_success: {delivery_result.get('success', False)}")
        
    except Exception as e:
        log_exception(f"Failed to publish script results to stream: {e}")
        # Don't raise - this is a background task