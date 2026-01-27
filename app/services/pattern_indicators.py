"""
Pattern Recognition Indicators

Classic trading patterns and algorithms including:
- Bill Williams Fractals
- Pivot Points (Standard, Fibonacci, Camarilla, Woodie)
- Fibonacci Retracement & Extension
- ZigZag indicator
- Volume Profile
- Market Profile (TPO)

Library: Custom implementation (no external dependencies)
"""
import logging

import numpy as np
import pandas as pd

from app.services.indicator_registry import IndicatorCategory, register_indicator

logger = logging.getLogger(__name__)


@register_indicator(
    name="fractal_high",
    category=IndicatorCategory.PATTERN_RECOGNITION,
    library="custom",
    description="Bill Williams Fractals - identifies 5-bar pattern highs (stricter than basic swings)",
    parameters={}
)
def fractal_high(
    df: pd.DataFrame,
    **kwargs
) -> pd.Series:
    """
    Detect Bill Williams Fractal Highs.

    Fractal High: Middle bar higher than 2 bars on each side.
    More strict than basic swing detection - requires exactly 5 bars.

    Args:
        df: DataFrame with OHLCV data

    Returns:
        Series with fractal high prices (NaN for non-fractals)
    """
    try:
        result = pd.Series(np.nan, index=df.index)
        highs = df['high'].values

        for i in range(2, len(highs) - 2):
            if (highs[i] > highs[i-1] and
                highs[i] > highs[i-2] and
                highs[i] > highs[i+1] and
                highs[i] > highs[i+2]):
                result.iloc[i] = highs[i]

        return result

    except Exception as e:
        logger.exception(f"Error detecting fractal highs: {e}")
        return pd.Series(np.nan, index=df.index)


@register_indicator(
    name="fractal_low",
    category=IndicatorCategory.PATTERN_RECOGNITION,
    library="custom",
    description="Bill Williams Fractals - identifies 5-bar pattern lows",
    parameters={}
)
def fractal_low(
    df: pd.DataFrame,
    **kwargs
) -> pd.Series:
    """
    Detect Bill Williams Fractal Lows.

    Fractal Low: Middle bar lower than 2 bars on each side.

    Args:
        df: DataFrame with OHLCV data

    Returns:
        Series with fractal low prices (NaN for non-fractals)
    """
    try:
        result = pd.Series(np.nan, index=df.index)
        lows = df['low'].values

        for i in range(2, len(lows) - 2):
            if (lows[i] < lows[i-1] and
                lows[i] < lows[i-2] and
                lows[i] < lows[i+1] and
                lows[i] < lows[i+2]):
                result.iloc[i] = lows[i]

        return result

    except Exception as e:
        logger.exception(f"Error detecting fractal lows: {e}")
        return pd.Series(np.nan, index=df.index)


