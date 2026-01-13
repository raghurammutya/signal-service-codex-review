# Signal Service Programming Constructs for Execution Engine

## Overview

The Signal Service provides a rich set of programming constructs that the Execution Engine can leverage for building sophisticated trading strategies. This document provides real-time examples of all supported constructs.

## 1. Greeks Calculations

### Basic Greeks
```python
# Real-time Delta calculation for NIFTY option
delta = await signal_service.get_realtime_greeks(
    instrument_key="NSE@NIFTY@equity_options@2024-01-25@call@21500"
)
# Returns: {"delta": 0.65, "gamma": 0.0012, "theta": -45.5, "vega": 125.3, "rho": 85.2}

# Batch Greeks for option chain
greeks_chain = await signal_service.compute_batch_greeks([
    "NSE@NIFTY@equity_options@2024-01-25@call@21000",
    "NSE@NIFTY@equity_options@2024-01-25@call@21100",
    "NSE@NIFTY@equity_options@2024-01-25@call@21200",
    "NSE@NIFTY@equity_options@2024-01-25@call@21300",
    "NSE@NIFTY@equity_options@2024-01-25@call@21400"
])
```

### Moneyness-Based Greeks
```python
# ATM Greeks aggregation
atm_greeks = await signal_service.get_moneyness_greeks(
    underlying="NIFTY",
    moneyness_level="ATM",
    expiry_date="2024-01-25"
)
# Returns aggregated Greeks for all ATM options

# OTM 5-delta puts for hedging
otm_puts = await signal_service.get_otm_delta_greeks(
    underlying="NIFTY",
    delta=0.05,
    option_type="put"
)

# Portfolio Greeks by moneyness distribution
distribution = await signal_service.get_moneyness_distribution(
    underlying="BANKNIFTY",
    moneyness_levels=["DITM", "ITM", "ATM", "OTM", "DOTM"]
)
```

## 2. Technical Indicators

### Standard Indicators
```python
# Real-time RSI
rsi = await signal_service.get_realtime_indicator(
    instrument_key="NSE@RELIANCE@equity_spot",
    indicator="rsi",
    period=14
)

# MACD with custom parameters
macd = await signal_service.get_realtime_indicator(
    instrument_key="NSE@TCS@equity_spot",
    indicator="macd",
    params={"fast": 12, "slow": 26, "signal": 9}
)

# Bollinger Bands
bb = await signal_service.get_realtime_indicator(
    instrument_key="NSE@INFY@equity_spot",
    indicator="bollinger_bands",
    params={"period": 20, "std_dev": 2}
)
```

### Complex Indicators
```python
# Supertrend for trend following
supertrend = await signal_service.get_realtime_indicator(
    instrument_key="NSE@HDFC@equity_spot",
    indicator="supertrend",
    params={"period": 7, "multiplier": 3}
)

# Ichimoku Cloud
ichimoku = await signal_service.get_realtime_indicator(
    instrument_key="NSE@ICICIBANK@equity_spot",
    indicator="ichimoku",
    params={"conversion": 9, "base": 26, "span": 52}
)

# Volume Weighted Average Price (VWAP)
vwap = await signal_service.get_realtime_indicator(
    instrument_key="NSE@SBIN@equity_spot",
    indicator="vwap",
    params={"anchor": "session"}
)
```

### Custom Indicators via External Functions
```python
# Custom momentum indicator
custom_momentum = await signal_service.compute_custom_function(
    instrument_key="NSE@WIPRO@equity_spot",
    function_code="""
    def custom_momentum(prices, volume, period=20):
        # Price momentum
        price_roc = (prices[-1] / prices[-period] - 1) * 100
        
        # Volume momentum
        vol_sma = np.mean(volume[-period:])
        vol_ratio = volume[-1] / vol_sma
        
        # Combined momentum score
        momentum_score = price_roc * vol_ratio
        
        return {
            'momentum_score': momentum_score,
            'price_roc': price_roc,
            'volume_ratio': vol_ratio,
            'signal': 'bullish' if momentum_score > 10 else 'bearish'
        }
    """,
    timeframe="5m"
)
```

## 3. Flexible Timeframe Support

