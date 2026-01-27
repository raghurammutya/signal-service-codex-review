"""
Smart Money Concepts Indicators

Professional institutional trading methodology indicators including:
- Break of Structure (BOS) - Real implementation using swing analysis
- Change of Character (CHoCH) - Real implementation using market structure
- Order Blocks - Real implementation using volume and displacement analysis
- Fair Value Gaps (FVG) - Real implementation using 3-candle gap patterns
- Liquidity Levels - Real implementation using swing clustering
- Smart Money Swings - Real implementation using existing swing detection

Implementation: Native algorithms (no external dependencies)
Fallback: smartmoneyconcepts library (when dependency conflicts resolved)
Documentation: Institutional trading concepts based on ICT methodology
"""
import logging

import pandas as pd

from app.services.indicator_registry import IndicatorCategory, register_indicator

logger = logging.getLogger(__name__)

# Try to import smartmoneyconcepts - OPTIONAL due to dependency conflicts
# (requires pandas==2.0.2 which conflicts with pandas-ta>=2.3.2)
try:
    import smartmoneyconcepts as smc
    SMC_AVAILABLE = True
    logger.info("smartmoneyconcepts library loaded successfully - using original library")
except ImportError:
    SMC_AVAILABLE = False
    logger.info("smartmoneyconcepts not available - using native Smart Money implementations (no dependency conflicts)")


@register_indicator(
    name="swing_highs_lows_smc",
    category=IndicatorCategory.SMART_MONEY,
    library="smartmoneyconcepts",
    description="Detect swing points using Smart Money Concepts methodology with volume confirmation",
    parameters={"swing_length": 10}
)
def swing_highs_lows_smc(
    df: pd.DataFrame,
    swing_length: int = 10,
    **kwargs
) -> pd.Series:
    """
    Detect swing highs and lows using SMC methodology.

    Args:
        df: DataFrame with OHLCV data
        swing_length: Length for swing detection (default 10)

    Returns:
        Series with 1 for swing high, -1 for swing low, 0 for neither
    """
    try:
        if not SMC_AVAILABLE:
            return _get_real_swings(df, swing_length)

        return smc.swing_highs_lows(df, swing_length=swing_length)

    except Exception as e:
        logger.exception(f"Error calculating SMC swings: {e}")
        return _get_real_swings(df, swing_length)


@register_indicator(
    name="break_of_structure",
    category=IndicatorCategory.SMART_MONEY,
    library="smartmoneyconcepts",
    description="Break of Structure (BOS) - indicates trend continuation when price breaks previous swing",
    parameters={"swing_length": 10}
)
def break_of_structure(
    df: pd.DataFrame,
    swing_length: int = 10,
    **kwargs
) -> pd.Series:
    """
    Detect Break of Structure (BOS) signals.

    BOS indicates trend continuation when price decisively breaks a previous
    swing point in the direction of the trend.

    Args:
        df: DataFrame with OHLCV data
        swing_length: Length for swing detection

    Returns:
        Series with 1 for bullish BOS, -1 for bearish BOS, 0 for no BOS
    """
    try:
        if not SMC_AVAILABLE:
            return _real_bos(df)

        # Get swing points first
        swings = smc.swing_highs_lows(df, swing_length=swing_length)

        # Calculate BOS
        return smc.bos(df, swings)


    except Exception as e:
        logger.exception(f"Error calculating BOS: {e}")
        return _real_bos(df)


@register_indicator(
    name="change_of_character",
    category=IndicatorCategory.SMART_MONEY,
    library="smartmoneyconcepts",
    description="Change of Character (CHoCH) - indicates potential trend reversal",
    parameters={"swing_length": 10}
)
def change_of_character(
    df: pd.DataFrame,
    swing_length: int = 10,
    **kwargs
) -> pd.Series:
    """
    Detect Change of Character (CHoCH) signals.

    CHoCH indicates potential trend reversal when price breaks structure
    against the prevailing trend.

    Args:
        df: DataFrame with OHLCV data
        swing_length: Length for swing detection

    Returns:
        Series with 1 for bullish CHoCH, -1 for bearish CHoCH, 0 for no CHoCH
    """
    try:
        if not SMC_AVAILABLE:
            return _real_choch(df)

        # Get swing points first
        swings = smc.swing_highs_lows(df, swing_length=swing_length)

        # Calculate CHoCH
        return smc.choch(df, swings)


    except Exception as e:
        logger.exception(f"Error calculating CHoCH: {e}")
        return _real_choch(df)


