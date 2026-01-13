"""
Test that leaked signals are blocked from delivery.
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from app.api.v2.websocket import ConnectionManager


@pytest.mark.asyncio
async def test_leak_detection_blocks_delivery():
    """Test that signals with detected leaks are not delivered."""
    
    # Create connection manager
    manager = ConnectionManager()
    
    # Mock watermark service
    mock_watermark_service = AsyncMock()
    mock_watermark_service.watermark_signal = AsyncMock(return_value={
        "data": "watermarked",
        "metadata": {"_wm": "abc123", "_wm_ts": 1234567890}
    })
    
    # Mock detect_leak_and_enforce to return leak detected with auto-enforce
    mock_watermark_service.detect_leak_and_enforce = AsyncMock(return_value={
        "leak_detected": True,
        "enforcement_policy": "auto_enforce",
        "should_block": True,
        "original_user_id": "user_456",
        "violation_id": "viol_789"
    })
    
    manager.watermark_service = mock_watermark_service
    
    # Set up connections
    client1_id = "client_1" 
    client2_id = "client_2"
    stream_key = "marketplace:prod_test123:NSE_EQ|RELIANCE:momentum"
    
    # Mock WebSockets
    mock_ws1 = AsyncMock()
    mock_ws2 = AsyncMock()
    
    # Client 1 is legitimate, Client 2 has leaked signal
    manager.active_connections[client1_id] = mock_ws1
    manager.active_connections[client2_id] = mock_ws2
    manager.subscription_connections[stream_key] = {client1_id, client2_id}
    
    # Set up metadata
    manager.connection_metadata[client1_id] = {
        "user_id": "user_123",
        "marketplace_metadata": {
            stream_key: {
                "subscription_id": "sub_12345",
                "product_id": "prod_test123",
                "signal_id": "momentum"
            }
        }
    }
    
    manager.connection_metadata[client2_id] = {
        "user_id": "user_789",  # Different user
        "marketplace_metadata": {
            stream_key: {
                "subscription_id": "sub_67890",  # Different subscription
                "product_id": "prod_test123",
                "signal_id": "momentum"
            }
        }
    }
    
    # Configure detect_leak_and_enforce to return different results for different users
    def leak_detect_side_effect(*args, **kwargs):
        receiving_user = kwargs.get('receiving_user_id')
        if receiving_user == "user_789":  # Client 2
            return {
                "leak_detected": True,
                "enforcement_policy": "auto_enforce",
                "should_block": True,
                "original_user_id": "user_123",
                "violation_id": "viol_789"
            }
        else:
            return {"leak_detected": False}
    
    mock_watermark_service.detect_leak_and_enforce.side_effect = leak_detect_side_effect
    
    # Broadcast a signal
    test_data = {"value": 42, "timestamp": datetime.utcnow().isoformat()}
    await manager.broadcast_to_subscription(stream_key, test_data)
    
    # Verify Client 1 received the signal (legitimate)
    mock_ws1.send_json.assert_called()
    sent_data = mock_ws1.send_json.call_args[0][0]
    assert sent_data.get("data") == "watermarked"
    
    # Verify Client 2 did NOT receive the signal (blocked due to leak)
    mock_ws2.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_log_only_policy_still_delivers():
    """Test that log-only policy doesn't block delivery."""
    
    manager = ConnectionManager()
    
    # Mock watermark service with log-only policy
    mock_watermark_service = AsyncMock()
    mock_watermark_service.watermark_signal = AsyncMock(return_value={
        "data": "watermarked",
        "metadata": {"_wm": "abc123", "_wm_ts": 1234567890}
    })
    
    mock_watermark_service.detect_leak_and_enforce = AsyncMock(return_value={
        "leak_detected": True,
        "enforcement_policy": "log_only",  # Log only, don't block
        "should_block": False,
        "original_user_id": "user_456",
        "violation_id": "viol_789"
    })
    
    manager.watermark_service = mock_watermark_service
    
    # Set up connection
    client_id = "client_1"
    stream_key = "marketplace:prod_test123:NSE_EQ|RELIANCE:momentum"
    
    mock_ws = AsyncMock()
    manager.active_connections[client_id] = mock_ws
    manager.subscription_connections[stream_key] = {client_id}
    
    manager.connection_metadata[client_id] = {
        "user_id": "user_123",
        "marketplace_metadata": {
            stream_key: {
                "subscription_id": "sub_12345",
                "product_id": "prod_test123",
                "signal_id": "momentum"
            }
        }
    }
    
    # Broadcast a signal
    test_data = {"value": 42, "timestamp": datetime.utcnow().isoformat()}
    await manager.broadcast_to_subscription(stream_key, test_data)
    
    # Verify signal was still delivered despite leak detection (log-only mode)
    mock_ws.send_json.assert_called()
    sent_data = mock_ws.send_json.call_args[0][0]
    assert sent_data.get("data") == "watermarked"


@pytest.mark.asyncio
async def test_non_marketplace_signals_not_blocked():
    """Test that non-marketplace signals are never blocked."""
    
    manager = ConnectionManager()
    
    # No watermark service configured
    manager.watermark_service = None
    
    # Set up connection for public signal
    client_id = "client_1" 
    stream_key = "public:NSE_EQ|RELIANCE:price"
    
    mock_ws = AsyncMock()
    manager.active_connections[client_id] = mock_ws
    manager.subscription_connections[stream_key] = {client_id}
    
    manager.connection_metadata[client_id] = {"user_id": "user_123"}
    
    # Broadcast a signal
    test_data = {"price": 2500.50, "timestamp": datetime.utcnow().isoformat()}
    await manager.broadcast_to_subscription(stream_key, test_data)
    
    # Verify signal was delivered (no watermarking for public signals)
    mock_ws.send_json.assert_called()
    sent_data = mock_ws.send_json.call_args[0][0]
    assert sent_data == test_data


@pytest.mark.asyncio
async def test_watermark_service_failure_still_delivers():
    """Test that watermark service failures don't block delivery (fail-open)."""
    
    manager = ConnectionManager()
    
    # Mock watermark service that fails
    mock_watermark_service = AsyncMock()
    mock_watermark_service.watermark_signal = AsyncMock(side_effect=Exception("Service error"))
    
    manager.watermark_service = mock_watermark_service
    
    # Set up connection
    client_id = "client_1"
    stream_key = "marketplace:prod_test123:NSE_EQ|RELIANCE:momentum"
    
    mock_ws = AsyncMock()
    manager.active_connections[client_id] = mock_ws
    manager.subscription_connections[stream_key] = {client_id}
    
    manager.connection_metadata[client_id] = {
        "user_id": "user_123",
        "marketplace_metadata": {
            stream_key: {
                "subscription_id": "sub_12345",
                "product_id": "prod_test123",
                "signal_id": "momentum"
            }
        }
    }
    
    # Broadcast a signal
    test_data = {"value": 42, "timestamp": datetime.utcnow().isoformat()}
    
    # Should not raise exception
    await manager.broadcast_to_subscription(stream_key, test_data)
    
    # Verify signal was delivered (fail-open on watermark error)
    mock_ws.send_json.assert_called()
    sent_data = mock_ws.send_json.call_args[0][0]
    assert sent_data == test_data  # Original data sent on watermark failure


if __name__ == "__main__":
    pytest.main([__file__, "-v"])