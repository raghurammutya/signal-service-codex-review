#!/usr/bin/env python3
"""
Systematic investigation of missing pandas_ta indicators
Check if functions exist, find alternative names, and clean up test database
"""


import numpy as np
import pandas as pd

try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
    print("✅ pandas_ta loaded successfully")
except ImportError:
    PANDAS_TA_AVAILABLE = False
    print("❌ pandas_ta not available")
    exit(1)


def get_all_pandas_ta_functions():
    """Get comprehensive list of all available pandas_ta functions"""
    all_attrs = dir(ta)
    functions = []

    for attr in all_attrs:
        if not attr.startswith('_'):
            try:
                obj = getattr(ta, attr)
                if callable(obj) and hasattr(obj, '__doc__'):
                    functions.append(attr)
            except Exception:
                pass

    return sorted(functions)


def search_for_indicator(search_terms, all_functions):
    """Search for indicators by various terms"""
    matches = []

    for term in search_terms:
        term_lower = term.lower()
        for func in all_functions:
            func_lower = func.lower()
            if (term_lower in func_lower or
                func_lower in term_lower or
                # Check for abbreviation matches
                any(t in func_lower for t in term_lower.split('_'))):
                if func not in matches:
                    matches.append(func)

    return matches


def test_indicator_function(func_name, test_data):
    """Test if an indicator function works with our test data"""
    if not hasattr(ta, func_name):
        return False, "Function not found"

    try:
        indicator_func = getattr(ta, func_name)

        # Try different parameter combinations
        parameter_sets = [
            {},  # No parameters
            {'length': 14}, {'length': 20},  # Common lengths
            {'period': 14}, {'period': 20},  # Alternative parameter names
            {'window': 14}, {'window': 20},  # Window parameters
        ]

        for params in parameter_sets:
            try:
                # Try with all OHLCV data
                result = indicator_func(
                    high=test_data['high'],
                    low=test_data['low'],
                    close=test_data['close'],
                    volume=test_data['volume'],
                    open_=test_data['open'],
                    **params
                )
                if result is not None:
                    return True, f"Works with params: {params}"
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
                    if result is not None:
                        return True, f"Works with params (no open): {params}"
                except TypeError:
                    # Try with just close
                    try:
                        result = indicator_func(close=test_data['close'], **params)
                        if result is not None:
                            return True, f"Works with params (close only): {params}"
                    except TypeError:
                        continue
            except Exception:
                continue

        return False, "No valid parameter combination found"

    except Exception as e:
        return False, f"Error: {str(e)}"


def generate_test_data():
    """Generate test OHLCV data"""
    periods = 50
    dates = pd.date_range(start='2024-01-01', periods=periods, freq='5min')

    # Simple trending data
    closes = [100 + i * 0.5 + np.random.normal(0, 1) for i in range(periods)]

    data = []
    for _i, (date, close) in enumerate(zip(dates, closes, strict=False)):
        open_price = close + np.random.uniform(-0.5, 0.5)
        high = max(open_price, close) + np.random.uniform(0, 1)
        low = min(open_price, close) - np.random.uniform(0, 1)
        volume = np.random.randint(10000, 50000)

        data.append({
            'timestamp': date,
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume
        })

    df = pd.DataFrame(data)
    df.set_index('timestamp', inplace=True)
    return df


def investigate_missing_indicators():
    """Investigate the specific missing indicators"""

    print("\n🔍 INVESTIGATING MISSING INDICATORS")
    print("="*60)

    # Get all available functions
    all_functions = get_all_pandas_ta_functions()
    print(f"📊 Total pandas_ta functions available: {len(all_functions)}")

    # Generate test data
    test_data = generate_test_data()
    print(f"📈 Generated test data: {len(test_data)} periods")

    # Failing indicators from our tests
    missing_indicators = {
        'trange': ['true_range', 'tr', 'truerange', 'true range', 'range'],
        'em': ['ease_of_movement', 'eom', 'ease movement', 'easement'],
        'fi': ['force_index', 'force index', 'fi'],
        'pvi': ['positive_volume_index', 'pos_vol_index', 'positive volume']
    }

    results = {}

    for indicator, search_terms in missing_indicators.items():
        print(f"\n🔎 Investigating '{indicator}'...")

        # Search for potential matches
        matches = search_for_indicator(search_terms, all_functions)

        if matches:
            print(f"   🎯 Potential matches found: {matches}")

            # Test each match
            for match in matches:
                works, details = test_indicator_function(match, test_data)
                if works:
                    print(f"   ✅ {match}: {details}")
                    results[indicator] = {
                        'status': 'found_alternative',
                        'alternative_name': match,
                        'details': details
                    }
                    break
                print(f"   ❌ {match}: {details}")

            if indicator not in results:
                results[indicator] = {
                    'status': 'matches_found_but_not_working',
                    'matches': matches
                }
        else:
            print("   ❌ No matches found")
            results[indicator] = {
                'status': 'not_found',
                'searched_terms': search_terms
            }

    return results, all_functions


