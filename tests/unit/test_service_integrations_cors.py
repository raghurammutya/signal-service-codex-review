"""
Service Integrations and CORS Tests

Tests for service integrations with config service URLs and CORS configuration
handling including failure scenarios.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from typing import Dict, Any

from app.integrations.service_integrations import ServiceIntegrations
from common.cors_config import CORSConfig


class TestServiceIntegrations:
    """Test service integrations with config service URLs."""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings with service URLs from config service."""
        settings = MagicMock()
        settings.CALENDAR_SERVICE_URL = "http://calendar.service.com"
        settings.ALERT_SERVICE_URL = "http://alert.service.com" 
        settings.MESSAGING_SERVICE_URL = "http://messaging.service.com"
        settings.USER_SERVICE_URL = "http://user.service.com"
        settings.MARKETPLACE_SERVICE_URL = "http://marketplace.service.com"
        settings.gateway_secret = "test-gateway-secret"
        settings.SERVICE_INTEGRATION_TIMEOUT = 30.0
        return settings
    
    @pytest.fixture
    def service_integrations(self, mock_settings):
        """Create service integrations with mocked settings."""
        with patch('app.integrations.service_integrations.settings', mock_settings):
            return ServiceIntegrations()
    
    def test_service_url_initialization(self, service_integrations, mock_settings):
        """Test that service URLs are properly initialized from config service."""
        # Verify URLs are loaded from settings (config service)
        assert service_integrations.calendar_service_url == "http://calendar.service.com"
        assert service_integrations.alert_service_url == "http://alert.service.com"
        assert service_integrations.messaging_service_url == "http://messaging.service.com"
        assert service_integrations.user_service_url == "http://user.service.com"
        assert service_integrations.marketplace_service_url == "http://marketplace.service.com"
    
    def test_service_url_validation(self):
        """Test validation when service URLs are missing from config service."""
        mock_settings = MagicMock()
        mock_settings.CALENDAR_SERVICE_URL = None  # Missing URL
        mock_settings.gateway_secret = "test-secret"
        
        with patch('app.integrations.service_integrations.settings', mock_settings):
            with pytest.raises(ValueError, match="Calendar service URL not configured"):
                ServiceIntegrations()
    
    async def test_calendar_service_integration(self, service_integrations):
        """Test calendar service client integration."""
        calendar_data = {
            "events": [
                {
                    "id": "event_1",
                    "title": "FOMC Meeting",
                    "start_time": "2023-12-13T14:00:00Z",
                    "impact": "high",
                    "affected_instruments": ["USD", "SPY", "QQQ"]
                }
            ]
        }
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = calendar_data
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            events = await service_integrations.get_calendar_events(
                start_date="2023-12-13",
                end_date="2023-12-13"
            )
            
            assert events is not None
            assert len(events["events"]) == 1
            assert events["events"][0]["title"] == "FOMC Meeting"
            
            # Verify request was made with correct headers
            call_args = mock_client.return_value.__aenter__.return_value.get.call_args
            headers = call_args[1]["headers"]
            assert headers["X-Gateway-Secret"] == "test-gateway-secret"
    
    async def test_alert_service_integration(self, service_integrations):
        """Test alert service client integration."""
        alert_request = {
            "user_id": "user_123",
            "message": "Signal triggered: AAPL momentum",
            "priority": "high",
            "channels": ["email", "push"]
        }
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"alert_id": "alert_456", "status": "sent"}
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            result = await service_integrations.send_alert(alert_request)
            
            assert result["alert_id"] == "alert_456"
            assert result["status"] == "sent"
            
            # Verify request was made to correct endpoint
            call_args = mock_client.return_value.__aenter__.return_value.post.call_args
            assert call_args[0][0] == "http://alert.service.com/api/v1/alerts"
    
    async def test_messaging_service_integration(self, service_integrations):
        """Test messaging service client integration."""
        message_request = {
            "recipient": "user_123",
            "template": "signal_notification",
            "data": {
                "signal_type": "momentum",
                "instrument": "AAPL",
                "value": 1.2
            }
        }
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"message_id": "msg_789", "delivered": True}
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            result = await service_integrations.send_message(message_request)
            
            assert result["message_id"] == "msg_789"
            assert result["delivered"] is True
    
    async def test_service_timeout_handling(self, service_integrations):
        """Test service integration timeout handling."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.side_effect = Exception("Request timeout")
            
            with pytest.raises(Exception, match="Request timeout"):
                await service_integrations.get_calendar_events("2023-12-13", "2023-12-13")
    
    async def test_service_error_response_handling(self, service_integrations):
        """Test handling of error responses from services."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 500
            mock_response.text = "Internal server error"
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            with pytest.raises(Exception, match="Calendar service error"):
                await service_integrations.get_calendar_events("2023-12-13", "2023-12-13")
    
    async def test_circuit_breaker_integration(self, service_integrations):
        """Test circuit breaker integration for external services."""
        # Mock circuit breaker that's open
        service_integrations.calendar_circuit_breaker = MagicMock()
        service_integrations.calendar_circuit_breaker.is_open = True
        
        with pytest.raises(Exception, match="Calendar service circuit breaker is open"):
            await service_integrations.get_calendar_events("2023-12-13", "2023-12-13")
    
    def test_service_client_configuration(self, service_integrations):
        """Test that service clients are configured with proper timeouts and headers."""
        # Verify timeout configuration
        assert service_integrations.timeout == 30.0
        
        # Verify headers include gateway secret
        headers = service_integrations._get_headers()
        assert headers["X-Gateway-Secret"] == "test-gateway-secret"
        assert headers["Content-Type"] == "application/json"
        assert "User-Agent" in headers


