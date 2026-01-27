"""
Comprehensive authentication and authorization testing
Tests gateway trust validation, token validation, and entitlement middleware
"""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch

import jwt
import pytest
from httpx import AsyncClient

from app.core.auth.gateway_trust import GatewayTrustValidator
from app.core.auth.token_validator import TokenValidator
from app.errors import AuthenticationError, AuthorizationError
from app.middleware.entitlement_middleware import EntitlementMiddleware


class TestGatewayTrustValidator:
    """Test gateway trust validation"""

    @pytest.fixture
    def validator(self):
        """Create validator instance"""
        return GatewayTrustValidator()

    @pytest.fixture
    def valid_gateway_secret(self):
        """Valid gateway secret for testing"""
        return "test-gateway-secret-12345"

    @pytest.fixture
    def mock_settings(self, valid_gateway_secret):
        """Mock settings with gateway configuration"""
        with patch('app.core.auth.gateway_trust.settings') as mock_settings:
            mock_settings.GATEWAY_SECRET = valid_gateway_secret
            mock_settings.GATEWAY_TRUSTED_IPS = ["127.0.0.1", "10.0.0.0/8", "172.16.0.0/12"]
            mock_settings.ENABLE_GATEWAY_TRUST = True
            yield mock_settings

    def test_valid_gateway_secret(self, validator, mock_settings, valid_gateway_secret):
        """Test validation with valid gateway secret"""
        headers = {
            "X-Gateway-Secret": valid_gateway_secret,
            "X-User-ID": "user_123",
            "X-Forwarded-For": "127.0.0.1"
        }

        result = validator.validate_gateway_trust(headers)

        assert result is True

    def test_invalid_gateway_secret(self, validator, mock_settings):
        """Test validation with invalid gateway secret"""
        headers = {
            "X-Gateway-Secret": "invalid-secret",
            "X-User-ID": "user_123",
            "X-Forwarded-For": "127.0.0.1"
        }

        with pytest.raises(AuthenticationError, match="Invalid gateway secret"):
            validator.validate_gateway_trust(headers)

    def test_missing_gateway_secret(self, validator, mock_settings):
        """Test validation with missing gateway secret"""
        headers = {
            "X-User-ID": "user_123",
            "X-Forwarded-For": "127.0.0.1"
        }

        with pytest.raises(AuthenticationError, match="Missing gateway secret"):
            validator.validate_gateway_trust(headers)

    def test_untrusted_ip_address(self, validator, mock_settings, valid_gateway_secret):
        """Test validation from untrusted IP address"""
        headers = {
            "X-Gateway-Secret": valid_gateway_secret,
            "X-User-ID": "user_123",
            "X-Forwarded-For": "192.168.1.100"  # Not in trusted range
        }

        with pytest.raises(AuthenticationError, match="Untrusted IP address"):
            validator.validate_gateway_trust(headers)

    def test_missing_user_id(self, validator, mock_settings, valid_gateway_secret):
        """Test validation with missing user ID"""
        headers = {
            "X-Gateway-Secret": valid_gateway_secret,
            "X-Forwarded-For": "127.0.0.1"
            # Missing X-User-ID
        }

        with pytest.raises(AuthenticationError, match="Missing user ID"):
            validator.validate_gateway_trust(headers)

    def test_ip_range_validation(self, validator, mock_settings, valid_gateway_secret):
        """Test IP range validation for trusted networks"""
        test_cases = [
            ("10.0.0.1", True),      # In 10.0.0.0/8
            ("172.16.0.1", True),    # In 172.16.0.0/12
            ("192.168.1.1", False), # Not in trusted ranges
            ("8.8.8.8", False),      # Public IP
            ("127.0.0.1", True),     # Localhost
        ]

        for ip, should_pass in test_cases:
            headers = {
                "X-Gateway-Secret": valid_gateway_secret,
                "X-User-ID": "user_123",
                "X-Forwarded-For": ip
            }

            if should_pass:
                result = validator.validate_gateway_trust(headers)
                assert result is True, f"IP {ip} should be trusted"
            else:
                with pytest.raises(AuthenticationError, match="Untrusted IP address"):
                    validator.validate_gateway_trust(headers)

    def test_gateway_trust_disabled(self, validator):
        """Test behavior when gateway trust is disabled"""
        with patch('app.core.auth.gateway_trust.settings') as mock_settings:
            mock_settings.ENABLE_GATEWAY_TRUST = False

            headers = {
                "X-Gateway-Secret": "any-secret",
                "X-User-ID": "user_123"
            }

            # Should pass without validation when disabled
            result = validator.validate_gateway_trust(headers)
            assert result is True


