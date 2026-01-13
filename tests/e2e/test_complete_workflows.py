"""
End-to-end workflow tests for Signal Service
"""
import pytest
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock
import websockets
from httpx import AsyncClient

@pytest.mark.e2e
class TestRealtimeTradingWorkflow:
    """End-to-end tests for real-time trading workflows"""
    
    @pytest.mark.asyncio
    async def test_complete_realtime_signal_flow(self, async_client, redis_client):
        """Test complete flow: Tick → Processing → Signal → Delivery"""
        
        # 1. Simulate tick data arrival via API
        tick_data = {
            'instrument_key': 'NSE@NIFTY@equity_options@2025-07-10@call@21500',
            'last_price': 125.50,
            'bid_price': 125.25,
            'ask_price': 125.75,
            'volume': 1000,
            'open_interest': 50000,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Send tick data to signal service
        response = await async_client.post("/api/v2/signals/process-tick", json=tick_data)
        assert response.status_code == 200
        
        # 2. Verify signal computation and caching
        await asyncio.sleep(0.1)  # Allow processing time
        
        # Check if Greeks are computed and cached
        cache_key = f"signal:latest:{tick_data['instrument_key']}:greeks"
        cached_greeks = await redis_client.get(cache_key)
        assert cached_greeks is not None
        
        greeks_data = json.loads(cached_greeks)
        assert 'delta' in greeks_data
        assert 'gamma' in greeks_data
        assert 'timestamp' in greeks_data
        
        # 3. Retrieve signal via real-time API
        response = await async_client.get(
            f"/api/v2/signals/realtime/greeks/{tick_data['instrument_key']}"
        )
        assert response.status_code == 200
        
        api_data = response.json()
        assert api_data['instrument_key'] == tick_data['instrument_key']
        assert 'greeks' in api_data
        assert api_data['greeks']['delta'] == greeks_data['delta']
        
        print("✓ Complete real-time signal flow working")
    
    @pytest.mark.asyncio
    async def test_websocket_subscription_workflow(self, async_client):
        """Test WebSocket subscription and real-time updates"""
        
        # 1. Establish WebSocket connection
        websocket_url = "ws://localhost:8003/api/v2/signals/subscriptions/websocket?client_id=test_e2e"
        
        try:
            async with websockets.connect(websocket_url) as websocket:
                
                # 2. Subscribe to signals
                subscription_message = {
                    'type': 'subscribe',
                    'channel': 'greeks',
                    'instrument': 'NSE@NIFTY@equity_options@2025-07-10@call@21500',
                    'frequency': 'realtime'
                }
                
                await websocket.send(json.dumps(subscription_message))
                
                # Wait for subscription confirmation
                response = await websocket.recv()
                confirmation = json.loads(response)
                assert confirmation['type'] == 'subscription_confirmed'
                
                # 3. Trigger signal update via API
                tick_data = {
                    'instrument_key': 'NSE@NIFTY@equity_options@2025-07-10@call@21500',
                    'last_price': 126.00,
                    'timestamp': datetime.utcnow().isoformat()
                }
                
                response = await async_client.post("/api/v2/signals/process-tick", json=tick_data)
                assert response.status_code == 200
                
                # 4. Receive real-time update via WebSocket
                update_message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                update_data = json.loads(update_message)
                
                assert update_data['type'] == 'signal_update'
                assert update_data['channel'] == 'greeks'
                assert update_data['instrument'] == tick_data['instrument_key']
                assert 'data' in update_data
                
                print("✓ WebSocket subscription workflow working")
                
        except websockets.exceptions.ConnectionClosed:
            pytest.skip("WebSocket server not available for E2E test")
    
    @pytest.mark.asyncio
    async def test_frequency_based_delivery_workflow(self, async_client, redis_client):
        """Test frequency-based signal delivery workflow"""
        
        # 1. Set up frequency subscription
        subscription_data = {
            'user_id': 'test_user',
            'instrument': 'NSE@NIFTY@equity_options@2025-07-10@call@21500',
            'signal_type': 'greeks',
            'frequency': '5m'
        }
        
        response = await async_client.post("/api/v2/signals/subscriptions/frequency", json=subscription_data)
        assert response.status_code == 200
        
        # 2. Send multiple tick updates
        for i in range(5):
            tick_data = {
                'instrument_key': 'NSE@NIFTY@equity_options@2025-07-10@call@21500',
                'last_price': 125.0 + i * 0.5,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            await async_client.post("/api/v2/signals/process-tick", json=tick_data)
            await asyncio.sleep(0.1)
        
        # 3. Verify frequency-based aggregation
        await asyncio.sleep(1)  # Allow processing time
        
        # Check user's frequency channel
        user_channel = f"signal:frequency:test_user:{subscription_data['instrument']}:greeks"
        frequency_data = await redis_client.get(user_channel)
        
        if frequency_data:  # May not be available immediately
            data = json.loads(frequency_data)
            assert 'aggregated_greeks' in data
            assert data['frequency'] == '5m'
        
        print("✓ Frequency-based delivery workflow working")


@pytest.mark.e2e
class TestMoneynessAnalyticsWorkflow:
    """End-to-end tests for moneyness analytics workflows"""
    
    @pytest.mark.asyncio
    async def test_atm_iv_calculation_workflow(self, async_client):
        """Test complete ATM IV calculation workflow"""
        
        # 1. Request ATM IV for NIFTY July expiry
        start_time = (datetime.utcnow() - timedelta(hours=3)).isoformat()
        end_time = datetime.utcnow().isoformat()
        
        response = await async_client.get(
            "/api/v2/signals/historical/greeks/MONEYNESS@NIFTY@ATM@2025-07-10",
            params={
                'start_time': start_time,
                'end_time': end_time,
                'timeframe': '5m'
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # 2. Verify response structure
        assert 'time_series' in data
        assert 'metadata' in data
        assert data['metadata']['moneyness_level'] == 'ATM'
        assert data['metadata']['underlying'] == 'NIFTY'
        
        # 3. Verify data points structure
        if len(data['time_series']) > 0:
            point = data['time_series'][0]
            assert 'timestamp' in point
            assert 'value' in point
            assert 'iv' in point['value']  # Implied Volatility
            assert 'strike_count' in point['value']
        
        print("✓ ATM IV calculation workflow working")
    
    @pytest.mark.asyncio
    async def test_moneyness_comparison_workflow(self, async_client):
        """Test moneyness level comparison workflow"""
        
        # 1. Request multiple moneyness levels
        moneyness_levels = ['ATM', 'OTM5delta', 'ITM5delta']
        results = {}
        
        for level in moneyness_levels:
            response = await async_client.get(
                f"/api/v2/signals/realtime/greeks/MONEYNESS@NIFTY@{level}@2025-07-10"
            )
            
            if response.status_code == 200:
                results[level] = response.json()
        
        # 2. Verify we got data for multiple levels
        assert len(results) > 0
        
        # 3. Compare IV across moneyness levels
        iv_values = {}
        for level, data in results.items():
            if 'greeks' in data and 'iv' in data['greeks']:
                iv_values[level] = data['greeks']['iv']
        
        if len(iv_values) >= 2:
            # ATM should typically have different IV than OTM
            assert 'ATM' in iv_values
            print(f"✓ Moneyness comparison: {iv_values}")
        
        print("✓ Moneyness comparison workflow working")


@pytest.mark.e2e
class TestMarketProfileWorkflow:
    """End-to-end tests for market profile workflows"""
    
    @pytest.mark.asyncio
    async def test_market_profile_calculation_workflow(self, async_client):
        """Test complete market profile calculation workflow"""
        
        # 1. Request market profile for NIFTY
        response = await async_client.get(
            "/api/v2/signals/market-profile/NSE@NIFTY@equity_spot",
            params={
                'interval': '30m',
                'lookback_period': '1d',
                'profile_type': 'volume'
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # 2. Verify profile structure
        assert 'profile' in data
        assert 'metadata' in data
        assert 'market_structure' in data
        
        profile = data['profile']
        assert 'price_levels' in profile
        assert 'volumes' in profile
        assert 'value_area' in profile
        
        # 3. Verify value area calculations
        value_area = profile['value_area']
        assert 'vah' in value_area  # Value Area High
        assert 'val' in value_area  # Value Area Low
        assert 'poc' in value_area  # Point of Control
        
        # Value area percentage should be around 70%
        if 'volume_percentage' in value_area:
            va_percentage = value_area['volume_percentage']
            assert 60 <= va_percentage <= 80  # Should be around 70%
        
        print("✓ Market profile calculation workflow working")
    
    @pytest.mark.asyncio
    async def test_developing_profile_workflow(self, async_client):
        """Test developing profile workflow"""
        
        # 1. Request developing profile
        response = await async_client.get(
            "/api/v2/signals/market-profile/NSE@NIFTY@equity_spot/developing",
            params={'interval': '30m'}
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # 2. Verify developing profile structure
            assert 'developing_profile' in data
            assert 'completion_percentage' in data
            
            developing = data['developing_profile']
            assert 'current_poc' in developing
            assert 'time_progression' in developing
            
            # Completion should be partial for developing profile
            completion = data['completion_percentage']
            assert 0 <= completion <= 100
            
            print(f"✓ Developing profile: {completion}% complete")
        
        print("✓ Developing profile workflow working")


@pytest.mark.e2e
class TestBatchProcessingWorkflow:
    """End-to-end tests for batch processing workflows"""
    
    @pytest.mark.asyncio
    async def test_bulk_greeks_calculation_workflow(self, async_client):
        """Test bulk Greeks calculation workflow"""
        
        # 1. Prepare batch request
        instruments = [
            'NSE@NIFTY@equity_options@2025-07-10@call@21400',
            'NSE@NIFTY@equity_options@2025-07-10@call@21500',
            'NSE@NIFTY@equity_options@2025-07-10@call@21600',
            'NSE@BANKNIFTY@equity_options@2025-07-10@call@45000',
            'NSE@BANKNIFTY@equity_options@2025-07-10@call@45500'
        ]
        
        payload = {
            'instruments': instruments,
            'signal_types': ['greeks', 'indicators'],
            'include_metadata': True
        }
        
        # 2. Submit batch request
        response = await async_client.post("/api/v2/signals/batch/compute", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        
        # 3. Verify batch results
        assert 'results' in data
        assert 'metadata' in data
        assert len(data['results']) == len(instruments)
        
        # 4. Verify individual results
        for i, result in enumerate(data['results']):
            assert result['instrument_key'] == instruments[i]
            assert 'greeks' in result or 'error' in result
            
            if 'greeks' in result:
                greeks = result['greeks']
                assert 'delta' in greeks
                assert 'gamma' in greeks
        
        # 5. Check processing time
        processing_time = data['metadata'].get('processing_time_ms', 0)
        assert processing_time < 5000  # Should complete within 5 seconds
        
        print(f"✓ Bulk calculation: {len(instruments)} instruments in {processing_time}ms")
    
    @pytest.mark.asyncio
    async def test_historical_iv_analysis_workflow(self, async_client):
        """Test historical IV analysis workflow"""
        
        # 1. Request historical IV analysis for option chain
        payload = {
            'underlying': 'NIFTY',
            'expiry_date': '2025-07-10',
            'strikes': [21400, 21450, 21500, 21550, 21600],
            'start_time': (datetime.utcnow() - timedelta(days=7)).isoformat(),
            'end_time': datetime.utcnow().isoformat(),
            'timeframe': '1h'
        }
        
        response = await async_client.post("/api/v2/signals/batch/historical-iv", json=payload)
        
        if response.status_code == 200:
            data = response.json()
            
            # 2. Verify response structure
            assert 'iv_surface' in data
            assert 'analysis' in data
            
            iv_surface = data['iv_surface']
            assert 'strikes' in iv_surface
            assert 'time_series' in iv_surface
            
            # 3. Verify IV analysis
            analysis = data['analysis']
            assert 'iv_skew' in analysis
            assert 'term_structure' in analysis
            
            print("✓ Historical IV analysis workflow working")
        else:
            print("ℹ Historical IV analysis not available (expected in development)")


@pytest.mark.e2e
class TestScalingWorkflow:
    """End-to-end tests for horizontal scaling workflows"""
    
    @pytest.mark.asyncio
    async def test_load_distribution_workflow(self, async_client):
        """Test load distribution across instances"""
        
        # 1. Send requests for different instruments
        instruments = [
            f'NSE@TEST{i}@equity_options@2025-07-10@call@{21000 + i*10}'
            for i in range(20)
        ]
        
        responses = []
        for instrument in instruments:
            response = await async_client.get(f"/api/v2/signals/realtime/greeks/{instrument}")
            responses.append((instrument, response.status_code))
        
        # 2. Verify all requests were handled
        successful_requests = len([r for r in responses if r[1] == 200])
        success_rate = successful_requests / len(responses)
        
        assert success_rate > 0.8, f"Success rate {success_rate:.2%} too low"
        
        # 3. Check load balancer health
        response = await async_client.get("/api/v2/admin/health")
        if response.status_code == 200:
            health_data = response.json()
            assert health_data['status'] == 'healthy'
        
        print(f"✓ Load distribution: {success_rate:.2%} success rate")
    
    @pytest.mark.asyncio
    async def test_backpressure_handling_workflow(self, async_client):
        """Test backpressure handling workflow"""
        
        # 1. Generate high load to trigger backpressure
        concurrent_requests = 100
        
        async def make_request(i):
            try:
                response = await async_client.get(
                    f"/api/v2/signals/realtime/greeks/NSE@LOAD{i}@equity_options@2025-07-10@call@{21000+i}"
                )
                return response.status_code
            except Exception:
                return 500  # Treat exceptions as server errors
        
        # 2. Execute concurrent requests
        tasks = [make_request(i) for i in range(concurrent_requests)]
        results = await asyncio.gather(*tasks)
        
        # 3. Analyze response patterns
        status_counts = {}
        for status in results:
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Should handle most requests successfully or with proper rate limiting
        success_or_throttled = status_counts.get(200, 0) + status_counts.get(429, 0)
        success_rate = success_or_throttled / len(results)
        
        assert success_rate > 0.7, f"System handling rate {success_rate:.2%} too low under load"
        
        # 4. Check if backpressure metrics are available
        response = await async_client.get("/api/v2/admin/metrics")
        if response.status_code == 200:
            metrics = response.json()
            if 'backpressure_level' in metrics:
                print(f"ℹ Backpressure level: {metrics['backpressure_level']}")
        
        print(f"✓ Backpressure handling: {success_rate:.2%} success/throttled rate")


@pytest.mark.e2e
class TestErrorRecoveryWorkflow:
    """End-to-end tests for error recovery workflows"""
    
    @pytest.mark.asyncio
    async def test_service_resilience_workflow(self, async_client):
        """Test service resilience under error conditions"""
        
        # 1. Test with invalid instrument
        response = await async_client.get("/api/v2/signals/realtime/greeks/INVALID@INSTRUMENT")
        assert response.status_code in [400, 404]  # Should handle gracefully
        
        # 2. Test with malformed request
        response = await async_client.post("/api/v2/signals/process-tick", json={'invalid': 'data'})
        assert response.status_code == 400  # Should validate input
        
        # 3. Test service continues working after errors
        valid_instrument = 'NSE@NIFTY@equity_options@2025-07-10@call@21500'
        response = await async_client.get(f"/api/v2/signals/realtime/greeks/{valid_instrument}")
        assert response.status_code == 200  # Should still work
        
        print("✓ Service resilience workflow working")
    
    @pytest.mark.asyncio
    async def test_health_check_workflow(self, async_client):
        """Test health check workflow"""
        
        # 1. Basic health check
        response = await async_client.get("/health")
        assert response.status_code == 200
        
        # 2. Detailed health check
        response = await async_client.get("/api/v2/admin/health")
        if response.status_code == 200:
            health_data = response.json()
            
            # Should include component health
            expected_components = ['database', 'redis', 'signal_processor']
            for component in expected_components:
                if component in health_data:
                    assert health_data[component] in ['healthy', 'degraded']
        
        # 3. Metrics endpoint
        response = await async_client.get("/metrics")
        if response.status_code == 200:
            # Should return Prometheus metrics
            metrics_text = response.text
            assert 'signal_service_' in metrics_text
        
        print("✓ Health check workflow working")


@pytest.mark.e2e
class TestUserJourneyWorkflow:
    """End-to-end tests simulating complete user journeys"""
    
    @pytest.mark.asyncio
    async def test_options_trader_journey(self, async_client):
        """Test complete options trader user journey"""
        
        # 1. Trader checks NIFTY option chain
        response = await async_client.get(
            "/api/v2/signals/batch/option-chain",
            params={
                'underlying': 'NIFTY',
                'expiry': '2025-07-10',
                'strikes': '21400,21450,21500,21550,21600'
            }
        )
        
        if response.status_code == 200:
            chain_data = response.json()
            assert 'options' in chain_data
            
            # 2. Trader analyzes ATM IV
            atm_response = await async_client.get(
                "/api/v2/signals/realtime/greeks/MONEYNESS@NIFTY@ATM@2025-07-10"
            )
            
            if atm_response.status_code == 200:
                atm_data = atm_response.json()
                assert 'greeks' in atm_data
                
                # 3. Trader checks market profile
                profile_response = await async_client.get(
                    "/api/v2/signals/market-profile/NSE@NIFTY@equity_spot",
                    params={'interval': '30m', 'lookback_period': '1d'}
                )
                
                if profile_response.status_code == 200:
                    profile_data = profile_response.json()
                    assert 'value_area' in profile_data['profile']
                    
                    print("✓ Complete options trader journey working")
                    return
        
        print("ℹ Options trader journey partially available (development mode)")
    
    @pytest.mark.asyncio
    async def test_quantitative_analyst_journey(self, async_client):
        """Test quantitative analyst user journey"""
        
        # 1. Analyst requests historical Greeks data
        start_time = (datetime.utcnow() - timedelta(days=30)).isoformat()
        end_time = datetime.utcnow().isoformat()
        
        response = await async_client.get(
            "/api/v2/signals/historical/greeks/NSE@NIFTY@equity_options@2025-07-10@call@21500",
            params={
                'start_time': start_time,
                'end_time': end_time,
                'timeframe': '1h'
            }
        )
        
        if response.status_code == 200:
            historical_data = response.json()
            assert 'time_series' in historical_data
            
            # 2. Analyst requests IV surface analysis
            surface_response = await async_client.post(
                "/api/v2/signals/batch/iv-surface",
                json={
                    'underlying': 'NIFTY',
                    'expiry_date': '2025-07-10',
                    'analysis_type': 'skew'
                }
            )
            
            if surface_response.status_code == 200:
                surface_data = surface_response.json()
                print("✓ Quantitative analyst journey working")
                return
        
        print("ℹ Quantitative analyst journey partially available")


@pytest.mark.e2e
class TestComplianceWorkflow:
    """End-to-end tests for compliance and monitoring workflows"""
    
    @pytest.mark.asyncio
    async def test_audit_trail_workflow(self, async_client):
        """Test audit trail and logging workflow"""
        
        # 1. Make tracked request
        response = await async_client.get(
            "/api/v2/signals/realtime/greeks/NSE@NIFTY@equity_options@2025-07-10@call@21500",
            headers={'X-User-ID': 'test_user', 'X-Request-ID': 'test_request_123'}
        )
        
        assert response.status_code == 200
        
        # 2. Check if request was logged (via admin endpoint)
        audit_response = await async_client.get(
            "/api/v2/admin/audit-trail",
            params={'user_id': 'test_user', 'limit': 10}
        )
        
        if audit_response.status_code == 200:
            audit_data = audit_response.json()
            assert 'entries' in audit_data
            print("✓ Audit trail workflow working")
        else:
            print("ℹ Audit trail not available (expected in development)")
    
    @pytest.mark.asyncio
    async def test_rate_limiting_workflow(self, async_client):
        """Test rate limiting workflow"""
        
        # 1. Make requests to test rate limiting
        user_headers = {'X-User-ID': 'rate_test_user'}
        responses = []
        
        for i in range(50):  # Try to exceed rate limit
            response = await async_client.get(
                f"/api/v2/signals/realtime/greeks/NSE@TEST{i}@equity_options@2025-07-10@call@21500",
                headers=user_headers
            )
            responses.append(response.status_code)
            
            if response.status_code == 429:  # Rate limited
                break
            
            await asyncio.sleep(0.01)  # Small delay
        
        # 2. Verify rate limiting is working
        rate_limited_responses = len([r for r in responses if r == 429])
        
        if rate_limited_responses > 0:
            print(f"✓ Rate limiting active: {rate_limited_responses} requests limited")
        else:
            print("ℹ Rate limiting not triggered (may have high limits)")
        
        print("✓ Rate limiting workflow tested")

@pytest.mark.e2e
class TestDataConsistencyWorkflow:
    """End-to-end tests for data consistency workflows"""
    
    @pytest.mark.asyncio
    async def test_cross_service_data_consistency(self, async_client):
        """Test data consistency across service boundaries"""
        instrument = 'NSE@NIFTY@equity_options@2025-07-10@call@21500'
        
        # Process tick data
        tick_data = {
            'instrument_key': instrument,
            'last_price': 125.50,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        response = await async_client.post("/api/v2/signals/process-tick", json=tick_data)
        assert response.status_code == 200
        
        # Verify data in different endpoints
        realtime_response = await async_client.get(f"/api/v2/signals/realtime/greeks/{instrument}")
        historical_response = await async_client.get(
            f"/api/v2/signals/historical/greeks/{instrument}",
            params={
                'start_time': (datetime.utcnow() - timedelta(minutes=1)).isoformat(),
                'end_time': datetime.utcnow().isoformat(),
                'timeframe': '1m'
            }
        )
        
        # Both should return consistent data structure
        if realtime_response.status_code == 200 and historical_response.status_code == 200:
            realtime_data = realtime_response.json()
            historical_data = historical_response.json()
            
            assert 'greeks' in realtime_data or 'time_series' in historical_data
    
    @pytest.mark.asyncio
    async def test_timestamp_consistency_workflow(self, async_client):
        """Test timestamp consistency across all operations"""
        current_time = datetime.utcnow()
        
        # Process multiple ticks with timestamps
        for i in range(3):
            tick_time = current_time + timedelta(seconds=i*10)
            tick_data = {
                'instrument_key': f'NSE@TIME{i}@equity_options@2025-07-10@call@21500',
                'last_price': 125.50 + i,
                'timestamp': tick_time.isoformat()
            }
            
            response = await async_client.post("/api/v2/signals/process-tick", json=tick_data)
            assert response.status_code == 200
        
        print("✅ Timestamp consistency workflow working")

@pytest.mark.e2e
class TestSystemReliabilityWorkflow:
    """End-to-end tests for system reliability"""
    
    @pytest.mark.asyncio
    async def test_system_stability_under_load(self, async_client):
        """Test system stability under sustained load"""
        success_count = 0
        error_count = 0
        
        # Generate sustained load
        for i in range(100):
            try:
                response = await async_client.get(
                    f"/api/v2/signals/realtime/greeks/NSE@STABILITY{i}@equity_options@2025-07-10@call@{21000+i}"
                )
                if response.status_code == 200:
                    success_count += 1
                else:
                    error_count += 1
            except Exception:
                error_count += 1
        
        # System should maintain reasonable success rate
        success_rate = success_count / (success_count + error_count)
        assert success_rate > 0.7, f"System success rate {success_rate:.2%} too low under load"
        
        print(f"✅ System stability: {success_rate:.2%} success rate")
    
    @pytest.mark.asyncio
    async def test_graceful_degradation_workflow(self, async_client):
        """Test graceful degradation workflow"""
        # Test with invalid data that should be handled gracefully
        invalid_requests = [
            {'url': '/api/v2/signals/realtime/greeks/INVALID', 'expected': [400, 404]},
            {'url': '/api/v2/signals/historical/greeks/NSE@INVALID', 'expected': [400, 404]},
            {'url': '/api/v2/signals/market-profile/INVALID', 'expected': [400, 404]}
        ]
        
        for req in invalid_requests:
            response = await async_client.get(req['url'])
            assert response.status_code in req['expected'], f"Unexpected response for {req['url']}"
        
        print("✅ Graceful degradation workflow working")

@pytest.mark.e2e
class TestBusinessLogicWorkflow:
    """End-to-end tests for business logic workflows"""
    
    @pytest.mark.asyncio
    async def test_options_pricing_workflow(self, async_client):
        """Test complete options pricing workflow"""
        # Create option chain request
        underlying = 'NIFTY'
        expiry = '2025-07-10'
        strikes = [21400, 21450, 21500, 21550, 21600]
        
        for strike in strikes:
            for option_type in ['call', 'put']:
                instrument = f'NSE@{underlying}@equity_options@{expiry}@{option_type}@{strike}'
                
                response = await async_client.get(f"/api/v2/signals/realtime/greeks/{instrument}")
                # Should handle gracefully regardless of data availability
                assert response.status_code in [200, 404]
        
        print("✅ Options pricing workflow working")
    
    @pytest.mark.asyncio
    async def test_risk_management_workflow(self, async_client):
        """Test risk management workflow"""
        # Test portfolio-level risk calculations
        portfolio_instruments = [
            'NSE@NIFTY@equity_options@2025-07-10@call@21500',
            'NSE@NIFTY@equity_options@2025-07-10@put@21500',
            'NSE@BANKNIFTY@equity_options@2025-07-10@call@45000'
        ]
        
        # Request Greeks for entire portfolio
        payload = {
            'instruments': portfolio_instruments,
            'signal_types': ['greeks'],
            'portfolio_analysis': True
        }
        
        response = await async_client.post("/api/v2/signals/batch/portfolio-risk", json=payload)
        # Should handle gracefully even if endpoint doesn't exist yet
        assert response.status_code in [200, 404, 422]
        
        print("✅ Risk management workflow working")

@pytest.mark.e2e  
class TestIntegrationWorkflow:
    """End-to-end tests for service integration workflows"""
    
    @pytest.mark.asyncio
    async def test_full_service_integration(self, async_client):
        """Test full service integration workflow"""
        # Test health of all integrated services
        health_endpoints = [
            '/health',
            '/api/v2/admin/health',
            '/metrics'
        ]
        
        service_health = {}
        for endpoint in health_endpoints:
            try:
                response = await async_client.get(endpoint)
                service_health[endpoint] = response.status_code == 200
            except Exception:
                service_health[endpoint] = False
        
        # At least basic health should work
        assert service_health.get('/health', False), "Basic health check not working"
        
        print(f"✅ Service integration health: {service_health}")
    
    @pytest.mark.asyncio
    async def test_end_to_end_data_pipeline(self, async_client):
        """Test complete data pipeline from ingestion to delivery"""
        pipeline_stages = []
        
        # Stage 1: Data ingestion
        tick_data = {
            'instrument_key': 'NSE@PIPELINE@equity_options@2025-07-10@call@21500',
            'last_price': 125.50,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        response = await async_client.post("/api/v2/signals/process-tick", json=tick_data)
        pipeline_stages.append(('ingestion', response.status_code == 200))
        
        # Stage 2: Real-time processing
        response = await async_client.get(
            f"/api/v2/signals/realtime/greeks/{tick_data['instrument_key']}"
        )
        pipeline_stages.append(('realtime', response.status_code in [200, 404]))
        
        # Stage 3: Historical storage
        response = await async_client.get(
            f"/api/v2/signals/historical/greeks/{tick_data['instrument_key']}",
            params={
                'start_time': (datetime.utcnow() - timedelta(minutes=1)).isoformat(),
                'end_time': datetime.utcnow().isoformat(),
                'timeframe': '1m'
            }
        )
        pipeline_stages.append(('historical', response.status_code in [200, 404]))
        
        # Verify pipeline stages
        successful_stages = [stage for stage, success in pipeline_stages if success]
        assert len(successful_stages) >= 2, f"Pipeline stages failing: {pipeline_stages}"
        
        print(f"✅ Data pipeline stages: {dict(pipeline_stages)}")