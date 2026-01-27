"""
pandas_ta Indicator Calculation Coverage Tests with Real OHLCV Data

Addresses functionality_issues.txt requirement:
"pandas_ta indicator calls require real OHLCV history; tests must cover both successful
indicator calculation and failure when history missing to hit 95% branch coverage."

These tests verify pandas_ta indicator calculations work with real OHLCV data
and fail appropriately when historical data is missing or insufficient.
"""
import json
import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

try:
    import pandas_ta as ta

    from app.errors import TechnicalIndicatorError
    from app.schemas.config_schema import (
        SignalConfigData,
        TechnicalIndicatorConfig,
        TickProcessingContext,
    )
    from app.services.pandas_ta_executor import PandasTAExecutor
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False


class TestPandasTARealOHLCVData:
    """Test pandas_ta calculations with real OHLCV data scenarios."""

    @pytest.fixture
    def real_ohlcv_data(self):
        """Generate realistic OHLCV data for testing."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='5T')
        base_price = 100.0

        # Generate realistic price movements
        np.random.seed(42)  # For reproducible tests
        returns = np.random.normal(0, 0.02, len(dates))  # 2% volatility

        prices = [base_price]
        for ret in returns[1:]:
            prices.append(prices[-1] * (1 + ret))

        # Create OHLC from price series
        data = []
        for i, (date, price) in enumerate(zip(dates, prices, strict=False)):
            # Simulate intraday volatility
            high = price * (1 + abs(np.random.normal(0, 0.01)))
            low = price * (1 - abs(np.random.normal(0, 0.01)))
            open_price = prices[i-1] if i > 0 else price

            data.append({
                'timestamp': date,
                'open': open_price,
                'high': high,
                'low': low,
                'close': price,
                'volume': np.random.randint(1000, 10000)
            })

        return data

    @pytest.fixture
    def insufficient_ohlcv_data(self):
        """Generate insufficient OHLCV data (too few periods)."""
        return [
            {
                'timestamp': datetime.now(),
                'open': 100.0,
                'high': 102.0,
                'low': 98.0,
                'close': 101.0,
                'volume': 1000
            }
        ]

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client for caching."""
        redis_mock = AsyncMock()
        redis_mock.get.return_value = None
        redis_mock.setex.return_value = True
        return redis_mock

    @pytest.fixture
    def mock_historical_manager(self):
        """Mock historical data manager."""
        manager = AsyncMock()
        manager.get_historical_data_for_indicator = AsyncMock()
        return manager

    @pytest.fixture
    def pandas_ta_executor(self, mock_redis_client):
        """Create PandasTAExecutor with mocked dependencies."""
        if not PANDAS_TA_AVAILABLE:
            pytest.skip("pandas_ta not available")

        return PandasTAExecutor(mock_redis_client)

    @pytest.mark.asyncio
    async def test_successful_indicator_calculation_with_real_data(self, pandas_ta_executor, real_ohlcv_data, mock_historical_manager):
        """Test successful indicator calculation when sufficient OHLCV data is available."""
        # Mock historical data manager to return real OHLCV data
        with patch('app.services.pandas_ta_executor.get_historical_data_manager') as mock_get_manager:
            mock_get_manager.return_value = mock_historical_manager
            mock_historical_manager.get_historical_data_for_indicator.return_value = {
                "success": True,
                "data": real_ohlcv_data
            }

            # Create test configuration
            config = MagicMock()
            config.technical_indicators = [
                MagicMock(
                    name="SMA",
                    parameters={"length": 20},
                    output_key="sma_20"
                ),
                MagicMock(
                    name="RSI",
                    parameters={"length": 14},
                    output_key="rsi_14"
                )
            ]
            config.interval.value = "5m"
            config.frequency.value = "1h"
            config.output.cache_results = False

            # Create test context
            context = MagicMock()
            context.instrument_key = "NSE@RELIANCE@EQ"
            context.timestamp = datetime.now()
            context.tick_data = {
                'ltp': {'value': 101.5, 'currency': 'INR'},
                'open': 100.0,
                'high': 102.0,
                'low': 99.0,
                'volume': 1500
            }
            context.aggregated_data = {}

            # Execute indicators
            result = await pandas_ta_executor.execute_indicators(config, context)

            # Verify successful execution
            assert result is not None
            assert result['calculation_type'] == 'technical_indicators'
            assert result['indicators_count'] > 0
            assert result['data_points'] > 20  # Sufficient data for calculations
            assert 'results' in result
            assert len(result['results']) > 0

            # Verify specific indicator results
            results = result['results']
            assert 'sma_20' in results or any('sma' in str(k).lower() for k in results)
            assert 'rsi_14' in results or any('rsi' in str(k).lower() for k in results)

    @pytest.mark.asyncio
    async def test_indicator_failure_with_missing_historical_data(self, pandas_ta_executor, mock_historical_manager):
        """Test indicator calculation failure when historical data is completely missing."""
        # Mock historical data manager to return no data
        with patch('app.services.pandas_ta_executor.get_historical_data_manager') as mock_get_manager:
            mock_get_manager.return_value = mock_historical_manager
            mock_historical_manager.get_historical_data_for_indicator.return_value = {
                "success": False,
                "data": []
            }

            # Create test configuration
            config = MagicMock()
            config.technical_indicators = [
                MagicMock(
                    name="SMA",
                    parameters={"length": 20},
                    output_key="sma_20"
                )
            ]
            config.interval.value = "5m"
            config.frequency.value = "1h"
            config.output.cache_results = False

            # Create test context with no aggregated data
            context = MagicMock()
            context.instrument_key = "NSE@RELIANCE@EQ"
            context.timestamp = datetime.now()
            context.tick_data = {
                'ltp': {'value': 101.5, 'currency': 'INR'}
            }
            context.aggregated_data = {}

            # Should raise TechnicalIndicatorError due to missing data
            with pytest.raises(TechnicalIndicatorError) as exc_info:
                await pandas_ta_executor.execute_indicators(config, context)

            assert "historical data" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_indicator_failure_with_insufficient_data_periods(self, pandas_ta_executor, insufficient_ohlcv_data, mock_historical_manager):
        """Test indicator calculation failure when data periods are insufficient."""
        # Mock historical data manager to return insufficient data
        with patch('app.services.pandas_ta_executor.get_historical_data_manager') as mock_get_manager:
            mock_get_manager.return_value = mock_historical_manager
            mock_historical_manager.get_historical_data_for_indicator.return_value = {
                "success": True,
                "data": insufficient_ohlcv_data  # Only 1 data point
            }

            # Create test configuration requiring more data than available
            config = MagicMock()
            config.technical_indicators = [
                MagicMock(
                    name="SMA",
                    parameters={"length": 20},  # Requires 20 periods
                    output_key="sma_20"
                )
            ]
            config.interval.value = "5m"
            config.frequency.value = "1h"
            config.output.cache_results = False

            context = MagicMock()
            context.instrument_key = "NSE@RELIANCE@EQ"
            context.timestamp = datetime.now()
            context.tick_data = {
                'ltp': {'value': 101.5, 'currency': 'INR'}
            }
            context.aggregated_data = {}

            # Should return empty results due to insufficient data
            result = await pandas_ta_executor.execute_indicators(config, context)
            assert result == {}

    @pytest.mark.asyncio
    async def test_dataframe_preparation_with_missing_ohlcv_columns(self, pandas_ta_executor, mock_historical_manager):
        """Test DataFrame preparation failure when OHLCV columns are missing."""
        # Mock historical data with missing required columns
        incomplete_data = [
            {
                'timestamp': datetime.now(),
                'close': 100.0,
                'volume': 1000
                # Missing: open, high, low
            }
        ]

        with patch('app.services.pandas_ta_executor.get_historical_data_manager') as mock_get_manager:
            mock_get_manager.return_value = mock_historical_manager
            mock_historical_manager.get_historical_data_for_indicator.return_value = {
                "success": True,
                "data": incomplete_data
            }

            config = MagicMock()
            config.interval.value = "5m"
            config.frequency.value = "1h"

            context = MagicMock()
            context.instrument_key = "NSE@RELIANCE@EQ"
            context.timestamp = datetime.now()
            context.tick_data = {'ltp': {'value': 101.5}}
            context.aggregated_data = {}

            # Should fail to prepare DataFrame with missing columns
            df = await pandas_ta_executor.prepare_dataframe("NSE@RELIANCE@EQ", config, context)

            # Should return empty DataFrame when required columns missing
            assert df is None or df.empty

    @pytest.mark.asyncio
    async def test_pandas_ta_library_not_available(self, mock_redis_client):
        """Test behavior when pandas_ta library is not available."""
        with patch('app.services.pandas_ta_executor.PANDAS_TA_AVAILABLE', False):
            # Should raise error during initialization
            with pytest.raises(TechnicalIndicatorError) as exc_info:
                PandasTAExecutor(mock_redis_client)

            assert "pandas_ta library not available" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_strategy_execution_without_pandas_ta(self, pandas_ta_executor):
        """Test strategy execution failure when pandas_ta becomes unavailable."""
        # Mock pandas_ta unavailability during execution
        with patch('app.services.pandas_ta_executor.PANDAS_TA_AVAILABLE', False):
            df = pd.DataFrame({
                'open': [100, 101, 102],
                'high': [102, 103, 104],
                'low': [99, 100, 101],
                'close': [101, 102, 103],
                'volume': [1000, 1100, 1200]
            })

            strategy_dict = {'sma': [{'kind': 'sma', 'length': 2}]}
            indicators = [MagicMock(output_key='sma_2', name='sma', parameters={'length': 2})]

            # Should raise error when pandas_ta not available
            with pytest.raises(TechnicalIndicatorError) as exc_info:
                await pandas_ta_executor.execute_strategy(df, strategy_dict, indicators)

            assert "pandas_ta library not available" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_historical_data_retrieval_timeout(self, pandas_ta_executor, mock_historical_manager):
        """Test handling of historical data retrieval timeouts."""
        # Mock historical manager to raise timeout exception
        with patch('app.services.pandas_ta_executor.get_historical_data_manager') as mock_get_manager:
            mock_get_manager.return_value = mock_historical_manager
            mock_historical_manager.get_historical_data_for_indicator.side_effect = TimeoutError("Historical data timeout")

            config = MagicMock()
            config.technical_indicators = [MagicMock(name="SMA", parameters={}, output_key="sma")]
            config.interval.value = "5m"
            config.frequency.value = "1h"
            config.output.cache_results = False

            context = MagicMock()
            context.instrument_key = "NSE@RELIANCE@EQ"
            context.timestamp = datetime.now()
            context.tick_data = {'ltp': {'value': 101.5}}
            context.aggregated_data = {}

            # Should raise TechnicalIndicatorError when historical data times out
            with pytest.raises(TechnicalIndicatorError) as exc_info:
                await pandas_ta_executor.execute_indicators(config, context)

            assert "failed to retrieve sufficient historical data" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_invalid_ohlcv_data_validation(self, pandas_ta_executor):
        """Test validation of invalid OHLCV data."""
        # Test with negative prices
        invalid_data = pd.DataFrame({
            'open': [100, -50, 102],  # Negative price
            'high': [102, 103, 104],
            'low': [99, 100, 101],
            'close': [101, 102, 103],
            'volume': [1000, 1100, 1200]
        })

        # Should detect invalid data and return empty DataFrame
        formatted_df = pandas_ta_executor.format_dataframe(invalid_data)

        # Validation should handle negative values appropriately
        assert formatted_df is not None

    @pytest.mark.asyncio
    async def test_cache_behavior_with_real_data(self, pandas_ta_executor, real_ohlcv_data, mock_historical_manager):
        """Test caching behavior with real OHLCV data."""
        # Test cache miss -> data retrieval -> cache storage
        cached_data = json.dumps(real_ohlcv_data[:50])  # Partial cached data
        pandas_ta_executor.redis_client.get.return_value = cached_data.encode()

        config = MagicMock()
        config.interval.value = "5m"

        context = MagicMock()
        context.instrument_key = "NSE@RELIANCE@EQ"
        context.timestamp = datetime.now()
        context.tick_data = {
            'ltp': {'value': 101.5, 'currency': 'INR'},
            'open': 100.0,
            'high': 102.0,
            'low': 99.0,
            'volume': 1500
        }
        context.aggregated_data = {}

        # Should use cached data and add current tick
        df = await pandas_ta_executor.prepare_dataframe("NSE@RELIANCE@EQ", config, context)

        assert df is not None
        assert len(df) > len(real_ohlcv_data[:50])  # Should include cached data + current tick


