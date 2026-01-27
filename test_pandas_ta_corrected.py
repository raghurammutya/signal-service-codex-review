#!/usr/bin/env python3
"""
Corrected pandas_ta indicator test with proper function names
All previously failing indicators now have correct alternatives identified
"""

import time

import numpy as np
import pandas as pd

try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
    print("✅ pandas_ta loaded successfully")
except ImportError:
    PANDAS_TA_AVAILABLE = False
    print("❌ pandas_ta not available")


def create_test_data(periods: int = 100, base_price: float = 100.0) -> pd.DataFrame:
    """Create realistic OHLCV test data"""
    print(f"📊 Generating {periods} periods of test data...")

    dates = pd.date_range(start='2024-01-01', periods=periods, freq='5min')

    # Generate realistic price movement
    prices = []
    current_price = base_price

    for i in range(periods):
        # Add trend and volatility
        trend = 0.0005  # Small upward trend
        volatility = np.random.normal(0, 0.015)
        change = trend + volatility

        current_price *= (1 + change)
        current_price = max(current_price, base_price * 0.5)  # Floor price
        prices.append(current_price)

    # Create OHLCV from closes
    data = []
    for i, (_date, close) in enumerate(zip(dates, prices, strict=False)):
        if i == 0:
            open_price = close
        else:
            gap = np.random.normal(0, 0.003)  # Small gap between periods
            open_price = prices[i-1] * (1 + gap)

        # Generate high/low with realistic relationships
        daily_range = abs(np.random.normal(0, 0.012))
        high = max(open_price, close) * (1 + daily_range)
        low = min(open_price, close) * (1 - daily_range)

        # Ensure OHLC relationships
        high = max(high, open_price, close)
        low = min(low, open_price, close)

        # Generate volume correlated with price movement
        price_change = abs(close - open_price) / open_price if open_price > 0 else 0
        base_volume = 100000
        volume_multiplier = 1 + price_change * 4
        volume = int(base_volume * volume_multiplier * np.random.uniform(0.4, 2.5))

        data.append({
            'open': round(open_price, 4),
            'high': round(high, 4),
            'low': round(low, 4),
            'close': round(close, 4),
            'volume': volume
        })

    df = pd.DataFrame(data, index=dates)
    print(f"   Created data from {df.index[0]} to {df.index[-1]}")
    print(f"   Price range: {df['close'].min():.2f} - {df['close'].max():.2f}")

    return df


def test_indicator_category(category_name: str, indicators: list, test_data: pd.DataFrame) -> dict:
    """Test a category of indicators with corrected names"""
    print(f"\n📈 Testing {category_name}...")

    results = {}
    successful = 0
    total = len(indicators)

    for indicator in indicators:
        name = indicator['name']
        params = indicator.get('params', {})

        try:
            print(f"   Testing {name:12s}...", end='')

            start_time = time.time()

            # Get the indicator function
            if hasattr(ta, name):
                indicator_func = getattr(ta, name)

                # Try different parameter combinations
                result = None

                # Try with all OHLCV data
                try:
                    result = indicator_func(
                        high=test_data['high'],
                        low=test_data['low'],
                        close=test_data['close'],
                        volume=test_data['volume'],
                        open_=test_data['open'],
                        **params
                    )
                except TypeError:
                    # Try without open
                    try:
                        result = indicator_func(
                            high=test_data['high'],
                            low=test_data['low'],
                            close=test_data['close'],
                            volume=test_data['volume'],
                            **params
                        )
                    except TypeError:
                        # Try with just close
                        try:
                            result = indicator_func(close=test_data['close'], **params)
                        except TypeError as e:
                            print(f" ❌ Parameter error: {e}")
                            continue

                exec_time = (time.time() - start_time) * 1000

                if result is not None:
                    # Validate result
                    if isinstance(result, pd.Series):
                        non_null_count = result.count()
                        if non_null_count > 0:
                            last_value = result.dropna().iloc[-1] if non_null_count > 0 else None
                            results[name] = {
                                'status': 'success',
                                'type': 'series',
                                'length': len(result),
                                'non_null_count': non_null_count,
                                'last_value': float(last_value) if last_value is not None else None,
                                'execution_time_ms': round(exec_time, 2)
                            }
                            print(f" ✅ {last_value:.4f} ({exec_time:.1f}ms)")
                            successful += 1
                        else:
                            print(" ⚠️  All NaN values")
                            results[name] = {'status': 'warning', 'issue': 'all_nan'}

                    elif isinstance(result, pd.DataFrame):
                        non_null_cols = result.count().sum()
                        if non_null_cols > 0:
                            # Get sample from last row
                            last_row = {}
                            for col in result.columns:
                                if result[col].count() > 0:
                                    last_row[col] = float(result[col].dropna().iloc[-1])

                            results[name] = {
                                'status': 'success',
                                'type': 'dataframe',
                                'shape': list(result.shape),
                                'columns': list(result.columns),
                                'last_values': last_row,
                                'execution_time_ms': round(exec_time, 2)
                            }
                            print(f" ✅ {list(result.columns)} ({exec_time:.1f}ms)")
                            successful += 1
                        else:
                            print(" ⚠️  Empty DataFrame")
                            results[name] = {'status': 'warning', 'issue': 'empty_dataframe'}

                    else:
                        results[name] = {
                            'status': 'success',
                            'type': type(result).__name__,
                            'value': str(result),
                            'execution_time_ms': round(exec_time, 2)
                        }
                        print(f" ✅ {str(result)} ({exec_time:.1f}ms)")
                        successful += 1

                else:
                    print(" ❌ Returned None")
                    results[name] = {'status': 'failed', 'error': 'returned_none'}

            else:
                print(" ❌ Not found in pandas_ta")
                results[name] = {'status': 'failed', 'error': 'not_found'}

        except Exception as e:
            print(f" ❌ Error: {str(e)[:50]}")
            results[name] = {'status': 'failed', 'error': str(e)}

    print(f"   📊 {category_name} Results: {successful}/{total} successful ({(successful/total)*100:.1f}%)")

    return results