@register_indicator(
    name="pivot_points",
    category=IndicatorCategory.PATTERN_RECOGNITION,
    library="custom",
    description="Pivot Points - intraday support/resistance levels (standard, fibonacci, camarilla, woodie)",
    parameters={"method": "standard"},
    output_type="dict"
)
def pivot_points(
    df: pd.DataFrame,
    method: str = "standard",
    **kwargs
) -> dict[str, float]:
    """
    Calculate pivot points for intraday trading.

    Methods:
    - standard: Classic pivot points
    - fibonacci: Using Fibonacci ratios (38.2%, 61.8%, 100%)
    - camarilla: Camarilla equation (tighter levels)
    - woodie: Woodie's pivot (emphasizes close)

    Args:
        df: DataFrame with OHLCV data
        method: Calculation method

    Returns:
        Dict with pivot, r1, r2, r3, s1, s2, s3 levels
    """
    try:
        # Use previous bar's data
        prev_high = float(df['high'].iloc[-1])
        prev_low = float(df['low'].iloc[-1])
        prev_close = float(df['close'].iloc[-1])

        if method == "standard":
            pivot = (prev_high + prev_low + prev_close) / 3
            r1 = 2 * pivot - prev_low
            r2 = pivot + (prev_high - prev_low)
            r3 = prev_high + 2 * (pivot - prev_low)
            s1 = 2 * pivot - prev_high
            s2 = pivot - (prev_high - prev_low)
            s3 = prev_low - 2 * (prev_high - pivot)

        elif method == "fibonacci":
            pivot = (prev_high + prev_low + prev_close) / 3
            range_hl = prev_high - prev_low
            r1 = pivot + 0.382 * range_hl
            r2 = pivot + 0.618 * range_hl
            r3 = pivot + 1.000 * range_hl
            s1 = pivot - 0.382 * range_hl
            s2 = pivot - 0.618 * range_hl
            s3 = pivot - 1.000 * range_hl

        elif method == "camarilla":
            pivot = (prev_high + prev_low + prev_close) / 3
            range_hl = prev_high - prev_low
            r1 = prev_close + range_hl * 1.1 / 12
            r2 = prev_close + range_hl * 1.1 / 6
            r3 = prev_close + range_hl * 1.1 / 4
            r4 = prev_close + range_hl * 1.1 / 2
            s1 = prev_close - range_hl * 1.1 / 12
            s2 = prev_close - range_hl * 1.1 / 6
            s3 = prev_close - range_hl * 1.1 / 4
            s4 = prev_close - range_hl * 1.1 / 2

            return {
                'pivot': pivot,
                'r1': r1, 'r2': r2, 'r3': r3, 'r4': r4,
                's1': s1, 's2': s2, 's3': s3, 's4': s4
            }

        elif method == "woodie":
            pivot = (prev_high + prev_low + 2 * prev_close) / 4
            r1 = 2 * pivot - prev_low
            r2 = pivot + (prev_high - prev_low)
            r3 = prev_high + 2 * (pivot - prev_low)
            s1 = 2 * pivot - prev_high
            s2 = pivot - (prev_high - prev_low)
            s3 = prev_low - 2 * (prev_high - pivot)

        else:
            raise ValueError(f"Unknown pivot method: {method}")

        return {
            'pivot': pivot,
            'r1': r1, 'r2': r2, 'r3': r3,
            's1': s1, 's2': s2, 's3': s3
        }

    except Exception as e:
        logger.exception(f"Error calculating pivot points: {e}")
        return {}


@register_indicator(
    name="fibonacci_retracement",
    category=IndicatorCategory.PATTERN_RECOGNITION,
    library="custom",
    description="Fibonacci retracement levels (23.6%, 38.2%, 50%, 61.8%, 78.6%) between two points",
    parameters={"lookback": 50},
    output_type="dict"
)
def fibonacci_retracement(
    df: pd.DataFrame,
    lookback: int = 50,
    **kwargs
) -> dict[str, float]:
    """
    Calculate Fibonacci retracement levels.

    Automatically finds swing high and low in lookback period.

    Args:
        df: DataFrame with OHLCV data
        lookback: Bars to look back for swing points

    Returns:
        Dict with fib levels: 0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100%
    """
    try:
        recent_df = df.tail(lookback)

        # Find swing high and low
        swing_high = float(recent_df['high'].max())
        swing_low = float(recent_df['low'].min())

        # Calculate retracement levels (from low to high)
        diff = swing_high - swing_low

        return {
            'level_0': swing_low,
            'level_236': swing_low + 0.236 * diff,
            'level_382': swing_low + 0.382 * diff,
            'level_500': swing_low + 0.500 * diff,
            'level_618': swing_low + 0.618 * diff,
            'level_786': swing_low + 0.786 * diff,
            'level_100': swing_high,
            'swing_high': swing_high,
            'swing_low': swing_low
        }

    except Exception as e:
        logger.exception(f"Error calculating Fibonacci retracement: {e}")
        return {}


@register_indicator(
    name="fibonacci_extension",
    category=IndicatorCategory.PATTERN_RECOGNITION,
    library="custom",
    description="Fibonacci extension levels (127.2%, 161.8%, 200%, 261.8%) for profit targets",
    parameters={"lookback": 50},
    output_type="dict"
)
def fibonacci_extension(
    df: pd.DataFrame,
    lookback: int = 50,
    **kwargs
) -> dict[str, float]:
    """
    Calculate Fibonacci extension levels for profit targets.

    Args:
        df: DataFrame with OHLCV data
        lookback: Bars to look back for swing points

    Returns:
        Dict with extension levels: 100%, 127.2%, 161.8%, 200%, 261.8%
    """
    try:
        recent_df = df.tail(lookback)

        # Find swing high and low
        swing_high = float(recent_df['high'].max())
        swing_low = float(recent_df['low'].min())

        diff = swing_high - swing_low

        return {
            'level_100': swing_high,
            'level_1272': swing_high + 0.272 * diff,
            'level_1618': swing_high + 0.618 * diff,
            'level_200': swing_high + 1.000 * diff,
            'level_2618': swing_high + 1.618 * diff,
            'swing_high': swing_high,
            'swing_low': swing_low
        }

    except Exception as e:
        logger.exception(f"Error calculating Fibonacci extension: {e}")
        return {}