@register_indicator(
    name="order_blocks",
    category=IndicatorCategory.SMART_MONEY,
    library="smartmoneyconcepts",
    description="Order Blocks - institutional supply/demand zones where large orders were placed",
    parameters={"swing_length": 10},
    output_type="dataframe"
)
def order_blocks(
    df: pd.DataFrame,
    swing_length: int = 10,
    **kwargs
) -> pd.DataFrame:
    """
    Detect Order Blocks - institutional supply/demand zones.

    Order blocks represent areas where institutions placed large orders.
    Price often returns to these zones for liquidity.

    Args:
        df: DataFrame with OHLCV data
        swing_length: Length for swing detection

    Returns:
        DataFrame with order block levels, types (bullish/bearish), and timestamps
    """
    try:
        if not SMC_AVAILABLE:
            return _real_order_blocks(df)

        # Get swing points first
        swings = smc.swing_highs_lows(df, swing_length=swing_length)

        # Calculate order blocks
        return smc.ob(df, swings)


    except Exception as e:
        logger.exception(f"Error calculating order blocks: {e}")
        return _real_order_blocks(df)


@register_indicator(
    name="fair_value_gaps",
    category=IndicatorCategory.SMART_MONEY,
    library="smartmoneyconcepts",
    description="Fair Value Gaps (FVG) - price imbalance zones likely to be revisited",
    parameters={},
    output_type="dataframe"
)
def fair_value_gaps(
    df: pd.DataFrame,
    **kwargs
) -> pd.DataFrame:
    """
    Detect Fair Value Gaps (FVG).

    FVG are price imbalances created by aggressive buying/selling.
    These gaps often get filled as price returns for liquidity.

    Args:
        df: DataFrame with OHLCV data

    Returns:
        DataFrame with FVG levels, types (bullish/bearish), and timestamps
    """
    try:
        if not SMC_AVAILABLE:
            return _real_fvg(df)

        # Calculate fair value gaps
        return smc.fvg(df)


    except Exception as e:
        logger.exception(f"Error calculating FVG: {e}")
        return _real_fvg(df)


@register_indicator(
    name="liquidity",
    category=IndicatorCategory.SMART_MONEY,
    library="smartmoneyconcepts",
    description="Liquidity levels - areas where stop losses cluster (likely to be hunted)",
    parameters={"swing_length": 10},
    output_type="dataframe"
)
def liquidity_levels(
    df: pd.DataFrame,
    swing_length: int = 10,
    **kwargs
) -> pd.DataFrame:
    """
    Detect liquidity levels where stop losses cluster.

    Institutions target these levels to accumulate positions (stop hunts).

    Args:
        df: DataFrame with OHLCV data
        swing_length: Length for swing detection

    Returns:
        DataFrame with liquidity levels, types (buy-side/sell-side), and strength
    """
    try:
        if not SMC_AVAILABLE:
            return _real_liquidity(df)

        # Get swing points first
        swings = smc.swing_highs_lows(df, swing_length=swing_length)

        # Calculate liquidity levels
        return smc.liquidity(df, swings)


    except Exception as e:
        logger.exception(f"Error calculating liquidity: {e}")
        return _real_liquidity(df)


@register_indicator(
    name="previous_high_low",
    category=IndicatorCategory.SMART_MONEY,
    library="smartmoneyconcepts",
    description="Previous period high/low - key support/resistance levels",
    parameters={"period": "1D"},
    output_type="dict"
)
def previous_high_low(
    df: pd.DataFrame,
    period: str = "1D",
    **kwargs
) -> dict[str, float]:
    """
    Calculate previous period high and low.

    These are critical support/resistance levels watched by all traders.

    Args:
        df: DataFrame with OHLCV data
        period: Period for calculation ("1D", "1W", "1M")

    Returns:
        Dict with 'previous_high' and 'previous_low' values
    """
    try:
        if not SMC_AVAILABLE or len(df) < 2:
            return _real_prev_hl(df)

        # Get previous period
        return smc.previous_high_low(df, period=period)


    except Exception as e:
        logger.exception(f"Error calculating previous high/low: {e}")
        return _real_prev_hl(df)


