"""Tests for custom indicators"""
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from app.services.custom_indicators import CustomIndicators, IndicatorUtils


class TestCustomIndicators:

    def create_sample_data(self, periods=100):
        """Create sample OHLCV data for testing"""
        dates = pd.date_range(start='2024-01-01', periods=periods, freq='1min')

        # Generate realistic price movements
        base_price = 100
        prices = []

        for i in range(periods):
            # Add some trend and noise
            trend = i * 0.01
            noise = np.random.normal(0, 0.5)
            price = base_price + trend + noise
            prices.append(price)

        df = pd.DataFrame({
            'high': [p + np.random.uniform(0, 0.5) for p in prices],
            'low': [p - np.random.uniform(0, 0.5) for p in prices],
            'close': prices,
            'volume': np.random.randint(1000, 5000, periods)
        }, index=dates)

        df['open'] = df['close'].shift(1).fillna(df['close'].iloc[0])

        return df

    def test_anchored_vwap(self):
        """Test anchored VWAP calculation"""
        # Create sample data
        df = self.create_sample_data(100)

        # Calculate anchored VWAP from middle point
        anchor = df.index[50]
        result = CustomIndicators.anchored_vwap(df, anchor.isoformat())

        # Verify results
        assert len(result) == 100
        assert pd.isna(result[:50]).all()  # No values before anchor
        assert not pd.isna(result[50:]).any()  # All values after anchor

        # Verify VWAP is between high and low
        for i in range(50, 100):
            if not pd.isna(result.iloc[i]):
                assert df['low'].iloc[i] <= result.iloc[i] <= df['high'].iloc[i]

    def test_anchored_vwap_with_nearest_timestamp(self):
        """Test anchored VWAP with non-exact timestamp"""
        df = self.create_sample_data(100)

        # Use timestamp between actual data points
        anchor = df.index[50] + timedelta(seconds=30)
        result = CustomIndicators.anchored_vwap(df, anchor.isoformat())

        # Should still work by finding nearest timestamp
        assert not result.isna().all()

    def test_swing_high_detection(self):
        """Test swing high detection"""
        # Create data with known swing high
        prices = [100, 101, 102, 103, 102, 101, 100]  # Peak at index 3
        df = pd.DataFrame({
            'high': prices
        })

        result = CustomIndicators.swing_high(df, left_bars=2, right_bars=2)

        # Should detect swing high at index 3
        assert pd.isna(result[0])
        assert pd.isna(result[1])
        assert pd.isna(result[2])
        assert result[3] == 103  # Swing high
        assert pd.isna(result[4])
        assert pd.isna(result[5])
        assert pd.isna(result[6])

    def test_swing_low_detection(self):
        """Test swing low detection"""
        # Create data with known swing low
        prices = [103, 102, 101, 100, 101, 102, 103]  # Valley at index 3
        df = pd.DataFrame({
            'low': prices
        })

        result = CustomIndicators.swing_low(df, left_bars=2, right_bars=2)

        # Should detect swing low at index 3
        assert result[3] == 100  # Swing low
        assert pd.isna(result[0])
        assert pd.isna(result[4])

    def test_combined_premium(self):
        """Test combined premium calculation"""
        df = pd.DataFrame({
            'call_price': [10, 12, 15, 14, 13],
            'put_price': [8, 9, 11, 10, 9]
        })

        result = CustomIndicators.combined_premium(df)

        assert len(result) == 5
        assert result[0] == 18  # 10 + 8
        assert result[2] == 26  # 15 + 11

    def test_premium_ratio(self):
        """Test premium ratio calculation"""
        df = pd.DataFrame({
            'call_price': [10, 12, 15, 0, 13],
            'put_price': [5, 6, 5, 0, 10]
        })

        result = CustomIndicators.premium_ratio(df)

        assert len(result) == 5
        assert result[0] == 2.0  # 10/5
        assert result[1] == 2.0  # 12/6
        assert result[2] == 3.0  # 15/5
        assert pd.isna(result[3])  # Division by zero
        assert result[4] == 1.3  # 13/10


class TestIndicatorUtils:

    def test_find_swing_highs(self):
        """Test finding all swing highs"""
        # Create data with multiple swing highs
        prices = [100, 102, 101, 105, 103, 104, 102, 106, 104]
        df = pd.DataFrame({
            'high': prices
        }, index=pd.date_range('2024-01-01', periods=len(prices), freq='1min'))

        swings = IndicatorUtils.find_swing_highs(df, window=4)

        assert len(swings) > 0
        assert all(s['type'] == 'swing_high' for s in swings)
        assert all('timestamp' in s and 'price' in s for s in swings)

    def test_find_recent_swing_high(self):
        """Test finding most recent swing high"""
        df = pd.DataFrame({
            'high': [100, 102, 101, 105, 103, 104, 102, 106, 104]
        }, index=pd.date_range('2024-01-01', periods=9, freq='1min'))

        recent_swing = IndicatorUtils.find_recent_swing_high(df, lookback_periods=20)

        assert recent_swing is not None
        assert recent_swing['type'] == 'swing_high'
        assert 'timestamp' in recent_swing
        assert 'price' in recent_swing

    def test_calculate_multiple_anchored_vwaps(self):
        """Test calculating multiple anchored VWAPs"""
        df = pd.DataFrame({
            'high': [101, 102, 103, 104, 105],
            'low': [99, 100, 101, 102, 103],
            'close': [100, 101, 102, 103, 104],
            'volume': [1000, 1100, 1200, 1300, 1400]
        }, index=pd.date_range('2024-01-01', periods=5, freq='1H'))

        anchor_points = [
            df.index[1].isoformat(),
            df.index[3].isoformat()
        ]

        vwaps = IndicatorUtils.calculate_multiple_anchored_vwaps(df, anchor_points)

        assert len(vwaps) == 2
        assert 'avwap_1' in vwaps
        assert 'avwap_2' in vwaps
        assert len(vwaps['avwap_1']) == 5
        assert len(vwaps['avwap_2']) == 5


@pytest.mark.asyncio
async def test_custom_indicators_registration():
    """Test that custom indicators can be registered with pandas_ta"""
    from app.services.custom_indicators import register_custom_indicators

    # Register indicators
    register_custom_indicators()

    # Try to use them with pandas_ta
    import pandas_ta as ta

    # Check if indicators are registered
    assert hasattr(ta, 'anchored_vwap') or 'anchored_vwap' in ta.CUSTOM_TA
    assert hasattr(ta, 'swing_high') or 'swing_high' in ta.CUSTOM_TA
    assert hasattr(ta, 'swing_low') or 'swing_low' in ta.CUSTOM_TA
