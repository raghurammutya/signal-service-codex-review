"""
Algo Engine API Client

Replaces direct algo_engine imports with proper API delegation.
Follows Architecture v3.0 - API Delegation Era patterns.
"""
import logging
from typing import Dict, List, Optional, Any
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class AlgoEngineAPIError(Exception):
    """Exception raised for algo_engine API errors"""
    pass


class AlgoEngineClient:
    """
    Client for algo_engine service API calls.
    
    Replaces direct imports with HTTP API calls to maintain service boundaries.
    """
    
    def __init__(self):
        self.base_url = self._get_algo_engine_url()
        self.internal_api_key = self._get_internal_api_key()
        self.session: Optional[httpx.AsyncClient] = None
        self.timeout = 30.0
        
        logger.info("AlgoEngineClient initialized")
    
    def _get_algo_engine_url(self) -> str:
        """Get algo_engine service URL from config_service (Architecture Principle #1)"""
        try:
            from common.config_service.client import ConfigServiceClient
            
            config_client = ConfigServiceClient(
                service_name="signal_service",
                environment=settings.environment,
                timeout=5
            )
            
            algo_url = config_client.get_service_url("algo_engine")
            if not algo_url:
                raise ValueError("algo_engine service URL not found in config_service")
            return algo_url
            
        except Exception as e:
            raise RuntimeError(f"Failed to get algo_engine URL from config_service: {e}. No hardcoded fallbacks allowed per architecture.")
    
    def _get_internal_api_key(self) -> str:
        """Get internal API key for service-to-service authentication"""
        api_key = getattr(settings, 'internal_api_key', None)
        if not api_key:
            raise ValueError("INTERNAL_API_KEY not configured - required for algo_engine authentication")
        return api_key
    
    async def initialize(self):
        """Initialize HTTP session"""
        if not self.session:
            self.session = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.ClientTimeout(total=self.timeout),
                headers={
                    "X-Internal-API-Key": self.internal_api_key,
                    "User-Agent": "signal-service/1.0",
                    "Content-Type": "application/json"
                }
            )
    
    async def close(self):
        """Close HTTP session"""
        if self.session:
            await self.session.aclose()
            self.session = None
    
    async def list_personal_scripts(
        self, 
        user_id: str, 
        script_type: str = "signal",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List user's personal signal scripts via API.
        
        Replaces: from algo_engine.app.services.personal_script_service import PersonalScriptService
        
        Args:
            user_id: User ID
            script_type: Type of scripts to list
            limit: Maximum number of scripts
            
        Returns:
            List of script information dictionaries
        """
        try:
            await self.initialize()
            
            response = await self.session.get(
                f"/api/v1/users/{user_id}/scripts",
                params={
                    "type": script_type,
                    "limit": limit
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                scripts = data.get("scripts", [])
                logger.info(f"Retrieved {len(scripts)} personal scripts for user {user_id}")
                return scripts
            elif response.status_code == 404:
                logger.info(f"No personal scripts found for user {user_id}")
                return []
            else:
                logger.error(f"algo_engine API error: {response.status_code} - {response.text}")
                raise AlgoEngineAPIError(f"Failed to list scripts: {response.status_code}")
                
        except httpx.RequestError as e:
            logger.error(f"algo_engine service request failed: {e}")
            raise AlgoEngineAPIError(f"Network error contacting algo_engine: {e}")
        except Exception as e:
            logger.error(f"Unexpected error listing personal scripts: {e}")
            raise AlgoEngineAPIError(f"Failed to list personal scripts: {e}")
    
    async def get_script_details(
        self, 
        user_id: str, 
        script_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get details for a specific personal script.
        
        Args:
            user_id: User ID
            script_id: Script ID
            
        Returns:
            Script details or None if not found
        """
        try:
            await self.initialize()
            
            response = await self.session.get(
                f"/api/v1/users/{user_id}/scripts/{script_id}"
            )
            
            if response.status_code == 200:
                script_data = response.json()
                logger.debug(f"Retrieved script details: {script_id}")
                return script_data
            elif response.status_code == 404:
                logger.info(f"Script not found: {script_id}")
                return None
            else:
                logger.error(f"algo_engine API error: {response.status_code} - {response.text}")
                raise AlgoEngineAPIError(f"Failed to get script details: {response.status_code}")
                
        except httpx.RequestError as e:
            logger.error(f"algo_engine service request failed: {e}")
            raise AlgoEngineAPIError(f"Network error contacting algo_engine: {e}")
        except Exception as e:
            logger.error(f"Unexpected error getting script details: {e}")
            raise AlgoEngineAPIError(f"Failed to get script details: {e}")
    
    async def execute_script(
        self,
        user_id: str,
        script_id: str,
        execution_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a personal script with given context.
        
        Args:
            user_id: User ID
            script_id: Script ID to execute
            execution_context: Context data for execution
            
        Returns:
            Execution result
        """
        try:
            await self.initialize()
            
            response = await self.session.post(
                f"/api/v1/users/{user_id}/scripts/{script_id}/execute",
                json={
                    "context": execution_context,
                    "source": "signal_service"
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Successfully executed script {script_id} for user {user_id}")
                return result
            else:
                logger.error(f"Script execution failed: {response.status_code} - {response.text}")
                raise AlgoEngineAPIError(f"Script execution failed: {response.status_code}")
                
        except httpx.RequestError as e:
            logger.error(f"algo_engine service request failed: {e}")
            raise AlgoEngineAPIError(f"Network error contacting algo_engine: {e}")
        except Exception as e:
            logger.error(f"Unexpected error executing script: {e}")
            raise AlgoEngineAPIError(f"Failed to execute script: {e}")
    
    async def validate_script_access(
        self,
        user_id: str,
        script_id: str
    ) -> bool:
        """
        Validate if user has access to a specific script.
        
        Args:
            user_id: User ID
            script_id: Script ID
            
        Returns:
            True if user has access, False otherwise
        """
        try:
            await self.initialize()
            
            response = await self.session.get(
                f"/api/v1/users/{user_id}/scripts/{script_id}/access"
            )
            
            if response.status_code == 200:
                access_data = response.json()
                has_access = access_data.get("has_access", False)
                logger.debug(f"Script access check: {script_id} -> {has_access}")
                return has_access
            elif response.status_code == 404:
                logger.info(f"Script not found for access check: {script_id}")
                return False
            else:
                logger.error(f"Access check failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error checking script access: {e}")
            return False
    
    async def health_check(self) -> bool:
        """Check if algo_engine service is healthy"""
        try:
            await self.initialize()
            
            response = await self.session.get("/health")
            
            if response.status_code == 200:
                health_data = response.json()
                is_healthy = health_data.get("status") == "healthy"
                logger.debug(f"algo_engine health check: {is_healthy}")
                return is_healthy
            else:
                logger.warning(f"algo_engine health check failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"algo_engine health check error: {e}")
            return False


# Global client instance
_algo_engine_client: Optional[AlgoEngineClient] = None


async def get_algo_engine_client() -> AlgoEngineClient:
    """Get singleton algo_engine client instance"""
    global _algo_engine_client
    if _algo_engine_client is None:
        _algo_engine_client = AlgoEngineClient()
        await _algo_engine_client.initialize()
    return _algo_engine_client


async def cleanup_algo_engine_client():
    """Clean up algo_engine client"""
    global _algo_engine_client
    if _algo_engine_client:
        await _algo_engine_client.close()
        _algo_engine_client = None
