"""
Vectorized pyvollib Greeks Engine Fallback Behavior Tests

Addresses functionality_issues.txt requirement:
"Vectorized pyvollib-based Greeks engine still documents fallback behavior; ensure tests
exercise both vectorized success and fallback-disabled failure paths so the fallback
logic is proven and coverage validated."

These tests verify the vectorized pyvollib engine's production behavior where fallback
is disabled in production environments to ensure fail-fast reliability.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import importlib.util

if importlib.util.find_spec('py_vollib'):
    PYVOLLIB_AVAILABLE = True
else:
    PYVOLLIB_AVAILABLE = False


class TestVectorizedPyvolibProductionBehavior:
    """Test vectorized pyvollib engine production behavior with disabled fallbacks."""

    @pytest.fixture
    def mock_greeks_model_config(self):
        """Mock Greeks model configuration."""
        config = MagicMock()
        config.model_name = "black_scholes_merton"
        config.parameters = MagicMock()
        config.parameters.risk_free_rate = 0.05
        config.parameters.dividend_yield = 0.02
        config.initialize = MagicMock()
        return config

    @pytest.fixture
    def mock_circuit_breaker(self):
        """Mock circuit breaker."""
        breaker = AsyncMock()
        breaker.execute = AsyncMock()
        return breaker

    @pytest.fixture
    def vectorized_engine(self, mock_greeks_model_config, mock_circuit_breaker):
        """Create vectorized engine with mocked dependencies."""
        if not PYVOLLIB_AVAILABLE:
            pytest.skip("pyvollib not available")

        with patch('app.services.vectorized_pyvollib_engine.get_greeks_model_config') as mock_config, patch('app.services.vectorized_pyvollib_engine.get_circuit_breaker') as mock_breaker:
            mock_config.return_value = mock_greeks_model_config
            mock_breaker.return_value = mock_circuit_breaker

            return VectorizedPyvolibGreeksEngine(chunk_size=100, max_workers=2)

    @pytest.fixture
    def valid_option_chain_data(self):
        """Generate valid option chain data for testing."""
        return [
            {
                'strike': 100.0,
                'expiry_date': '2024-12-31',
                'option_type': 'CE',
                'volatility': 0.20,
                'price': 5.50
            },
            {
                'strike': 110.0,
                'expiry_date': '2024-12-31',
                'option_type': 'PE',
                'volatility': 0.25,
                'price': 8.20
            },
            {
                'strike': 120.0,
                'expiry_date': '2024-12-31',
                'option_type': 'CE',
                'volatility': 0.18,
                'price': 2.10
            }
        ]

    @pytest.mark.asyncio
    async def test_successful_vectorized_calculation_production_path(self, vectorized_engine, valid_option_chain_data, mock_circuit_breaker):
        """Test successful vectorized calculation in production environment."""
        # Mock successful circuit breaker execution
        mock_result = {
            'results': [
                {'delta': 0.6, 'gamma': 0.02, 'theta': -0.05, 'vega': 0.15, 'rho': 0.08},
                {'delta': -0.4, 'gamma': 0.018, 'theta': -0.04, 'vega': 0.12, 'rho': -0.06},
                {'delta': 0.3, 'gamma': 0.015, 'theta': -0.03, 'vega': 0.10, 'rho': 0.04}
            ],
            'performance': {'execution_time_ms': 15.5, 'options_processed': 3},
            'method_used': 'vectorized'
        }

        mock_circuit_breaker.execute.return_value = mock_result

        # Test in production environment
        with patch.dict('os.environ', {'ENVIRONMENT': 'production'}):
            result = await vectorized_engine.calculate_option_chain_greeks_vectorized(
                valid_option_chain_data,
                underlying_price=105.0,
                greeks_to_calculate=['delta', 'gamma', 'theta', 'vega', 'rho'],
                enable_fallback=True  # Fallback enabled but should be ignored in production
            )

        # Verify successful vectorized execution
        assert result is not None
        assert result['method_used'] == 'vectorized'
        assert len(result['results']) == 3
        assert all('delta' in res for res in result['results'])

        # Verify circuit breaker was used
        mock_circuit_breaker.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_production_fail_fast_no_fallback(self, vectorized_engine, valid_option_chain_data, mock_circuit_breaker):
        """Test that production environment fails fast without fallback when vectorized calculation fails."""
        # Mock circuit breaker to raise exception
        mock_circuit_breaker.execute.side_effect = Exception("Vectorized calculation failed")

        # Test in production environment
        with patch.dict('os.environ', {'ENVIRONMENT': 'production'}), pytest.raises(GreeksCalculationError) as exc_info:
            await vectorized_engine.calculate_option_chain_greeks_vectorized(
                valid_option_chain_data,
                underlying_price=105.0,
                enable_fallback=True  # Fallback enabled but should be ignored
            )

        # Verify production fail-fast behavior
        assert "vectorized Greeks calculation failed" in str(exc_info.value).lower()
        assert "fallback disabled for production reliability" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_development_environment_allows_fallback(self, vectorized_engine, valid_option_chain_data, mock_circuit_breaker):
        """Test that development environment allows fallback when vectorized calculation fails."""
        # Mock circuit breaker to raise exception
        mock_circuit_breaker.execute.side_effect = Exception("Vectorized calculation failed")

        # Mock the fallback calculation method
        fallback_result = {
            'results': [
                {'delta': 0.6, 'gamma': 0.02, 'theta': -0.05, 'vega': 0.15, 'rho': 0.08},
                {'delta': -0.4, 'gamma': 0.018, 'theta': -0.04, 'vega': 0.12, 'rho': -0.06}
            ],
            'performance': {'execution_time_ms': 85.0, 'options_processed': 2},
            'method_used': 'fallback'
        }

        with patch.object(vectorized_engine, '_fallback_option_chain_calculation', return_value=fallback_result), patch.dict('os.environ', {'ENVIRONMENT': 'development'}):
            result = await vectorized_engine.calculate_option_chain_greeks_vectorized(
                valid_option_chain_data,
                underlying_price=105.0,
                enable_fallback=True
            )

        # Verify fallback was used in development
        assert result is not None
        assert result['method_used'] == 'fallback'
        assert len(result['results']) == 2

    @pytest.mark.asyncio
    async def test_fallback_disabled_explicitly_fails_fast(self, vectorized_engine, valid_option_chain_data, mock_circuit_breaker):
        """Test that explicitly disabling fallback causes fail-fast behavior regardless of environment."""
        # Mock circuit breaker to raise exception
        mock_circuit_breaker.execute.side_effect = Exception("Vectorized calculation failed")

        # Test in development with fallback explicitly disabled
        with patch.dict('os.environ', {'ENVIRONMENT': 'development'}), pytest.raises(GreeksCalculationError):
            await vectorized_engine.calculate_option_chain_greeks_vectorized(
                valid_option_chain_data,
                underlying_price=105.0,
                enable_fallback=False  # Explicitly disabled
            )

    @pytest.mark.asyncio
    async def test_vectorized_array_preparation_failure(self, vectorized_engine, mock_circuit_breaker):
        """Test vectorized calculation failure when array preparation fails."""
        # Mock circuit breaker to call the internal method
        mock_circuit_breaker.execute.side_effect = lambda func, *args, **kwargs: func(*args[:-1])  # Remove cache_key

        # Invalid option data that should cause array preparation to fail
        invalid_option_data = [
            {
                'strike': 'invalid',  # Non-numeric strike
                'expiry_date': '2024-12-31',
                'option_type': 'CE'
            }
        ]

        with patch.dict('os.environ', {'ENVIRONMENT': 'production'}), pytest.raises(GreeksCalculationError):
            await vectorized_engine.calculate_option_chain_greeks_vectorized(
                invalid_option_data,
                underlying_price=105.0,
                enable_fallback=False
            )

    @pytest.mark.asyncio
    async def test_unsupported_model_error(self):
        """Test error handling for unsupported pricing models."""
        with patch('app.services.vectorized_pyvollib_engine.get_greeks_model_config') as mock_config, patch('app.services.vectorized_pyvollib_engine.get_circuit_breaker'):
            config = MagicMock()
            config.model_name = "unsupported_model"
            config.initialize = MagicMock()
            mock_config.return_value = config

            # Should raise UnsupportedModelError during initialization
            with pytest.raises(UnsupportedModelError):
                VectorizedPyvolibGreeksEngine()

    @pytest.mark.asyncio
    async def test_pyvollib_import_failure(self):
        """Test error handling when pyvollib import fails."""
        with patch('app.services.vectorized_pyvollib_engine.get_greeks_model_config') as mock_config, patch('app.services.vectorized_pyvollib_engine.get_circuit_breaker'):
            config = MagicMock()
            config.model_name = "black_scholes_merton"
            config.initialize = MagicMock()
            mock_config.return_value = config

            # Mock import failure
            with patch('builtins.__import__', side_effect=ImportError("pyvollib not available")), pytest.raises(GreeksCalculationError) as exc_info:
                engine = VectorizedPyvolibGreeksEngine()
                engine._load_model_functions()

            assert "failed to import pyvollib functions" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_vectorized_calculation_with_invalid_data_types(self, vectorized_engine, mock_circuit_breaker):
        """Test vectorized calculation with invalid data types."""
        # Mock circuit breaker to call internal method
        async def mock_execute(func, *args, **kwargs):
            return await func(*args[:-1])  # Remove cache_key

        mock_circuit_breaker.execute.side_effect = mock_execute

        # Invalid data types in option chain
        invalid_data = [
            {
                'strike': None,  # None value
                'expiry_date': '2024-12-31',
                'option_type': 'CE',
                'volatility': 0.20
            }
        ]

        with patch.dict('os.environ', {'ENVIRONMENT': 'production'}), pytest.raises(GreeksCalculationError):
            await vectorized_engine.calculate_option_chain_greeks_vectorized(
                invalid_data,
                underlying_price=105.0,
                enable_fallback=False
            )

    @pytest.mark.asyncio
    async def test_term_structure_calculation_with_mixed_success_failure(self, vectorized_engine):
        """Test term structure calculation with mixed success and failure scenarios."""
        symbols_data = {
            'VALID_SYMBOL': [
                {
                    'strike': 100.0,
                    'expiry_date': '2024-12-31',
                    'option_type': 'CE',
                    'volatility': 0.20
                }
            ],
            'INVALID_SYMBOL': [
                {
                    'strike': 'invalid',
                    'expiry_date': '2024-12-31',
                    'option_type': 'CE'
                }
            ]
        }

        underlying_prices = {
            'VALID_SYMBOL': 105.0,
            'INVALID_SYMBOL': 110.0
        }

        # Mock successful calculation for valid symbol
        with patch.object(vectorized_engine, 'calculate_option_chain_greeks_vectorized') as mock_calc:
            mock_calc.side_effect = [
                {
                    'results': [{'delta': 0.6}],
                    'performance': {},
                    'method_used': 'vectorized'
                },
                Exception("Calculation failed for invalid symbol")
            ]

            with pytest.raises(GreeksCalculationError):
                await vectorized_engine.calculate_term_structure_vectorized(
                    symbols_data,
                    underlying_prices
                )

    @pytest.mark.asyncio
    async def test_performance_metrics_tracking(self, vectorized_engine, valid_option_chain_data, mock_circuit_breaker):
        """Test that performance metrics are correctly tracked for vectorized calculations."""
        # Mock successful execution with performance data
        mock_result = {
            'results': [{'delta': 0.6}],
            'performance': {'execution_time_ms': 12.5, 'options_processed': 1},
            'method_used': 'vectorized'
        }
        mock_circuit_breaker.execute.return_value = mock_result

        # Reset performance metrics
        vectorized_engine.reset_performance_metrics()

        # Execute calculation
        await vectorized_engine.calculate_option_chain_greeks_vectorized(
            valid_option_chain_data[:1],  # Single option
            underlying_price=105.0
        )

        # Verify metrics were updated
        metrics = vectorized_engine.get_performance_metrics()
        assert metrics['vectorized_calls'] == 1
        assert metrics['total_options_processed'] == 1
        assert metrics['avg_vectorized_time_ms'] > 0

    @pytest.mark.asyncio
    async def test_array_validation_edge_cases(self, vectorized_engine):
        """Test array validation with edge cases."""
        # Test arrays with extreme values
        strikes = np.array([0.01, 1000000.0])  # Very small and very large
        times_to_expiry = np.array([0.001, 15.0])  # Very short and very long
        volatilities = np.array([0.001, 10.0])  # Very low and very high

        # Should fail validation for extreme values
        is_valid = vectorized_engine._validate_vectorized_arrays(
            strikes, times_to_expiry, volatilities
        )
        assert not is_valid

    @pytest.mark.asyncio
    async def test_greek_array_validation_with_bounds(self, vectorized_engine):
        """Test Greek array validation with out-of-bounds values."""
        # Test delta values outside [-1, 1] range
        invalid_deltas = np.array([-2.0, 0.5, 1.5])  # Out of bounds values

        validated_deltas = vectorized_engine._validate_greek_array(invalid_deltas, 'delta')

        # Out of bounds values should be replaced with NaN
        assert np.isnan(validated_deltas[0])  # -2.0 -> NaN
        assert validated_deltas[1] == 0.5    # Valid value preserved
        assert np.isnan(validated_deltas[2])  # 1.5 -> NaN

    @pytest.mark.asyncio
    async def test_bulk_calculation_with_performance_comparison(self, vectorized_engine):
        """Test bulk calculation with performance comparison enabled."""
        bulk_data = [
            {
                'underlying_price': 100.0,
                'strike': 100.0,
                'expiry_date': '2024-12-31',
                'option_type': 'CE',
                'volatility': 0.20
            }
        ]

        # Mock both vectorized and legacy calculations
        with patch.object(vectorized_engine, 'calculate_option_chain_greeks_vectorized') as mock_vectorized, patch.object(vectorized_engine, '_legacy_bulk_calculation') as mock_legacy:
            mock_vectorized.return_value = {
                'results': [{'delta': 0.6}],
                'performance': {},
                'method_used': 'vectorized'
            }
            mock_legacy.return_value = {'note': 'Legacy calculation completed'}

            result = await vectorized_engine.calculate_bulk_greeks_with_performance_metrics(
                bulk_data,
                compare_with_legacy=True
            )

            assert 'performance_comparison' in result
            assert result['performance_comparison']['speedup_ratio'] >= 0


def run_coverage_test():
    """Run pyvollib vectorized engine coverage tests."""
    import subprocess
    import sys

    print("🔍 Running pyvollib Vectorized Engine Fallback Coverage Tests...")

    cmd = [
        sys.executable, '-m', 'pytest',
        __file__,
        '--cov=app.services.vectorized_pyvollib_engine',
        '--cov-report=term-missing',
        '--cov-report=json:coverage_pyvollib_vectorized.json',
        '--cov-fail-under=95',
        '-v'
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    print("STDOUT:")
    print(result.stdout)

    if result.stderr:
        print("STDERR:")
        print(result.stderr)

    return result.returncode == 0


if __name__ == "__main__":
    print("🚀 pyvollib Vectorized Engine Fallback Coverage Tests")
    print("=" * 60)

    success = run_coverage_test()

    if success:
        print("\n✅ pyvollib vectorized engine tests passed with ≥95% coverage!")
        print("📊 Coverage validated for:")
        print("  - Successful vectorized calculation in production")
        print("  - Production fail-fast behavior (no fallback)")
        print("  - Development environment fallback allowance")
        print("  - Explicit fallback disable behavior")
        print("  - Vectorized array preparation failures")
        print("  - Unsupported model error handling")
        print("  - pyvollib import failure handling")
        print("  - Invalid data type handling")
        print("  - Term structure calculation mixed scenarios")
        print("  - Performance metrics tracking")
        print("  - Array validation edge cases")
        print("  - Greek array bounds validation")
        print("  - Bulk calculation with performance comparison")
        print("\n🎯 Fallback behavior validation:")
        print("  - Production: Fail-fast, no fallback allowed")
        print("  - Development: Fallback to legacy engine allowed")
        print("  - Explicit disable: Always fail-fast regardless of environment")
        print("  - Circuit breaker integration with fail-fast behavior")
    else:
        print("\n❌ pyvollib vectorized engine tests need improvement")
        sys.exit(1)
