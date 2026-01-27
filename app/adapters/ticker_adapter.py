"""
Enhanced Ticker Adapter for Signal Service.
Handles the new enhanced tick format with timezone and currency support.
"""
import logging
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

import httpx
import pandas as pd
import pytz

from app.core.config import settings
from app.errors import ComputationError, DataAccessError
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


class Currency(Enum):
    """Supported currencies matching ticker service."""
    INR = "INR"  # Indian Rupee
    USD = "USD"  # US Dollar
    EUR = "EUR"  # Euro
    GBP = "GBP"  # British Pound
    JPY = "JPY"  # Japanese Yen
    CNY = "CNY"  # Chinese Yuan
    AUD = "AUD"  # Australian Dollar
    CAD = "CAD"  # Canadian Dollar
    CHF = "CHF"  # Swiss Franc
    HKD = "HKD"  # Hong Kong Dollar
    SGD = "SGD"  # Singapore Dollar
    # Crypto base currencies
    BTC = "BTC"  # Bitcoin
    ETH = "ETH"  # Ethereum
    USDT = "USDT"  # Tether
    USDC = "USDC"  # USD Coin


class AssetClass(Enum):
    """Asset classes for proper handling."""
    EQUITY = "equity"
    DERIVATIVE = "derivative"
    COMMODITY = "commodity"
    CURRENCY = "currency"
    CRYPTO = "crypto"
    INDEX = "index"


