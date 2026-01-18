"""
Shared Metadata Utilities for Alert and Communications Services

Provides common metadata construction and signal data transformation
to eliminate duplication between service clients.
"""
from datetime import datetime
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class MetadataBuilder:
    """Utility class for building consistent metadata across services"""
    
    @staticmethod
    def build_signal_metadata(
        signal_data: Dict[str, Any], 
        metadata_type: str = "signal_notification",
        extra_fields: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Build standard signal metadata structure"""
        metadata = {
            "source": "signal_service",
            "type": metadata_type,
            "signal_id": signal_data.get("signal_id"),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Add strategy_id if available
        if signal_data.get("strategy_id"):
            metadata["strategy_id"] = signal_data.get("strategy_id")
        
        # Add any extra fields
        if extra_fields:
            metadata.update(extra_fields)
        
        return metadata
    
    @staticmethod
    def build_batch_metadata(
        batch_id: str,
        signal_id: Optional[str] = None,
        metadata_type: str = "batch_operation"
    ) -> Dict[str, Any]:
        """Build metadata for batch operations"""
        metadata = {
            "source": "signal_service",
            "type": metadata_type,
            "batch_id": batch_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if signal_id:
            metadata["signal_id"] = signal_id
        
        return metadata


class SignalDataTransformer:
    """Utility class for transforming signal data consistently"""
    
    @staticmethod
    def extract_template_data(
        signal_data: Dict[str, Any], 
        priority: str = "normal",
        include_user_info: bool = True
    ) -> Dict[str, Any]:
        """Extract and transform signal data for template rendering"""
        template_data = {
            "signal_type": signal_data.get("signal_type", "Signal"),
            "symbol": signal_data.get("symbol", "Unknown"),
            "instrument_key": signal_data.get("instrument_key"),
            "message": signal_data.get("message", "Signal notification"),
            "value": signal_data.get("value"),
            "timestamp": signal_data.get("timestamp", datetime.utcnow().isoformat()),
            "priority": priority
        }
        
        if include_user_info:
            template_data.update({
                "user_id": signal_data.get("user_id"),
                "signal_id": signal_data.get("signal_id")
            })
        
        return template_data
    
    @staticmethod
    def extract_condition_config(signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract signal data for alert condition configuration"""
        return {
            "signal_type": signal_data.get("signal_type"),
            "symbol": signal_data.get("symbol"),
            "instrument_key": signal_data.get("instrument_key"),
            "message": signal_data.get("message"),
            "value": signal_data.get("value"),
            "timestamp": signal_data.get("timestamp", datetime.utcnow().isoformat())
        }


class ServiceClientBase:
    """Base class for service clients with common functionality"""
    
    def __init__(self, service_name: str, default_port: int):
        self.service_name = service_name
        self.default_port = default_port
        self.session = None
        self._service_url = None
        self._internal_api_key = None
    
    def _get_service_url(self) -> str:
        """Get service URL from config with fallback"""
        if self._service_url is None:
            from app.core.config import settings
            url_setting = f"{self.service_name.upper()}_SERVICE_URL"
            default_url = f"http://{self.service_name.lower()}-service:{self.default_port}"
            self._service_url = getattr(settings, url_setting, default_url)
        return self._service_url
    
    def _get_internal_api_key(self) -> str:
        """Get internal API key for service-to-service authentication"""
        if self._internal_api_key is None:
            from app.core.config import settings
            api_key = getattr(settings, 'internal_api_key', None)
            if not api_key:
                raise ValueError("INTERNAL_API_KEY not configured in settings - required for service-to-service authentication")
            self._internal_api_key = api_key
        return self._internal_api_key
    
    async def ensure_session(self):
        """Ensure HTTP session is created with standard configuration"""
        if not self.session:
            import aiohttp
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={'X-Internal-API-Key': self._get_internal_api_key()}
            )
    
    async def close_session(self):
        """Clean up HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None


def build_service_response(
    success: bool, 
    data: Optional[Any] = None, 
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Build standardized service response format"""
    response = {
        "success": success,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if data is not None:
        response["data"] = data
    
    if error:
        response["error"] = error
    
    if metadata:
        response["metadata"] = metadata
    
    return response