"""
Signal Processing Indicators

Advanced peak detection and signal processing using scipy.signal library.

Features:
- Prominence-based peak detection
- Distance-filtered peak detection
- Peak width calculation
- Savitzky-Golay smoothing
- Hilbert transform for cycle analysis

Library: scipy.signal (already installed)
"""
import logging

import numpy as np
import pandas as pd
from scipy import signal

from app.services.indicator_registry import IndicatorCategory, register_indicator

logger = logging.getLogger(__name__)


@register_indicator(
    name="significant_peaks",
    category=IndicatorCategory.SIGNAL_PROCESSING,
    library="scipy.signal",
    description="Find significant peaks using prominence filter - identifies major swing highs",
    parameters={"prominence": 0.02, "distance": 5, "price_col": "high"},
    output_type="series"
)
def significant_peaks(
    df: pd.DataFrame,
    prominence: float = 0.02,
    distance: int = 5,
    price_col: str = "high",
    **kwargs
) -> pd.Series:
    """
    Find significant peaks using scipy's find_peaks with prominence filter.

    More robust than simple peak detection - focuses on prominent swings.

    Args:
        df: DataFrame with OHLCV data
        prominence: Minimum height difference from surrounding valleys (2% default)
        distance: Minimum bars between peaks
        price_col: Column to analyze (default: 'high')

    Returns:
        Series with peak prices (NaN for non-peak points)
    """
    try:
        prices = df[price_col].values
        mean_price = np.mean(prices)

        # Find peaks with prominence and distance filters
        peaks, properties = signal.find_peaks(
            prices,
            prominence=prominence * mean_price,
            distance=distance
        )

        # Create result series
        result = pd.Series(np.nan, index=df.index)
        result.iloc[peaks] = prices[peaks]

        return result

    except Exception as e:
        logger.exception(f"Error finding significant peaks: {e}")
        return pd.Series(np.nan, index=df.index)


@register_indicator(
    name="significant_valleys",
    category=IndicatorCategory.SIGNAL_PROCESSING,
    library="scipy.signal",
    description="Find significant valleys/troughs using prominence filter - identifies major swing lows",
    parameters={"prominence": 0.02, "distance": 5, "price_col": "low"},
    output_type="series"
)
def significant_valleys(
    df: pd.DataFrame,
    prominence: float = 0.02,
    distance: int = 5,
    price_col: str = "low",
    **kwargs
) -> pd.Series:
    """
    Find significant valleys (troughs) using scipy's find_peaks on inverted data.

    Args:
        df: DataFrame with OHLCV data
        prominence: Minimum depth from surrounding peaks (2% default)
        distance: Minimum bars between valleys
        price_col: Column to analyze (default: 'low')

    Returns:
        Series with valley prices (NaN for non-valley points)
    """
    try:
        prices = df[price_col].values
        mean_price = np.mean(prices)

        # Find valleys by inverting the signal
        valleys, properties = signal.find_peaks(
            -prices,
            prominence=prominence * mean_price,
            distance=distance
        )

        # Create result series
        result = pd.Series(np.nan, index=df.index)
        result.iloc[valleys] = prices[valleys]

        return result

    except Exception as e:
        logger.exception(f"Error finding significant valleys: {e}")
        return pd.Series(np.nan, index=df.index)


@register_indicator(
    name="peak_prominence",
    category=IndicatorCategory.SIGNAL_PROCESSING,
    library="scipy.signal",
    description="Calculate prominence (significance) of each peak - measures how much peak stands out",
    parameters={"price_col": "high"},
    output_type="series"
)
def peak_prominence(
    df: pd.DataFrame,
    price_col: str = "high",
    **kwargs
) -> pd.Series:
    """
    Calculate prominence values for all peaks.

    Prominence measures how much a peak stands out from surrounding valleys.
    Higher prominence = more significant peak.

    Args:
        df: DataFrame with OHLCV data
        price_col: Column to analyze

    Returns:
        Series with prominence values (0 for non-peaks)
    """
    try:
        prices = df[price_col].values

        # Find all peaks
        peaks, _ = signal.find_peaks(prices)

        if len(peaks) == 0:
            return pd.Series(0.0, index=df.index)

        # Calculate prominence
        prominences = signal.peak_prominences(prices, peaks)[0]

        # Create result series
        result = pd.Series(0.0, index=df.index)
        result.iloc[peaks] = prominences

        return result

    except Exception as e:
        logger.exception(f"Error calculating peak prominence: {e}")
        return pd.Series(0.0, index=df.index)


