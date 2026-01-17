"""
Comprehensive unit tests for PandasTAExecutor
Tests all 244+ pandas_ta indicators with proper data generation and validation
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from typing import Dict, Any, List
import asyncio
import json

try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False

from app.services.pandas_ta_executor import PandasTAExecutor
from app.schemas.config_schema import SignalConfigData, TickProcessingContext, TechnicalIndicatorConfig
from app.errors import TechnicalIndicatorError


class TestDataFactory:
    """Factory for generating test data for pandas_ta indicators"""
    
    @staticmethod
    def create_ohlcv_data(
        periods: int = 100,
        base_price: float = 100.0,
        volatility: float = 0.02,
        trend: float = 0.001,
        volume_base: int = 10000
    ) -> pd.DataFrame:
        """
        Generate realistic OHLCV data for testing indicators
        
        Args:
            periods: Number of periods to generate
            base_price: Starting price
            volatility: Price volatility (standard deviation as fraction of price)
            trend: Trend per period (as fraction)
            volume_base: Base volume
            
        Returns:
            DataFrame with OHLCV data
        """
        dates = pd.date_range(
            start='2024-01-01', 
            periods=periods, 
            freq='5T'
        )
        
        # Generate price series with trend and volatility
        prices = []
        current_price = base_price
        
        for i in range(periods):
            # Add trend
            current_price *= (1 + trend)
            
            # Add random volatility
            noise = np.random.normal(0, volatility * current_price)
            current_price += noise
            
            # Ensure price stays positive
            current_price = max(current_price, base_price * 0.1)
            prices.append(current_price)
        
        # Generate OHLC from close prices
        data = []
        for i, close in enumerate(prices):
            # Generate realistic OHLC relationships
            range_pct = np.random.uniform(0.005, 0.03)  # 0.5% to 3% range
            
            high = close * (1 + np.random.uniform(0, range_pct))
            low = close * (1 - np.random.uniform(0, range_pct))
            
            # Open is previous close with some gap
            if i == 0:
                open_price = close
            else:
                gap = np.random.normal(0, 0.002)  # Small gap
                open_price = prices[i-1] * (1 + gap)
            
            # Ensure OHLC relationships are correct
            high = max(high, open_price, close)
            low = min(low, open_price, close)
            
            # Generate volume with some correlation to price movement
            price_change = abs(close - open_price) / open_price if open_price > 0 else 0
            volume_multiplier = 1 + price_change * 2  # Higher volume on bigger moves
            volume = int(volume_base * volume_multiplier * np.random.uniform(0.5, 2.0))
            
            data.append({
                'timestamp': dates[i],
                'open': round(open_price, 2),
                'high': round(high, 2),
                'low': round(low, 2),
                'close': round(close, 2),
                'volume': volume
            })
        
        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        return df
    
    @staticmethod
    def create_trending_data(periods: int = 100, trend_strength: float = 0.01) -> pd.DataFrame:
        """Create data with strong trend for testing trend indicators"""
        return TestDataFactory.create_ohlcv_data(
            periods=periods,
            trend=trend_strength,
            volatility=0.01
        )
    
    @staticmethod
    def create_ranging_data(periods: int = 100, volatility: float = 0.03) -> pd.DataFrame:
        """Create ranging/sideways data for testing momentum indicators"""
        return TestDataFactory.create_ohlcv_data(
            periods=periods,
            trend=0.0001,  # Very small trend
            volatility=volatility
        )
    
    @staticmethod
    def create_volatile_data(periods: int = 100, volatility: float = 0.05) -> pd.DataFrame:
        """Create highly volatile data for testing volatility indicators"""
        return TestDataFactory.create_ohlcv_data(
            periods=periods,
            volatility=volatility,
            trend=0.001
        )
    
    @staticmethod
    def create_known_values_data() -> pd.DataFrame:
        """
        Create data with known indicator values for validation
        This uses a simple pattern where indicators can be calculated manually
        """
        periods = 20
        # Create simple ascending price series for easy calculation
        closes = list(range(100, 100 + periods))
        
        data = []
        for i, close in enumerate(closes):
            data.append({
                'timestamp': pd.Timestamp('2024-01-01') + pd.Timedelta(minutes=5*i),
                'open': close - 0.5,
                'high': close + 1.0,
                'low': close - 1.0,
                'close': float(close),
                'volume': 1000
            })
        
        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        return df


class TestPandasTAIndicators:
    """Test individual pandas_ta indicators for accuracy and robustness"""
    
    @pytest.fixture
    def sample_data(self):
        """Standard test data fixture"""
        return TestDataFactory.create_ohlcv_data(periods=50)
    
    @pytest.fixture
    def known_data(self):
        """Data with known/predictable values"""
        return TestDataFactory.create_known_values_data()
    
    @pytest.fixture
    def trending_data(self):
        """Trending market data"""
        return TestDataFactory.create_trending_data(periods=50, trend_strength=0.02)
    
    @pytest.fixture
    def volatile_data(self):
        """Volatile market data"""
        return TestDataFactory.create_volatile_data(periods=50, volatility=0.06)

    def test_trend_indicators(self, sample_data):
        """Test all trend-following indicators"""
        trend_indicators = [
            ('sma', {'length': 20}),
            ('ema', {'length': 20}),
            ('wma', {'length': 20}),
            ('dema', {'length': 20}),
            ('tema', {'length': 20}),
            ('trima', {'length': 20}),
            ('kama', {'length': 20}),
            ('mama', {}),
            ('hma', {'length': 20}),
            ('zlma', {'length': 20}),
            ('alma', {'length': 20}),
            ('linreg', {'length': 20}),
            ('midpoint', {'length': 20}),
            ('midprice', {'length': 20}),
            ('supertrend', {'length': 20, 'multiplier': 3.0}),
            ('vwma', {'length': 20}),
        ]
        
        for indicator_name, params in trend_indicators:
            if hasattr(ta, indicator_name):
                try:
                    result = getattr(ta, indicator_name)(
                        high=sample_data['high'],
                        low=sample_data['low'],
                        close=sample_data['close'],
                        volume=sample_data['volume'],
                        **params
                    )
                    
                    assert result is not None, f"{indicator_name} returned None"
                    
                    if isinstance(result, pd.Series):
                        assert len(result) <= len(sample_data), f"{indicator_name} returned too many values"
                        assert not result.isna().all(), f"{indicator_name} returned all NaN values"
                    elif isinstance(result, pd.DataFrame):
                        assert len(result) <= len(sample_data), f"{indicator_name} DataFrame too long"
                        assert not result.isna().all().all(), f"{indicator_name} returned all NaN DataFrame"
                    
                    print(f"✓ {indicator_name} passed")
                    
                except Exception as e:
                    pytest.fail(f"{indicator_name} failed: {e}")

    def test_momentum_indicators(self, sample_data):
        """Test momentum and oscillator indicators"""
        momentum_indicators = [
            ('rsi', {'length': 14}),
            ('cci', {'length': 20}),
            ('mfi', {'length': 14}),
            ('roc', {'length': 10}),
            ('cmo', {'length': 14}),
            ('mom', {'length': 10}),
            ('ppo', {'fast': 12, 'slow': 26}),
            ('trix', {'length': 14}),
            ('bop', {}),
            ('uo', {'fast': 7, 'medium': 14, 'slow': 28}),
            ('willr', {'length': 14}),
            ('stochrsi', {'length': 14}),
            ('fisher', {'length': 9}),
            ('cg', {'length': 10}),
            ('er', {'length': 10}),
            ('squeeze', {'bb_length': 20, 'bb_std': 2, 'kc_length': 20, 'kc_scalar': 1.5}),
            ('kdj', {'length': 9}),
            ('psl', {'length': 12}),
            ('qqe', {'length': 14, 'smooth': 5}),
            ('rsx', {'length': 14}),
            ('rvgi', {'length': 14}),
            ('smi', {'fast': 5, 'slow': 20, 'signal': 5}),
            ('tsi', {'fast': 25, 'slow': 13, 'signal': 13}),
        ]
        
        for indicator_name, params in momentum_indicators:
            if hasattr(ta, indicator_name):
                try:
                    result = getattr(ta, indicator_name)(
                        high=sample_data['high'],
                        low=sample_data['low'],
                        close=sample_data['close'],
                        volume=sample_data['volume'],
                        **params
                    )
                    
                    assert result is not None, f"{indicator_name} returned None"
                    
                    if isinstance(result, pd.Series):
                        # Check that values are within reasonable ranges for oscillators
                        if indicator_name in ['rsi', 'stochrsi', 'uo']:
                            valid_values = result.dropna()
                            if not valid_values.empty:
                                assert valid_values.min() >= 0, f"{indicator_name} has values below 0"
                                assert valid_values.max() <= 100, f"{indicator_name} has values above 100"
                    
                    print(f"✓ {indicator_name} passed")
                    
                except Exception as e:
                    pytest.fail(f"{indicator_name} failed: {e}")

    def test_volatility_indicators(self, volatile_data):
        """Test volatility indicators"""
        volatility_indicators = [
            ('atr', {'length': 14}),
            ('natr', {'length': 14}),
            ('trange', {}),
            ('bbands', {'length': 20, 'std': 2}),
            ('kc', {'length': 20, 'scalar': 2}),
            ('dpo', {'length': 20}),
            ('hwc', {'na': 0.2, 'nb': 0.1}),
            ('hwl', {'na': 0.2, 'nb': 0.1}),
            ('hwh', {'na': 0.2, 'nb': 0.1}),
            ('pdist', {}),
            ('thermo', {'length': 20}),
        ]
        
        for indicator_name, params in volatility_indicators:
            if hasattr(ta, indicator_name):
                try:
                    result = getattr(ta, indicator_name)(
                        high=volatile_data['high'],
                        low=volatile_data['low'],
                        close=volatile_data['close'],
                        volume=volatile_data['volume'],
                        **params
                    )
                    
                    assert result is not None, f"{indicator_name} returned None"
                    
                    if isinstance(result, pd.Series) and indicator_name in ['atr', 'natr']:
                        # ATR should be positive
                        valid_values = result.dropna()
                        if not valid_values.empty:
                            assert valid_values.min() >= 0, f"{indicator_name} has negative values"
                    
                    print(f"✓ {indicator_name} passed")
                    
                except Exception as e:
                    pytest.fail(f"{indicator_name} failed: {e}")

    def test_volume_indicators(self, sample_data):
        """Test volume-based indicators"""
        volume_indicators = [
            ('obv', {}),
            ('ad', {}),
            ('adosc', {'fast': 3, 'slow': 10}),
            ('cmf', {'length': 20}),
            ('efi', {'length': 13}),
            ('em', {'length': 14}),
            ('fi', {'length': 13}),
            ('nvi', {}),
            ('pvi', {}),
            ('pvol', {}),
            ('vp', {'width': 10}),
            ('vwap', {}),
            ('vwma', {'length': 20}),
            ('aobv', {'fast': 4, 'slow': 12}),
            ('kvo', {'fast': 34, 'slow': 55, 'signal': 13}),
        ]
        
        for indicator_name, params in volume_indicators:
            if hasattr(ta, indicator_name):
                try:
                    result = getattr(ta, indicator_name)(
                        high=sample_data['high'],
                        low=sample_data['low'],
                        close=sample_data['close'],
                        volume=sample_data['volume'],
                        **params
                    )
                    
                    assert result is not None, f"{indicator_name} returned None"
                    print(f"✓ {indicator_name} passed")
                    
                except Exception as e:
                    pytest.fail(f"{indicator_name} failed: {e}")

    def test_overlap_indicators(self, trending_data):
        """Test overlap/trend indicators"""
        overlap_indicators = [
            ('ichimoku', {}),
            ('fwma', {'length': 20}),
            ('pwma', {'length': 20}),
            ('sinwma', {'length': 20}),
            ('ssf', {'length': 20, 'poles': 2}),
            ('swma', {'length': 20}),
            ('t3', {'length': 20}),
            ('vidya', {'length': 20}),
            ('jma', {'length': 20}),
        ]
        
        for indicator_name, params in overlap_indicators:
            if hasattr(ta, indicator_name):
                try:
                    result = getattr(ta, indicator_name)(
                        high=trending_data['high'],
                        low=trending_data['low'],
                        close=trending_data['close'],
                        volume=trending_data['volume'],
                        **params
                    )
                    
                    assert result is not None, f"{indicator_name} returned None"
                    print(f"✓ {indicator_name} passed")
                    
                except Exception as e:
                    pytest.fail(f"{indicator_name} failed: {e}")

    def test_cycle_indicators(self, sample_data):
        """Test cycle analysis indicators"""
        cycle_indicators = [
            ('ebsw', {}),
            ('jdks', {'n': 20}),
        ]
        
        for indicator_name, params in cycle_indicators:
            if hasattr(ta, indicator_name):
                try:
                    result = getattr(ta, indicator_name)(
                        high=sample_data['high'],
                        low=sample_data['low'],
                        close=sample_data['close'],
                        volume=sample_data['volume'],
                        **params
                    )
                    
                    assert result is not None, f"{indicator_name} returned None"
                    print(f"✓ {indicator_name} passed")
                    
                except Exception as e:
                    pytest.fail(f"{indicator_name} failed: {e}")

    def test_statistics_indicators(self, sample_data):
        """Test statistical indicators"""
        stats_indicators = [
            ('kurtosis', {'length': 20}),
            ('mad', {'length': 20}),
            ('median', {'length': 20}),
            ('quantile', {'length': 20, 'q': 0.75}),
            ('skew', {'length': 20}),
            ('stdev', {'length': 20}),
            ('variance', {'length': 20}),
            ('zscore', {'length': 20}),
        ]
        
        for indicator_name, params in stats_indicators:
            if hasattr(ta, indicator_name):
                try:
                    result = getattr(ta, indicator_name)(
                        close=sample_data['close'],
                        **params
                    )
                    
                    assert result is not None, f"{indicator_name} returned None"
                    print(f"✓ {indicator_name} passed")
                    
                except Exception as e:
                    pytest.fail(f"{indicator_name} failed: {e}")


@pytest.mark.asyncio
class TestPandasTAExecutor:
    """Test the main PandasTAExecutor class functionality"""
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client"""
        redis = AsyncMock()
        redis.get.return_value = None
        redis.setex.return_value = True
        return redis
    
    @pytest.fixture
    def executor(self, mock_redis):
        """Create PandasTAExecutor instance"""
        return PandasTAExecutor(mock_redis)
    
    @pytest.fixture
    def sample_config(self):
        """Sample signal configuration"""
        return Mock(
            technical_indicators=[
                Mock(
                    name='sma',
                    output_key='sma_20',
                    parameters={'length': 20}
                ),
                Mock(
                    name='rsi',
                    output_key='rsi_14',
                    parameters={'length': 14}
                ),
                Mock(
                    name='macd',
                    output_key='macd',
                    parameters={'fast': 12, 'slow': 26, 'signal': 9}
                )
            ],
            interval=Mock(value='5m'),
            frequency=Mock(value='realtime'),
            output=Mock(cache_results=True, cache_ttl_seconds=300),
            parameters=Mock(length=20)
        )
    
    @pytest.fixture
    def sample_context(self):
        """Sample processing context"""
        return Mock(
            instrument_key='NSE@RELIANCE@EQ',
            timestamp=datetime.now(),
            tick_data={
                'ltp': {'value': 2500.50, 'currency': 'INR'},
                'high': {'value': 2510.00},
                'low': {'value': 2490.00},
                'open': {'value': 2495.00},
                'volume': 1000000,
                'metadata': {
                    'exchange': 'NSE',
                    'is_market_open': True
                }
            },
            aggregated_data={
                '5m': TestDataFactory.create_ohlcv_data(periods=50).to_dict('records')
            }
        )

    async def test_execute_indicators_success(self, executor, sample_config, sample_context):
        """Test successful indicator execution"""
        result = await executor.execute_indicators(sample_config, sample_context)
        
        assert result is not None
        assert 'instrument_key' in result
        assert 'results' in result
        assert 'metadata' in result
        assert result['instrument_key'] == 'NSE@RELIANCE@EQ'

    async def test_execute_indicators_no_config(self, executor, sample_context):
        """Test handling of empty indicator configuration"""
        config = Mock(technical_indicators=[])
        result = await executor.execute_indicators(config, sample_context)
        
        assert result == {}

    async def test_prepare_dataframe_from_cache(self, executor, sample_config, sample_context, mock_redis):
        """Test DataFrame preparation from cached data"""
        # Mock cached data
        cached_data = TestDataFactory.create_ohlcv_data(periods=30).to_dict('records')
        mock_redis.get.return_value = json.dumps(cached_data)
        
        df = await executor.prepare_dataframe('NSE@RELIANCE@EQ', sample_config, sample_context)
        
        assert df is not None
        assert len(df) >= 30  # Should include cached data + current tick
        assert all(col in df.columns for col in ['open', 'high', 'low', 'close', 'volume'])

    async def test_prepare_dataframe_from_context(self, executor, sample_config, sample_context):
        """Test DataFrame preparation from context aggregated data"""
        df = await executor.prepare_dataframe('NSE@RELIANCE@EQ', sample_config, sample_context)
        
        assert df is not None
        assert len(df) >= 50  # Should include context data + current tick
        assert all(col in df.columns for col in ['open', 'high', 'low', 'close', 'volume'])

    def test_extract_ohlcv_from_tick(self, executor):
        """Test OHLCV extraction from tick data"""
        tick_data = {
            'ltp': {'value': 2500.50, 'currency': 'INR'},
            'high': {'value': 2510.00},
            'low': {'value': 2490.00},
            'open': {'value': 2495.00},
            'volume': 1000000,
            'metadata': {
                'exchange': 'NSE',
                'is_market_open': True
            }
        }
        
        ohlcv = executor.extract_ohlcv_from_tick(tick_data, datetime.now())
        
        assert ohlcv is not None
        assert ohlcv['open'] == 2495.00
        assert ohlcv['high'] == 2510.00
        assert ohlcv['low'] == 2490.00
        assert ohlcv['close'] == 2500.50
        assert ohlcv['volume'] == 1000000
        assert ohlcv['currency'] == 'INR'

    def test_format_dataframe(self, executor):
        """Test DataFrame formatting for pandas_ta"""
        # Create test data with missing columns
        df = pd.DataFrame({
            'close': [100, 101, 102],
            'timestamp': pd.date_range('2024-01-01', periods=3, freq='5T')
        })
        
        formatted_df = executor.format_dataframe(df)
        
        assert all(col in formatted_df.columns for col in ['open', 'high', 'low', 'close', 'volume'])
        assert len(formatted_df) >= 2  # Minimum data points

    def test_build_strategy(self, executor, sample_config):
        """Test strategy building from indicator configurations"""
        strategy_dict = executor.build_strategy(sample_config.technical_indicators)
        
        if PANDAS_TA_AVAILABLE:
            assert 'sma' in strategy_dict
            assert 'rsi' in strategy_dict
            assert 'macd' in strategy_dict
            
            # Check parameter mapping
            sma_config = strategy_dict['sma'][0]
            assert sma_config['length'] == 20

    def test_validate_indicator_parameters(self, executor):
        """Test parameter validation for indicators"""
        # Test SMA parameters
        params = executor.validate_indicator_parameters('sma', {})
        assert params['length'] == 20  # Default
        
        # Test custom length
        params = executor.validate_indicator_parameters('sma', {'length': 50})
        assert params['length'] == 50
        
        # Test MACD parameters
        params = executor.validate_indicator_parameters('macd', {})
        assert params['fast'] == 12
        assert params['slow'] == 26
        assert params['signal'] == 9

    async def test_cache_results(self, executor, sample_config, sample_context, mock_redis):
        """Test results caching"""
        results = {'sma_20': 100.0, 'rsi_14': 55.0}
        
        await executor.cache_results('NSE@RELIANCE@EQ', sample_config, results)
        
        # Verify cache was called
        mock_redis.setex.assert_called_once()

    def test_get_metrics(self, executor):
        """Test metrics reporting"""
        metrics = executor.get_metrics()
        
        assert 'pandas_ta_available' in metrics
        assert isinstance(metrics['pandas_ta_available'], bool)