### Standard Timeframes
```python
# 5-minute RSI
rsi_5m = await signal_service.get_historical_indicator(
    instrument_key="NSE@NIFTY@equity_spot",
    indicator="rsi",
    timeframe="5m",
    start_time=datetime.now() - timedelta(hours=1),
    end_time=datetime.now()
)

# Hourly MACD
macd_1h = await signal_service.get_historical_indicator(
    instrument_key="NSE@BANKNIFTY@equity_spot",
    indicator="macd",
    timeframe="1h",
    start_time=datetime.now() - timedelta(days=7),
    end_time=datetime.now()
)
```

### Custom Timeframes
```python
# 7-minute timeframe for unique strategy
custom_7m = await signal_service.get_historical_greeks(
    instrument_key="NSE@NIFTY@equity_options@2024-01-25@call@21500",
    timeframe="7m",  # Custom 7-minute bars
    start_time=datetime.now() - timedelta(hours=2),
    end_time=datetime.now()
)

# 13-minute Fibonacci timeframe
fib_13m = await signal_service.get_historical_indicator(
    instrument_key="NSE@TCS@equity_spot",
    indicator="ema",
    timeframe="13m",  # Custom 13-minute bars
    period=21
)
```

## 4. WebSocket Streaming Constructs

### Real-time Greeks Streaming
```python
# WebSocket subscription for Greeks updates
ws_client = SignalWebSocketClient()

# Subscribe to option Greeks
await ws_client.subscribe({
    "type": "subscribe",
    "channel": "greeks",
    "instrument_key": "NSE@NIFTY@equity_options@2024-01-25@call@21500"
})

# Callback for real-time updates
async def on_greeks_update(data):
    delta = data['greeks']['delta']
    if delta > 0.7:
        # High delta - option behaving like stock
        await execution_engine.adjust_hedge()
```

### Moneyness-based Streaming
```python
# Stream ATM IV for NIFTY
await ws_client.subscribe({
    "type": "subscribe",
    "channel": "moneyness",
    "instrument_key": "moneyness_greeks",
    "params": {
        "underlying": "NIFTY",
        "moneyness_level": "ATM"
    }
})

# Real-time IV skew monitoring
async def on_iv_update(data):
    atm_iv = data['aggregated_greeks']['all']['iv']
    if atm_iv > 0.25:  # IV spike
        await execution_engine.execute_volatility_strategy()
```

## 5. Batch Processing Constructs

### Option Chain Analysis
```python
# Analyze entire option chain
strikes = range(21000, 22000, 100)
option_keys = []

for strike in strikes:
    option_keys.append(f"NSE@NIFTY@equity_options@2024-01-25@call@{strike}")
    option_keys.append(f"NSE@NIFTY@equity_options@2024-01-25@put@{strike}")

# Batch compute Greeks for entire chain
chain_greeks = await signal_service.compute_batch_greeks(option_keys)

# Find max gamma strike (pin risk)
max_gamma_strike = max(chain_greeks.items(), 
                      key=lambda x: x[1].get('gamma', 0))
```

### Multi-Indicator Screening
```python
# Screen 50 stocks with multiple indicators
stocks = ["RELIANCE", "TCS", "INFY", "HDFC", "ICICIBANK", ...]  # 50 stocks

indicators_config = [
    {"name": "rsi", "params": {"period": 14}},
    {"name": "macd", "params": {"fast": 12, "slow": 26}},
    {"name": "adx", "params": {"period": 14}},
    {"name": "atr", "params": {"period": 14}}
]

# Batch compute all indicators
screening_results = await signal_service.compute_batch_indicators(
    instrument_keys=[f"NSE@{stock}@equity_spot" for stock in stocks],
    indicators=indicators_config,
    timeframe="15m"
)

# Filter stocks meeting criteria
qualified_stocks = []
for stock, indicators in screening_results.items():
    if (indicators['rsi']['value'] < 30 and 
        indicators['adx']['value'] > 25 and
        indicators['macd']['histogram'] > 0):
        qualified_stocks.append(stock)
```

## 6. Historical Analysis Constructs

### Backtesting Support
```python
# Get historical Greeks for backtesting
historical_greeks = await signal_service.get_historical_greeks(
    instrument_key="NSE@NIFTY@equity_options@2024-01-25@call@21500",
    start_time=datetime(2024, 1, 1),
    end_time=datetime(2024, 1, 15),
    timeframe="5m"
)

# Analyze Greeks behavior
for point in historical_greeks['time_series']:
    timestamp = point['timestamp']
    greeks = point['value']
    
    # Backtest delta hedging strategy
    if greeks['delta'] > 0.6:
        # Simulate hedge adjustment
        hedge_shares = -greeks['delta'] * 100  # Per contract
```

