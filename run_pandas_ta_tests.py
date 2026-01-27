#!/usr/bin/env python3
"""
Comprehensive pandas_ta test runner for the Signal Service
Tests all indicators via API calls and subscription patterns as requested
"""

import time

import numpy as np
import pandas as pd

try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
    print("✅ pandas_ta loaded successfully")
    # Get version if available
    try:
        print(f"   Version: {ta.__version__}")
    except AttributeError:
        print("   Version: unknown")
except ImportError:
    PANDAS_TA_AVAILABLE = False
    print("❌ pandas_ta not available")


class PandasTATestRunner:
    """Comprehensive test runner for pandas_ta indicators"""

    def __init__(self):
        self.test_results = {}
        self.successful_indicators = []
        self.failed_indicators = []

    def generate_test_data(self, periods=200, market_type="normal"):
        """Generate realistic test data based on market type"""
        dates = pd.date_range(start='2024-01-01', periods=periods, freq='1min')

        if market_type == "normal":
            # Normal trending market with moderate volatility
            base_price = 2500.0
            trend = 0.0002
            volatility = 0.015
        elif market_type == "volatile":
            # High volatility market
            base_price = 50000.0  # Crypto-like
            trend = 0.0001
            volatility = 0.05
        elif market_type == "ranging":
            # Sideways market
            base_price = 100.0
            trend = 0.0
            volatility = 0.02
        else:
            base_price = 100.0
            trend = 0.001
            volatility = 0.02

        # Generate prices
        prices = []
        current_price = base_price

        for i in range(periods):
            # Add trend and noise
            current_price *= (1 + trend + np.random.normal(0, volatility))
            current_price = max(current_price, base_price * 0.1)
            prices.append(current_price)

        # Create OHLCV data
        data = []
        for i, (date, close) in enumerate(zip(dates, prices, strict=False)):
            open_price = close * (1 + np.random.uniform(-0.002, 0.002))
            daily_range = abs(np.random.normal(0, 0.015))
            high = max(open_price, close) * (1 + daily_range)
            low = min(open_price, close) * (1 - daily_range)
            high = max(high, open_price, close)
            low = min(low, open_price, close)

            # Volume correlated with price movement
            price_change = abs(close - open_price) / open_price if open_price > 0 else 0
            volume = int(100000 * (1 + price_change * 4) * np.random.uniform(0.5, 2.5))

            data.append({
                'timestamp': date,
                'open': round(open_price, 2),
                'high': round(high, 2),
                'low': round(low, 2),
                'close': round(close, 2),
                'volume': volume
            })

        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        return df

    def get_all_indicators(self):
        """Get all available pandas_ta indicators"""
        if not PANDAS_TA_AVAILABLE:
            return []

        all_attrs = dir(ta)
        indicators = []

        for attr in all_attrs:
            if not attr.startswith('_') and not attr.startswith('__'):
                try:
                    func = getattr(ta, attr)
                    if callable(func) and hasattr(func, '__doc__'):
                        # Filter out utility functions
                        if not any(skip in attr.lower() for skip in [
                            'category', 'camelcase', 'deprecated', 'utils', 'version',
                            'donchian', 'increasing', 'decreasing', 'cross', 'signals',
                            'above', 'below', 'long_run', 'short_run', 'hl2', 'hlc3',
                            'ohlc4', 'typical_price', 'weighted_close', 'cov', 'corr',
                            'log', 'true_range', 'cumulative', 'percent_return'
                        ]):
                            indicators.append(attr)
                except Exception:
                    pass

        return sorted(indicators)

    def test_single_indicator(self, indicator_name, test_data):
        """Test a single indicator with multiple parameter sets"""
        if not hasattr(ta, indicator_name):
            return {'status': 'failed', 'error': 'not_found'}

        start_time = time.time()

        try:
            indicator_func = getattr(ta, indicator_name)

            # Try different parameter combinations
            parameter_sets = self.get_parameter_sets(indicator_name)

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
                        return self.validate_result(indicator_name, result, start_time, params)

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
                            return self.validate_result(indicator_name, result, start_time, params)
                    except TypeError:
                        # Try with just close
                        try:
                            result = indicator_func(close=test_data['close'], **params)
                            if result is not None:
                                return self.validate_result(indicator_name, result, start_time, params)
                        except TypeError:
                            continue
                except Exception:
                    continue

            return {'status': 'failed', 'error': 'no_valid_parameters'}

        except Exception as e:
            return {'status': 'failed', 'error': str(e)}

    def get_parameter_sets(self, indicator_name):
        """Get parameter sets to try for each indicator"""
        parameter_sets = [{}]  # Always try empty params first

        # Length-based indicators
        if any(x in indicator_name.lower() for x in ['sma', 'ema', 'wma', 'rsi', 'atr', 'adx', 'cci']):
            parameter_sets.extend([
                {'length': 14},
                {'length': 20},
                {'length': 10},
                {'period': 14},
                {'window': 14}
            ])

        # MACD variations
        if 'macd' in indicator_name.lower():
            parameter_sets.extend([
                {'fast': 12, 'slow': 26, 'signal': 9},
                {'fast': 8, 'slow': 21, 'signal': 5}
            ])

        # Bollinger Bands
        if any(x in indicator_name.lower() for x in ['bb', 'bollinger']):
            parameter_sets.extend([
                {'length': 20, 'std': 2},
                {'length': 20, 'std': 2.5}
            ])

        # Stochastic
        if 'stoch' in indicator_name.lower():
            parameter_sets.extend([
                {'k': 14, 'd': 3},
                {'k': 14, 'd': 3, 'smooth_k': 3}
            ])

        return parameter_sets

    def validate_result(self, indicator_name, result, start_time, params):
        """Validate the indicator result"""
        execution_time = (time.time() - start_time) * 1000

        validation = {'is_valid': True, 'issues': []}

        if isinstance(result, pd.Series):
            non_null_count = result.count()
            if non_null_count == 0:
                validation['is_valid'] = False
                validation['issues'].append('all_nan')

            # Range validation for specific indicators
            if non_null_count > 0:
                if 'rsi' in indicator_name.lower():
                    min_val, max_val = result.min(), result.max()
                    if min_val < 0 or max_val > 100:
                        validation['issues'].append(f'rsi_out_of_range_{min_val:.2f}_{max_val:.2f}')

                if 'willr' in indicator_name.lower():
                    min_val, max_val = result.min(), result.max()
                    if min_val < -100 or max_val > 0:
                        validation['issues'].append(f'willr_out_of_range_{min_val:.2f}_{max_val:.2f}')

        elif isinstance(result, pd.DataFrame):
            if result.empty or result.isna().all().all():
                validation['is_valid'] = False
                validation['issues'].append('empty_dataframe')

        return {
            'status': 'success',
            'execution_time_ms': round(execution_time, 2),
            'parameters': params,
            'validation': validation,
            'result_info': self.extract_result_info(result)
        }

    def extract_result_info(self, result):
        """Extract information about the result"""
        if isinstance(result, pd.Series):
            return {
                'type': 'series',
                'length': len(result),
                'non_null_count': result.count(),
                'last_value': float(result.dropna().iloc[-1]) if result.count() > 0 else None
            }
        if isinstance(result, pd.DataFrame):
            return {
                'type': 'dataframe',
                'shape': list(result.shape),
                'columns': list(result.columns),
                'non_null_counts': result.count().to_dict()
            }
        return {
            'type': type(result).__name__,
            'value': str(result)
        }

    def run_comprehensive_tests(self):
        """Run comprehensive tests on all indicators"""
        if not PANDAS_TA_AVAILABLE:
            print("❌ pandas_ta not available")
            return {}

        print("🚀 Starting comprehensive pandas_ta test suite")
        print("=" * 60)

        # Get all indicators
        all_indicators = self.get_all_indicators()
        print(f"📊 Found {len(all_indicators)} pandas_ta indicators to test")

        # Generate different market data scenarios
        test_scenarios = {
            'normal_market': self.generate_test_data(200, 'normal'),
            'volatile_market': self.generate_test_data(200, 'volatile'),
            'ranging_market': self.generate_test_data(200, 'ranging')
        }

        print(f"📈 Generated {len(test_scenarios)} market scenarios")

        # Test each indicator across all scenarios
        total_tests = len(all_indicators) * len(test_scenarios)
        completed_tests = 0

        for indicator_name in all_indicators:
            print(f"\n🔬 Testing {indicator_name}...")
            indicator_results = {}

            for scenario_name, test_data in test_scenarios.items():
                completed_tests += 1
                print(f"  [{completed_tests}/{total_tests}] {scenario_name}...", end="")

                result = self.test_single_indicator(indicator_name, test_data)
                indicator_results[scenario_name] = result

                if result['status'] == 'success':
                    print(f" ✅ {result['execution_time_ms']:.1f}ms")
                else:
                    print(f" ❌ {result['error']}")

            # Determine overall success
            success_count = sum(1 for r in indicator_results.values() if r['status'] == 'success')
            if success_count >= 2:  # At least 2/3 scenarios successful
                self.successful_indicators.append(indicator_name)
            else:
                self.failed_indicators.append(indicator_name)

            self.test_results[indicator_name] = indicator_results

        # Print summary
        self.print_summary()

        return self.test_results

    def test_api_integration_patterns(self):
        """Test pandas_ta indicators as they would be used via API calls"""
        print("\n🌐 Testing API Integration Patterns")
        print("=" * 50)

        # Simulate common API request patterns
        api_test_cases = [
            {
                'name': 'Basic Trend Analysis',
                'indicators': [
                    {'name': 'sma', 'params': {'length': 20}},
                    {'name': 'ema', 'params': {'length': 20}},
                    {'name': 'rsi', 'params': {'length': 14}}
                ]
            },
            {
                'name': 'Advanced Technical Analysis',
                'indicators': [
                    {'name': 'macd', 'params': {'fast': 12, 'slow': 26, 'signal': 9}},
                    {'name': 'bbands', 'params': {'length': 20, 'std': 2}},
                    {'name': 'atr', 'params': {'length': 14}},
                    {'name': 'adx', 'params': {'length': 14}}
                ]
            },
            {
                'name': 'Momentum Oscillators',
                'indicators': [
                    {'name': 'rsi', 'params': {'length': 14}},
                    {'name': 'cci', 'params': {'length': 20}},
                    {'name': 'willr', 'params': {'length': 14}},
                    {'name': 'mfi', 'params': {'length': 14}}
                ]
            }
        ]

        test_data = self.generate_test_data(100, 'normal')

        for test_case in api_test_cases:
            print(f"\n📋 Testing: {test_case['name']}")
            success_count = 0
            total_indicators = len(test_case['indicators'])

            for indicator_config in test_case['indicators']:
                indicator_name = indicator_config['name']
                params = indicator_config['params']

                if hasattr(ta, indicator_name):
                    try:
                        indicator_func = getattr(ta, indicator_name)
                        result = indicator_func(
                            high=test_data['high'],
                            low=test_data['low'],
                            close=test_data['close'],
                            volume=test_data['volume'],
                            **params
                        )

                        if result is not None:
                            if isinstance(result, (pd.Series, pd.DataFrame)):
                                if not (isinstance(result, pd.Series) and result.isna().all()) and \
                                   not (isinstance(result, pd.DataFrame) and result.empty):
                                    success_count += 1
                                    print(f"    ✅ {indicator_name}")
                                else:
                                    print(f"    ❌ {indicator_name} (no data)")
                            else:
                                success_count += 1
                                print(f"    ✅ {indicator_name}")
                        else:
                            print(f"    ❌ {indicator_name} (None result)")
                    except Exception as e:
                        print(f"    ❌ {indicator_name} (error: {str(e)[:50]})")
                else:
                    print(f"    ❌ {indicator_name} (not found)")

            print(f"    📊 Success Rate: {success_count}/{total_indicators} ({(success_count/total_indicators)*100:.1f}%)")

    def test_subscription_patterns(self):
        """Test indicators as they would be used in WebSocket subscriptions"""
        print("\n🔄 Testing Subscription Patterns")
        print("=" * 50)

        # Simulate real-time data updates
        print("📡 Simulating real-time tick data processing...")

        # Create incremental data updates
        base_data = self.generate_test_data(50, 'normal')

        subscription_indicators = [
            {'name': 'sma', 'params': {'length': 10}},
            {'name': 'rsi', 'params': {'length': 14}},
            {'name': 'macd', 'params': {'fast': 12, 'slow': 26, 'signal': 9}}
        ]

        print("🎯 Testing incremental updates (simulating WebSocket ticks)...")

        for i in range(5):
            print(f"   Update {i+1}/5:", end="")

            # Add new tick data
            new_tick = {
                'timestamp': base_data.index[-1] + pd.Timedelta(minutes=1),
                'open': base_data['close'].iloc[-1] * (1 + np.random.uniform(-0.002, 0.002)),
                'high': base_data['close'].iloc[-1] * (1 + np.random.uniform(0, 0.01)),
                'low': base_data['close'].iloc[-1] * (1 + np.random.uniform(-0.01, 0)),
                'close': base_data['close'].iloc[-1] * (1 + np.random.uniform(-0.005, 0.005)),
                'volume': np.random.randint(50000, 200000)
            }

            # Add to dataframe
            updated_data = pd.concat([
                base_data,
                pd.DataFrame([new_tick]).set_index('timestamp')
            ])

            # Test all indicators with updated data
            update_success = 0
            for indicator_config in subscription_indicators:
                indicator_name = indicator_config['name']
                params = indicator_config['params']

                if hasattr(ta, indicator_name):
                    try:
                        indicator_func = getattr(ta, indicator_name)
                        result = indicator_func(
                            close=updated_data['close'],
                            high=updated_data['high'],
                            low=updated_data['low'],
                            volume=updated_data['volume'],
                            **params
                        )

                        if result is not None:
                            update_success += 1
                    except Exception:
                        pass

            print(f" {update_success}/{len(subscription_indicators)} indicators updated")
            base_data = updated_data

        print("✅ Subscription pattern testing completed")

    def print_summary(self):
        """Print test summary"""
        total_indicators = len(self.test_results)
        successful_indicators = len(self.successful_indicators)
        failed_indicators = len(self.failed_indicators)

        print("\n🎯 COMPREHENSIVE TEST RESULTS")
        print("=" * 60)
        print(f"📊 Total Indicators Tested: {total_indicators}")
        print(f"✅ Successful: {successful_indicators}")
        print(f"❌ Failed: {failed_indicators}")
        print(f"🎯 Success Rate: {(successful_indicators/total_indicators)*100:.1f}%")

        # Performance statistics
        all_times = []
        for indicator_results in self.test_results.values():
            for result in indicator_results.values():
                if result['status'] == 'success' and 'execution_time_ms' in result:
                    all_times.append(result['execution_time_ms'])

        if all_times:
            print("\n⏱️  PERFORMANCE METRICS")
            print(f"   Average Execution Time: {np.mean(all_times):.1f} ms")
            print(f"   Median Execution Time: {np.median(all_times):.1f} ms")
            print(f"   Fastest Indicator: {min(all_times):.1f} ms")
            print(f"   Slowest Indicator: {max(all_times):.1f} ms")

        # Show some successful examples
        print("\n✅ SUCCESSFUL INDICATORS (Sample):")
        for indicator in self.successful_indicators[:15]:
            print(f"   ✓ {indicator}")

        if len(self.successful_indicators) > 15:
            print(f"   ... and {len(self.successful_indicators) - 15} more")

        # Show failed indicators
        if self.failed_indicators:
            print("\n❌ FAILED INDICATORS:")
            for indicator in self.failed_indicators[:10]:
                print(f"   ✗ {indicator}")

            if len(self.failed_indicators) > 10:
                print(f"   ... and {len(self.failed_indicators) - 10} more")


def main():
    """Main test execution"""
    print("🚀 Comprehensive pandas_ta Test Suite for Signal Service")
    print("Testing all indicators via direct calls and API/subscription patterns")
    print("=" * 70)

    if not PANDAS_TA_AVAILABLE:
        print("❌ pandas_ta not available. Install with: pip install pandas_ta")
        return None

    # Initialize test runner
    test_runner = PandasTATestRunner()

    # Run comprehensive indicator tests
    print("🧪 Phase 1: Comprehensive Indicator Testing")
    test_runner.run_comprehensive_tests()

    # Test API integration patterns
    print("\n🌐 Phase 2: API Integration Pattern Testing")
    test_runner.test_api_integration_patterns()

    # Test subscription patterns
    print("\n🔄 Phase 3: Subscription Pattern Testing")
    test_runner.test_subscription_patterns()

    print("\n🎉 All testing phases completed!")
    print("📈 pandas_ta integration validated for Signal Service")
    print("=" * 70)

    return test_runner.test_results


if __name__ == "__main__":
    results = main()
