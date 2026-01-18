"""
Real-time Signal API v2
Provides real-time Greeks, indicators, and moneyness-based calculations
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Dict, List, Optional, Any
from datetime import datetime

import logging
logger = logging.getLogger(__name__)
from app.services.signal_processor import SignalProcessor
from app.services.moneyness_greeks_calculator import MoneynessAwareGreeksCalculator
from app.services.instrument_service_client import InstrumentServiceClient
# from app.models.signal_models import SignalGreeks, SignalIndicators
from app.schemas.signal_schemas import (
    GreeksResponse, IndicatorResponse, MoneynessGreeksResponse
)


router = APIRouter(prefix="/realtime", tags=["realtime"])

# Service instances (in production, use dependency injection)
signal_processor = None
moneyness_calculator = None
instrument_client = None


async def get_signal_processor() -> SignalProcessor:
    """Get signal processor instance"""
    global signal_processor
    if not signal_processor:
        signal_processor = SignalProcessor()
        await signal_processor.initialize()
    return signal_processor


async def get_moneyness_calculator() -> MoneynessAwareGreeksCalculator:
    """Get moneyness calculator instance"""
    global moneyness_calculator, instrument_client
    if not moneyness_calculator:
        from app.clients.client_factory import get_client_manager
        manager = get_client_manager()
        instrument_client = await manager.get_client('instrument_service')
        moneyness_calculator = MoneynessAwareGreeksCalculator(instrument_client)
    return moneyness_calculator


@router.get("/greeks/{instrument_key}", response_model=GreeksResponse)
async def get_realtime_greeks(
    instrument_key: str,
    processor: SignalProcessor = Depends(get_signal_processor)
) -> GreeksResponse:
    """
    Get real-time Greeks for an instrument
    
    Args:
        instrument_key: Universal instrument key
        
    Returns:
        Current Greeks values
    """
    try:
        # Get latest Greeks from cache or compute
        greeks = await processor.get_latest_greeks(instrument_key)
        
        if not greeks:
            raise HTTPException(status_code=404, detail="Greeks not found for instrument")
            
        return GreeksResponse(
            instrument_key=instrument_key,
            timestamp=datetime.utcnow(),
            greeks={
                "delta": greeks.delta,
                "gamma": greeks.gamma,
                "theta": greeks.theta,
                "vega": greeks.vega,
                "rho": greeks.rho,
                "implied_volatility": greeks.implied_volatility
            },
            underlying_price=greeks.underlying_price,
            option_price=greeks.theoretical_value
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting real-time Greeks: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/indicators/{instrument_key}/{indicator}", response_model=IndicatorResponse)
async def get_realtime_indicator(
    instrument_key: str,
    indicator: str,
    period: int = Query(14, ge=1, le=200),
    processor: SignalProcessor = Depends(get_signal_processor)
) -> IndicatorResponse:
    """
    Get real-time indicator value
    
    Args:
        instrument_key: Universal instrument key
        indicator: Indicator name (rsi, macd, sma, etc.)
        period: Indicator period
        
    Returns:
        Current indicator value
    """
    try:
        # Get latest indicator value
        value = await processor.get_latest_indicator(
            instrument_key, indicator, period
        )
        
        if value is None:
            raise HTTPException(status_code=404, detail="Indicator not found")
            
        return IndicatorResponse(
            instrument_key=instrument_key,
            indicator=indicator,
            period=period,
            timestamp=datetime.utcnow(),
            value=value,
            metadata={
                "calculation_time": datetime.utcnow().isoformat(),
                "data_points": period
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting real-time indicator: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/moneyness/{underlying}/greeks/{moneyness_level}", response_model=MoneynessGreeksResponse)
async def get_moneyness_greeks(
    underlying: str,
    moneyness_level: str,
    expiry_date: Optional[str] = None,
    calculator: MoneynessAwareGreeksCalculator = Depends(get_moneyness_calculator),
    processor: SignalProcessor = Depends(get_signal_processor)
) -> MoneynessGreeksResponse:
    """
    Get aggregated Greeks for a moneyness level
    
    Args:
        underlying: Underlying symbol
        moneyness_level: Moneyness level (ATM, OTM5delta, etc.)
        expiry_date: Optional expiry date filter
        
    Returns:
        Aggregated Greeks for the moneyness level
    """
    try:
        # Get current spot price
        spot_price = await processor.get_latest_price(underlying)
        if not spot_price:
            raise HTTPException(status_code=404, detail="Underlying price not found")
            
        # Calculate moneyness Greeks
        result = await calculator.calculate_moneyness_greeks(
            underlying,
            spot_price,
            moneyness_level,
            expiry_date
        )
        
        if not result or not result.get("aggregated_greeks", {}).get("all"):
            raise HTTPException(status_code=404, detail="No options found for moneyness level")
            
        return MoneynessGreeksResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting moneyness Greeks: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/moneyness/{underlying}/atm-iv")
async def get_atm_iv(
    underlying: str,
    expiry_date: str,
    timeframe: str = Query("5m", regex="^[0-9]+m$"),
    calculator: MoneynessAwareGreeksCalculator = Depends(get_moneyness_calculator),
    processor: SignalProcessor = Depends(get_signal_processor)
) -> Dict[str, Any]:
    """
    Get ATM implied volatility
    
    Args:
        underlying: Underlying symbol
        expiry_date: Option expiry date
        timeframe: Time interval (default 5m)
        
    Returns:
        ATM IV data
    """
    try:
        # Get current spot price
        spot_price = await processor.get_latest_price(underlying)
        if not spot_price:
            raise HTTPException(status_code=404, detail="Underlying price not found")
            
        # Calculate ATM IV
        result = await calculator.calculate_atm_iv(
            underlying,
            spot_price,
            expiry_date,
            timeframe
        )
        
        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])
            
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting ATM IV: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/moneyness/{underlying}/otm-delta")
async def get_otm_delta_greeks(
    underlying: str,
    delta: float = Query(0.05, ge=0.01, le=0.5),
    option_type: str = Query("put", regex="^(call|put)$"),
    expiry_date: Optional[str] = None,
    calculator: MoneynessAwareGreeksCalculator = Depends(get_moneyness_calculator),
    processor: SignalProcessor = Depends(get_signal_processor)
) -> Dict[str, Any]:
    """
    Get Greeks for OTM options by delta
    
    Args:
        underlying: Underlying symbol
        delta: Target delta value
        option_type: 'call' or 'put'
        expiry_date: Optional expiry filter
        
    Returns:
        Greeks for matching options
    """
    try:
        # Get current spot price
        spot_price = await processor.get_latest_price(underlying)
        if not spot_price:
            raise HTTPException(status_code=404, detail="Underlying price not found")
            
        # Get OTM delta Greeks
        result = await calculator.calculate_otm_delta_greeks(
            underlying,
            spot_price,
            delta,
            option_type,
            expiry_date
        )
        
        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])
            
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting OTM delta Greeks: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/price/{instrument_key}")
async def get_realtime_price(
    instrument_key: str,
    processor: SignalProcessor = Depends(get_signal_processor)
) -> Dict[str, Any]:
    """
    Get real-time price for an instrument
    
    Args:
        instrument_key: Universal instrument key
        
    Returns:
        Current price data
    """
    try:
        price = await processor.get_latest_price(instrument_key)
        
        if price is None:
            raise HTTPException(status_code=404, detail="Price not found")
            
        return {
            "instrument_key": instrument_key,
            "price": price,
            "timestamp": datetime.utcnow().isoformat(),
            "source": "signal_service"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting real-time price: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/health")
async def realtime_health_check():
    """Health check endpoint for real-time API"""
    return {
        "status": "healthy",
        "api_version": "v2",
        "component": "realtime",
        "timestamp": datetime.utcnow().isoformat()
    }