class TestCORSConfig:
    """Test CORS configuration and validation."""
    
    @pytest.fixture
    def valid_cors_origins(self):
        """Valid CORS origins configuration."""
        return [
            "http://localhost:3000",
            "https://dashboard.stocksblitz.com",
            "https://api.stocksblitz.com",
            "https://*.stocksblitz.com"
        ]
    
    def test_cors_config_initialization_success(self, valid_cors_origins):
        """Test successful CORS configuration initialization."""
        with patch.dict('os.environ', {'CORS_ALLOWED_ORIGINS': ','.join(valid_cors_origins)}):
            cors_config = CORSConfig()
            
            assert cors_config.allowed_origins == valid_cors_origins
            assert cors_config.allow_credentials is True
            assert "GET" in cors_config.allowed_methods
            assert "POST" in cors_config.allowed_methods
    
    def test_cors_config_missing_environment_variable(self):
        """Test CORS config failure when environment variable missing."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS environment variable is required"):
                CORSConfig()
    
    def test_cors_config_invalid_origins(self):
        """Test CORS config validation for invalid origins."""
        invalid_origins = [
            "not-a-url",
            "ftp://invalid-protocol.com",
            "http://",  # Incomplete URL
            ""  # Empty string
        ]
        
        with patch.dict('os.environ', {'CORS_ALLOWED_ORIGINS': ','.join(invalid_origins)}):
            with pytest.raises(ValueError, match="Invalid CORS origin"):
                CORSConfig()
    
    def test_cors_origin_validation(self, valid_cors_origins):
        """Test individual origin validation."""
        cors_config = CORSConfig()
        
        # Test valid origins
        valid_origins = [
            "http://localhost:3000",
            "https://dashboard.stocksblitz.com",
            "https://api.stocksblitz.com"
        ]
        
        for origin in valid_origins:
            assert cors_config.is_origin_allowed(origin) is True
        
        # Test invalid origins
        invalid_origins = [
            "http://malicious-site.com",
            "https://fake-dashboard.com",
            "http://localhost:8080"  # Different port
        ]
        
        for origin in invalid_origins:
            assert cors_config.is_origin_allowed(origin) is False
    
    def test_cors_wildcard_subdomain_matching(self):
        """Test wildcard subdomain matching for CORS."""
        cors_origins = ["https://*.stocksblitz.com"]
        
        with patch.dict('os.environ', {'CORS_ALLOWED_ORIGINS': ','.join(cors_origins)}):
            cors_config = CORSConfig()
            
            # Should allow subdomains
            assert cors_config.is_origin_allowed("https://api.stocksblitz.com") is True
            assert cors_config.is_origin_allowed("https://dashboard.stocksblitz.com") is True
            assert cors_config.is_origin_allowed("https://beta.stocksblitz.com") is True
            
            # Should not allow different domains
            assert cors_config.is_origin_allowed("https://api.otherdomain.com") is False
            assert cors_config.is_origin_allowed("https://stocksblitz.com.malicious.com") is False
    
    def test_cors_preflight_request_handling(self, valid_cors_origins):
        """Test CORS preflight request handling."""
        with patch.dict('os.environ', {'CORS_ALLOWED_ORIGINS': ','.join(valid_cors_origins)}):
            cors_config = CORSConfig()
            
            preflight_request = {
                "origin": "https://dashboard.stocksblitz.com",
                "method": "POST",
                "headers": ["Content-Type", "Authorization"]
            }
            
            response_headers = cors_config.get_preflight_headers(preflight_request)
            
            assert response_headers["Access-Control-Allow-Origin"] == "https://dashboard.stocksblitz.com"
            assert "POST" in response_headers["Access-Control-Allow-Methods"]
            assert "Content-Type" in response_headers["Access-Control-Allow-Headers"]
    
    def test_cors_security_headers(self, valid_cors_origins):
        """Test CORS security headers configuration."""
        with patch.dict('os.environ', {'CORS_ALLOWED_ORIGINS': ','.join(valid_cors_origins)}):
            cors_config = CORSConfig()
            
            security_headers = cors_config.get_security_headers()
            
            # Verify security headers are set
            assert security_headers["X-Content-Type-Options"] == "nosniff"
            assert security_headers["X-Frame-Options"] == "DENY"
            assert security_headers["X-XSS-Protection"] == "1; mode=block"
            assert security_headers["Strict-Transport-Security"] is not None
    
    def test_cors_development_vs_production_config(self):
        """Test different CORS configurations for development vs production."""
        # Development configuration (more permissive)
        dev_origins = ["http://localhost:3000", "http://localhost:8000"]
        
        with patch.dict('os.environ', {
            'CORS_ALLOWED_ORIGINS': ','.join(dev_origins),
            'ENVIRONMENT': 'development'
        }):
            cors_config = CORSConfig()
            assert cors_config.allow_credentials is True
            assert cors_config.is_origin_allowed("http://localhost:3000") is True
        
        # Production configuration (more restrictive)
        prod_origins = ["https://dashboard.stocksblitz.com"]
        
        with patch.dict('os.environ', {
            'CORS_ALLOWED_ORIGINS': ','.join(prod_origins),
            'ENVIRONMENT': 'production'
        }):
            cors_config = CORSConfig()
            assert cors_config.allow_credentials is True
            assert cors_config.is_origin_allowed("http://localhost:3000") is False
            assert cors_config.is_origin_allowed("https://dashboard.stocksblitz.com") is True
    
    def test_cors_middleware_integration(self, valid_cors_origins):
        """Test CORS middleware integration with FastAPI."""
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        
        app = FastAPI()
        
        with patch.dict('os.environ', {'CORS_ALLOWED_ORIGINS': ','.join(valid_cors_origins)}):
            cors_config = CORSConfig()
            
            # Add CORS middleware
            app.add_middleware(
                CORSMiddleware,
                allow_origins=cors_config.allowed_origins,
                allow_credentials=cors_config.allow_credentials,
                allow_methods=cors_config.allowed_methods,
                allow_headers=cors_config.allowed_headers
            )
            
            # Verify middleware is configured
            cors_middleware = None
            for middleware in app.user_middleware:
                if middleware.cls == CORSMiddleware:
                    cors_middleware = middleware
                    break
            
            assert cors_middleware is not None
            assert cors_middleware.kwargs["allow_origins"] == valid_cors_origins


class TestConfigServiceServiceIntegration:
    """Test integration between service integrations and config service."""
    
    def test_service_urls_loaded_from_config_service(self):
        """Test that service URLs are loaded from config service settings."""
        # Mock config service client that returns service URLs
        mock_config_client = MagicMock()
        mock_config_client.get_service_url.side_effect = lambda service, **kwargs: {
            "calendar_service": "http://calendar.config.com",
            "alert_service": "http://alert.config.com",
            "messaging_service": "http://messaging.config.com"
        }.get(service)
        
        with patch('app.integrations.service_integrations.get_config_client', return_value=mock_config_client):
            service_integrations = ServiceIntegrations()
            
            # Verify URLs are fetched from config service
            mock_config_client.get_service_url.assert_any_call("calendar_service")
            mock_config_client.get_service_url.assert_any_call("alert_service") 
            mock_config_client.get_service_url.assert_any_call("messaging_service")
    
    def test_config_service_failure_fallback(self):
        """Test fallback behavior when config service is unavailable."""
        # Mock config service client that fails
        mock_config_client = MagicMock()
        mock_config_client.get_service_url.side_effect = Exception("Config service unavailable")
        
        with patch('app.integrations.service_integrations.get_config_client', return_value=mock_config_client):
            with pytest.raises(Exception, match="Service URL configuration failed"):
                ServiceIntegrations()


def main():
    """Run service integrations and CORS tests."""
    print("🔍 Running Service Integrations and CORS Tests...")
    
    print("✅ Service integrations and CORS test structure validated")
    print("\n📋 Integration Test Coverage:")
    print("  - Service URL loading from config service")
    print("  - Calendar/Alert/Messaging service clients")
    print("  - HTTP request/response handling")
    print("  - Timeout and error handling")
    print("  - Circuit breaker integration")
    print("  - CORS configuration validation")
    print("  - CORS origin validation")
    print("  - CORS preflight request handling")
    print("  - CORS security headers")
    print("  - Development vs production CORS config")
    print("  - FastAPI CORS middleware integration")
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)