class TestTokenValidator:
    """Test JWT token validation"""

    @pytest.fixture
    def validator(self):
        """Create token validator instance"""
        return TokenValidator()

    @pytest.fixture
    def jwt_secret(self):
        """JWT secret for testing"""
        return "test-jwt-secret-key-12345"

    @pytest.fixture
    def mock_settings(self, jwt_secret):
        """Mock settings with JWT configuration"""
        with patch('app.core.auth.token_validator.settings') as mock_settings:
            mock_settings.JWT_SECRET = jwt_secret
            mock_settings.JWT_ALGORITHM = "HS256"
            mock_settings.JWT_EXPIRATION_HOURS = 24
            yield mock_settings

    def test_valid_jwt_token(self, validator, mock_settings, jwt_secret):
        """Test validation of valid JWT token"""
        # Create valid JWT token
        payload = {
            "user_id": "user_123",
            "role": "premium",
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow()
        }

        token = jwt.encode(payload, jwt_secret, algorithm="HS256")

        result = validator.validate_token(token)

        assert result["user_id"] == "user_123"
        assert result["role"] == "premium"

    def test_expired_jwt_token(self, validator, mock_settings, jwt_secret):
        """Test validation of expired JWT token"""
        # Create expired JWT token
        payload = {
            "user_id": "user_123",
            "role": "basic",
            "exp": datetime.utcnow() - timedelta(hours=1),  # Expired
            "iat": datetime.utcnow() - timedelta(hours=2)
        }

        token = jwt.encode(payload, jwt_secret, algorithm="HS256")

        with pytest.raises(AuthenticationError, match="Token expired"):
            validator.validate_token(token)

    def test_invalid_jwt_signature(self, validator, mock_settings):
        """Test validation of token with invalid signature"""
        # Create token with wrong secret
        payload = {
            "user_id": "user_123",
            "role": "basic",
            "exp": datetime.utcnow() + timedelta(hours=1)
        }

        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")

        with pytest.raises(AuthenticationError, match="Invalid token signature"):
            validator.validate_token(token)

    def test_malformed_jwt_token(self, validator, mock_settings):
        """Test validation of malformed JWT token"""
        malformed_tokens = [
            "not.a.jwt.token",
            "invalid_token",
            "",
            "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9",  # Incomplete JWT
        ]

        for token in malformed_tokens:
            with pytest.raises(AuthenticationError, match="Invalid token format"):
                validator.validate_token(token)

    def test_missing_required_claims(self, validator, mock_settings, jwt_secret):
        """Test validation of token missing required claims"""
        # Token without user_id
        payload = {
            "role": "basic",
            "exp": datetime.utcnow() + timedelta(hours=1)
            # Missing user_id
        }

        token = jwt.encode(payload, jwt_secret, algorithm="HS256")

        with pytest.raises(AuthenticationError, match="Missing required claims"):
            validator.validate_token(token)

    def test_token_blacklist_check(self, validator, mock_settings, jwt_secret):
        """Test token blacklist validation"""
        payload = {
            "user_id": "user_123",
            "role": "basic",
            "exp": datetime.utcnow() + timedelta(hours=1),
            "jti": "token_id_123"  # JWT ID for blacklisting
        }

        token = jwt.encode(payload, jwt_secret, algorithm="HS256")

        # Mock blacklist check
        with patch.object(validator, '_is_token_blacklisted', return_value=True):
            with pytest.raises(AuthenticationError, match="Token has been revoked"):
                validator.validate_token(token)

    def test_user_role_validation(self, validator, mock_settings, jwt_secret):
        """Test user role validation in token"""
        valid_roles = ["basic", "premium", "admin", "suspended"]

        for role in valid_roles:
            payload = {
                "user_id": "user_123",
                "role": role,
                "exp": datetime.utcnow() + timedelta(hours=1)
            }

            token = jwt.encode(payload, jwt_secret, algorithm="HS256")
            result = validator.validate_token(token)

            assert result["role"] == role

    def test_invalid_user_role(self, validator, mock_settings, jwt_secret):
        """Test validation of invalid user role"""
        payload = {
            "user_id": "user_123",
            "role": "invalid_role",
            "exp": datetime.utcnow() + timedelta(hours=1)
        }

        token = jwt.encode(payload, jwt_secret, algorithm="HS256")

        with pytest.raises(AuthenticationError, match="Invalid user role"):
            validator.validate_token(token)


