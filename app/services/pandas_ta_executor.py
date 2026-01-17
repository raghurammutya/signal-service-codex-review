"""Technical Indicators executor using pandas_ta"""
import asyncio
import json
from typing import Dict, List, Optional, Any
import pandas as pd
from datetime import datetime
from decimal import Decimal

try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False

from app.utils.logging_utils import log_info, log_exception, log_warning

from app.core.config import settings
from app.errors import TechnicalIndicatorError
from app.schemas.config_schema import SignalConfigData, TickProcessingContext, TechnicalIndicatorConfig
from app.adapters import EnhancedTickerAdapter
from app.services.indicator_registry import IndicatorRegistry
from app.services.historical_data_manager import get_historical_data_manager


class PandasTAExecutor:
    """
    Technical Indicators executor using pandas_ta library
    Processes indicators efficiently using dynamic strategy construction
    """
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.ticker_adapter = EnhancedTickerAdapter()
        
        if not PANDAS_TA_AVAILABLE:
            log_warning("pandas_ta not available - technical indicator results will be unavailable")
        
        log_info("PandasTAExecutor initialized")
    
    async def execute_indicators(
        self, 
        config: SignalConfigData, 
        context: TickProcessingContext
    ) -> Dict[str, Any]:
        """Execute technical indicators for the given configuration"""
        try:
            if not config.technical_indicators:
                return {}
            
            instrument_key = context.instrument_key
            log_info(f"Executing technical indicators for {instrument_key}: {len(config.technical_indicators)} indicators")
            
            # Get historical data for indicators
            df = await self.prepare_dataframe(instrument_key, config, context)
            
            if df is None or df.empty:
                log_warning(f"No data available for technical indicators: {instrument_key}")
                return {}
            
            # Build and execute strategy
            strategy_dict = self.build_strategy(config.technical_indicators)
            
            if not strategy_dict:
                log_warning("No valid strategy built from indicators")
                return {}
            
            # Execute indicators
            results = await self.execute_strategy(df, strategy_dict, config.technical_indicators)
            
            # Cache results if enabled
            if config.output.cache_results:
                await self.cache_results(instrument_key, config, results)
            
            log_info(f"Executed {len(results)} technical indicators for {instrument_key}")
            
            # Extract currency from context
            currency = None
            if isinstance(context.tick_data, dict):
                ltp_data = context.tick_data.get('ltp', {})
                if isinstance(ltp_data, dict):
                    currency = ltp_data.get('currency', 'USD')
                else:
                    currency = context.tick_data.get('currency', 'USD')
            
            return {
                "instrument_key": instrument_key,
                "calculation_type": "technical_indicators",
                "indicators_count": len(results),
                "data_points": len(df),
                "results": results,
                "metadata": {
                    "interval": config.interval.value,
                    "frequency": config.frequency.value,
                    "timestamp": context.timestamp.isoformat(),
                    "currency": currency,
                    "timezone": context.tick_data.get('timestamp', {}).get('timezone', 'UTC') if isinstance(context.tick_data, dict) else 'UTC'
                }
            }
            
        except Exception as e:
            error = TechnicalIndicatorError(f"Technical indicators execution failed: {str(e)}")
            log_exception(f"Error in technical indicators execution: {error}")
            raise error
    
    async def prepare_dataframe(
        self, 
        instrument_key: str, 
        config: SignalConfigData, 
        context: TickProcessingContext
    ) -> Optional[pd.DataFrame]:
        """Prepare pandas DataFrame for technical analysis"""
        try:
            # Try to get from cache first
            cache_key = f"ta_data:{instrument_key}:{config.interval.value}"
            cached_data = await self.redis_client.get(cache_key)
            
            if cached_data:
                try:
                    data = json.loads(cached_data)
                    df = pd.DataFrame(data)
                    
                    # Add current tick data
                    current_tick = self.extract_ohlcv_from_tick(context.tick_data, context.timestamp)
                    if current_tick:
                        df = pd.concat([df, pd.DataFrame([current_tick])], ignore_index=True)
                    
                    return self.format_dataframe(df)
                except Exception as e:
                    log_exception(f"Failed to use cached TA data: {e}")
            
            # Get aggregated data from context
            if context.aggregated_data and config.interval.value in context.aggregated_data:
                data = context.aggregated_data[config.interval.value]
                
                if isinstance(data, list) and data:
                    df = pd.DataFrame(data)
                    
                    # Add current tick
                    current_tick = self.extract_ohlcv_from_tick(context.tick_data, context.timestamp)
                    if current_tick:
                        df = pd.concat([df, pd.DataFrame([current_tick])], ignore_index=True)
                    
                    # Cache for future use
                    await self.redis_client.setex(
                        cache_key,
                        settings.CACHE_TTL_SECONDS,
                        json.dumps(df.to_dict('records'))
                    )
                    
                    return self.format_dataframe(df)
            
            # Enhanced Fallback: Try to get historical data from ticker_service
            try:
                historical_manager = await get_historical_data_manager()
                if historical_manager and context.instrument_key:
                    symbol = context.instrument_key.replace("@", "-")  # Convert NSE@RELIANCE@EQ to RELIANCE format
                    
                    # Map interval to timeframe
                    timeframe_map = {
                        "1m": "1minute",
                        "3m": "3minute", 
                        "5m": "5minute",
                        "15m": "15minute",
                        "30m": "30minute",
                        "1h": "1hour",
                        "1d": "1day"
                    }
                    timeframe = timeframe_map.get(config.interval.value, "5minute")
                    
                    # Get sufficient historical data for indicator calculation
                    periods_needed = max(50, getattr(config.parameters, 'length', 14) * 3)
                    
                    log_info(f"Fetching historical data for {symbol} ({timeframe}) - {periods_needed} periods")
                    historical_result = await historical_manager.get_historical_data_for_indicator(
                        symbol=symbol,
                        timeframe=timeframe,
                        periods_required=periods_needed,
                        indicator_name=config.indicator
                    )
                    
                    if historical_result.get("success") and historical_result.get("data"):
                        # Convert historical data to DataFrame
                        df = pd.DataFrame(historical_result["data"])
                        if not df.empty and all(col in df.columns for col in ['open', 'high', 'low', 'close']):
                            # Add current tick to historical data
                            current_tick = self.extract_ohlcv_from_tick(context.tick_data, context.timestamp)
                            if current_tick:
                                df = pd.concat([df, pd.DataFrame([current_tick])], ignore_index=True)
                            
                            # Cache the combined data
                            await self.redis_client.setex(
                                cache_key,
                                settings.CACHE_TTL_SECONDS,
                                json.dumps(df.to_dict('records'))
                            )
                            
                            log_info(f"Successfully prepared DataFrame with {len(df)} periods from historical data")
                            return self.format_dataframe(df)
                        
            except Exception as e:
                log_warning(f"Historical data fallback failed: {e}")
            
            # Final fallback: create minimal DataFrame from current tick
            current_tick = self.extract_ohlcv_from_tick(context.tick_data, context.timestamp)
            if current_tick:
                df = pd.DataFrame([current_tick])
                log_warning("Using single-tick DataFrame - indicator accuracy may be limited")
                return self.format_dataframe(df)
            
            return None
            
        except Exception as e:
            log_exception(f"Failed to prepare DataFrame: {e}")
            return None
    
    def extract_ohlcv_from_tick(self, tick_data: Dict, timestamp: datetime) -> Optional[Dict]:
        """Extract OHLCV data from enhanced tick format"""
        try:
            # Map tick fields to OHLCV
            ohlcv = {}
            
            # Handle enhanced tick format with nested price data
            price = None
            currency = None
            
            # Extract LTP from enhanced format
            if 'ltp' in tick_data:
                if isinstance(tick_data['ltp'], dict):
                    # Enhanced format with nested price data
                    price = float(tick_data['ltp'].get('value', 0))
                    currency = tick_data['ltp'].get('currency', 'USD')
                else:
                    # Legacy format
                    price = float(tick_data['ltp'])
                    currency = tick_data.get('currency', 'USD')
            
            if price is None:
                return None
            
            # Extract OHLC values from enhanced format
            def extract_price_value(field_name: str, default: float) -> float:
                if field_name in tick_data:
                    field_value = tick_data[field_name]
                    if isinstance(field_value, dict):
                        return float(field_value.get('value', default))
                    else:
                        return float(field_value)
                return default
            
            # For real-time ticks, OHLC might be the same as LTP
            ohlcv['open'] = extract_price_value('open', price)
            ohlcv['high'] = extract_price_value('high', price)
            ohlcv['low'] = extract_price_value('low', price)
            ohlcv['close'] = price
            ohlcv['volume'] = float(tick_data.get('volume', 0))
            ohlcv['timestamp'] = timestamp
            ohlcv['currency'] = currency
            
            # Add additional metadata if available
            if 'metadata' in tick_data:
                ohlcv['exchange'] = tick_data['metadata'].get('exchange')
                ohlcv['is_market_open'] = tick_data['metadata'].get('is_market_open')
            
            return ohlcv
            
        except Exception as e:
            log_exception(f"Failed to extract OHLCV from enhanced tick: {e}")
            return None
    
    def format_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Format DataFrame for pandas_ta"""
        try:
            # Ensure required columns exist
            required_columns = ['open', 'high', 'low', 'close', 'volume']
            
            for col in required_columns:
                if col not in df.columns:
                    if col == 'volume':
                        df[col] = 0  # Default volume
                    else:
                        df[col] = df['close'] if 'close' in df.columns else 0
            
            # Convert to numeric
            for col in required_columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Handle timestamp
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.sort_values('timestamp').reset_index(drop=True)
            
            # Ensure minimum data points for indicators
            if len(df) < 2:
                # Duplicate last row to have minimum data
                if len(df) == 1:
                    df = pd.concat([df, df], ignore_index=True)
                else:
                    # Create dummy data
                    dummy_row = {col: 100.0 for col in required_columns}
                    df = pd.DataFrame([dummy_row, dummy_row])
            
            return df
            
        except Exception as e:
            log_exception(f"Failed to format DataFrame: {e}")
            return df
    
    async def prepare_currency_converted_data(
        self,
        df: pd.DataFrame,
        from_currency: str,
        to_currency: str,
        instrument_key: str
    ) -> pd.DataFrame:
        """
        Prepare DataFrame with currency conversion for cross-currency indicators.
        Useful for comparing indicators across different currency pairs.
        """
        try:
            if from_currency == to_currency:
                return df
            
            # Check if we need USD conversion for this asset class
            exchange = self.ticker_adapter.get_exchange_from_instrument(instrument_key)
            asset_class = 'equity'  # Default, would need instrument service for accurate classification
            
            if exchange in ['BINANCE', 'FOREX']:
                asset_class = 'crypto' if exchange == 'BINANCE' else 'currency'
            
            if not self.ticker_adapter.requires_usd_conversion(asset_class):
                return df
            
            # Convert price columns
            price_columns = ['open', 'high', 'low', 'close']
            converted_df = df.copy()
            
            for col in price_columns:
                if col in converted_df.columns:
                    # Convert each price value
                    for idx in converted_df.index:
                        original_value = converted_df.loc[idx, col]
                        if pd.notna(original_value):
                            converted_value = await self.ticker_adapter.currency_handler.convert(
                                Decimal(str(original_value)),
                                from_currency,
                                to_currency
                            )
                            converted_df.loc[idx, col] = float(converted_value)
            
            # Add metadata about conversion
            converted_df['original_currency'] = from_currency
            converted_df['converted_currency'] = to_currency
            
            return converted_df
            
        except Exception as e:
            log_warning(f"Failed to convert currency for DataFrame: {e}")
            return df
    
    def build_strategy(self, indicators: List[TechnicalIndicatorConfig]) -> Dict[str, Any]:
        """Build pandas_ta strategy from indicator configurations"""
        try:
            if not PANDAS_TA_AVAILABLE:
                return {}
            
            strategy_dict = {}
            
            for indicator in indicators:
                try:
                    indicator_name = indicator.name.lower()
                    parameters = indicator.parameters.copy()
                    
                    # Map common parameter names
                    param_mapping = {
                        'period': 'length',
                        'periods': 'length',
                        'window': 'length'
                    }
                    
                    for old_key, new_key in param_mapping.items():
                        if old_key in parameters:
                            parameters[new_key] = parameters.pop(old_key)
                    
                    # Validate parameters for specific indicators
                    parameters = self.validate_indicator_parameters(indicator_name, parameters)
                    
                    # Add to strategy
                    if indicator_name not in strategy_dict:
                        strategy_dict[indicator_name] = []
                    
                    strategy_dict[indicator_name].append({
                        "kind": indicator_name,
                        **parameters
                    })
                    
                except Exception as e:
                    log_exception(f"Failed to add indicator {indicator.name} to strategy: {e}")
                    continue
            
            return strategy_dict
            
        except Exception as e:
            log_exception(f"Failed to build strategy: {e}")
            return {}
    
    def validate_indicator_parameters(self, indicator_name: str, parameters: Dict) -> Dict:
        """Validate and adjust parameters for specific indicators"""
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
                'willr': {'length': 14}
            }
            
            # Apply defaults
            if indicator_name in defaults:
                for key, value in defaults[indicator_name].items():
                    if key not in parameters:
                        parameters[key] = value
            
            # Ensure minimum length for period-based indicators
            if 'length' in parameters:
                parameters['length'] = max(1, int(parameters.get('length', 14)))
            
            return parameters
            
        except Exception as e:
            log_exception(f"Failed to validate parameters for {indicator_name}: {e}")
            return parameters
    
    async def execute_strategy(
        self,
        df: pd.DataFrame,
        strategy_dict: Dict,
        indicators: List[TechnicalIndicatorConfig]
    ) -> Dict[str, Any]:
        """
        Execute indicators - checks custom registry first, then falls back to pandas_ta.

        This allows seamless integration of custom indicators (SMC, scipy, etc.)
        alongside standard pandas_ta indicators.
        """
        try:
            results = {}
            pandas_ta_indicators = []

            # First pass: Execute custom registry indicators
            for indicator in indicators:
                indicator_name = indicator.name.lower()
                output_key = indicator.output_key

                # Check if this is a custom indicator
                custom_indicator = IndicatorRegistry.get(indicator_name)

                if custom_indicator:
                    # Execute custom indicator
                    try:
                        log_info(f"Executing custom indicator: {indicator_name} ({custom_indicator.library})")

                        # Call the indicator function with parameters
                        params = indicator.parameters.copy() if indicator.parameters else {}
                        result = custom_indicator.function(df, **params)

                        # Handle different output types
                        if custom_indicator.output_type == "series":
                            # Return latest value
                            if isinstance(result, pd.Series):
                                results[output_key] = float(result.iloc[-1]) if not result.empty and pd.notna(result.iloc[-1]) else None
                            else:
                                results[output_key] = result

                        elif custom_indicator.output_type == "dataframe":
                            # Convert DataFrame to dict
                            if isinstance(result, pd.DataFrame):
                                results[output_key] = result.to_dict('records')
                            else:
                                results[output_key] = result

                        elif custom_indicator.output_type == "dict":
                            # Already a dict
                            results[output_key] = result

                        elif custom_indicator.output_type == "float":
                            results[output_key] = float(result) if result is not None else None

                        else:
                            results[output_key] = result

                        log_info(f"  ✓ {indicator_name} executed successfully")

                    except Exception as e:
                        log_exception(f"Error executing custom indicator {indicator_name}: {e}")
                        results[output_key] = None
                else:
                    # Not a custom indicator, add to pandas_ta batch
                    pandas_ta_indicators.append(indicator)

            # Second pass: Execute pandas_ta indicators if any
            if pandas_ta_indicators:
                if not PANDAS_TA_AVAILABLE:
                    # Fail fast when pandas_ta not available in production
                    raise TechnicalIndicatorError("pandas_ta library not available - cannot calculate technical indicators")
                else:
                    log_info(f"Executing {len(pandas_ta_indicators)} pandas_ta indicators")

                    # Execute pandas_ta strategy
                    result_df = await asyncio.get_event_loop().run_in_executor(
                        None,
                        self._execute_strategy_sync,
                        df,
                        strategy_dict
                    )

                    # Extract results for pandas_ta indicators
                    for indicator in pandas_ta_indicators:
                        try:
                            output_key = indicator.output_key
                            indicator_name = indicator.name.lower()

                            # Find the result column(s)
                            result_columns = [col for col in result_df.columns if indicator_name in col.lower()]

                            if result_columns:
                                # Get the last (most recent) value
                                if len(result_columns) == 1:
                                    # Single value indicator
                                    value = result_df[result_columns[0]].iloc[-1]
                                    results[output_key] = float(value) if pd.notna(value) else None
                                else:
                                    # Multi-value indicator (like MACD)
                                    indicator_result = {}
                                    for col in result_columns:
                                        col_key = col.split('_')[-1]  # Get suffix like 'signal', 'histogram'
                                        value = result_df[col].iloc[-1]
                                        indicator_result[col_key] = float(value) if pd.notna(value) else None
                                    results[output_key] = indicator_result
                            else:
                                log_warning(f"No result found for pandas_ta indicator {indicator.name}")
                                results[output_key] = None

                        except Exception as e:
                            log_exception(f"Failed to extract result for {indicator.name}: {e}")
                            results[indicator.output_key] = None

            return results

        except Exception as e:
            log_exception(f"Failed to execute strategy: {e}")
            # Fail fast instead of synthetic results
            raise ValueError(f"Technical indicator strategy execution failed: {e}. No mock data allowed in production.")
    
    def _execute_strategy_sync(self, df: pd.DataFrame, strategy_dict: Dict) -> pd.DataFrame:
        """Synchronous strategy execution (for thread pool)"""
        try:
            # Create custom strategy
            custom_strategy = ta.Strategy(
                name="SignalService",
                description="Custom strategy for signal service",
                ta=strategy_dict
            )
            
            # Execute strategy
            df.ta.strategy(custom_strategy)
            
            return df
            
        except Exception as e:
            log_exception(f"Strategy execution failed: {e}")
            return df
    
    
    async def cache_results(
        self, 
        instrument_key: str, 
        config: SignalConfigData, 
        results: Dict
    ):
        """Cache technical indicator results"""
        try:
            cache_key = settings.get_ta_results_cache_key(
                instrument_key, 
                config.interval.value, 
                config.frequency.value
            )
            
            cache_data = {
                'timestamp': datetime.utcnow().isoformat(),
                'results': results
            }
            
            await self.redis_client.setex(
                cache_key,
                config.output.cache_ttl_seconds,
                json.dumps(cache_data)
            )
            
        except Exception as e:
            log_exception(f"Failed to cache TA results: {e}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get executor metrics"""
        return {
            "pandas_ta_available": PANDAS_TA_AVAILABLE,
            "max_ta_periods": settings.TA_MAX_PERIODS,
            "cache_enabled": settings.TA_CACHE_RESULTS
        }
