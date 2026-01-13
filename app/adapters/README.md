# Enhanced Ticker Adapter for Signal Service

## Overview

The Enhanced Ticker Adapter handles the new enhanced tick format from the ticker service, which includes nested price data with currency information and timezone support. This adapter ensures proper processing of multi-region, multi-currency tick data for signal computations.

## Key Features

### 1. Enhanced Tick Format Support
- Handles nested price data structure with `value` and `currency` fields
- Backward compatible with legacy flat format
- Supports all asset classes: equity, derivative, commodity, currency, crypto

### 2. Currency Handling
- Built-in currency conversion for cross-currency indicators
- Supports major currencies: INR, USD, EUR, GBP, JPY, etc.
- Crypto currencies: BTC, ETH, USDT, USDC
- Automatic USD conversion for assets requiring standardization

### 3. Timezone Management
- Handles multiple exchange timezones
- Converts between timezones for global trading
- Market hours detection for each exchange
- Timezone-aware timestamp processing

### 4. Data Validation
- Validates enhanced tick format
- Ensures required fields are present
- Validates timezone and timestamp formats
- Currency validation

## Usage

### Basic Processing

```python
from app.adapters import EnhancedTickerAdapter

adapter = EnhancedTickerAdapter()

# Process enhanced tick
tick_data = {
    "ik": "NSE:RELIANCE",
    "ltp": {
        "value": "2450.50",
        "currency": "INR"
    },
    "ts_exch": "2024-01-15T16:00:00+05:30",
    "tz": "Asia/Kolkata",
    # ... other fields
}

processed_tick = await adapter.process_tick(tick_data)
```

### Currency Conversion

```python
# Convert INR to USD
inr_amount = Decimal("83500")
usd_amount = await adapter.currency_handler.convert(
    inr_amount, "INR", "USD"
)

# Prepare data with currency conversion
indicator_data = await adapter.prepare_for_indicators(
    processed_tick, 
    target_currency="USD"
)
```

### Timezone Handling

```python
# Convert time between timezones
ist_time = datetime.now(pytz.timezone("Asia/Kolkata"))
nyc_time = adapter.timezone_handler.convert_time(
    ist_time, "Asia/Kolkata", "America/New_York"
)

# Get market hours
open_time, close_time = adapter.timezone_handler.get_market_hours(
    "NSE", datetime.now()
)
```

## Integration with Signal Components

### 1. Signal Processor
The signal processor uses the adapter to process incoming ticks before computation:

```python
# In signal_processor.py
processed_tick = await self.ticker_adapter.process_tick(tick_data)
is_valid, error_msg = await self.ticker_adapter.validate_tick_data(tick_data)
processed_tick = await self.ticker_adapter.enrich_with_metadata(processed_tick)
```

### 2. Technical Indicators (pandas_ta_executor)
The pandas TA executor extracts OHLCV data from enhanced format:

```python
# Handles nested price format
if isinstance(tick_data['ltp'], dict):
    price = float(tick_data['ltp'].get('value', 0))
    currency = tick_data['ltp'].get('currency', 'USD')
```

### 3. Greeks Calculator
Greeks calculators extract option prices and handle currency metadata:

```python
# Extract option price from enhanced format
if isinstance(ltp_data, dict):
    price = ltp_data.get('value')
    currency = ltp_data.get('currency', 'INR')
```

## Enhanced Tick Format

### Structure
```json
{
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
    "v": 1250000,
    "mode": "full"
}
```

### Fields
- `ik`: Instrument key
- `bs`: Broker source
- `ac`: Asset class
- `ts_utc`: UTC timestamp
- `ts_exch`: Exchange local timestamp
- `tz`: Exchange timezone
- Price fields (`ltp`, `open`, `high`, `low`, `close`, `bid`, `ask`): Nested objects with `value` and `currency`
- `v`: Volume
- `oi`: Open interest
- `mode`: Data completeness mode

## Error Handling

The adapter includes comprehensive error handling:

1. **Invalid Format**: Returns validation error with specific field issues
2. **Missing Data**: Handles missing optional fields gracefully
3. **Conversion Errors**: Falls back to default values with warnings
4. **Timezone Errors**: Validates timezone strings before processing

## Performance Considerations

1. **Caching**: Currency conversion rates are cached for 5 minutes
2. **Validation**: Lightweight validation for high-frequency processing
3. **Memory**: Efficient data structures for tick processing
4. **Async**: All I/O operations are asynchronous

## Testing

Run tests with:
```bash
pytest tests/test_enhanced_ticker_adapter.py -v
```

Tests cover:
- Enhanced tick format processing
- Legacy format compatibility
- Currency conversion
- Timezone handling
- Market hours detection
- Data validation
- Metadata enrichment