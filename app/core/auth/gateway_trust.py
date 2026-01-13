"""Gateway Trust Authentication Pattern for Signal Service

ARCHITECTURE COMPLIANCE:
- Principle #7: JWT validation at API Gateway ONLY
- Services trust gateway headers (X-User-ID, X-Gateway-Secret)
- NO direct JWT validation in services
- Fail-closed security (deny on error)

This module provides authentication for signal_service following the
established gateway trust pattern used across all microservices.

SECURITY MODEL:
1. API Gateway validates JWT and extracts user info
2. Gateway adds X-User-ID and X-Gateway-Secret headers
3. Services verify X-Gateway-Secret matches expected value
4. Services trust X-User-ID as authenticated user identity
"""
import logging
from typing import Optional, Dict
from fastapi import Header, HTTPException, Depends

from app.core.config import settings

logger = logging.getLogger(__name__)


class GatewayAuthenticationError(HTTPException):
    """Exception raised when gateway authentication fails."""

    def __init__(self, detail: str):
        super().__init__(status_code=403, detail=detail)


def verify_gateway_secret(gateway_secret: Optional[str]) -> bool:
    """
    Verify gateway secret header.

    ARCHITECTURE COMPLIANCE:
    - Fail-closed security (deny if secret is missing or invalid)
    - Constant-time comparison to prevent timing attacks

    Args:
        gateway_secret: X-Gateway-Secret header value

    Returns:
        bool: True if secret is valid, False otherwise
    """
    if not gateway_secret:
        logger.warning("Gateway secret missing - denying access")
        return False

    # Use secrets.compare_digest for constant-time comparison
    # (prevents timing attacks)
    import secrets
    expected = settings.gateway_secret
    is_valid = secrets.compare_digest(gateway_secret, expected)

    if not is_valid:
        logger.warning("Gateway secret invalid - denying access")

    return is_valid