@register_indicator(
    name="zigzag",
    category=IndicatorCategory.PATTERN_RECOGNITION,
    library="custom",
    description="ZigZag indicator - connects significant price swings, filters noise",
    parameters={"deviation": 0.05, "price_col": "close"}
)
def zigzag(
    df: pd.DataFrame,
    deviation: float = 0.05,
    price_col: str = "close",
    **kwargs
) -> pd.Series:
    """
    Calculate ZigZag indicator.

    Connects significant price swings while filtering out noise.
    Only shows moves greater than the deviation threshold.

    Args:
        df: DataFrame with OHLCV data
        deviation: Minimum price change to form new leg (5% default)
        price_col: Column to analyze

    Returns:
        Series with zigzag line values (forward-filled)
    """
    try:
        prices = df[price_col].values
        result = pd.Series(np.nan, index=df.index)

        # Initialize
        result.iloc[0] = prices[0]
        last_pivot = prices[0]
        direction = 0  # 1 for up, -1 for down

        for i in range(1, len(prices)):
            price = prices[i]

            if direction == 0:
                # Determine initial direction
                if price > last_pivot * (1 + deviation):
                    direction = 1
                    result.iloc[i] = price
                    last_pivot = price
                elif price < last_pivot * (1 - deviation):
                    direction = -1
                    result.iloc[i] = price
                    last_pivot = price

            elif direction == 1:
                # Uptrend
                if price > last_pivot:
                    # Update high
                    result.iloc[i] = price
                    last_pivot = price
                elif price < last_pivot * (1 - deviation):
                    # Reversal to downtrend
                    direction = -1
                    result.iloc[i] = price
                    last_pivot = price

            else:  # direction == -1
                # Downtrend
                if price < last_pivot:
                    # Update low
                    result.iloc[i] = price
                    last_pivot = price
                elif price > last_pivot * (1 + deviation):
                    # Reversal to uptrend
                    direction = 1
                    result.iloc[i] = price
                    last_pivot = price

        # Forward fill zigzag line
        result = result.ffill()

        return result

    except Exception as e:
        logger.exception(f"Error calculating ZigZag: {e}")
        return pd.Series(np.nan, index=df.index)


@register_indicator(
    name="volume_profile",
    category=IndicatorCategory.PATTERN_RECOGNITION,
    library="custom",
    description="Volume Profile - distribution of volume at different price levels, identifies value areas",
    parameters={"bins": 20},
    output_type="dataframe"
)
def volume_profile(
    df: pd.DataFrame,
    bins: int = 20,
    **kwargs
) -> pd.DataFrame:
    """
    Calculate Volume Profile.

    Shows distribution of volume at different price levels.
    Identifies Point of Control (POC), Value Area High/Low.

    Args:
        df: DataFrame with OHLCV data
        bins: Number of price bins

    Returns:
        DataFrame with price_level, volume, percentage columns
    """
    try:
        # Create price bins
        price_min = df['low'].min()
        price_max = df['high'].max()
        bin_edges = np.linspace(price_min, price_max, bins + 1)

        # Assign each bar to a price bin and accumulate volume
        volume_by_price = np.zeros(bins)

        for _, row in df.iterrows():
            # Find which bin this bar's typical price falls into
            typical_price = (row['high'] + row['low'] + row['close']) / 3
            bin_idx = min(np.searchsorted(bin_edges, typical_price) - 1, bins - 1)
            bin_idx = max(bin_idx, 0)
            volume_by_price[bin_idx] += row['volume']

        # Calculate price levels (bin centers)
        price_levels = (bin_edges[:-1] + bin_edges[1:]) / 2

        # Create result DataFrame
        total_volume = volume_by_price.sum()
        result_df = pd.DataFrame({
            'price_level': price_levels,
            'volume': volume_by_price,
            'percentage': (volume_by_price / total_volume * 100) if total_volume > 0 else 0
        })

        # Sort by volume descending
        result_df = result_df.sort_values('volume', ascending=False).reset_index(drop=True)

        # Add POC (Point of Control) - price with most volume
        result_df['is_poc'] = False
        if len(result_df) > 0:
            result_df.loc[0, 'is_poc'] = True

        return result_df

    except Exception as e:
        logger.exception(f"Error calculating volume profile: {e}")
        return pd.DataFrame(columns=['price_level', 'volume', 'percentage', 'is_poc'])