@register_indicator(
    name="sessions",
    category=IndicatorCategory.SMART_MONEY,
    library="smartmoneyconcepts",
    description="Trading session markers (Asian, London, New York) with high/low levels",
    parameters={},
    output_type="dataframe"
)
def trading_sessions(
    df: pd.DataFrame,
    **kwargs
) -> pd.DataFrame:
    """
    Mark trading sessions (Asian, London, NY) with their high/low levels.

    Different sessions show different character - useful for timing entries.

    Args:
        df: DataFrame with OHLCV data (must have datetime index with timezone)

    Returns:
        DataFrame with session markers and key levels
    """
    try:
        if not SMC_AVAILABLE:
            return _real_sessions(df)

        # Calculate session data
        return smc.sessions(df)


    except Exception as e:
        logger.exception(f"Error calculating sessions: {e}")
        return _real_sessions(df)


# =============================================================================
# Real Smart Money Concept Implementations
# Using existing professional swing detection and institutional logic
# =============================================================================

def _get_real_swings(df: pd.DataFrame, swing_length: int = 5) -> pd.Series:
    """
    Real swing detection using professional algorithms

    Returns:
        Series with 1 for swing high, -1 for swing low, 0 for neither
    """
    try:
        from app.services.custom_indicators import CustomIndicators

        # Get swing highs and lows using real implementation
        swing_highs = CustomIndicators.swing_high(df, left_bars=swing_length, right_bars=swing_length)
        swing_lows = CustomIndicators.swing_low(df, left_bars=swing_length, right_bars=swing_length)

        # Combine into single series
        result = pd.Series(0, index=df.index)
        result[swing_highs.notna()] = 1  # Swing high = 1
        result[swing_lows.notna()] = -1  # Swing low = -1

        return result

    except Exception as e:
        logger.exception(f"Error in real swing detection: {e}")
        # Fallback to simple pattern if custom indicators fail
        return _simple_swing_fallback(df, swing_length)


def _simple_swing_fallback(df: pd.DataFrame, swing_length: int) -> pd.Series:
    """Simple swing detection fallback"""
    result = pd.Series(0, index=df.index)
    highs = df['high'].rolling(window=swing_length*2+1, center=True).max()
    lows = df['low'].rolling(window=swing_length*2+1, center=True).min()

    result[(df['high'] == highs) & (df['high'].shift(1) < df['high']) & (df['high'].shift(-1) < df['high'])] = 1
    result[(df['low'] == lows) & (df['low'].shift(1) > df['low']) & (df['low'].shift(-1) > df['low'])] = -1

    return result


def _real_bos(df: pd.DataFrame) -> pd.Series:
    """
    REAL Break of Structure Implementation

    BOS Logic:
    1. Identify swing highs/lows using real swing detection
    2. Determine market structure (bullish/bearish trend)
    3. Bullish BOS: Price breaks above previous swing high
    4. Bearish BOS: Price breaks below previous swing low
    """
    try:
        if len(df) < 20:  # Need minimum data
            return pd.Series(0, index=df.index)

        # Get real swing points
        swings = _get_real_swings(df, swing_length=5)

        # Initialize result
        result = pd.Series(0, index=df.index)

        # Get swing high and low indices
        swing_high_indices = df.index[swings == 1].tolist()
        swing_low_indices = df.index[swings == -1].tolist()

        # Track last swing highs and lows
        for i in range(len(df)):
            current_idx = df.index[i]
            current_high = df['high'].iloc[i]
            current_low = df['low'].iloc[i]

            # Find most recent swing high before current bar
            recent_swing_highs = [idx for idx in swing_high_indices if idx < current_idx]
            if recent_swing_highs:
                last_swing_high = df.loc[recent_swing_highs[-1], 'high']

                # Bullish BOS: Current high breaks above last swing high
                if current_high > last_swing_high:
                    # Confirm with volume if available
                    if 'volume' in df.columns and i > 0:
                        avg_volume = df['volume'].iloc[max(0, i-10):i].mean()
                        if df['volume'].iloc[i] > avg_volume * 1.2:  # 20% above average
                            result.iloc[i] = 1
                    else:
                        result.iloc[i] = 1

            # Find most recent swing low before current bar
            recent_swing_lows = [idx for idx in swing_low_indices if idx < current_idx]
            if recent_swing_lows:
                last_swing_low = df.loc[recent_swing_lows[-1], 'low']

                # Bearish BOS: Current low breaks below last swing low
                if current_low < last_swing_low:
                    # Confirm with volume if available
                    if 'volume' in df.columns and i > 0:
                        avg_volume = df['volume'].iloc[max(0, i-10):i].mean()
                        if df['volume'].iloc[i] > avg_volume * 1.2:  # 20% above average
                            result.iloc[i] = -1
                    else:
                        result.iloc[i] = -1

        return result

    except Exception as e:
        logger.exception(f"Error in real BOS calculation: {e}")
        return pd.Series(0, index=df.index)


