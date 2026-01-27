# [AGENT-4-SECURITY-TIMEZONE] - F&O Entitlement Middleware
"""
Entitlement Middleware for F&O Route Protection

Protects premium F&O routes by validating user entitlements before allowing access.
This middleware prevents unauthorized access to premium features like Greeks calculations
and option analytics.

CRITICAL SECURITY: This middleware blocks access to F&O routes for unauthorized users,
preventing the security bypass that allowed any user to access premium features.
"""

import logging

import httpx
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.services.unified_entitlement_service import get_unified_entitlement_service

logger = logging.getLogger(__name__)


class EntitlementMiddleware:
    """
    Middleware to check F&O entitlements for protected routes.

    This middleware intercepts requests to premium F&O endpoints and validates
    user subscriptions before allowing access.
    """

    # F&O routes that require entitlement checking
    PROTECTED_FO_ROUTES: set[str] = {
        "/api/v2/signals/fo/greeks/",
        "/api/v2/signals/fo/premium-analysis/",
        "/api/v2/signals/fo/option-chain/",
        "/api/v2/signals/fo/",
    }

    # Premium analysis routes that require premium tier
    PREMIUM_ANALYSIS_ROUTES: set[str] = {
        "/premium-analysis/expiry",
        "/premium-analysis/strike-range",
        "/premium-analysis/term-structure",
        "/premium-analysis/arbitrage-opportunities/",
    }

    def __init__(self, marketplace_service_url: str):
        """Initialize entitlement middleware."""
        self.marketplace_service_url = marketplace_service_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close HTTP client."""
        await self._client.aclose()

    def _is_protected_route(self, path: str) -> bool:
        """Check if route requires F&O entitlement."""
        # Check if path starts with any protected route pattern
        return any(
            path.startswith(protected_route)
            for protected_route in self.PROTECTED_FO_ROUTES
        )

    def _requires_premium_analysis(self, path: str) -> bool:
        """Check if route requires premium analysis entitlement."""
        return any(
            premium_route in path
            for premium_route in self.PREMIUM_ANALYSIS_ROUTES
        )

    def _extract_user_id_str(self, request: Request) -> str:
        """Extract user ID from request headers."""
        # Check X-User-ID header (from API Gateway)
        user_id_header = request.headers.get("X-User-ID")
        if user_id_header:
            return user_id_header


        # No user ID found
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User authentication required for F&O access"
        )

    async def _check_fo_entitlement(self, user_id: int) -> bool:
        """Check if user has F&O access entitlement."""
        try:
            response = await self._client.get(
                f"{self.marketplace_service_url}/api/v1/entitlements/check",
                params={
                    "user_id": user_id,
                    "feature": "fo_greeks_access"
                }
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("has_access", False)
            logger.warning(
                f"Entitlement check failed for user {user_id}: {response.status_code}"
            )
            return False

        except httpx.RequestError as e:
            logger.error(f"Entitlement service request failed: {e}")
            # Fail secure - deny access if service is unavailable
            return False

    async def _check_premium_analysis_entitlement(self, user_id: int) -> bool:
        """Check if user has premium analysis access."""
        try:
            response = await self._client.get(
                f"{self.marketplace_service_url}/api/v1/entitlements/check",
                params={
                    "user_id": user_id,
                    "feature": "premium_analysis"
                }
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("has_access", False)
            logger.warning(
                f"Premium analysis check failed for user {user_id}: {response.status_code}"
            )
            return False

        except httpx.RequestError as e:
            logger.error(f"Premium analysis service request failed: {e}")
            # Fail secure - deny access if service is unavailable
            return False

    async def __call__(self, request: Request, call_next):
        """Process request through unified entitlement service."""
        path = request.url.path

        # Skip entitlement check for non-protected routes and public endpoints
        if not self._is_protected_route(path):
            return await call_next(request)
        if any(endpoint in path for endpoint in ["/health", "/admin", "/docs", "/openapi"]):
            return await call_next(request)

        try:
            # Extract user ID from request
            user_id_str = self._extract_user_id_str(request)

            # Use unified entitlement service for access check
            entitlement_service = await get_unified_entitlement_service()

            # Get client ID for tracking
            client_id = request.headers.get("X-Client-ID") or f"http_{request.client.host}"

            # Check HTTP access via unified service
            result = await entitlement_service.check_http_access(
                user_id=user_id_str,
                request_path=path,
                client_id=client_id
            )

            if not result.is_allowed:
                logger.warning(
                    f"Access denied for user {user_id_str} to {path} - {result.reason}"
                )
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "detail": result.reason,
                        "error_code": "entitlement_required",
                        "user_tier": result.user_tier,
                        "upgrade_url": "/api/v1/billing/upgrade"
                    }
                )

            # Log successful access for audit
            logger.info(
                f"Access granted for user {user_id_str} to {path} (tier: {result.user_tier})"
            )

            # Add entitlement info to request state for downstream use
            request.state.user_id = user_id_str
            request.state.has_fo_access = True
            request.state.user_tier = result.user_tier
            request.state.access_limits = result.limits

            return await call_next(request)

        except HTTPException as e:
            # Re-raise HTTP exceptions (like 401 Unauthorized)
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail}
            )
        except Exception as e:
            logger.error(f"Entitlement middleware error for {path}: {e}")
            # Fail secure - deny access on unexpected errors
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "detail": "Entitlement check failed",
                    "error_code": "entitlement_service_error"
                }
            )


async def create_entitlement_middleware(marketplace_service_url: str) -> EntitlementMiddleware:
    """
    Factory function to create entitlement middleware.

    Args:
        marketplace_service_url: URL of marketplace service for entitlement checks

    Returns:
        Configured entitlement middleware instance
    """
    return EntitlementMiddleware(marketplace_service_url)
