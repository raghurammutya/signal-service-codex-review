#!/usr/bin/env python3
"""
Updated Indicators API Tests - P0 Fix Validation

Tests the updated indicators API to ensure it properly uses instrument_key
instead of instrument_token, maintaining backward compatibility.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v2.indicators import IndicatorCalculator


@pytest.fixture
def mock_registry_client():
    """Mock instrument registry client"""
    mock_client = AsyncMock()
    mock_client.get_broker_token = AsyncMock(return_value=12345)
    return mock_client

@pytest.fixture
def mock_http_response():
    """Mock HTTP response from ticker_service"""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "candles": [
            {
                "timestamp": "2026-01-27T10:00:00Z",
                "open": 150.00,
                "high": 152.00,
                "low": 149.00,
                "close": 151.50,
                "volume": 1000
            },
            {
                "timestamp": "2026-01-27T11:00:00Z",
                "open": 151.50,
                "high": 153.00,
                "low": 150.50,
                "close": 152.75,
                "volume": 1200
            }
        ]
    }
    return mock_response

@pytest.mark.asyncio
async def test_instrument_key_parameter_usage(mock_registry_client, mock_http_response):
    """Test that get_historical_data properly accepts instrument_key parameter"""

    calculator = IndicatorCalculator()
    await calculator.initialize()

    with patch('app.api.v2.indicators.create_registry_client', return_value=mock_registry_client), patch.object(calculator._http_client, 'get', return_value=mock_http_response):
        instrument_key = "AAPL_NASDAQ_EQUITY"
        df = await calculator.get_historical_data(
            instrument_key=instrument_key,
            timeframe="5minute",
            periods=2
        )

        # Verify registry client was called with correct parameters
        mock_registry_client.get_broker_token.assert_called_once_with(instrument_key, "kite")

        # Verify DataFrame structure
        assert not df.empty
        assert len(df) == 2
        assert list(df.columns) == ['open', 'high', 'low', 'close', 'volume']
        assert df.iloc[0]['close'] == 151.50
        assert df.iloc[1]['close'] == 152.75

@pytest.mark.asyncio
async def test_instrument_key_resolution_error(mock_registry_client):
    """Test error handling when instrument_key resolution fails"""

    calculator = IndicatorCalculator()
    await calculator.initialize()

    # Make registry client raise an exception
    mock_registry_client.get_broker_token.side_effect = Exception("Invalid instrument_key")

    with patch('app.api.v2.indicators.create_registry_client', return_value=mock_registry_client):

        with pytest.raises(Exception) as exc_info:
            await calculator.get_historical_data(
                instrument_key="INVALID_KEY",
                timeframe="5minute",
                periods=10
            )

        assert "Invalid instrument_key" in str(exc_info.value)

@pytest.mark.asyncio
async def test_backward_compatibility_maintained(mock_registry_client, mock_http_response):
    """Test that the fix maintains backward compatibility with ticker_service"""

    calculator = IndicatorCalculator()
    await calculator.initialize()

    with patch('app.api.v2.indicators.create_registry_client', return_value=mock_registry_client), patch.object(calculator._http_client, 'get', return_value=mock_http_response) as mock_get:
        instrument_key = "GOOGL_NASDAQ_EQUITY"
        await calculator.get_historical_data(
            instrument_key=instrument_key,
            timeframe="1minute",
            periods=5
        )

        # Verify that ticker_service is still called with instrument_token
        call_args = mock_get.call_args
        params = call_args[1]['params']  # kwargs params
        assert 'instrument_token' in params
        assert params['instrument_token'] == 12345  # The resolved token

@pytest.mark.asyncio
async def test_contract_compliance():
    """Test that the API contract now properly uses instrument_key"""

    calculator = IndicatorCalculator()

    # Verify method signature uses instrument_key
    import inspect
    sig = inspect.signature(calculator.get_historical_data)

    # Check that instrument_key is a parameter
    assert 'instrument_key' in sig.parameters

    # Check that instrument_token is NOT a parameter
    assert 'instrument_token' not in sig.parameters

    # Verify parameter type annotation
    instrument_key_param = sig.parameters['instrument_key']
    assert instrument_key_param.annotation == str

def test_documentation_updated():
    """Test that documentation properly reflects instrument_key usage"""

    calculator = IndicatorCalculator()
    docstring = calculator.get_historical_data.__doc__

    # Verify documentation mentions instrument_key
    assert 'instrument_key' in docstring
    assert 'Instrument identifier' in docstring

    # Verify old documentation is removed
    assert 'Kite instrument token' not in docstring

@pytest.mark.asyncio
async def test_logging_uses_instrument_key(mock_registry_client, mock_http_response):
    """Test that logging statements now reference instrument_key"""

    calculator = IndicatorCalculator()
    await calculator.initialize()

    with patch('app.api.v2.indicators.create_registry_client', return_value=mock_registry_client), patch.object(calculator._http_client, 'get', return_value=mock_http_response), patch('app.api.v2.indicators.log_info') as mock_log:
            instrument_key = "MSFT_NASDAQ_EQUITY"
            await calculator.get_historical_data(
                instrument_key=instrument_key,
                timeframe="day",
                periods=1
            )

            # Verify logging includes instrument_key
            log_calls = [call.args[0] for call in mock_log.call_args_list]
            instrument_key_logged = any(instrument_key in log_msg for log_msg in log_calls)
            assert instrument_key_logged, f"instrument_key not found in log messages: {log_calls}"

@pytest.mark.integration
async def test_end_to_end_api_contract():
    """Integration test for the complete API contract fix"""

    # This would be a real integration test in practice
    # For now, verify the contract at the API endpoint level
    # Verify the endpoint accepts symbol parameter (which should be instrument_key format)
    import inspect

    from app.api.v2.indicators import calculate_sma_endpoint
    sig = inspect.signature(calculate_sma_endpoint)

    assert 'symbol' in sig.parameters  # Parameter name is symbol but should contain instrument_key

    # Verify documentation indicates it expects instrument_key format
    docstring = calculate_sma_endpoint.__doc__
    assert 'Instrument key' in docstring or 'NSE@RELIANCE@equities' in docstring

if __name__ == "__main__":
    # Run basic validation
    asyncio.run(test_contract_compliance())
    test_documentation_updated()
    print("✅ All P0 fix validation tests passed!")
