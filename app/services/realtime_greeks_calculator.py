"""Real-time Greeks calculator for single tick processing"""
import json
from datetime import datetime
from typing import Any

from app.adapters import EnhancedTickerAdapter
from app.core.config import settings
from app.errors import GreeksCalculationError
from app.schemas.config_schema import SignalConfigData, TickProcessingContext
from app.services.greeks_calculation_engine import GreeksCalculationEngine
from app.utils.logging_utils import log_exception, log_info, log_warning


class RealTimeGreeksCalculator:
    """
    Real-time Greeks calculator for processing individual ticks
    Handles out-of-order data arrival and caches intermediate results
    """

    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.engine = GreeksCalculationEngine()
        self.ticker_adapter = EnhancedTickerAdapter()
        self.underlying_buffer = {}  # Buffer for out-of-order underlying data
        self.indvix_cache = {}  # Cache for INDVIX data

        log_info("RealTimeGreeksCalculator initialized")

    async def calculate_realtime_greeks(
        self,
        config: SignalConfigData,
        context: TickProcessingContext
    ) -> dict[str, Any]:
        """Calculate Greeks for real-time tick data"""
        try:
            instrument_key = context.instrument_key
            greeks_config = config.option_greeks

            if not greeks_config or not greeks_config.enabled:
                return {}

            log_info(f"Calculating real-time Greeks for {instrument_key}")

            # Extract option details from instrument key
            option_details = self.extract_option_details(instrument_key)
            if not option_details:
                log_warning(f"Could not extract option details from {instrument_key}")
                return {}

            # Get current option price from tick data
            option_price = self.extract_option_price(context.tick_data)
            if not option_price:
                log_warning("Could not extract option price from tick data")
                return {}

            # Get underlying price (with buffering for out-of-order arrival)
            underlying_price = await self.get_underlying_price(
                option_details['underlying_symbol'],
                context.timestamp
            )

            if not underlying_price:
                log_warning(f"Could not get underlying price for {option_details['underlying_symbol']}")
                return {}

            # Get volatility (INDVIX or implied)
            volatility = await self.get_volatility(
                option_details,
                option_price,
                underlying_price,
                greeks_config
            )

            if not volatility:
                log_warning("Could not get volatility for Greeks calculation")
                return {}

            # Calculate time to expiry
            time_to_expiry = self.engine.calculate_time_to_expiry(option_details['expiry_date'])

            # Calculate all requested Greeks
            greeks = await self.engine.calculate_all_greeks(
                underlying_price,
                option_details['strike'],
                time_to_expiry,
                volatility,
                option_details['option_type'],
                greeks_config.risk_free_rate,
                greeks_config.calculate
            )

            # Cache results for future use
            await self.cache_results(instrument_key, {
                'timestamp': context.timestamp.isoformat(),
                'option_price': option_price,
                'underlying_price': underlying_price,
                'volatility': volatility,
                'time_to_expiry': time_to_expiry,
                'greeks': greeks
            })

            log_info(f"Calculated real-time Greeks for {instrument_key}: {list(greeks.keys())}")

            # Extract currency and timezone from context
            currency = None
            timezone = None
            if isinstance(context.tick_data, dict):
                ltp_data = context.tick_data.get('ltp', {})
                if isinstance(ltp_data, dict):
                    currency = ltp_data.get('currency', 'INR')
                timestamp_data = context.tick_data.get('timestamp', {})
                if isinstance(timestamp_data, dict):
                    timezone = timestamp_data.get('timezone', 'Asia/Kolkata')

            return {
                "instrument_key": instrument_key,
                "calculation_type": "realtime",
                "timestamp": context.timestamp.isoformat(),
                "option_price": option_price,
                "underlying_price": underlying_price,
                "volatility": volatility,
                "time_to_expiry": time_to_expiry,
                "greeks": greeks,
                "metadata": {
                    "risk_free_rate": greeks_config.risk_free_rate,
                    "underlying_symbol": option_details['underlying_symbol'],
                    "strike": option_details['strike'],
                    "option_type": option_details['option_type'],
                    "expiry_date": option_details['expiry_date'],
                    "currency": currency or 'INR',
                    "timezone": timezone or 'Asia/Kolkata'
                }
            }

        except Exception as e:
            error = GreeksCalculationError(f"Real-time Greeks calculation failed: {str(e)}")
            log_exception(f"Error in real-time Greeks calculation: {error}")
            raise error

    def extract_option_details(self, instrument_key: str) -> dict | None:
        """Extract option details from instrument key"""
        try:
            # Format: EXCHANGE@SYMBOL@TYPE@EXPIRY@OPTION_TYPE@STRIKE
            parts = instrument_key.split('@')

            if len(parts) >= 6:
                exchange = parts[0]
                symbol = parts[1]
                instrument_type = parts[2]
                expiry_str = parts[3]
                option_type = parts[4]
                strike_str = parts[5]

                # Parse expiry date
                expiry_date = self.parse_expiry_date(expiry_str)
                if not expiry_date:
                    return None

                # Parse strike price
                try:
                    strike = float(strike_str)
                except ValueError:
                    return None

                underlying_symbol = f"{exchange}@{symbol}@{instrument_type}"

                return {
                    'underlying_symbol': underlying_symbol,
                    'strike': strike,
                    'option_type': option_type,
                    'expiry_date': expiry_date,
                    'exchange': exchange,
                    'symbol': symbol
                }

            return None

        except Exception as e:
            log_exception(f"Failed to extract option details from {instrument_key}: {e}")
            return None

    def parse_expiry_date(self, expiry_str: str) -> str | None:
        """Parse expiry date string to standard format"""
        try:
            # Convert format like "25DEC25" to "2025-12-25"
            if len(expiry_str) == 7:  # Format: 25DEC25
                day = expiry_str[:2]
                month_str = expiry_str[2:5]
                year = "20" + expiry_str[5:]

                month_map = {
                    'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
                    'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
                    'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'
                }

                month = month_map.get(month_str.upper())
                if month:
                    return f"{year}-{month}-{day}"

            return None

        except Exception as e:
            log_exception(f"Failed to parse expiry date {expiry_str}: {e}")
            return None

    def extract_option_price(self, tick_data: dict) -> float | None:
        """Extract option price from enhanced tick data format"""
        try:
            # Handle enhanced tick format with nested price data
            if 'ltp' in tick_data:
                ltp_data = tick_data['ltp']
                if isinstance(ltp_data, dict):
                    # Enhanced format with nested price data
                    price = ltp_data.get('value')
                    if price is not None:
                        return float(price)
                else:
                    # Legacy format
                    return float(ltp_data)

            # Fallback to other price fields
            price_fields = ['close', 'last_traded_price', 'price']

            for field in price_fields:
                if field in tick_data:
                    price_data = tick_data[field]
                    if isinstance(price_data, dict):
                        price = price_data.get('value')
                    else:
                        price = price_data

                    if price is not None:
                        try:
                            return float(price)
                        except (ValueError, TypeError):
                            continue

            return None

        except Exception as e:
            log_exception(f"Failed to extract option price from enhanced tick: {e}")
            return None

    async def get_underlying_price(self, underlying_symbol: str, timestamp: datetime) -> float | None:
        """Get underlying price with buffering for out-of-order data"""
        try:
            # Try to get from buffer first (for recent data)
            buffer_key = f"underlying_buffer:{underlying_symbol}"

            if buffer_key in self.underlying_buffer:
                buffer_data = self.underlying_buffer[buffer_key]
                # Check if data is recent enough (within 5 seconds)
                if (timestamp - buffer_data['timestamp']).total_seconds() <= 5:
                    return buffer_data['price']

            # Get from Redis cache
            cache_key = f"underlying_price:{underlying_symbol}"
            cached_data = await self.redis_client.get(cache_key)

            if cached_data:
                try:
                    data = json.loads(cached_data)
                    price = data.get('price')
                    data_timestamp = datetime.fromisoformat(data.get('timestamp', ''))

                    # Check if data is recent (within 10 seconds)
                    if (timestamp - data_timestamp).total_seconds() <= 10:
                        # Update buffer
                        self.underlying_buffer[buffer_key] = {
                            'price': price,
                            'timestamp': data_timestamp
                        }
                        return price
                except Exception as e:
                    log_exception(f"Failed to parse cached underlying data: {e}")

            # Fallback: get last known good value
            return await self.get_last_known_underlying_price(underlying_symbol)

        except Exception as e:
            log_exception(f"Failed to get underlying price for {underlying_symbol}: {e}")
            return None

    async def get_last_known_underlying_price(self, underlying_symbol: str) -> float | None:
        """Get last known good underlying price"""
        try:
            # Try to get from raw ticks cache
            raw_ticks_key = f"raw_ticks:{underlying_symbol}"
            recent_ticks = await self.redis_client.lrange(raw_ticks_key, 0, 9)  # Last 10 ticks

            for tick_data in recent_ticks:
                try:
                    tick = json.loads(tick_data)
                    price = self.extract_option_price(tick)  # Reuse price extraction logic
                    if price:
                        return price
                except Exception:
                    continue

            # No fallback - fail if underlying price not available
            raise ValueError(f"Underlying price not available for {underlying_symbol}")

        except Exception as e:
            log_exception(f"Failed to get last known underlying price: {e}")
            raise

    async def get_volatility(
        self,
        option_details: dict,
        option_price: float,
        underlying_price: float,
        greeks_config
    ) -> float | None:
        """Get volatility from INDVIX or calculate implied volatility"""
        try:
            if greeks_config.use_indvix:
                # Get INDVIX volatility
                volatility = await self.get_indvix_volatility()
                if volatility:
                    return volatility

            # Calculate implied volatility as fallback
            time_to_expiry = self.engine.calculate_time_to_expiry(option_details['expiry_date'])

            implied_vol = await self.engine.calculate_implied_volatility(
                option_price,
                underlying_price,
                option_details['strike'],
                time_to_expiry,
                option_details['option_type'],
                greeks_config.risk_free_rate
            )

            return implied_vol

        except Exception as e:
            log_exception(f"Failed to get volatility: {e}")
            raise

    async def get_indvix_volatility(self) -> float | None:
        """Get current INDVIX volatility"""
        try:
            # Check cache first
            cache_key = "indvix:current"
            cached_data = await self.redis_client.get(cache_key)

            if cached_data:
                try:
                    data = json.loads(cached_data)
                    volatility = data.get('volatility') or data.get('close') or data.get('ltp')

                    if volatility:
                        # Convert to decimal if it's in percentage
                        vol_float = float(volatility)
                        if vol_float > 1:  # Assuming percentage format
                            vol_float = vol_float / 100
                        return vol_float
                except Exception as e:
                    log_exception(f"Failed to parse INDVIX data: {e}")

            # No fallback - return None if INDVIX not available
            return None

        except Exception as e:
            log_exception(f"Failed to get INDVIX volatility: {e}")
            return None

    async def cache_results(self, instrument_key: str, results: dict):
        """Cache Greeks calculation results"""
        try:
            cache_key = f"greeks_cache:{instrument_key}"
            await self.redis_client.setex(
                cache_key,
                300,  # 5 minutes TTL
                json.dumps(results)
            )
        except Exception as e:
            log_exception(f"Failed to cache Greeks results: {e}")

    def get_metrics(self) -> dict[str, Any]:
        """Get calculator metrics"""
        return {
            "underlying_buffer_size": len(self.underlying_buffer),
            "indvix_cache_size": len(self.indvix_cache),
            "engine_available": True,
            "buffer_timeout_ms": settings.UNDERLYING_BUFFER_TIMEOUT_MS
        }