### Pattern Recognition
```python
# Historical data for pattern analysis
price_data = await signal_service.get_historical_indicator(
    instrument_key="NSE@BANKNIFTY@equity_spot",
    indicator="ohlcv",
    timeframe="15m",
    start_time=datetime.now() - timedelta(days=30),
    end_time=datetime.now()
)

# Identify chart patterns
patterns = await signal_service.compute_custom_function(
    instrument_key="NSE@BANKNIFTY@equity_spot",
    function_code="""
    def identify_patterns(ohlcv_data):
        patterns_found = []
        
        # Head and Shoulders
        if detect_head_shoulders(ohlcv_data):
            patterns_found.append({
                'pattern': 'head_and_shoulders',
                'confidence': 0.85,
                'target': calculate_target_price()
            })
        
        # Double Bottom
        if detect_double_bottom(ohlcv_data):
            patterns_found.append({
                'pattern': 'double_bottom',
                'confidence': 0.75,
                'target': calculate_target_price()
            })
        
        return patterns_found
    """,
    data=price_data
)
```

## 7. Complex Strategy Constructs

### Iron Condor with Dynamic Adjustments
```python
# Batman Strategy implementation
async def setup_iron_condor():
    # Get current market data
    spot_price = await signal_service.get_realtime_price("NSE@NIFTY@equity_spot")
    
    # Find strikes by moneyness
    otm_call = await signal_service.get_strikes_by_moneyness(
        underlying="NIFTY",
        moneyness_level="OTM10delta",
        option_type="call"
    )
    
    otm_put = await signal_service.get_strikes_by_moneyness(
        underlying="NIFTY",
        moneyness_level="OTM10delta",
        option_type="put"
    )
    
    # Get Greeks for all legs
    iron_condor_legs = await signal_service.compute_batch_greeks([
        otm_call['sell_strike'],
        otm_call['buy_strike'],
        otm_put['sell_strike'],
        otm_put['buy_strike']
    ])
    
    # Calculate net Greeks
    net_delta = sum(leg['delta'] * leg['position'] for leg in iron_condor_legs)
    net_gamma = sum(leg['gamma'] * leg['position'] for leg in iron_condor_legs)
    net_theta = sum(leg['theta'] * leg['position'] for leg in iron_condor_legs)
    
    return {
        'structure': iron_condor_legs,
        'net_greeks': {
            'delta': net_delta,
            'gamma': net_gamma,
            'theta': net_theta
        },
        'max_profit': calculate_max_profit(),
        'max_loss': calculate_max_loss()
    }
```

### Volatility Arbitrage
```python
# IV Rank calculation
async def calculate_iv_rank(underlying="NIFTY", lookback_days=252):
    # Get historical ATM IV
    historical_iv = await signal_service.get_historical_moneyness(
        underlying=underlying,
        moneyness_level="ATM",
        start_time=datetime.now() - timedelta(days=lookback_days),
        end_time=datetime.now(),
        timeframe="1d"
    )
    
    # Current IV
    current_iv = await signal_service.get_atm_iv(
        underlying=underlying,
        expiry_date=get_current_expiry()
    )
    
    # Calculate IV rank
    iv_values = [point['value']['iv'] for point in historical_iv['time_series']]
    iv_rank = percentileofscore(iv_values, current_iv['iv'])
    
    # Generate signals
    if iv_rank > 80:
        return {"signal": "sell_volatility", "iv_rank": iv_rank}
    elif iv_rank < 20:
        return {"signal": "buy_volatility", "iv_rank": iv_rank}
    else:
        return {"signal": "neutral", "iv_rank": iv_rank}
```

