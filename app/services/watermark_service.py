"""
Watermark Service - Fail-Secure Implementation

Provides watermarking functionality with fail-secure behavior.
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class WatermarkValidationError(Exception):
    """Raised when watermark validation fails."""
    pass


class WatermarkService:
    """
    Watermark service with fail-secure behavior.
    
    Ensures that any watermark validation failures result in secure defaults
    rather than allowing unauthorized access.
    """
    
    def __init__(self):
        self.enabled = True
        self.strict_validation = True
    
    def apply_watermark(self, data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """
        Apply watermark to data with fail-secure behavior.
        
        Args:
            data: Data to watermark
            user_id: User identifier for watermark
            
        Returns:
            Watermarked data
            
        Raises:
            WatermarkValidationError: If watermarking fails (fail-secure)
        """
        try:
            if not self.enabled:
                logger.warning("Watermark service disabled - using fail-secure mode")
                raise WatermarkValidationError("Watermark service disabled")
            
            if not user_id:
                logger.error("Invalid user_id for watermarking")
                raise WatermarkValidationError("User identification required")
            
            # Add watermark metadata
            watermarked_data = data.copy()
            watermarked_data['_watermark'] = {
                'user_id': user_id,
                'timestamp': datetime.now().isoformat(),
                'service': 'signal-service'
            }
            
            logger.debug(f"Applied watermark for user {user_id}")
            return watermarked_data
            
        except Exception as e:
            logger.error(f"Watermark application failed: {e}")
            # Fail-secure: raise exception rather than returning unwatermarked data
            raise WatermarkValidationError(f"Watermarking failed: {e}")
    
    def validate_watermark(self, data: Dict[str, Any], expected_user_id: str) -> bool:
        """
        Validate watermark with fail-secure behavior.
        
        Args:
            data: Data with potential watermark
            expected_user_id: Expected user identifier
            
        Returns:
            True if watermark is valid
            
        Raises:
            WatermarkValidationError: If validation fails (fail-secure)
        """
        try:
            if not self.enabled:
                logger.warning("Watermark validation disabled - fail-secure mode")
                return False
            
            watermark = data.get('_watermark')
            if not watermark:
                logger.warning("No watermark found in data")
                return False
            
            stored_user_id = watermark.get('user_id')
            if stored_user_id != expected_user_id:
                logger.warning(f"Watermark user mismatch: {stored_user_id} != {expected_user_id}")
                return False
            
            logger.debug(f"Watermark validation passed for user {expected_user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Watermark validation failed: {e}")
            # Fail-secure: return False on any validation error
            return False
    
    def verify_integrity(self, data: Dict[str, Any]) -> bool:
        """
        Verify data integrity with fail-secure behavior.
        
        Args:
            data: Data to verify
            
        Returns:
            True if integrity check passes
        """
        try:
            if not self.strict_validation:
                return True
            
            watermark = data.get('_watermark')
            if not watermark:
                logger.warning("No watermark for integrity verification")
                return False
            
            # Verify required watermark fields
            required_fields = ['user_id', 'timestamp', 'service']
            for field in required_fields:
                if field not in watermark:
                    logger.warning(f"Missing watermark field: {field}")
                    return False
            
            # Verify service origin
            if watermark.get('service') != 'signal-service':
                logger.warning(f"Invalid service in watermark: {watermark.get('service')}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Integrity verification failed: {e}")
            # Fail-secure: return False on any error
            return False


# Global service instance
_watermark_service = None


def get_watermark_service() -> WatermarkService:
    """Get the global watermark service instance."""
    global _watermark_service
    if _watermark_service is None:
        _watermark_service = WatermarkService()
    return _watermark_service