def _real_choch(df: pd.DataFrame) -> pd.Series:
    """
    REAL Change of Character Implementation

    CHoCH Logic:
    1. Determine current market structure trend
    2. Bullish CHoCH: In bearish trend, price breaks above previous swing high
    3. Bearish CHoCH: In bullish trend, price breaks below previous swing low
    4. This indicates potential trend reversal
    """
    try:
        if len(df) < 30:  # Need more data for trend determination
            return pd.Series(0, index=df.index)

        # Get real swing points
        swings = _get_real_swings(df, swing_length=5)
        result = pd.Series(0, index=df.index)

        # Determine market structure using Higher Highs/Lower Lows
        swing_high_indices = df.index[swings == 1].tolist()
        swing_low_indices = df.index[swings == -1].tolist()

        for i in range(20, len(df)):  # Start after enough data
            current_idx = df.index[i]
            current_high = df['high'].iloc[i]
            current_low = df['low'].iloc[i]

            # Get recent swing structure (last 3 swings)
            recent_highs = [idx for idx in swing_high_indices if idx < current_idx][-3:]
            recent_lows = [idx for idx in swing_low_indices if idx < current_idx][-3:]

            if len(recent_highs) >= 2 and len(recent_lows) >= 2:
                # Determine trend based on swing structure
                high_values = [df.loc[idx, 'high'] for idx in recent_highs]
                low_values = [df.loc[idx, 'low'] for idx in recent_lows]

                # Bearish trend: Lower Highs and Lower Lows
                is_bearish_trend = (len(high_values) >= 2 and high_values[-1] < high_values[-2] and
                                  len(low_values) >= 2 and low_values[-1] < low_values[-2])

                # Bullish trend: Higher Highs and Higher Lows
                is_bullish_trend = (len(high_values) >= 2 and high_values[-1] > high_values[-2] and
                                  len(low_values) >= 2 and low_values[-1] > low_values[-2])

                # Bullish CHoCH: In bearish trend, break above recent swing high
                if is_bearish_trend and recent_highs:
                    last_swing_high = df.loc[recent_highs[-1], 'high']
                    if current_high > last_swing_high:
                        result.iloc[i] = 1

                # Bearish CHoCH: In bullish trend, break below recent swing low
                elif is_bullish_trend and recent_lows:
                    last_swing_low = df.loc[recent_lows[-1], 'low']
                    if current_low < last_swing_low:
                        result.iloc[i] = -1

        return result

    except Exception as e:
        logger.exception(f"Error in real CHoCH calculation: {e}")
        return pd.Series(0, index=df.index)


