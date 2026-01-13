"""
Local Moneyness Calculator for Signal Service
Performs real-time moneyness calculations without external dependencies
"""
import math
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from enum import Enum
import numpy as np

from app.utils.logging_utils import log_info, log_error


class MoneynessLevel(Enum):
    """Moneyness level classifications"""
    DITM = "DITM"          # Deep In The Money
    ITM = "ITM"            # In The Money
    ATM = "ATM"            # At The Money
    OTM = "OTM"            # Out of The Money
    DOTM = "DOTM"          # Deep Out of The Money
    OTM5DELTA = "OTM5delta"    # 5-delta OTM
    OTM10DELTA = "OTM10delta"  # 10-delta OTM
    OTM25DELTA = "OTM25delta"  # 25-delta OTM


class LocalMoneynessCalculator:
    """
    High-performance moneyness calculator for Signal Service
    Optimized for real-time calculations without external dependencies
    """
    
    def __init__(self):
        # Moneyness thresholds (can be loaded from config)
        self.thresholds = {
            "DITM": {"min": 0.0, "max": 0.85},      # < 85% of spot
            "ITM": {"min": 0.85, "max": 0.97},      # 85-97% of spot
            "ATM": {"min": 0.97, "max": 1.03},      # 97-103% of spot
            "OTM": {"min": 1.03, "max": 1.15},      # 103-115% of spot
            "DOTM": {"min": 1.15, "max": float('inf')}  # > 115% of spot
        }
        
        # Cache for performance
        self._strike_cache = {}
        self._cache_ttl = 60  # 1 minute cache
        
    def calculate_moneyness_ratio(
        self,
        strike: float,
        spot_price: float,
        option_type: str
    ) -> float:
        """
        Calculate moneyness ratio
        
        Args:
            strike: Strike price
            spot_price: Current spot price
            option_type: 'call' or 'put'
            
        Returns:
            Moneyness ratio
        """
        if option_type.lower() == 'call':
            return strike / spot_price
        else:  # put
            return spot_price / strike
            
    def classify_moneyness(
        self,
        strike: float,
        spot_price: float,
        option_type: str
    ) -> MoneynessLevel:
        """
        Classify option moneyness level
        
        Args:
            strike: Strike price
            spot_price: Current spot price
            option_type: 'call' or 'put'
            
        Returns:
            Moneyness level
        """
        ratio = self.calculate_moneyness_ratio(strike, spot_price, option_type)
        
        # For puts, invert the classification
        if option_type.lower() == 'put':
            if ratio > 1.15:
                return MoneynessLevel.DITM
            elif ratio > 1.03:
                return MoneynessLevel.ITM
            elif ratio > 0.97:
                return MoneynessLevel.ATM
            elif ratio > 0.85:
                return MoneynessLevel.OTM
            else:
                return MoneynessLevel.DOTM
        else:  # call
            if ratio < 0.85:
                return MoneynessLevel.DITM
            elif ratio < 0.97:
                return MoneynessLevel.ITM
            elif ratio < 1.03:
                return MoneynessLevel.ATM
            elif ratio < 1.15:
                return MoneynessLevel.OTM
            else:
                return MoneynessLevel.DOTM
                
    def find_strikes_by_moneyness(
        self,
        spot_price: float,
        available_strikes: List[float],
        moneyness_level: str,
        option_type: str
    ) -> List[float]:
        """
        Find strikes matching moneyness level
        
        Args:
            spot_price: Current spot price
            available_strikes: List of available strikes
            moneyness_level: Target moneyness level
            option_type: 'call' or 'put'
            
        Returns:
            List of strikes matching moneyness
        """
        matching_strikes = []
        
        for strike in available_strikes:
            level = self.classify_moneyness(strike, spot_price, option_type)
            if level.value == moneyness_level:
                matching_strikes.append(strike)
                
        return sorted(matching_strikes)
        
    def find_atm_strike(
        self,
        spot_price: float,
        available_strikes: List[float]
    ) -> float:
        """
        Find the ATM strike
        
        Args:
            spot_price: Current spot price
            available_strikes: List of available strikes
            
        Returns:
            ATM strike price
        """
        # Find closest strike to spot
        if not available_strikes:
            return spot_price
            
        return min(available_strikes, key=lambda x: abs(x - spot_price))
        
    def find_strikes_by_delta(
        self,
        spot_price: float,
        available_strikes: List[float],
        target_delta: float,
        option_type: str,
        greeks_data: Dict[float, Dict[str, float]]
    ) -> Optional[float]:
        """
        Find strike by target delta
        
        Args:
            spot_price: Current spot price
            available_strikes: List of available strikes
            target_delta: Target delta (e.g., 0.05 for 5-delta)
            option_type: 'call' or 'put'
            greeks_data: Greeks data by strike {strike: {delta, gamma, ...}}
            
        Returns:
            Strike matching target delta
        """
        best_strike = None
        min_delta_diff = float('inf')
        
        for strike in available_strikes:
            if strike in greeks_data:
                delta = greeks_data[strike].get('delta', 0)
                
                # For puts, delta is negative
                if option_type.lower() == 'put':
                    delta = abs(delta)
                    
                delta_diff = abs(delta - target_delta)
                if delta_diff < min_delta_diff:
                    min_delta_diff = delta_diff
                    best_strike = strike
                    
        return best_strike
        
    def calculate_moneyness_weights(
        self,
        strikes: List[float],
        spot_price: float,
        option_type: str
    ) -> Dict[float, float]:
        """
        Calculate weights for aggregating Greeks across strikes
        
        Args:
            strikes: List of strikes in moneyness bucket
            spot_price: Current spot price
            option_type: 'call' or 'put'
            
        Returns:
            Weights by strike for aggregation
        """
        if not strikes:
            return {}
            
        # Calculate distances from spot
        distances = [abs(strike - spot_price) for strike in strikes]
        max_distance = max(distances) if distances else 1.0
        
        # Calculate weights (inverse distance weighting)
        weights = {}
        total_weight = 0
        
        for strike, distance in zip(strikes, distances):
            # Closer to spot gets higher weight
            weight = 1.0 - (distance / (max_distance + 1))
            weights[strike] = weight
            total_weight += weight
            
        # Normalize weights
        if total_weight > 0:
            for strike in weights:
                weights[strike] /= total_weight
                
        return weights
        
    def aggregate_greeks_by_moneyness(
        self,
        moneyness_level: str,
        strikes: List[float],
        greeks_by_strike: Dict[float, Dict[str, float]],
        spot_price: float,
        option_type: str
    ) -> Dict[str, float]:
        """
        Aggregate Greeks for a moneyness level
        
        Args:
            moneyness_level: Moneyness level
            strikes: Strikes at this moneyness
            greeks_by_strike: Greeks data by strike
            spot_price: Current spot price
            option_type: 'call' or 'put'
            
        Returns:
            Aggregated Greeks
        """
        if not strikes or not greeks_by_strike:
            return {
                'delta': 0, 'gamma': 0, 'theta': 0, 
                'vega': 0, 'rho': 0, 'iv': 0
            }
            
        # Get weights for aggregation
        weights = self.calculate_moneyness_weights(strikes, spot_price, option_type)
        
        # Aggregate Greeks
        aggregated = {
            'delta': 0, 'gamma': 0, 'theta': 0,
            'vega': 0, 'rho': 0, 'iv': 0
        }
        
        for strike in strikes:
            if strike in greeks_by_strike and strike in weights:
                weight = weights[strike]
                greeks = greeks_by_strike[strike]
                
                for greek in aggregated:
                    if greek in greeks:
                        aggregated[greek] += greeks[greek] * weight
                        
        return aggregated
        
    def get_strike_distribution(
        self,
        underlying: str,
        spot_price: float,
        expiry_date: str
    ) -> List[float]:
        """
        Get likely strikes for an underlying
        
        This is a simplified version - in production, this would
        integrate with exchange rules or historical data
        """
        # Common strike intervals by price range
        if spot_price < 100:
            interval = 1
        elif spot_price < 1000:
            interval = 5
        elif spot_price < 10000:
            interval = 50
        else:
            interval = 100
            
        # Generate strikes around spot (±20%)
        min_strike = int(spot_price * 0.8 / interval) * interval
        max_strike = int(spot_price * 1.2 / interval) * interval
        
        strikes = []
        current = min_strike
        while current <= max_strike:
            strikes.append(float(current))
            current += interval
            
        return strikes
        
    def calculate_iv_skew_by_moneyness(
        self,
        greeks_by_moneyness: Dict[str, Dict[str, float]]
    ) -> Dict[str, float]:
        """
        Calculate IV skew metrics across moneyness levels
        
        Args:
            greeks_by_moneyness: Greeks aggregated by moneyness level
            
        Returns:
            Skew metrics
        """
        skew_metrics = {}
        
        # Get ATM IV as reference
        atm_iv = greeks_by_moneyness.get('ATM', {}).get('iv', 0)
        
        if atm_iv > 0:
            # Calculate skew relative to ATM
            for level, greeks in greeks_by_moneyness.items():
                if level != 'ATM':
                    level_iv = greeks.get('iv', 0)
                    if level_iv > 0:
                        skew_metrics[f'{level}_skew'] = level_iv - atm_iv
                        
            # Risk reversal (25-delta call IV - 25-delta put IV)
            if 'OTM25DELTA' in greeks_by_moneyness:
                call_25d_iv = greeks_by_moneyness['OTM25DELTA'].get('iv', 0)
                # In a full implementation, we'd have separate call/put data
                skew_metrics['risk_reversal_25d'] = call_25d_iv - atm_iv
                
        return skew_metrics