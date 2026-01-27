"""
Historical Signal API v2
Provides historical Greeks, indicators, and moneyness data with flexible timeframes
"""
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

logger = logging.getLogger(__name__)
from app.dependencies import (
    get_moneyness_calculator,
    get_moneyness_processor,
    get_timeframe_manager,
)
from app.schemas.signal_schemas import (
    HistoricalGreeksResponse,
    HistoricalIndicatorResponse,
    HistoricalMoneynessResponse,
    TimeSeriesDataPoint,
)
from app.services.flexible_timeframe_manager import FlexibleTimeframeManager
from app.services.moneyness_greeks_calculator import MoneynessAwareGreeksCalculator
from app.services.moneyness_historical_processor import MoneynessHistoricalProcessor

router = APIRouter(prefix="/historical", tags=["historical"])

# Service instances
timeframe_manager = None
moneyness_calculator = None
signal_repository = None


# Using dependency injection functions imported above
# No local implementations needed


# get_moneyness_calculator imported from dependencies above


@router.get("/greeks/{instrument_key}", response_model=HistoricalGreeksResponse)
async def get_historical_greeks(
    instrument_key: str,
    start_time: datetime = Query(..., description="Start time for historical data"),
    end_time: datetime = Query(..., description="End time for historical data"),
    timeframe: str = Query("5m", regex="^([0-9]+m|[0-9]+h|[0-9]+d)$"),
    fields: list[str] | None = Query(None, description="Specific fields to return"),
    manager: FlexibleTimeframeManager = Depends(get_timeframe_manager),
    moneyness_processor: MoneynessHistoricalProcessor = Depends(get_moneyness_processor)
) -> HistoricalGreeksResponse:
    """
    Get historical Greeks data with flexible timeframe

    Transparently handles both strike-based and moneyness-based queries:
    - Strike-based: EXCHANGE@SYMBOL@ASSET_TYPE@EXPIRY@TYPE@STRIKE
    - Moneyness-based: MONEYNESS@SYMBOL@LEVEL@EXPIRY

    Args:
        instrument_key: Universal instrument key or moneyness key
        start_time: Start of time range
        end_time: End of time range
        timeframe: Time interval (e.g., 5m, 15m, 1h, custom_7m)
        fields: Optional list of specific fields

    Returns:
        Historical Greeks time series
    """
    try:
        # Validate time range
        if end_time <= start_time:
            raise HTTPException(status_code=400, detail="End time must be after start time")

        if (end_time - start_time).days > 365:
            raise HTTPException(status_code=400, detail="Time range cannot exceed 365 days")

        # Check if this is a moneyness query
        if instrument_key.startswith("MONEYNESS@"):
            # Parse moneyness key: MONEYNESS@SYMBOL@LEVEL@EXPIRY
            parts = instrument_key.split("@")
            if len(parts) != 4:
                raise HTTPException(status_code=400, detail="Invalid moneyness key format")

            _, underlying, moneyness_level, expiry_date = parts

            # Get moneyness-based Greeks transparently
            data = await moneyness_processor.get_moneyness_greeks_like_strike(
                underlying=underlying,
                moneyness_level=moneyness_level,
                expiry_date=expiry_date,
                start_time=start_time,
                end_time=end_time,
                timeframe=timeframe
            )
        else:
            # Regular strike-based Greeks
            data = await manager.get_aggregated_data(
                instrument_key,
                "greeks",
                timeframe,
                start_time,
                end_time,
                fields
            )

        if not data:
            raise HTTPException(status_code=404, detail="No historical data found")

        # Convert to response format
        time_series = []
        for point in data:
            # Handle both formats
            if isinstance(point, dict) and 'value' in point:
                # Moneyness format
                time_series.append(TimeSeriesDataPoint(
                    timestamp=point['timestamp'],
                    value=point['value'],
                    metadata=point.get('metadata', {})
                ))
            else:
                # Regular format
                time_series.append(TimeSeriesDataPoint(
                    timestamp=datetime.fromisoformat(point['timestamp']) if isinstance(point['timestamp'], str) else point['timestamp'],
                    value={
                        "delta": point.get("delta"),
                        "gamma": point.get("gamma"),
                        "theta": point.get("theta"),
                        "vega": point.get("vega"),
                        "rho": point.get("rho"),
                        "iv": point.get("implied_volatility") or point.get("iv")
                    },
                    metadata={
                        "underlying_price": point.get("underlying_price"),
                        "option_price": point.get("theoretical_value"),
                        "calculation_method": point.get("calculation_method")
                    }
                ))

        return HistoricalGreeksResponse(
            instrument_key=instrument_key,
            start_time=start_time,
            end_time=end_time,
            timeframe=timeframe,
            data_points=len(time_series),
            time_series=time_series
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting historical Greeks: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e from e


@router.get("/indicators/{instrument_key}/{indicator}", response_model=HistoricalIndicatorResponse)
async def get_historical_indicator(
    instrument_key: str,
    indicator: str,
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    timeframe: str = Query("5m", regex="^([0-9]+m|[0-9]+h|[0-9]+d)$"),
    period: int = Query(14, ge=1, le=200),
    manager: FlexibleTimeframeManager = Depends(get_timeframe_manager)
) -> HistoricalIndicatorResponse:
    """
    Get historical indicator data

    Args:
        instrument_key: Universal instrument key
        indicator: Indicator name
        start_time: Start of time range
        end_time: End of time range
        timeframe: Time interval
        period: Indicator period

    Returns:
        Historical indicator time series
    """
    try:
        # Get aggregated data
        data = await manager.get_aggregated_data(
            instrument_key,
            "indicators",
            timeframe,
            start_time,
            end_time,
            [indicator]
        )

        if not data:
            raise HTTPException(status_code=404, detail="No historical data found")

        # Convert to response format
        time_series = []
        for point in data:
            time_series.append(TimeSeriesDataPoint(
                timestamp=datetime.fromisoformat(point['timestamp']),
                value=point.get(indicator),
                metadata={
                    "period": period,
                    "calculation_method": point.get("calculation_method", "standard")
                }
            ))

        return HistoricalIndicatorResponse(
            instrument_key=instrument_key,
            indicator=indicator,
            period=period,
            start_time=start_time,
            end_time=end_time,
            timeframe=timeframe,
            data_points=len(time_series),
            time_series=time_series
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting historical indicator: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/moneyness/{underlying}/greeks/{moneyness_level}", response_model=HistoricalMoneynessResponse)
async def get_historical_moneyness_greeks(
    underlying: str,
    moneyness_level: str,
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    timeframe: str = Query("5m"),
    expiry_date: str | None = None,
    calculator: MoneynessAwareGreeksCalculator = Depends(get_moneyness_calculator),
    manager: FlexibleTimeframeManager = Depends(get_timeframe_manager)
) -> HistoricalMoneynessResponse:
    """
    Get historical moneyness-based Greeks

    Args:
        underlying: Underlying symbol
        moneyness_level: Moneyness level (ATM, OTM5delta, etc.)
        start_time: Start of time range
        end_time: End of time range
        timeframe: Time interval
        expiry_date: Optional expiry filter

    Returns:
        Historical moneyness Greeks time series
    """
    try:
        # Production implementation: route through ticker_service for historical moneyness data
        pass


    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting historical moneyness Greeks: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/moneyness/{underlying}/atm-iv/history")
async def get_historical_atm_iv(
    underlying: str,
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    timeframe: str = Query("5m"),
    expiry_date: str = Query(..., description="Option expiry date"),
    moneyness_processor: MoneynessHistoricalProcessor = Depends(get_moneyness_processor)
) -> dict[str, Any]:
    """
    Get historical ATM IV data with time series

    This is a convenience endpoint that internally uses the moneyness processor
    to get ATM IV history in a simplified format.

    Args:
        underlying: Underlying symbol
        start_time: Start of time range
        end_time: End of time range
        timeframe: Time interval
        expiry_date: Option expiry date

    Returns:
        ATM IV time series with statistics
    """
    try:
        # Use moneyness processor to get ATM IV history
        return await moneyness_processor.get_atm_iv_history(
            underlying=underlying,
            expiry_date=expiry_date,
            start_time=start_time,
            end_time=end_time,
            timeframe=timeframe
        )


    except Exception as e:
        logger.error(f"Error getting historical ATM IV: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/available-timeframes/{instrument_key}")
async def get_available_timeframes(
    instrument_key: str,
    signal_type: str = Query("greeks", regex="^(greeks|indicators|moneyness_greeks)$"),
    manager: FlexibleTimeframeManager = Depends(get_timeframe_manager)
) -> dict[str, Any]:
    """
    Get available timeframes for an instrument

    Args:
        instrument_key: Universal instrument key
        signal_type: Type of signal data

    Returns:
        List of available timeframes
    """
    try:
        timeframes = await manager.get_available_timeframes(
            instrument_key,
            signal_type
        )

        return {
            "instrument_key": instrument_key,
            "signal_type": signal_type,
            "standard_timeframes": list(FlexibleTimeframeManager.STANDARD_TIMEFRAMES.keys()),
            "custom_timeframes": [tf for tf in timeframes if tf not in FlexibleTimeframeManager.STANDARD_TIMEFRAMES],
            "all_timeframes": timeframes
        }

    except Exception as e:
        logger.error(f"Error getting available timeframes: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/health")
async def historical_health_check():
    """Health check endpoint for historical API"""
    return {
        "status": "healthy",
        "api_version": "v2",
        "component": "historical",
        "timestamp": datetime.utcnow().isoformat()
    }
