# [AGENT-2-PREMIUM-DISCOUNT] Test Cases for Premium/Discount Calculator
"""
Test cases for PremiumDiscountCalculator and premium analysis functionality.
Tests integration with Agent 1's vectorized pyvollib engine.
"""

import asyncio
from datetime import date, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.errors import GreeksCalculationError
from app.services.premium_discount_calculator import MispricingSeverity, PremiumDiscountCalculator
from app.services.vectorized_pyvollib_engine import VectorizedPyvolibGreeksEngine


class TestPremiumDiscountCalculator:
    """Test suite for PremiumDiscountCalculator."""

    @pytest.fixture
    def mock_vectorized_engine(self):
        """Create mock vectorized engine for testing."""
        engine = Mock(spec=VectorizedPyvolibGreeksEngine)
        return engine

    @pytest.fixture
    def calculator(self, mock_vectorized_engine):
        """Create calculator instance with mock engine."""
        return PremiumDiscountCalculator(mock_vectorized_engine)

    @pytest.fixture
    def sample_option_chain_data(self):
        """Sample option chain data for testing."""
        return [
            {
                'strike': 26000.0,
                'expiry_date': '2025-01-30',
                'option_type': 'CE',
                'volatility': 0.2,
                'underlying_price': 26000.0
            },
            {
                'strike': 26000.0,
                'expiry_date': '2025-01-30',
                'option_type': 'PE',
                'volatility': 0.2,
                'underlying_price': 26000.0
            },
            {
                'strike': 26100.0,
                'expiry_date': '2025-01-30',
                'option_type': 'CE',
                'volatility': 0.18,
                'underlying_price': 26000.0
            }
        ]

    @pytest.fixture
    def sample_market_prices(self):
        """Sample market prices corresponding to option chain."""
        return [47.30, 45.20, 25.80]

    def test_calculator_initialization(self, mock_vectorized_engine):
        """Test calculator initializes correctly."""
        calculator = PremiumDiscountCalculator(mock_vectorized_engine)

        assert calculator.vectorized_engine == mock_vectorized_engine
        assert isinstance(calculator.severity_thresholds, dict)
        assert MispricingSeverity.LOW in calculator.severity_thresholds
        assert calculator.performance_metrics['premium_analyses'] == 0

    def test_mispricing_severity_classification(self, calculator):
        """Test mispricing severity classification logic."""
        # Test severity thresholds
        assert calculator.calculate_mispricing_severity(1.0) == MispricingSeverity.LOW
        assert calculator.calculate_mispricing_severity(5.0) == MispricingSeverity.MEDIUM
        assert calculator.calculate_mispricing_severity(10.0) == MispricingSeverity.HIGH
        assert calculator.calculate_mispricing_severity(20.0) == MispricingSeverity.EXTREME

        # Test boundary conditions
        assert calculator.calculate_mispricing_severity(3.0) == MispricingSeverity.MEDIUM
        assert calculator.calculate_mispricing_severity(2.99) == MispricingSeverity.LOW
        assert calculator.calculate_mispricing_severity(15.0) == MispricingSeverity.EXTREME
        assert calculator.calculate_mispricing_severity(14.99) == MispricingSeverity.HIGH

    @pytest.mark.asyncio
    async def test_calculate_premium_analysis_success(
        self,
        calculator,
        sample_option_chain_data,
        sample_market_prices
    ):
        """Test successful premium analysis calculation."""
        # Mock vectorized engine response
        mock_greeks_result = {
            'results': [
                {'delta': 0.55, 'gamma': 0.001, 'theta': -0.02, 'vega': 0.1, 'rho': 0.05},
                {'delta': -0.45, 'gamma': 0.001, 'theta': -0.02, 'vega': 0.1, 'rho': -0.05},
                {'delta': 0.35, 'gamma': 0.002, 'theta': -0.015, 'vega': 0.08, 'rho': 0.04}
            ],
            'performance': {'execution_time_ms': 5.0},
            'method_used': 'vectorized'
        }

        calculator.vectorized_engine.calculate_option_chain_greeks_vectorized = AsyncMock(
            return_value=mock_greeks_result
        )

        # Mock theoretical price calculation
        with patch.object(calculator, '_calculate_theoretical_prices') as mock_theoretical:
            mock_theoretical.return_value = [45.20, 43.10, 24.50]  # Theoretical prices

            result = await calculator.calculate_premium_analysis(
                market_prices=sample_market_prices,
                option_chain_data=sample_option_chain_data,
                underlying_price=26000.0,
                include_greeks=True
            )

        # Verify result structure
        assert 'results' in result
        assert 'performance' in result
        assert 'method_used' in result

        # Verify premium calculations
        results = result['results']
        assert len(results) == 3

        # Check first option premium analysis
        first_result = results[0]
        assert first_result['strike'] == 26000.0
        assert first_result['market_price'] == 47.30
        assert first_result['theoretical_price'] == 45.20
        assert abs(first_result['premium_amount'] - 2.10) < 0.01
        assert abs(first_result['premium_percentage'] - 4.65) < 0.1
        assert first_result['is_overpriced']
        assert first_result['mispricing_severity'] == MispricingSeverity.MEDIUM.value

        # Verify Greeks integration
        assert 'greeks' in first_result
        assert first_result['greeks']['delta'] == 0.55

        # Verify performance metrics updated
        assert calculator.performance_metrics['premium_analyses'] == 1
        assert calculator.performance_metrics['total_options_analyzed'] == 3

    @pytest.mark.asyncio
    async def test_calculate_premium_analysis_without_greeks(
        self,
        calculator,
        sample_option_chain_data,
        sample_market_prices
    ):
        """Test premium analysis without Greeks calculations."""
        # Mock vectorized engine response (empty since no Greeks requested)
        mock_greeks_result = {
            'results': [{}] * 3,
            'performance': {'execution_time_ms': 3.0},
            'method_used': 'vectorized'
        }

        calculator.vectorized_engine.calculate_option_chain_greeks_vectorized = AsyncMock(
            return_value=mock_greeks_result
        )

        with patch.object(calculator, '_calculate_theoretical_prices') as mock_theoretical:
            mock_theoretical.return_value = [45.20, 43.10, 24.50]

            result = await calculator.calculate_premium_analysis(
                market_prices=sample_market_prices,
                option_chain_data=sample_option_chain_data,
                underlying_price=26000.0,
                include_greeks=False
            )

        # Verify no Greeks in results
        for option_result in result['results']:
            assert 'greeks' not in option_result or option_result.get('greeks') is None

    @pytest.mark.asyncio
    async def test_analyze_option_chain_mispricing(self, calculator):
        """Test option chain mispricing analysis."""
        option_chain_data = [
            {
                'strike': 26000.0,
                'expiry_date': '2025-01-30',
                'option_type': 'CE',
                'market_price': 50.0,
                'underlying_price': 26000.0,
                'volatility': 0.2
            },
            {
                'strike': 26000.0,
                'expiry_date': '2025-02-27',
                'option_type': 'CE',
                'market_price': 60.0,
                'underlying_price': 26000.0,
                'volatility': 0.18
            }
        ]

        # Mock premium analysis for different expiries
        with patch.object(calculator, 'calculate_premium_analysis') as mock_analysis:
            mock_analysis.side_effect = [
                {
                    'results': [
                        {
                            'strike': 26000.0,
                            'premium_percentage': 8.5,
                            'arbitrage_signal': True,
                            'mispricing_severity': 'HIGH'
                        }
                    ]
                },
                {
                    'results': [
                        {
                            'strike': 26000.0,
                            'premium_percentage': 2.1,
                            'arbitrage_signal': False,
                            'mispricing_severity': 'LOW'
                        }
                    ]
                }
            ]

            with patch.object(calculator, '_detect_arbitrage_opportunities') as mock_arb:
                mock_arb.return_value = [
                    {
                        'type': 'mispricing_arbitrage',
                        'strike': 26000.0,
                        'severity': 'HIGH'
                    }
                ]

                result = await calculator.analyze_option_chain_mispricing(option_chain_data)

        # Verify result structure
        assert 'expiry_analysis' in result
        assert 'summary' in result
        assert result['summary']['total_expiries_analyzed'] == 2
        assert result['summary']['total_arbitrage_opportunities'] == 1

    @pytest.mark.asyncio
    async def test_calculate_arbitrage_opportunities(self, calculator):
        """Test arbitrage opportunity calculation."""
        chain_data = [
            {
                'strike': 26000.0,
                'option_type': 'CE',
                'premium_percentage': 12.0,
                'arbitrage_signal': True,
                'mispricing_severity': 'HIGH'
            },
            {
                'strike': 26000.0,
                'option_type': 'PE',
                'premium_percentage': 15.5,
                'arbitrage_signal': True,
                'mispricing_severity': 'EXTREME'
            }
        ]

        opportunities = await calculator.calculate_arbitrage_opportunities(chain_data)

        # Should detect mispricing arbitrage opportunities
        assert len(opportunities) >= 1

        # Verify arbitrage opportunity structure
        if opportunities:
            opp = opportunities[0]
            assert 'type' in opp
            assert 'strike' in opp
            assert 'severity' in opp

    @pytest.mark.asyncio
    async def test_error_handling_vectorized_engine_failure(
        self,
        calculator,
        sample_option_chain_data,
        sample_market_prices
    ):
        """Test error handling when vectorized engine fails."""
        # Mock engine failure
        calculator.vectorized_engine.calculate_option_chain_greeks_vectorized = AsyncMock(
            side_effect=Exception("Vectorized calculation failed")
        )

        with pytest.raises(GreeksCalculationError, match="Premium analysis failed"):
            await calculator.calculate_premium_analysis(
                market_prices=sample_market_prices,
                option_chain_data=sample_option_chain_data,
                underlying_price=26000.0
            )

    @pytest.mark.asyncio
    async def test_empty_option_chain(self, calculator):
        """Test handling of empty option chain."""
        result = await calculator.calculate_premium_analysis(
            market_prices=[],
            option_chain_data=[],
            underlying_price=26000.0
        )

        assert result['results'] == []
        assert result['method_used'] == 'none'

    @pytest.mark.asyncio
    async def test_mismatched_prices_and_options(self, calculator, sample_option_chain_data):
        """Test error handling for mismatched market prices and option data."""
        with pytest.raises(ValueError, match="Market prices and option data lengths must match"):
            await calculator.calculate_premium_analysis(
                market_prices=[47.30, 45.20],  # Only 2 prices
                option_chain_data=sample_option_chain_data,  # 3 options
                underlying_price=26000.0
            )

    def test_performance_metrics(self, calculator):
        """Test performance metrics tracking."""
        # Initial state
        metrics = calculator.get_performance_metrics()
        assert metrics['premium_analyses'] == 0
        assert metrics['total_options_analyzed'] == 0

        # Simulate metric updates
        calculator.performance_metrics['premium_analyses'] = 5
        calculator.performance_metrics['total_options_analyzed'] = 100
        calculator.performance_metrics['arbitrage_opportunities_found'] = 3

        updated_metrics = calculator.get_performance_metrics()
        assert updated_metrics['premium_analyses'] == 5
        assert updated_metrics['total_options_analyzed'] == 100
        assert updated_metrics['arbitrage_opportunities_found'] == 3

        # Test reset
        calculator.reset_performance_metrics()
        reset_metrics = calculator.get_performance_metrics()
        assert reset_metrics['premium_analyses'] == 0
        assert reset_metrics['total_options_analyzed'] == 0

    @pytest.mark.asyncio
    async def test_time_to_expiry_calculation(self, calculator):
        """Test time to expiry calculation logic."""
        # Test string date format
        time_to_expiry = calculator._calculate_time_to_expiry('2025-01-30')
        assert time_to_expiry > 0

        # Test date object
        expiry_date = date(2025, 1, 30)
        time_to_expiry = calculator._calculate_time_to_expiry(expiry_date)
        assert time_to_expiry > 0

        # Test datetime object
        expiry_datetime = datetime(2025, 1, 30, 15, 30)
        time_to_expiry = calculator._calculate_time_to_expiry(expiry_datetime)
        assert time_to_expiry > 0

        # Test minimum time constraint (should be at least 1 day)
        min_time = 1/365.25
        assert time_to_expiry >= min_time

    @pytest.mark.asyncio
    async def test_theoretical_price_calculation(self, calculator, sample_option_chain_data):
        """Test theoretical price calculation using Black-Scholes-Merton."""
        with patch('app.services.premium_discount_calculator.black_scholes_merton') as mock_bsm:
            mock_bsm.side_effect = [45.20, 43.10, 24.50]  # Mock theoretical prices

            theoretical_prices = await calculator._calculate_theoretical_prices(
                sample_option_chain_data,
                underlying_price=26000.0
            )

            assert len(theoretical_prices) == 3
            assert theoretical_prices[0] == 45.20
            assert theoretical_prices[1] == 43.10
            assert theoretical_prices[2] == 24.50

            # Verify BSM was called with correct parameters
            assert mock_bsm.call_count == 3

    @pytest.mark.asyncio
    async def test_performance_target_compliance(
        self,
        calculator,
        sample_option_chain_data,
        sample_market_prices
    ):
        """Test that performance targets are met (<15ms for 200 options)."""
        # Create larger option chain (200 options) for performance test
        large_option_chain = []
        large_market_prices = []

        for i in range(200):
            strike = 24000 + (i * 50)
            for option_type in ['CE', 'PE']:
                large_option_chain.append({
                    'strike': strike,
                    'expiry_date': '2025-01-30',
                    'option_type': option_type,
                    'volatility': 0.2,
                    'underlying_price': 26000.0
                })
                large_market_prices.append(50.0 + (i * 0.1))

        # Mock fast vectorized response
        mock_greeks_result = {
            'results': [{}] * len(large_option_chain),
            'performance': {'execution_time_ms': 8.0},  # Fast vectorized calculation
            'method_used': 'vectorized'
        }

        calculator.vectorized_engine.calculate_option_chain_greeks_vectorized = AsyncMock(
            return_value=mock_greeks_result
        )

        with patch.object(calculator, '_calculate_theoretical_prices') as mock_theoretical:
            mock_theoretical.return_value = [45.0] * len(large_option_chain)

            start_time = asyncio.get_event_loop().time()

            result = await calculator.calculate_premium_analysis(
                market_prices=large_market_prices,
                option_chain_data=large_option_chain,
                underlying_price=26000.0,
                include_greeks=False
            )

            end_time = asyncio.get_event_loop().time()
            total_time_ms = (end_time - start_time) * 1000

        # Verify performance target (<15ms for 200 options)
        assert total_time_ms < 15.0, f"Performance target missed: {total_time_ms:.2f}ms > 15ms"
        assert len(result['results']) == len(large_option_chain)
        assert result['performance']['options_per_second'] > 10000  # High throughput

    def test_group_by_expiry(self, calculator):
        """Test grouping options by expiry date."""
        options = [
            {'expiry_date': '2025-01-30', 'strike': 26000},
            {'expiry_date': '2025-01-30', 'strike': 26100},
            {'expiry_date': '2025-02-27', 'strike': 26000},
            {'expiry_date': '2025-02-27', 'strike': 26100},
        ]

        grouped = calculator._group_by_expiry(options)

        assert len(grouped) == 2
        assert '2025-01-30' in grouped
        assert '2025-02-27' in grouped
        assert len(grouped['2025-01-30']) == 2
        assert len(grouped['2025-02-27']) == 2


