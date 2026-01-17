"""
User Service Client for ACL and permission management
"""
import logging
import httpx
from typing import Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class UserServiceClient:
    """Client for communicating with the User Service for ACL operations"""
    
    def __init__(self):
        from app.core.config import settings
        self.base_url = settings.USER_SERVICE_URL
        self.timeout = 10.0
        
    async def get_user_permissions(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user permissions from user service"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/users/{user_id}/permissions"
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to get user permissions for {user_id}: {e}")
            raise
    
    def get_user_permissions_sync(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Synchronous version for non-async contexts"""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{self.base_url}/api/v1/users/{user_id}/permissions"
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to get user permissions for {user_id}: {e}")
            raise