class CurrencyHandler:
    """Handles currency conversions for cross-currency indicators."""

    def __init__(self):
        self.conversion_cache = {}
        self.cache_ttl = 300  # 5 minutes
        self.last_update = {}

    async def convert(self, amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
        """
        Convert amount from one currency to another.
        Uses cached rates when available.
        """
        if from_currency == to_currency:
            return amount

        cache_key = f"{from_currency}_{to_currency}"

        # Check cache
        if cache_key in self.conversion_cache:
            last_update = self.last_update.get(cache_key, 0)
            if (utcnow().timestamp() - last_update) < self.cache_ttl:
                rate = self.conversion_cache[cache_key]
                return amount * rate

        # Fetch latest rate (simplified - in production would call forex service)
        rate = await self._fetch_conversion_rate(from_currency, to_currency)

        # Update cache
        self.conversion_cache[cache_key] = rate
        self.last_update[cache_key] = utcnow().timestamp()

        return amount * rate

    async def _fetch_conversion_rate(self, from_currency: str, to_currency: str) -> Decimal:
        """
        Fetch conversion rate from external service.
        This is a simplified implementation - in production would integrate with
        actual forex data provider.
        """
        # Simplified static rates for demonstration
        # In production, this would call a forex API or use rates from ticker data
        static_rates = {
            "USD_INR": Decimal("83.50"),
            "INR_USD": Decimal("0.01197"),
            "EUR_USD": Decimal("1.08"),
            "USD_EUR": Decimal("0.926"),
            "GBP_USD": Decimal("1.27"),
            "USD_GBP": Decimal("0.787"),
            "USDT_USD": Decimal("1.0"),
            "USD_USDT": Decimal("1.0"),
            "BTC_USD": Decimal("45000"),
            "USD_BTC": Decimal("0.000022"),
            "ETH_USD": Decimal("2500"),
            "USD_ETH": Decimal("0.0004"),
        }

        rate_key = f"{from_currency}_{to_currency}"
        if rate_key in static_rates:
            return static_rates[rate_key]

        # If no direct rate, try through USD
        if from_currency != "USD" and to_currency != "USD":
            from_usd_key = f"{from_currency}_USD"
            usd_to_key = f"USD_{to_currency}"

            if from_usd_key in static_rates and usd_to_key in static_rates:
                return static_rates[from_usd_key] * static_rates[usd_to_key]

        # Default to 1 if no rate found
        logger.warning("No conversion rate found for %s to %s, using 1.0", from_currency, to_currency)
        return Decimal("1.0")


class TimezoneHandler:
    """Handles timezone conversions for multi-region support."""

    def __init__(self):
        self.exchange_timezones = {
            "NSE": "Asia/Kolkata",
            "BSE": "Asia/Kolkata",
            "NFO": "Asia/Kolkata",
            "MCX": "Asia/Kolkata",
            "NYSE": "America/New_York",
            "NASDAQ": "America/New_York",
            "BINANCE": "UTC",
            "FOREX": "UTC"
        }

    def convert_time(self, timestamp: datetime, from_tz: str, to_tz: str) -> datetime:
        """Convert timestamp from one timezone to another."""
        if from_tz == to_tz:
            return timestamp

        # Ensure timestamp is timezone aware
        if timestamp.tzinfo is None:
            from_timezone = pytz.timezone(from_tz)
            timestamp = from_timezone.localize(timestamp)

        # Convert to target timezone
        to_timezone = pytz.timezone(to_tz)
        return timestamp.astimezone(to_timezone)

    def get_market_hours(self, exchange: str, date: datetime) -> tuple[datetime, datetime]:
        """Get market open and close times for an exchange on a given date."""
        market_hours = {
            "NSE": ("09:15", "15:30"),
            "BSE": ("09:15", "15:30"),
            "NFO": ("09:15", "15:30"),
            "MCX": ("09:00", "23:30"),
            "NYSE": ("09:30", "16:00"),
            "NASDAQ": ("09:30", "16:00"),
            "BINANCE": ("00:00", "23:59"),  # 24/7
            "FOREX": ("00:00", "23:59")  # 24/5
        }

        if exchange not in market_hours:
            return None, None

        tz_name = self.exchange_timezones.get(exchange, "UTC")
        tz = pytz.timezone(tz_name)

        open_time_str, close_time_str = market_hours[exchange]

        # Parse times and localize to exchange timezone
        open_hour, open_min = map(int, open_time_str.split(":"))
        close_hour, close_min = map(int, close_time_str.split(":"))

        open_time = tz.localize(date.replace(hour=open_hour, minute=open_min, second=0, microsecond=0))
        close_time = tz.localize(date.replace(hour=close_hour, minute=close_min, second=0, microsecond=0))

        return open_time, close_time


class EnhancedTickerAdapter:
    """
    Adapter for enhanced ticker data model.
    Handles the new format with nested price data and timezone information.
    """

    def __init__(self, base_url: str = None):
        self.currency_handler = CurrencyHandler()
        self.timezone_handler = TimezoneHandler()
        self._logger = logging.getLogger(__name__)

        # Get ticker_service URL from config_service exclusively (Architecture Principle #1)
        try:
            from common.config_service.client import ConfigServiceClient
            config_client = ConfigServiceClient(
                service_name="signal_service",
                environment=settings.environment
            )

            self.base_url = base_url or config_client.get_service_url('ticker_service')
            internal_api_key = config_client.get_config('INTERNAL_API_KEY')

            if not internal_api_key:
                raise RuntimeError("INTERNAL_API_KEY not found in config_service. Required for ticker_service authentication.")

        except Exception as e:
            raise RuntimeError(f"Failed to get ticker_service configuration from config_service: {e}. No hardcoded fallbacks allowed per architecture.")

        # Initialize HTTP client for ticker_service
        self.http_client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=30.0,
            headers={
                'Content-Type': 'application/json',
                'X-Internal-API-Key': internal_api_key,
                'User-Agent': 'signal-service/ticker-adapter'
            }
        )

        # Cache for instrument metadata
        self.instrument_cache = {}
        self.cache_ttl = 3600  # 1 hour

        logger.info(f"EnhancedTickerAdapter initialized with ticker_service at {self.base_url}")

    async def get_frequency_configuration(self):
        return {}

    async def subscribe_to_feeds(self, instruments: list[str]):
        return True

    async def notify_backpressure(self, *_args, **_kwargs):
        return True

    async def get_latest_price(self, instrument_key: str = None, **kwargs) -> float:
        """
        Get latest price from ticker_service.

        Args:
            instrument_key: Instrument identifier
            **kwargs: Additional parameters

        Returns:
            Latest price from ticker_service
        """
        try:
            if not instrument_key:
                raise ValueError("instrument_key is required for get_latest_price")

            # Call ticker_service API
            response = await self.http_client.get(f"/api/v1/latest/{instrument_key}")
            response.raise_for_status()

            data = response.json()
            price = data.get('price', data.get('ltp', 0.0))

            if price == 0.0:
                logger.warning(f"ticker_service returned zero price for {instrument_key}")

            return float(price)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ValueError(f"Instrument {instrument_key} not found in ticker_service")
            raise DataAccessError(f"ticker_service error for {instrument_key}: {e.response.status_code}")
        except Exception as e:
            raise DataAccessError(f"Failed to get latest price for {instrument_key}: {e}")

    async def process_tick(self, tick_data: dict[str, Any]) -> dict[str, Any]:
        """
        Process enhanced tick format.
        Extracts and normalizes data for signal processing.
        """
        try:
            # Extract core fields
            instrument_key = tick_data.get("ik")
            asset_class = tick_data.get("ac", "equity")

            # Extract nested price data
            ltp_data = tick_data.get("ltp", {})
            if isinstance(ltp_data, dict):
                ltp = Decimal(str(ltp_data.get("value", 0)))
                currency = ltp_data.get("currency", "USD")
            else:
                # Handle legacy format
                ltp = Decimal(str(tick_data.get("ltp", 0)))
                currency = tick_data.get("cur", "USD")

            # Extract timezone information
            exchange_time_str = tick_data.get("ts_exch")
            exchange_tz = tick_data.get("tz", "UTC")

            if exchange_time_str:
                exchange_time = datetime.fromisoformat(exchange_time_str.replace('Z', '+00:00'))
            else:
                exchange_time = datetime.utcnow()

            # Create processed tick data
            processed_tick = {
                "instrument_key": instrument_key,
                "asset_class": asset_class,
                "ltp": {
                    "value": ltp,
                    "currency": currency
                },
                "timestamp": {
                    "exchange": exchange_time,
                    "timezone": exchange_tz,
                    "utc": self.timezone_handler.convert_time(exchange_time, exchange_tz, "UTC")
                },
                "volume": tick_data.get("v"),
                "oi": tick_data.get("oi"),
                "bid": self._extract_price_data(tick_data, "b", currency),
                "ask": self._extract_price_data(tick_data, "a", currency),
                "open": self._extract_price_data(tick_data, "o", currency),
                "high": self._extract_price_data(tick_data, "h", currency),
                "low": self._extract_price_data(tick_data, "l", currency),
                "close": self._extract_price_data(tick_data, "c", currency),
                "mode": tick_data.get("mode", "full"),
                "broker_source": tick_data.get("bs")
            }

            # Add optional fields
            if "chg" in tick_data:
                processed_tick["change"] = {
                    "value": Decimal(str(tick_data["chg"])),
                    "currency": currency
                }

            if "chgp" in tick_data:
                processed_tick["change_percent"] = float(tick_data["chgp"])

            # Handle forex/crypto pairs
            if "bc" in tick_data and "qc" in tick_data:
                processed_tick["base_currency"] = tick_data["bc"]
                processed_tick["quote_currency"] = tick_data["qc"]

            return processed_tick

        except Exception as e:
            logger.exception("Error processing enhanced tick: %s", e)
            raise DataAccessError(f"Failed to process tick data: {str(e)}")

    def _extract_price_data(self, tick_data: dict, field: str, default_currency: str) -> dict | None:
        """Extract price data from tick, handling both nested and flat formats."""
        if field not in tick_data:
            return None

        value = tick_data[field]
        if isinstance(value, dict):
            return {
                "value": Decimal(str(value.get("value", 0))),
                "currency": value.get("currency", default_currency)
            }
        if value is not None:
            return {
                "value": Decimal(str(value)),
                "currency": default_currency
            }

        return None

    async def prepare_for_indicators(
        self,
        processed_tick: dict[str, Any],
        target_currency: str | None = None
    ) -> dict[str, Any]:
        """
        Prepare tick data for indicator calculations.
        Handles currency conversion if needed.
        """
        try:
            indicator_data = {
                "instrument_key": processed_tick["instrument_key"],
                "timestamp": processed_tick["timestamp"]["utc"],
                "exchange_time": processed_tick["timestamp"]["exchange"],
                "timezone": processed_tick["timestamp"]["timezone"],
                "volume": processed_tick.get("volume", 0),
                "oi": processed_tick.get("oi", 0)
            }

            # Get base currency
            base_currency = processed_tick["ltp"]["currency"]

            # Price fields to convert
            price_fields = ["ltp", "bid", "ask", "open", "high", "low", "close", "change"]

            for field in price_fields:
                if field in processed_tick and processed_tick[field]:
                    price_data = processed_tick[field]
                    value = price_data["value"]
                    currency = price_data.get("currency", base_currency)

                    # Convert if needed
                    if target_currency and currency != target_currency:
                        converted_value = await self.currency_handler.convert(
                            value, currency, target_currency
                        )
                        indicator_data[field] = float(converted_value)
                        indicator_data[f"{field}_original"] = float(value)
                        indicator_data[f"{field}_currency"] = currency
                    else:
                        indicator_data[field] = float(value)
                        indicator_data[f"{field}_currency"] = currency

            # Add change percent (currency agnostic)
            if "change_percent" in processed_tick:
                indicator_data["change_percent"] = processed_tick["change_percent"]

            return indicator_data

        except Exception as e:
            logger.exception("Error preparing data for indicators: %s", e)
            raise ComputationError(f"Failed to prepare indicator data: {str(e)}")

    async def calculate_indicators(
        self,
        instrument_key: str,
        ltp: Decimal,
        exchange_time: datetime,
        currency: str,
        historical_data: list[dict] | None = None
    ) -> dict[str, Any]:
        """
        Calculate indicators with timezone and currency awareness.
        Production implementation requires pandas_ta_executor integration.
        """
        try:
            # Production implementation requires indicator calculation service integration
            from app.errors import ComputationError
            raise ComputationError(f"Indicator calculation requires pandas_ta_executor integration - cannot compute indicators for {instrument_key}")

        except Exception as e:
            logger.exception("Error calculating indicators: %s", e)
            from app.errors import ComputationError
            raise ComputationError(f"Failed to calculate indicators: {str(e)}")

    def requires_usd_conversion(self, asset_class: str) -> bool:
        """
        Check if asset class requires USD conversion for indicators.
        Some indicators may need standardized USD values for comparison.
        """
        # Asset classes that typically need USD conversion
        usd_required = ["crypto", "currency", "commodity"]
        return asset_class.lower() in usd_required

    async def validate_tick_data(self, tick_data: dict[str, Any]) -> tuple[bool, str | None]:
        """
        Validate enhanced tick data format.
        Returns (is_valid, error_message).
        """
        try:
            # Required fields
            required_fields = ["ik", "ltp", "ts_exch", "tz"]

            for field in required_fields:
                if field not in tick_data:
                    return False, f"Missing required field: {field}"

            # Validate LTP format
            ltp = tick_data.get("ltp")
            if isinstance(ltp, dict):
                if "value" not in ltp or "currency" not in ltp:
                    return False, "Invalid LTP format: missing value or currency"
            elif not isinstance(ltp, (int, float, str)):
                return False, "Invalid LTP format: must be dict or numeric"

            # Validate timezone
            tz = tick_data.get("tz")
            try:
                pytz.timezone(tz)
            except Exception:
                return False, f"Invalid timezone: {tz}"

            # Validate timestamp
            try:
                datetime.fromisoformat(tick_data.get("ts_exch").replace('Z', '+00:00'))
            except Exception:
                return False, "Invalid exchange timestamp format"

            return True, None

        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def get_exchange_from_instrument(self, instrument_key: str) -> str:
        """Extract exchange from instrument key."""
        # New standardized format: EXCHANGE@SYMBOL@PRODUCT_TYPE[@expiry][@option_type][@strike]
        if "@" in instrument_key:
            return instrument_key.split("@")[0]
        # Legacy format support: EXCHANGE:SYMBOL
        if ":" in instrument_key:
            return instrument_key.split(":")[0]
        return "UNKNOWN"

    async def get_option_price(self, underlying: str, strike: float, expiry: str, option_type: str, **kwargs) -> float:
        """
        Get option market price from ticker_service.

        Args:
            underlying: Underlying symbol
            strike: Strike price
            expiry: Expiry date
            option_type: 'call' or 'put'

        Returns:
            Current market price of the option
        """
        try:
            # Call ticker_service for option price
            params = {
                'underlying': underlying,
                'strike': strike,
                'expiry': expiry,
                'option_type': option_type
            }
            params.update(kwargs)

            response = await self.http_client.get("/api/v1/options/price", params=params)
            response.raise_for_status()

            data = response.json()
            return float(data.get('price', data.get('ltp', 0.0)))

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ValueError(f"Option {underlying} {strike} {option_type} not found in ticker_service")
            raise DataAccessError(f"ticker_service error for option price: {e.response.status_code}")
        except Exception as e:
            raise DataAccessError(f"Failed to get option price for {underlying} {strike} {option_type}: {e}")

    async def get_historical_options(
        self,
        underlying: str,
        expiry_date: str,
        timestamp: datetime = None,
        moneyness_level: str = None,
        **kwargs
    ) -> list[dict[str, Any]]:
        """
        Get historical option chain data from ticker_service.

        Args:
            underlying: Underlying symbol
            expiry_date: Option expiry date
            timestamp: Historical timestamp (optional)
            moneyness_level: Moneyness level filter (optional)

        Returns:
            List of historical option data
        """
        try:
            # Call ticker_service for historical option chain
            params = {
                'underlying': underlying,
                'expiry_date': expiry_date
            }
            if timestamp:
                params['timestamp'] = timestamp.isoformat()
            if moneyness_level:
                params['moneyness_level'] = moneyness_level
            params.update(kwargs)

            response = await self.http_client.get("/api/v1/options/historical", params=params)
            response.raise_for_status()

            data = response.json()
            return data.get('options', [])

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ValueError(f"Historical options for {underlying} at {timestamp} not found in ticker_service")
            raise DataAccessError(f"ticker_service error for historical options: {e.response.status_code}")
        except Exception as e:
            raise DataAccessError(f"Failed to get historical options for {underlying} at {timestamp}: {e}")

    async def get_option_iv(
        self,
        underlying: str,
        strike: float,
        expiry: str,
        option_type: str,
        timestamp: datetime = None,
        **kwargs
    ) -> float | None:
        """
        Get option implied volatility from ticker_service.

        Args:
            underlying: Underlying symbol
            strike: Strike price
            expiry: Expiry date
            option_type: 'call' or 'put'
            timestamp: Historical timestamp (optional)

        Returns:
            Implied volatility or None if not available
        """
        try:
            # Call ticker_service for option IV
            params = {
                'underlying': underlying,
                'strike': strike,
                'expiry': expiry,
                'option_type': option_type
            }
            if timestamp:
                params['timestamp'] = timestamp.isoformat()
            params.update(kwargs)

            response = await self.http_client.get("/api/v1/options/iv", params=params)
            response.raise_for_status()

            data = response.json()
            iv = data.get('iv', data.get('implied_volatility'))
            return float(iv) if iv is not None else None

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ValueError(f"IV for {underlying} {strike} {option_type} not found in ticker_service")
            raise DataAccessError(f"ticker_service error for option IV: {e.response.status_code}")
        except Exception as e:
            raise DataAccessError(f"Failed to get option IV for {underlying} {strike} {option_type}: {e}")

    async def get_option_chain(
        self,
        underlying: str,
        expiry: str = None,
        **kwargs
    ) -> list[dict[str, Any]]:
        """
        Get option chain data from ticker_service.

        Args:
            underlying: Underlying symbol
            expiry: Option expiry date (optional)

        Returns:
            List of option chain data
        """
        try:
            # Call ticker_service for option chain
            params = {'underlying': underlying}
            if expiry:
                params['expiry'] = expiry
            params.update(kwargs)

            response = await self.http_client.get("/api/v1/options/chain", params=params)
            response.raise_for_status()

            data = response.json()
            return data.get('options', data.get('chain', []))

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ValueError(f"Option chain for {underlying} not found in ticker_service")
            raise DataAccessError(f"ticker_service error for option chain: {e.response.status_code}")
        except Exception as e:
            raise DataAccessError(f"Failed to get option chain for {underlying}: {e}")

    async def get_historical_data(
        self,
        symbol: str,
        timeframe: str = "1day",
        periods: int = 100,
        start_date: str = None,
        end_date: str = None,
        interval: str = None,
        **kwargs
    ) -> pd.DataFrame:
        """
        Get historical OHLCV data from ticker_service.

        Args:
            symbol: Symbol to fetch data for
            timeframe: Time interval (e.g., "1day", "1hour", "5minute")
            periods: Number of periods to fetch
            start_date: Start date (YYYY-MM-DD format)
            end_date: End date (YYYY-MM-DD format)
            interval: Time interval (alternative to timeframe)

        Returns:
            DataFrame with historical OHLCV data
        """
        try:
            # Call ticker_service for historical data
            params = {
                'symbol': symbol,
                'timeframe': interval or timeframe,  # Support both interval and timeframe
                'periods': periods
            }

            if start_date:
                params['start_date'] = start_date
            if end_date:
                params['end_date'] = end_date

            params.update(kwargs)

            response = await self.http_client.get("/api/v1/historical", params=params)
            response.raise_for_status()

            data = response.json()
            historical_records = data.get('data', data.get('historical', []))

            # Convert to DataFrame
            if not historical_records:
                # Return empty DataFrame with expected columns
                return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            df = pd.DataFrame(historical_records)

            # Ensure timestamp is datetime and set as index if present
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
            elif 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)

            # Ensure numeric columns are properly typed
            numeric_columns = ['open', 'high', 'low', 'close', 'volume', 'oi']
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            return df

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ValueError(f"Historical data for {symbol} not found in ticker_service")
            raise DataAccessError(f"ticker_service error for historical data: {e.response.status_code}")
        except Exception as e:
            raise DataAccessError(f"Failed to get historical data for {symbol}: {e}")

    async def close(self):
        """Close the HTTP client connection"""
        if self.http_client:
            await self.http_client.aclose()


# Alias to maintain backward compatibility with tests
TickerAdapter = EnhancedTickerAdapter
