"""Custom technical indicators not available in pandas_ta"""
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

import numpy as np
import pandas as pd
import pandas_ta as ta

logger = logging.getLogger(__name__)


class CustomIndicators:
    """Custom technical indicators not available in pandas_ta"""
    
    @staticmethod
    def anchored_vwap(df: pd.DataFrame, 
                     anchor_datetime: str,
                     high_col: str = 'high',
                     low_col: str = 'low', 
                     close_col: str = 'close',
                     volume_col: str = 'volume') -> pd.Series:
        """
        Calculate Anchored VWAP from a specific datetime
        
        Args:
            df: DataFrame with OHLCV data
            anchor_datetime: Datetime string to anchor VWAP calculation
            
        Returns:
            Series with anchored VWAP values
        """
        try:
            # Convert anchor_datetime to pandas datetime
            anchor_dt = pd.to_datetime(anchor_datetime)
            
            # Find anchor index
            if anchor_dt not in df.index:
                # Find nearest timestamp
                idx = df.index.get_indexer([anchor_dt], method='nearest')[0]
            else:
                idx = df.index.get_loc(anchor_dt)
            
            # Initialize result series
            result = pd.Series(index=df.index, dtype=float)
            result[:idx] = np.nan  # No VWAP before anchor
            
            # Calculate from anchor point
            df_subset = df.iloc[idx:]
            
            # Calculate typical price
            typical_price = (df_subset[high_col] + df_subset[low_col] + df_subset[close_col]) / 3
            
            # Calculate cumulative volume-weighted price
            cum_volume = df_subset[volume_col].cumsum()
            cum_vp = (typical_price * df_subset[volume_col]).cumsum()
            
            # Calculate anchored VWAP
            avwap = cum_vp / cum_volume
            
            # Fill result
            result.iloc[idx:] = avwap
            
            return result
            
        except Exception as e:
            logger.exception("Error calculating anchored VWAP: %s", e)
            return pd.Series(index=df.index, dtype=float)
    
    @staticmethod
    def swing_high(df: pd.DataFrame,
                  left_bars: int = 2,
                  right_bars: int = 2,
                  price_col: str = 'high') -> pd.Series:
        """
        Detect swing highs in price data
        
        Args:
            df: DataFrame with price data
            left_bars: Number of bars to left that must be lower
            right_bars: Number of bars to right that must be lower
            price_col: Column to analyze for swings
            
        Returns:
            Series with swing high prices (NaN for non-swing points)
        """
        try:
            result = pd.Series(index=df.index, dtype=float)
            prices = df[price_col].values
            
            for i in range(left_bars, len(prices) - right_bars):
                is_swing_high = True
                current_price = prices[i]
                
                # Check left side
                for j in range(1, left_bars + 1):
                    if prices[i - j] >= current_price:
                        is_swing_high = False
                        break
                
                # Check right side
                if is_swing_high:
                    for j in range(1, right_bars + 1):
                        if prices[i + j] >= current_price:
                            is_swing_high = False
                            break
                
                if is_swing_high:
                    result.iloc[i] = current_price
                else:
                    result.iloc[i] = np.nan
                    
            return result
            
        except Exception as e:
            logger.exception("Error detecting swing highs: %s", e)
            return pd.Series(index=df.index, dtype=float)
    
    @staticmethod
    def swing_low(df: pd.DataFrame,
                 left_bars: int = 2,
                 right_bars: int = 2,
                 price_col: str = 'low') -> pd.Series:
        """
        Detect swing lows in price data
        
        Args:
            df: DataFrame with price data
            left_bars: Number of bars to left that must be higher
            right_bars: Number of bars to right that must be higher
            price_col: Column to analyze for swings
            
        Returns:
            Series with swing low prices (NaN for non-swing points)
        """
        try:
            result = pd.Series(index=df.index, dtype=float)
            prices = df[price_col].values
            
            for i in range(left_bars, len(prices) - right_bars):
                is_swing_low = True
                current_price = prices[i]
                
                # Check left side
                for j in range(1, left_bars + 1):
                    if prices[i - j] <= current_price:
                        is_swing_low = False
                        break
                
                # Check right side
                if is_swing_low:
                    for j in range(1, right_bars + 1):
                        if prices[i + j] <= current_price:
                            is_swing_low = False
                            break
                
                if is_swing_low:
                    result.iloc[i] = current_price
                else:
                    result.iloc[i] = np.nan
                    
            return result
            
        except Exception as e:
            logger.exception("Error detecting swing lows: %s", e)
            return pd.Series(index=df.index, dtype=float)
    
    @staticmethod
    def combined_premium(df: pd.DataFrame,
                        call_col: str = 'call_price',
                        put_col: str = 'put_price') -> pd.Series:
        """
        Calculate combined option premium (call + put)
        Useful for straddle/strangle analysis
        
        Args:
            df: DataFrame with option prices
            call_col: Column with call prices
            put_col: Column with put prices
            
        Returns:
            Series with combined premium values
        """
        try:
            if call_col not in df.columns or put_col not in df.columns:
                raise ValueError(f"Required columns {call_col} or {put_col} not found")
                
            return df[call_col] + df[put_col]
            
        except Exception as e:
            logger.exception("Error calculating combined premium: %s", e)
            return pd.Series(index=df.index, dtype=float)
    
    @staticmethod
    def premium_ratio(df: pd.DataFrame,
                     call_col: str = 'call_price',
                     put_col: str = 'put_price') -> pd.Series:
        """
        Calculate call/put premium ratio
        Useful for skew analysis
        
        Args:
            df: DataFrame with option prices
            call_col: Column with call prices
            put_col: Column with put prices
            
        Returns:
            Series with premium ratio values
        """
        try:
            if call_col not in df.columns or put_col not in df.columns:
                raise ValueError(f"Required columns {call_col} or {put_col} not found")
                
            # Avoid division by zero
            put_prices = df[put_col].replace(0, np.nan)
            return df[call_col] / put_prices
            
        except Exception as e:
            logger.exception("Error calculating premium ratio: %s", e)
            return pd.Series(index=df.index, dtype=float)


