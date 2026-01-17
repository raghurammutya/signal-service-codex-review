"""
Marketplace Client for Signal Service

Sprint 5A: Client for verifying marketplace execution tokens
and checking user entitlements for premium signals.
"""
import httpx
import logging
import os
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class MarketplaceClient:
    """
    Client for marketplace_service integration in signal_service.
    
    Handles:
    - Execution token verification
    - Entitlement checking for premium signals
    """
    
    def __init__(self, base_url: str, internal_api_key: str, timeout: float = 10.0):
        """
        Initialize marketplace client.
        
        Args:
            base_url: Marketplace service URL
            internal_api_key: Internal API key for service-to-service auth
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.internal_api_key = internal_api_key
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={
                "X-Internal-API-Key": self.internal_api_key,
                "Content-Type": "application/json"
            }
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None
            
    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={
                    "X-Internal-API-Key": self.internal_api_key,
                    "Content-Type": "application/json"
                }
            )
        return self._client
        
    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def verify_execution_token(
        self,
        token: str,
        product_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Verify marketplace execution token for a user and product.
        
        Args:
            token: Execution token to verify
            product_id: Marketplace product ID
            user_id: User ID requesting access
            
        Returns:
            Dict with:
                - is_valid: bool (whether token is valid)
                - product_id: str (verified product ID)
                - user_id: str (verified user ID)
                - expires_at: str (token expiration)
                
        Raises:
            Exception: If verification request fails
        """
        client = self._get_client()
        
        try:
            # Call marketplace service to verify token
            response = await client.post(
                "/api/v1/integration/verify-execution-token",
                json={
                    "execution_token": token,
                    "product_id": product_id,
                    "user_id": user_id
                }
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(
                    f"Token verification failed: {response.status_code} - {response.text}"
                )
                return {"is_valid": False}
                
        except Exception as e:
            logger.error(f"Error verifying execution token: {e}")
            return {"is_valid": False}
    
    async def get_product_signals(
        self,
        product_id: str,
        user_id: str,
        execution_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get available signals for a marketplace product.
        
        Args:
            product_id: Marketplace product ID
            user_id: User requesting signal metadata
            execution_token: Optional execution token for premium access
            
        Returns:
            Dict with signal metadata:
                - signals: List of signal groups with indicators
                - requires_subscription: bool
                - has_active_subscription: bool
                
        Raises:
            Exception: If request fails
        """
        client = self._get_client()
        
        try:
            # Use gateway headers for authentication since marketplace API requires it
            # Get the real gateway secret from config_service (Architecture Principle #1: Config service exclusivity)
            try:
                from common.config_service.client import ConfigServiceClient
                from app.core.config import settings
                
                config_client = ConfigServiceClient(
                    service_name="signal_service",
                    environment=settings.environment,
                    timeout=5
                )
                gateway_secret = config_client.get_secret("GATEWAY_SECRET")
                if not gateway_secret:
                    raise ValueError("GATEWAY_SECRET not found in config_service")
            except Exception as e:
                raise RuntimeError(f"Failed to get gateway secret from config_service: {e}. No environment fallbacks allowed per architecture.")
                
            headers = {
                "X-User-ID": user_id,
                "X-Gateway-Secret": gateway_secret,
            }
            if execution_token:
                headers["X-Execution-Token"] = execution_token
            
            # Call marketplace service for product signals (no params needed, user in headers)
            response = await client.get(
                f"/api/v1/products/{product_id}/signals",
                headers=headers
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(
                    f"Get product signals failed: {response.status_code} - {response.text}"
                )
                return {"signals": []}
                
        except Exception as e:
            logger.error(f"Error fetching product signals: {e}")
            return {"signals": []}
    
    async def get_user_subscriptions(
        self,
        user_id: str,
        include_inactive: bool = False
    ) -> Dict[str, Any]:
        """
        Get user's active subscriptions to marketplace products.
        
        Args:
            user_id: User ID to check subscriptions for
            include_inactive: Include expired/cancelled subscriptions
            
        Returns:
            Dict with:
                - subscriptions: List of subscription data
                - total_count: int
                
        Raises:
            Exception: If request fails
        """
        client = self._get_client()
        
        try:
            # Use gateway headers for authentication from config_service exclusively (Architecture Principle #1: Config service exclusivity)
            try:
                from common.config_service.client import ConfigServiceClient
                from app.core.config import settings
                
                config_client = ConfigServiceClient(
                    service_name="signal_service", 
                    environment=settings.environment,
                    timeout=5
                )
                gateway_secret = config_client.get_secret("GATEWAY_SECRET")
                if not gateway_secret:
                    raise ValueError("GATEWAY_SECRET not found in config_service")
            except Exception as e:
                logger.error(f"Failed to get gateway secret from config_service: {e}. No environment fallbacks allowed per architecture.")
                return {"subscriptions": [], "total_count": 0}
            
            headers = {
                "X-User-ID": user_id,
                "X-Gateway-Secret": gateway_secret,
            }
            
            params = {}
            if include_inactive:
                params["include_inactive"] = "true"
            
            response = await client.get(
                f"/api/v1/users/{user_id}/subscriptions",
                headers=headers,
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Ensure tier information is included in each subscription
                # Sprint 5A: Add tier extraction for dynamic limits
                for subscription in data.get("subscriptions", []):
                    # Extract tier from subscription or product metadata
                    if "tier" not in subscription:
                        # Try to extract from product data
                        product_data = subscription.get("product", {})
                        subscription["tier"] = product_data.get("tier", "free")
                        
                        # Map legacy product types to tiers if needed
                        if subscription["tier"] == "free" and product_data.get("is_premium"):
                            subscription["tier"] = "premium"
                        elif subscription["tier"] == "free" and product_data.get("is_enterprise"):
                            subscription["tier"] = "enterprise"
                            
                return data
            else:
                logger.warning(
                    f"Get user subscriptions failed: {response.status_code} - {response.text}"
                )
                return {"subscriptions": [], "total_count": 0}
                
        except Exception as e:
            logger.error(f"Error fetching user subscriptions: {e}")
            return {"subscriptions": [], "total_count": 0}
    
    async def get_product_definition(
        self,
        product_id: str,
        user_id: str,
        execution_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get complete product definition with signal metadata.
        
        Args:
            product_id: Marketplace product ID
            user_id: User requesting product definition
            execution_token: Optional execution token for premium access
            
        Returns:
            Dict with complete product definition:
                - product_id: str
                - name: str
                - description: str
                - signal_groups: List of signal group definitions
                - access_level: str (free/premium/subscription)
                - requires_subscription: bool
                - user_access: Dict with user's access status
                
        Raises:
            Exception: If request fails
        """
        client = self._get_client()
        
        try:
            # Use gateway headers for authentication from config_service exclusively (Architecture Principle #1: Config service exclusivity)
            try:
                from common.config_service.client import ConfigServiceClient
                from app.core.config import settings
                
                config_client = ConfigServiceClient(
                    service_name="signal_service", 
                    environment=settings.environment,
                    timeout=5
                )
                gateway_secret = config_client.get_secret("GATEWAY_SECRET")
                if not gateway_secret:
                    raise ValueError("GATEWAY_SECRET not found in config_service")
            except Exception as e:
                logger.error(f"Failed to get gateway secret from config_service: {e}. No environment fallbacks allowed per architecture.")
                return {"signal_groups": []}
            
            headers = {
                "X-User-ID": user_id,
                "X-Gateway-Secret": gateway_secret,
            }
            if execution_token:
                headers["X-Execution-Token"] = execution_token
            
            response = await client.get(
                f"/api/v1/products/{product_id}/definition",
                headers=headers
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(
                    f"Get product definition failed: {response.status_code} - {response.text}"
                )
                return {"signal_groups": []}
                
        except Exception as e:
            logger.error(f"Error fetching product definition: {e}")
            return {"signal_groups": []}
    
    async def check_subscription_access(
        self,
        user_id: str,
        product_id: str,
        execution_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Check if user has valid access to a product.
        
        Args:
            user_id: User ID to check access for
            product_id: Product ID to check access to
            execution_token: Optional execution token for premium access
            
        Returns:
            Dict with access information:
                - has_access: bool
                - access_level: str (free/premium/subscription)
                - subscription_status: str (active/expired/none)
                - expires_at: Optional datetime string
                - usage_limits: Dict with any usage restrictions
                
        Raises:
            Exception: If request fails
        """
        client = self._get_client()
        
        try:
            # Use gateway headers for authentication from config_service exclusively (Architecture Principle #1: Config service exclusivity)
            try:
                from common.config_service.client import ConfigServiceClient
                from app.core.config import settings
                
                config_client = ConfigServiceClient(
                    service_name="signal_service", 
                    environment=settings.environment,
                    timeout=5
                )
                gateway_secret = config_client.get_secret("GATEWAY_SECRET")
                if not gateway_secret:
                    raise ValueError("GATEWAY_SECRET not found in config_service")
            except Exception as e:
                logger.error(f"Failed to get gateway secret from config_service: {e}. No environment fallbacks allowed per architecture.")
                return {"has_access": False, "access_level": "none"}
            
            headers = {
                "X-User-ID": user_id,
                "X-Gateway-Secret": gateway_secret,
            }
            if execution_token:
                headers["X-Execution-Token"] = execution_token
            
            response = await client.get(
                f"/api/v1/products/{product_id}/access-check",
                headers=headers
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(
                    f"Check subscription access failed: {response.status_code} - {response.text}"
                )
                return {"has_access": False, "access_level": "none"}
                
        except Exception as e:
            logger.error(f"Error checking subscription access: {e}")
            return {"has_access": False, "access_level": "none"}


def create_marketplace_client() -> MarketplaceClient:
    """
    Create marketplace client with configuration from environment.
    
    Returns:
        MarketplaceClient instance
    """
    # Get marketplace URL and API key from config_service (Architecture Principle #1: Config service exclusivity)
    try:
        from common.config_service.client import ConfigServiceClient
        from app.core.config import settings
        
        config_client = ConfigServiceClient(
            service_name="signal_service",
            environment=settings.environment,
            timeout=5
        )
        
        base_url = config_client.get_config("MARKETPLACE_SERVICE_URL")
        if not base_url:
            raise ValueError("MARKETPLACE_SERVICE_URL not found in config_service")
            
        internal_api_key = config_client.get_secret("INTERNAL_API_KEY")
        if not internal_api_key:
            raise ValueError("INTERNAL_API_KEY not found in config_service")
            
    except Exception as e:
        raise RuntimeError(f"Failed to get marketplace configuration from config_service: {e}. No environment fallbacks allowed per architecture.")
    
    if not internal_api_key:
        logger.warning("INTERNAL_API_KEY not set - marketplace integration may fail")
    
    return MarketplaceClient(
        base_url=base_url,
        internal_api_key=internal_api_key,
        timeout=10.0
    )