"""
Dynamic Greeks Model Configuration
Loads pyvollib models based on config_service parameters with proper validation
"""

import logging
from typing import Dict, Callable, Optional, Any
from dataclasses import dataclass

from app.core.config import settings
from app.errors import UnsupportedModelError, ConfigurationError

logger = logging.getLogger(__name__)


@dataclass
class ModelParameters:
    """Parameters for the configured options pricing model"""
    risk_free_rate: float
    dividend_yield: float
    default_volatility: float
    volatility_min: float
    volatility_max: float


class GreeksModelConfig:
    """
    Dynamic configuration for options pricing models.
    
    Loads the appropriate pyvollib model based on config_service settings
    and provides validated parameters for Greeks calculations.
    """
    
    SUPPORTED_MODELS = {
        "black_scholes_merton": "py_vollib.black_scholes_merton.greeks",
        "black_scholes": "py_vollib.black_scholes.greeks",
        "black76": "py_vollib.black_76.greeks",
    }
    
    def __init__(self):
        self._model_name: Optional[str] = None
        self._greeks_functions: Optional[Dict[str, Callable]] = None
        self._parameters: Optional[ModelParameters] = None
        self._initialized = False
        
    def initialize(self):
        """Initialize the model configuration from config_service"""
        if self._initialized:
            return
            
        try:
            # Load model selection from config_service (MANDATORY - no defaults)
            self._model_name = settings.get_config("signal_service.options_pricing_model")
            if not self._model_name:
                raise ValueError("signal_service.options_pricing_model not found in config_service")
            
            # Validate model is supported
            if self._model_name not in self.SUPPORTED_MODELS:
                available_models = ", ".join(self.SUPPORTED_MODELS.keys())
                raise UnsupportedModelError(
                    f"Unsupported options pricing model: '{self._model_name}'. "
                    f"Supported models: {available_models}",
                    details={
                        "requested_model": self._model_name,
                        "supported_models": list(self.SUPPORTED_MODELS.keys())
                    }
                )
            
            # Load model parameters (MANDATORY from config_service - no defaults)
            risk_free_rate = settings.get_config("signal_service.model_params.risk_free_rate")
            if not risk_free_rate:
                raise ValueError("signal_service.model_params.risk_free_rate not found in config_service")
                
            dividend_yield = settings.get_config("signal_service.model_params.dividend_yield")
            if dividend_yield is None:
                raise ValueError("signal_service.model_params.dividend_yield not found in config_service")
                
            default_volatility = settings.get_config("signal_service.model_params.default_volatility")
            if not default_volatility:
                raise ValueError("signal_service.model_params.default_volatility not found in config_service")
                
            volatility_min = settings.get_config("signal_service.model_params.volatility_min")
            if not volatility_min:
                raise ValueError("signal_service.model_params.volatility_min not found in config_service")
                
            volatility_max = settings.get_config("signal_service.model_params.volatility_max")
            if not volatility_max:
                raise ValueError("signal_service.model_params.volatility_max not found in config_service")
            
            self._parameters = ModelParameters(
                risk_free_rate=float(risk_free_rate),
                dividend_yield=float(dividend_yield),
                default_volatility=float(default_volatility),
                volatility_min=float(volatility_min),
                volatility_max=float(volatility_max)
            )
            
            # Validate parameters
            self._validate_parameters()
            
            # Load the appropriate pyvollib functions
            self._greeks_functions = self._load_model_functions()
            
            self._initialized = True
            logger.info(f"Greeks model configuration initialized: {self._model_name}")
            
        except Exception as e:
            if isinstance(e, (UnsupportedModelError, ConfigurationError)):
                raise
            else:
                raise ConfigurationError(
                    f"Failed to initialize Greeks model configuration: {str(e)}",
                    details={"original_error": str(e)}
                )
    
    def _validate_parameters(self):
        """Validate model parameters are within reasonable ranges"""
        if not self._parameters:
            raise ConfigurationError("Model parameters not loaded")
            
        # Risk-free rate validation (0% to 50% annual)
        if not (0.0 <= self._parameters.risk_free_rate <= 0.50):
            raise ConfigurationError(
                f"Invalid risk_free_rate: {self._parameters.risk_free_rate}. Must be between 0.0 and 0.50",
                details={"risk_free_rate": self._parameters.risk_free_rate}
            )
        
        # Dividend yield validation (0% to 20% annual)    
        if not (0.0 <= self._parameters.dividend_yield <= 0.20):
            raise ConfigurationError(
                f"Invalid dividend_yield: {self._parameters.dividend_yield}. Must be between 0.0 and 0.20",
                details={"dividend_yield": self._parameters.dividend_yield}
            )
        
        # Volatility validation
        if not (self._parameters.volatility_min < self._parameters.volatility_max):
            raise ConfigurationError(
                f"Invalid volatility bounds: min={self._parameters.volatility_min}, max={self._parameters.volatility_max}",
                details={
                    "volatility_min": self._parameters.volatility_min,
                    "volatility_max": self._parameters.volatility_max
                }
            )
        
        if not (0.01 <= self._parameters.default_volatility <= 10.0):
            raise ConfigurationError(
                f"Invalid default_volatility: {self._parameters.default_volatility}. Must be between 0.01 and 10.0",
                details={"default_volatility": self._parameters.default_volatility}
            )
    
    def _load_model_functions(self) -> Dict[str, Callable]:
        """Dynamically load the appropriate pyvollib functions"""
        try:
            if self._model_name == "black_scholes_merton":
                from py_vollib.black_scholes_merton.greeks.analytical import (
                    delta, gamma, theta, vega, rho
                )
                return {
                    'delta': delta, 'gamma': gamma, 'theta': theta,
                    'vega': vega, 'rho': rho
                }
                
            elif self._model_name == "black_scholes":
                from py_vollib.black_scholes.greeks.analytical import (
                    delta, gamma, theta, vega, rho
                )
                return {
                    'delta': delta, 'gamma': gamma, 'theta': theta,
                    'vega': vega, 'rho': rho
                }
                
            elif self._model_name == "black76":
                try:
                    from py_vollib.black_76.greeks.analytical import (
                        delta, gamma, theta, vega, rho
                    )
                    return {
                        'delta': delta, 'gamma': gamma, 'theta': theta,
                        'vega': vega, 'rho': rho
                    }
                except ImportError:
                    # Fall back to black_scholes if black76 not available
                    from py_vollib.black_scholes.greeks.analytical import (
                        delta, gamma, theta, vega, rho
                    )
                    return {
                        'delta': delta, 'gamma': gamma, 'theta': theta,
                        'vega': vega, 'rho': rho
                    }
                
            else:
                # This should never happen due to validation above, but defensive programming
                raise UnsupportedModelError(f"Model loading not implemented for: {self._model_name}")
                
        except ImportError as e:
            raise ConfigurationError(
                f"Failed to import pyvollib functions for model '{self._model_name}': {str(e)}",
                details={
                    "model": self._model_name,
                    "import_error": str(e)
                }
            )
    
    @property
    def model_name(self) -> str:
        """Get the configured model name"""
        if not self._initialized:
            self.initialize()
        return self._model_name
    
    @property
    def parameters(self) -> ModelParameters:
        """Get the model parameters"""
        if not self._initialized:
            self.initialize()
        return self._parameters
    
    @property
    def greeks_functions(self) -> Dict[str, Callable]:
        """Get the loaded pyvollib functions"""
        if not self._initialized:
            self.initialize()
        return self._greeks_functions
    
    def calculate_greek(
        self,
        greek_name: str,
        flag: str,
        underlying_price: float,
        strike_price: float,
        time_to_expiry: float,
        volatility: float,
        risk_free_rate: Optional[float] = None,
        dividend_yield: Optional[float] = None
    ) -> float:
        """
        Calculate a specific Greek using the configured model.
        
        Args:
            greek_name: 'delta', 'gamma', 'theta', 'vega', or 'rho'
            flag: 'c' for call, 'p' for put
            underlying_price: Current underlying price
            strike_price: Option strike price
            time_to_expiry: Time to expiration in years
            volatility: Implied volatility (annual)
            risk_free_rate: Optional override for risk-free rate
            dividend_yield: Optional override for dividend yield
            
        Returns:
            Calculated Greek value
            
        Raises:
            UnsupportedModelError: If Greek name is not supported
            GreeksCalculationError: If calculation fails
        """
        if not self._initialized:
            self.initialize()
            
        if greek_name not in self._greeks_functions:
            supported_greeks = ", ".join(self._greeks_functions.keys())
            raise UnsupportedModelError(
                f"Unsupported Greek: '{greek_name}'. Supported Greeks: {supported_greeks}",
                details={
                    "requested_greek": greek_name,
                    "supported_greeks": list(self._greeks_functions.keys())
                }
            )
        
        # Use provided parameters or defaults from config
        final_risk_free_rate = risk_free_rate if risk_free_rate is not None else self._parameters.risk_free_rate
        final_dividend_yield = dividend_yield if dividend_yield is not None else self._parameters.dividend_yield
        
        # Validate volatility bounds
        if not (self._parameters.volatility_min <= volatility <= self._parameters.volatility_max):
            raise ConfigurationError(
                f"Volatility {volatility} outside configured bounds "
                f"[{self._parameters.volatility_min}, {self._parameters.volatility_max}]"
            )
        
        try:
            func = self._greeks_functions[greek_name]
            
            # Call function with appropriate parameters based on model
            if self._model_name in ["black_scholes_merton", "black76"]:
                # These models require dividend yield parameter
                return func(flag, underlying_price, strike_price, time_to_expiry, 
                           final_risk_free_rate, volatility, final_dividend_yield)
            else:
                # black_scholes model doesn't use dividend yield
                return func(flag, underlying_price, strike_price, time_to_expiry,
                           final_risk_free_rate, volatility)
                
        except Exception as e:
            from app.errors import GreeksCalculationError
            raise GreeksCalculationError(
                f"Failed to calculate {greek_name} using {self._model_name}: {str(e)}",
                details={
                    "greek": greek_name,
                    "model": self._model_name,
                    "parameters": {
                        "flag": flag,
                        "underlying_price": underlying_price,
                        "strike_price": strike_price,
                        "time_to_expiry": time_to_expiry,
                        "volatility": volatility,
                        "risk_free_rate": final_risk_free_rate,
                        "dividend_yield": final_dividend_yield
                    }
                }
            )
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the configured model"""
        if not self._initialized:
            self.initialize()
            
        return {
            "model_name": self._model_name,
            "parameters": {
                "risk_free_rate": self._parameters.risk_free_rate,
                "dividend_yield": self._parameters.dividend_yield,
                "default_volatility": self._parameters.default_volatility,
                "volatility_bounds": [self._parameters.volatility_min, self._parameters.volatility_max]
            },
            "supported_greeks": list(self._greeks_functions.keys()),
            "supported_models": list(self.SUPPORTED_MODELS.keys())
        }


# Global instance
_greeks_model_config: Optional[GreeksModelConfig] = None


def get_greeks_model_config() -> GreeksModelConfig:
    """Get the global Greeks model configuration instance"""
    global _greeks_model_config
    if _greeks_model_config is None:
        _greeks_model_config = GreeksModelConfig()
    return _greeks_model_config