class TestEntitlementMiddleware:
    """Test entitlement middleware for F&O route protection"""

    @pytest.fixture
    def middleware(self):
        """Create entitlement middleware instance"""
        return EntitlementMiddleware()

    @pytest.fixture
    def mock_user_service(self):
        """Mock user service for entitlement checks"""
        with patch('app.middleware.entitlement_middleware.UserServiceClient') as mock_service:
            yield mock_service

    @pytest.mark.asyncio
    async def test_fo_route_access_with_entitlement(self, middleware, mock_user_service):
        """Test F&O route access with valid entitlement"""
        # Mock user with F&O entitlement
        mock_user_service.return_value.get_user_entitlements.return_value = {
            "user_id": "user_123",
            "entitlements": ["equity", "fo", "currency"],
            "fo_access": True,
            "fo_expiry": (datetime.utcnow() + timedelta(days=30)).isoformat()
        }

        user_context = {
            "user_id": "user_123",
            "role": "premium"
        }

        # F&O route should be accessible
        result = await middleware.check_fo_entitlement(user_context, "/api/v2/fo/greeks")

        assert result is True

    @pytest.mark.asyncio
    async def test_fo_route_access_without_entitlement(self, middleware, mock_user_service):
        """Test F&O route access without entitlement"""
        # Mock user without F&O entitlement
        mock_user_service.return_value.get_user_entitlements.return_value = {
            "user_id": "user_123",
            "entitlements": ["equity"],  # No F&O entitlement
            "fo_access": False
        }

        user_context = {
            "user_id": "user_123",
            "role": "basic"
        }

        # F&O route should be blocked
        with pytest.raises(AuthorizationError, match="F&O access not permitted"):
            await middleware.check_fo_entitlement(user_context, "/api/v2/fo/greeks")

    @pytest.mark.asyncio
    async def test_fo_route_access_expired_entitlement(self, middleware, mock_user_service):
        """Test F&O route access with expired entitlement"""
        # Mock user with expired F&O entitlement
        mock_user_service.return_value.get_user_entitlements.return_value = {
            "user_id": "user_123",
            "entitlements": ["equity", "fo"],
            "fo_access": True,
            "fo_expiry": (datetime.utcnow() - timedelta(days=1)).isoformat()  # Expired
        }

        user_context = {
            "user_id": "user_123",
            "role": "premium"
        }

        with pytest.raises(AuthorizationError, match="F&O entitlement expired"):
            await middleware.check_fo_entitlement(user_context, "/api/v2/fo/greeks")

    @pytest.mark.asyncio
    async def test_equity_route_access(self, middleware, mock_user_service):
        """Test equity route access (should always be allowed)"""
        # Even basic user should access equity routes
        mock_user_service.return_value.get_user_entitlements.return_value = {
            "user_id": "user_123",
            "entitlements": ["equity"],
            "fo_access": False
        }

        user_context = {
            "user_id": "user_123",
            "role": "basic"
        }

        # Equity route should be accessible
        result = await middleware.check_route_entitlement(user_context, "/api/v2/equity/indicators")

        assert result is True

    @pytest.mark.asyncio
    async def test_premium_feature_access_control(self, middleware):
        """Test premium feature access control"""
        test_cases = [
            # (user_role, route, should_allow)
            ("premium", "/api/v2/premium/advanced_greeks", True),
            ("basic", "/api/v2/premium/advanced_greeks", False),
            ("admin", "/api/v2/premium/advanced_greeks", True),
            ("basic", "/api/v2/basic/indicators", True),
            ("premium", "/api/v2/basic/indicators", True),
        ]

        for user_role, route, should_allow in test_cases:
            user_context = {
                "user_id": "user_123",
                "role": user_role
            }

            if should_allow:
                result = await middleware.check_premium_access(user_context, route)
                assert result is True, f"Role {user_role} should access {route}"
            else:
                with pytest.raises(AuthorizationError, match="Premium access required"):
                    await middleware.check_premium_access(user_context, route)

    @pytest.mark.asyncio
    async def test_rate_limit_by_user_tier(self, middleware):
        """Test rate limiting based on user tier"""
        user_tiers = {
            "basic": {"requests_per_minute": 60},
            "premium": {"requests_per_minute": 300},
            "admin": {"requests_per_minute": 1000}
        }

        for tier, limits in user_tiers.items():
            user_context = {
                "user_id": f"user_{tier}",
                "role": tier
            }

            rate_limit = middleware.get_rate_limit(user_context)

            assert rate_limit["requests_per_minute"] == limits["requests_per_minute"]

    @pytest.mark.asyncio
    async def test_suspended_user_access_denial(self, middleware, mock_user_service):
        """Test access denial for suspended users"""
        mock_user_service.return_value.get_user_entitlements.return_value = {
            "user_id": "user_123",
            "entitlements": [],
            "account_status": "suspended"
        }

        user_context = {
            "user_id": "user_123",
            "role": "suspended"
        }

        with pytest.raises(AuthorizationError, match="Account suspended"):
            await middleware.check_user_status(user_context)