async def get_current_user_from_gateway(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_gateway_secret: Optional[str] = Header(None, alias="X-Gateway-Secret"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Dict[str, str]:
    """
    Get current user from API Gateway headers.

    ARCHITECTURE COMPLIANCE:
    - Principle #7: Services trust gateway headers (X-User-ID, X-Gateway-Secret)
    - Fail-closed security: Deny access if headers are missing or invalid

    DEVELOPMENT MODE:
    - In development, supports direct access without gateway for testing
    - Enabled via ALLOW_DIRECT_ACCESS=true environment variable
    - Extracts user_id from Authorization header if present
    - NEVER enabled in production

    This is the PRIMARY authentication mechanism for all services.
    The API Gateway:
    1. Validates JWT token
    2. Extracts user_id from token claims
    3. Adds X-User-ID header
    4. Adds X-Gateway-Secret header (proves request came from gateway)
    5. Forwards request to service

    Services verify:
    1. X-Gateway-Secret matches settings.gateway_secret (proves request from gateway)
    2. X-User-ID is present (identifies the user)

    Args:
        x_user_id: User ID from gateway (from JWT 'sub' claim)
        x_gateway_secret: Gateway secret for verification
        authorization: Bearer token (only used in development mode)

    Returns:
        Dict[str, str]: User information with keys:
            - user_id: User ID from gateway
            - from_gateway: Always "true"

    Raises:
        GatewayAuthenticationError: If authentication fails (403 Forbidden)

    Example Usage:
        @router.get("/api/v1/signals")
        async def get_signals(
            user: Dict = Depends(get_current_user_from_gateway)
        ):
            user_id = user["user_id"]
            # ... your logic here
    """
    # =========================================================================
    # DEVELOPMENT MODE: Allow direct access for testing
    # =========================================================================
    import os
    allow_direct_access = os.getenv("ALLOW_DIRECT_ACCESS", "false").lower() == "true"
    is_development = settings.environment != "production"

    if allow_direct_access and is_development:
        # Development mode: Allow direct access without gateway
        logger.warning("DEVELOPMENT MODE: Direct access allowed (bypass gateway auth)")

        # Try to extract user_id from Authorization header
        if authorization and authorization.startswith("Bearer "):
            # Extract user_id from JWT (simplified - no validation in dev mode)
            try:
                import jwt
                token = authorization.replace("Bearer ", "")
                # Decode without verification (dev mode only!)
                payload = jwt.decode(token, options={"verify_signature": False})
                user_id = payload.get("sub", "dev-user")
                logger.debug(f"Development mode: Extracted user_id={user_id} from JWT")
            except Exception as e:
                logger.warning(f"Failed to decode JWT in dev mode: {e}")
                user_id = "dev-user"
        elif x_user_id:
            # Use provided X-User-ID header
            user_id = x_user_id
        else:
            # Default dev user
            user_id = "dev-user"

        return {
            "user_id": user_id,
            "from_gateway": "dev",
        }

    # =========================================================================
    # PRODUCTION MODE: Strict gateway authentication
    # =========================================================================

    # SECURITY: Fail-closed - deny if gateway secret is invalid
    if not verify_gateway_secret(x_gateway_secret):
        logger.error(
            "Direct access attempt blocked - missing or invalid gateway secret. "
            "All requests MUST go through API Gateway."
        )
        raise GatewayAuthenticationError(
            "Direct service access is forbidden. "
            "Requests must be routed through API Gateway."
        )

    # SECURITY: Fail-closed - deny if user ID is missing
    if not x_user_id:
        logger.error("User ID missing from gateway headers - denying access")
        raise GatewayAuthenticationError(
            "User ID missing from request. "
            "Ensure API Gateway is configured correctly."
        )

    # Authentication successful
    logger.debug(f"Gateway authentication successful for user: {x_user_id}")

    return {
        "user_id": x_user_id,
        "from_gateway": "true",
    }


async def get_optional_user_from_gateway(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_gateway_secret: Optional[str] = Header(None, alias="X-Gateway-Secret"),
) -> Optional[Dict[str, str]]:
    """
    Get optional user from API Gateway headers (for public endpoints).

    Same as get_current_user_from_gateway but returns None instead of raising
    exception if user is not authenticated.

    Useful for endpoints that:
    - Support both authenticated and unauthenticated access
    - Return different data based on authentication status

    Args:
        x_user_id: User ID from gateway (from JWT 'sub' claim)
        x_gateway_secret: Gateway secret for verification

    Returns:
        Optional[Dict[str, str]]: User information or None if not authenticated

    Example Usage:
        @router.get("/api/v1/signals/public")
        async def get_public_signals(
            user: Optional[Dict] = Depends(get_optional_user_from_gateway)
        ):
            if user:
                # Show personalized data
                user_id = user["user_id"]
                return get_user_signals(user_id)
            else:
                # Show public data
                return get_public_signals()
    """
    # Gateway secret must be valid (deny direct access)
    if not verify_gateway_secret(x_gateway_secret):
        logger.error("Direct access attempt blocked - missing or invalid gateway secret")
        raise GatewayAuthenticationError(
            "Direct service access is forbidden. "
            "Requests must be routed through API Gateway."
        )

    # User ID is optional for this endpoint
    if not x_user_id:
        logger.debug("Optional authentication: No user ID present")
        return None

    logger.debug(f"Optional authentication: User {x_user_id} authenticated")

    return {
        "user_id": x_user_id,
        "from_gateway": "true",
    }


async def get_current_user_with_roles(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_user_roles: Optional[str] = Header(None, alias="X-User-Roles"),
    x_gateway_secret: Optional[str] = Header(None, alias="X-Gateway-Secret"),
) -> Dict[str, any]:
    """
    Get current user with roles from API Gateway headers.

    Enhanced version of get_current_user_from_gateway that includes user roles.
    Requires API Gateway to pass X-User-Roles header.

    Args:
        x_user_id: User ID from gateway (from JWT 'sub' claim)
        x_user_roles: Comma-separated user roles (e.g., "user,admin")
        x_gateway_secret: Gateway secret for verification

    Returns:
        Dict[str, any]: User information with keys:
            - user_id: User ID from gateway
            - roles: List of user roles
            - from_gateway: Always "true"

    Raises:
        GatewayAuthenticationError: If authentication fails (403 Forbidden)

    Example Usage:
        @router.delete("/api/v1/admin/signals/{signal_id}")
        async def delete_signal(
            signal_id: int,
            current_user: Dict = Depends(get_current_user_with_roles)
        ):
            if "admin" not in current_user["roles"]:
                raise HTTPException(403, "Admin access required")
            # ... your logic here
    """
    # Verify gateway secret and user ID (same as get_current_user_from_gateway)
    if not verify_gateway_secret(x_gateway_secret):
        raise GatewayAuthenticationError(
            "Direct service access is forbidden. "
            "Requests must be routed through API Gateway."
        )

    if not x_user_id:
        raise GatewayAuthenticationError(
            "User ID missing from request. "
            "Ensure API Gateway is configured correctly."
        )

    # Parse roles (comma-separated string)
    roles = []
    if x_user_roles:
        roles = [role.strip() for role in x_user_roles.split(",") if role.strip()]

    logger.debug(f"Gateway authentication successful for user: {x_user_id}, roles: {roles}")

    return {
        "user_id": x_user_id,
        "roles": roles,
        "from_gateway": "true",
    }


def require_role(required_role: str):
    """
    Dependency factory to require specific role.

    Args:
        required_role: Role name required (e.g., "admin", "trader")

    Returns:
        Callable: FastAPI dependency function

    Example Usage:
        @router.post("/api/v1/admin/signals")
        async def create_signal(
            signal_data: SignalCreate,
            current_user: Dict = Depends(require_role("admin"))
        ):
            # Only admins can access this endpoint
            # ... your logic here
    """
    async def _check_role(
        user: Dict = Depends(get_current_user_with_roles)
    ) -> Dict:
        if required_role not in user.get("roles", []):
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required role: {required_role}"
            )
        return user

    return _check_role


# =============================================================================
# INTERNAL SERVICE AUTHENTICATION (For Service-to-Service Communication)
# =============================================================================

async def verify_internal_api_key(
    x_internal_api_key: Optional[str] = Header(None, alias="X-Internal-API-Key"),
) -> bool:
    """
    Verify internal API key for service-to-service communication.

    Some services need to be called by other internal services (not through gateway).
    Example: config_service, token_manager

    Args:
        x_internal_api_key: Internal API key from calling service

    Returns:
        bool: True if API key is valid

    Raises:
        HTTPException: If API key is missing or invalid (403 Forbidden)

    Example Usage:
        @router.get("/api/v1/internal/signals")
        async def get_internal_signals(
            _: bool = Depends(verify_internal_api_key)
        ):
            # Only accessible with internal API key
            # ... your logic here
    """
    # Load internal API key from settings
    # (add this to your config.py if needed)
    expected_key = getattr(settings, "internal_api_key", None)

    if not expected_key:
        logger.error("internal_api_key not configured")
        raise HTTPException(
            status_code=500,
            detail="Internal API key not configured"
        )

    if not x_internal_api_key:
        logger.warning("Internal API key missing - denying access")
        raise HTTPException(
            status_code=403,
            detail="Internal API key required"
        )

    # Constant-time comparison
    import secrets
    is_valid = secrets.compare_digest(x_internal_api_key, expected_key)

    if not is_valid:
        logger.warning("Internal API key invalid - denying access")
        raise HTTPException(
            status_code=403,
            detail="Invalid internal API key"
        )

    logger.debug("Internal API key verification successful")
    return True