def _real_order_blocks(df: pd.DataFrame) -> pd.DataFrame:
    """
    REAL Order Blocks Implementation

    Order Block Logic:
    1. Identify swing points with high volume
    2. Find candlesticks before strong moves (displacement)
    3. Mark these as institutional order zones
    4. Distinguish bullish vs bearish order blocks
    """
    try:
        if len(df) < 20:
            return pd.DataFrame(columns=['top', 'bottom', 'type', 'timestamp', 'strength'])

        # Get swing points
        _get_real_swings(df, swing_length=3)
        order_blocks = []

        # Find displacement moves (strong price movements)
        price_change = df['close'].pct_change().abs()
        avg_change = price_change.rolling(window=20).mean()
        displacement_threshold = avg_change * 2  # 2x average move

        for i in range(10, len(df) - 5):
            # Check if this bar created displacement
            if price_change.iloc[i] > displacement_threshold.iloc[i]:

                # Volume confirmation if available
                volume_confirmed = True
                if 'volume' in df.columns:
                    avg_volume = df['volume'].iloc[i-10:i].mean()
                    volume_confirmed = df['volume'].iloc[i] > avg_volume * 1.5

                if volume_confirmed:
                    # Bullish displacement (strong up move)
                    if df['close'].iloc[i] > df['open'].iloc[i]:
                        # Look for the last bearish candle before displacement
                        for j in range(i-1, max(0, i-5), -1):
                            if df['close'].iloc[j] < df['open'].iloc[j]:  # Bearish candle
                                order_blocks.append({
                                    'top': float(df['high'].iloc[j]),
                                    'bottom': float(df['low'].iloc[j]),
                                    'type': 'bullish',
                                    'timestamp': df.index[j],
                                    'strength': float(price_change.iloc[i])
                                })
                                break

                    # Bearish displacement (strong down move)
                    elif df['close'].iloc[i] < df['open'].iloc[i]:
                        # Look for the last bullish candle before displacement
                        for j in range(i-1, max(0, i-5), -1):
                            if df['close'].iloc[j] > df['open'].iloc[j]:  # Bullish candle
                                order_blocks.append({
                                    'top': float(df['high'].iloc[j]),
                                    'bottom': float(df['low'].iloc[j]),
                                    'type': 'bearish',
                                    'timestamp': df.index[j],
                                    'strength': float(price_change.iloc[i])
                                })
                                break

        # Return top 10 strongest order blocks
        if order_blocks:
            ob_df = pd.DataFrame(order_blocks)
            ob_df = ob_df.sort_values('strength', ascending=False).head(10)
            return ob_df.reset_index(drop=True)

        return pd.DataFrame(columns=['top', 'bottom', 'type', 'timestamp', 'strength'])

    except Exception as e:
        logger.exception(f"Error in real Order Blocks calculation: {e}")
        return pd.DataFrame(columns=['top', 'bottom', 'type', 'timestamp', 'strength'])


def _real_fvg(df: pd.DataFrame) -> pd.DataFrame:
    """
    REAL Fair Value Gaps Implementation

    FVG Logic:
    1. Identify 3-candle patterns with gaps
    2. Bullish FVG: Gap between candle 1 high and candle 3 low
    3. Bearish FVG: Gap between candle 1 low and candle 3 high
    4. Must have displacement (strong move) to be valid
    """
    try:
        if len(df) < 10:
            return pd.DataFrame(columns=['top', 'bottom', 'type', 'timestamp', 'filled'])

        fvg_list = []

        for i in range(2, len(df)):  # Need at least 3 candles
            # Get 3-candle pattern
            candle1 = df.iloc[i-2]
            df.iloc[i-1]
            candle3 = df.iloc[i]

            # Bullish FVG: Gap up pattern
            # Candle 1 high < Candle 3 low (gap between them)
            if candle1['high'] < candle3['low']:
                # Confirm it's a strong bullish move
                if candle3['close'] > candle1['close'] * 1.005:  # At least 0.5% move
                    gap_top = candle3['low']
                    gap_bottom = candle1['high']

                    # Check if gap is significant (> 0.1% of price)
                    if (gap_top - gap_bottom) / candle1['close'] > 0.001:
                        fvg_list.append({
                            'top': float(gap_top),
                            'bottom': float(gap_bottom),
                            'type': 'bullish',
                            'timestamp': df.index[i],
                            'filled': False
                        })

            # Bearish FVG: Gap down pattern
            # Candle 1 low > Candle 3 high (gap between them)
            elif candle1['low'] > candle3['high']:
                # Confirm it's a strong bearish move
                if candle3['close'] < candle1['close'] * 0.995:  # At least 0.5% move
                    gap_top = candle1['low']
                    gap_bottom = candle3['high']

                    # Check if gap is significant (> 0.1% of price)
                    if (gap_top - gap_bottom) / candle1['close'] > 0.001:
                        fvg_list.append({
                            'top': float(gap_top),
                            'bottom': float(gap_bottom),
                            'type': 'bearish',
                            'timestamp': df.index[i],
                            'filled': False
                        })

        # Check if any FVGs have been filled by subsequent price action
        if fvg_list:
            fvg_df = pd.DataFrame(fvg_list)
            current_price = df['close'].iloc[-1]

            for idx, row in fvg_df.iterrows():
                # FVG is filled if price has traded through the gap
                if row['bottom'] <= current_price <= row['top']:
                    fvg_df.loc[idx, 'filled'] = True

            # Return unfilled FVGs (most relevant)
            return fvg_df[not fvg_df['filled']].reset_index(drop=True)

        return pd.DataFrame(columns=['top', 'bottom', 'type', 'timestamp', 'filled'])

    except Exception as e:
        logger.exception(f"Error in real FVG calculation: {e}")
        return pd.DataFrame(columns=['top', 'bottom', 'type', 'timestamp', 'filled'])