class TestIntegratedAuthFlow:
    """Test integrated authentication and authorization flow"""

    @pytest.fixture
    async def client(self):
        """Create test client"""
        from app.main import app
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac

    @pytest.mark.asyncio
    async def test_complete_auth_flow_success(self, client):
        """Test complete authentication flow with valid credentials"""
        # Mock all auth components
        with patch('app.core.auth.gateway_trust.GatewayTrustValidator.validate_gateway_trust') as mock_gateway:
            with patch('app.core.auth.token_validator.TokenValidator.validate_token') as mock_token:
                with patch('app.middleware.entitlement_middleware.EntitlementMiddleware.check_route_entitlement') as mock_entitlement:

                    mock_gateway.return_value = True
                    mock_token.return_value = {
                        "user_id": "user_123",
                        "role": "premium"
                    }
                    mock_entitlement.return_value = True

                    response = await client.get(
                        "/api/v2/health",
                        headers={
                            "X-Gateway-Secret": "valid-secret",
                            "X-User-ID": "user_123",
                            "Authorization": "Bearer valid-token",
                            "X-Forwarded-For": "127.0.0.1"
                        }
                    )

                    assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_auth_flow_gateway_failure(self, client):
        """Test auth flow failure at gateway trust level"""
        with patch('app.core.auth.gateway_trust.GatewayTrustValidator.validate_gateway_trust') as mock_gateway:
            mock_gateway.side_effect = AuthenticationError("Invalid gateway secret")

            response = await client.get(
                "/api/v2/health",
                headers={
                    "X-Gateway-Secret": "invalid-secret",
                    "X-User-ID": "user_123",
                    "Authorization": "Bearer token",
                    "X-Forwarded-For": "127.0.0.1"
                }
            )

            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_auth_flow_token_failure(self, client):
        """Test auth flow failure at token validation level"""
        with patch('app.core.auth.gateway_trust.GatewayTrustValidator.validate_gateway_trust') as mock_gateway:
            with patch('app.core.auth.token_validator.TokenValidator.validate_token') as mock_token:

                mock_gateway.return_value = True
                mock_token.side_effect = AuthenticationError("Invalid token")

                response = await client.get(
                    "/api/v2/health",
                    headers={
                        "X-Gateway-Secret": "valid-secret",
                        "X-User-ID": "user_123",
                        "Authorization": "Bearer invalid-token",
                        "X-Forwarded-For": "127.0.0.1"
                    }
                )

                assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_auth_flow_entitlement_failure(self, client):
        """Test auth flow failure at entitlement level"""
        with patch('app.core.auth.gateway_trust.GatewayTrustValidator.validate_gateway_trust') as mock_gateway:
            with patch('app.core.auth.token_validator.TokenValidator.validate_token') as mock_token:
                with patch('app.middleware.entitlement_middleware.EntitlementMiddleware.check_route_entitlement') as mock_entitlement:

                    mock_gateway.return_value = True
                    mock_token.return_value = {"user_id": "user_123", "role": "basic"}
                    mock_entitlement.side_effect = AuthorizationError("F&O access not permitted")

                    response = await client.get(
                        "/api/v2/fo/greeks",  # F&O endpoint
                        headers={
                            "X-Gateway-Secret": "valid-secret",
                            "X-User-ID": "user_123",
                            "Authorization": "Bearer valid-token",
                            "X-Forwarded-For": "127.0.0.1"
                        }
                    )

                    assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_rate_limiting_integration(self, client):
        """Test rate limiting integration with auth system"""
        with patch('app.core.auth.gateway_trust.GatewayTrustValidator.validate_gateway_trust') as mock_gateway:
            with patch('app.core.auth.token_validator.TokenValidator.validate_token') as mock_token:
                with patch('app.middleware.ratelimit.RateLimiter.check_rate_limit') as mock_rate_limit:

                    mock_gateway.return_value = True
                    mock_token.return_value = {"user_id": "user_123", "role": "basic"}
                    mock_rate_limit.return_value = False  # Rate limit exceeded

                    response = await client.get(
                        "/api/v2/health",
                        headers={
                            "X-Gateway-Secret": "valid-secret",
                            "X-User-ID": "user_123",
                            "Authorization": "Bearer valid-token",
                            "X-Forwarded-For": "127.0.0.1"
                        }
                    )

                    assert response.status_code == 429  # Too Many Requests


