"""
Moneyness-aware Greeks Calculator
Computes Greeks with moneyness integration from instrument service
"""
import logging
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime

# Follow existing pattern for PyVolLib usage
from app.core.greeks_model_config import get_greeks_model_config
from app.errors import UnsupportedModelError

from app.services.instrument_service_client import InstrumentServiceClient
from app.services.greeks_calculator import GreeksCalculator


class MoneynessAwareGreeksCalculator:
    """
    Enhanced Greeks calculator with moneyness integration
    Provides moneyness-based Greeks aggregation and analysis
    """
    
    def __init__(self, instrument_client: InstrumentServiceClient = None):
        self.instrument_client = instrument_client  # Should be provided via dependency injection
        self.greeks_calculator = GreeksCalculator(None)  # timescale_session will be initialized later
        self._moneyness_cache = {}
        self._cache_ttl = 60  # 1 minute cache for moneyness data
        self.logger = logging.getLogger(__name__)
        
        # Initialize Greeks model configuration following existing pattern
        self._model_config = get_greeks_model_config()
        self._iv_function = None
        self._greeks_functions = {}
        self._load_model_functions()
    
    def _load_model_functions(self):
        """Load PyVolLib functions based on configured model (following existing pattern)"""
        try:
            model_name = self._model_config.model_name
            self.logger.info(f"Loading PyVolLib model: {model_name}")
            
            if model_name == "black_scholes_merton":
                from py_vollib.black_scholes_merton.implied_volatility import implied_volatility
                from py_vollib.black_scholes_merton.greeks import (
                    delta, gamma, theta, vega, rho
                )
                self._iv_function = implied_volatility
                self._greeks_functions = {
                    'delta': delta, 'gamma': gamma, 'theta': theta,
                    'vega': vega, 'rho': rho
                }
                
            elif model_name == "black_scholes":
                from py_vollib.black_scholes.implied_volatility import implied_volatility
                from py_vollib.black_scholes.greeks import (
                    delta, gamma, theta, vega, rho
                )
                self._iv_function = implied_volatility
                self._greeks_functions = {
                    'delta': delta, 'gamma': gamma, 'theta': theta,
                    'vega': vega, 'rho': rho
                }
                
            elif model_name == "black76":
                from py_vollib.black_76.implied_volatility import implied_volatility
                from py_vollib.black_76.greeks import (
                    delta, gamma, theta, vega, rho
                )
                self._iv_function = implied_volatility
                self._greeks_functions = {
                    'delta': delta, 'gamma': gamma, 'theta': theta,
                    'vega': vega, 'rho': rho
                }
                
            else:
                raise UnsupportedModelError(f"Unsupported model: {model_name}")
                
            self.logger.info(f"PyVolLib model loaded successfully: {model_name}")
            
        except ImportError as e:
            self.logger.warning(f"PyVolLib not available: {e}")
            self._iv_function = None
            self._greeks_functions = {}
        except Exception as e:
            self.logger.error(f"Failed to load PyVolLib model: {e}")
            self._iv_function = None
            self._greeks_functions = {}
        
    async def calculate_moneyness_greeks(
        self,
        underlying_symbol: str,
        spot_price: float,
        moneyness_level: str,
        expiry_date: Optional[str] = None,
        risk_free_rate: float = 0.05,
        dividend_yield: float = 0.0
    ) -> Dict[str, Any]:
        """
        Calculate aggregated Greeks for a moneyness level
        
        Args:
            underlying_symbol: Underlying instrument symbol
            spot_price: Current spot price
            moneyness_level: Target moneyness (ATM, OTM5delta, etc.)
            expiry_date: Optional expiry date filter
            risk_free_rate: Risk-free interest rate
            dividend_yield: Dividend yield
            
        Returns:
            Aggregated Greeks for the moneyness level
        """
        try:
            # Get options at the specified moneyness level
            options = await self.instrument_client.get_strikes_by_moneyness(
                underlying_symbol,
                moneyness_level,
                expiry_date
            )
            
            if not options:
                self.logger.info("No options found for %s at %s", underlying_symbol, moneyness_level)
                return self._empty_moneyness_result(moneyness_level)
                
            # Calculate Greeks for each option
            results = []
            for option in options:
                greeks = await self._calculate_single_option_greeks(
                    option,
                    spot_price,
                    risk_free_rate,
                    dividend_yield
                )
                if greeks:
                    results.append(greeks)
                    
            # Aggregate results
            return self._aggregate_moneyness_greeks(
                moneyness_level,
                results,
                spot_price,
                underlying_symbol
            )
            
        except Exception as e:
            self.logger.exception("Error calculating moneyness Greeks: %s", e)
            return self._empty_moneyness_result(moneyness_level)
            
    async def calculate_atm_iv(
        self,
        underlying_symbol: str,
        spot_price: float,
        expiry_date: str,
        timeframe: str = "5m"
    ) -> Dict[str, Any]:
        """
        Calculate ATM implied volatility with historical data
        
        Args:
            underlying_symbol: Underlying symbol
            spot_price: Current spot price
            expiry_date: Option expiry
            timeframe: Time interval for calculations
            
        Returns:
            ATM IV data with statistics
        """
        try:
            # Get ATM options
            atm_options = await self.instrument_client.get_strikes_by_moneyness(
                underlying_symbol,
                "ATM",
                expiry_date
            )
            
            if not atm_options:
                return {
                    "underlying": underlying_symbol,
                    "moneyness": "ATM",
                    "iv": None,
                    "timestamp": datetime.utcnow().isoformat(),
                    "error": "No ATM options found"
                }
                
            # Calculate IV for calls and puts
            call_ivs = []
            put_ivs = []
            
            for option in atm_options:
                try:
                    # Extract option details
                    strike = option.get('strike_price')
                    option_type = option.get('option_type', '').upper()  # 'CE' or 'PE'
                    market_price = option.get('last_price') or option.get('close_price')
                    
                    if not all([strike, option_type, market_price]):
                        self.logger.warning("Missing option data for IV calculation: %s", option.get("instrument_key"))
                        continue
                    
                    # Calculate time to expiry in years
                    expiry_dt = datetime.strptime(expiry_date, '%Y-%m-%d')
                    time_to_expiry = (expiry_dt - datetime.now()).days / 365.25
                    
                    if time_to_expiry <= 0:
                        self.logger.warning("Option expired, skipping IV calculation")
                        continue
                    
                    # Get risk-free rate (simplified - could be enhanced with real rate data)
                    risk_free_rate = 0.06  # 6% default risk-free rate
                    
                    # Calculate IV using configured PyVolLib model
                    calculated_iv = self._calculate_implied_volatility(
                        market_price, spot_price, strike, time_to_expiry, 
                        risk_free_rate, option_type
                    )
                    
                    if calculated_iv and calculated_iv > 0:
                        if option_type in ['CE', 'CALL']:
                            call_ivs.append(calculated_iv)
                        elif option_type in ['PE', 'PUT']:
                            put_ivs.append(calculated_iv)
                        
                        self.logger.info("Calculated IV %.4f for %s", calculated_iv, option.get("instrument_key"))
                    
                except Exception as e:
                    self.logger.warning("Failed to calculate IV for option %s: %s", option.get("instrument_key"), e)
                    continue
                    
            # Average IVs
            avg_call_iv = np.mean(call_ivs) if call_ivs else None
            avg_put_iv = np.mean(put_ivs) if put_ivs else None
            atm_iv = np.mean([avg_call_iv, avg_put_iv]) if avg_call_iv and avg_put_iv else (avg_call_iv or avg_put_iv)
            
            return {
                "underlying": underlying_symbol,
                "moneyness": "ATM",
                "expiry": expiry_date,
                "timeframe": timeframe,
                "iv": float(atm_iv) if atm_iv else None,
                "call_iv": float(avg_call_iv) if avg_call_iv else None,
                "put_iv": float(avg_put_iv) if avg_put_iv else None,
                "iv_skew": float(avg_put_iv - avg_call_iv) if avg_call_iv and avg_put_iv else None,
                "timestamp": datetime.utcnow().isoformat(),
                "option_count": len(atm_options)
            }
            
        except Exception as e:
            self.logger.exception("Error calculating ATM IV: %s", e)
            return {
                "underlying": underlying_symbol,
                "moneyness": "ATM",
                "iv": None,
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            }
    
    def _calculate_implied_volatility(
        self, 
        market_price: float,
        spot_price: float, 
        strike: float, 
        time_to_expiry: float, 
        risk_free_rate: float, 
        option_type: str
    ) -> Optional[float]:
        """
        Calculate implied volatility using configured PyVolLib model.
        
        Args:
            market_price: Current option market price
            spot_price: Current underlying price
            strike: Option strike price  
            time_to_expiry: Time to expiry in years
            risk_free_rate: Risk-free interest rate
            option_type: 'CE'/'CALL' or 'PE'/'PUT'
            
        Returns:
            Implied volatility or None if calculation fails
        """
        try:
            if not self._iv_function:
                self.logger.warning("PyVolLib IV function not available")
                return None
                
            # Normalize option type to PyVolLib flag
            flag = 'c' if option_type in ['CE', 'CALL'] else 'p'
            
            # Get model parameters
            dividend_yield = self._model_config.parameters.dividend_yield
            
            # Use configured PyVolLib model for IV calculation
            if self._model_config.model_name == "black_scholes_merton":
                iv = self._iv_function(
                    price=market_price,
                    S=spot_price,
                    K=strike, 
                    t=time_to_expiry,
                    r=risk_free_rate,
                    q=dividend_yield,
                    flag=flag
                )
            else:
                # Black-Scholes or Black76 models
                iv = self._iv_function(
                    price=market_price,
                    S=spot_price,
                    K=strike, 
                    t=time_to_expiry,
                    r=risk_free_rate,
                    flag=flag
                )
            
            # Validate result
            min_vol = self._model_config.parameters.volatility_min
            max_vol = self._model_config.parameters.volatility_max
            
            if iv and min_vol <= iv <= max_vol:
                return float(iv)
            else:
                self.logger.warning("IV out of valid range: %.6f (valid: %.3f-%.3f)", 
                                  iv, min_vol, max_vol)
                return None
                
        except Exception as e:
            self.logger.warning("IV calculation failed: %s", e)
            return None
            
    async def calculate_otm_delta_greeks(
        self,
        underlying_symbol: str,
        spot_price: float,
        delta_target: float,
        option_type: str,
        expiry_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate Greeks for OTM options by delta
        
        Args:
            underlying_symbol: Underlying symbol
            spot_price: Current spot price
            delta_target: Target delta (e.g., 0.05)
            option_type: 'call' or 'put'
            expiry_date: Optional expiry filter
            
        Returns:
            Greeks for options matching delta criteria
        """
        try:
            # Get OTM options by delta
            options = await self.instrument_client.get_otm_delta_strikes(
                underlying_symbol,
                delta_target,
                option_type,
                expiry_date
            )
            
            if not options:
                return {
                    "underlying": underlying_symbol,
                    "delta_target": delta_target,
                    "option_type": option_type,
                    "greeks": None,
                    "error": "No matching options found"
                }
                
            # Calculate Greeks for matching options
            results = []
            for option in options:
                greeks = await self._calculate_single_option_greeks(
                    option,
                    spot_price,
                    risk_free_rate=0.05,
                    dividend_yield=0.0
                )
                if greeks and abs(greeks.delta - delta_target) < 0.02:  # Within 2% of target
                    results.append(greeks)
                    
            # Return best match
            if results:
                best_match = min(results, key=lambda g: abs(g.delta - delta_target))
                return {
                    "underlying": underlying_symbol,
                    "delta_target": delta_target,
                    "option_type": option_type,
                    "strike": best_match.strike_price,
                    "greeks": {
                        "delta": best_match.delta,
                        "gamma": best_match.gamma,
                        "theta": best_match.theta,
                        "vega": best_match.vega,
                        "rho": best_match.rho
                    },
                    "iv": best_match.implied_volatility,
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                return {
                    "underlying": underlying_symbol,
                    "delta_target": delta_target,
                    "option_type": option_type,
                    "greeks": None,
                    "error": "No options within delta tolerance"
                }
                
        except Exception as e:
            self.logger.exception("Error calculating OTM delta Greeks: %s", e)
            return {
                "underlying": underlying_symbol,
                "delta_target": delta_target,
                "option_type": option_type,
                "greeks": None,
                "error": str(e)
            }
            
    async def get_moneyness_distribution(
        self,
        underlying_symbol: str,
        spot_price: float,
        expiry_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get Greeks distribution across moneyness levels
        
        Args:
            underlying_symbol: Underlying symbol
            spot_price: Current spot price
            expiry_date: Optional expiry filter
            
        Returns:
            Greeks distribution by moneyness
        """
        moneyness_levels = [
            "DITM", "ITM", "ATM", "OTM", "DOTM",
            "OTM5delta", "OTM10delta", "OTM25delta"
        ]
        
        distribution = {}
        
        for level in moneyness_levels:
            greeks = await self.calculate_moneyness_greeks(
                underlying_symbol,
                spot_price,
                level,
                expiry_date
            )
            distribution[level] = greeks
            
        return {
            "underlying": underlying_symbol,
            "spot_price": spot_price,
            "expiry": expiry_date,
            "distribution": distribution,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    async def _calculate_single_option_greeks(
        self,
        option_data: Dict[str, Any],
        spot_price: float,
        risk_free_rate: float,
        dividend_yield: float
    ) -> Optional[Dict[str, Any]]:
        """Calculate Greeks for a single option"""
        try:
            strike = option_data.get("strike_price", 0)
            option_type = option_data.get("option_type", "call")
            expiry_str = option_data.get("expiry_date")
            
            if not strike or not expiry_str:
                raise ValueError(f"Missing required option data: strike={strike}, expiry={expiry_str}")
                
            # Calculate time to expiry
            expiry = datetime.fromisoformat(expiry_str)
            time_to_expiry = (expiry - datetime.utcnow()).days / 365.0
            
            if time_to_expiry <= 0:
                return None
                
            # Get IV from instrument service or use default
            iv = await self.instrument_client.get_atm_iv(
                option_data.get("underlying_symbol"),
                expiry_str,
                spot_price
            ) or 0.25
            
            # Calculate Greeks
            return self.greeks_calculator.calculate_greeks(
                spot_price=spot_price,
                strike_price=strike,
                time_to_expiry=time_to_expiry,
                volatility=iv,
                risk_free_rate=risk_free_rate,
                dividend_yield=dividend_yield,
                option_type=option_type
            )
            
        except Exception as e:
            self.logger.error("Error calculating Greeks for option: %s", e)
            from app.errors import GreeksCalculationError
            raise GreeksCalculationError(f"Failed to calculate Greeks: {str(e)}") from e
            
    def _aggregate_moneyness_greeks(
        self,
        moneyness_level: str,
        results: List[Dict[str, Any]],
        spot_price: float,
        underlying_symbol: str
    ) -> Dict[str, Any]:
        """Aggregate Greeks results for a moneyness level"""
        if not results:
            return self._empty_moneyness_result(moneyness_level)
            
        # Separate calls and puts
        calls = [r for r in results if r.option_type == "call"]
        puts = [r for r in results if r.option_type == "put"]
        
        # Calculate aggregates
        def aggregate_greeks(greeks_list):
            if not greeks_list:
                return None
            return {
                "delta": np.mean([g.delta for g in greeks_list]),
                "gamma": np.mean([g.gamma for g in greeks_list]),
                "theta": np.mean([g.theta for g in greeks_list]),
                "vega": np.mean([g.vega for g in greeks_list]),
                "rho": np.mean([g.rho for g in greeks_list]),
                "iv": np.mean([g.implied_volatility for g in greeks_list]),
                "count": len(greeks_list)
            }
            
        return {
            "underlying": underlying_symbol,
            "spot_price": spot_price,
            "moneyness_level": moneyness_level,
            "timestamp": datetime.utcnow().isoformat(),
            "aggregated_greeks": {
                "all": aggregate_greeks(results),
                "calls": aggregate_greeks(calls),
                "puts": aggregate_greeks(puts)
            },
            "strikes": {
                "min": min(r.strike_price for r in results),
                "max": max(r.strike_price for r in results),
                "count": len(set(r.strike_price for r in results))
            }
        }
        
    def _empty_moneyness_result(self, moneyness_level: str) -> Dict[str, Any]:
        """Return empty result structure"""
        return {
            "moneyness_level": moneyness_level,
            "timestamp": datetime.utcnow().isoformat(),
            "aggregated_greeks": {
                "all": None,
                "calls": None,
                "puts": None
            },
            "error": "No data available"
        }
