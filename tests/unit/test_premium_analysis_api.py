# [AGENT-2-PREMIUM-DISCOUNT] API Test Cases for Premium Analysis Endpoints
"""
Test cases for premium analysis API endpoints.
Tests FastAPI routes and integration with PremiumDiscountCalculator.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v2.premium_analysis import router

# Create test app
test_app = FastAPI()
test_app.include_router(router)

@pytest.fixture
def client():
    """Create test client."""
    return TestClient(test_app)

@pytest.fixture
def mock_premium_calculator():
    """Mock premium calculator for testing."""
    calculator = Mock()
    calculator.calculate_premium_analysis = AsyncMock()
    calculator.analyze_option_chain_mispricing = AsyncMock()
    calculator.calculate_arbitrage_opportunities = AsyncMock()
    calculator.get_performance_metrics = Mock(return_value={
        'premium_analyses': 10,
        'total_options_analyzed': 500,
        'avg_analysis_time_ms': 8.5,
        'arbitrage_opportunities_found': 3
    })
    return calculator

@pytest.fixture
def sample_premium_analysis_request():
    """Sample premium analysis request."""
    return {
        "symbol": "NIFTY",
        "underlying_price": 26000.0,
        "options": [
            {
                "strike": 26000.0,
                "expiry_date": "2025-01-30",
                "option_type": "CE",
                "market_price": 47.30,
                "volatility": 0.2
            },
            {
                "strike": 26000.0,
                "expiry_date": "2025-01-30",
                "option_type": "PE",
                "market_price": 45.20,
                "volatility": 0.2
            }
        ],
        "include_greeks": True
    }


class TestPremiumAnalysisAPI:
    """Test suite for premium analysis API endpoints."""

    def test_premium_analysis_expiry_success(
        self,
        client,
        sample_premium_analysis_request,
        mock_premium_calculator
    ):
        """Test successful premium analysis for expiry."""
        # Mock calculator response
        mock_response = {
            'results': [
                {
                    'strike': 26000.0,
                    'expiry_date': '2025-01-30',
                    'option_type': 'CE',
                    'market_price': 47.30,
                    'theoretical_price': 45.20,
                    'premium_amount': 2.10,
                    'premium_percentage': 4.65,
                    'is_overpriced': True,
                    'is_underpriced': False,
                    'mispricing_severity': 'MEDIUM',
                    'arbitrage_signal': False,
                    'greeks': {
                        'delta': 0.55,
                        'gamma': 0.001,
                        'theta': -0.02,
                        'vega': 0.1,
                        'rho': 0.05
                    }
                }
            ],
            'performance': {
                'execution_time_ms': 12.5,
                'options_processed': 2,
                'options_per_second': 160
            }
        }

        with patch('app.api.v2.premium_analysis.premium_calculator', mock_premium_calculator):
            mock_premium_calculator.calculate_premium_analysis.return_value = mock_response

            response = client.post(
                "/api/v2/signals/fo/premium-analysis/expiry",
                json=sample_premium_analysis_request
            )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert data['symbol'] == 'NIFTY'
        assert data['underlying_price'] == 26000.0
        assert 'analysis_timestamp' in data
        assert 'results' in data
        assert 'summary_stats' in data
        assert 'performance' in data

        # Verify results
        results = data['results']
        assert len(results) == 1

        result = results[0]
        assert result['strike'] == 26000.0
        assert result['market_price'] == 47.30
        assert result['theoretical_price'] == 45.20
        assert result['premium_percentage'] == 4.65
        assert result['mispricing_severity'] == 'MEDIUM'
        assert 'greeks' in result

    def test_premium_analysis_expiry_validation_errors(self, client):
        """Test validation errors for premium analysis expiry endpoint."""
        # Test empty options list
        invalid_request = {
            "symbol": "NIFTY",
            "underlying_price": 26000.0,
            "options": [],
            "include_greeks": True
        }

        response = client.post(
            "/api/v2/signals/fo/premium-analysis/expiry",
            json=invalid_request
        )
        assert response.status_code == 422  # Validation error

        # Test invalid underlying price
        invalid_request = {
            "symbol": "NIFTY",
            "underlying_price": -1000.0,  # Negative price
            "options": [
                {
                    "strike": 26000.0,
                    "expiry_date": "2025-01-30",
                    "option_type": "CE",
                    "market_price": 47.30
                }
            ]
        }

        response = client.post(
            "/api/v2/signals/fo/premium-analysis/expiry",
            json=invalid_request
        )
        assert response.status_code == 422

        # Test invalid option type
        invalid_request = {
            "symbol": "NIFTY",
            "underlying_price": 26000.0,
            "options": [
                {
                    "strike": 26000.0,
                    "expiry_date": "2025-01-30",
                    "option_type": "INVALID",  # Invalid option type
                    "market_price": 47.30
                }
            ]
        }

        response = client.post(
            "/api/v2/signals/fo/premium-analysis/expiry",
            json=invalid_request
        )
        assert response.status_code == 422

    def test_premium_analysis_strike_range_success(self, client, mock_premium_calculator):
        """Test successful strike range premium analysis."""

        with patch('app.api.v2.premium_analysis.premium_calculator', mock_premium_calculator):
            mock_premium_calculator.calculate_premium_analysis.return_value = {
                'results': [
                    {
                        'strike': 25900.0,
                        'option_type': 'CE',
                        'market_price': 55.30,
                        'theoretical_price': 52.10,
                        'premium_percentage': 6.14,
                        'mispricing_severity': 'MEDIUM'
                    }
                ],
                'performance': {'execution_time_ms': 15.2}
            }

            response = client.get(
                "/api/v2/signals/fo/premium-analysis/strike-range/NIFTY",
                params={
                    "expiry_date": "2025-01-30",
                    "underlying_price": 26000.0,
                    "strike_min": 25800.0,
                    "strike_max": 26200.0,
                    "strike_step": 100.0,
                    "include_greeks": True
                }
            )

        assert response.status_code == 200
        data = response.json()

        assert data['symbol'] == 'NIFTY'
        assert data['expiry_date'] == '2025-01-30'
        assert data['underlying_price'] == 26000.0
        assert 'strike_range' in data
        assert 'performance' in data

    def test_premium_analysis_strike_range_validation(self, client):
        """Test validation for strike range endpoint."""
        # Test invalid strike range (min >= max)
        response = client.get(
            "/api/v2/signals/fo/premium-analysis/strike-range/NIFTY",
            params={
                "expiry_date": "2025-01-30",
                "underlying_price": 26000.0,
                "strike_min": 26200.0,  # Greater than max
                "strike_max": 25800.0,
                "strike_step": 100.0
            }
        )
        assert response.status_code == 400

        # Test too large strike range (> 100 strikes)
        response = client.get(
            "/api/v2/signals/fo/premium-analysis/strike-range/NIFTY",
            params={
                "expiry_date": "2025-01-30",
                "underlying_price": 26000.0,
                "strike_min": 10000.0,
                "strike_max": 30000.0,  # 200 strikes with step 100
                "strike_step": 100.0
            }
        )
        assert response.status_code == 400

    def test_premium_analysis_term_structure_success(self, client, mock_premium_calculator):
        """Test successful term structure premium analysis."""
        request_data = {
            "symbol": "NIFTY",
            "underlying_price": 26000.0,
            "expiry_dates": ["2025-01-30", "2025-02-27"],
            "strikes": [25900.0, 26000.0, 26100.0]
        }

        {
            'symbol': 'NIFTY',
            'underlying_price': 26000.0,
            'expiry_dates': request_data['expiry_dates'],
            'strikes': request_data['strikes'],
            'term_structure_results': {
                '2025-01-30': {
                    'results': [
                        {
                            'strike': 26000.0,
                            'premium_percentage': 4.5,
                            'mispricing_severity': 'MEDIUM'
                        }
                    ],
                    'summary_stats': {'avg_premium_percentage': 4.5}
                }
            },
            'cross_expiry_analysis': {
                'contango_backwardation': 'contango',
                'arbitrage_calendar_spreads': []
            }
        }

        with patch('app.api.v2.premium_analysis.premium_calculator', mock_premium_calculator):
            mock_premium_calculator.calculate_premium_analysis.return_value = {
                'results': [
                    {
                        'strike': 26000.0,
                        'premium_percentage': 4.5,
                        'mispricing_severity': 'MEDIUM'
                    }
                ],
                'performance': {'execution_time_ms': 8.0}
            }

            response = client.post(
                "/api/v2/signals/fo/premium-analysis/term-structure",
                json=request_data
            )

        assert response.status_code == 200
        data = response.json()

        assert data['symbol'] == 'NIFTY'
        assert data['underlying_price'] == 26000.0
        assert len(data['expiry_dates']) == 2
        assert len(data['strikes']) == 3
        assert 'term_structure_results' in data
        assert 'cross_expiry_analysis' in data

    def test_arbitrage_opportunities_success(self, client):
        """Test arbitrage opportunities endpoint."""
        response = client.get(
            "/api/v2/signals/fo/premium-analysis/arbitrage-opportunities/NIFTY",
            params={
                "min_severity": "MEDIUM",
                "expiry_date": "2025-01-30"
            }
        )

        assert response.status_code == 200
        data = response.json()

        assert data['symbol'] == 'NIFTY'
        assert 'scan_timestamp' in data
        assert data['min_severity_filter'] == 'MEDIUM'
        assert data['expiry_filter'] == '2025-01-30'
        assert 'opportunities_found' in data
        assert 'opportunities' in data
        assert 'summary' in data

        # Verify opportunity structure
        if data['opportunities']:
            opp = data['opportunities'][0]
            assert 'opportunity_id' in opp
            assert 'type' in opp
            assert 'symbol' in opp
            assert 'action' in opp
            assert 'confidence_score' in opp

    def test_arbitrage_opportunities_severity_filtering(self, client):
        """Test severity filtering in arbitrage opportunities."""
        # Test valid severity levels
        valid_severities = ['LOW', 'MEDIUM', 'HIGH', 'EXTREME']

        for severity in valid_severities:
            response = client.get(
                "/api/v2/signals/fo/premium-analysis/arbitrage-opportunities/NIFTY",
                params={"min_severity": severity}
            )
            assert response.status_code == 200

        # Test invalid severity
        response = client.get(
            "/api/v2/signals/fo/premium-analysis/arbitrage-opportunities/NIFTY",
            params={"min_severity": "INVALID"}
        )
        assert response.status_code == 422  # Validation error

    def test_performance_metrics_endpoint(self, client, mock_premium_calculator):
        """Test performance metrics endpoint."""
        mock_vectorized_metrics = {
            'vectorized_calls': 50,
            'avg_vectorized_time_ms': 5.2,
            'total_options_processed': 1000,
            'speedup_ratio': 8.5
        }

        with patch('app.api.v2.premium_analysis.premium_calculator', mock_premium_calculator), patch('app.api.v2.premium_analysis.vectorized_engine') as mock_engine:
            mock_engine.get_performance_metrics.return_value = mock_vectorized_metrics

            response = client.get(
                "/api/v2/signals/fo/premium-analysis/performance-metrics"
            )

        assert response.status_code == 200
        data = response.json()

        assert 'timestamp' in data
        assert 'premium_calculator' in data
        assert 'vectorized_engine' in data
        assert 'integrated_performance' in data

        # Verify integrated performance calculations
        integrated = data['integrated_performance']
        assert 'total_options_processed' in integrated
        assert 'avg_total_time_ms' in integrated
        assert 'theoretical_calculation_ratio' in integrated
        assert 'performance_target_met' in integrated

    def test_error_handling_calculator_failure(self, client, sample_premium_analysis_request):
        """Test error handling when calculator fails."""
        with patch('app.api.v2.premium_analysis.premium_calculator') as mock_calculator:
            mock_calculator.calculate_premium_analysis.side_effect = Exception("Calculator failed")

            response = client.post(
                "/api/v2/signals/fo/premium-analysis/expiry",
                json=sample_premium_analysis_request
            )

        assert response.status_code == 500
        assert "Premium analysis failed" in response.json()['detail']

    def test_summary_stats_calculation(self, client):
        """Test summary statistics calculation in helper function."""
        from app.api.v2.premium_analysis import _calculate_summary_stats

        results = [
            {
                'premium_percentage': 5.0,
                'is_overpriced': True,
                'arbitrage_signal': True,
                'mispricing_severity': 'MEDIUM'
            },
            {
                'premium_percentage': -2.0,
                'is_overpriced': False,
                'arbitrage_signal': False,
                'mispricing_severity': 'LOW'
            },
            {
                'premium_percentage': 10.0,
                'is_overpriced': True,
                'arbitrage_signal': True,
                'mispricing_severity': 'HIGH'
            }
        ]

        stats = _calculate_summary_stats(results)

        assert stats['total_options'] == 3
        assert stats['overpriced_options'] == 2
        assert stats['underpriced_options'] == 1
        assert stats['arbitrage_signals'] == 2
        assert stats['avg_premium_percentage'] == pytest.approx(4.33, rel=1e-2)
        assert stats['max_premium_percentage'] == 10.0
        assert stats['min_premium_percentage'] == -2.0
        assert stats['mispricing_rate'] == pytest.approx(66.67, rel=1e-2)

        # Test severity distribution
        assert 'severity_distribution' in stats
        assert stats['severity_distribution']['MEDIUM'] == 1
        assert stats['severity_distribution']['LOW'] == 1
        assert stats['severity_distribution']['HIGH'] == 1

    def test_mock_market_price_generation(self, client):
        """Test mock market price generation helper function."""
        from app.api.v2.premium_analysis import _mock_market_price

        # Test call option price
        call_price = _mock_market_price(
            underlying_price=26000.0,
            strike=25900.0,
            option_type='CE',
            expiry_date='2025-01-30'
        )
        assert call_price > 0
        assert isinstance(call_price, float)

        # Test put option price
        put_price = _mock_market_price(
            underlying_price=26000.0,
            strike=26100.0,
            option_type='PE',
            expiry_date='2025-01-30'
        )
        assert put_price > 0
        assert isinstance(put_price, float)

        # Call should generally be more expensive for ITM calls
        itm_call = _mock_market_price(26000.0, 25900.0, 'CE', '2025-01-30')
        otm_call = _mock_market_price(26000.0, 26100.0, 'CE', '2025-01-30')
        assert itm_call >= otm_call  # ITM should be >= OTM

    def test_term_structure_pattern_analysis(self, client):
        """Test term structure pattern analysis helper function."""
        from app.api.v2.premium_analysis import _analyze_term_structure_patterns

        term_results = {
            '2025-01-30': {  # Near month
                'results': [
                    {'premium_percentage': 8.0},
                    {'premium_percentage': 6.0}
                ]
            },
            '2025-02-27': {  # Far month
                'results': [
                    {'premium_percentage': 4.0},
                    {'premium_percentage': 5.0}
                ]
            }
        }

        patterns = _analyze_term_structure_patterns(term_results, [26000.0, 26100.0])

        assert 'contango_backwardation' in patterns
        assert 'volatility_skew_evolution' in patterns
        assert 'arbitrage_calendar_spreads' in patterns
        assert 'time_decay_patterns' in patterns

        # Should detect backwardation (near month > far month premium)
        assert patterns['contango_backwardation'] == 'backwardation'


class TestPremiumAnalysisIntegrationAPI:
    """Integration tests for premium analysis API with real components."""

    def test_api_with_real_calculator(self, client):
        """Test API with real calculator (mocked vectorized engine)."""
        from app.services.premium_discount_calculator import PremiumDiscountCalculator
        from app.services.vectorized_pyvollib_engine import VectorizedPyvolibGreeksEngine

        # Mock only the vectorized engine, use real calculator
        mock_engine = Mock(spec=VectorizedPyvolibGreeksEngine)
        mock_engine.calculate_option_chain_greeks_vectorized = AsyncMock(
            return_value={
                'results': [{'delta': 0.5, 'gamma': 0.001}],
                'performance': {'execution_time_ms': 5.0},
                'method_used': 'vectorized'
            }
        )

        real_calculator = PremiumDiscountCalculator(mock_engine)

        request_data = {
            "symbol": "NIFTY",
            "underlying_price": 26000.0,
            "options": [
                {
                    "strike": 26000.0,
                    "expiry_date": "2025-01-30",
                    "option_type": "CE",
                    "market_price": 50.0,
                    "volatility": 0.2
                }
            ],
            "include_greeks": True
        }

        with patch('app.api.v2.premium_analysis.premium_calculator', real_calculator):
            response = client.post(
                "/api/v2/signals/fo/premium-analysis/expiry",
                json=request_data
            )

        assert response.status_code == 200
        data = response.json()

        # Verify real calculation results
        assert len(data['results']) == 1
        result = data['results'][0]
        assert 'premium_amount' in result
        assert 'premium_percentage' in result
        assert 'theoretical_price' in result
        assert 'mispricing_severity' in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
