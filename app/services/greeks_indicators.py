"""
PyVolLib Greeks Indicators Registration
Register all PyVolLib Greeks calculations as accessible indicators
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from app.services.indicator_registry import IndicatorRegistry, IndicatorCategory, register_indicator
from app.utils.logging_utils import log_info, log_error

logger = logging.getLogger(__name__)


@register_indicator(
    name="option_delta",
    category=IndicatorCategory.GREEKS,
    library="py_vollib",
    description="Option Delta - Rate of change of option price with respect to underlying asset price",
    parameters={
        "option_type": {
            "type": "str", 
            "default": "c", 
            "description": "Option type: 'c' for call, 'p' for put"
        },
        "spot_price": {
            "type": "float", 
            "required": True, 
            "description": "Current price of underlying asset"
        },
        "strike_price": {
            "type": "float", 
            "required": True, 
            "description": "Strike price of the option"
        },
        "time_to_expiry": {
            "type": "float", 
            "required": True, 
            "description": "Time to expiration in years"
        },
        "risk_free_rate": {
            "type": "float", 
            "default": 0.05, 
            "description": "Risk-free interest rate"
        },
        "volatility": {
            "type": "float", 
            "required": True, 
            "description": "Implied volatility of the underlying"
        },
        "model": {
            "type": "str", 
            "default": "black_scholes", 
            "description": "Pricing model: black_scholes, black_scholes_merton, black76"
        }
    }
)
def calculate_option_delta(
    option_type: str = "c",
    spot_price: float = None,
    strike_price: float = None, 
    time_to_expiry: float = None,
    risk_free_rate: float = 0.05,
    volatility: float = None,
    model: str = "black_scholes",
    **kwargs
) -> float:
    """Calculate option delta using PyVolLib"""
    try:
        from app.services.greeks_calculator import GreeksCalculator
        
        # Use the configured Greeks calculator
        calculator = GreeksCalculator()
        
        # Calculate delta using the configured model
        delta = calculator.calculate_delta(
            option_type=option_type,
            spot_price=spot_price,
            strike_price=strike_price,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            volatility=volatility
        )
        
        return delta
        
    except Exception as e:
        log_error(f"Error calculating option delta: {e}")
        raise


@register_indicator(
    name="option_gamma", 
    category=IndicatorCategory.GREEKS,
    library="py_vollib",
    description="Option Gamma - Rate of change of delta with respect to underlying asset price",
    parameters={
        "option_type": {"type": "str", "default": "c"},
        "spot_price": {"type": "float", "required": True},
        "strike_price": {"type": "float", "required": True},
        "time_to_expiry": {"type": "float", "required": True}, 
        "risk_free_rate": {"type": "float", "default": 0.05},
        "volatility": {"type": "float", "required": True},
        "model": {"type": "str", "default": "black_scholes"}
    }
)
def calculate_option_gamma(
    option_type: str = "c",
    spot_price: float = None,
    strike_price: float = None,
    time_to_expiry: float = None,
    risk_free_rate: float = 0.05, 
    volatility: float = None,
    model: str = "black_scholes",
    **kwargs
) -> float:
    """Calculate option gamma using PyVolLib"""
    try:
        from app.services.greeks_calculator import GreeksCalculator
        
        calculator = GreeksCalculator()
        gamma = calculator.calculate_gamma(
            option_type=option_type,
            spot_price=spot_price,
            strike_price=strike_price,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            volatility=volatility
        )
        
        return gamma
        
    except Exception as e:
        log_error(f"Error calculating option gamma: {e}")
        raise


@register_indicator(
    name="option_theta",
    category=IndicatorCategory.GREEKS,
    library="py_vollib", 
    description="Option Theta - Time decay of option value",
    parameters={
        "option_type": {"type": "str", "default": "c"},
        "spot_price": {"type": "float", "required": True},
        "strike_price": {"type": "float", "required": True},
        "time_to_expiry": {"type": "float", "required": True},
        "risk_free_rate": {"type": "float", "default": 0.05},
        "volatility": {"type": "float", "required": True},
        "model": {"type": "str", "default": "black_scholes"}
    }
)
def calculate_option_theta(
    option_type: str = "c",
    spot_price: float = None,
    strike_price: float = None,
    time_to_expiry: float = None,
    risk_free_rate: float = 0.05,
    volatility: float = None,
    model: str = "black_scholes", 
    **kwargs
) -> float:
    """Calculate option theta using PyVolLib"""
    try:
        from app.services.greeks_calculator import GreeksCalculator
        
        calculator = GreeksCalculator()
        theta = calculator.calculate_theta(
            option_type=option_type,
            spot_price=spot_price,
            strike_price=strike_price,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            volatility=volatility
        )
        
        return theta
        
    except Exception as e:
        log_error(f"Error calculating option theta: {e}")
        raise


@register_indicator(
    name="option_vega",
    category=IndicatorCategory.GREEKS,
    library="py_vollib",
    description="Option Vega - Sensitivity to volatility changes",
    parameters={
        "option_type": {"type": "str", "default": "c"},
        "spot_price": {"type": "float", "required": True}, 
        "strike_price": {"type": "float", "required": True},
        "time_to_expiry": {"type": "float", "required": True},
        "risk_free_rate": {"type": "float", "default": 0.05},
        "volatility": {"type": "float", "required": True},
        "model": {"type": "str", "default": "black_scholes"}
    }
)
def calculate_option_vega(
    option_type: str = "c",
    spot_price: float = None,
    strike_price: float = None,
    time_to_expiry: float = None,
    risk_free_rate: float = 0.05,
    volatility: float = None,
    model: str = "black_scholes",
    **kwargs
) -> float:
    """Calculate option vega using PyVolLib"""
    try:
        from app.services.greeks_calculator import GreeksCalculator
        
        calculator = GreeksCalculator()
        vega = calculator.calculate_vega(
            option_type=option_type,
            spot_price=spot_price,
            strike_price=strike_price,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            volatility=volatility
        )
        
        return vega
        
    except Exception as e:
        log_error(f"Error calculating option vega: {e}")
        raise


@register_indicator(
    name="option_rho",
    category=IndicatorCategory.GREEKS,
    library="py_vollib",
    description="Option Rho - Sensitivity to interest rate changes", 
    parameters={
        "option_type": {"type": "str", "default": "c"},
        "spot_price": {"type": "float", "required": True},
        "strike_price": {"type": "float", "required": True},
        "time_to_expiry": {"type": "float", "required": True},
        "risk_free_rate": {"type": "float", "default": 0.05},
        "volatility": {"type": "float", "required": True},
        "model": {"type": "str", "default": "black_scholes"}
    }
)
def calculate_option_rho(
    option_type: str = "c",
    spot_price: float = None,
    strike_price: float = None,
    time_to_expiry: float = None,
    risk_free_rate: float = 0.05,
    volatility: float = None,
    model: str = "black_scholes",
    **kwargs
) -> float:
    """Calculate option rho using PyVolLib"""
    try:
        from app.services.greeks_calculator import GreeksCalculator
        
        calculator = GreeksCalculator()
        rho = calculator.calculate_rho(
            option_type=option_type,
            spot_price=spot_price,
            strike_price=strike_price,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            volatility=volatility
        )
        
        return rho
        
    except Exception as e:
        log_error(f"Error calculating option rho: {e}")
        raise


@register_indicator(
    name="all_greeks",
    category=IndicatorCategory.GREEKS, 
    library="py_vollib",
    description="Calculate all option Greeks (Delta, Gamma, Theta, Vega, Rho) at once",
    parameters={
        "option_type": {"type": "str", "default": "c"},
        "spot_price": {"type": "float", "required": True},
        "strike_price": {"type": "float", "required": True},
        "time_to_expiry": {"type": "float", "required": True},
        "risk_free_rate": {"type": "float", "default": 0.05},
        "volatility": {"type": "float", "required": True},
        "model": {"type": "str", "default": "black_scholes"}
    },
    output_type="dict"
)
def calculate_all_greeks(
    option_type: str = "c",
    spot_price: float = None,
    strike_price: float = None,
    time_to_expiry: float = None,
    risk_free_rate: float = 0.05,
    volatility: float = None,
    model: str = "black_scholes",
    **kwargs
) -> Dict[str, float]:
    """Calculate all option Greeks at once using PyVolLib"""
    try:
        from app.services.greeks_calculator import GreeksCalculator
        
        calculator = GreeksCalculator()
        
        # Calculate all Greeks efficiently using the calculator
        result = calculator.calculate_all_greeks(
            option_type=option_type,
            spot_price=spot_price,
            strike_price=strike_price,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            volatility=volatility
        )
        
        return {
            "delta": result.delta,
            "gamma": result.gamma,
            "theta": result.theta,
            "vega": result.vega,
            "rho": result.rho,
            "implied_volatility": result.implied_volatility
        }
        
    except Exception as e:
        log_error(f"Error calculating all option Greeks: {e}")
        raise


@register_indicator(
    name="vectorized_greeks",
    category=IndicatorCategory.GREEKS,
    library="py_vollib_vectorized", 
    description="High-performance vectorized calculation of Greeks for option chains",
    parameters={
        "option_data": {"type": "list", "required": True, "description": "List of option dictionaries"},
        "model": {"type": "str", "default": "black_scholes"},
        "chunk_size": {"type": "int", "default": 500, "description": "Batch size for vectorized processing"}
    },
    output_type="dataframe"
)
def calculate_vectorized_greeks(
    option_data: list = None,
    model: str = "black_scholes",
    chunk_size: int = 500,
    **kwargs
) -> Dict[str, Any]:
    """Calculate Greeks for multiple options using vectorized PyVolLib"""
    try:
        from app.services.vectorized_pyvollib_engine import VectorizedPyvolibGreeksEngine
        
        engine = VectorizedPyvolibGreeksEngine(chunk_size=chunk_size)
        
        # Process the option data using vectorized engine
        results = engine.calculate_greeks_bulk(option_data)
        
        return {
            "results": results,
            "processed_count": len(option_data),
            "model_used": model,
            "chunk_size": chunk_size
        }
        
    except Exception as e:
        log_error(f"Error in vectorized Greeks calculation: {e}")
        raise


def register_pyvollib_indicators():
    """Register all PyVolLib indicators (called by registration system)"""
    log_info("PyVolLib Greeks indicators registered successfully")
    # The @register_indicator decorators above handle the actual registration


# Make sure this module is imported during indicator registration
if __name__ == "__main__":
    register_pyvollib_indicators()