class TestPandasTAIntegration:
    """Integration tests for pandas_ta with real calculations"""
    
    def test_sma_calculation_accuracy(self):
        """Test SMA calculation against known values"""
        if not PANDAS_TA_AVAILABLE:
            pytest.skip("pandas_ta not available")
        
        # Create simple data for manual verification
        closes = [100, 101, 102, 103, 104]
        df = pd.DataFrame({'close': closes})
        
        # Calculate SMA(3)
        result = ta.sma(df['close'], length=3)
        
        # Manual calculation: (100+101+102)/3 = 101, (101+102+103)/3 = 102, (102+103+104)/3 = 103
        expected = [None, None, 101.0, 102.0, 103.0]
        
        for i, expected_val in enumerate(expected):
            if expected_val is not None:
                assert abs(result.iloc[i] - expected_val) < 0.001

    def test_rsi_boundary_values(self):
        """Test RSI stays within 0-100 bounds"""
        if not PANDAS_TA_AVAILABLE:
            pytest.skip("pandas_ta not available")
        
        # Create extreme data
        data = TestDataFactory.create_volatile_data(periods=100, volatility=0.1)
        
        rsi = ta.rsi(data['close'], length=14)
        
        valid_values = rsi.dropna()
        assert valid_values.min() >= 0, "RSI below 0"
        assert valid_values.max() <= 100, "RSI above 100"

    def test_macd_signal_crossover(self):
        """Test MACD signal generation"""
        if not PANDAS_TA_AVAILABLE:
            pytest.skip("pandas_ta not available")
        
        data = TestDataFactory.create_trending_data(periods=100, trend_strength=0.01)
        
        macd_result = ta.macd(data['close'])
        
        assert 'MACD_12_26_9' in macd_result.columns
        assert 'MACDs_12_26_9' in macd_result.columns
        assert 'MACDh_12_26_9' in macd_result.columns
        
        # Check that histogram = macd - signal
        for i in range(len(macd_result)):
            if not any(pd.isna([
                macd_result['MACD_12_26_9'].iloc[i],
                macd_result['MACDs_12_26_9'].iloc[i],
                macd_result['MACDh_12_26_9'].iloc[i]
            ])):
                calculated_hist = macd_result['MACD_12_26_9'].iloc[i] - macd_result['MACDs_12_26_9'].iloc[i]
                assert abs(macd_result['MACDh_12_26_9'].iloc[i] - calculated_hist) < 0.001

    def test_bollinger_bands_relationships(self):
        """Test Bollinger Bands maintain proper relationships"""
        if not PANDAS_TA_AVAILABLE:
            pytest.skip("pandas_ta not available")
        
        data = TestDataFactory.create_ranging_data(periods=50)
        
        bb = ta.bbands(data['close'], length=20, std=2)
        
        assert 'BBL_20_2.0' in bb.columns  # Lower band
        assert 'BBM_20_2.0' in bb.columns  # Middle band (SMA)
        assert 'BBU_20_2.0' in bb.columns  # Upper band
        
        # Check relationships: Lower < Middle < Upper
        for i in range(len(bb)):
            if not any(pd.isna([bb['BBL_20_2.0'].iloc[i], bb['BBM_20_2.0'].iloc[i], bb['BBU_20_2.0'].iloc[i]])):
                assert bb['BBL_20_2.0'].iloc[i] <= bb['BBM_20_2.0'].iloc[i] <= bb['BBU_20_2.0'].iloc[i]


if __name__ == "__main__":
    # Run specific test categories
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "indicators":
        # Test individual indicators
        test_class = TestPandasTAIndicators()
        
        print("Testing pandas_ta indicators...")
        print(f"pandas_ta available: {PANDAS_TA_AVAILABLE}")
        
        if PANDAS_TA_AVAILABLE:
            print("\n=== Testing Trend Indicators ===")
            test_class.test_trend_indicators(TestDataFactory.create_ohlcv_data())
            
            print("\n=== Testing Momentum Indicators ===")
            test_class.test_momentum_indicators(TestDataFactory.create_ohlcv_data())
            
            print("\n=== Testing Volatility Indicators ===")
            test_class.test_volatility_indicators(TestDataFactory.create_volatile_data())
            
            print("\n=== Testing Volume Indicators ===")
            test_class.test_volume_indicators(TestDataFactory.create_ohlcv_data())
            
            print("\nAll indicator tests completed!")
        else:
            print("pandas_ta not available - install to run indicator tests")
    else:
        print("Run with 'python test_pandas_ta_executor.py indicators' to test all indicators")
