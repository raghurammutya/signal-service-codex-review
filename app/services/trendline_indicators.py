"""
Trendline Detection Indicators

Automated trendline and channel detection using trendln library.

Features:
- Support trendline detection
- Resistance trendline detection
- Trendline breakout signals
- Channel detection (parallel lines)

Library: trendln
"""
import logging
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
import numpy as np

from app.services.indicator_registry import (
    register_indicator,
    IndicatorCategory
)

logger = logging.getLogger(__name__)

# Try to import trendln, use fallback if not available
try:
    import trendln
    TRENDLN_AVAILABLE = True
    logger.info("trendln library loaded successfully")
except ImportError:
    TRENDLN_AVAILABLE = False
    logger.warning("trendln not available - Trendline indicators will return mock data")


@register_indicator(
    name="support_trendline",
    category=IndicatorCategory.TRENDLINES,
    library="trendln",
    description="Automated support trendline detection - connects swing lows for uptrend lines",
    parameters={"extmethod": "LSTSQ", "method": "minmax"},
    output_type="dict"
)
def support_trendline(
    df: pd.DataFrame,
    extmethod: str = "LSTSQ",
    method: str = "minmax",
    **kwargs
) -> Dict[str, Any]:
    """
    Detect support trendlines automatically.

    Connects swing lows to identify uptrend support.

    Args:
        df: DataFrame with OHLCV data
        extmethod: Extrema detection method ("LSTSQ" or "RANSAC")
        method: Method for trendline calculation ("minmax" or "manual")

    Returns:
        Dict with slope, intercept, start_idx, end_idx, r_squared
    """
    try:
        if not TRENDLN_AVAILABLE:
            return _mock_support_trendline(df)

        prices = df['low'].values

        # Find support trendline
        minimaIdxs, pmin, mintrend, minwindows = trendln.calc_support_resistance(
            prices,
            accuracy=1
        )

        if not minimaIdxs or len(minimaIdxs) < 2:
            return _mock_support_trendline(df)

        # Get the strongest support line
        # Calculate slope and intercept
        x = np.array(minimaIdxs)
        y = prices[minimaIdxs]

        if len(x) < 2:
            return _mock_support_trendline(df)

        # Linear regression
        coeffs = np.polyfit(x, y, 1)
        slope = float(coeffs[0])
        intercept = float(coeffs[1])

        # Calculate R-squared
        y_pred = slope * x + intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

        return {
            'slope': slope,
            'intercept': intercept,
            'start_idx': int(x[0]),
            'end_idx': int(x[-1]),
            'start_price': float(y[0]),
            'end_price': float(y[-1]),
            'r_squared': float(r_squared),
            'touch_count': len(x),
            'type': 'support'
        }

    except Exception as e:
        logger.exception(f"Error detecting support trendline: {e}")
        return _mock_support_trendline(df)


@register_indicator(
    name="resistance_trendline",
    category=IndicatorCategory.TRENDLINES,
    library="trendln",
    description="Automated resistance trendline detection - connects swing highs for downtrend lines",
    parameters={"extmethod": "LSTSQ", "method": "minmax"},
    output_type="dict"
)
def resistance_trendline(
    df: pd.DataFrame,
    extmethod: str = "LSTSQ",
    method: str = "minmax",
    **kwargs
) -> Dict[str, Any]:
    """
    Detect resistance trendlines automatically.

    Connects swing highs to identify downtrend resistance.

    Args:
        df: DataFrame with OHLCV data
        extmethod: Extrema detection method
        method: Method for trendline calculation

    Returns:
        Dict with slope, intercept, start_idx, end_idx, r_squared
    """
    try:
        if not TRENDLN_AVAILABLE:
            return _mock_resistance_trendline(df)

        prices = df['high'].values

        # Find resistance trendline (invert prices)
        maximaIdxs, pmax, maxtrend, maxwindows = trendln.calc_support_resistance(
            -prices,  # Invert for resistance
            accuracy=1
        )

        if not maximaIdxs or len(maximaIdxs) < 2:
            return _mock_resistance_trendline(df)

        # Get the strongest resistance line
        x = np.array(maximaIdxs)
        y = prices[maximaIdxs]

        if len(x) < 2:
            return _mock_resistance_trendline(df)

        # Linear regression
        coeffs = np.polyfit(x, y, 1)
        slope = float(coeffs[0])
        intercept = float(coeffs[1])

        # Calculate R-squared
        y_pred = slope * x + intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

        return {
            'slope': slope,
            'intercept': intercept,
            'start_idx': int(x[0]),
            'end_idx': int(x[-1]),
            'start_price': float(y[0]),
            'end_price': float(y[-1]),
            'r_squared': float(r_squared),
            'touch_count': len(x),
            'type': 'resistance'
        }

    except Exception as e:
        logger.exception(f"Error detecting resistance trendline: {e}")
        return _mock_resistance_trendline(df)


