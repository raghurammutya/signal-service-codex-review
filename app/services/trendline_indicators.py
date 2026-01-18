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
<<<<<<< HEAD
    logger.error("trendln not available - Trendline indicators will fail fast")
=======
    logger.warning("trendln not available - Trendline indicators will raise ComputationError")
>>>>>>> compliance-violations-fixed


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
<<<<<<< HEAD
            raise ImportError("trendln library required for support trendline calculation. No mock data allowed in production.")
=======
            from app.errors import ComputationError
            raise ComputationError("trendln library not available - support trendline detection requires trendln library")
>>>>>>> compliance-violations-fixed

        prices = df['low'].values

        # Find support trendline
        minimaIdxs, pmin, mintrend, minwindows = trendln.calc_support_resistance(
            prices,
            accuracy=1
        )

        if not minimaIdxs or len(minimaIdxs) < 2:
<<<<<<< HEAD
            raise ValueError("Insufficient data for support trendline calculation. No fallback allowed in production.")
=======
            from app.errors import ComputationError
            raise ComputationError("Insufficient swing lows found for support trendline detection")
>>>>>>> compliance-violations-fixed

        # Get the strongest support line
        # Calculate slope and intercept
        x = np.array(minimaIdxs)
        y = prices[minimaIdxs]

        if len(x) < 2:
<<<<<<< HEAD
            raise ValueError("Insufficient data for support trendline calculation. No fallback allowed in production.")
=======
            from app.errors import ComputationError
            raise ComputationError("Insufficient data points for support trendline linear regression")
>>>>>>> compliance-violations-fixed

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
        from app.errors import ComputationError
        logger.exception(f"Error detecting support trendline: {e}")
<<<<<<< HEAD
        raise ValueError("Insufficient data for support trendline calculation. No fallback allowed in production.")
=======
        raise ComputationError(f"Failed to detect support trendline: {e}") from e
>>>>>>> compliance-violations-fixed


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
<<<<<<< HEAD
            raise ValueError("Insufficient data for resistance trendline calculation. No fallback allowed in production.")
=======
            from app.errors import ComputationError
            raise ComputationError("trendln library not available - resistance trendline detection requires trendln library")
>>>>>>> compliance-violations-fixed

        prices = df['high'].values

        # Find resistance trendline (invert prices)
        maximaIdxs, pmax, maxtrend, maxwindows = trendln.calc_support_resistance(
            -prices,  # Invert for resistance
            accuracy=1
        )

        if not maximaIdxs or len(maximaIdxs) < 2:
<<<<<<< HEAD
            raise ValueError("Insufficient data for resistance trendline calculation. No fallback allowed in production.")
=======
            from app.errors import ComputationError
            raise ComputationError("Insufficient swing highs found for resistance trendline detection")
>>>>>>> compliance-violations-fixed

        # Get the strongest resistance line
        x = np.array(maximaIdxs)
        y = prices[maximaIdxs]

        if len(x) < 2:
<<<<<<< HEAD
            raise ValueError("Insufficient data for resistance trendline calculation. No fallback allowed in production.")
=======
            from app.errors import ComputationError
            raise ComputationError("Insufficient data points for resistance trendline linear regression")
>>>>>>> compliance-violations-fixed

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
        from app.errors import ComputationError
        logger.exception(f"Error detecting resistance trendline: {e}")
<<<<<<< HEAD
        raise ValueError("Insufficient data for resistance trendline calculation. No fallback allowed in production.")
=======
        raise ComputationError(f"Failed to detect resistance trendline: {e}") from e
>>>>>>> compliance-violations-fixed


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
<<<<<<< HEAD
            raise ImportError("trendln library required for breakout detection. No mock data allowed in production.")
=======
            from app.errors import ComputationError
            raise ComputationError("trendln library not available - breakout detection requires trendln library")
>>>>>>> compliance-violations-fixed

        result = pd.Series(0, index=df.index)

        # Get support and resistance trendlines
        try:
            support = support_trendline(df)
            resistance = resistance_trendline(df)
        except Exception:
            # If trendline detection fails, we cannot detect breakouts
            from app.errors import ComputationError
            raise ComputationError("Failed to compute trendlines required for breakout detection")

        if not support or not resistance:
            from app.errors import ComputationError
            raise ComputationError("Could not establish valid support and resistance trendlines for breakout detection")

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
        from app.errors import ComputationError
        logger.exception(f"Error detecting trendline breakout: {e}")
        raise ComputationError(f"Failed to detect trendline breakout: {e}") from e


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
<<<<<<< HEAD
            raise ValueError("Channel detection failed: trendln library not available. No fallback allowed in production.")
=======
            from app.errors import ComputationError
            raise ComputationError("trendln library not available - channel detection requires trendln library")
>>>>>>> compliance-violations-fixed

        # Get both trendlines
        try:
            support = support_trendline(df)
            resistance = resistance_trendline(df)
        except Exception:
            # If trendline detection fails, we cannot detect channels
            from app.errors import ComputationError
            raise ComputationError("Failed to compute trendlines required for channel detection")

        if not support or not resistance:
<<<<<<< HEAD
            raise ValueError("Channel detection failed: unable to detect support or resistance trendlines. No fallback allowed in production.")
=======
            from app.errors import ComputationError
            raise ComputationError("Could not establish valid support and resistance trendlines for channel detection")
>>>>>>> compliance-violations-fixed

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
        from app.errors import ComputationError
        logger.exception(f"Error detecting channel: {e}")
<<<<<<< HEAD
        raise ValueError(f"Channel detection failed: {e}. No fallback allowed in production.")


=======
        raise ComputationError(f"Failed to detect channel: {e}") from e


# Note: Mock functions removed - production code must handle missing dependencies properly
# by raising ComputationError when trendln library is not available
>>>>>>> compliance-violations-fixed
