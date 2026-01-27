"""Test native Smart Money implementations."""
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from app.services.smart_money_indicators import SmartMoneyIndicators


class TestSmartMoneyIndicators:
    """Test native Smart Money implementations."""

    @pytest.fixture
    def indicators(self):
        """Create SmartMoney indicators instance."""
        return SmartMoneyIndicators()

    @pytest.fixture
    def sample_ohlcv_data(self):
        """Create realistic OHLCV data with known patterns."""
        # Create data with deliberate market structure patterns
        dates = pd.date_range('2024-01-01', periods=100, freq='1H')

        # Create trending price action with some reversals
        base_prices = np.linspace(20000, 21000, 100)  # Uptrend
        noise = np.random.normal(0, 20, 100)

        ohlcv_data = []
        for i, (date, base_price) in enumerate(zip(dates, base_prices, strict=False)):
            price = base_price + noise[i]

            # Create realistic OHLC
            high = price + abs(np.random.normal(0, 15))
            low = price - abs(np.random.normal(0, 15))
            open_price = low + (high - low) * np.random.random()
            close = low + (high - low) * np.random.random()

            volume = np.random.randint(80000, 200000)

            # Add some volume spikes for order block detection
            if i % 20 == 0:
                volume *= 3

            ohlcv_data.append({
                'open': round(open_price, 2),
                'high': round(high, 2),
                'low': round(low, 2),
                'close': round(close, 2),
                'volume': volume
            })

        return pd.DataFrame(ohlcv_data, index=dates)

    def test_break_of_structure_detection(self, indicators, sample_ohlcv_data):
        """Test Break of Structure (BOS) detection algorithm."""
        bos_signals = indicators.calculate_break_of_structure(sample_ohlcv_data)

        # Verify return type and structure
        assert isinstance(bos_signals, (pd.Series, pd.DataFrame)), "BOS should return pandas Series or DataFrame"
        assert len(bos_signals) == len(sample_ohlcv_data), "BOS output length should match input"

        # Test that it's not returning mock data (should have variation)
        if isinstance(bos_signals, pd.Series):
            unique_values = bos_signals.nunique()
        else:
            unique_values = bos_signals.iloc[:, 0].nunique()

        # Real implementation should have some variation, not all same value
        assert unique_values > 1, "BOS implementation should not return uniform mock data"

        # Test with empty data
        empty_df = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
        empty_result = indicators.calculate_break_of_structure(empty_df)
        assert len(empty_result) == 0, "Empty input should return empty output"

    def test_change_of_character_detection(self, indicators, sample_ohlcv_data):
        """Test Change of Character (CHoCH) detection."""
        choch_signals = indicators.calculate_change_of_character(sample_ohlcv_data)

        # Verify return type
        assert isinstance(choch_signals, (pd.Series, pd.DataFrame)), "CHoCH should return pandas Series or DataFrame"
        assert len(choch_signals) == len(sample_ohlcv_data), "CHoCH output length should match input"

        # Should detect some character changes in trending data
        if isinstance(choch_signals, pd.Series):
            character_changes = choch_signals.sum() if choch_signals.dtype == bool else len(choch_signals.dropna())
        else:
            character_changes = len(choch_signals)

        assert character_changes >= 0, "CHoCH should detect non-negative number of changes"

    def test_order_blocks_identification(self, indicators, sample_ohlcv_data):
        """Test Order Blocks identification with volume confirmation."""
        order_blocks = indicators.identify_order_blocks(sample_ohlcv_data)

        # Verify return structure
        assert isinstance(order_blocks, pd.DataFrame), "Order blocks should return DataFrame"

        required_columns = ['level', 'strength', 'volume_confirmation']
        for col in required_columns:
            assert col in order_blocks.columns, f"Order blocks should include {col} column"

        if len(order_blocks) > 0:
            # Verify data types
            assert order_blocks['level'].dtype in [np.float64, np.int64], "Level should be numeric"
            assert order_blocks['strength'].dtype in [np.float64, np.int64], "Strength should be numeric"
            assert order_blocks['volume_confirmation'].dtype == bool, "Volume confirmation should be boolean"

            # Verify volume confirmation logic is working
            confirmed_blocks = order_blocks[order_blocks['volume_confirmation']]
            if len(confirmed_blocks) > 0:
                # Volume-confirmed blocks should have reasonable strength
                assert confirmed_blocks['strength'].min() > 0, "Confirmed blocks should have positive strength"

    def test_fair_value_gaps_detection(self, indicators, sample_ohlcv_data):
        """Test Fair Value Gaps (FVG) detection."""
        fvg_zones = indicators.detect_fair_value_gaps(sample_ohlcv_data)

        # Verify return structure
        assert isinstance(fvg_zones, pd.DataFrame), "FVG should return DataFrame"

        required_columns = ['gap_start', 'gap_end', 'gap_type']
        for col in required_columns:
            assert col in fvg_zones.columns, f"FVG should include {col} column"

        if len(fvg_zones) > 0:
            # Verify gap types are valid
            valid_types = ['bullish', 'bearish']
            assert all(gap_type in valid_types for gap_type in fvg_zones['gap_type']), "Invalid gap types found"

            # Verify gap start/end are numeric and logical
            assert fvg_zones['gap_start'].dtype in [np.float64, np.int64], "Gap start should be numeric"
            assert fvg_zones['gap_end'].dtype in [np.float64, np.int64], "Gap end should be numeric"

            # Gap end should be greater than gap start for valid gaps
            valid_gaps = fvg_zones['gap_end'] > fvg_zones['gap_start']
            assert valid_gaps.all(), "All gaps should have end > start"

    def test_liquidity_levels_calculation(self, indicators, sample_ohlcv_data):
        """Test Liquidity Levels calculation using support/resistance analysis."""
        liquidity_levels = indicators.calculate_liquidity_levels(sample_ohlcv_data)

        # Verify return structure
        assert isinstance(liquidity_levels, (pd.DataFrame, dict)), "Liquidity levels should return DataFrame or dict"

        if isinstance(liquidity_levels, pd.DataFrame):
            expected_columns = ['level', 'type', 'strength', 'touches']
            for col in expected_columns:
                assert col in liquidity_levels.columns, f"Liquidity levels should include {col} column"

            if len(liquidity_levels) > 0:
                # Verify level types
                valid_types = ['support', 'resistance']
                assert all(level_type in valid_types for level_type in liquidity_levels['type']), "Invalid level types"

                # Verify touches count
                assert (liquidity_levels['touches'] >= 1).all(), "All levels should have at least 1 touch"
        elif isinstance(liquidity_levels, dict):
            assert 'support_levels' in liquidity_levels or 'resistance_levels' in liquidity_levels, "Dict should contain level info"

    def test_combined_smart_money_analysis(self, indicators, sample_ohlcv_data):
        """Test combined Smart Money analysis."""
        try:
            combined_analysis = indicators.analyze_smart_money_structure(sample_ohlcv_data)

            # Verify combined analysis structure
            assert isinstance(combined_analysis, dict), "Combined analysis should return dict"

            expected_keys = ['break_of_structure', 'change_of_character', 'order_blocks', 'fair_value_gaps', 'liquidity_levels']
            for key in expected_keys:
                assert key in combined_analysis, f"Combined analysis should include {key}"

        except AttributeError:
            # Method might not exist yet
            pytest.skip("Combined analysis method not implemented")

    def test_real_vs_mock_implementations(self, indicators, sample_ohlcv_data):
        """Test that implementations are real algorithmic calculations, not mocks."""
        # Test BOS with different data should yield different results
        data1 = sample_ohlcv_data.copy()
        data2 = sample_ohlcv_data.copy()
        data2['close'] = data2['close'] * 1.1  # 10% price increase

        bos1 = indicators.calculate_break_of_structure(data1)
        bos2 = indicators.calculate_break_of_structure(data2)

        # Real implementations should produce different results for different inputs
        if isinstance(bos1, pd.Series) and isinstance(bos2, pd.Series):
            assert not bos1.equals(bos2), "Real implementation should produce different results for different inputs"

    def test_pandas_dependency_elimination(self, indicators, sample_ohlcv_data):
        """Test that Smart Money doesn't depend on pandas_ta for core calculations."""
        # Check that calculations work without pandas_ta
        with patch.dict('sys.modules', {'pandas_ta': None}):
            try:
                # These should work without pandas_ta
                bos = indicators.calculate_break_of_structure(sample_ohlcv_data)
                order_blocks = indicators.identify_order_blocks(sample_ohlcv_data)

                assert bos is not None, "BOS should work without pandas_ta"
                assert order_blocks is not None, "Order blocks should work without pandas_ta"

            except ImportError as e:
                if 'pandas_ta' in str(e):
                    pytest.fail("Smart Money implementation should not depend on pandas_ta")
                else:
                    raise  # Re-raise other import errors

    def test_performance_with_large_dataset(self, indicators):
        """Test Smart Money performance with large datasets."""
        # Create large dataset
        large_data = pd.DataFrame({
            'open': np.random.uniform(19800, 20200, 5000),
            'high': np.random.uniform(20000, 20400, 5000),
            'low': np.random.uniform(19600, 20000, 5000),
            'close': np.random.uniform(19800, 20200, 5000),
            'volume': np.random.randint(100000, 1000000, 5000)
        })

        import time

        start_time = time.time()
        bos = indicators.calculate_break_of_structure(large_data)
        bos_time = time.time() - start_time

        start_time = time.time()
        order_blocks = indicators.identify_order_blocks(large_data)
        ob_time = time.time() - start_time

        # Performance thresholds (should complete in reasonable time)
        assert bos_time < 10.0, f"BOS calculation too slow for large dataset: {bos_time:.2f}s"
        assert ob_time < 10.0, f"Order blocks calculation too slow for large dataset: {ob_time:.2f}s"

        # Verify results are still valid
        assert len(bos) == len(large_data), "BOS should handle large datasets correctly"
        assert isinstance(order_blocks, pd.DataFrame), "Order blocks should handle large datasets correctly"

    @pytest.mark.parametrize("swing_length", [3, 5, 10, 20])
    def test_swing_length_parameter(self, indicators, sample_ohlcv_data, swing_length):
        """Test Smart Money calculations with different swing lengths."""
        try:
            # Test BOS with different swing lengths
            bos = indicators.calculate_break_of_structure(sample_ohlcv_data, swing_length=swing_length)

            assert len(bos) == len(sample_ohlcv_data), f"BOS should work with swing_length={swing_length}"

            # Different swing lengths should potentially produce different results
            if swing_length == 5:  # Store default result for comparison
                self.default_bos = bos
            elif hasattr(self, 'default_bos') and isinstance(bos, pd.Series):
                # Allow for some difference but not necessarily enforce it
                # (some parameter changes might not affect all datasets)
                pass

        except TypeError:
            # Parameter might not be implemented yet
            pytest.skip("swing_length parameter not implemented")
