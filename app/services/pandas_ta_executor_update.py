"""Updates to pandas_ta_executor for custom indicators"""
import pandas as pd
from datetime import datetime
from typing import Dict
from app.utils.logging_utils import log_exception


def validate_indicator_parameters(self, indicator_name: str, parameters: Dict) -> Dict:
    """Validate and adjust parameters for specific indicators including custom ones"""
    try:
        # Default parameters for common indicators
        defaults = {
            'sma': {'length': 20},
            'ema': {'length': 20},
            'rsi': {'length': 14},
            'macd': {'fast': 12, 'slow': 26, 'signal': 9},
            'bb': {'length': 20, 'std': 2},
            'stoch': {'k': 14, 'd': 3},
            'adx': {'length': 14},
            'atr': {'length': 14},
            'cci': {'length': 20},
            'mfi': {'length': 14},
            'willr': {'length': 14},
            # Custom indicators
            'anchored_vwap': {},  # Requires anchor_datetime
            'swing_high': {'left_bars': 2, 'right_bars': 2},
            'swing_low': {'left_bars': 2, 'right_bars': 2},
            'combined_premium': {},
            'premium_ratio': {}
        }
        
        # Apply defaults
        if indicator_name in defaults:
            for key, value in defaults[indicator_name].items():
                if key not in parameters:
                    parameters[key] = value
        
        # Special validation for anchored VWAP
        if indicator_name == 'anchored_vwap':
            if 'anchor_datetime' not in parameters:
                raise ValueError("anchored_vwap requires anchor_datetime parameter")
            
            # Validate datetime format
            try:
                pd.to_datetime(parameters['anchor_datetime'])
            except:
                raise ValueError(f"Invalid anchor_datetime format: {parameters['anchor_datetime']}")
        
        # Special validation for swing indicators
        if indicator_name in ['swing_high', 'swing_low']:
            if 'left_bars' in parameters:
                parameters['left_bars'] = max(1, int(parameters['left_bars']))
            if 'right_bars' in parameters:
                parameters['right_bars'] = max(1, int(parameters['right_bars']))
        
        # Ensure minimum length for period-based indicators
        if 'length' in parameters:
            parameters['length'] = max(1, int(parameters.get('length', 14)))
        
        return parameters
        
    except Exception as e:
        log_exception(f"Failed to validate parameters for {indicator_name}: {e}")
        raise


# Additional method to handle custom indicator results
def extract_custom_indicator_results(self, indicator_name: str, result_df: pd.DataFrame, output_key: str) -> any:
    """Extract results for custom indicators"""
    
    if indicator_name == 'anchored_vwap':
        # Anchored VWAP returns a single series
        if 'anchored_vwap' in result_df.columns:
            value = result_df['anchored_vwap'].iloc[-1]
            return float(value) if pd.notna(value) else None
    
    elif indicator_name in ['swing_high', 'swing_low']:
        # Swing indicators return sparse series with NaN for non-swing points
        col_name = indicator_name
        if col_name in result_df.columns:
            # Get the most recent swing point
            series = result_df[col_name]
            recent_swings = series.dropna().tail(1)
            
            if not recent_swings.empty:
                return {
                    'price': float(recent_swings.iloc[-1]),
                    'timestamp': recent_swings.index[-1].isoformat() if hasattr(recent_swings.index[-1], 'isoformat') else str(recent_swings.index[-1])
                }
            else:
                return None
    
    elif indicator_name == 'combined_premium':
        if 'combined_premium' in result_df.columns:
            value = result_df['combined_premium'].iloc[-1]
            return float(value) if pd.notna(value) else None
    
    elif indicator_name == 'premium_ratio':
        if 'premium_ratio' in result_df.columns:
            value = result_df['premium_ratio'].iloc[-1]
            return float(value) if pd.notna(value) else None
    
    return None