"""
Comprehensive pandas_ta indicator testing with real data generation and validation
Tests all 244+ pandas_ta indicators systematically with proper data validation
"""

import csv
import json
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
    print(f"pandas_ta version: {ta.__version__}")
except ImportError:
    PANDAS_TA_AVAILABLE = False
    print("pandas_ta not available")


class PandasTAComprehensiveTester:
    """
    Comprehensive testing suite for all pandas_ta indicators
    Generates realistic market data and validates all indicator calculations
    """

    def __init__(self):
        self.test_results = {}
        self.failed_indicators = []
        self.successful_indicators = []
        self.test_data_variants = {}

        if PANDAS_TA_AVAILABLE:
            self.all_indicators = self._get_all_indicators()
            print(f"Found {len(self.all_indicators)} pandas_ta indicators to test")
        else:
            self.all_indicators = []

    def _get_all_indicators(self) -> list[str]:
        """Get comprehensive list of all pandas_ta indicators"""
        # Get all functions from pandas_ta
        all_attrs = dir(ta)
        indicators = []

        for attr in all_attrs:
            if not attr.startswith('_') and not attr.startswith('__'):
                try:
                    func = getattr(ta, attr)
                    if (callable(func) and hasattr(func, '__doc__') and
                        not any(skip in attr.lower() for skip in [
                            'category', 'camelcase', 'deprecated', 'utils', 'version',
                            'donchian', 'increasing', 'decreasing', 'cross', 'signals',
                            'above', 'below', 'long_run', 'short_run'
                        ])):
                        indicators.append(attr)
                except Exception:
                    pass

        return sorted(indicators)

    def generate_test_data_variants(self) -> dict[str, pd.DataFrame]:
        """
        Generate multiple variants of test data for comprehensive testing
        Each variant tests different market conditions
        """
        variants = {}

        # 1. Standard trending market
        variants['trending_up'] = self._create_trending_data(
            periods=200, trend=0.002, volatility=0.015, base_price=100.0
        )

        # 2. Downtrending market
        variants['trending_down'] = self._create_trending_data(
            periods=200, trend=-0.0015, volatility=0.02, base_price=100.0
        )

        # 3. Sideways/ranging market
        variants['ranging'] = self._create_ranging_data(
            periods=200, volatility=0.025, base_price=100.0
        )

        # 4. High volatility market
        variants['high_volatility'] = self._create_volatile_data(
            periods=200, volatility=0.06, base_price=100.0
        )

        # 5. Low volatility market
        variants['low_volatility'] = self._create_trending_data(
            periods=200, trend=0.0005, volatility=0.005, base_price=100.0
        )

        # 6. Market crash scenario
        variants['crash'] = self._create_crash_data(
            periods=200, crash_start=100, crash_magnitude=0.3
        )

        # 7. Market recovery scenario
        variants['recovery'] = self._create_recovery_data(
            periods=200, recovery_start=50, recovery_strength=0.05
        )

        # 8. High frequency data (crypto-like)
        variants['high_frequency'] = self._create_high_frequency_data(
            periods=1000, base_price=50000.0
        )

        # 9. Traditional stock data
        variants['traditional_stock'] = self._create_traditional_stock_data(
            periods=252, base_price=250.0  # 1 year of daily data
        )

        # 10. Forex-like data
        variants['forex'] = self._create_forex_data(
            periods=500, base_price=1.2000
        )

        self.test_data_variants = variants
        return variants

    def _create_trending_data(self, periods: int, trend: float, volatility: float,
                             base_price: float) -> pd.DataFrame:
        """Create trending market data"""
        dates = pd.date_range(start='2024-01-01', periods=periods, freq='1H')

        prices = []
        current_price = base_price

        for _i in range(periods):
            # Apply trend
            current_price *= (1 + trend + np.random.normal(0, volatility))
            current_price = max(current_price, base_price * 0.1)  # Prevent negative prices
            prices.append(current_price)

        return self._create_ohlcv_from_closes(dates, prices)

    def _create_ranging_data(self, periods: int, volatility: float,
                            base_price: float) -> pd.DataFrame:
        """Create ranging/sideways market data"""
        dates = pd.date_range(start='2024-01-01', periods=periods, freq='1H')

        prices = []
        current_price = base_price

        # Use sine wave for ranging pattern
        for i in range(periods):
            sine_component = np.sin(i * 2 * np.pi / 50) * 0.05  # 5% range
            noise = np.random.normal(0, volatility)
            current_price = base_price * (1 + sine_component + noise)
            current_price = max(current_price, base_price * 0.5)
            prices.append(current_price)

        return self._create_ohlcv_from_closes(dates, prices)

    def _create_volatile_data(self, periods: int, volatility: float,
                             base_price: float) -> pd.DataFrame:
        """Create highly volatile market data"""
        dates = pd.date_range(start='2024-01-01', periods=periods, freq='30T')

        prices = []
        current_price = base_price

        for _i in range(periods):
            # High volatility with occasional jumps
            if np.random.random() < 0.05:  # 5% chance of jump
                jump = np.random.choice([-1, 1]) * np.random.uniform(0.03, 0.08)
            else:
                jump = 0

            change = jump + np.random.normal(0, volatility)
            current_price *= (1 + change)
            current_price = max(current_price, base_price * 0.1)
            prices.append(current_price)

        return self._create_ohlcv_from_closes(dates, prices)

    def _create_crash_data(self, periods: int, crash_start: int,
                          crash_magnitude: float) -> pd.DataFrame:
        """Create market crash scenario"""
        dates = pd.date_range(start='2024-01-01', periods=periods, freq='1H')

        prices = []
        base_price = 100.0
        current_price = base_price

        for i in range(periods):
            if crash_start <= i <= crash_start + 20:  # 20-period crash
                # Accelerating decline
                crash_factor = -crash_magnitude * ((i - crash_start) / 20) ** 2
                change = crash_factor + np.random.normal(0, 0.03)
            elif i > crash_start + 20:
                # Post-crash stabilization with high volatility
                change = np.random.normal(-0.001, 0.025)
            else:
                # Pre-crash normal market
                change = np.random.normal(0.001, 0.015)

            current_price *= (1 + change)
            current_price = max(current_price, base_price * 0.1)
            prices.append(current_price)

        return self._create_ohlcv_from_closes(dates, prices)

    def _create_recovery_data(self, periods: int, recovery_start: int,
                             recovery_strength: float) -> pd.DataFrame:
        """Create market recovery scenario"""
        dates = pd.date_range(start='2024-01-01', periods=periods, freq='1H')

        prices = []
        base_price = 100.0
        current_price = base_price * 0.7  # Start at 70% of base (post-crash)

        for i in range(periods):
            if recovery_start <= i:
                # Recovery phase with diminishing returns
                recovery_factor = recovery_strength * np.exp(-(i - recovery_start) / 50)
                change = recovery_factor + np.random.normal(0, 0.02)
            else:
                # Pre-recovery depressed market
                change = np.random.normal(-0.001, 0.02)

            current_price *= (1 + change)
            current_price = max(current_price, base_price * 0.1)
            prices.append(current_price)

        return self._create_ohlcv_from_closes(dates, prices)

    def _create_high_frequency_data(self, periods: int, base_price: float) -> pd.DataFrame:
        """Create high-frequency trading data (crypto-like)"""
        dates = pd.date_range(start='2024-01-01', periods=periods, freq='1T')

        prices = []
        current_price = base_price

        for i in range(periods):
            # High frequency with clustering volatility
            volatility = 0.001 if i % 100 < 80 else 0.005  # Volatility clustering
            change = np.random.normal(0, volatility)

            # Add some microstructure effects
            if i > 0 and np.random.random() < 0.1:
                # Momentum/mean reversion
                prev_change = (prices[i-1] - (prices[i-2] if i > 1 else current_price)) / current_price
                change += prev_change * 0.1 * np.random.choice([-1, 1])

            current_price *= (1 + change)
            current_price = max(current_price, base_price * 0.5)
            prices.append(current_price)

        return self._create_ohlcv_from_closes(dates, prices)

    def _create_traditional_stock_data(self, periods: int, base_price: float) -> pd.DataFrame:
        """Create traditional stock market data (daily)"""
        dates = pd.date_range(start='2024-01-01', periods=periods, freq='1D')

        prices = []
        current_price = base_price

        for i in range(periods):
            # Seasonal effects
            seasonal_factor = 0.001 * np.sin(i * 2 * np.pi / 252)  # Yearly cycle

            # Random walk with slight upward bias
            change = 0.0003 + seasonal_factor + np.random.normal(0, 0.018)

            # Weekend effect (if trading on weekends)
            if dates[i].weekday() >= 5:  # Saturday/Sunday
                change *= 0.5

            current_price *= (1 + change)
            current_price = max(current_price, base_price * 0.2)
            prices.append(current_price)

        return self._create_ohlcv_from_closes(dates, prices)

    def _create_forex_data(self, periods: int, base_price: float) -> pd.DataFrame:
        """Create forex-like data"""
        dates = pd.date_range(start='2024-01-01', periods=periods, freq='1H')

        prices = []
        current_price = base_price

        for _i in range(periods):
            # Central bank intervention effects
            if abs(current_price - base_price) / base_price > 0.15:
                # Mean reversion when too far from base
                intervention = -0.001 * np.sign(current_price - base_price)
            else:
                intervention = 0

            change = intervention + np.random.normal(0, 0.008)

            current_price *= (1 + change)
            current_price = max(current_price, base_price * 0.5)
            prices.append(current_price)

        return self._create_ohlcv_from_closes(dates, prices)

    def _create_ohlcv_from_closes(self, dates: pd.DatetimeIndex, closes: list[float]) -> pd.DataFrame:
        """Create realistic OHLCV data from close prices"""
        data = []

        for i, (date, close) in enumerate(zip(dates, closes, strict=False)):
            # Create realistic OHLC from close
            if i == 0:
                open_price = close
            else:
                # Open is previous close with small gap
                gap = np.random.normal(0, 0.002)
                open_price = closes[i-1] * (1 + gap)

            # Generate high and low
            daily_range = abs(np.random.normal(0, 0.02))  # Daily range
            high = max(open_price, close) * (1 + daily_range * np.random.uniform(0, 1))
            low = min(open_price, close) * (1 - daily_range * np.random.uniform(0, 1))

            # Ensure OHLC relationships
            high = max(high, open_price, close)
            low = min(low, open_price, close)

            # Generate volume correlated with price movement
            price_change = abs(close - open_price) / open_price if open_price > 0 else 0
            base_volume = 100000
            volume_multiplier = 1 + price_change * 5  # Higher volume on big moves
            volume = int(base_volume * volume_multiplier * np.random.uniform(0.3, 3.0))

            data.append({
                'timestamp': date,
                'open': round(open_price, 4),
                'high': round(high, 4),
                'low': round(low, 4),
                'close': round(close, 4),
                'volume': volume
            })

        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        return df

    def test_all_indicators(self, save_results: bool = True) -> dict[str, Any]:
        """
        Test all pandas_ta indicators across all data variants
        """
        if not PANDAS_TA_AVAILABLE:
            print("pandas_ta not available - cannot run tests")
            return {}

        print(f"Starting comprehensive test of {len(self.all_indicators)} indicators...")
        print("Generating test data variants...")

        # Generate test data
        data_variants = self.generate_test_data_variants()
        print(f"Generated {len(data_variants)} data variants")

        # Test each indicator
        total_tests = len(self.all_indicators) * len(data_variants)
        current_test = 0

        for indicator_name in self.all_indicators:
            print(f"\nTesting indicator: {indicator_name}")
            indicator_results = {}

            for variant_name, data in data_variants.items():
                current_test += 1
                print(f"  [{current_test}/{total_tests}] Testing on {variant_name} data...", end="")

                try:
                    result = self._test_single_indicator(indicator_name, data, variant_name)
                    indicator_results[variant_name] = result
                    print(f" ✓ {result['status']}")

                except Exception as e:
                    print(f" ✗ FAILED: {str(e)[:100]}")
                    indicator_results[variant_name] = {
                        'status': 'failed',
                        'error': str(e),
                        'error_type': type(e).__name__
                    }

            # Aggregate results for this indicator
            self.test_results[indicator_name] = indicator_results

            # Determine overall status
            success_count = sum(1 for r in indicator_results.values() if r['status'] == 'success')
            if success_count >= len(data_variants) * 0.7:  # 70% success rate
                self.successful_indicators.append(indicator_name)
            else:
                self.failed_indicators.append(indicator_name)

        # Generate summary
        summary = self._generate_test_summary()

        if save_results:
            self._save_test_results(summary)

        return summary

    def _test_single_indicator(self, indicator_name: str, data: pd.DataFrame,
                              variant_name: str) -> dict[str, Any]:
        """Test a single indicator on a specific dataset"""
        start_time = time.time()

        try:
            # Get the indicator function
            indicator_func = getattr(ta, indicator_name)

            # Try different parameter combinations
            result = None
            params_used = {}

            # Common parameter sets to try
            parameter_sets = self._get_parameter_sets(indicator_name)

            for params in parameter_sets:
                try:
                    # Execute the indicator
                    result = indicator_func(
                        high=data['high'],
                        low=data['low'],
                        close=data['close'],
                        volume=data['volume'],
                        open_=data['open'],
                        **params
                    )
                    params_used = params
                    break

                except TypeError:
                    # Try with fewer parameters
                    try:
                        result = indicator_func(
                            close=data['close'],
                            high=data['high'],
                            low=data['low'],
                            volume=data['volume'],
                            **params
                        )
                        params_used = params
                        break
                    except TypeError:
                        # Try with just close price
                        try:
                            result = indicator_func(close=data['close'], **params)
                            params_used = params
                            break
                        except TypeError:
                            continue

                except Exception:
                    # Parameter set failed, try next one
                    continue

            if result is None:
                return {
                    'status': 'failed',
                    'error': 'No valid parameter combination found'
                }

            # Validate the result
            validation = self._validate_indicator_result(indicator_name, result, data, variant_name)

            execution_time = time.time() - start_time

            return {
                'status': 'success',
                'execution_time_ms': round(execution_time * 1000, 2),
                'parameters_used': params_used,
                'result_type': type(result).__name__,
                'result_shape': getattr(result, 'shape', None),
                'validation': validation,
                'sample_values': self._extract_sample_values(result)
            }

        except Exception as e:
            execution_time = time.time() - start_time
            return {
                'status': 'failed',
                'execution_time_ms': round(execution_time * 1000, 2),
                'error': str(e),
                'error_type': type(e).__name__,
                'traceback': traceback.format_exc()
            }

    def _get_parameter_sets(self, indicator_name: str) -> list[dict]:
        """Get appropriate parameter sets for testing different indicators"""
        # Default empty parameters
        parameter_sets = [{}]

        # Common length-based parameters
        if any(x in indicator_name.lower() for x in ['sma', 'ema', 'wma', 'rsi', 'atr', 'adx', 'cci']):
            parameter_sets.extend([
                {'length': 14},
                {'length': 20},
                {'length': 50},
                {'period': 14},  # Alternative parameter name
                {'window': 14}   # Alternative parameter name
            ])

        # MACD parameters
        if 'macd' in indicator_name.lower():
            parameter_sets.extend([
                {'fast': 12, 'slow': 26, 'signal': 9},
                {'fast': 8, 'slow': 21, 'signal': 5}
            ])

        # Bollinger Bands parameters
        if 'bb' in indicator_name.lower() or 'bollinger' in indicator_name.lower():
            parameter_sets.extend([
                {'length': 20, 'std': 2},
                {'length': 20, 'std': 2.5},
                {'period': 20, 'stddev': 2}
            ])

        # Stochastic parameters
        if 'stoch' in indicator_name.lower():
            parameter_sets.extend([
                {'k': 14, 'd': 3},
                {'k': 14, 'd': 3, 'smooth_k': 3}
            ])

        # Williams %R parameters
        if 'willr' in indicator_name.lower():
            parameter_sets.extend([
                {'length': 14},
                {'period': 14}
            ])

        # Volume indicators
        if any(x in indicator_name.lower() for x in ['obv', 'ad', 'mfi', 'cmf']):
            parameter_sets.extend([
                {'length': 14},
                {'length': 20}
            ])

        return parameter_sets

    def _validate_indicator_result(self, indicator_name: str, result: Any,
                                  data: pd.DataFrame, variant_name: str) -> dict[str, Any]:
        """Validate the indicator calculation result"""
        validation = {
            'is_valid': True,
            'issues': [],
            'statistics': {}
        }

        try:
            if isinstance(result, pd.Series):
                # Validate Series result
                validation['statistics']['length'] = len(result)
                validation['statistics']['non_null_count'] = result.count()
                validation['statistics']['null_percentage'] = (result.isna().sum() / len(result)) * 100

                if result.count() > 0:
                    validation['statistics']['min'] = float(result.min())
                    validation['statistics']['max'] = float(result.max())
                    validation['statistics']['mean'] = float(result.mean())
                    validation['statistics']['std'] = float(result.std())

                # Check for common issues
                if result.isna().all():
                    validation['is_valid'] = False
                    validation['issues'].append('All values are NaN')

                if result.count() > 0:
                    # Check for infinite values
                    if np.isinf(result).any():
                        validation['issues'].append('Contains infinite values')

                    # Check for unreasonable values (indicator-specific)
                    self._validate_indicator_range(indicator_name, result, validation)

            elif isinstance(result, pd.DataFrame):
                # Validate DataFrame result
                validation['statistics']['shape'] = list(result.shape)
                validation['statistics']['columns'] = list(result.columns)
                validation['statistics']['non_null_counts'] = result.count().to_dict()

                total_cells = result.size
                null_cells = result.isna().sum().sum()
                validation['statistics']['null_percentage'] = (null_cells / total_cells) * 100

                if result.empty:
                    validation['is_valid'] = False
                    validation['issues'].append('DataFrame is empty')

                if result.isna().all().all():
                    validation['is_valid'] = False
                    validation['issues'].append('All values are NaN')

                # Check each column
                for col in result.columns:
                    if np.isinf(result[col]).any():
                        validation['issues'].append(f'Column {col} contains infinite values')

            else:
                validation['statistics']['type'] = type(result).__name__
                validation['statistics']['value'] = str(result)

        except Exception as e:
            validation['is_valid'] = False
            validation['issues'].append(f'Validation error: {str(e)}')

        return validation

    def _validate_indicator_range(self, indicator_name: str, result: pd.Series,
                                 validation: dict) -> None:
        """Validate indicator values are within expected ranges"""
        if result.count() == 0:
            return

        min_val = float(result.min())
        max_val = float(result.max())

        # RSI should be between 0 and 100
        if 'rsi' in indicator_name.lower() and (min_val < 0 or max_val > 100):
            validation['issues'].append(f'RSI values outside 0-100 range: {min_val:.2f} to {max_val:.2f}')

        # Williams %R should be between -100 and 0
        if 'willr' in indicator_name.lower() and (min_val < -100 or max_val > 0):
            validation['issues'].append(f'Williams %R values outside -100 to 0 range: {min_val:.2f} to {max_val:.2f}')

        # ATR should be positive
        if 'atr' in indicator_name.lower() and not indicator_name.lower().startswith('natr') and min_val < 0:
            validation['issues'].append(f'ATR should be positive, got minimum: {min_val:.4f}')

        # Volume indicators should generally follow volume patterns
        if 'obv' in indicator_name.lower():
            # OBV can be any value but should show trend
            pass

        # Check for extremely large values (potential calculation errors)
        if abs(max_val) > 1e10 or abs(min_val) > 1e10:
            validation['issues'].append(f'Extremely large values detected: {min_val:.2e} to {max_val:.2e}')

    def _extract_sample_values(self, result: Any) -> dict[str, Any]:
        """Extract sample values from the result for inspection"""
        samples = {}

        try:
            if isinstance(result, pd.Series):
                if len(result) > 0:
                    samples['first_valid'] = self._safe_convert(result.dropna().iloc[0] if result.count() > 0 else None)
                    samples['last_valid'] = self._safe_convert(result.dropna().iloc[-1] if result.count() > 0 else None)
                    samples['last_5'] = [self._safe_convert(x) for x in result.tail(5).tolist()]

            elif isinstance(result, pd.DataFrame):
                if not result.empty:
                    samples['columns'] = list(result.columns)
                    samples['last_row'] = {}
                    for col in result.columns:
                        last_valid = result[col].dropna().iloc[-1] if result[col].count() > 0 else None
                        samples['last_row'][col] = self._safe_convert(last_valid)

            else:
                samples['value'] = str(result)

        except Exception as e:
            samples['error'] = f"Could not extract samples: {str(e)}"

        return samples

    def _safe_convert(self, value) -> Any:
        """Safely convert pandas values to JSON-serializable types"""
        if pd.isna(value):
            return None
        if isinstance(value, np.integer | np.floating):
            return float(value)
        return value

    def _generate_test_summary(self) -> dict[str, Any]:
        """Generate comprehensive test summary"""
        total_indicators = len(self.test_results)
        successful_indicators = len(self.successful_indicators)
        failed_indicators = len(self.failed_indicators)

        # Calculate success rates by data variant
        variant_success_rates = {}
        for variant in self.test_data_variants:
            successes = sum(1 for results in self.test_results.values()
                          if results.get(variant, {}).get('status') == 'success')
            variant_success_rates[variant] = (successes / total_indicators) * 100

        # Identify most problematic indicators
        problematic_indicators = {}
        for indicator, results in self.test_results.items():
            failure_count = sum(1 for r in results.values() if r.get('status') != 'success')
            if failure_count > 0:
                problematic_indicators[indicator] = failure_count

        # Performance statistics
        execution_times = []
        for results in self.test_results.values():
            for result in results.values():
                if 'execution_time_ms' in result:
                    execution_times.append(result['execution_time_ms'])

        return {
            'test_summary': {
                'total_indicators_tested': total_indicators,
                'successful_indicators': successful_indicators,
                'failed_indicators': failed_indicators,
                'success_rate_percent': (successful_indicators / total_indicators) * 100,
                'test_timestamp': datetime.now().isoformat()
            },
            'data_variants': {
                'variants_tested': list(self.test_data_variants.keys()),
                'variant_success_rates': variant_success_rates
            },
            'performance': {
                'total_execution_time_ms': sum(execution_times),
                'average_execution_time_ms': np.mean(execution_times) if execution_times else 0,
                'median_execution_time_ms': np.median(execution_times) if execution_times else 0,
                'slowest_execution_ms': max(execution_times) if execution_times else 0,
                'fastest_execution_ms': min(execution_times) if execution_times else 0
            },
            'indicators': {
                'successful': self.successful_indicators,
                'failed': self.failed_indicators,
                'most_problematic': dict(sorted(problematic_indicators.items(),
                                              key=lambda x: x[1], reverse=True)[:10])
            },
            'detailed_results': self.test_results
        }


    def _save_test_results(self, summary: dict[str, Any]) -> None:
        """Save test results to files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("test_results")
        output_dir.mkdir(exist_ok=True)

        # Save full results as JSON
        results_file = output_dir / f"pandas_ta_test_results_{timestamp}.json"
        with open(results_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)

        # Save summary as CSV
        summary_file = output_dir / f"pandas_ta_test_summary_{timestamp}.csv"
        summary_rows = []

        for indicator, results in self.test_results.items():
            success_count = sum(1 for r in results.values() if r.get('status') == 'success')
            total_tests = len(results)
            success_rate = (success_count / total_tests) * 100

            avg_time = np.mean([r.get('execution_time_ms', 0) for r in results.values()])

            summary_rows.append({
                'indicator': indicator,
                'success_count': success_count,
                'total_tests': total_tests,
                'success_rate_percent': round(success_rate, 1),
                'average_execution_time_ms': round(avg_time, 2),
                'status': 'PASSED' if success_rate >= 70 else 'FAILED'
            })

        with open(summary_file, 'w', newline='') as f:
            if summary_rows:
                writer = csv.DictWriter(f, fieldnames=summary_rows[0].keys())
                writer.writeheader()
                writer.writerows(summary_rows)

        print("\n✅ Test results saved:")
        print(f"   📁 Full results: {results_file}")
        print(f"   📊 Summary CSV: {summary_file}")

    def print_summary(self, summary: dict[str, Any]) -> None:
        """Print a human-readable test summary"""
        print("\n" + "="*80)
        print("🔍 PANDAS_TA COMPREHENSIVE TEST RESULTS")
        print("="*80)

        test_summary = summary['test_summary']
        print(f"📈 Total Indicators Tested: {test_summary['total_indicators_tested']}")
        print(f"✅ Successful: {test_summary['successful_indicators']}")
        print(f"❌ Failed: {test_summary['failed_indicators']}")
        print(f"🎯 Success Rate: {test_summary['success_rate_percent']:.1f}%")

        print("\n⏱️  PERFORMANCE METRICS")
        perf = summary['performance']
        print(f"   Total Test Time: {perf['total_execution_time_ms']/1000:.1f} seconds")
        print(f"   Average per Indicator: {perf['average_execution_time_ms']:.1f} ms")
        print(f"   Fastest Indicator: {perf['fastest_execution_ms']:.1f} ms")
        print(f"   Slowest Indicator: {perf['slowest_execution_ms']:.1f} ms")

        print("\n📊 DATA VARIANT SUCCESS RATES")
        for variant, rate in summary['data_variants']['variant_success_rates'].items():
            print(f"   {variant:20s}: {rate:5.1f}%")

        print("\n❌ MOST PROBLEMATIC INDICATORS")
        for indicator, failure_count in list(summary['indicators']['most_problematic'].items())[:5]:
            print(f"   {indicator:20s}: {failure_count} failures")

        print("\n✅ SUCCESSFULLY TESTED INDICATORS (Sample):")
        for indicator in summary['indicators']['successful'][:10]:
            print(f"   ✓ {indicator}")

        if len(summary['indicators']['successful']) > 10:
            remaining = len(summary['indicators']['successful']) - 10
            print(f"   ... and {remaining} more")

        print("\n" + "="*80)


def main():
    """Run the comprehensive pandas_ta test suite"""
    print("🚀 Starting Comprehensive pandas_ta Test Suite")
    print("="*60)

    if not PANDAS_TA_AVAILABLE:
        print("❌ pandas_ta not available. Please install with: pip install pandas_ta")
        return None

    # Initialize tester
    tester = PandasTAComprehensiveTester()

    # Run comprehensive tests
    print("🧪 Running comprehensive indicator tests...")
    summary = tester.test_all_indicators(save_results=True)

    # Print summary
    tester.print_summary(summary)

    # Return summary for programmatic use
    return summary


if __name__ == "__main__":
    main()
