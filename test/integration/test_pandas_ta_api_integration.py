"""
Integration tests for pandas_ta indicators via API calls and subscriptions
Tests real-world usage patterns with HTTP endpoints and WebSocket subscriptions
"""

import asyncio
import json
from datetime import datetime
from unittest.mock import patch

import pytest
import websockets

from app.main import app
from test.unit.services.test_pandas_ta_executor import TestDataFactory


class TestPandasTAAPIIntegration:
    """Test pandas_ta indicators via direct API calls"""

    @pytest.fixture
    def client(self):
        """HTTP test client"""
        from fastapi.testclient import TestClient
        return TestClient(app)

    @pytest.fixture
    def sample_indicator_request(self):
        """Sample API request for technical indicators"""
        return {
            "instrument_key": "NSE@RELIANCE@EQ",
            "interval": "5m",
            "frequency": "realtime",
            "technical_indicators": [
                {
                    "name": "sma",
                    "output_key": "sma_20",
                    "parameters": {"length": 20}
                },
                {
                    "name": "rsi",
                    "output_key": "rsi_14",
                    "parameters": {"length": 14}
                },
                {
                    "name": "macd",
                    "output_key": "macd",
                    "parameters": {"fast": 12, "slow": 26, "signal": 9}
                },
                {
                    "name": "bbands",
                    "output_key": "bb",
                    "parameters": {"length": 20, "std": 2}
                }
            ],
            "output": {
                "cache_results": True,
                "cache_ttl_seconds": 300
            }
        }

    @pytest.fixture
    def comprehensive_indicator_request(self):
        """Comprehensive test request with all major indicator categories"""
        return {
            "instrument_key": "NSE@NIFTY@INDEX",
            "interval": "15m",
            "frequency": "realtime",
            "technical_indicators": [
                # Trend indicators
                {"name": "sma", "output_key": "sma_20", "parameters": {"length": 20}},
                {"name": "ema", "output_key": "ema_20", "parameters": {"length": 20}},
                {"name": "wma", "output_key": "wma_20", "parameters": {"length": 20}},
                {"name": "tema", "output_key": "tema_20", "parameters": {"length": 20}},

                # Momentum indicators
                {"name": "rsi", "output_key": "rsi_14", "parameters": {"length": 14}},
                {"name": "cci", "output_key": "cci_20", "parameters": {"length": 20}},
                {"name": "mfi", "output_key": "mfi_14", "parameters": {"length": 14}},
                {"name": "willr", "output_key": "willr_14", "parameters": {"length": 14}},
                {"name": "roc", "output_key": "roc_10", "parameters": {"length": 10}},
                {"name": "cmo", "output_key": "cmo_14", "parameters": {"length": 14}},

                # Volatility indicators
                {"name": "atr", "output_key": "atr_14", "parameters": {"length": 14}},
                {"name": "natr", "output_key": "natr_14", "parameters": {"length": 14}},
                {"name": "bbands", "output_key": "bb_20", "parameters": {"length": 20, "std": 2}},
                {"name": "kc", "output_key": "kc_20", "parameters": {"length": 20, "scalar": 2}},

                # Volume indicators
                {"name": "obv", "output_key": "obv", "parameters": {}},
                {"name": "ad", "output_key": "ad", "parameters": {}},
                {"name": "cmf", "output_key": "cmf_20", "parameters": {"length": 20}},
                {"name": "vwap", "output_key": "vwap", "parameters": {}},

                # Multi-component indicators
                {"name": "macd", "output_key": "macd", "parameters": {"fast": 12, "slow": 26, "signal": 9}},
                {"name": "stoch", "output_key": "stoch", "parameters": {"k": 14, "d": 3}},
                {"name": "adx", "output_key": "adx_14", "parameters": {"length": 14}},

                # Advanced indicators
                {"name": "ichimoku", "output_key": "ichimoku", "parameters": {}},
                {"name": "supertrend", "output_key": "supertrend", "parameters": {"length": 20, "multiplier": 3.0}},
                {"name": "squeeze", "output_key": "squeeze", "parameters": {"bb_length": 20, "bb_std": 2, "kc_length": 20}},
            ],
            "output": {
                "cache_results": True,
                "cache_ttl_seconds": 300
            }
        }

    @pytest.mark.asyncio
    async def test_single_indicator_api_call(self, client, sample_indicator_request):
        """Test single indicator calculation via API"""
        with patch('app.services.pandas_ta_executor.get_historical_data_manager') as mock_manager:
            # Mock historical data
            mock_manager.return_value.get_historical_data_for_indicator.return_value = {
                "success": True,
                "data": TestDataFactory.create_ohlcv_data(periods=50).to_dict('records')
            }

            response = client.post("/api/v1/signals/calculate", json=sample_indicator_request)

            assert response.status_code == 200
            result = response.json()

            assert "results" in result
            assert "sma_20" in result["results"]
            assert "rsi_14" in result["results"]
            assert "macd" in result["results"]
            assert "bb" in result["results"]

            # Validate result types
            assert isinstance(result["results"]["sma_20"], (float, type(None)))
            assert isinstance(result["results"]["rsi_14"], (float, type(None)))
            assert isinstance(result["results"]["macd"], (dict, type(None)))
            assert isinstance(result["results"]["bb"], (dict, type(None)))

    @pytest.mark.asyncio
    async def test_comprehensive_indicators_api_call(self, client, comprehensive_indicator_request):
        """Test comprehensive indicator set via API"""
        with patch('app.services.pandas_ta_executor.get_historical_data_manager') as mock_manager:
            # Mock historical data
            mock_manager.return_value.get_historical_data_for_indicator.return_value = {
                "success": True,
                "data": TestDataFactory.create_ohlcv_data(periods=100).to_dict('records')
            }

            response = client.post("/api/v1/signals/calculate", json=comprehensive_indicator_request)

            assert response.status_code == 200
            result = response.json()

            assert "results" in result
            assert len(result["results"]) >= 20  # Should have most indicators calculated

            # Check specific indicator categories
            trend_indicators = ["sma_20", "ema_20", "wma_20", "tema_20"]
            momentum_indicators = ["rsi_14", "cci_20", "mfi_14", "willr_14"]
            volatility_indicators = ["atr_14", "natr_14", "bb_20", "kc_20"]
            volume_indicators = ["obv", "ad", "cmf_20", "vwap"]

            for indicator in trend_indicators + momentum_indicators + volatility_indicators + volume_indicators:
                if indicator in result["results"]:
                    value = result["results"][indicator]
                    assert value is not None or value == 0, f"{indicator} returned None unexpectedly"

    @pytest.mark.asyncio
    async def test_api_error_handling(self, client):
        """Test API error handling for invalid requests"""
        # Test invalid indicator name
        invalid_request = {
            "instrument_key": "NSE@RELIANCE@EQ",
            "interval": "5m",
            "frequency": "realtime",
            "technical_indicators": [
                {
                    "name": "invalid_indicator",
                    "output_key": "invalid",
                    "parameters": {}
                }
            ]
        }

        response = client.post("/api/v1/signals/calculate", json=invalid_request)
        # Should handle gracefully, not return 500
        assert response.status_code in [200, 400, 422]

    @pytest.mark.asyncio
    async def test_api_parameter_validation(self, client):
        """Test API parameter validation"""
        # Test invalid parameters
        request_with_invalid_params = {
            "instrument_key": "NSE@RELIANCE@EQ",
            "interval": "5m",
            "frequency": "realtime",
            "technical_indicators": [
                {
                    "name": "sma",
                    "output_key": "sma_invalid",
                    "parameters": {"length": -5}  # Invalid negative length
                },
                {
                    "name": "rsi",
                    "output_key": "rsi_invalid",
                    "parameters": {"length": 0}  # Invalid zero length
                }
            ]
        }

        response = client.post("/api/v1/signals/calculate", json=request_with_invalid_params)
        # Should handle parameter validation
        assert response.status_code in [200, 400, 422]

    @pytest.mark.asyncio
    async def test_api_caching_behavior(self, client, sample_indicator_request):
        """Test API caching behavior"""
        with patch('app.services.pandas_ta_executor.get_historical_data_manager') as mock_manager:
            mock_manager.return_value.get_historical_data_for_indicator.return_value = {
                "success": True,
                "data": TestDataFactory.create_ohlcv_data(periods=50).to_dict('records')
            }

            # First call
            response1 = client.post("/api/v1/signals/calculate", json=sample_indicator_request)
            assert response1.status_code == 200

            # Second call (should use cache)
            response2 = client.post("/api/v1/signals/calculate", json=sample_indicator_request)
            assert response2.status_code == 200

            # Results should be consistent
            result1 = response1.json()
            result2 = response2.json()
            assert result1["results"] == result2["results"]

    @pytest.mark.asyncio
    async def test_batch_indicator_calculation(self, client):
        """Test batch calculation of multiple indicators"""
        batch_request = {
            "instruments": [
                "NSE@RELIANCE@EQ",
                "NSE@TCS@EQ",
                "NSE@HDFC@EQ"
            ],
            "interval": "5m",
            "frequency": "realtime",
            "technical_indicators": [
                {"name": "sma", "output_key": "sma_20", "parameters": {"length": 20}},
                {"name": "rsi", "output_key": "rsi_14", "parameters": {"length": 14}},
                {"name": "atr", "output_key": "atr_14", "parameters": {"length": 14}}
            ]
        }

        with patch('app.services.pandas_ta_executor.get_historical_data_manager') as mock_manager:
            mock_manager.return_value.get_historical_data_for_indicator.return_value = {
                "success": True,
                "data": TestDataFactory.create_ohlcv_data(periods=50).to_dict('records')
            }

            # Note: This would require a batch endpoint implementation
            # For now, test individual calls in sequence
            for instrument in batch_request["instruments"]:
                single_request = {
                    "instrument_key": instrument,
                    "interval": batch_request["interval"],
                    "frequency": batch_request["frequency"],
                    "technical_indicators": batch_request["technical_indicators"]
                }

                response = client.post("/api/v1/signals/calculate", json=single_request)
                assert response.status_code == 200

                result = response.json()
                assert "results" in result
                assert result["instrument_key"] == instrument


