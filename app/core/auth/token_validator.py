"""Token Validator Module for Signal Service

This module is an alias to gateway_trust.py for consistency with SDK signals.
The SDK signals module expects to import from token_validator, so we provide
this compatibility layer.

ARCHITECTURE COMPLIANCE:
- Principle #7: JWT validation at API Gateway ONLY
- Services trust gateway headers (X-User-ID, X-Gateway-Secret)
- NO direct JWT validation in services
- Fail-closed security (deny on error)

MIGRATION PATH:
1. Import from this module: from app.core.auth.token_validator import get_current_user_from_gateway
2. This forwards to gateway_trust.py implementation
3. Over time, code can migrate to use gateway_trust.py directly

DEAD CODE REMOVAL:
❌ Remove verify_jwt_token() function if it exists elsewhere
❌ Remove JWKS client initialization if it exists elsewhere
❌ Remove jwt.decode() calls if they exist elsewhere
❌ Remove RS256 public key loading if it exists elsewhere
✅ Use gateway trust pattern (gateway_trust.py/this module)
"""

# Import all from gateway_trust for backwards compatibility
from .gateway_trust import (
    GatewayAuthenticationError,
    verify_gateway_secret,
    get_current_user_from_gateway,
    get_optional_user_from_gateway,
    get_current_user_with_roles,
    require_role,
    verify_internal_api_key,
)

__all__ = [
    "GatewayAuthenticationError",
    "verify_gateway_secret",
    "get_current_user_from_gateway",
    "get_optional_user_from_gateway",
    "get_current_user_with_roles",
    "require_role",
    "verify_internal_api_key",
]