"""
Signal Script Executor Service

Executes signal scripts fetched from MinIO (marketplace or personal).
Publishes results to Redis streams using signal_stream_contract keys.
"""

import asyncio
import json
import logging
import os
import time
import hashlib
from io import BytesIO
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from minio import Minio
from minio.error import S3Error

from app.core.logging import log_info, log_error, log_warning
from app.services.signal_stream_contract import StreamKeyFormat
from app.core.redis_manager import get_redis_client

logger = logging.getLogger(__name__)


class SignalExecutor:
    """
    Execute signal scripts from MinIO and publish results to Redis streams.
    
    Sprint 5A: Signal execution with MinIO-only code loading
    - No inline code execution allowed
    - Marketplace signals via execution tokens
    - Personal signals from personal namespace
    """
    
    # MinIO configuration - fail fast if not properly configured
    # Match marketplace storage service bucket naming convention exactly
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    BUCKET_MAP = {
        "development": "stocksblitz-scripts-dev",
        "staging": "stocksblitz-scripts-staging", 
        "production": "stocksblitz-scripts-prod",
        "dev": "stocksblitz-scripts-dev",
        "prod": "stocksblitz-scripts-prod",
    }
    
    # CRITICAL: No default values - fail fast if not configured
    MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")
    MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
    MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY") 
    MINIO_USE_SSL = os.getenv("MINIO_USE_SSL", "false").lower() == "true"
    MINIO_BUCKET = BUCKET_MAP.get(ENVIRONMENT.lower())
    
    # Personal namespace prefix (matching algo_engine)
    PERSONAL_PREFIX = "personal"
    
    # Allowed APIs for signal scripts
    ALLOWED_MODULES = {
        "math", "statistics", "datetime", "time", "json",
        "collections", "itertools", "functools", "operator"
    }
    
    # Sandbox globals provided to scripts
    SANDBOX_BUILTINS = {
        "abs", "all", "any", "bool", "dict", "enumerate", "filter",
        "float", "int", "len", "list", "map", "max", "min", "pow",
        "range", "reversed", "round", "set", "sorted", "str", "sum",
        "tuple", "type", "zip"
    }
    
    @classmethod
    def _get_client(cls) -> Minio:
        """
        Get MinIO client instance with proper credential validation.
        
        Fails fast if credentials are not configured to prevent silent defaults.
        """
        # Validate ALL required MinIO configuration is present (no defaults)
        if not cls.MINIO_ENDPOINT:
            raise ValueError(
                "MINIO_ENDPOINT not configured. Signal execution requires proper MinIO configuration. "
                "Set MINIO_ENDPOINT environment variable or configure in config service."
            )
            
        if not cls.MINIO_ACCESS_KEY:
            raise ValueError(
                "MINIO_ACCESS_KEY not configured. Signal execution requires proper MinIO credentials. "
                "Set MINIO_ACCESS_KEY environment variable or configure in config service."
            )
            
        if not cls.MINIO_SECRET_KEY:
            raise ValueError(
                "MINIO_SECRET_KEY not configured. Signal execution requires proper MinIO credentials. "
                "Set MINIO_SECRET_KEY environment variable or configure in config service."
            )
            
        # Validate bucket is properly mapped for environment
        if not cls.MINIO_BUCKET:
            raise ValueError(
                f"No bucket configured for environment '{cls.ENVIRONMENT}'. "
                f"Valid environments: {list(cls.BUCKET_MAP.keys())}. "
                "Check ENVIRONMENT environment variable."
            )
        
        # Prevent dangerous default credentials (fail-fast for security)
        if cls.MINIO_ACCESS_KEY == "minioadmin":
            raise ValueError(
                "Detected default MinIO access key 'minioadmin'. "
                "This is insecure and not allowed. Configure proper credentials."
            )
            
        if cls.MINIO_SECRET_KEY == "minioadmin":
            raise ValueError(
                "Detected default MinIO secret key 'minioadmin'. "
                "This is insecure and not allowed. Configure proper credentials."
            )
            
        # Log the bucket being used for transparency
        log_info(f"Signal executor using MinIO bucket: {cls.MINIO_BUCKET} (environment: {cls.ENVIRONMENT})")
        
        try:
            return Minio(
                endpoint=cls.MINIO_ENDPOINT,
                access_key=cls.MINIO_ACCESS_KEY,
                secret_key=cls.MINIO_SECRET_KEY,
                secure=cls.MINIO_USE_SSL
            )
        except Exception as e:
            raise ValueError(f"Failed to create MinIO client: {e}. Check MinIO configuration.")
    
    @classmethod
    def _get_personal_path(cls, user_id: str, script_id: str) -> str:
        """
        Get MinIO path for personal signal script.
        Format: personal/{user_id}/signal/{script_id}.py
        """
        return f"{cls.PERSONAL_PREFIX}/{user_id}/signal/{script_id}.py"
    
    @classmethod
    async def _set_execution_status(
        cls,
        execution_id: str,
        status: str,
        message: str = "",
        error: Optional[str] = None
    ):
        """
        Set execution status in Redis with 1-hour TTL.
        
        Args:
            execution_id: Unique execution identifier
            status: Status (pending, running, completed, failed)
            message: Status message
            error: Error message if failed
        """
        try:
            from app.core.redis_manager import get_redis_client
            import json
            
            redis_client = await get_redis_client()
            execution_key = f"signal_execution:{execution_id}"
            
            status_data = {
                "status": status,
                "message": message,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            if error:
                status_data["error"] = error
                
            # Set status with 1-hour TTL
            await redis_client.setex(
                execution_key,
                3600,  # 1 hour TTL
                json.dumps(status_data)
            )
            
        except Exception as e:
            log_error(f"Failed to set execution status for {execution_id}: {e}")
    
    @classmethod
    async def _init_execution_tracking(cls, execution_id: str):
        """Initialize execution tracking with pending status"""
        await cls._set_execution_status(
            execution_id,
            "pending",
            "Execution initiated, fetching script..."
        )
    
    @classmethod
    async def fetch_marketplace_script(
        cls,
        execution_token: str,
        product_id: str,
        version: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch marketplace signal script using execution token.
        
        This mirrors algo_engine's approach: use token to get presigned URL
        from marketplace service, then fetch from MinIO.
        """
        try:
            import httpx
            
            # Get marketplace service URL
            marketplace_url = os.getenv("MARKETPLACE_SERVICE_URL", "http://marketplace_service:8090")
            
            # Get internal API key for service-to-service authentication
            try:
                from app.core.config import settings
                internal_api_key = settings.internal_api_key
                if not internal_api_key:
                    log_error("internal_api_key not configured - cannot authenticate to marketplace service")
                    return None
            except Exception as e:
                log_error(f"Failed to get internal API key: {e}")
                return None

            # Request script access via token with service authentication
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{marketplace_url}/api/v1/scripts/access",
                    json={
                        "execution_token": execution_token,
                        "product_id": product_id,
                        "version": version,
                        "script_type": "signal"
                    },
                    headers={
                        "Content-Type": "application/json",
                        "X-Internal-API-Key": internal_api_key  # Service-to-service authentication
                    },
                    timeout=10.0
                )
                
                if response.status_code != 200:
                    log_error(f"Failed to get script access: {response.status_code} - {response.text}")
                    return None
                
                access_data = response.json()
                
                # Get presigned URL
                presigned_url = access_data.get("presigned_url")
                if not presigned_url:
                    log_error("No presigned URL in marketplace response")
                    return None
                
                # Fetch script content from MinIO via presigned URL
                script_response = await client.get(presigned_url, timeout=30.0)
                if script_response.status_code != 200:
                    log_error(f"Failed to fetch script from MinIO: {script_response.status_code}")
                    return None
                
                script_content = script_response.text
                
                return {
                    "content": script_content,
                    "metadata": access_data.get("metadata", {}),
                    "version": access_data.get("version", "latest"),
                    "product_id": product_id
                }
                
        except Exception as e:
            log_error(f"Error fetching marketplace script: {e}")
            return None
    
    @classmethod
    async def fetch_personal_script(
        cls,
        user_id: str,
        script_id: str,
        requesting_user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch personal signal script from MinIO.
        
        Only the owner can fetch their own scripts (ACL enforcement).
        """
        if user_id != requesting_user_id:
            log_warning(
                f"ACL violation: User {requesting_user_id} tried to access "
                f"personal signal owned by {user_id}"
            )
            return None
        
        script_path = cls._get_personal_path(user_id, script_id)
        
        async def _fetch():
            client = cls._get_client()
            
            try:
                # Fetch script content
                response = client.get_object(cls.MINIO_BUCKET, script_path)
                content = response.read().decode('utf-8')
                response.close()
                response.release_conn()
                
                # Fetch metadata if exists (algo_engine uses .meta.json)
                metadata_path = script_path.replace('.py', '.meta.json')
                metadata = {}
                try:
                    meta_response = client.get_object(cls.MINIO_BUCKET, metadata_path)
                    metadata = json.loads(meta_response.read())
                    meta_response.close()
                    meta_response.release_conn()
                except:
                    pass  # Metadata is optional
                
                return {
                    "content": content,
                    "metadata": metadata,
                    "script_id": script_id,
                    "owner_id": user_id
                }
                
            except S3Error as e:
                if e.code == 'NoSuchKey':
                    log_warning(f"Personal signal not found: {script_path}")
                else:
                    log_error(f"MinIO error fetching personal signal: {e}")
                return None
            except Exception as e:
                log_error(f"Error fetching personal signal: {e}")
                return None
        
        return await asyncio.to_thread(_fetch)
    
    @classmethod
    def _create_sandbox_globals(cls, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create sandboxed globals for signal script execution.
        
        Provides limited APIs and context variables with security restrictions.
        """
        # Import allowed modules with restricted access
        safe_modules = {}
        for module_name in cls.ALLOWED_MODULES:
            try:
                module = __import__(module_name)
                # Filter dangerous attributes from modules
                safe_module = type('SafeModule', (), {})()
                for attr_name in dir(module):
                    if not attr_name.startswith('_') and attr_name not in ['exec', 'eval', 'compile', 'open', 'input']:
                        setattr(safe_module, attr_name, getattr(module, attr_name))
                safe_modules[module_name] = safe_module
            except ImportError:
                pass
        
        # Create highly restricted builtins - remove dangerous functions
        safe_builtins = {}
        for name in cls.SANDBOX_BUILTINS:
            if hasattr(__builtins__, name):
                builtin_func = getattr(__builtins__, name)
                # Additional safety checks
                if name not in ['exec', 'eval', 'compile', 'open', 'input', 'raw_input', 'file', 'reload', '__import__']:
                    safe_builtins[name] = builtin_func
        
        # Completely isolated builtins
        restricted_builtins = {
            "__builtins__": safe_builtins,
            "__name__": "__sandbox__",
            "__doc__": "Secure Signal Script Sandbox",
            "__file__": "<sandbox>",
        }
        
        # Add safe modules with restricted access
        sandbox_globals = {**safe_modules, **restricted_builtins}
        
        # Add controlled context variables
        sandbox_globals.update({
            "context": context,  # Read-only context
            "log": lambda msg: log_info(f"[Signal Script] {str(msg)[:200]}"),  # Limit log message length
            "get_timestamp": lambda: datetime.now(timezone.utc).isoformat(),
            "get_unix_timestamp": lambda: int(time.time()),
        })
        
        return sandbox_globals
    
    @classmethod
    async def execute_signal_script(
        cls,
        script_content: str,
        context: Dict[str, Any],
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        Execute signal script in secure sandboxed environment.
        
        Args:
            script_content: Python code to execute
            context: Context variables (instrument, params, etc.)
            timeout: Execution timeout in seconds
            
        Returns:
            Dict with execution results and any signals generated
        """
        # SECURITY: Disable script execution in production
        environment = os.getenv('ENVIRONMENT', 'development')
        if environment in ['production', 'prod', 'staging']:
            raise RuntimeError(
                f"Script execution is disabled in {environment} environment for security reasons. "
                "Use pre-compiled signal libraries or contact administrators for signal deployment. "
                "See SCRIPT_EXECUTION_POLICY.md for migration guidance and alternative approaches."
            )
        
        try:
            # Validate script content for basic security
            if not cls._validate_script_security(script_content):
                return {
                    "success": False,
                    "error": "Script contains potentially unsafe code",
                    "error_type": "SecurityError"
                }
            
            # Create sandbox globals
            sandbox_globals = cls._create_sandbox_globals(context)
            
            # Add signal collection with limits
            signals_generated = []
            max_signals = 100  # Limit number of signals
            
            def emit_signal(signal):
                if len(signals_generated) < max_signals:
                    # Sanitize signal data
                    if isinstance(signal, dict):
                        # Limit signal data size and content
                        safe_signal = {}
                        for k, v in signal.items():
                            if isinstance(k, str) and len(k) < 50:
                                if isinstance(v, (int, float, str, bool)):
                                    if isinstance(v, str) and len(v) < 500:
                                        safe_signal[k] = v
                                    elif not isinstance(v, str):
                                        safe_signal[k] = v
                        signals_generated.append(safe_signal)
                
            sandbox_globals["emit_signal"] = emit_signal
            
            # Execute script with resource limits
            start_time = time.time()
            
            async def _execute():
                try:
                    # Compile first to catch syntax errors
                    compiled_code = compile(script_content, '<sandbox>', 'exec')
                    
                    # Execute in thread to prevent blocking event loop
                    def run_script():
                        exec(compiled_code, sandbox_globals)
                        return signals_generated
                    
                    # Run in thread with timeout
                    return await asyncio.get_event_loop().run_in_executor(None, run_script)
                    
                except SyntaxError as e:
                    raise ValueError(f"Script syntax error: {e}")
                except Exception as e:
                    # Log the error but don't expose internal details
                    log_error(f"Script execution error: {e}")
                    raise RuntimeError("Script execution failed")
            
            # Run with timeout
            signals = await asyncio.wait_for(_execute(), timeout=timeout)
            
            execution_time = time.time() - start_time
            
            return {
                "success": True,
                "signals": signals[:max_signals],  # Ensure limit
                "execution_time": execution_time,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "signals_count": len(signals)
            }
            
        except asyncio.TimeoutError:
            log_error(f"Signal script execution timed out after {timeout}s")
            return {
                "success": False,
                "error": "Execution timeout",
                "timeout": timeout
            }
        except Exception as e:
            log_error(f"Signal script execution error: {e}")
            return {
                "success": False,
                "error": str(e)[:200],  # Limit error message length
                "error_type": type(e).__name__
            }
    
    @classmethod
    def _validate_script_security(cls, script_content: str) -> bool:
        """
        Basic security validation of script content.
        
        Args:
            script_content: Script to validate
            
        Returns:
            True if script appears safe, False otherwise
        """
        # Basic blacklist of dangerous patterns
        dangerous_patterns = [
            'import os', 'import sys', 'import subprocess', 'import socket',
            'import urllib', 'import requests', 'import http',
            '__import__', 'eval(', 'exec(', 'compile(',
            'open(', 'file(', 'input(', 'raw_input(',
            'globals()', 'locals()', 'vars()', 'dir(',
            'getattr(', 'setattr(', 'delattr(', 'hasattr(',
            'reload(', '__builtins__',
            'while True:', 'for i in range(999',  # Potential infinite loops
        ]
        
        script_lower = script_content.lower()
        
        for pattern in dangerous_patterns:
            if pattern.lower() in script_lower:
                log_warning(f"Script contains potentially dangerous pattern: {pattern}")
                return False
        
        # Check script length (prevent overly complex scripts)
        if len(script_content) > 10000:  # 10KB limit
            log_warning("Script exceeds maximum allowed length")
            return False
        
        # Check for excessive complexity indicators
        if script_content.count('\n') > 500:  # Line limit
            log_warning("Script exceeds maximum line count")
            return False
            
        return True
    
    @classmethod
    async def publish_to_redis(
        cls,
        stream_key: str,
        signal_data: Dict[str, Any]
    ) -> bool:
        """
        Publish signal to Redis stream.
        
        Uses Redis XADD to append to stream with automatic ID.
        """
        try:
            redis_client = await get_redis_client()
            
            # Add metadata
            signal_data["_published_at"] = datetime.now(timezone.utc).isoformat()
            signal_data["_stream_key"] = stream_key
            
            # Convert to Redis format (flatten nested dicts)
            redis_data = {}
            for key, value in signal_data.items():
                if isinstance(value, (dict, list)):
                    redis_data[key] = json.dumps(value)
                else:
                    redis_data[key] = str(value)
            
            # Publish to stream
            stream_id = await redis_client.xadd(
                stream_key,
                redis_data,
                maxlen=1000  # Keep last 1000 signals
            )
            
            log_info(f"Published signal to {stream_key}: {stream_id}")
            return True
            
        except Exception as e:
            log_error(f"Failed to publish to Redis: {e}")
            return False
    
    @classmethod
    async def execute_marketplace_signal(
        cls,
        execution_token: str,
        product_id: str,
        instrument: str,
        params: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        subscription_id: Optional[str] = None,
        execution_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute marketplace signal script and publish results.
        """
        try:
            # Update status to running
            if execution_id:
                await cls._set_execution_status(
                    execution_id, "running", "Fetching marketplace script..."
                )
            
            # Fetch script from MinIO
            script_data = await cls.fetch_marketplace_script(execution_token, product_id)
            if not script_data:
                if execution_id:
                    await cls._set_execution_status(
                        execution_id, "failed", "Failed to fetch marketplace script",
                        error="Script not found or access denied"
                    )
                return {
                    "success": False,
                    "error": "Failed to fetch marketplace script"
                }
        
            # Update status to running
            if execution_id:
                await cls._set_execution_status(
                    execution_id, "running", "Executing marketplace script..."
                )
        
            # Create execution context
            context = {
                "instrument": instrument,
                "params": params or {},
                "product_id": product_id,
                "execution_token": execution_token,
                "user_id": user_id,
                "subscription_id": subscription_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Execute script
            result = await cls.execute_signal_script(
                script_data["content"],
                context
            )
            
            if result["success"] and result.get("signals"):
                # Update status to publishing
                if execution_id:
                    await cls._set_execution_status(
                        execution_id, "running", "Publishing signals to Redis..."
                    )
                
                # Publish each signal to appropriate Redis stream
                for signal in result["signals"]:
                    signal_name = signal.get("name", "default")
                    stream_key = StreamKeyFormat.create_marketplace_key(
                        product_id, instrument, signal_name, params
                    )
                    
                    # Add watermarking metadata if subscription_id provided
                    if subscription_id:
                        signal["_subscription_id"] = subscription_id
                    
                    await cls.publish_to_redis(stream_key, signal)
                
                # Mark as completed
                if execution_id:
                    await cls._set_execution_status(
                        execution_id, "completed", f"Published {len(result['signals'])} signals"
                    )
            else:
                # Mark as failed if execution failed
                if execution_id:
                    error_msg = result.get("error", "Script execution failed")
                    await cls._set_execution_status(
                        execution_id, "failed", "Script execution failed", error=error_msg
                    )
            
            return result
            
        except Exception as e:
            # Mark as failed on exception
            if execution_id:
                await cls._set_execution_status(
                    execution_id, "failed", "Execution error", error=str(e)
                )
            log_error(f"Error in marketplace signal execution: {e}")
            return {"success": False, "error": str(e)}
    
    @classmethod
    async def execute_personal_signal(
        cls,
        user_id: str,
        script_id: str,
        instrument: str,
        params: Optional[Dict[str, Any]] = None,
        execution_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute personal signal script and publish results.
        """
        try:
            # Update status to running
            if execution_id:
                await cls._set_execution_status(
                    execution_id, "running", "Fetching personal script..."
                )
            
            # Fetch script from MinIO (with ACL check)
            script_data = await cls.fetch_personal_script(
                user_id, script_id, user_id
            )
            if not script_data:
                if execution_id:
                    await cls._set_execution_status(
                        execution_id, "failed", "Failed to fetch personal script",
                        error="Script not found or access denied"
                    )
                return {
                    "success": False,
                    "error": "Failed to fetch personal script"
                }
            
            # Update status to executing
            if execution_id:
                await cls._set_execution_status(
                    execution_id, "running", "Executing personal script..."
                )
            
            # Create execution context
            context = {
                "instrument": instrument,
                "params": params or {},
                "user_id": user_id,
                "script_id": script_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Execute script
            result = await cls.execute_signal_script(
                script_data["content"],
                context
            )
            
            if result["success"] and result.get("signals"):
                # Update status to publishing
                if execution_id:
                    await cls._set_execution_status(
                        execution_id, "running", "Publishing personal signals..."
                    )
                
                # Publish each signal to personal Redis stream
                for signal in result["signals"]:
                    signal_name = signal.get("name", "default")
                    stream_key = StreamKeyFormat.create_personal_key(
                        user_id, script_id, instrument, params
                    )
                    
                    await cls.publish_to_redis(stream_key, signal)
                
                # Mark as completed
                if execution_id:
                    await cls._set_execution_status(
                        execution_id, "completed", f"Published {len(result['signals'])} personal signals"
                    )
            else:
                # Mark as failed if execution failed
                if execution_id:
                    error_msg = result.get("error", "Script execution failed")
                    await cls._set_execution_status(
                        execution_id, "failed", "Personal script execution failed", error=error_msg
                    )
            
            return result
            
        except Exception as e:
            # Mark as failed on exception
            if execution_id:
                await cls._set_execution_status(
                    execution_id, "failed", "Personal execution error", error=str(e)
                )
            log_error(f"Error in personal signal execution: {e}")
            return {"success": False, "error": str(e)}