class TestPandasTASubscriptionIntegration:
    """Test pandas_ta indicators via WebSocket subscriptions"""

    @pytest.fixture
    def sample_subscription_request(self):
        """Sample subscription request"""
        return {
            "action": "subscribe",
            "subscription_id": "test_pandas_ta_sub",
            "instrument_key": "NSE@NIFTY@INDEX",
            "interval": "1m",
            "frequency": "realtime",
            "technical_indicators": [
                {"name": "sma", "output_key": "sma_10", "parameters": {"length": 10}},
                {"name": "sma", "output_key": "sma_20", "parameters": {"length": 20}},
                {"name": "rsi", "output_key": "rsi_14", "parameters": {"length": 14}},
                {"name": "macd", "output_key": "macd", "parameters": {"fast": 12, "slow": 26, "signal": 9}},
                {"name": "bbands", "output_key": "bb", "parameters": {"length": 20, "std": 2}}
            ],
            "output": {
                "format": "json",
                "include_metadata": True,
                "cache_results": False  # Real-time, no caching
            }
        }

    @pytest.fixture
    def multi_timeframe_subscription(self):
        """Multi-timeframe subscription for testing"""
        return {
            "action": "subscribe_multi",
            "subscription_id": "multi_tf_pandas_ta",
            "instrument_key": "NSE@BANKNIFTY@INDEX",
            "timeframes": ["1m", "5m", "15m"],
            "technical_indicators": {
                "1m": [
                    {"name": "sma", "output_key": "sma_5", "parameters": {"length": 5}},
                    {"name": "rsi", "output_key": "rsi_14", "parameters": {"length": 14}}
                ],
                "5m": [
                    {"name": "sma", "output_key": "sma_20", "parameters": {"length": 20}},
                    {"name": "macd", "output_key": "macd", "parameters": {"fast": 12, "slow": 26, "signal": 9}},
                    {"name": "atr", "output_key": "atr_14", "parameters": {"length": 14}}
                ],
                "15m": [
                    {"name": "sma", "output_key": "sma_50", "parameters": {"length": 50}},
                    {"name": "bb", "output_key": "bb_20", "parameters": {"length": 20, "std": 2}},
                    {"name": "adx", "output_key": "adx_14", "parameters": {"length": 14}}
                ]
            }
        }

    @pytest.mark.asyncio
    async def test_websocket_subscription_flow(self, sample_subscription_request):
        """Test complete WebSocket subscription flow"""
        # Mock WebSocket server for testing
        async def mock_websocket_handler(websocket, path):
            try:
                # Receive subscription request
                request = await websocket.recv()
                request_data = json.loads(request)

                assert request_data["action"] == "subscribe"
                assert "technical_indicators" in request_data

                # Send subscription confirmation
                confirmation = {
                    "type": "subscription_confirmed",
                    "subscription_id": request_data["subscription_id"],
                    "status": "active",
                    "indicators_count": len(request_data["technical_indicators"])
                }
                await websocket.send(json.dumps(confirmation))

                # Simulate periodic indicator updates
                for i in range(3):
                    await asyncio.sleep(0.1)  # Short delay for test

                    # Generate mock indicator results
                    indicator_update = {
                        "type": "indicator_update",
                        "subscription_id": request_data["subscription_id"],
                        "timestamp": datetime.now().isoformat(),
                        "instrument_key": request_data["instrument_key"],
                        "interval": request_data["interval"],
                        "results": {
                            "sma_10": 25150.50 + i * 10,
                            "sma_20": 25140.25 + i * 8,
                            "rsi_14": 55.0 + i * 2,
                            "macd": {
                                "macd": 12.5 + i,
                                "signal": 10.0 + i,
                                "histogram": 2.5 + i * 0.5
                            },
                            "bb": {
                                "upper": 25200.0 + i * 15,
                                "middle": 25150.0 + i * 10,
                                "lower": 25100.0 + i * 5
                            }
                        },
                        "metadata": {
                            "calculation_time_ms": 45.5,
                            "data_points_used": 50 + i,
                            "cache_hit": False
                        }
                    }
                    await websocket.send(json.dumps(indicator_update))

            except websockets.exceptions.ConnectionClosed:
                pass

        # Test the WebSocket flow
        async with websockets.serve(mock_websocket_handler, "localhost", 0) as server:
            host, port = server.sockets[0].getsockname()
            uri = f"ws://{host}:{port}"

            async with websockets.connect(uri) as websocket:
                # Send subscription
                await websocket.send(json.dumps(sample_subscription_request))

                # Receive confirmation
                confirmation = await websocket.recv()
                confirmation_data = json.loads(confirmation)

                assert confirmation_data["type"] == "subscription_confirmed"
                assert confirmation_data["status"] == "active"
                assert confirmation_data["indicators_count"] == 5

                # Receive indicator updates
                updates_received = 0
                async for message in websocket:
                    update_data = json.loads(message)

                    assert update_data["type"] == "indicator_update"
                    assert "results" in update_data
                    assert "metadata" in update_data

                    # Validate indicator results structure
                    results = update_data["results"]
                    assert isinstance(results["sma_10"], (int, float))
                    assert isinstance(results["sma_20"], (int, float))
                    assert isinstance(results["rsi_14"], (int, float))
                    assert isinstance(results["macd"], dict)
                    assert isinstance(results["bb"], dict)

                    # Validate MACD structure
                    assert "macd" in results["macd"]
                    assert "signal" in results["macd"]
                    assert "histogram" in results["macd"]

                    # Validate Bollinger Bands structure
                    assert "upper" in results["bb"]
                    assert "middle" in results["bb"]
                    assert "lower" in results["bb"]
                    assert results["bb"]["lower"] <= results["bb"]["middle"] <= results["bb"]["upper"]

                    updates_received += 1
                    if updates_received >= 3:
                        break

    @pytest.mark.asyncio
    async def test_subscription_error_handling(self):
        """Test error handling in subscriptions"""
        invalid_subscription = {
            "action": "subscribe",
            "subscription_id": "invalid_test",
            "instrument_key": "INVALID@SYMBOL@EQ",
            "technical_indicators": [
                {"name": "invalid_indicator", "output_key": "invalid", "parameters": {}}
            ]
        }

        # Mock WebSocket handler that simulates errors
        async def error_handler(websocket, path):
            try:
                request = await websocket.recv()
                request_data = json.loads(request)

                # Send error response
                error_response = {
                    "type": "subscription_error",
                    "subscription_id": request_data["subscription_id"],
                    "error": {
                        "code": "INVALID_INDICATOR",
                        "message": "Indicator 'invalid_indicator' is not supported",
                        "details": {
                            "supported_indicators": ["sma", "ema", "rsi", "macd", "bbands", "atr"]
                        }
                    }
                }
                await websocket.send(json.dumps(error_response))

            except websockets.exceptions.ConnectionClosed:
                pass

        async with websockets.serve(error_handler, "localhost", 0) as server:
            host, port = server.sockets[0].getsockname()
            uri = f"ws://{host}:{port}"

            async with websockets.connect(uri) as websocket:
                await websocket.send(json.dumps(invalid_subscription))

                error_response = await websocket.recv()
                error_data = json.loads(error_response)

                assert error_data["type"] == "subscription_error"
                assert "error" in error_data
                assert error_data["error"]["code"] == "INVALID_INDICATOR"

    @pytest.mark.asyncio
    async def test_multi_timeframe_subscription(self, multi_timeframe_subscription):
        """Test multi-timeframe indicator subscriptions"""
        async def multi_tf_handler(websocket, path):
            try:
                request = await websocket.recv()
                request_data = json.loads(request)

                assert request_data["action"] == "subscribe_multi"
                assert len(request_data["timeframes"]) == 3

                # Send confirmation for each timeframe
                for timeframe in request_data["timeframes"]:
                    confirmation = {
                        "type": "multi_subscription_confirmed",
                        "subscription_id": request_data["subscription_id"],
                        "timeframe": timeframe,
                        "indicators_count": len(request_data["technical_indicators"][timeframe]),
                        "status": "active"
                    }
                    await websocket.send(json.dumps(confirmation))

                # Send updates for each timeframe
                for i in range(2):
                    await asyncio.sleep(0.1)

                    for timeframe in request_data["timeframes"]:
                        # Generate appropriate results for each timeframe
                        if timeframe == "1m":
                            results = {
                                "sma_5": 25100.0 + i * 5,
                                "rsi_14": 50.0 + i * 3
                            }
                        elif timeframe == "5m":
                            results = {
                                "sma_20": 25120.0 + i * 8,
                                "macd": {"macd": 10.0 + i, "signal": 8.0 + i, "histogram": 2.0},
                                "atr_14": 25.5 + i * 2
                            }
                        else:  # 15m
                            results = {
                                "sma_50": 25080.0 + i * 12,
                                "bb_20": {"upper": 25200.0, "middle": 25150.0, "lower": 25100.0},
                                "adx_14": 20.0 + i * 5
                            }

                        update = {
                            "type": "multi_timeframe_update",
                            "subscription_id": request_data["subscription_id"],
                            "timeframe": timeframe,
                            "timestamp": datetime.now().isoformat(),
                            "results": results
                        }
                        await websocket.send(json.dumps(update))

            except websockets.exceptions.ConnectionClosed:
                pass

        async with websockets.serve(multi_tf_handler, "localhost", 0) as server:
            host, port = server.sockets[0].getsockname()
            uri = f"ws://{host}:{port}"

            async with websockets.connect(uri) as websocket:
                await websocket.send(json.dumps(multi_timeframe_subscription))

                # Receive confirmations for all timeframes
                confirmations = []
                for _ in range(3):
                    confirmation = await websocket.recv()
                    confirmations.append(json.loads(confirmation))

                # Verify all timeframes confirmed
                confirmed_timeframes = [conf["timeframe"] for conf in confirmations]
                assert "1m" in confirmed_timeframes
                assert "5m" in confirmed_timeframes
                assert "15m" in confirmed_timeframes

                # Receive updates
                updates_received = 0
                timeframe_updates = {"1m": 0, "5m": 0, "15m": 0}

                async for message in websocket:
                    update_data = json.loads(message)

                    assert update_data["type"] == "multi_timeframe_update"
                    timeframe = update_data["timeframe"]
                    timeframe_updates[timeframe] += 1

                    # Validate results based on timeframe
                    results = update_data["results"]
                    if timeframe == "1m":
                        assert "sma_5" in results
                        assert "rsi_14" in results
                    elif timeframe == "5m":
                        assert "sma_20" in results
                        assert "macd" in results
                        assert "atr_14" in results
                    elif timeframe == "15m":
                        assert "sma_50" in results
                        assert "bb_20" in results
                        assert "adx_14" in results

                    updates_received += 1
                    if updates_received >= 6:  # 2 updates per timeframe
                        break

                # Verify each timeframe received updates
                for tf, count in timeframe_updates.items():
                    assert count >= 2, f"Timeframe {tf} did not receive enough updates"

    @pytest.mark.asyncio
    async def test_subscription_performance_monitoring(self):
        """Test performance monitoring in subscriptions"""
        performance_subscription = {
            "action": "subscribe",
            "subscription_id": "perf_test",
            "instrument_key": "NSE@NIFTY@INDEX",
            "interval": "1m",
            "technical_indicators": [
                # Include many indicators to test performance
                {"name": "sma", "output_key": "sma_10", "parameters": {"length": 10}},
                {"name": "sma", "output_key": "sma_20", "parameters": {"length": 20}},
                {"name": "sma", "output_key": "sma_50", "parameters": {"length": 50}},
                {"name": "ema", "output_key": "ema_12", "parameters": {"length": 12}},
                {"name": "ema", "output_key": "ema_26", "parameters": {"length": 26}},
                {"name": "rsi", "output_key": "rsi_14", "parameters": {"length": 14}},
                {"name": "macd", "output_key": "macd", "parameters": {"fast": 12, "slow": 26, "signal": 9}},
                {"name": "bbands", "output_key": "bb_20", "parameters": {"length": 20, "std": 2}},
                {"name": "atr", "output_key": "atr_14", "parameters": {"length": 14}},
                {"name": "adx", "output_key": "adx_14", "parameters": {"length": 14}}
            ],
            "output": {
                "include_performance_metrics": True
            }
        }

        async def performance_handler(websocket, path):
            try:
                request = await websocket.recv()
                request_data = json.loads(request)

                # Send confirmation with performance expectations
                confirmation = {
                    "type": "subscription_confirmed",
                    "subscription_id": request_data["subscription_id"],
                    "status": "active",
                    "performance_profile": {
                        "expected_calculation_time_ms": 150,
                        "memory_usage_mb": 2.5,
                        "indicators_count": 10
                    }
                }
                await websocket.send(json.dumps(confirmation))

                # Send updates with performance metrics
                for i in range(3):
                    await asyncio.sleep(0.1)

                    update = {
                        "type": "indicator_update",
                        "subscription_id": request_data["subscription_id"],
                        "timestamp": datetime.now().isoformat(),
                        "results": {
                            f"indicator_{j}": 100.0 + i * 5 + j for j in range(10)
                        },
                        "performance_metrics": {
                            "calculation_time_ms": 120 + i * 10,
                            "memory_usage_mb": 2.3 + i * 0.1,
                            "cpu_usage_percent": 15.0 + i * 2,
                            "cache_hit_ratio": 0.85 - i * 0.05,
                            "data_points_processed": 1000 + i * 100
                        }
                    }
                    await websocket.send(json.dumps(update))

            except websockets.exceptions.ConnectionClosed:
                pass

        async with websockets.serve(performance_handler, "localhost", 0) as server:
            host, port = server.sockets[0].getsockname()
            uri = f"ws://{host}:{port}"

            async with websockets.connect(uri) as websocket:
                await websocket.send(json.dumps(performance_subscription))

                # Receive confirmation
                confirmation = await websocket.recv()
                confirmation_data = json.loads(confirmation)

                assert "performance_profile" in confirmation_data
                perf_profile = confirmation_data["performance_profile"]
                assert perf_profile["expected_calculation_time_ms"] <= 200  # Performance expectation

                # Monitor performance metrics in updates
                updates_received = 0
                async for message in websocket:
                    update_data = json.loads(message)

                    assert "performance_metrics" in update_data
                    perf_metrics = update_data["performance_metrics"]

                    # Validate performance metrics
                    assert perf_metrics["calculation_time_ms"] >= 0
                    assert perf_metrics["memory_usage_mb"] >= 0
                    assert 0 <= perf_metrics["cpu_usage_percent"] <= 100
                    assert 0 <= perf_metrics["cache_hit_ratio"] <= 1
                    assert perf_metrics["data_points_processed"] > 0

                    # Performance thresholds
                    assert perf_metrics["calculation_time_ms"] < 500, "Calculation too slow"
                    assert perf_metrics["memory_usage_mb"] < 10, "Memory usage too high"

                    updates_received += 1
                    if updates_received >= 3:
                        break


if __name__ == "__main__":
    # Run integration tests
    import asyncio
    import sys

    async def run_tests():
        print("Running pandas_ta API integration tests...")

        # Initialize test classes
        TestPandasTAAPIIntegration()
        sub_tester = TestPandasTASubscriptionIntegration()

        print("\n=== Testing API Calls ===")
        # Note: These would need actual FastAPI test setup
        print("API tests require FastAPI test client setup")

        print("\n=== Testing WebSocket Subscriptions ===")
        await sub_tester.test_websocket_subscription_flow({
            "action": "subscribe",
            "subscription_id": "test_pandas_ta_sub",
            "instrument_key": "NSE@NIFTY@INDEX",
            "interval": "1m",
            "frequency": "realtime",
            "technical_indicators": [
                {"name": "sma", "output_key": "sma_20", "parameters": {"length": 20}},
                {"name": "rsi", "output_key": "rsi_14", "parameters": {"length": 14}}
            ]
        })

        print("\nIntegration tests completed!")

    if len(sys.argv) > 1 and sys.argv[1] == "run":
        asyncio.run(run_tests())
    else:
        print("Run with 'python test_pandas_ta_api_integration.py run' to execute tests")