### Market Regime Detection
```python
# Multi-timeframe regime analysis
async def detect_market_regime():
    regimes = {}
    
    # Short-term regime (5m)
    st_indicators = await signal_service.compute_batch_indicators(
        ["NSE@NIFTY@equity_spot"],
        indicators=[
            {"name": "ema", "params": {"period": 9}},
            {"name": "ema", "params": {"period": 21}},
            {"name": "adx", "params": {"period": 14}},
            {"name": "atr", "params": {"period": 14}}
        ],
        timeframe="5m"
    )
    
    # Medium-term regime (1h)
    mt_indicators = await signal_service.compute_batch_indicators(
        ["NSE@NIFTY@equity_spot"],
        indicators=[
            {"name": "sma", "params": {"period": 50}},
            {"name": "sma", "params": {"period": 200}},
            {"name": "rsi", "params": {"period": 14}}
        ],
        timeframe="1h"
    )
    
    # Classify regimes
    if st_indicators['ema_9'] > st_indicators['ema_21']:
        regimes['short_term'] = 'bullish'
    else:
        regimes['short_term'] = 'bearish'
        
    if st_indicators['adx'] > 25:
        regimes['trend_strength'] = 'strong'
    else:
        regimes['trend_strength'] = 'weak'
        
    if st_indicators['atr'] > historical_avg_atr * 1.5:
        regimes['volatility'] = 'high'
    else:
        regimes['volatility'] = 'normal'
    
    return regimes
```

## 8. Risk Management Constructs

### Portfolio Greeks Aggregation
```python
# Calculate portfolio-wide Greeks
async def calculate_portfolio_greeks(positions):
    # Get all instrument keys
    instrument_keys = [pos['instrument_key'] for pos in positions]
    
    # Batch compute Greeks
    all_greeks = await signal_service.compute_batch_greeks(instrument_keys)
    
    # Aggregate by position size
    portfolio_greeks = {
        'delta': 0,
        'gamma': 0,
        'theta': 0,
        'vega': 0,
        'rho': 0
    }
    
    for pos in positions:
        greeks = all_greeks[pos['instrument_key']]
        quantity = pos['quantity']
        
        portfolio_greeks['delta'] += greeks['delta'] * quantity
        portfolio_greeks['gamma'] += greeks['gamma'] * quantity
        portfolio_greeks['theta'] += greeks['theta'] * quantity
        portfolio_greeks['vega'] += greeks['vega'] * quantity
        portfolio_greeks['rho'] += greeks['rho'] * quantity
    
    # Calculate risk metrics
    return {
        'portfolio_greeks': portfolio_greeks,
        'delta_dollars': portfolio_greeks['delta'] * spot_price,
        'gamma_risk': portfolio_greeks['gamma'] * spot_price * 0.01,  # 1% move
        'daily_theta': portfolio_greeks['theta'],
        'vega_risk': portfolio_greeks['vega'] * 0.01  # 1 vol point
    }
```

### Dynamic Hedging
```python
# Real-time delta hedging
async def dynamic_delta_hedge():
    while True:
        # Get current portfolio Greeks
        portfolio = await calculate_portfolio_greeks(current_positions)
        
        # Check if rehedge needed
        if abs(portfolio['portfolio_greeks']['delta']) > DELTA_THRESHOLD:
            # Calculate hedge requirement
            hedge_qty = -portfolio['portfolio_greeks']['delta']
            
            # Execute hedge
            if hedge_qty > 0:
                await execution_engine.buy_hedge("NSE@NIFTY@equity_spot", hedge_qty)
            else:
                await execution_engine.sell_hedge("NSE@NIFTY@equity_spot", abs(hedge_qty))
        
        # Check gamma risk
        if abs(portfolio['portfolio_greeks']['gamma']) > GAMMA_THRESHOLD:
            # Add gamma hedge using options
            await add_gamma_hedge()
        
        # Wait for next check
        await asyncio.sleep(60)  # Check every minute
```

## 9. Advanced Computation Constructs

### Implied Volatility Surface
```python
# Build IV surface for options
async def build_iv_surface(underlying="NIFTY"):
    expiries = get_available_expiries(underlying)
    strikes = range(20000, 22000, 100)
    
    iv_surface = {}
    
    for expiry in expiries:
        iv_surface[expiry] = {}
        
        # Get IVs for all strikes
        for strike in strikes:
            call_iv = await signal_service.get_implied_volatility(
                f"NSE@{underlying}@equity_options@{expiry}@call@{strike}"
            )
            put_iv = await signal_service.get_implied_volatility(
                f"NSE@{underlying}@equity_options@{expiry}@put@{strike}"
            )
            
            iv_surface[expiry][strike] = {
                'call_iv': call_iv,
                'put_iv': put_iv,
                'avg_iv': (call_iv + put_iv) / 2
            }
    
    return iv_surface
```