def register_custom_indicators():
    """Register custom indicators with pandas_ta"""
    try:
        # Register anchored VWAP
        ta.register_custom_indicator(
            name="anchored_vwap",
            function=CustomIndicators.anchored_vwap,
            category="overlap"
        )
        
        # Register swing high
        ta.register_custom_indicator(
            name="swing_high",
            function=CustomIndicators.swing_high,
            category="volatility"
        )
        
        # Register swing low
        ta.register_custom_indicator(
            name="swing_low", 
            function=CustomIndicators.swing_low,
            category="volatility"
        )
        
        # Register combined premium
        ta.register_custom_indicator(
            name="combined_premium",
            function=CustomIndicators.combined_premium,
            category="other"
        )
        
        # Register premium ratio
        ta.register_custom_indicator(
            name="premium_ratio",
            function=CustomIndicators.premium_ratio,
            category="other"
        )
        
        logger.info("Custom indicators registered successfully")
    
    except Exception as e:
        logger.exception("Error registering custom indicators: %s", e)


# Additional utility functions for indicator calculations
class IndicatorUtils:
    """Utility functions for indicator calculations"""
    
    @staticmethod
    def find_swing_highs(df: pd.DataFrame, window: int = 10) -> List[Dict[str, Any]]:
        """
        Find all swing highs in the data with timestamps
        
        Args:
            df: DataFrame with OHLCV data
            window: Window size for swing detection
            
        Returns:
            List of dicts with swing high info
        """
        swings = CustomIndicators.swing_high(df, left_bars=window//2, right_bars=window//2)
        
        swing_points = []
        for idx, value in swings.items():
            if not pd.isna(value):
                swing_points.append({
                    'timestamp': idx,
                    'price': value,
                    'type': 'swing_high'
                })
                
        return swing_points
    
    @staticmethod
    def find_recent_swing_high(df: pd.DataFrame, lookback_periods: int = 50) -> Optional[Dict[str, Any]]:
        """
        Find the most recent swing high
        
        Args:
            df: DataFrame with OHLCV data
            lookback_periods: Number of periods to look back
            
        Returns:
            Dict with swing high info or None
        """
        # Get recent data
        recent_df = df.tail(lookback_periods)
        
        # Find swing highs
        swing_highs = IndicatorUtils.find_swing_highs(recent_df)
        
        if swing_highs:
            # Return the most recent one
            return swing_highs[-1]
            
        return None
    
    @staticmethod
    def calculate_multiple_anchored_vwaps(df: pd.DataFrame, 
                                        anchor_points: List[str]) -> Dict[str, pd.Series]:
        """
        Calculate multiple anchored VWAPs from different anchor points
        
        Args:
            df: DataFrame with OHLCV data
            anchor_points: List of datetime strings for anchoring
            
        Returns:
            Dict of anchored VWAP series
        """
        vwaps = {}
        
        for i, anchor in enumerate(anchor_points):
            key = f"avwap_{i+1}"
            vwaps[key] = CustomIndicators.anchored_vwap(df, anchor)
            
        return vwaps
