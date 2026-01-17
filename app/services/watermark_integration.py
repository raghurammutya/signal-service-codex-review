"""
Signal Service Watermark Integration

Integrates with marketplace watermark service to add tracking
to marketplace signal streams for leak detection.
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import hashlib
import hmac
import os

from app.utils.logging_utils import log_info, log_error

logger = logging.getLogger(__name__)


class SignalWatermarkService:
    """
    Service for watermarking marketplace signals in the signal stream.
    
    This ensures all marketplace signals delivered through signal_service
    have proper watermarking for leak detection and forensics.
    
    SECURITY ARCHITECTURE:
    - verify_watermark() only checks for PRESENCE of _wm/_wm_ts fields
    - TRUE validation happens in detect_leak_and_enforce() via marketplace service
    - Enforcement policies in detect_leak_and_enforce() block delivery on detected leaks
    - Do NOT assume verify_watermark() provides cryptographic validation
    """
    
    def __init__(self):
        self._watermark_secret = None
        self._enforcement_enabled = True
        self._enforcement_policy = "auto-enforce"  # Default to strict anti-retransmission
        self._load_config()
        
    def _load_config(self):
        """Load watermark configuration"""
        try:
            # Get configuration from settings only - no environment variable fallbacks
            try:
                from app.core.config import settings
                if not hasattr(settings, 'environment'):
                    raise RuntimeError("Environment not configured in settings from config service")
                
                # Get watermark secret from settings (required for marketplace signals)
                if not hasattr(settings, 'WATERMARK_SECRET'):
                    raise RuntimeError("WATERMARK_SECRET not configured in config service")
                self._watermark_secret = settings.WATERMARK_SECRET
                
                # Get enforcement flag from settings
                if not hasattr(settings, 'WATERMARK_ENFORCEMENT_ENABLED'):
                    raise RuntimeError("WATERMARK_ENFORCEMENT_ENABLED not configured in config service")
                self._enforcement_enabled = settings.WATERMARK_ENFORCEMENT_ENABLED != "false"
                
                # Get enforcement policy from settings
                if not hasattr(settings, 'WATERMARK_ENFORCEMENT_POLICY'):
                    raise RuntimeError("WATERMARK_ENFORCEMENT_POLICY not configured in config service")
                policy = settings.WATERMARK_ENFORCEMENT_POLICY
                self._enforcement_policy = policy if policy in ["audit-only", "auto-enforce"] else "auto-enforce"
                
                log_info(f"Watermark service configured from config service - policy: {self._enforcement_policy}")
                
            except ImportError:
                # Config service integration required - no environment variable fallbacks
                raise RuntimeError("Config service unavailable and watermark configuration required - cannot operate without config service")
                    
        except Exception as e:
            log_error(f"Failed to load watermark config: {e}")
            # Service can continue but marketplace signals won't be watermarked
            
    def is_enabled(self) -> bool:
        """Check if watermarking is enabled and configured"""
        return bool(self._watermark_secret and self._enforcement_enabled)
        
    async def watermark_signal(
        self,
        stream_key: str,
        signal_data: Dict[str, Any],
        user_id: str,
        subscription_id: Optional[int] = None,
        signal_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Apply watermark to marketplace signal data by calling marketplace watermark service.
        
        Args:
            stream_key: The signal stream key (e.g., "marketplace:prod123:NIFTY50:momentum")
            signal_data: The signal data to watermark
            user_id: ID of the user receiving the signal
            subscription_id: Marketplace subscription ID (required for marketplace signals)
            signal_id: Signal ID for watermark tracking
            
        Returns:
            Watermarked signal data from marketplace service
        """
        if not self.is_enabled():
            # Watermarking not configured, return data as-is
            return signal_data
            
        # Check if this is a marketplace signal
        if not stream_key.startswith("marketplace:"):
            # Only watermark marketplace signals
            return signal_data
            
        if not subscription_id:
            log_error(f"Cannot watermark marketplace signal without subscription_id: {stream_key}")
            return signal_data
            
        if not signal_id:
            # Generate a collision-safe unique signal ID within PostgreSQL BIGINT limits
            import time
            import uuid
            
            # BIGINT max: 9,223,372,036,854,775,807 (19 digits)
            # Strategy: Use timestamp seconds (10 digits) + microseconds (6 digits) + random (3 digits)
            # Total: 19 digits, safely under BIGINT limit
            
            now = time.time()
            timestamp_sec = int(now)                          # ~10 digits (e.g., 1640995200)
            microseconds = int((now % 1) * 1000000)          # 0-999999 (6 digits)
            random_component = uuid.uuid4().int % 1000       # 0-999 (3 digits)
            
            # Construct: {timestamp_sec}{microseconds:06d}{random:03d}
            signal_id = int(f"{timestamp_sec}{microseconds:06d}{random_component:03d}")
            
            # Verify it's within BIGINT limits (safety check)
            if signal_id > 9223372036854775807:
                # Fallback: use just timestamp + random for safety
                signal_id = int(f"{timestamp_sec}{random_component:06d}")
                
            log_info(f"Generated BIGINT-safe signal_id {signal_id} for marketplace watermarking")
            
        try:
            import httpx
            
            # Get marketplace service URL
            from app.core.config import settings
            marketplace_url = settings.MARKETPLACE_SERVICE_URL
            
            # Get gateway secret for authentication
            gateway_secret = await self._get_gateway_secret()
            if not gateway_secret:
                log_error("Cannot watermark signal: gateway secret not available")
                return signal_data
            
            # Call marketplace watermark service
            async with httpx.AsyncClient() as client:
                watermark_request = {
                    "signal_id": signal_id,  # Now guaranteed to be a valid unique int
                    "subscription_id": subscription_id,
                    "payload": signal_data,
                    "algorithm": "hmac_sha256"
                }
                
                response = await client.post(
                    f"{marketplace_url}/api/v1/webhooks/drm/watermark",
                    json=watermark_request,
                    headers={
                        "X-Gateway-Secret": gateway_secret,
                        "Content-Type": "application/json"
                    },
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    watermarked_data = result.get("watermarked_payload", signal_data)
                    
                    log_info(
                        f"Watermarked marketplace signal via marketplace service: "
                        f"stream={stream_key}, user={user_id}, "
                        f"watermark={result.get('watermark_hash', 'unknown')[:16]}..."
                    )
                    
                    return watermarked_data
                else:
                    log_error(
                        f"Marketplace watermarking failed: {response.status_code} - {response.text}"
                    )
                    return signal_data
                    
        except Exception as e:
            log_error(f"Failed to watermark signal via marketplace service: {e}")
            # Return original data on error (fail open for availability)
            return signal_data
    
    async def _get_gateway_secret(self) -> Optional[str]:
        """Get gateway secret from config service settings only"""
        try:
            from app.core.config import settings
            if not hasattr(settings, 'gateway_secret') or not settings.gateway_secret:
                raise RuntimeError("GATEWAY_SECRET not configured in settings from config service")
            return settings.gateway_secret
        except Exception as e:
            raise RuntimeError(f"Failed to get gateway secret from config service: {e}")
            
    def verify_watermark(
        self,
        signal_data: Dict[str, Any],
        expected_user_id: str
    ) -> bool:
        """
        Verify if a signal has valid marketplace watermark.
        
        CRITICAL SECURITY NOTE: This method only checks for the PRESENCE of watermark
        fields (_wm/_wm_ts) but does NOT cryptographically validate their content.
        
        The security model relies ENTIRELY on:
        1. detect_leak_and_enforce() for marketplace leak detection
        2. Proper watermark generation at signal creation time
        3. Enforcement policies blocking delivery when leaks are detected
        
        This method ACCEPTS ANY _wm/_wm_ts watermark as valid, which means:
        - Forged watermarks will pass verification here
        - Watermarks for different users will pass verification here  
        - Invalid/corrupted watermarks will pass verification here
        
        TRUE VALIDATION occurs in detect_leak_and_enforce() via marketplace service
        verification. This method exists only to distinguish watermarked signals
        from non-watermarked (public) signals.
        
        DO NOT rely on this method for actual leak prevention - it provides a
        false sense of security. Use enforce policies in detect_leak_and_enforce().
        
        Args:
            signal_data: The signal data to verify
            expected_user_id: The user ID (not used in marketplace watermarks) 
            
        Returns:
            True if signal appears to have valid watermark or is public, False otherwise
        """
        if not self.is_enabled():
            # Watermarking not configured, skip verification
            return True
            
        try:
            # Extract watermark from metadata
            metadata = signal_data.get("metadata", {})
            
            # Check for marketplace watermark format (_wm/_wm_ts)
            marketplace_watermark = metadata.get("_wm")
            marketplace_timestamp = metadata.get("_wm_ts")
            
            if marketplace_watermark and marketplace_timestamp:
                # SECURITY WARNING: Signal has marketplace watermark - assume valid
                # WITHOUT cryptographic validation. This accepts ANY _wm/_wm_ts values.
                # True validation occurs in detect_leak_and_enforce() via marketplace service.
                log_info(f"Marketplace watermark detected: {marketplace_watermark[:8]}... (presence check only)")
                return True
            
            # Check for legacy watermark format (deprecated)
            legacy_watermark = metadata.get("_watermark", {})
            if legacy_watermark:
                log_info("Legacy watermark format detected")
                # Check if user ID matches (legacy verification)
                watermark_user = legacy_watermark.get("user_id")
                if watermark_user != expected_user_id:
                    log_error(
                        f"Legacy watermark verification failed: expected user {expected_user_id}, "
                        f"found {watermark_user}"
                    )
                    return False
                return True
            
            # No watermark found - might be public signal or pre-watermarked
            log_info("No watermark found in signal - assuming public/valid")
            return True
            
        except Exception as e:
            log_error(f"Failed to verify watermark: {e}")
            # Fail open for availability
            return True
    
    async def detect_leak_and_enforce(
        self,
        signal_data: Dict[str, Any],
        channel_id: str,
        receiving_user_id: str
    ) -> Dict[str, Any]:
        """
        Detect potential signal leaks and apply enforcement policy.
        
        Args:
            signal_data: The signal data to check for foreign watermarks
            channel_id: Channel where signal was received
            receiving_user_id: User receiving the signal
            
        Returns:
            Dict with detection results and enforcement actions taken
        """
        if not self.is_enabled():
            return {"leak_detected": False, "reason": "watermarking_disabled"}
        
        try:
            # Extract marketplace watermark from signal metadata
            metadata = signal_data.get("metadata", {})
            watermark_hash = metadata.get("_wm")
            watermark_timestamp = metadata.get("_wm_ts")
            
            if not watermark_hash:
                # No marketplace watermark found - not necessarily a leak (could be public signal)
                return {"leak_detected": False, "reason": "no_watermark"}
            
            # For marketplace watermarks, we can't determine the original user locally
            # We need to call the marketplace service to detect if this is a leak
            log_info(
                f"Marketplace watermark detected in channel {channel_id} for user {receiving_user_id}, "
                f"calling marketplace for leak detection"
            )
            
            # Initialize enforcement result - leak_detected will be set after marketplace verification
            enforcement_result = {
                "leak_detected": False,  # Will be updated after marketplace verification
                "receiving_user": receiving_user_id,
                "channel_id": channel_id,
                "watermark_hash": watermark_hash,
                "watermark_timestamp": watermark_timestamp,
                "enforcement_policy": self._enforcement_policy
            }
            
            if self._enforcement_policy == "audit-only":
                # Audit-only mode: Record potential leak but avoid marketplace calls
                # to prevent triggering marketplace auto-enforcement policies
                log_info(
                    f"AUDIT-ONLY: Marketplace watermark detected for user {receiving_user_id} "
                    f"in channel {channel_id} (watermark: {watermark_hash[:16]}...). "
                    f"Recording potential leak for audit trail without marketplace verification "
                    f"to avoid triggering marketplace auto-enforcement."
                )
                enforcement_result["leak_detected"] = False  # Cannot confirm without marketplace verification
                enforcement_result["action"] = "audit_recorded_potential"
                enforcement_result["reason"] = "audit_only_avoids_marketplace_enforcement"
                enforcement_result["marketplace_confirmed"] = False
                enforcement_result["severity"] = "medium"
                enforcement_result["audit_note"] = (
                    "Marketplace watermark detected but not verified to avoid "
                    "triggering marketplace enforcement in audit-only mode"
                )
                
            else:
                # Auto-enforce mode: Call marketplace for verification and enforcement
                try:
                    detection_result = await self._call_marketplace_enforcement(
                        signal_data, channel_id, receiving_user_id
                    )
                    
                    if detection_result.get("success") and detection_result.get("leak_detected"):
                        # Marketplace confirmed this is a leak and may have enforced
                        log_error(
                            f"AUTO-ENFORCE LEAK DETECTED: User {receiving_user_id} received leaked signal "
                            f"from user {detection_result.get('original_user', 'unknown')} "
                            f"(violation_id: {detection_result.get('violation_id')}). "
                            f"Marketplace enforcement may have been applied."
                        )
                        enforcement_result["leak_detected"] = True
                        enforcement_result["action"] = "leak_confirmed_enforced"
                        enforcement_result["violation_id"] = detection_result.get("violation_id")
                        enforcement_result["original_user"] = detection_result.get("original_user")
                        enforcement_result["marketplace_confirmed"] = True
                        enforcement_result["watermark_hash"] = detection_result.get("watermark_hash")
                        enforcement_result["severity"] = "critical"
                        # For auto-enforce mode, we should block delivery
                        enforcement_result["should_block"] = True
                        
                    elif detection_result.get("leak_detected") == False:
                        # No leak detected by marketplace - signal is legitimate
                        log_info(
                            f"MARKETPLACE VERIFIED: No leak detected for user {receiving_user_id}: "
                            f"{detection_result.get('reason', 'unknown')}"
                        )
                        enforcement_result["leak_detected"] = False
                        enforcement_result["action"] = "no_leak_detected"
                        enforcement_result["marketplace_reason"] = detection_result.get("reason")
                        enforcement_result["marketplace_confirmed"] = True
                        
                    else:
                        # Marketplace detection failed
                        log_error(
                            f"MARKETPLACE DETECTION FAILED for user {receiving_user_id}: "
                            f"{detection_result.get('error', 'Unknown error')}"
                        )
                        enforcement_result["leak_detected"] = False  # Fail safe - assume no leak on error
                        enforcement_result["action"] = "detection_failed"
                        enforcement_result["error"] = detection_result.get("error")
                        enforcement_result["marketplace_confirmed"] = False
                        
                except Exception as e:
                    log_error(f"Error calling marketplace detection: {e}")
                    enforcement_result["leak_detected"] = False  # Fail safe
                    enforcement_result["action"] = "detection_error"
                    enforcement_result["error"] = str(e)
                    enforcement_result["marketplace_confirmed"] = False
            
            return enforcement_result
            
        except Exception as e:
            log_error(f"Failed to detect leak and enforce: {e}")
            return {"leak_detected": False, "reason": "detection_error", "error": str(e)}
    
    async def _call_marketplace_enforcement(
        self,
        signal_data: Dict[str, Any],
        channel_id: str,
        violator_user_id: str
    ) -> Dict[str, Any]:
        """
        Call marketplace service to detect signal leak.
        
        Args:
            signal_data: Signal payload that may contain marketplace watermark
            channel_id: Channel where potential leak was detected
            violator_user_id: User who received the signal
            
        Returns:
            Dict with leak detection result
        """
        try:
            import httpx
            
            # Get marketplace service URL
            from app.core.config import settings
            marketplace_url = settings.MARKETPLACE_SERVICE_URL
            
            # Get gateway secret from settings only
            try:
                from app.core.config import settings
                if not hasattr(settings, 'gateway_secret') or not settings.gateway_secret:
                    return {"success": False, "error": "Gateway secret not configured in config service"}
                gateway_secret = settings.gateway_secret
            except Exception as e:
                return {"success": False, "error": f"Failed to get gateway secret from config service: {e}"}
            
            # Prepare leak detection request data 
            # Note: This function should only be called with signal_data that was already 
            # watermarked by the marketplace service, so it should contain metadata._wm
            if not signal_data.get("metadata", {}).get("_wm"):
                return {
                    "success": False,
                    "error": "Signal does not contain marketplace watermark (_wm). Cannot detect leak."
                }
            
            leak_detection_data = {
                "signal_payload": signal_data,  # Send full signal payload as received
                "channel_id": channel_id,
                "user_id": int(violator_user_id),
                "signal_id": None  # Optional[int] field
            }
            
            # Call marketplace leak detection API (this will auto-enforce if policy is enabled)
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{marketplace_url}/api/v1/webhooks/drm/detect-leak",
                    json=leak_detection_data,
                    headers={
                        "X-User-ID": "0",  # System user ID for automated detection
                        "X-Gateway-Secret": gateway_secret,
                        "Content-Type": "application/json"
                    },
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    # LeakDetectionResponse schema: leak_detected, reason, violation_id, original_channel, original_user, watermark_hash
                    leak_detected = result.get("leak_detected", False)
                    if leak_detected:
                        return {
                            "success": True,
                            "leak_detected": True,
                            "violation_id": result.get("violation_id"),
                            "original_user": result.get("original_user"),
                            "watermark_hash": result.get("watermark_hash"),
                            "reason": result.get("reason", "watermark_mismatch")
                        }
                    else:
                        return {
                            "success": False,
                            "leak_detected": False,
                            "reason": result.get("reason", "no_leak_detected")
                        }
                else:
                    return {
                        "success": False,
                        "error": f"Marketplace leak detection failed: {response.status_code} - {response.text}"
                    }
                    
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to call marketplace enforcement: {str(e)}"
            }


# Global instance
_watermark_service = None


def get_watermark_service() -> SignalWatermarkService:
    """Get or create watermark service instance"""
    global _watermark_service
    if _watermark_service is None:
        _watermark_service = SignalWatermarkService()
    return _watermark_service