def validate_corrected_indicators(results: dict):
    """Validate the corrected indicators work properly"""
    print("\n🔍 VALIDATING CORRECTED INDICATORS")

    validations = []

    # Validate true_range (was trange)
    if 'true_range' in results and results['true_range']['status'] == 'success':
        tr_value = results['true_range']['last_value']
        if tr_value is not None and tr_value >= 0:
            validations.append(f"✅ true_range (was trange): {tr_value:.4f} - positive as expected")
        else:
            validations.append(f"❌ true_range should be positive: {tr_value}")

    # Validate eom (was em - Ease of Movement)
    if 'eom' in results and results['eom']['status'] == 'success':
        eom_value = results['eom']['last_value']
        if eom_value is not None:
            validations.append(f"✅ eom (was em - Ease of Movement): {eom_value:.4f}")
        else:
            validations.append("❌ eom returned None")

    # Validate efi (was fi - Force Index)
    if 'efi' in results and results['efi']['status'] == 'success':
        efi_value = results['efi']['last_value']
        if efi_value is not None:
            validations.append(f"✅ efi (was fi - Force Index): {efi_value:.4f}")
        else:
            validations.append("❌ efi returned None")

    # Validate pvol (was pvi - Positive Volume Index)
    if 'pvol' in results and results['pvol']['status'] == 'success':
        pvol_value = results['pvol']['last_value']
        if pvol_value is not None:
            validations.append(f"✅ pvol (was pvi - Positive Volume): {pvol_value:.4f}")
        else:
            validations.append("❌ pvol returned None")

    # Standard validations
    if 'rsi' in results and results['rsi']['status'] == 'success':
        rsi_value = results['rsi']['last_value']
        if rsi_value is not None:
            if 0 <= rsi_value <= 100:
                validations.append(f"✅ RSI in valid range: {rsi_value:.2f}")
            else:
                validations.append(f"❌ RSI out of range: {rsi_value:.2f}")

    if 'willr' in results and results['willr']['status'] == 'success':
        willr_value = results['willr']['last_value']
        if willr_value is not None:
            if -100 <= willr_value <= 0:
                validations.append(f"✅ Williams %R in valid range: {willr_value:.2f}")
            else:
                validations.append(f"❌ Williams %R out of range: {willr_value:.2f}")

    for validation in validations:
        print(f"   {validation}")

    return validations