@register_indicator(
    name="peak_width",
    category=IndicatorCategory.SIGNAL_PROCESSING,
    library="scipy.signal",
    description="Calculate width of peaks - identifies accumulation/distribution zones",
    parameters={"price_col": "high", "rel_height": 0.5},
    output_type="series"
)
def peak_width(
    df: pd.DataFrame,
    price_col: str = "high",
    rel_height: float = 0.5,
    **kwargs
) -> pd.Series:
    """
    Calculate width of peaks at relative height.

    Wide peaks indicate accumulation/distribution zones.
    Narrow peaks indicate sharp reversals.

    Args:
        df: DataFrame with OHLCV data
        price_col: Column to analyze
        rel_height: Relative height for width measurement (0.5 = half height)

    Returns:
        Series with peak widths in bars (0 for non-peaks)
    """
    try:
        prices = df[price_col].values

        # Find all peaks
        peaks, _ = signal.find_peaks(prices)

        if len(peaks) == 0:
            return pd.Series(0.0, index=df.index)

        # Calculate widths
        widths = signal.peak_widths(prices, peaks, rel_height=rel_height)[0]

        # Create result series
        result = pd.Series(0.0, index=df.index)
        result.iloc[peaks] = widths

        return result

    except Exception as e:
        logger.exception(f"Error calculating peak width: {e}")
        return pd.Series(0.0, index=df.index)


@register_indicator(
    name="savgol_smooth",
    category=IndicatorCategory.SIGNAL_PROCESSING,
    library="scipy.signal",
    description="Savitzky-Golay smoothing - better than SMA, preserves peaks while removing noise",
    parameters={"window_length": 11, "polyorder": 3, "price_col": "close"}
)
def savgol_smooth(
    df: pd.DataFrame,
    window_length: int = 11,
    polyorder: int = 3,
    price_col: str = "close",
    **kwargs
) -> pd.Series:
    """
    Smooth price data using Savitzky-Golay filter.

    Better than simple moving average - preserves peaks while removing noise.
    Uses polynomial fitting in sliding window.

    Args:
        df: DataFrame with OHLCV data
        window_length: Window size (must be odd, default 11)
        polyorder: Polynomial order (default 3)
        price_col: Column to smooth

    Returns:
        Series with smoothed prices
    """
    try:
        prices = df[price_col].values

        # Ensure window_length is odd
        if window_length % 2 == 0:
            window_length += 1

        # Ensure window_length > polyorder
        if window_length <= polyorder:
            window_length = polyorder + 2
            if window_length % 2 == 0:
                window_length += 1

        # Apply Savitzky-Golay filter
        smoothed = signal.savgol_filter(prices, window_length, polyorder)

        return pd.Series(smoothed, index=df.index)

    except Exception as e:
        logger.exception(f"Error applying Savitzky-Golay filter: {e}")
        return df[price_col].copy()