def check_all_volume_indicators():
    """Specifically check all volume-related indicators"""
    print("\n📊 CHECKING ALL VOLUME INDICATORS")
    print("="*50)

    all_functions = get_all_pandas_ta_functions()
    volume_indicators = [func for func in all_functions
                        if any(term in func.lower() for term in ['vol', 'obv', 'ad', 'mf', 'nvi', 'pvi'])]

    print(f"Found {len(volume_indicators)} volume-related indicators:")

    test_data = generate_test_data()

    for indicator in volume_indicators:
        works, details = test_indicator_function(indicator, test_data)
        status = "✅" if works else "❌"
        print(f"   {status} {indicator:20s}: {details}")


def check_volatility_indicators():
    """Check all volatility/range indicators"""
    print("\n📈 CHECKING ALL VOLATILITY/RANGE INDICATORS")
    print("="*50)

    all_functions = get_all_pandas_ta_functions()
    volatility_indicators = [func for func in all_functions
                           if any(term in func.lower() for term in ['atr', 'range', 'volatility', 'true', 'tr'])]

    print(f"Found {len(volatility_indicators)} volatility-related indicators:")

    test_data = generate_test_data()

    for indicator in volatility_indicators:
        works, details = test_indicator_function(indicator, test_data)
        status = "✅" if works else "❌"
        print(f"   {status} {indicator:20s}: {details}")


def generate_corrected_test_list():
    """Generate a corrected test list with only working indicators"""
    print("\n🛠️  GENERATING CORRECTED INDICATOR TEST LIST")
    print("="*50)

    all_functions = get_all_pandas_ta_functions()
    test_data = generate_test_data()

    # Filter out utility functions
    exclude_patterns = [
        'category', 'camelcase', 'deprecated', 'utils', 'version',
        'donchian', 'increasing', 'decreasing', 'cross', 'signals',
        'above', 'below', 'long_run', 'short_run', 'hl2', 'hlc3',
        'ohlc4', 'typical_price', 'weighted_close', 'cov', 'corr',
        'log', 'cumulative', 'percent_return', 'df_', 'create_dir',
        'combination', 'consecutive_streak', 'candle_color'
    ]

    working_indicators = []
    categories = {
        'trend': [],
        'momentum': [],
        'volatility': [],
        'volume': [],
        'overlap': [],
        'multi_component': []
    }

    for func_name in all_functions:
        # Skip utility functions
        if any(pattern in func_name.lower() for pattern in exclude_patterns):
            continue

        # Skip class constructors
        if func_name[0].isupper():
            continue

        works, details = test_indicator_function(func_name, test_data)

        if works:
            working_indicators.append(func_name)

            # Categorize
            func_lower = func_name.lower()
            if any(term in func_lower for term in ['sma', 'ema', 'wma', 'tema', 'dema', 'linreg', 'supertrend']):
                categories['trend'].append(func_name)
            elif any(term in func_lower for term in ['rsi', 'cci', 'mfi', 'willr', 'roc', 'cmo', 'trix']):
                categories['momentum'].append(func_name)
            elif any(term in func_lower for term in ['atr', 'natr', 'bbands', 'kc']):
                categories['volatility'].append(func_name)
            elif any(term in func_lower for term in ['obv', 'ad', 'cmf', 'vwap', 'nvi', 'pvi']):
                categories['volume'].append(func_name)
            elif any(term in func_lower for term in ['ichimoku', 'alma', 'hma']):
                categories['overlap'].append(func_name)
            elif any(term in func_lower for term in ['macd', 'stoch', 'adx', 'aroon']):
                categories['multi_component'].append(func_name)
        else:
            print(f"   ❌ {func_name}: {details}")

    print(f"\n✅ Working Indicators: {len(working_indicators)}")
    print("📊 By Category:")
    for category, indicators in categories.items():
        print(f"   {category:15s}: {len(indicators):3d} indicators")

    return working_indicators, categories


def main():
    """Main investigation function"""
    print("🚀 pandas_ta Indicator Investigation and Cleanup")
    print("="*60)

    if not PANDAS_TA_AVAILABLE:
        print("❌ pandas_ta not available")
        return None

    # 1. Investigate specific missing indicators
    missing_results, all_functions = investigate_missing_indicators()

    # 2. Check volume indicators comprehensively
    check_all_volume_indicators()

    # 3. Check volatility indicators comprehensively
    check_volatility_indicators()

    # 4. Generate corrected test list
    working_indicators, categories = generate_corrected_test_list()

    # 5. Print summary and recommendations
    print("\n🎯 INVESTIGATION SUMMARY")
    print("="*50)

    print("📋 Missing Indicator Analysis:")
    for indicator, result in missing_results.items():
        status = result['status']
        if status == 'found_alternative':
            alt_name = result['alternative_name']
            print(f"   ✅ {indicator:8s} -> Use '{alt_name}' instead")
        elif status == 'matches_found_but_not_working':
            matches = result['matches']
            print(f"   ⚠️  {indicator:8s} -> Found {matches} but not working")
        else:
            print(f"   ❌ {indicator:8s} -> Not found in pandas_ta")

    print(f"\n📊 Total Working Indicators: {len(working_indicators)}")
    print("📈 Recommended Action: Update tests to use only these working indicators")

    # Generate updated test configuration
    print("\n🛠️  UPDATED TEST CONFIGURATION:")
    print("```python")
    print("# Updated indicator test categories")
    for category, indicators in categories.items():
        if indicators:
            print(f"{category}_indicators = {indicators[:5]}  # Top 5, total: {len(indicators)}")
    print("```")

    return missing_results, working_indicators, categories


if __name__ == "__main__":
    results = main()
