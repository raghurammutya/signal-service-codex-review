"""
Test suite for Enhanced Ticker Adapter.
Validates handling of enhanced tick format with timezone and currency support.
"""
import pytest
import asyncio
from datetime import datetime
from decimal import Decimal
import pytz

from app.adapters import EnhancedTickerAdapter, Currency, AssetClass


class TestEnhancedTickerAdapter:
    """Test cases for enhanced ticker adapter."""
    
    @pytest.fixture
    def adapter(self):
        """Create ticker adapter instance."""
        return EnhancedTickerAdapter()
    
    @pytest.fixture
    def sample_enhanced_tick(self):
        """Sample enhanced tick data with nested format."""
        return {
            "ik": "NSE:RELIANCE",
            "bs": "kite_prod_1",
            "ac": "equity",
            "ts_utc": "2024-01-15T10:30:00Z",
            "ts_exch": "2024-01-15T16:00:00+05:30",
            "tz": "Asia/Kolkata",
            "ltp": {
                "value": "2450.50",
                "currency": "INR"
            },
            "open": {
                "value": "2440.00",
                "currency": "INR"
            },
            "high": {
                "value": "2455.00",
                "currency": "INR"
            },
            "low": {
                "value": "2435.00",
                "currency": "INR"
            },
            "close": {
                "value": "2450.50",
                "currency": "INR"
            },
            "v": 1250000,
            "oi": 0,
            "b": {
                "value": "2450.00",
                "currency": "INR"
            },
            "a": {
                "value": "2451.00",
                "currency": "INR"
            },
            "bq": 500,
            "aq": 750,
            "chg": {
                "value": "10.50",
                "currency": "INR"
            },
            "chgp": 0.43,
            "mode": "full",
            "rt": True
        }
    
    @pytest.fixture
    def sample_crypto_tick(self):
        """Sample crypto tick with USD base."""
        return {
            "ik": "BINANCE:BTCUSDT",
            "bs": "binance_prod",
            "ac": "crypto",
            "ts_utc": "2024-01-15T10:30:00Z",
            "ts_exch": "2024-01-15T10:30:00Z",
            "tz": "UTC",
            "ltp": {
                "value": "45250.50",
                "currency": "USDT"
            },
            "bc": "BTC",
            "qc": "USDT",
            "v": 15000,
            "b": {
                "value": "45250.00",
                "currency": "USDT"
            },
            "a": {
                "value": "45251.00",
                "currency": "USDT"
            },
            "mode": "quote"
        }
    
    @pytest.fixture
    def sample_legacy_tick(self):
        """Sample legacy tick format for backward compatibility."""
        return {
            "ik": "NSE:TATAMOTORS",
            "ltp": 650.50,
            "cur": "INR",
            "ts_exch": "2024-01-15T16:00:00+05:30",
            "tz": "Asia/Kolkata",
            "v": 500000,
            "o": 648.00,
            "h": 652.00,
            "l": 647.00,
            "c": 650.50
        }
    
    @pytest.mark.asyncio
    async def test_process_enhanced_tick(self, adapter, sample_enhanced_tick):
        """Test processing of enhanced tick format."""
        processed = await adapter.process_tick(sample_enhanced_tick)
        
        assert processed["instrument_key"] == "NSE:RELIANCE"
        assert processed["asset_class"] == "equity"
        assert processed["ltp"]["value"] == Decimal("2450.50")
        assert processed["ltp"]["currency"] == "INR"
        assert processed["volume"] == 1250000
        assert processed["timestamp"]["timezone"] == "Asia/Kolkata"
        assert isinstance(processed["timestamp"]["exchange"], datetime)
        assert isinstance(processed["timestamp"]["utc"], datetime)
    
    @pytest.mark.asyncio
    async def test_process_crypto_tick(self, adapter, sample_crypto_tick):
        """Test processing of crypto tick with base/quote currencies."""
        processed = await adapter.process_tick(sample_crypto_tick)
        
        assert processed["instrument_key"] == "BINANCE:BTCUSDT"
        assert processed["asset_class"] == "crypto"
        assert processed["ltp"]["value"] == Decimal("45250.50")
        assert processed["ltp"]["currency"] == "USDT"
        assert processed["base_currency"] == "BTC"
        assert processed["quote_currency"] == "USDT"
        assert processed["timestamp"]["timezone"] == "UTC"
    
    @pytest.mark.asyncio
    async def test_process_legacy_tick(self, adapter, sample_legacy_tick):
        """Test backward compatibility with legacy format."""
        processed = await adapter.process_tick(sample_legacy_tick)
        
        assert processed["instrument_key"] == "NSE:TATAMOTORS"
        assert processed["ltp"]["value"] == Decimal("650.50")
        assert processed["ltp"]["currency"] == "INR"
        assert processed["open"]["value"] == Decimal("648.00")
    
    @pytest.mark.asyncio
    async def test_currency_conversion(self, adapter):
        """Test currency conversion functionality."""
        # Test INR to USD conversion
        inr_amount = Decimal("83500")
        usd_amount = await adapter.currency_handler.convert(inr_amount, "INR", "USD")
        assert abs(float(usd_amount) - 1000.0) < 10  # Allow small variance
        
        # Test same currency (no conversion)
        same_amount = await adapter.currency_handler.convert(inr_amount, "INR", "INR")
        assert same_amount == inr_amount
        
        # Test USD to EUR conversion (through USD)
        eur_amount = await adapter.currency_handler.convert(Decimal("100"), "USD", "EUR")
        assert eur_amount > 0
    
    def test_timezone_conversion(self, adapter):
        """Test timezone conversion functionality."""
        # Create IST time
        ist_tz = pytz.timezone("Asia/Kolkata")
        ist_time = ist_tz.localize(datetime(2024, 1, 15, 15, 30, 0))
        
        # Convert to NYC time
        nyc_time = adapter.timezone_handler.convert_time(
            ist_time, "Asia/Kolkata", "America/New_York"
        )
        
        assert nyc_time.tzinfo.zone == "America/New_York"
        assert nyc_time.hour == 5  # 15:30 IST = 05:00 EST
    
    def test_market_hours_detection(self, adapter):
        """Test market hours detection for different exchanges."""
        # Test NSE market hours
        ist_tz = pytz.timezone("Asia/Kolkata")
        test_date = ist_tz.localize(datetime(2024, 1, 15, 0, 0, 0))
        
        open_time, close_time = adapter.timezone_handler.get_market_hours("NSE", test_date)
        assert open_time.hour == 9
        assert open_time.minute == 15
        assert close_time.hour == 15
        assert close_time.minute == 30
        
        # Test NASDAQ market hours
        nyc_tz = pytz.timezone("America/New_York")
        test_date_nyc = nyc_tz.localize(datetime(2024, 1, 15, 0, 0, 0))
        
        open_time, close_time = adapter.timezone_handler.get_market_hours("NASDAQ", test_date_nyc)
        assert open_time.hour == 9
        assert open_time.minute == 30
        assert close_time.hour == 16
        assert close_time.minute == 0
    
    @pytest.mark.asyncio
    async def test_validate_tick_data(self, adapter, sample_enhanced_tick):
        """Test tick data validation."""
        # Valid tick
        is_valid, error = await adapter.validate_tick_data(sample_enhanced_tick)
        assert is_valid
        assert error is None
        
        # Missing required field
        invalid_tick = sample_enhanced_tick.copy()
        del invalid_tick["ik"]
        is_valid, error = await adapter.validate_tick_data(invalid_tick)
        assert not is_valid
        assert "Missing required field: ik" in error
        
        # Invalid timezone
        invalid_tick = sample_enhanced_tick.copy()
        invalid_tick["tz"] = "Invalid/Timezone"
        is_valid, error = await adapter.validate_tick_data(invalid_tick)
        assert not is_valid
        assert "Invalid timezone" in error
    
    @pytest.mark.asyncio
    async def test_prepare_for_indicators(self, adapter, sample_enhanced_tick):
        """Test data preparation for indicator calculations."""
        processed = await adapter.process_tick(sample_enhanced_tick)
        
        # Prepare without currency conversion
        indicator_data = await adapter.prepare_for_indicators(processed)
        
        assert indicator_data["instrument_key"] == "NSE:RELIANCE"
        assert indicator_data["ltp"] == 2450.50
        assert indicator_data["ltp_currency"] == "INR"
        assert indicator_data["volume"] == 1250000
        assert isinstance(indicator_data["timestamp"], datetime)
        
        # Prepare with USD conversion
        indicator_data_usd = await adapter.prepare_for_indicators(processed, "USD")
        
        assert indicator_data_usd["ltp_original"] == 2450.50
        assert indicator_data_usd["ltp_currency"] == "INR"
        assert indicator_data_usd["ltp"] != indicator_data_usd["ltp_original"]  # Converted
    
    def test_requires_usd_conversion(self, adapter):
        """Test asset class USD conversion requirements."""
        assert adapter.requires_usd_conversion("crypto")
        assert adapter.requires_usd_conversion("currency")
        assert adapter.requires_usd_conversion("commodity")
        assert not adapter.requires_usd_conversion("equity")
        assert not adapter.requires_usd_conversion("derivative")
    
    def test_exchange_extraction(self, adapter):
        """Test exchange extraction from instrument key."""
        assert adapter.get_exchange_from_instrument("NSE:RELIANCE") == "NSE"
        assert adapter.get_exchange_from_instrument("NASDAQ:AAPL") == "NASDAQ"
        assert adapter.get_exchange_from_instrument("BINANCE:BTCUSDT") == "BINANCE"
        assert adapter.get_exchange_from_instrument("INVALID") == "UNKNOWN"
    
    @pytest.mark.asyncio
    async def test_enrich_with_metadata(self, adapter, sample_enhanced_tick):
        """Test metadata enrichment."""
        processed = await adapter.process_tick(sample_enhanced_tick)
        enriched = await adapter.enrich_with_metadata(processed)
        
        assert "metadata" in enriched
        assert enriched["metadata"]["exchange"] == "NSE"
        assert isinstance(enriched["metadata"]["is_market_open"], bool)
        assert "processing_timestamp" in enriched["metadata"]
        
        # During market hours (16:00 IST = within NSE hours)
        if enriched["metadata"]["market_hours"]:
            assert enriched["metadata"]["market_hours"]["open"] is not None
            assert enriched["metadata"]["market_hours"]["close"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])