class TestSecurityAuditLogging:
    """Test security audit logging for auth events"""

    def test_successful_auth_logging(self):
        """Test logging of successful authentication events"""
        validator = GatewayTrustValidator()

        with patch('app.core.auth.gateway_trust.log_info') as mock_log:
            with patch('app.core.auth.gateway_trust.settings') as mock_settings:
                mock_settings.GATEWAY_SECRET = "test-secret"
                mock_settings.GATEWAY_TRUSTED_IPS = ["127.0.0.1"]
                mock_settings.ENABLE_GATEWAY_TRUST = True

                headers = {
                    "X-Gateway-Secret": "test-secret",
                    "X-User-ID": "user_123",
                    "X-Forwarded-For": "127.0.0.1"
                }

                validator.validate_gateway_trust(headers)

                # Verify successful auth was logged
                mock_log.assert_called_with("Gateway trust validated successfully for user: user_123")

    def test_failed_auth_logging(self):
        """Test logging of failed authentication events"""
        validator = GatewayTrustValidator()

        with patch('app.core.auth.gateway_trust.log_warning') as mock_log:
            with patch('app.core.auth.gateway_trust.settings') as mock_settings:
                mock_settings.GATEWAY_SECRET = "test-secret"
                mock_settings.ENABLE_GATEWAY_TRUST = True

                headers = {
                    "X-Gateway-Secret": "wrong-secret",
                    "X-User-ID": "user_123",
                    "X-Forwarded-For": "192.168.1.1"
                }

                try:
                    validator.validate_gateway_trust(headers)
                except AuthenticationError:
                    pass

                # Verify failed auth was logged
                mock_log.assert_called_with("Gateway trust validation failed for user: user_123 from IP: 192.168.1.1")

    def test_security_event_auditing(self):
        """Test comprehensive security event auditing"""
        middleware = EntitlementMiddleware()

        with patch('app.middleware.entitlement_middleware.log_warning') as mock_log:
            user_context = {"user_id": "user_123", "role": "basic"}

            try:
                # This should trigger an authorization failure
                asyncio.run(middleware.check_premium_access(user_context, "/api/v2/premium/advanced"))
            except AuthorizationError:
                pass

            # Verify security event was audited
            mock_log.assert_called_with("Authorization denied: user_123 attempted to access premium endpoint without entitlement")