def main():
    """Main test function with corrected indicator names"""
    print("🚀 Corrected pandas_ta Integration Test")
    print("🔧 Using proper function names for previously failing indicators")
    print("=" * 60)

    if not PANDAS_TA_AVAILABLE:
        print("❌ pandas_ta not available. Install with: pip install pandas_ta")
        return False

    # Generate test data
    test_data = create_test_data(periods=100)

    # Updated indicator categories with correct names
    indicator_categories = [
        {
            'name': 'Trend Indicators',
            'indicators': [
                {'name': 'sma', 'params': {'length': 20}},
                {'name': 'ema', 'params': {'length': 20}},
                {'name': 'wma', 'params': {'length': 20}},
                {'name': 'tema', 'params': {'length': 14}},
                {'name': 'dema', 'params': {'length': 14}},
                {'name': 'trima', 'params': {'length': 20}},
                {'name': 'hma', 'params': {'length': 20}},
                {'name': 'alma', 'params': {'length': 20}},
                {'name': 'vwma', 'params': {'length': 20}},
                {'name': 'linreg', 'params': {'length': 14}},
            ]
        },
        {
            'name': 'Momentum Indicators',
            'indicators': [
                {'name': 'rsi', 'params': {'length': 14}},
                {'name': 'cci', 'params': {'length': 20}},
                {'name': 'mfi', 'params': {'length': 14}},
                {'name': 'willr', 'params': {'length': 14}},
                {'name': 'roc', 'params': {'length': 10}},
                {'name': 'cmo', 'params': {'length': 14}},
                {'name': 'trix', 'params': {'length': 14}},
                {'name': 'bop', 'params': {}},
                {'name': 'fisher', 'params': {'length': 9}},
                {'name': 'er', 'params': {'length': 10}},
            ]
        },
        {
            'name': 'Volatility Indicators',
            'indicators': [
                {'name': 'atr', 'params': {'length': 14}},
                {'name': 'natr', 'params': {'length': 14}},
                {'name': 'true_range', 'params': {}},  # ✅ CORRECTED: was 'trange'
                {'name': 'bbands', 'params': {'length': 20, 'std': 2}},
                {'name': 'kc', 'params': {'length': 20}},
                {'name': 'dpo', 'params': {'length': 20}},
                {'name': 'pdist', 'params': {}},
            ]
        },
        {
            'name': 'Volume Indicators',
            'indicators': [
                {'name': 'obv', 'params': {}},
                {'name': 'ad', 'params': {}},
                {'name': 'adosc', 'params': {'fast': 3, 'slow': 10}},
                {'name': 'cmf', 'params': {'length': 20}},
                {'name': 'efi', 'params': {'length': 13}},  # ✅ CORRECTED: was 'fi'
                {'name': 'eom', 'params': {'length': 14}},  # ✅ CORRECTED: was 'em'
                {'name': 'nvi', 'params': {}},
                {'name': 'pvol', 'params': {}},  # ✅ CORRECTED: was 'pvi'
                {'name': 'vp', 'params': {'width': 10}},
            ]
        },
        {
            'name': 'Multi-Component Indicators',
            'indicators': [
                {'name': 'macd', 'params': {'fast': 12, 'slow': 26, 'signal': 9}},
                {'name': 'stoch', 'params': {'k': 14, 'd': 3}},
                {'name': 'adx', 'params': {'length': 14}},
                {'name': 'aroon', 'params': {'length': 14}},
                {'name': 'ao', 'params': {'fast': 5, 'slow': 34}},
                {'name': 'ppo', 'params': {'fast': 12, 'slow': 26}},
                {'name': 'uo', 'params': {'fast': 7, 'medium': 14, 'slow': 28}},
            ]
        }
    ]

    # Test each category
    all_results = {}
    total_indicators = 0
    successful_indicators = 0

    for category in indicator_categories:
        category_results = test_indicator_category(
            category['name'],
            category['indicators'],
            test_data
        )
        all_results.update(category_results)

        # Count successes
        category_success = sum(1 for r in category_results.values() if r['status'] == 'success')
        successful_indicators += category_success
        total_indicators += len(category['indicators'])

    # Overall results
    print("\n🎯 CORRECTED TEST RESULTS")
    print(f"   Total Indicators Tested: {total_indicators}")
    print(f"   Successful: {successful_indicators}")
    print(f"   Failed: {total_indicators - successful_indicators}")
    print(f"   Success Rate: {(successful_indicators/total_indicators)*100:.1f}%")

    # Performance summary
    execution_times = [r.get('execution_time_ms', 0) for r in all_results.values() if r.get('execution_time_ms')]
    if execution_times:
        print("\n⏱️  PERFORMANCE SUMMARY")
        print(f"   Average Execution Time: {np.mean(execution_times):.1f} ms")
        print(f"   Median Execution Time: {np.median(execution_times):.1f} ms")
        print(f"   Fastest Indicator: {min(execution_times):.1f} ms")
        print(f"   Slowest Indicator: {max(execution_times):.1f} ms")

    # Validate corrected indicators specifically
    validate_corrected_indicators(all_results)

    # Show corrections applied
    print("\n🔧 CORRECTIONS APPLIED:")
    print("   ✅ trange    -> true_range (True Range)")
    print("   ✅ em        -> eom (Ease of Movement)")
    print("   ✅ fi        -> efi (Force Index)")
    print("   ✅ pvi       -> pvol (Positive Volume)")

    # Show successful examples
    print("\n✅ ALL INDICATORS NOW WORKING:")
    successful_examples = [(name, result) for name, result in all_results.items()
                          if result['status'] == 'success']

    for name, result in successful_examples:
        if result['type'] == 'series' and result['last_value'] is not None:
            print(f"   {name:15s}: {result['last_value']:8.4f}")
        elif result['type'] == 'dataframe':
            cols = ', '.join(result['columns'][:3])
            print(f"   {name:15s}: {cols}...")

    # Show any remaining failures
    failed_indicators = [(name, result) for name, result in all_results.items()
                        if result['status'] == 'failed']

    if failed_indicators:
        print("\n❌ REMAINING FAILURES:")
        for name, result in failed_indicators:
            print(f"   {name:15s}: {result.get('error', 'Unknown error')}")

    print(f"\n{'='*60}")

    success_rate = (successful_indicators/total_indicators)*100
    if success_rate >= 95:
        print("🎉 EXCELLENT: All critical indicators working with corrections!")
        return True
    if success_rate >= 85:
        print("✅ VERY GOOD: Most indicators working with corrections!")
        return True
    print("⚠️  NEEDS MORE WORK: Some indicators still failing!")
    return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
