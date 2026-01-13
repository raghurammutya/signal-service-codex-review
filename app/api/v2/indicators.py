"""
On-demand Indicator Calculation API
Provides one-time calculation of technical indicators without subscriptions
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone
import pandas as pd
import numpy as np
import pandas_ta as ta
import inspect
import json
from typing import Callable
import httpx

from app.utils.logging_utils import log_info, log_error, log_exception
from app.schemas.signal_schemas import BaseResponse
from app.services.worker_affinity_manager import get_worker_affinity_manager
from app.services.indicator_cache_manager import indicator_cache_manager, cached_indicator_calculation
from app.core.config import settings

router = APIRouter(prefix="/indicators", tags=["on-demand-indicators"])


class IndicatorCalculator:
    """Handles on-demand technical indicator calculations"""

    def __init__(self):
        self._http_client: Optional[httpx.AsyncClient] = None
        self._initialized = False

    async def initialize(self):
        """Initialize HTTP client for ticker_service API calls"""
        if not self._initialized:
            self._http_client = httpx.AsyncClient(timeout=30.0)
            self._initialized = True

    async def get_historical_data(
        self,
        instrument_token: int,
        timeframe: str,
        periods: int,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        Fetch historical data from ticker_service API.

        Args:
            instrument_token: Kite instrument token (e.g., 256265)
            timeframe: Timeframe like "5minute", "1minute", "day"
            periods: Number of candles to fetch
            end_date: End date for data (default: now)

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        if not end_date:
            end_date = datetime.now(timezone.utc)

        # Ensure we're initialized
        if not self._initialized:
            await self.initialize()

        # Map timeframe to ticker_service interval format
        timeframe_map = {
            "1minute": "minute",
            "3minute": "3minute",
            "5minute": "5minute",
            "15minute": "15minute",
            "30minute": "30minute",
            "60minute": "60minute",
            "day": "day"
        }
        interval = timeframe_map.get(timeframe, "5minute")

        # Calculate from_ts based on periods (add buffer for market gaps)
        interval_minutes = {
            "minute": 1,
            "3minute": 3,
            "5minute": 5,
            "15minute": 15,
            "30minute": 30,
            "60minute": 60,
            "day": 1440
        }
        minutes = interval_minutes.get(interval, 5)
        from_ts = end_date - timedelta(minutes=periods * minutes * 2)  # 2x buffer for market gaps

        # Call ticker_service API using instrument_token
        try:
            url = f"{settings.TICKER_SERVICE_URL}/api/v2/historical/ohlcv"
            params = {
                "instrument_token": instrument_token,
                "from_ts": from_ts.isoformat(),
                "to_ts": end_date.isoformat(),
                "interval": interval,
                "continuous": False,
                "oi": False
            }

            log_info(f"Fetching historical data from ticker_service: {url}")
            log_info(f"Params: instrument_token={instrument_token}, interval={interval}, periods={periods}")

            response = await self._http_client.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            candles = data.get("candles", [])

            if not candles:
                log_info(f"No historical data found for instrument_token={instrument_token}")
                raise HTTPException(
                    status_code=404,
                    detail=f"No historical data found for instrument_token={instrument_token}"
                )

            # Convert to DataFrame
            df_data = []
            for candle in candles:
                df_data.append({
                    'timestamp': pd.to_datetime(candle['timestamp']),
                    'open': float(candle['open']),
                    'high': float(candle['high']),
                    'low': float(candle['low']),
                    'close': float(candle['close']),
                    'volume': int(candle['volume'])
                })

            df = pd.DataFrame(df_data)
            df = df.sort_values('timestamp')
            df.set_index('timestamp', inplace=True)

            # Limit to requested periods (take last N candles)
            if len(df) > periods:
                df = df.tail(periods)

            log_info(f"Fetched {len(df)} candles for instrument_token={instrument_token}")
            return df

        except httpx.HTTPStatusError as e:
            log_error(f"HTTP error fetching historical data: {e.response.status_code} - {e.response.text}")
            raise HTTPException(
                status_code=502,
                detail=f"Error fetching data from ticker_service: {e.response.status_code}"
            )
        except Exception as e:
            log_error(f"Unexpected error fetching historical data: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch historical data: {str(e)}"
            )
    
    def calculate_sma(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Simple Moving Average"""
        return df['close'].rolling(window=period).mean()
    
    def calculate_ema(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Exponential Moving Average"""
        return df['close'].ewm(span=period, adjust=False).mean()
    
    def calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index"""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def calculate_macd(self, df: pd.DataFrame, fast=12, slow=26, signal=9) -> Dict[str, pd.Series]:
        """Calculate MACD"""
        ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
        
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }
    
    def calculate_bollinger_bands(self, df: pd.DataFrame, period: int = 20, std_dev: int = 2) -> Dict[str, pd.Series]:
        """Calculate Bollinger Bands"""
        sma = df['close'].rolling(window=period).mean()
        std = df['close'].rolling(window=period).std()
        
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        
        return {
            'upper': upper_band,
            'middle': sma,
            'lower': lower_band
        }
    
    def calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        """Calculate Volume Weighted Average Price"""
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        vwap = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
        return vwap
    
    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range"""
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()
        return atr
    
    def get_available_indicators(self) -> Dict[str, Dict[str, Any]]:
        """Get all available pandas_ta indicators with their parameters"""
        indicators = {}
        
        # Get all indicators from pandas_ta
        for name, obj in inspect.getmembers(ta):
            if callable(obj) and not name.startswith('_'):
                try:
                    # Get function signature
                    sig = inspect.signature(obj)
                    params = {}
                    
                    for param_name, param in sig.parameters.items():
                        if param_name not in ['self', 'close', 'high', 'low', 'open', 'volume', 'df']:
                            params[param_name] = {
                                'default': param.default if param.default is not inspect.Parameter.empty else None,
                                'type': str(param.annotation) if param.annotation is not inspect.Parameter.empty else 'Any'
                            }
                    
                    indicators[name] = {
                        'function': obj,
                        'parameters': params,
                        'doc': obj.__doc__ or 'No documentation available'
                    }
                except Exception:
                    continue
        
        return indicators
    
    async def calculate_dynamic_indicator(self, df: pd.DataFrame, indicator: str, **kwargs) -> pd.DataFrame:
        """Calculate any indicator dynamically - checks custom registry first, then pandas_ta"""
        try:
            # STEP 1: Check custom registry FIRST
            from app.services.indicator_registry import IndicatorRegistry

            custom_indicator = IndicatorRegistry.get(indicator)
            if custom_indicator:
                log_info(f"Using custom indicator: {indicator} from {custom_indicator.library}")
                result = custom_indicator.function(df, **kwargs)

                # Handle different output types from custom indicators
                if isinstance(result, pd.Series):
                    return pd.DataFrame({indicator: result})
                elif isinstance(result, pd.DataFrame):
                    return result
                elif isinstance(result, dict):
                    # Convert dict to DataFrame (for indicators like previous_high_low, pivot_points)
                    return pd.DataFrame([result])
                elif isinstance(result, (int, float)):
                    return pd.DataFrame({indicator: [result]})
                elif isinstance(result, list):
                    return pd.DataFrame({indicator: result})
                else:
                    log_error(f"Unsupported output type from custom indicator {indicator}: {type(result)}")
                    raise ValueError(f"Unsupported output type: {type(result)}")

            # STEP 2: Check if indicator exists in pandas_ta
            if hasattr(ta, indicator):
                log_info(f"Using pandas_ta indicator: {indicator}")

                # Prepare the dataframe with pandas_ta extension
                df.ta.cores = 0  # Use all CPU cores

                # Get the indicator method from df.ta accessor
                if hasattr(df.ta, indicator):
                    indicator_method = getattr(df.ta, indicator)
                    result = indicator_method(**kwargs)
                else:
                    # Fallback to calling ta.indicator(df, **kwargs) for some indicators
                    indicator_func = getattr(ta, indicator)
                    result = indicator_func(df, **kwargs)

                # Handle different return types
                if isinstance(result, pd.Series):
                    return pd.DataFrame({indicator: result})
                elif isinstance(result, pd.DataFrame):
                    return result
                elif result is None:
                    # pandas_ta returned None - likely not enough data or wrong parameters
                    log_error(f"pandas_ta returned None for {indicator} with params {kwargs}. DataFrame shape: {df.shape}")
                    raise ValueError(f"pandas_ta returned None for {indicator}. Check data and parameters.")
                else:
                    raise ValueError(f"Unexpected result type from {indicator}: {type(result)}")

            # STEP 3: Fallback to built-in methods
            method_map = {
                'sma': self.calculate_sma,
                'ema': self.calculate_ema,
                'rsi': self.calculate_rsi,
                'macd': self.calculate_macd,
                'bollinger_bands': self.calculate_bollinger_bands,
                'vwap': self.calculate_vwap,
                'atr': self.calculate_atr
            }

            if indicator in method_map:
                log_info(f"Using built-in method for indicator: {indicator}")
                result = method_map[indicator](df, **kwargs)
                if isinstance(result, pd.Series):
                    return pd.DataFrame({indicator: result})
                elif isinstance(result, dict):
                    return pd.DataFrame(result)
                else:
                    return result

            raise ValueError(f"Unknown indicator: {indicator}")

        except Exception as e:
            log_error(f"Error calculating {indicator}: {str(e)}")
            raise


# Create global instance
indicator_calculator = IndicatorCalculator()


@router.on_event("startup")
async def startup():
    """Initialize indicator calculator on startup"""
    await indicator_calculator.initialize()


@router.get("/cache/stats")
async def get_cache_stats():
    """Get cache statistics"""
    try:
        stats = await indicator_cache_manager.get_cache_stats()
        return BaseResponse(
            success=True,
            message="Cache statistics retrieved",
            data=stats
        )
    except Exception as e:
        log_exception(f"Error getting cache stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/invalidate/{symbol}")
async def invalidate_symbol_cache(symbol: str):
    """Invalidate all cached indicators for a symbol"""
    try:
        deleted = await indicator_cache_manager.invalidate_symbol_cache(symbol)
        return BaseResponse(
            success=True,
            message=f"Invalidated {deleted} cache entries for {symbol}",
            data={'deleted': deleted}
        )
    except Exception as e:
        log_exception(f"Error invalidating cache: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calculate/sma")
async def calculate_sma_endpoint(
    symbol: str,
    period: int = Query(20, ge=1, le=500),
    timeframe: str = Query("1day", regex="^(1day|1hour|30min|15min|5min|1min)$"),
    data_points: int = Query(1, ge=1, le=100, description="Number of SMA values to return")
):
    """
    Calculate Simple Moving Average (SMA) on demand
    
    Args:
        symbol: Instrument key (e.g., NSE@RELIANCE@equities)
        period: SMA period (default 20)
        timeframe: Data timeframe (default 1day)
        data_points: Number of values to return (default 1, latest only)
    """
    try:
        # Check worker affinity
        affinity_manager = await get_worker_affinity_manager()
        if not await affinity_manager.should_handle_computation(symbol):
            # Get correct worker
            assigned_worker = await affinity_manager.get_worker_for_symbol(symbol)
            log_info(f"Redirecting {symbol} computation to worker {assigned_worker}")
            
            # In production, this would redirect to the correct worker
            # For now, we'll just note it and continue
            return BaseResponse(
                success=True,
                message=f"Computation handled by worker {assigned_worker}",
                data={
                    'redirect': True,
                    'assigned_worker': assigned_worker,
                    'note': 'In production, this would redirect to the correct worker instance'
                }
            )
        # For single data point, check cache first
        if data_points == 1:
            # Define the calculation function
            async def calculate():
                df = await indicator_calculator.get_historical_data(
                    symbol, timeframe, period
                )
                sma_series = indicator_calculator.calculate_sma(df, period)
                return {
                    'value': round(sma_series.iloc[-1], 2),
                    'timestamp': df.index[-1]
                }
            
            # Use cached calculation
            result = await cached_indicator_calculation(
                symbol=symbol,
                indicator="sma",
                period=period,
                timeframe=timeframe,
                calculation_func=calculate
            )
            
            return BaseResponse(
                success=True,
                message=f"SMA({period}) {'retrieved from cache' if result.get('cached') else 'calculated'}",
                data={
                    'symbol': symbol,
                    'indicator': 'sma',
                    'period': period,
                    'timeframe': timeframe,
                    'values': [{
                        'timestamp': result['timestamp'].isoformat(),
                        'value': result['value']
                    }],
                    'cached': result.get('cached', False),
                    'cache_time': result.get('cache_time').isoformat() if result.get('cache_time') else None
                }
            )
        
        # For multiple data points, calculate fresh (can be cached later)
        required_periods = period + data_points - 1
        
        # Get historical data
        df = await indicator_calculator.get_historical_data(
            symbol, timeframe, required_periods
        )
        
        # Calculate SMA
        sma_series = indicator_calculator.calculate_sma(df, period)
        
        # Prepare response
        values = []
        for idx in range(-data_points, 0):
            if not pd.isna(sma_series.iloc[idx]):
                values.append({
                    'timestamp': df.index[idx].isoformat(),
                    'value': round(sma_series.iloc[idx], 2)
                })
        
        # Cache the latest value
        if values:
            await indicator_cache_manager.cache_indicator_result(
                symbol=symbol,
                indicator="sma",
                period=period,
                timeframe=timeframe,
                value=values[-1]['value'],
                timestamp=datetime.fromisoformat(values[-1]['timestamp'])
            )
        
        return BaseResponse(
            success=True,
            message=f"SMA({period}) calculated successfully",
            data={
                'symbol': symbol,
                'indicator': 'sma',
                'period': period,
                'timeframe': timeframe,
                'values': values,
                'cached': False
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error calculating SMA: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calculate/ema")
async def calculate_ema_endpoint(
    symbol: str,
    period: int = Query(12, ge=1, le=500),
    timeframe: str = Query("1day"),
    data_points: int = Query(1, ge=1, le=100)
):
    """Calculate Exponential Moving Average (EMA) on demand"""
    try:
        # EMA needs more historical data for accuracy
        required_periods = period * 2 + data_points
        
        df = await indicator_calculator.get_historical_data(
            symbol, timeframe, required_periods
        )
        
        ema_series = indicator_calculator.calculate_ema(df, period)
        
        values = []
        for idx in range(-data_points, 0):
            if not pd.isna(ema_series.iloc[idx]):
                values.append({
                    'timestamp': df.index[idx].isoformat(),
                    'value': round(ema_series.iloc[idx], 2)
                })
        
        return BaseResponse(
            success=True,
            message=f"EMA({period}) calculated successfully",
            data={
                'symbol': symbol,
                'indicator': 'ema',
                'period': period,
                'timeframe': timeframe,
                'values': values
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error calculating EMA: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calculate/rsi")
async def calculate_rsi_endpoint(
    symbol: str,
    period: int = Query(14, ge=2, le=100),
    timeframe: str = Query("1day"),
    data_points: int = Query(1, ge=1, le=100)
):
    """Calculate Relative Strength Index (RSI) on demand"""
    try:
        required_periods = period + data_points + 10  # Extra for RSI calculation
        
        df = await indicator_calculator.get_historical_data(
            symbol, timeframe, required_periods
        )
        
        rsi_series = indicator_calculator.calculate_rsi(df, period)
        
        values = []
        for idx in range(-data_points, 0):
            if not pd.isna(rsi_series.iloc[idx]):
                values.append({
                    'timestamp': df.index[idx].isoformat(),
                    'value': round(rsi_series.iloc[idx], 2)
                })
        
        return BaseResponse(
            success=True,
            message=f"RSI({period}) calculated successfully",
            data={
                'symbol': symbol,
                'indicator': 'rsi',
                'period': period,
                'timeframe': timeframe,
                'values': values
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error calculating RSI: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calculate/macd")
async def calculate_macd_endpoint(
    symbol: str,
    fast_period: int = Query(12, ge=1, le=100),
    slow_period: int = Query(26, ge=1, le=200),
    signal_period: int = Query(9, ge=1, le=100),
    timeframe: str = Query("1day"),
    data_points: int = Query(1, ge=1, le=100)
):
    """Calculate MACD on demand"""
    try:
        required_periods = slow_period * 2 + data_points
        
        df = await indicator_calculator.get_historical_data(
            symbol, timeframe, required_periods
        )
        
        macd_result = indicator_calculator.calculate_macd(
            df, fast_period, slow_period, signal_period
        )
        
        values = []
        for idx in range(-data_points, 0):
            if not pd.isna(macd_result['macd'].iloc[idx]):
                values.append({
                    'timestamp': df.index[idx].isoformat(),
                    'macd': round(macd_result['macd'].iloc[idx], 2),
                    'signal': round(macd_result['signal'].iloc[idx], 2),
                    'histogram': round(macd_result['histogram'].iloc[idx], 2)
                })
        
        return BaseResponse(
            success=True,
            message="MACD calculated successfully",
            data={
                'symbol': symbol,
                'indicator': 'macd',
                'fast_period': fast_period,
                'slow_period': slow_period,
                'signal_period': signal_period,
                'timeframe': timeframe,
                'values': values
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error calculating MACD: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calculate/bollinger_bands")
async def calculate_bollinger_bands_endpoint(
    symbol: str,
    period: int = Query(20, ge=2, le=200),
    std_dev: int = Query(2, ge=1, le=3),
    timeframe: str = Query("1day"),
    data_points: int = Query(1, ge=1, le=100)
):
    """Calculate Bollinger Bands on demand"""
    try:
        required_periods = period + data_points - 1
        
        df = await indicator_calculator.get_historical_data(
            symbol, timeframe, required_periods
        )
        
        bb_result = indicator_calculator.calculate_bollinger_bands(
            df, period, std_dev
        )
        
        values = []
        for idx in range(-data_points, 0):
            if not pd.isna(bb_result['middle'].iloc[idx]):
                values.append({
                    'timestamp': df.index[idx].isoformat(),
                    'upper': round(bb_result['upper'].iloc[idx], 2),
                    'middle': round(bb_result['middle'].iloc[idx], 2),
                    'lower': round(bb_result['lower'].iloc[idx], 2)
                })
        
        return BaseResponse(
            success=True,
            message=f"Bollinger Bands({period},{std_dev}) calculated successfully",
            data={
                'symbol': symbol,
                'indicator': 'bollinger_bands',
                'period': period,
                'std_dev': std_dev,
                'timeframe': timeframe,
                'values': values
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error calculating Bollinger Bands: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calculate/batch")
async def calculate_batch_indicators(
    request: Dict[str, Any]
):
    """
    Calculate multiple indicators in one request
    
    Request format:
    {
        "symbol": "NSE@RELIANCE@equities",
        "timeframe": "1day",
        "indicators": [
            {"type": "sma", "params": {"period": 20}},
            {"type": "ema", "params": {"period": 12}},
            {"type": "rsi", "params": {"period": 14}}
        ]
    }
    """
    try:
        symbol = request.get('symbol')
        timeframe = request.get('timeframe', '1day')
        indicators = request.get('indicators', [])
        
        if not symbol or not indicators:
            raise HTTPException(
                status_code=400, 
                detail="Symbol and indicators list required"
            )
        
        # Calculate max periods needed
        max_periods = 50  # Default
        for ind in indicators:
            if ind['type'] in ['sma', 'ema']:
                max_periods = max(max_periods, ind['params'].get('period', 20) * 2)
            elif ind['type'] == 'macd':
                max_periods = max(max_periods, ind['params'].get('slow_period', 26) * 2)
        
        # Get historical data once
        df = await indicator_calculator.get_historical_data(
            symbol, timeframe, max_periods
        )
        
        # Calculate all indicators
        results = {}
        
        for ind in indicators:
            ind_type = ind['type']
            params = ind.get('params', {})
            
            try:
                if ind_type == 'sma':
                    period = params.get('period', 20)
                    series = indicator_calculator.calculate_sma(df, period)
                    results[f'sma_{period}'] = {
                        'value': round(series.iloc[-1], 2) if not pd.isna(series.iloc[-1]) else None,
                        'timestamp': df.index[-1].isoformat()
                    }
                
                elif ind_type == 'ema':
                    period = params.get('period', 12)
                    series = indicator_calculator.calculate_ema(df, period)
                    results[f'ema_{period}'] = {
                        'value': round(series.iloc[-1], 2) if not pd.isna(series.iloc[-1]) else None,
                        'timestamp': df.index[-1].isoformat()
                    }
                
                elif ind_type == 'rsi':
                    period = params.get('period', 14)
                    series = indicator_calculator.calculate_rsi(df, period)
                    results[f'rsi_{period}'] = {
                        'value': round(series.iloc[-1], 2) if not pd.isna(series.iloc[-1]) else None,
                        'timestamp': df.index[-1].isoformat()
                    }
                
                elif ind_type == 'macd':
                    fast = params.get('fast_period', 12)
                    slow = params.get('slow_period', 26)
                    signal = params.get('signal_period', 9)
                    macd_result = indicator_calculator.calculate_macd(df, fast, slow, signal)
                    results['macd'] = {
                        'macd': round(macd_result['macd'].iloc[-1], 2),
                        'signal': round(macd_result['signal'].iloc[-1], 2),
                        'histogram': round(macd_result['histogram'].iloc[-1], 2),
                        'timestamp': df.index[-1].isoformat()
                    }
                
            except Exception as e:
                results[ind_type] = {'error': str(e)}
        
        # Add current price info
        current_price = {
            'open': round(df['open'].iloc[-1], 2),
            'high': round(df['high'].iloc[-1], 2),
            'low': round(df['low'].iloc[-1], 2),
            'close': round(df['close'].iloc[-1], 2),
            'volume': int(df['volume'].iloc[-1]),
            'timestamp': df.index[-1].isoformat()
        }
        
        return BaseResponse(
            success=True,
            message="Batch indicators calculated successfully",
            data={
                'symbol': symbol,
                'timeframe': timeframe,
                'current_price': current_price,
                'indicators': results
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error in batch calculation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/worker-affinity/status")
async def get_worker_affinity_status():
    """Get current worker affinity status and statistics"""
    try:
        affinity_manager = await get_worker_affinity_manager()
        stats = await affinity_manager.get_affinity_stats()
        
        return BaseResponse(
            success=True,
            message="Worker affinity status retrieved",
            data=stats
        )
        
    except Exception as e:
        log_exception(f"Error getting worker affinity status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/worker-affinity/check/{symbol}")
async def check_symbol_affinity(symbol: str):
    """Check which worker should handle a specific symbol"""
    try:
        affinity_manager = await get_worker_affinity_manager()
        assigned_worker = await affinity_manager.get_worker_for_symbol(symbol)
        should_handle = await affinity_manager.should_handle_computation(symbol)
        
        return BaseResponse(
            success=True,
            message="Symbol affinity checked",
            data={
                'symbol': symbol,
                'assigned_worker': assigned_worker,
                'current_worker': affinity_manager.worker_id,
                'should_handle': should_handle
            }
        )
        
    except Exception as e:
        log_exception(f"Error checking symbol affinity: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/available-indicators")
async def get_available_indicators():
    """Get list of all available pandas_ta indicators with their parameters"""
    try:
        indicators = indicator_calculator.get_available_indicators()
        
        # Format for API response
        formatted_indicators = {}
        for name, info in indicators.items():
            formatted_indicators[name] = {
                'parameters': info['parameters'],
                'description': info['doc'].split('\n')[0] if info['doc'] else 'No description'
            }
        
        return BaseResponse(
            success=True,
            message=f"Found {len(formatted_indicators)} available indicators",
            data=formatted_indicators
        )
        
    except Exception as e:
        log_exception(f"Error getting available indicators: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calculate/dynamic/{indicator}")
async def calculate_dynamic_indicator(
    indicator: str,
    symbol: str,
    timeframe: str = Query("1day", regex="^(1day|1hour|30min|15min|5min|1min)$"),
    data_points: int = Query(1, ge=1, le=100),
    params: Dict[str, Any] = {}
):
    """
    Calculate any pandas_ta indicator dynamically
    
    Args:
        indicator: Name of the pandas_ta indicator (e.g., 'sma', 'ema', 'bbands', 'stoch', etc.)
        symbol: Instrument key (e.g., NSE@RELIANCE@equities)
        timeframe: Data timeframe
        data_points: Number of values to return
        params: Indicator-specific parameters (e.g., {"length": 20} for SMA)
    """
    try:
        # For single data point, use caching
        if data_points == 1:
            # Create cache key from params
            cache_params = f"{indicator}_{json.dumps(params, sort_keys=True)}"
            
            async def calculate():
                # Determine periods needed based on indicator
                required_periods = params.get('length', params.get('period', 50)) * 2 + 50
                
                df = await indicator_calculator.get_historical_data(
                    symbol, timeframe, required_periods
                )
                
                result_df = await indicator_calculator.calculate_dynamic_indicator(
                    df, indicator, **params
                )
                
                # Get the last value(s)
                if len(result_df.columns) == 1:
                    return {
                        'value': round(result_df.iloc[-1, 0], 4),
                        'timestamp': df.index[-1]
                    }
                else:
                    # Multiple columns (like Bollinger Bands)
                    values = {}
                    for col in result_df.columns:
                        if not pd.isna(result_df[col].iloc[-1]):
                            values[col] = round(result_df[col].iloc[-1], 4)
                    return {
                        'values': values,
                        'timestamp': df.index[-1]
                    }
            
            # Use cached calculation
            result = await cached_indicator_calculation(
                symbol=symbol,
                indicator=indicator,
                period=params.get('length', params.get('period', 20)),
                timeframe=timeframe,
                calculation_func=calculate
            )
            
            return BaseResponse(
                success=True,
                message=f"{indicator} {'retrieved from cache' if result.get('cached') else 'calculated'}",
                data={
                    'symbol': symbol,
                    'indicator': indicator,
                    'params': params,
                    'timeframe': timeframe,
                    'result': result.get('value') or result.get('values'),
                    'timestamp': result['timestamp'].isoformat(),
                    'cached': result.get('cached', False)
                }
            )
        
        # Multiple data points - calculate fresh
        required_periods = params.get('length', params.get('period', 50)) * 2 + data_points + 50
        
        df = await indicator_calculator.get_historical_data(
            symbol, timeframe, required_periods
        )
        
        result_df = await indicator_calculator.calculate_dynamic_indicator(
            df, indicator, **params
        )
        
        # Prepare response values
        values = []
        
        if len(result_df.columns) == 1:
            # Single column result
            for idx in range(-data_points, 0):
                if idx >= -len(result_df):
                    val = result_df.iloc[idx, 0]
                    if not pd.isna(val):
                        values.append({
                            'timestamp': df.index[idx].isoformat(),
                            'value': round(val, 4)
                        })
        else:
            # Multiple columns (like Bollinger Bands)
            for idx in range(-data_points, 0):
                if idx >= -len(result_df):
                    row_values = {}
                    for col in result_df.columns:
                        if not pd.isna(result_df[col].iloc[idx]):
                            row_values[col] = round(result_df[col].iloc[idx], 4)
                    
                    if row_values:
                        values.append({
                            'timestamp': df.index[idx].isoformat(),
                            'values': row_values
                        })
        
        return BaseResponse(
            success=True,
            message=f"{indicator} calculated successfully",
            data={
                'symbol': symbol,
                'indicator': indicator,
                'params': params,
                'timeframe': timeframe,
                'values': values,
                'cached': False
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error calculating {indicator}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calculate/dynamic-batch")
async def calculate_dynamic_batch(
    request: Dict[str, Any]
):
    """
    Calculate multiple pandas_ta indicators in one request
    
    Request format:
    {
        "symbol": "NSE@RELIANCE@equities",
        "timeframe": "1day",
        "indicators": [
            {"name": "sma", "params": {"length": 20}},
            {"name": "ema", "params": {"length": 12}},
            {"name": "bbands", "params": {"length": 20, "std": 2}},
            {"name": "rsi", "params": {"length": 14}},
            {"name": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
            {"name": "stoch", "params": {"k": 14, "d": 3, "smooth_k": 3}}
        ]
    }
    """
    try:
        symbol = request.get('symbol')
        timeframe = request.get('timeframe', '1day')
        indicators = request.get('indicators', [])
        
        if not symbol or not indicators:
            raise HTTPException(
                status_code=400,
                detail="Symbol and indicators list required"
            )
        
        # Calculate max periods needed
        max_periods = 100  # Default minimum
        for ind in indicators:
            params = ind.get('params', {})
            # Check various parameter names used by pandas_ta
            for param_name in ['length', 'period', 'slow', 'timeperiod', 'window']:
                if param_name in params:
                    max_periods = max(max_periods, params[param_name] * 2 + 50)
        
        # Get historical data once
        df = await indicator_calculator.get_historical_data(
            symbol, timeframe, max_periods
        )
        
        # Calculate all indicators
        results = {}
        
        for ind in indicators:
            ind_name = ind['name']
            params = ind.get('params', {})
            
            try:
                result_df = await indicator_calculator.calculate_dynamic_indicator(
                    df, ind_name, **params
                )
                
                # Get latest values
                if len(result_df.columns) == 1:
                    val = result_df.iloc[-1, 0]
                    results[ind_name] = {
                        'value': round(val, 4) if not pd.isna(val) else None,
                        'timestamp': df.index[-1].isoformat(),
                        'params': params
                    }
                else:
                    # Multiple columns
                    values = {}
                    for col in result_df.columns:
                        if not pd.isna(result_df[col].iloc[-1]):
                            values[col] = round(result_df[col].iloc[-1], 4)
                    
                    results[ind_name] = {
                        'values': values,
                        'timestamp': df.index[-1].isoformat(),
                        'params': params
                    }
                    
            except Exception as e:
                results[ind_name] = {
                    'error': str(e),
                    'params': params
                }
        
        # Add current price info
        current_price = {
            'open': round(df['open'].iloc[-1], 2),
            'high': round(df['high'].iloc[-1], 2),
            'low': round(df['low'].iloc[-1], 2),
            'close': round(df['close'].iloc[-1], 2),
            'volume': int(df['volume'].iloc[-1]),
            'timestamp': df.index[-1].isoformat()
        }
        
        return BaseResponse(
            success=True,
            message="Dynamic batch indicators calculated successfully",
            data={
                'symbol': symbol,
                'timeframe': timeframe,
                'current_price': current_price,
                'indicators': results
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error in dynamic batch calculation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