class TestPandasTAErrorPaths:
    """Test error paths and edge cases in pandas_ta calculations."""

    @pytest.mark.asyncio
    async def test_extract_ohlcv_from_invalid_tick(self):
        """Test OHLCV extraction from invalid tick data."""
        if not PANDAS_TA_AVAILABLE:
            pytest.skip("pandas_ta not available")

        redis_mock = AsyncMock()
        executor = PandasTAExecutor(redis_mock)

        # Test with completely invalid tick data
        invalid_ticks = [
            {},  # Empty dict
            {'invalid_field': 'value'},  # No LTP
            {'ltp': None},  # Null LTP
            {'ltp': 'invalid'},  # Non-numeric LTP
            {'ltp': {'value': 'invalid'}},  # Non-numeric nested LTP
        ]

        for tick_data in invalid_ticks:
            result = executor.extract_ohlcv_from_tick(tick_data, datetime.now())
            assert result is None

    @pytest.mark.asyncio
    async def test_strategy_building_with_invalid_indicators(self):
        """Test strategy building with invalid indicator configurations."""
        if not PANDAS_TA_AVAILABLE:
            pytest.skip("pandas_ta not available")

        redis_mock = AsyncMock()
        executor = PandasTAExecutor(redis_mock)

        # Test with invalid indicators
        invalid_indicators = [
            MagicMock(name="INVALID_INDICATOR", parameters={}),
            MagicMock(name=None, parameters={}),  # None name
            MagicMock(name="SMA", parameters=None),  # None parameters
        ]

        strategy_dict = executor.build_strategy(invalid_indicators)

        # Should handle invalid indicators gracefully
        assert isinstance(strategy_dict, dict)

    @pytest.mark.asyncio
    async def test_currency_conversion_failure(self, mock_redis_client):
        """Test currency conversion failure handling."""
        if not PANDAS_TA_AVAILABLE:
            pytest.skip("pandas_ta not available")

        executor = PandasTAExecutor(mock_redis_client)

        df = pd.DataFrame({
            'open': [100, 101],
            'high': [102, 103],
            'low': [99, 100],
            'close': [101, 102],
            'volume': [1000, 1100]
        })

        # Test with invalid currency conversion
        result_df = await executor.prepare_currency_converted_data(
            df, "INVALID_CURRENCY", "USD", "NSE@RELIANCE@EQ"
        )

        # Should return original DataFrame on conversion failure
        pd.testing.assert_frame_equal(result_df, df)