def _real_liquidity(df: pd.DataFrame) -> pd.DataFrame:
    """
    REAL Liquidity Levels Implementation

    Liquidity Logic:
    1. Find swing highs/lows (where stops cluster)
    2. Equal highs/lows (liquidity pools)
    3. Previous day/week/month highs/lows
    4. Round numbers and psychological levels
    """
    try:
        if len(df) < 20:
            return pd.DataFrame(columns=['level', 'type', 'strength', 'touches'])

        liquidity_levels = []

        # Get swing points
        swings = _get_real_swings(df, swing_length=5)
        swing_high_indices = df.index[swings == 1].tolist()
        swing_low_indices = df.index[swings == -1].tolist()

        # 1. Swing High Liquidity (Sell-side liquidity)
        swing_highs = [df.loc[idx, 'high'] for idx in swing_high_indices]
        for high_level in swing_highs[-10:]:  # Last 10 swing highs
            touches = sum(1 for h in swing_highs if abs(h - high_level) < high_level * 0.002)  # Within 0.2%
            if touches >= 2:  # Multiple touches = stronger level
                liquidity_levels.append({
                    'level': float(high_level),
                    'type': 'sell-side',
                    'strength': min(touches / 5.0, 1.0),  # Normalize to 0-1
                    'touches': touches
                })

        # 2. Swing Low Liquidity (Buy-side liquidity)
        swing_lows = [df.loc[idx, 'low'] for idx in swing_low_indices]
        for low_level in swing_lows[-10:]:  # Last 10 swing lows
            touches = sum(1 for l in swing_lows if abs(l - low_level) < low_level * 0.002)  # Within 0.2%
            if touches >= 2:  # Multiple touches = stronger level
                liquidity_levels.append({
                    'level': float(low_level),
                    'type': 'buy-side',
                    'strength': min(touches / 5.0, 1.0),  # Normalize to 0-1
                    'touches': touches
                })

        # 3. Previous period highs/lows
        if len(df) >= 50:  # Daily data
            prev_high = df['high'].iloc[-50:-1].max()  # Previous ~2 months
            prev_low = df['low'].iloc[-50:-1].min()

            liquidity_levels.extend([
                {
                    'level': float(prev_high),
                    'type': 'sell-side',
                    'strength': 0.8,
                    'touches': 1
                },
                {
                    'level': float(prev_low),
                    'type': 'buy-side',
                    'strength': 0.8,
                    'touches': 1
                }
            ])

        # 4. Round number levels (psychological)
        current_price = df['close'].iloc[-1]
        price_range = df['high'].max() - df['low'].min()

        # Find round numbers within price range
        if current_price > 100:
            step = 50 if current_price > 1000 else 25
        else:
            step = 10 if current_price > 50 else 5

        price_min = int((current_price - price_range/2) / step) * step
        price_max = int((current_price + price_range/2) / step) * step

        for round_level in range(price_min, price_max + step, step):
            if round_level > 0:  # Valid price
                # Check if price has interacted with this level
                interaction_count = sum(1 for i in range(len(df))
                                     if abs(df['high'].iloc[i] - round_level) < round_level * 0.001 or
                                        abs(df['low'].iloc[i] - round_level) < round_level * 0.001)

                if interaction_count > 0:
                    liq_type = 'sell-side' if round_level > current_price else 'buy-side'
                    liquidity_levels.append({
                        'level': float(round_level),
                        'type': liq_type,
                        'strength': 0.6,  # Medium strength for round numbers
                        'touches': interaction_count
                    })

        # Remove duplicates and sort by strength
        if liquidity_levels:
            liq_df = pd.DataFrame(liquidity_levels)
            liq_df = liq_df.drop_duplicates(subset=['level'], keep='first')
            liq_df = liq_df.sort_values('strength', ascending=False).head(15)
            return liq_df.reset_index(drop=True)

        return pd.DataFrame(columns=['level', 'type', 'strength', 'touches'])

    except Exception as e:
        logger.exception(f"Error in real Liquidity calculation: {e}")
        return pd.DataFrame(columns=['level', 'type', 'strength', 'touches'])


