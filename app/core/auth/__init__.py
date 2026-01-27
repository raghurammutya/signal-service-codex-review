"""Signal Service Authentication Module

This module provides authentication utilities for the signal service,
following the gateway trust pattern used across all microservices.

ARCHITECTURE COMPLIANCE:
- JWT validation happens at API Gateway ONLY
- Services trust gateway headers (X-User-ID, X-Gateway-Secret)
- No direct JWT validation in services
- Fail-closed security model

Available imports:
- From gateway_trust: Full gateway trust implementation
- From token_validator: Compatibility alias for SDK signals
"""

# Export commonly used functions for convenience
from .gateway_trust import (
    GatewayAuthenticationError,
    get_current_user_from_gateway,
    get_current_user_with_roles,
    get_optional_user_from_gateway,
    require_role,
    verify_internal_api_key,
)

__all__ = [
    "get_current_user_from_gateway",
    "get_optional_user_from_gateway",
    "get_current_user_with_roles",
    "require_role",
    "verify_internal_api_key",
    "GatewayAuthenticationError",
]