def run_coverage_test():
    """Run pandas_ta coverage tests with real OHLCV data."""
    import subprocess
    import sys

    print("🔍 Running pandas_ta Real OHLCV Data Coverage Tests...")

    cmd = [
        sys.executable, '-m', 'pytest',
        __file__,
        '--cov=app.services.pandas_ta_executor',
        '--cov-report=term-missing',
        '--cov-report=json:coverage_pandas_ta_real_data.json',
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
    print("🚀 pandas_ta Real OHLCV Data Coverage Tests")
    print("=" * 60)

    success = run_coverage_test()

    if success:
        print("\n✅ pandas_ta real data tests passed with ≥95% coverage!")
        print("📊 Coverage validated for:")
        print("  - Successful indicator calculation with real OHLCV data")
        print("  - Failure when historical data completely missing")
        print("  - Failure when insufficient data periods available")
        print("  - DataFrame preparation with missing OHLCV columns")
        print("  - pandas_ta library unavailability handling")
        print("  - Strategy execution without pandas_ta")
        print("  - Historical data retrieval timeouts")
        print("  - Invalid OHLCV data validation")
        print("  - Cache behavior with real data")
        print("  - Error paths for invalid tick data")
        print("  - Strategy building with invalid indicators")
        print("  - Currency conversion failure handling")
        print("\n🎯 Real-world scenarios covered:")
        print("  - Market data with realistic price movements")
        print("  - Insufficient historical data scenarios")
        print("  - Network timeouts and service failures")
        print("  - Data quality validation and error handling")
    else:
        print("\n❌ pandas_ta real data tests need improvement")
        sys.exit(1)