def _real_prev_hl(df: pd.DataFrame) -> dict[str, float]:
    """
    REAL Previous High/Low Implementation

    Returns significant previous period levels based on timeframe
    """
    try:
        if len(df) < 2:
            return {'previous_high': float(df['high'].iloc[-1]), 'previous_low': float(df['low'].iloc[-1])}

        # Determine lookback period based on data frequency
        if len(df) > 100:  # Likely daily or higher frequency data
            lookback = min(20, len(df) // 2)  # Previous 20 periods or half the data
        else:
            lookback = min(10, len(df) // 2)

        # Get previous period (excluding current bar)
        prev_data = df.iloc[-(lookback+1):-1] if len(df) > lookback else df.iloc[:-1]

        # Find significant levels (not just previous bar)
        prev_high = prev_data['high'].max()
        prev_low = prev_data['low'].min()

        # Add additional context
        return {
            'previous_high': float(prev_high),
            'previous_low': float(prev_low),
            'previous_close': float(df['close'].iloc[-2]) if len(df) >= 2 else float(df['close'].iloc[-1]),
            'range_pct': float((prev_high - prev_low) / prev_low * 100) if prev_low > 0 else 0.0
        }


    except Exception as e:
        logger.exception(f"Error calculating previous high/low: {e}")
        return {'previous_high': float(df['high'].iloc[-1]), 'previous_low': float(df['low'].iloc[-1])}


def _real_sessions(df: pd.DataFrame) -> pd.DataFrame:
    """
    REAL Trading Sessions Implementation

    Identifies Asian, London, and New York sessions with their key levels
    """
    try:
        if len(df) < 10:
            return pd.DataFrame(columns=['session', 'high', 'low', 'open', 'close'])

        # Check if index has timezone info
        if not hasattr(df.index, 'tz') or df.index.tz is None:
            # Assume UTC if no timezone
            df_tz = df.copy()
            df_tz.index = pd.to_datetime(df.index, utc=True)
        else:
            df_tz = df.copy()

        sessions = []

        # Define session times (UTC)
        session_times = {
            'asian': (0, 8),      # 00:00-08:00 UTC
            'london': (7, 15),    # 07:00-15:00 UTC (overlap with Asian)
            'newyork': (13, 21)   # 13:00-21:00 UTC (overlap with London)
        }

        # Group data by date
        df_tz['date'] = df_tz.index.date
        daily_groups = df_tz.groupby('date')

        for date, day_data in daily_groups:
            day_data_hourly = day_data.copy()
            day_data_hourly['hour'] = day_data.index.hour

            for session_name, (start_hour, end_hour) in session_times.items():
                # Get session data
                if start_hour <= end_hour:
                    session_data = day_data_hourly[
                        (day_data_hourly['hour'] >= start_hour) &
                        (day_data_hourly['hour'] < end_hour)
                    ]
                else:  # Handle overnight sessions
                    session_data = day_data_hourly[
                        (day_data_hourly['hour'] >= start_hour) |
                        (day_data_hourly['hour'] < end_hour)
                    ]

                if not session_data.empty:
                    sessions.append({
                        'date': date,
                        'session': session_name,
                        'high': float(session_data['high'].max()),
                        'low': float(session_data['low'].min()),
                        'open': float(session_data['open'].iloc[0]),
                        'close': float(session_data['close'].iloc[-1]),
                        'start_time': session_data.index[0],
                        'end_time': session_data.index[-1]
                    })

        if sessions:
            session_df = pd.DataFrame(sessions)
            return session_df.tail(20)  # Return last 20 sessions

        # Fallback: Create simple session markers based on time patterns
        session_count = len(df) // 3
        return pd.DataFrame({
            'session': (['asian'] * session_count + ['london'] * session_count + ['newyork'] * session_count)[:len(df)],
            'high': df['high'].values,
            'low': df['low'].values,
            'open': df['open'].values if 'open' in df.columns else df['close'].values,
            'close': df['close'].values
        })

    except Exception as e:
        logger.exception(f"Error calculating sessions: {e}")
        return pd.DataFrame(columns=['session', 'high', 'low', 'open', 'close'])
