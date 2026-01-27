"""
Market Profile API endpoints
Provides volume profile, TPO, and value area calculations
"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_signal_repository
from app.services.market_profile_calculator import MarketProfileCalculator
from app.utils.logging_utils import log_error

router = APIRouter(prefix="/market-profile", tags=["market-profile"])


async def get_market_profile_calculator() -> MarketProfileCalculator:
    """Get market profile calculator instance"""
    repository = await get_signal_repository()
    return MarketProfileCalculator(repository)


@router.get("/{instrument_key}")
async def get_market_profile(
    instrument_key: str,
    interval: str = Query("30m", description="Time interval for profile calculation"),
    lookback_period: str = Query("1d", description="Lookback period (e.g., 1d, 1w, 1m)"),
    profile_type: str = Query("volume", regex="^(volume|tpo|both)$"),
    tick_size: float | None = Query(None, description="Price level granularity"),
    calculator: MarketProfileCalculator = Depends(get_market_profile_calculator)
) -> dict[str, Any]:
    """
    Get market profile for an instrument

    Args:
        instrument_key: Instrument identifier
        interval: Time interval (30m, 1h, etc.)
        lookback_period: How far back to analyze
        profile_type: Type of profile to calculate
        tick_size: Price granularity (auto-detected if not provided)

    Returns:
        Market profile with price levels, volumes/TPO, and value areas
    """
    try:
        return await calculator.calculate_market_profile(
            instrument_key=instrument_key,
            interval=interval,
            lookback_period=lookback_period,
            profile_type=profile_type,
            tick_size=tick_size
        )


    except Exception as e:
        log_error(f"Error calculating market profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate market profile")


@router.get("/{instrument_key}/composite")
async def get_composite_profile(
    instrument_key: str,
    sessions: list[str] = Query(..., description="List of session dates (YYYY-MM-DD)"),
    profile_type: str = Query("volume", regex="^(volume|tpo)$"),
    calculator: MarketProfileCalculator = Depends(get_market_profile_calculator)
) -> dict[str, Any]:
    """
    Get composite market profile across multiple sessions

    Args:
        instrument_key: Instrument identifier
        sessions: List of dates to include in composite
        profile_type: Type of profile to calculate

    Returns:
        Composite market profile combining multiple sessions
    """
    try:
        return await calculator.calculate_composite_profile(
            instrument_key=instrument_key,
            sessions=sessions,
            profile_type=profile_type
        )


    except Exception as e:
        log_error(f"Error calculating composite profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate composite profile")


@router.get("/{instrument_key}/developing")
async def get_developing_profile(
    instrument_key: str,
    interval: str = Query("30m", description="Time interval"),
    calculator: MarketProfileCalculator = Depends(get_market_profile_calculator)
) -> dict[str, Any]:
    """
    Get developing market profile for current session

    Args:
        instrument_key: Instrument identifier
        interval: Time interval for profile

    Returns:
        Current session's developing market profile
    """
    try:
        return await calculator.get_developing_profile(
            instrument_key=instrument_key,
            interval=interval
        )


    except Exception as e:
        log_error(f"Error getting developing profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to get developing profile")


@router.post("/{instrument_key}/patterns")
async def identify_profile_patterns(
    instrument_key: str,
    profile_data: dict[str, Any],
    calculator: MarketProfileCalculator = Depends(get_market_profile_calculator)
) -> dict[str, Any]:
    """
    Identify patterns in market profile data

    Args:
        instrument_key: Instrument identifier
        profile_data: Pre-calculated profile data

    Returns:
        Identified patterns and market structure analysis
    """
    try:
        patterns = await calculator.identify_profile_patterns(profile_data)

        return {
            "instrument_key": instrument_key,
            "patterns": patterns,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        log_error(f"Error identifying patterns: {e}")
        raise HTTPException(status_code=500, detail="Failed to identify patterns")
