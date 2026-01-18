"""
Enhanced Watermark Integration with Fail-Secure Behavior

Enhanced watermarking service that fails secure instead of fail-open to preserve
business trust. Addresses functionality_issues.txt concern about fail-open behavior
undermining business trust.
"""
import asyncio
import httpx
import hashlib
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
import logging

from app.utils.logging_utils import log_info, log_error, log_warning, log_exception
from app.errors import WatermarkError, SecurityError
from app.core.config import settings

logger = logging.getLogger(__name__)


class EnhancedWatermarkIntegration:
    """
    Enhanced watermark integration with fail-secure behavior.
    
    Key improvements:
    - Fail-secure behavior preserves business trust
    - Comprehensive validation of watermark integrity
    - Audit trail for compliance and security
    - Circuit breaker for service resilience
    - Performance monitoring and metrics
    """
    
    def __init__(self):
        self.http_client = None
        self._watermark_cache = {}
        self._cache_ttl = 300  # 5 minutes
        self._service_failures = 0
        self._max_failures = 3
        self._circuit_breaker_open = False
        self._circuit_reset_time = 0
        self._audit_records = []
        
    async def initialize(self):
        """Initialize watermark service with HTTP client."""
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            limits=httpx.Limits(max_connections=10)
        )
    
    async def apply_watermark_secure(
        self,
        signal_data: Dict[str, Any],
        user_id: str,
        stream_key: str,
        require_watermark: bool = True
    ) -> Dict[str, Any]:
        """
        Apply watermark with fail-secure behavior.
        
        Args:
            signal_data: Signal payload to watermark
            user_id: User identifier for watermarking
            stream_key: Stream identifier
            require_watermark: Whether watermarking is required (default: True)
            
        Returns:
            Watermarked signal data
            
        Raises:
            SecurityError: On authentication/authorization failures
            WatermarkError: On service or validation failures
        """
        start_time = time.time()
        
        try:
            # Check if watermarking is required
            if not require_watermark:
                log_info(f"Watermarking skipped for user {user_id} on stream {stream_key}")
                return signal_data
            
            # Check circuit breaker
            if self._is_circuit_breaker_open():
                raise WatermarkError("Watermark service circuit breaker is open - failing secure")
            
            # Validate prerequisites
            await self._validate_watermark_prerequisites(user_id, stream_key)
            
            # Get gateway secret with fail-secure validation
            gateway_secret = await self._get_gateway_secret_secure()
            
            # Check cache first (for performance)
            cache_key = self._generate_cache_key(signal_data, user_id)
            cached_result = self._get_cached_watermark(cache_key)
            if cached_result:
                log_info(f"Using cached watermark for user {user_id}")
                return cached_result
            
            # Apply watermark via service
            watermarked_data = await self._apply_watermark_via_service(
                signal_data, user_id, stream_key, gateway_secret
            )
            
            # Validate watermark integrity
            if not self._validate_watermark_integrity(watermarked_data, signal_data):
                raise WatermarkError("Watermark integrity validation failed")
            
            # Cache successful result
            self._cache_watermarked_data(cache_key, watermarked_data)
            
            # Create audit record
            self._create_audit_record({
                "action": "watermark_applied",
                "signal_id": signal_data.get("signal_id"),
                "user_id": user_id,
                "stream_key": stream_key,
                "success": True,
                "duration_ms": (time.time() - start_time) * 1000
            })
            
            # Reset circuit breaker on success
            self._service_failures = 0
            
            log_info(f"Successfully watermarked signal for user {user_id} on stream {stream_key}")
            return watermarked_data
            
        except (SecurityError, WatermarkError):
            # Re-raise security and watermark errors (fail-secure)
            self._record_failure(user_id, stream_key, signal_data)
            raise
            
        except Exception as e:
            # Any unexpected error should fail secure
            log_exception(f"Unexpected watermarking error for user {user_id}: {e}")
            self._record_failure(user_id, stream_key, signal_data)
            
            raise WatermarkError(f"Watermarking failed due to unexpected error: {e}")
    
    async def _validate_watermark_prerequisites(self, user_id: str, stream_key: str):
        """Validate prerequisites for watermarking."""
        if not user_id or not user_id.strip():
            raise SecurityError("User ID is required for watermarking")
        
        if not stream_key or not stream_key.strip():
            raise SecurityError("Stream key is required for watermarking")
        
        # Additional validation can be added here
        if len(user_id) < 3:
            raise SecurityError("Invalid user ID format")
    
    async def _get_gateway_secret_secure(self) -> str:
        """Get gateway secret with fail-secure validation."""
        try:
            # Only accept from config service - no fallbacks
            if not hasattr(settings, 'gateway_secret'):
                raise SecurityError("GATEWAY_SECRET not configured in config service")
            
            gateway_secret = settings.gateway_secret
            
            if not gateway_secret or not gateway_secret.strip():
                raise SecurityError("GATEWAY_SECRET is empty in config service")
            
            if len(gateway_secret) < 16:
                raise SecurityError("GATEWAY_SECRET is too short (minimum 16 characters required)")
            
            return gateway_secret
            
        except AttributeError:
            raise SecurityError("GATEWAY_SECRET not configured in config service")
        except Exception as e:
            raise SecurityError(f"Failed to get gateway secret from config service: {e}")
    
    async def _apply_watermark_via_service(
        self,
        signal_data: Dict[str, Any],
        user_id: str,
        stream_key: str,
        gateway_secret: str
    ) -> Dict[str, Any]:
        """Apply watermark via external service with fail-secure behavior."""
        
        try:
            # Prepare watermark request
            watermark_request = {
                "signal_data": signal_data,
                "user_id": user_id,
                "stream_key": stream_key,
                "timestamp": datetime.utcnow().isoformat(),
                "request_id": self._generate_request_id()
            }
            
            # Make request to watermark service
            response = await self.http_client.post(
                f"{settings.MARKETPLACE_SERVICE_URL}/api/v1/signals/watermark",
                json=watermark_request,
                headers={
                    "X-Gateway-Secret": gateway_secret,
                    "Content-Type": "application/json",
                    "User-Agent": "signal-service/watermark-client"
                }
            )
            
            # Handle response with fail-secure behavior
            if response.status_code == 401:
                raise SecurityError("Watermarking authentication failed - invalid gateway secret")
            elif response.status_code == 403:
                raise SecurityError("Watermarking authorization failed - user not authorized")
            elif response.status_code == 429:
                raise WatermarkError("Watermarking rate limit exceeded - service overloaded")
            elif response.status_code >= 500:
                raise WatermarkError("Watermark service unavailable - server error")
            elif response.status_code != 200:
                raise WatermarkError(f"Watermark service error: {response.status_code}")
            
            # Parse response with validation
            try:
                result = response.json()
            except (ValueError, json.JSONDecodeError):
                raise WatermarkError("Invalid watermark service response - malformed JSON")
            
            # Validate response structure
            if not isinstance(result, dict):
                raise WatermarkError("Invalid watermark service response - expected object")
            
            if "watermarked_payload" not in result:
                raise WatermarkError("Watermark service returned incomplete data - missing watermarked_payload")
            
            watermarked_data = result["watermarked_payload"]
            
            # Additional validation
            if not isinstance(watermarked_data, dict):
                raise WatermarkError("Invalid watermarked payload - expected object")
            
            # Ensure watermark metadata is present
            required_watermark_fields = ["_watermark", "_user_id", "_timestamp"]
            missing_fields = [field for field in required_watermark_fields if field not in watermarked_data]
            if missing_fields:
                raise WatermarkError(f"Incomplete watermark data - missing fields: {missing_fields}")
            
            return watermarked_data
            
        except httpx.TimeoutException:
            raise WatermarkError("Watermarking request timeout - service unavailable")
        except httpx.ConnectError:
            raise WatermarkError("Watermarking service unavailable - connection failed")
        except httpx.RequestError as e:
            raise WatermarkError(f"Watermarking request failed: {e}")
    
    def _validate_watermark_integrity(
        self, 
        watermarked_data: Dict[str, Any], 
        original_data: Dict[str, Any]
    ) -> bool:
        """Validate watermark integrity and consistency."""
        try:
            # Check required watermark fields
            if "_watermark" not in watermarked_data:
                log_error("Watermark integrity check failed - missing _watermark field")
                return False
            
            if "_user_id" not in watermarked_data:
                log_error("Watermark integrity check failed - missing _user_id field")
                return False
            
            # Verify original data is preserved
            original_signal_id = original_data.get("signal_id")
            watermarked_signal_id = watermarked_data.get("signal_id")
            
            if original_signal_id != watermarked_signal_id:
                log_error("Watermark integrity check failed - signal_id mismatch")
                return False
            
            # Additional integrity checks can be added here
            # For example, verifying checksum, timestamp validity, etc.
            
            return True
            
        except Exception as e:
            log_error(f"Watermark integrity validation error: {e}")
            return False
    
    def _is_circuit_breaker_open(self) -> bool:
        """Check if circuit breaker is open."""
        if not self._circuit_breaker_open:
            return False
        
        # Check if enough time has passed to attempt reset
        if time.time() > self._circuit_reset_time:
            self._circuit_breaker_open = False
            self._service_failures = 0
            log_info("Watermark service circuit breaker reset - attempting recovery")
            return False
        
        return True
    
    def _record_failure(self, user_id: str, stream_key: str, signal_data: Dict[str, Any]):
        """Record service failure and update circuit breaker."""
        self._service_failures += 1
        
        if self._service_failures >= self._max_failures:
            self._circuit_breaker_open = True
            self._circuit_reset_time = time.time() + 60  # 60 seconds
            log_warning(f"Watermark service circuit breaker opened after {self._service_failures} failures")
        
        # Create audit record for failure
        self._create_audit_record({
            "action": "watermark_failed",
            "signal_id": signal_data.get("signal_id"),
            "user_id": user_id,
            "stream_key": stream_key,
            "success": False,
            "failure_count": self._service_failures
        })
    
    def _generate_cache_key(self, signal_data: Dict[str, Any], user_id: str) -> str:
        """Generate cache key for watermarked data."""
        # Create cache key from signal content and user
        content_hash = hashlib.sha256(
            json.dumps(signal_data, sort_keys=True).encode()
        ).hexdigest()[:16]
        
        return f"watermark:{user_id}:{content_hash}"
    
    def _get_cached_watermark(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached watermarked data if valid."""
        if cache_key not in self._watermark_cache:
            return None
        
        cached_item = self._watermark_cache[cache_key]
        if time.time() - cached_item["timestamp"] > self._cache_ttl:
            del self._watermark_cache[cache_key]
            return None
        
        return cached_item["data"]
    
    def _cache_watermarked_data(self, cache_key: str, watermarked_data: Dict[str, Any]):
        """Cache watermarked data for performance."""
        self._watermark_cache[cache_key] = {
            "data": watermarked_data,
            "timestamp": time.time()
        }
        
        # Simple cache cleanup
        if len(self._watermark_cache) > 1000:
            self._cleanup_cache()
    
    def _cleanup_cache(self):
        """Clean up expired cache entries."""
        current_time = time.time()
        expired_keys = [
            key for key, value in self._watermark_cache.items()
            if current_time - value["timestamp"] > self._cache_ttl
        ]
        
        for key in expired_keys:
            del self._watermark_cache[key]
    
    def _generate_request_id(self) -> str:
        """Generate unique request ID for tracing."""
        return hashlib.sha256(
            f"{time.time()}:{id(self)}".encode()
        ).hexdigest()[:16]
    
    def _create_audit_record(self, event_data: Dict[str, Any]):
        """Create audit record for watermarking events."""
        audit_record = {
            "event_type": event_data["action"],
            "timestamp": datetime.utcnow().isoformat(),
            "signal_id": event_data.get("signal_id"),
            "user_id": event_data.get("user_id"),
            "stream_key": event_data.get("stream_key"),
            "success": event_data.get("success"),
            "duration_ms": event_data.get("duration_ms"),
            "failure_count": event_data.get("failure_count")
        }
        
        self._audit_records.append(audit_record)
        
        # Keep only recent audit records
        if len(self._audit_records) > 1000:
            self._audit_records = self._audit_records[-500:]
        
        log_info(f"Audit record created: {audit_record['event_type']} for signal {audit_record['signal_id']}")
    
    def get_audit_trail(self, user_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get audit trail for watermarking events."""
        records = self._audit_records
        
        if user_id:
            records = [r for r in records if r.get("user_id") == user_id]
        
        return records[-limit:]
    
    def get_service_health(self) -> Dict[str, Any]:
        """Get watermark service health information."""
        return {
            "circuit_breaker_open": self._circuit_breaker_open,
            "service_failures": self._service_failures,
            "cache_entries": len(self._watermark_cache),
            "cache_ttl_seconds": self._cache_ttl,
            "audit_records_count": len(self._audit_records),
            "next_circuit_reset": self._circuit_reset_time if self._circuit_breaker_open else None
        }
    
    def requires_watermark(self, user_tier: str, stream_type: str) -> bool:
        """Determine if watermarking is required based on user and stream."""
        # Premium users always require watermarking
        if user_tier.lower() in ["premium", "enterprise", "institutional"]:
            return True
        
        # Marketplace signals always require watermarking
        if "marketplace" in stream_type.lower() or "premium" in stream_type.lower():
            return True
        
        # Basic users on basic streams may not require watermarking
        return False
    
    async def close(self):
        """Clean up resources."""
        if self.http_client:
            await self.http_client.aclose()


# Global enhanced watermark service instance
_enhanced_watermark_service: Optional[EnhancedWatermarkIntegration] = None


async def get_enhanced_watermark_service() -> EnhancedWatermarkIntegration:
    """Get or create enhanced watermark service instance."""
    global _enhanced_watermark_service
    if _enhanced_watermark_service is None:
        _enhanced_watermark_service = EnhancedWatermarkIntegration()
        await _enhanced_watermark_service.initialize()
    return _enhanced_watermark_service