### Correlation Analysis
```python
# Multi-asset correlation
async def calculate_correlations(assets, timeframe="1h", lookback_days=30):
    # Get historical data for all assets
    historical_data = {}
    
    for asset in assets:
        data = await signal_service.get_historical_indicator(
            instrument_key=f"NSE@{asset}@equity_spot",
            indicator="close",
            timeframe=timeframe,
            start_time=datetime.now() - timedelta(days=lookback_days),
            end_time=datetime.now()
        )
        historical_data[asset] = data
    
    # Calculate correlation matrix
    correlation_matrix = await signal_service.compute_custom_function(
        function_code="""
        def calculate_correlation_matrix(data):
            import pandas as pd
            import numpy as np
            
            # Create DataFrame
            df = pd.DataFrame(data)
            
            # Calculate correlations
            corr_matrix = df.corr()
            
            # Find highly correlated pairs
            high_corr_pairs = []
            for i in range(len(corr_matrix.columns)):
                for j in range(i+1, len(corr_matrix.columns)):
                    if abs(corr_matrix.iloc[i, j]) > 0.7:
                        high_corr_pairs.append({
                            'pair': (corr_matrix.columns[i], corr_matrix.columns[j]),
                            'correlation': corr_matrix.iloc[i, j]
                        })
            
            return {
                'correlation_matrix': corr_matrix.to_dict(),
                'high_correlation_pairs': high_corr_pairs
            }
        """,
        data=historical_data
    )
    
    return correlation_matrix
```

## 10. Event-Driven Constructs

### Earnings Event Trading
```python
# Monitor for earnings-related volatility
async def earnings_volatility_trade(symbol="INFY"):
    # Get current and historical IV
    current_iv = await signal_service.get_atm_iv(
        underlying=symbol,
        expiry_date=get_earnings_expiry()
    )
    
    historical_iv = await signal_service.get_historical_moneyness(
        underlying=symbol,
        moneyness_level="ATM",
        start_time=datetime.now() - timedelta(days=30),
        end_time=datetime.now(),
        timeframe="1d"
    )
    
    # Check for IV expansion
    avg_iv = np.mean([p['value']['iv'] for p in historical_iv['time_series']])
    iv_expansion = current_iv['iv'] / avg_iv
    
    if iv_expansion > 1.3:  # 30% IV expansion
        # Sell volatility before earnings
        straddle = await setup_short_straddle(symbol)
        return {
            'strategy': 'short_volatility',
            'iv_expansion': iv_expansion,
            'position': straddle
        }
```

### Expiry Day Strategies
```python
# 0DTE (Zero Days to Expiry) trading
async def zerod_te_strategy():
    # Get today's expiring options
    today = datetime.now().date()
    expiry_options = await signal_service.get_expiring_options(date=today)
    
    # Monitor gamma for pinning
    gamma_distribution = await signal_service.compute_batch_greeks(
        [opt['instrument_key'] for opt in expiry_options]
    )
    
    # Find max gamma strike (potential pin)
    max_gamma = max(gamma_distribution.items(), 
                   key=lambda x: x[1]['gamma'])
    pin_strike = extract_strike(max_gamma[0])
    
    # Trade around the pin
    if spot_price > pin_strike * 1.005:  # Above pin
        # Sell call spreads
        return await setup_call_spread(pin_strike, pin_strike + 100)
    elif spot_price < pin_strike * 0.995:  # Below pin
        # Sell put spreads
        return await setup_put_spread(pin_strike - 100, pin_strike)
```

## Summary

The Signal Service provides a comprehensive set of programming constructs that enable the Execution Engine to implement sophisticated trading strategies:

1. **Real-time Data Access**: Greeks, indicators, prices
2. **Historical Analysis**: Backtesting, pattern recognition
3. **Batch Processing**: High-performance bulk computations
4. **Streaming Updates**: WebSocket for low-latency data
5. **Flexible Timeframes**: Standard and custom intervals
6. **Moneyness Analytics**: ATM, OTM, ITM analysis
7. **Risk Management**: Portfolio Greeks, dynamic hedging
8. **Custom Computations**: External functions for proprietary logic
9. **Event-Driven**: Earnings, expiry, market events
10. **Multi-Asset**: Correlations, spreads, pairs

These constructs can be combined to create complex trading systems ranging from simple technical indicators to sophisticated options strategies like the Batman Iron Condor strategy.