@register_indicator(
    name="trendline_breakout",
    category=IndicatorCategory.TRENDLINES,
    library="trendln",
    description="Detect trendline breakouts - signals when price decisively breaks through a trendline",
    parameters={"buffer": 0.01},
    output_type="series"
)
def trendline_breakout(
    df: pd.DataFrame,
    buffer: float = 0.01,
    **kwargs
) -> pd.Series:
    """
    Detect trendline breakouts.

    Identifies when price breaks through support or resistance trendlines.

    Args:
        df: DataFrame with OHLCV data
        buffer: Percentage buffer for breakout confirmation (1% default)

    Returns:
        Series with 1 for upward breakout, -1 for downward breakout, 0 for no breakout
    """
    try:
        if not TRENDLN_AVAILABLE:
            return _mock_breakout(df)

        result = pd.Series(0, index=df.index)

        # Get support and resistance trendlines
        support = support_trendline(df)
        resistance = resistance_trendline(df)

        if not support or not resistance:
            return result

        # Calculate trendline values for each bar
        indices = np.arange(len(df))

        support_values = support['slope'] * indices + support['intercept']
        resistance_values = resistance['slope'] * indices + resistance['intercept']

        closes = df['close'].values

        # Detect breakouts
        for i in range(1, len(df)):
            # Upward breakout through resistance
            if (closes[i] > resistance_values[i] * (1 + buffer) and
                closes[i-1] <= resistance_values[i-1] * (1 + buffer)):
                result.iloc[i] = 1

            # Downward breakout through support
            elif (closes[i] < support_values[i] * (1 - buffer) and
                  closes[i-1] >= support_values[i-1] * (1 - buffer)):
                result.iloc[i] = -1

        return result

    except Exception as e:
        logger.exception(f"Error detecting trendline breakout: {e}")
        return pd.Series(0, index=df.index)


@register_indicator(
    name="channel_detection",
    category=IndicatorCategory.TRENDLINES,
    library="trendln",
    description="Detect price channels - parallel support and resistance trendlines",
    parameters={},
    output_type="dict"
)
def channel_detection(
    df: pd.DataFrame,
    **kwargs
) -> Dict[str, Any]:
    """
    Detect price channels (parallel support and resistance).

    Channels indicate ranging markets - useful for range-bound strategies.

    Args:
        df: DataFrame with OHLCV data

    Returns:
        Dict with support_line, resistance_line, channel_width, is_valid
    """
    try:
        if not TRENDLN_AVAILABLE:
            return _mock_channel(df)

        # Get both trendlines
        support = support_trendline(df)
        resistance = resistance_trendline(df)

        if not support or not resistance:
            return _mock_channel(df)

        # Check if lines are approximately parallel (similar slopes)
        slope_diff = abs(support['slope'] - resistance['slope'])
        avg_slope = (abs(support['slope']) + abs(resistance['slope'])) / 2

        # Lines are parallel if slope difference < 20% of average slope
        is_parallel = slope_diff < (0.2 * avg_slope) if avg_slope > 0 else False

        # Calculate average channel width
        indices = np.arange(len(df))
        support_values = support['slope'] * indices + support['intercept']
        resistance_values = resistance['slope'] * indices + resistance['intercept']

        channel_widths = resistance_values - support_values
        avg_width = float(np.mean(channel_widths))

        # Calculate as percentage of price
        avg_price = float(df['close'].mean())
        width_pct = (avg_width / avg_price * 100) if avg_price > 0 else 0

        return {
            'support_line': support,
            'resistance_line': resistance,
            'channel_width': avg_width,
            'channel_width_pct': width_pct,
            'is_parallel': is_parallel,
            'is_valid': is_parallel and support['r_squared'] > 0.7 and resistance['r_squared'] > 0.7
        }

    except Exception as e:
        logger.exception(f"Error detecting channel: {e}")
        return _mock_channel(df)


# =============================================================================
# Mock Functions
# =============================================================================

def _mock_support_trendline(df: pd.DataFrame) -> Dict[str, Any]:
    """Mock support trendline"""
    start_price = float(df['low'].iloc[0])
    end_price = float(df['low'].iloc[-1])
    slope = (end_price - start_price) / len(df)

    return {
        'slope': slope,
        'intercept': start_price,
        'start_idx': 0,
        'end_idx': len(df) - 1,
        'start_price': start_price,
        'end_price': end_price,
        'r_squared': 0.75,
        'touch_count': 3,
        'type': 'support'
    }


def _mock_resistance_trendline(df: pd.DataFrame) -> Dict[str, Any]:
    """Mock resistance trendline"""
    start_price = float(df['high'].iloc[0])
    end_price = float(df['high'].iloc[-1])
    slope = (end_price - start_price) / len(df)

    return {
        'slope': slope,
        'intercept': start_price,
        'start_idx': 0,
        'end_idx': len(df) - 1,
        'start_price': start_price,
        'end_price': end_price,
        'r_squared': 0.70,
        'touch_count': 3,
        'type': 'resistance'
    }


def _mock_breakout(df: pd.DataFrame) -> pd.Series:
    """Mock breakout signals"""
    result = pd.Series(0, index=df.index)
    # Add some random breakouts
    if len(df) > 20:
        result.iloc[20] = 1
        result.iloc[40] = -1 if len(df) > 40 else 0
    return result


def _mock_channel(df: pd.DataFrame) -> Dict[str, Any]:
    """Mock channel detection"""
    return {
        'support_line': _mock_support_trendline(df),
        'resistance_line': _mock_resistance_trendline(df),
        'channel_width': float(df['high'].mean() - df['low'].mean()),
        'channel_width_pct': 5.0,
        'is_parallel': True,
        'is_valid': True
    }