@register_indicator(
    name="market_profile",
    category=IndicatorCategory.PATTERN_RECOGNITION,
    library="custom",
    description="Market Profile (TPO) - time-price opportunity chart, shows where price spent most time",
    parameters={"tick_size": 0.05},
    output_type="dataframe"
)
def market_profile(
    df: pd.DataFrame,
    tick_size: float = 0.05,
    **kwargs
) -> pd.DataFrame:
    """
    Calculate Market Profile (Time-Price Opportunity).

    Shows where price spent most time (not volume).
    Each bar contributes one TPO to its price levels.

    Args:
        df: DataFrame with OHLCV data
        tick_size: Price tick size for granularity

    Returns:
        DataFrame with price_level, tpo_count, percentage columns
    """
    try:
        # Create price levels based on tick size
        price_min = df['low'].min()
        price_max = df['high'].max()
        num_levels = int((price_max - price_min) / tick_size) + 1
        price_levels = np.linspace(price_min, price_max, num_levels)

        # Count TPOs at each level
        tpo_by_price = np.zeros(num_levels)

        for _, row in df.iterrows():
            # Each bar adds TPOs to all price levels it touched
            bar_low = row['low']
            bar_high = row['high']

            for i, price_level in enumerate(price_levels):
                if bar_low <= price_level <= bar_high:
                    tpo_by_price[i] += 1

        # Create result DataFrame
        total_tpos = tpo_by_price.sum()
        result_df = pd.DataFrame({
            'price_level': price_levels,
            'tpo_count': tpo_by_price,
            'percentage': (tpo_by_price / total_tpos * 100) if total_tpos > 0 else 0
        })

        # Sort by TPO count descending
        result_df = result_df[result_df['tpo_count'] > 0].sort_values('tpo_count', ascending=False).reset_index(drop=True)

        # Add Value Area (70% of TPOs)
        result_df['in_value_area'] = False
        cumsum = 0
        for i in range(len(result_df)):
            cumsum += result_df.loc[i, 'percentage']
            result_df.loc[i, 'in_value_area'] = cumsum <= 70

        return result_df

    except Exception as e:
        logger.exception(f"Error calculating market profile: {e}")
        return pd.DataFrame(columns=['price_level', 'tpo_count', 'percentage', 'in_value_area'])


@register_indicator(
    name="anchored_vwap",
    category=IndicatorCategory.CUSTOM,
    library="custom",
    description="Anchored VWAP from a specific datetime - institutional reference point",
    parameters={"anchor_datetime": None},
)
def anchored_vwap(
    df: pd.DataFrame,
    anchor_datetime: str | None = None,
    **kwargs
) -> pd.Series:
    """
    Calculate Anchored VWAP from a specific datetime.

    VWAP anchored to events (market open, earnings, etc.) shows institutional cost basis.

    Args:
        df: DataFrame with OHLCV data
        anchor_datetime: ISO datetime string to anchor from (default: first bar)

    Returns:
        Series with anchored VWAP values (NaN before anchor)
    """
    try:
        # Use first bar if no anchor specified
        if anchor_datetime is None:
            anchor_dt = df.index[0]
        else:
            anchor_dt = pd.to_datetime(anchor_datetime)

        # Find anchor index
        if anchor_dt not in df.index:
            # Find nearest timestamp
            idx = df.index.get_indexer([anchor_dt], method='nearest')[0]
        else:
            idx = df.index.get_loc(anchor_dt)

        # Initialize result
        result = pd.Series(np.nan, index=df.index)

        # Calculate from anchor point
        df_subset = df.iloc[idx:]

        # Calculate typical price
        typical_price = (df_subset['high'] + df_subset['low'] + df_subset['close']) / 3

        # Calculate cumulative volume-weighted price
        cum_volume = df_subset['volume'].cumsum()
        cum_vp = (typical_price * df_subset['volume']).cumsum()

        # Calculate anchored VWAP
        avwap = cum_vp / cum_volume

        # Fill result
        result.iloc[idx:] = avwap.values

        return result

    except Exception as e:
        logger.exception(f"Error calculating anchored VWAP: {e}")
        return pd.Series(np.nan, index=df.index)
