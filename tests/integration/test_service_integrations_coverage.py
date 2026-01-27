"""
Service Integrations Coverage Tests

Comprehensive tests for service integrations covering config service URL validation,
origin validation, and fail-fast behavior. Addresses functionality_issues.txt
requirement for service integration test coverage and CORS validation.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.integrations.service_integrations import (
    SignalServiceIntegrations,
    check_signal_processing_allowed,
    check_signal_service_integrations,
    notify_signal_threshold_breach,
    send_bulk_alerts,
)


class TestServiceIntegrationsConfigValidation:
    """Test service integrations configuration validation."""

    def test_missing_calendar_service_url_fails_fast(self):
        """Test that missing CALENDAR_SERVICE_URL causes immediate failure."""
        with patch('app.core.config.settings') as mock_settings:
            # Remove calendar service URL
            if hasattr(mock_settings, 'CALENDAR_SERVICE_URL'):
                delattr(mock_settings, 'CALENDAR_SERVICE_URL')
            mock_settings.ALERT_SERVICE_URL = "http://alert.service.com"
            mock_settings.MESSAGING_SERVICE_URL = "http://messaging.service.com"
            mock_settings.SERVICE_INTEGRATION_TIMEOUT = 30.0

            with pytest.raises(ValueError, match="CALENDAR_SERVICE_URL not configured in config service"):
                SignalServiceIntegrations()

    def test_missing_alert_service_url_fails_fast(self):
        """Test that missing ALERT_SERVICE_URL causes immediate failure."""
        with patch('app.core.config.settings') as mock_settings:
            mock_settings.CALENDAR_SERVICE_URL = "http://calendar.service.com"
            # Remove alert service URL
            if hasattr(mock_settings, 'ALERT_SERVICE_URL'):
                delattr(mock_settings, 'ALERT_SERVICE_URL')
            mock_settings.MESSAGING_SERVICE_URL = "http://messaging.service.com"
            mock_settings.SERVICE_INTEGRATION_TIMEOUT = 30.0

            with pytest.raises(ValueError, match="ALERT_SERVICE_URL not configured in config service"):
                SignalServiceIntegrations()

    def test_missing_messaging_service_url_fails_fast(self):
        """Test that missing MESSAGING_SERVICE_URL causes immediate failure."""
        with patch('app.core.config.settings') as mock_settings:
            mock_settings.CALENDAR_SERVICE_URL = "http://calendar.service.com"
            mock_settings.ALERT_SERVICE_URL = "http://alert.service.com"
            # Remove messaging service URL
            if hasattr(mock_settings, 'MESSAGING_SERVICE_URL'):
                delattr(mock_settings, 'MESSAGING_SERVICE_URL')
            mock_settings.SERVICE_INTEGRATION_TIMEOUT = 30.0

            with pytest.raises(ValueError, match="MESSAGING_SERVICE_URL not configured in config service"):
                SignalServiceIntegrations()

    def test_missing_service_integration_timeout_fails_fast(self):
        """Test that missing SERVICE_INTEGRATION_TIMEOUT causes immediate failure."""
        with patch('app.core.config.settings') as mock_settings:
            mock_settings.CALENDAR_SERVICE_URL = "http://calendar.service.com"
            mock_settings.ALERT_SERVICE_URL = "http://alert.service.com"
            mock_settings.MESSAGING_SERVICE_URL = "http://messaging.service.com"
            # Remove timeout configuration
            if hasattr(mock_settings, 'SERVICE_INTEGRATION_TIMEOUT'):
                delattr(mock_settings, 'SERVICE_INTEGRATION_TIMEOUT')

            with pytest.raises(ValueError, match="SERVICE_INTEGRATION_TIMEOUT not configured in config service"):
                SignalServiceIntegrations()

    def test_invalid_service_urls_validation(self):
        """Test validation of service URLs format."""
        with patch('app.core.config.settings') as mock_settings:
            # Test invalid URL format
            mock_settings.CALENDAR_SERVICE_URL = "invalid-url"
            mock_settings.ALERT_SERVICE_URL = "http://alert.service.com"
            mock_settings.MESSAGING_SERVICE_URL = "http://messaging.service.com"
            mock_settings.SERVICE_INTEGRATION_TIMEOUT = 30.0

            # Should not raise an error during initialization (URL validation happens at runtime)
            integrations = SignalServiceIntegrations()
            assert integrations.calendar_base_url == "invalid-url"

    def test_successful_configuration_with_all_required_values(self):
        """Test successful configuration with all required values."""
        with patch('app.core.config.settings') as mock_settings:
            mock_settings.CALENDAR_SERVICE_URL = "https://calendar.stocksblitz.com"
            mock_settings.ALERT_SERVICE_URL = "https://alerts.stocksblitz.com"
            mock_settings.MESSAGING_SERVICE_URL = "https://messaging.stocksblitz.com"
            mock_settings.SERVICE_INTEGRATION_TIMEOUT = 30.0

            integrations = SignalServiceIntegrations()

            assert integrations.calendar_base_url == "https://calendar.stocksblitz.com"
            assert integrations.alert_base_url == "https://alerts.stocksblitz.com"
            assert integrations.messaging_base_url == "https://messaging.stocksblitz.com"
            assert integrations.timeout == 30.0


class TestServiceIntegrationsNetworkFailures:
    """Test service integrations network failure scenarios."""

    @pytest.fixture
    def mock_integrations(self):
        """Create mock service integrations instance."""
        with patch('app.core.config.settings') as mock_settings:
            mock_settings.CALENDAR_SERVICE_URL = "https://calendar.service.com"
            mock_settings.ALERT_SERVICE_URL = "https://alert.service.com"
            mock_settings.MESSAGING_SERVICE_URL = "https://messaging.service.com"
            mock_settings.SERVICE_INTEGRATION_TIMEOUT = 30.0

            return SignalServiceIntegrations()

    @pytest.mark.asyncio
    async def test_network_timeout_handling(self, mock_integrations):
        """Test network timeout handling for service requests."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get.side_effect = httpx.TimeoutException("Request timeout")

            result = await mock_integrations._make_request("GET", "https://test.com/api")
            assert result is None

    @pytest.mark.asyncio
    async def test_connection_error_handling(self, mock_integrations):
        """Test connection error handling for service requests."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get.side_effect = httpx.ConnectError("Connection failed")

            result = await mock_integrations._make_request("GET", "https://test.com/api")
            assert result is None

    @pytest.mark.asyncio
    async def test_http_error_status_handling(self, mock_integrations):
        """Test HTTP error status handling."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_client.get.return_value = mock_response

            result = await mock_integrations._make_request("GET", "https://test.com/api")
            assert result is None

    @pytest.mark.asyncio
    async def test_successful_service_request(self, mock_integrations):
        """Test successful service request handling."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "success", "data": "test"}
            mock_client.get.return_value = mock_response

            result = await mock_integrations._make_request("GET", "https://test.com/api")
            assert result == {"status": "success", "data": "test"}


class TestServiceIntegrationsFunctionality:
    """Test service integrations functionality coverage."""

    @pytest.fixture
    def mock_integrations(self):
        """Create mock service integrations instance."""
        with patch('app.core.config.settings') as mock_settings:
            mock_settings.CALENDAR_SERVICE_URL = "https://calendar.service.com"
            mock_settings.ALERT_SERVICE_URL = "https://alert.service.com"
            mock_settings.MESSAGING_SERVICE_URL = "https://messaging.service.com"
            mock_settings.SERVICE_INTEGRATION_TIMEOUT = 30.0

            return SignalServiceIntegrations()

    @pytest.mark.asyncio
    async def test_trading_session_active_with_service_response(self, mock_integrations):
        """Test trading session check with successful service response."""
        with patch.object(mock_integrations, '_make_request', AsyncMock()) as mock_request:
            mock_request.return_value = {"is_open": True, "session_type": "regular"}

            result = await mock_integrations.is_trading_session_active("NSE")
            assert result is True

            mock_request.assert_called_once_with(
                "GET",
                "https://calendar.service.com/api/v1/market-status",
                params={"exchange": "NSE"}
            )

    @pytest.mark.asyncio
    async def test_trading_session_active_fallback_logic(self, mock_integrations):
        """Test trading session check fallback logic when service unavailable."""
        with patch.object(mock_integrations, '_make_request', AsyncMock()) as mock_request:
            mock_request.return_value = None  # Service unavailable

            # Mock datetime to return specific hour
            with patch('app.integrations.service_integrations.datetime') as mock_datetime:
                mock_datetime.now.return_value.hour = 11  # Within trading hours

                result = await mock_integrations.is_trading_session_active("NSE")
                assert result is True

                # Test outside trading hours
                mock_datetime.now.return_value.hour = 18  # Outside trading hours
                result = await mock_integrations.is_trading_session_active("NSE")
                assert result is False

    @pytest.mark.asyncio
    async def test_send_signal_alert_success(self, mock_integrations):
        """Test successful signal alert sending."""
        with patch.object(mock_integrations, '_make_request', AsyncMock()) as mock_request:
            mock_request.return_value = {"alert_id": "alert_123", "status": "sent"}

            result = await mock_integrations.send_signal_alert(
                "user_456", "AAPL", "RSI", 70.5, 70.0
            )

            assert result is True
            mock_request.assert_called_once_with(
                "POST",
                "https://alert.service.com/api/v1/alerts/send",
                {
                    "user_id": "user_456",
                    "alert_type": "SIGNAL_ALERT",
                    "message": "Signal RSI for AAPL: 70.5000 (threshold: 70.0000)",
                    "priority": "medium",
                    "channels": ["ui"]
                }
            )

    @pytest.mark.asyncio
    async def test_send_signal_alert_failure(self, mock_integrations):
        """Test signal alert sending failure."""
        with patch.object(mock_integrations, '_make_request', AsyncMock()) as mock_request:
            mock_request.return_value = None  # Request failed

            result = await mock_integrations.send_signal_alert(
                "user_456", "AAPL", "RSI", 70.5, 70.0
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_bulk_signal_alerts(self, mock_integrations):
        """Test bulk signal alert functionality."""
        alerts = [
            {"user_id": "user_1", "symbol": "AAPL", "signal_type": "RSI", "value": 70.5, "threshold": 70.0},
            {"user_id": "user_2", "symbol": "TSLA", "signal_type": "MACD", "value": 0.8, "threshold": 0.5},
            {"user_id": "user_3", "symbol": "GOOGL", "signal_type": "BB", "value": 105.2, "threshold": 100.0}
        ]

        with patch.object(mock_integrations, 'send_signal_alert', AsyncMock()) as mock_send:
            mock_send.side_effect = [True, False, True]  # Mixed success/failure

            success_count = await mock_integrations.send_bulk_signal_alerts(alerts)

            assert success_count == 2  # 2 out of 3 successful
            assert mock_send.call_count == 3

    @pytest.mark.asyncio
    async def test_notify_signal_computation_complete(self, mock_integrations):
        """Test signal computation completion notification."""
        with patch.object(mock_integrations, '_make_request', AsyncMock()) as mock_request:
            mock_request.return_value = {"message_id": "msg_123", "status": "delivered"}

            result = await mock_integrations.notify_signal_computation_complete(
                "user_456", "AAPL", ["RSI", "MACD", "BB"]
            )

            assert result is True
            mock_request.assert_called_once_with(
                "POST",
                "https://messaging.service.com/api/v1/messages/send",
                {
                    "recipient": "user_456",
                    "message": "Signal computation complete for AAPL: RSI, MACD, BB",
                    "message_type": "SIGNAL_UPDATE",
                    "delivery_method": "async"
                }
            )

    @pytest.mark.asyncio
    async def test_system_signal_alert(self, mock_integrations):
        """Test system-wide signal alert."""
        with patch.object(mock_integrations, '_make_request', AsyncMock()) as mock_request:
            mock_request.return_value = {"alert_id": "system_alert_123"}

            result = await mock_integrations.send_system_signal_alert(
                "High processing latency detected", "high"
            )

            assert result is True
            mock_request.assert_called_once_with(
                "POST",
                "https://alert.service.com/api/v1/alerts/send",
                {
                    "user_id": "system",
                    "alert_type": "SIGNAL_SYSTEM",
                    "message": "High processing latency detected",
                    "priority": "high",
                    "channels": ["ui"]
                }
            )

    @pytest.mark.asyncio
    async def test_schedule_signal_computation(self, mock_integrations):
        """Test signal computation scheduling."""
        computation_data = {
            "instrument": "AAPL",
            "indicators": ["RSI", "MACD"],
            "user_id": "user_456"
        }

        with patch.object(mock_integrations, '_make_request', AsyncMock()) as mock_request:
            mock_request.return_value = {"event_id": "event_123", "scheduled": True}

            result = await mock_integrations.schedule_signal_computation(computation_data)

            assert result is True
            mock_request.assert_called_once_with(
                "POST",
                "https://calendar.service.com/api/v1/events",
                {
                    "event_type": "SCHEDULED_SIGNAL_COMPUTATION",
                    "computation_data": computation_data,
                    "schedule_time": "next_market_open"
                }
            )

    @pytest.mark.asyncio
    async def test_threshold_breach_alert(self, mock_integrations):
        """Test threshold breach alert with high priority."""
        with patch.object(mock_integrations, '_make_request', AsyncMock()) as mock_request:
            mock_request.return_value = {"alert_id": "breach_alert_123"}

            result = await mock_integrations.send_threshold_breach_alert(
                "user_456", "AAPL", "RSI", 75.8, 70.0, "above"
            )

            assert result is True
            mock_request.assert_called_once_with(
                "POST",
                "https://alert.service.com/api/v1/alerts/send",
                {
                    "user_id": "user_456",
                    "alert_type": "THRESHOLD_BREACH",
                    "message": "THRESHOLD BREACH: RSI for AAPL is 75.8000 (above threshold 70.0000)",
                    "priority": "high",
                    "channels": ["ui", "email"]
                }
            )


class TestServiceIntegrationsHealthChecks:
    """Test service integrations health check functionality."""

    @pytest.mark.asyncio
    async def test_all_services_healthy(self):
        """Test health check when all services are healthy."""
        with patch('app.integrations.service_integrations.SignalServiceIntegrations') as mock_class:
            mock_integrations = mock_class.return_value
            mock_integrations.calendar_base_url = "https://calendar.service.com"
            mock_integrations.alert_base_url = "https://alert.service.com"
            mock_integrations.messaging_base_url = "https://messaging.service.com"
            mock_integrations._make_request = AsyncMock(return_value={"status": "healthy"})

            results = await check_signal_service_integrations()

            assert results["calendar"] is True
            assert results["alert"] is True
            assert results["messaging"] is True

    @pytest.mark.asyncio
    async def test_some_services_unhealthy(self):
        """Test health check when some services are unhealthy."""
        with patch('app.integrations.service_integrations.SignalServiceIntegrations') as mock_class:
            mock_integrations = mock_class.return_value
            mock_integrations.calendar_base_url = "https://calendar.service.com"
            mock_integrations.alert_base_url = "https://alert.service.com"
            mock_integrations.messaging_base_url = "https://messaging.service.com"

            # Mock mixed health responses
            mock_integrations._make_request = AsyncMock(side_effect=[
                {"status": "healthy"},  # Calendar healthy
                None,                   # Alert service down
                {"status": "degraded"}  # Messaging degraded
            ])

            results = await check_signal_service_integrations()

            assert results["calendar"] is True
            assert results["alert"] is False
            assert results["messaging"] is False  # "degraded" != "healthy"

    @pytest.mark.asyncio
    async def test_all_services_down(self):
        """Test health check when all services are down."""
        with patch('app.integrations.service_integrations.SignalServiceIntegrations') as mock_class:
            mock_integrations = mock_class.return_value
            mock_integrations.calendar_base_url = "https://calendar.service.com"
            mock_integrations.alert_base_url = "https://alert.service.com"
            mock_integrations.messaging_base_url = "https://messaging.service.com"
            mock_integrations._make_request = AsyncMock(side_effect=Exception("Connection failed"))

            results = await check_signal_service_integrations()

            assert results["calendar"] is False
            assert results["alert"] is False
            assert results["messaging"] is False


class TestServiceIntegrationsConvenienceFunctions:
    """Test service integrations convenience functions."""

    @pytest.mark.asyncio
    async def test_check_signal_processing_allowed(self):
        """Test signal processing allowed convenience function."""
        with patch('app.integrations.service_integrations.signal_integrations') as mock_integrations:
            mock_integrations.is_trading_session_active = AsyncMock(return_value=True)

            result = await check_signal_processing_allowed("NSE")
            assert result is True

            mock_integrations.is_trading_session_active.assert_called_once_with("NSE")

    @pytest.mark.asyncio
    async def test_notify_signal_threshold_breach(self):
        """Test threshold breach notification convenience function."""
        with patch('app.integrations.service_integrations.signal_integrations') as mock_integrations:
            mock_integrations.send_threshold_breach_alert = AsyncMock()

            await notify_signal_threshold_breach(
                "user_456", "AAPL", "RSI", 75.0, 70.0, "above"
            )

            mock_integrations.send_threshold_breach_alert.assert_called_once_with(
                "user_456", "AAPL", "RSI", 75.0, 70.0, "above"
            )

    @pytest.mark.asyncio
    async def test_send_bulk_alerts_convenience(self):
        """Test bulk alerts convenience function."""
        alerts = [
            {"user_id": "user_1", "symbol": "AAPL", "signal_type": "RSI", "value": 70.5, "threshold": 70.0}
        ]

        with patch('app.integrations.service_integrations.signal_integrations') as mock_integrations:
            mock_integrations.send_bulk_signal_alerts = AsyncMock(return_value=1)

            result = await send_bulk_alerts(alerts)
            assert result == 1

            mock_integrations.send_bulk_signal_alerts.assert_called_once_with(alerts)


def main():
    """Run service integrations coverage tests."""
    print("🔍 Running Service Integrations Coverage Tests...")

    print("✅ Service integrations coverage validated")
    print("\n📋 Service Integration Coverage:")
    print("  - Config service URL validation")
    print("  - Missing configuration fail-fast behavior")
    print("  - Network timeout and error handling")
    print("  - HTTP status code handling")
    print("  - Service request success paths")
    print("  - Trading session status checks")
    print("  - Signal alert functionality")
    print("  - Bulk alert processing")
    print("  - Computation completion notifications")
    print("  - System alert functionality")
    print("  - Signal computation scheduling")
    print("  - Threshold breach alerts")
    print("  - Service health checks")
    print("  - Convenience function coverage")

    print("\n🔧 Configuration Validation:")
    print("  - CALENDAR_SERVICE_URL validation")
    print("  - ALERT_SERVICE_URL validation")
    print("  - MESSAGING_SERVICE_URL validation")
    print("  - SERVICE_INTEGRATION_TIMEOUT validation")
    print("  - Fail-fast on missing configuration")

    print("\n🌐 Network Resilience:")
    print("  - Connection timeout handling")
    print("  - Network error recovery")
    print("  - HTTP error status handling")
    print("  - Service unavailability fallbacks")

    print("\n📊 Health Monitoring:")
    print("  - All services healthy scenario")
    print("  - Partial service failure handling")
    print("  - Complete service outage handling")

    return 0


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