@register_indicator(
    name="hilbert_envelope",
    category=IndicatorCategory.SIGNAL_PROCESSING,
    library="scipy.signal",
    description="Hilbert transform envelope - identifies cycle bounds and trend strength",
    parameters={"price_col": "close"}
)
def hilbert_envelope(
    df: pd.DataFrame,
    price_col: str = "close",
    **kwargs
) -> pd.Series:
    """
    Calculate Hilbert transform envelope.

    The envelope represents the bounds of oscillations in the price.
    Useful for cycle analysis and identifying overbought/oversold conditions.

    Args:
        df: DataFrame with OHLCV data
        price_col: Column to analyze

    Returns:
        Series with envelope values
    """
    try:
        prices = df[price_col].values

        # Remove trend (detrend)
        detrended = signal.detrend(prices)

        # Calculate Hilbert transform
        analytic_signal = signal.hilbert(detrended)

        # Calculate envelope (amplitude)
        envelope = np.abs(analytic_signal)

        return pd.Series(envelope, index=df.index)

    except Exception as e:
        logger.exception(f"Error calculating Hilbert envelope: {e}")
        return pd.Series(0.0, index=df.index)


@register_indicator(
    name="hilbert_phase",
    category=IndicatorCategory.SIGNAL_PROCESSING,
    library="scipy.signal",
    description="Hilbert transform phase - identifies cycle position (useful for timing entries)",
    parameters={"price_col": "close"}
)
def hilbert_phase(
    df: pd.DataFrame,
    price_col: str = "close",
    **kwargs
) -> pd.Series:
    """
    Calculate Hilbert transform instantaneous phase.

    Phase indicates where in the cycle the price currently is.
    Useful for timing entries at cycle bottoms/tops.

    Args:
        df: DataFrame with OHLCV data
        price_col: Column to analyze

    Returns:
        Series with phase values (in radians, -π to π)
    """
    try:
        prices = df[price_col].values

        # Remove trend
        detrended = signal.detrend(prices)

        # Calculate Hilbert transform
        analytic_signal = signal.hilbert(detrended)

        # Calculate instantaneous phase
        phase = np.angle(analytic_signal)

        return pd.Series(phase, index=df.index)

    except Exception as e:
        logger.exception(f"Error calculating Hilbert phase: {e}")
        return pd.Series(0.0, index=df.index)


@register_indicator(
    name="peaks_with_metadata",
    category=IndicatorCategory.SIGNAL_PROCESSING,
    library="scipy.signal",
    description="Find peaks with complete metadata (prominence, width, height)",
    parameters={"prominence": 0.02, "distance": 5, "price_col": "high"},
    output_type="dataframe"
)
def peaks_with_metadata(
    df: pd.DataFrame,
    prominence: float = 0.02,
    distance: int = 5,
    price_col: str = "high",
    **kwargs
) -> pd.DataFrame:
    """
    Find peaks with complete metadata including prominence, width, and height.

    Provides comprehensive peak analysis for advanced strategies.

    Args:
        df: DataFrame with OHLCV data
        prominence: Minimum prominence
        distance: Minimum distance between peaks
        price_col: Column to analyze

    Returns:
        DataFrame with columns: index, price, prominence, width, left_base, right_base
    """
    try:
        prices = df[price_col].values
        mean_price = np.mean(prices)

        # Find peaks with all properties
        peaks, properties = signal.find_peaks(
            prices,
            prominence=prominence * mean_price,
            distance=distance,
            width=1
        )

        if len(peaks) == 0:
            return pd.DataFrame(columns=['index', 'price', 'prominence', 'width', 'left_base', 'right_base'])

        # Calculate additional properties
        prominences = signal.peak_prominences(prices, peaks)[0]
        widths, width_heights, left_ips, right_ips = signal.peak_widths(prices, peaks, rel_height=0.5)

        # Create result DataFrame
        return pd.DataFrame({
            'index': peaks,
            'timestamp': [df.index[i] for i in peaks],
            'price': prices[peaks],
            'prominence': prominences,
            'width': widths,
            'left_base': properties['left_bases'],
            'right_base': properties['right_bases']
        })


    except Exception as e:
        logger.exception(f"Error finding peaks with metadata: {e}")
        return pd.DataFrame(columns=['index', 'price', 'prominence', 'width', 'left_base', 'right_base'])
