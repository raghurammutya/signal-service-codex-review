"""
Comprehensive integration tests for external service clients
Tests alert service, communication service, and subscription service integrations
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone
import httpx

from app.clients.alert_service_client import AlertServiceClient
from app.clients.comms_service_client import CommsServiceClient
from app.integrations.subscription_service_client import SubscriptionServiceClient
from app.integrations.service_integrations import ServiceIntegrations
from app.errors import ServiceUnavailableError, ConfigurationError


class TestAlertServiceClient:
    """Test alert service integration"""
    
    @pytest.fixture
    def client(self):
        """Create alert service client"""
        return AlertServiceClient(base_url="http://alert-service:8080")
    
    @pytest.fixture
    def sample_alert(self):
        """Sample alert data"""
        return {
            "user_id": "user_123",
            "alert_type": "price_target",
            "instrument_key": "NSE@RELIANCE@EQ",
            "condition": "price > 2500",
            "message": "RELIANCE crossed 2500",
            "priority": "high",
            "metadata": {
                "current_price": 2505.50,
                "target_price": 2500.00,
                "signal_source": "technical_analysis"
            }
        }
    
    @pytest.mark.asyncio
    async def test_send_alert_success(self, client, sample_alert):
        """Test successful alert sending"""
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "alert_id": "alert_123",
                "status": "sent",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            mock_post.return_value = mock_response
            
            result = await client.send_alert(sample_alert)
            
            assert result["alert_id"] == "alert_123"
            assert result["status"] == "sent"
            
            # Verify request was made correctly
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/api/v1/alerts" in call_args[0][0]
            assert call_args[1]["json"] == sample_alert
    
    @pytest.mark.asyncio
    async def test_send_alert_service_unavailable(self, client, sample_alert):
        """Test alert sending when service is unavailable"""
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection failed")
            
            with pytest.raises(ServiceUnavailableError, match="Alert service unavailable"):
                await client.send_alert(sample_alert)
    
    @pytest.mark.asyncio
    async def test_send_alert_validation_error(self, client):
        """Test alert sending with invalid data"""
        invalid_alert = {
            "user_id": "user_123",
            # Missing required fields
        }
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 422
            mock_response.json.return_value = {
                "error": "Validation failed",
                "details": ["alert_type is required", "instrument_key is required"]
            }
            mock_post.return_value = mock_response
            
            with pytest.raises(ValueError, match="Validation failed"):
                await client.send_alert(invalid_alert)
    
    @pytest.mark.asyncio
    async def test_send_bulk_alerts(self, client, sample_alert):
        """Test sending bulk alerts"""
        alerts = [sample_alert.copy() for _ in range(5)]
        for i, alert in enumerate(alerts):
            alert["user_id"] = f"user_{i}"
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "sent_count": 5,
                "failed_count": 0,
                "alert_ids": [f"alert_{i}" for i in range(5)]
            }
            mock_post.return_value = mock_response
            
            result = await client.send_bulk_alerts(alerts)
            
            assert result["sent_count"] == 5
            assert result["failed_count"] == 0
    
    @pytest.mark.asyncio
    async def test_get_alert_status(self, client):
        """Test getting alert delivery status"""
        alert_id = "alert_123"
        
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "alert_id": alert_id,
                "status": "delivered",
                "delivery_timestamp": datetime.now(timezone.utc).isoformat(),
                "delivery_methods": ["push", "email"],
                "delivery_details": {
                    "push": {"status": "delivered", "device_count": 2},
                    "email": {"status": "delivered", "email": "user@example.com"}
                }
            }
            mock_get.return_value = mock_response
            
            result = await client.get_alert_status(alert_id)
            
            assert result["status"] == "delivered"
            assert "delivery_details" in result
    
    @pytest.mark.asyncio
    async def test_alert_circuit_breaker(self, client, sample_alert):
        """Test circuit breaker behavior on repeated failures"""
        # Simulate repeated failures
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.side_effect = httpx.ConnectError("Service down")
            
            # First few failures should trigger circuit breaker
            for _ in range(3):
                with pytest.raises(ServiceUnavailableError):
                    await client.send_alert(sample_alert)
            
            # Circuit should be open now
            with pytest.raises(ServiceUnavailableError, match="Circuit breaker open"):
                await client.send_alert(sample_alert)


class TestCommsServiceClient:
    """Test communication service integration"""
    
    @pytest.fixture
    def client(self):
        """Create communication service client"""
        return CommsServiceClient(base_url="http://comms-service:8081")
    
    @pytest.fixture
    def sample_notification(self):
        """Sample notification data"""
        return {
            "user_id": "user_123",
            "notification_type": "signal_generated",
            "title": "New Trading Signal",
            "message": "BUY signal generated for RELIANCE",
            "channels": ["push", "email"],
            "priority": "high",
            "metadata": {
                "instrument": "NSE@RELIANCE@EQ",
                "signal_type": "momentum",
                "confidence": 0.85
            }
        }
    
    @pytest.mark.asyncio
    async def test_send_notification_success(self, client, sample_notification):
        """Test successful notification sending"""
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "notification_id": "notif_123",
                "status": "queued",
                "estimated_delivery": "2024-12-20T10:00:00Z"
            }
            mock_post.return_value = mock_response
            
            result = await client.send_notification(sample_notification)
            
            assert result["notification_id"] == "notif_123"
            assert result["status"] == "queued"
    
    @pytest.mark.asyncio
    async def test_send_email_notification(self, client):
        """Test sending email notification"""
        email_data = {
            "user_id": "user_123",
            "template": "signal_alert",
            "subject": "Trading Signal Alert",
            "variables": {
                "user_name": "John Doe",
                "signal": "BUY RELIANCE",
                "price": 2505.50
            },
            "priority": "normal"
        }
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "email_id": "email_123",
                "status": "sent",
                "delivery_timestamp": datetime.now(timezone.utc).isoformat()
            }
            mock_post.return_value = mock_response
            
            result = await client.send_email(email_data)
            
            assert result["email_id"] == "email_123"
            assert result["status"] == "sent"
    
    @pytest.mark.asyncio
    async def test_send_sms_notification(self, client):
        """Test sending SMS notification"""
        sms_data = {
            "user_id": "user_123",
            "phone_number": "+91-9876543210",
            "message": "BUY signal: RELIANCE @ 2505.50",
            "priority": "high"
        }
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "sms_id": "sms_123",
                "status": "sent",
                "delivery_timestamp": datetime.now(timezone.utc).isoformat(),
                "delivery_report": "delivered"
            }
            mock_post.return_value = mock_response
            
            result = await client.send_sms(sms_data)
            
            assert result["sms_id"] == "sms_123"
            assert result["status"] == "sent"
    
    @pytest.mark.asyncio
    async def test_get_notification_preferences(self, client):
        """Test getting user notification preferences"""
        user_id = "user_123"
        
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "user_id": user_id,
                "preferences": {
                    "email_enabled": True,
                    "push_enabled": True,
                    "sms_enabled": False,
                    "quiet_hours": {
                        "start": "22:00",
                        "end": "08:00"
                    },
                    "categories": {
                        "trading_signals": {"email": True, "push": True},
                        "price_alerts": {"email": False, "push": True}
                    }
                }
            }
            mock_get.return_value = mock_response
            
            result = await client.get_notification_preferences(user_id)
            
            assert result["user_id"] == user_id
            assert result["preferences"]["email_enabled"] is True
    
    @pytest.mark.asyncio
    async def test_notification_rate_limiting(self, client, sample_notification):
        """Test notification rate limiting"""
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 429
            mock_response.json.return_value = {
                "error": "Rate limit exceeded",
                "retry_after": 60
            }
            mock_post.return_value = mock_response
            
            with pytest.raises(ServiceUnavailableError, match="Rate limit exceeded"):
                await client.send_notification(sample_notification)


class TestSubscriptionServiceClient:
    """Test subscription service integration"""
    
    @pytest.fixture
    def client(self):
        """Create subscription service client"""
        return SubscriptionServiceClient(base_url="http://subscription-service:8082")
    
    @pytest.mark.asyncio
    async def test_get_user_subscription(self, client):
        """Test getting user subscription details"""
        user_id = "user_123"
        
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "user_id": user_id,
                "subscription": {
                    "plan": "premium",
                    "status": "active",
                    "start_date": "2024-01-01T00:00:00Z",
                    "end_date": "2024-12-31T23:59:59Z",
                    "features": [
                        "advanced_signals",
                        "fo_access",
                        "real_time_data",
                        "custom_indicators"
                    ],
                    "limits": {
                        "api_calls_per_minute": 300,
                        "concurrent_websockets": 10,
                        "custom_scripts": 50
                    }
                }
            }
            mock_get.return_value = mock_response
            
            result = await client.get_user_subscription(user_id)
            
            assert result["subscription"]["plan"] == "premium"
            assert result["subscription"]["status"] == "active"
    
    @pytest.mark.asyncio
    async def test_validate_feature_access(self, client):
        """Test validating user feature access"""
        user_id = "user_123"
        feature = "fo_access"
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "user_id": user_id,
                "feature": feature,
                "has_access": True,
                "reason": "Premium subscription active"
            }
            mock_post.return_value = mock_response
            
            result = await client.validate_feature_access(user_id, feature)
            
            assert result["has_access"] is True
            assert result["feature"] == feature
    
    @pytest.mark.asyncio
    async def test_track_feature_usage(self, client):
        """Test tracking feature usage"""
        usage_data = {
            "user_id": "user_123",
            "feature": "custom_scripts",
            "usage_type": "execution",
            "metadata": {
                "script_id": "script_456",
                "execution_time": 2.5,
                "resource_usage": {
                    "memory_mb": 45,
                    "cpu_seconds": 2.1
                }
            }
        }
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "usage_id": "usage_789",
                "status": "tracked",
                "remaining_quota": {
                    "custom_scripts": 47  # 50 - 3 used
                }
            }
            mock_post.return_value = mock_response
            
            result = await client.track_feature_usage(usage_data)
            
            assert result["usage_id"] == "usage_789"
            assert result["remaining_quota"]["custom_scripts"] == 47
    
    @pytest.mark.asyncio
    async def test_get_usage_analytics(self, client):
        """Test getting usage analytics"""
        user_id = "user_123"
        
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "user_id": user_id,
                "period": "current_month",
                "usage_summary": {
                    "api_calls": 15420,
                    "websocket_hours": 145.5,
                    "custom_script_executions": 23,
                    "data_volume_mb": 1240.8
                },
                "top_features": [
                    {"feature": "real_time_data", "usage_count": 8750},
                    {"feature": "technical_indicators", "usage_count": 3420},
                    {"feature": "custom_scripts", "usage_count": 23}
                ]
            }
            mock_get.return_value = mock_response
            
            result = await client.get_usage_analytics(user_id)
            
            assert result["usage_summary"]["api_calls"] == 15420
            assert len(result["top_features"]) == 3


class TestServiceIntegrations:
    """Test service integration orchestration"""
    
    @pytest.fixture
    def integrations(self):
        """Create service integrations instance"""
        return ServiceIntegrations()
    
    @pytest.mark.asyncio
    async def test_signal_notification_workflow(self, integrations):
        """Test complete signal notification workflow"""
        signal_data = {
            "user_id": "user_123",
            "signal": {
                "instrument_key": "NSE@RELIANCE@EQ",
                "type": "BUY",
                "price": 2505.50,
                "confidence": 0.85,
                "reason": "Bullish momentum detected"
            }
        }
        
        # Mock service calls
        with patch.object(integrations.alert_client, 'send_alert') as mock_alert:
            with patch.object(integrations.comms_client, 'send_notification') as mock_notification:
                with patch.object(integrations.subscription_client, 'validate_feature_access') as mock_feature:
                    
                    mock_feature.return_value = {"has_access": True}
                    mock_alert.return_value = {"alert_id": "alert_123", "status": "sent"}
                    mock_notification.return_value = {"notification_id": "notif_123", "status": "queued"}
                    
                    result = await integrations.process_signal_notification(signal_data)
                    
                    assert result["alert"]["status"] == "sent"
                    assert result["notification"]["status"] == "queued"
                    
                    # Verify all services were called
                    mock_feature.assert_called_once()
                    mock_alert.assert_called_once()
                    mock_notification.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_user_onboarding_workflow(self, integrations):
        """Test user onboarding workflow"""
        user_data = {
            "user_id": "new_user_123",
            "email": "user@example.com",
            "phone": "+91-9876543210",
            "subscription_plan": "basic",
            "preferences": {
                "email_alerts": True,
                "push_notifications": True
            }
        }
        
        with patch.object(integrations.subscription_client, 'create_subscription') as mock_subscription:
            with patch.object(integrations.comms_client, 'setup_notification_preferences') as mock_preferences:
                with patch.object(integrations.comms_client, 'send_welcome_email') as mock_welcome:
                    
                    mock_subscription.return_value = {"subscription_id": "sub_123", "status": "active"}
                    mock_preferences.return_value = {"preferences_id": "pref_123"}
                    mock_welcome.return_value = {"email_id": "welcome_123", "status": "sent"}
                    
                    result = await integrations.process_user_onboarding(user_data)
                    
                    assert result["subscription"]["status"] == "active"
                    assert result["welcome_email"]["status"] == "sent"
    
    @pytest.mark.asyncio
    async def test_service_health_monitoring(self, integrations):
        """Test service health monitoring"""
        with patch.object(integrations.alert_client, 'health_check') as mock_alert_health:
            with patch.object(integrations.comms_client, 'health_check') as mock_comms_health:
                with patch.object(integrations.subscription_client, 'health_check') as mock_sub_health:
                    
                    mock_alert_health.return_value = {"status": "healthy", "response_time": 45}
                    mock_comms_health.return_value = {"status": "healthy", "response_time": 67}
                    mock_sub_health.return_value = {"status": "degraded", "response_time": 890}
                    
                    result = await integrations.check_service_health()
                    
                    assert result["alert_service"]["status"] == "healthy"
                    assert result["comms_service"]["status"] == "healthy"
                    assert result["subscription_service"]["status"] == "degraded"
                    assert result["overall_status"] == "degraded"  # Any degraded service affects overall
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self, integrations):
        """Test circuit breaker behavior across services"""
        signal_data = {
            "user_id": "user_123",
            "signal": {"type": "BUY", "instrument": "RELIANCE"}
        }
        
        # Simulate alert service failure
        with patch.object(integrations.alert_client, 'send_alert') as mock_alert:
            with patch.object(integrations.comms_client, 'send_notification') as mock_notification:
                
                mock_alert.side_effect = ServiceUnavailableError("Alert service down")
                mock_notification.return_value = {"notification_id": "notif_123", "status": "queued"}
                
                result = await integrations.process_signal_notification(signal_data)
                
                # Should continue with other services even if one fails
                assert result["alert"]["status"] == "failed"
                assert result["notification"]["status"] == "queued"
                assert result["overall_status"] == "partial_success"


class TestServiceFailureRecovery:
    """Test service failure scenarios and recovery"""
    
    @pytest.fixture
    def alert_client(self):
        return AlertServiceClient(base_url="http://alert-service:8080")
    
    @pytest.mark.asyncio
    async def test_service_timeout_handling(self, alert_client):
        """Test handling of service timeout"""
        sample_alert = {
            "user_id": "user_123",
            "alert_type": "test",
            "message": "Test alert"
        }
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Request timeout")
            
            with pytest.raises(ServiceUnavailableError, match="timeout"):
                await alert_client.send_alert(sample_alert)
    
    @pytest.mark.asyncio
    async def test_service_retry_mechanism(self, alert_client):
        """Test automatic retry mechanism"""
        sample_alert = {
            "user_id": "user_123", 
            "alert_type": "test",
            "message": "Test alert"
        }
        
        with patch('httpx.AsyncClient.post') as mock_post:
            # First call fails, second succeeds
            mock_responses = [
                httpx.ConnectError("Connection failed"),
                Mock(status_code=200, json=lambda: {"alert_id": "alert_123"})
            ]
            mock_post.side_effect = mock_responses
            
            result = await alert_client.send_alert(sample_alert, retry_count=2)
            
            assert result["alert_id"] == "alert_123"
            assert mock_post.call_count == 2  # One failure, one success
    
    @pytest.mark.asyncio
    async def test_fallback_notification_channels(self):
        """Test fallback to alternative notification channels"""
        integrations = ServiceIntegrations()
        
        notification_data = {
            "user_id": "user_123",
            "message": "Important alert",
            "channels": ["push", "email", "sms"]
        }
        
        with patch.object(integrations.comms_client, 'send_notification') as mock_notification:
            # Push fails, email succeeds, SMS not attempted
            mock_notification.side_effect = [
                ServiceUnavailableError("Push service down"),
                {"notification_id": "email_123", "status": "sent"},
                {"notification_id": "sms_123", "status": "sent"}
            ]
            
            result = await integrations.send_notification_with_fallback(notification_data)
            
            assert result["successful_channels"] == ["email", "sms"]
            assert result["failed_channels"] == ["push"]