class TestPremiumAnalysisIntegration:
    """Integration tests with actual vectorized engine."""

    @pytest.mark.asyncio
    async def test_full_integration_with_vectorized_engine(self):
        """Test full integration with actual vectorized engine (not mocked)."""
        # This test requires the actual vectorized engine
        try:
            from app.services.vectorized_pyvollib_engine import VectorizedPyvolibGreeksEngine

            vectorized_engine = VectorizedPyvolibGreeksEngine()
            calculator = PremiumDiscountCalculator(vectorized_engine)

            # Simple option data for integration test
            option_data = [
                {
                    'strike': 26000.0,
                    'expiry_date': '2025-01-30',
                    'option_type': 'CE',
                    'volatility': 0.2
                }
            ]
            market_prices = [50.0]

            result = await calculator.calculate_premium_analysis(
                market_prices=market_prices,
                option_chain_data=option_data,
                underlying_price=26000.0,
                include_greeks=True
            )

            # Verify integration worked
            assert len(result['results']) == 1
            assert 'premium_amount' in result['results'][0]
            assert 'mispricing_severity' in result['results'][0]

            # Verify performance
            performance = result['performance']
            assert 'execution_time_ms' in performance
            assert 'options_per_second' in performance

        except ImportError:
            pytest.skip("Vectorized engine not available for integration test")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
