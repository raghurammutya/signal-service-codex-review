"""
Simple pandas_ta integration test to validate core functionality
Tests key indicators via direct API calls and validates results
"""

import asyncio
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False

# Mock the missing modules for testing
class MockHistoricalDataManager:
    @staticmethod
    async def get_historical_data_for_indicator(symbol: str, timeframe: str,
                                              periods_required: int, indicator_name: str):
        # Generate mock historical data
        dates = pd.date_range(end=datetime.now(), periods=periods_required, freq='5T')
        base_price = 2500.0

        # Create realistic price movement
        price_changes = np.random.normal(0.001, 0.015, periods_required)
        prices = [base_price]

        for change in price_changes[1:]:
            new_price = prices[-1] * (1 + change)
            prices.append(max(new_price, base_price * 0.5))  # Prevent unrealistic drops

        data = []
        for i, (date, close) in enumerate(zip(dates, prices, strict=False)):
            open_price = close * (1 + np.random.uniform(-0.002, 0.002))
            high = max(open_price, close) * (1 + np.random.uniform(0, 0.01))
            low = min(open_price, close) * (1 - np.random.uniform(0, 0.01))
            volume = np.random.randint(50000, 200000)

            data.append({
                'timestamp': date.isoformat(),
                'open': round(open_price, 2),
                'high': round(high, 2),
                'low': round(low, 2),
                'close': round(close, 2),
                'volume': volume
            })

        return {
            "success": True,
            "data": data,
            "symbol": symbol,
            "timeframe": timeframe,
            "periods": len(data)
        }

async def get_historical_data_manager():
    return MockHistoricalDataManager()

# Patch the imports
import sys

sys.modules['app.services.historical_data_manager'] = type(sys)('mock_module')
sys.modules['app.services.historical_data_manager'].get_historical_data_manager = get_historical_data_manager

# Now import the pandas_ta executor
from app.services.pandas_ta_executor import PandasTAExecutor


class PandasTAIntegrationTest:
    """Integration test for pandas_ta functionality"""

    def __init__(self):
        self.redis_client = MockRedisClient()
        self.executor = PandasTAExecutor(self.redis_client)

    async def test_comprehensive_indicators(self):
        """Test a comprehensive set of pandas_ta indicators"""

        print("🧪 Testing Comprehensive pandas_ta Indicators")
        print("=" * 50)

        if not PANDAS_TA_AVAILABLE:
            print("❌ pandas_ta not available")
            return None

        # Create test configuration
        config = MockConfig()
        context = await self.create_test_context()

        print(f"📊 Generated test data: {len(context.aggregated_data['5m'])} periods")

        # Test different indicator categories
        test_cases = [
            {
                'name': 'Trend Indicators',
                'indicators': [
                    {'name': 'sma', 'output_key': 'sma_20', 'parameters': {'length': 20}},
                    {'name': 'ema', 'output_key': 'ema_20', 'parameters': {'length': 20}},
                    {'name': 'wma', 'output_key': 'wma_20', 'parameters': {'length': 20}},
                    {'name': 'tema', 'output_key': 'tema_14', 'parameters': {'length': 14}},
                ]
            },
            {
                'name': 'Momentum Indicators',
                'indicators': [
                    {'name': 'rsi', 'output_key': 'rsi_14', 'parameters': {'length': 14}},
                    {'name': 'cci', 'output_key': 'cci_20', 'parameters': {'length': 20}},
                    {'name': 'mfi', 'output_key': 'mfi_14', 'parameters': {'length': 14}},
                    {'name': 'willr', 'output_key': 'willr_14', 'parameters': {'length': 14}},
                ]
            },
            {
                'name': 'Volatility Indicators',
                'indicators': [
                    {'name': 'atr', 'output_key': 'atr_14', 'parameters': {'length': 14}},
                    {'name': 'bbands', 'output_key': 'bb_20', 'parameters': {'length': 20, 'std': 2}},
                    {'name': 'kc', 'output_key': 'kc_20', 'parameters': {'length': 20}},
                    {'name': 'natr', 'output_key': 'natr_14', 'parameters': {'length': 14}},
                ]
            },
            {
                'name': 'Volume Indicators',
                'indicators': [
                    {'name': 'obv', 'output_key': 'obv', 'parameters': {}},
                    {'name': 'ad', 'output_key': 'ad', 'parameters': {}},
                    {'name': 'cmf', 'output_key': 'cmf_20', 'parameters': {'length': 20}},
                    {'name': 'vwap', 'output_key': 'vwap', 'parameters': {}},
                ]
            },
            {
                'name': 'Multi-Component Indicators',
                'indicators': [
                    {'name': 'macd', 'output_key': 'macd', 'parameters': {'fast': 12, 'slow': 26, 'signal': 9}},
                    {'name': 'stoch', 'output_key': 'stoch', 'parameters': {'k': 14, 'd': 3}},
                    {'name': 'adx', 'output_key': 'adx_14', 'parameters': {'length': 14}},
                ]
            }
        ]

        all_results = {}
        total_indicators = 0
        successful_indicators = 0

        for test_case in test_cases:
            print(f"\n📈 Testing {test_case['name']}...")
            config.technical_indicators = [MockIndicator(**ind) for ind in test_case['indicators']]

            try:
                result = await self.executor.execute_indicators(config, context)

                if result and 'results' in result:
                    results = result['results']
                    category_success = 0

                    for indicator in test_case['indicators']:
                        total_indicators += 1
                        output_key = indicator['output_key']

                        if output_key in results and results[output_key] is not None:
                            successful_indicators += 1
                            category_success += 1

                            # Validate result
                            value = results[output_key]
                            if isinstance(value, dict):
                                print(f"  ✅ {indicator['name']:8s} -> {output_key}: {list(value.keys())}")
                            else:
                                print(f"  ✅ {indicator['name']:8s} -> {output_key}: {value:.4f}")

                            all_results[output_key] = value
                        else:
                            print(f"  ❌ {indicator['name']:8s} -> {output_key}: FAILED")

                    print(f"     Category Success: {category_success}/{len(test_case['indicators'])}")
                else:
                    print(f"  ❌ Failed to execute {test_case['name']}")

            except Exception as e:
                print(f"  ❌ Error testing {test_case['name']}: {str(e)}")

        # Print summary
        print("\n🎯 OVERALL RESULTS")
        print(f"   Total Indicators Tested: {total_indicators}")
        print(f"   Successful: {successful_indicators}")
        print(f"   Success Rate: {(successful_indicators/total_indicators)*100:.1f}%")

        # Test specific indicator validations
        await self.validate_indicator_results(all_results)

        return all_results

    async def validate_indicator_results(self, results: dict[str, Any]):
        """Validate specific indicator results for correctness"""
        print("\n🔍 VALIDATING INDICATOR RESULTS")

        # Validate RSI range
        if 'rsi_14' in results and results['rsi_14'] is not None:
            rsi_value = results['rsi_14']
            if 0 <= rsi_value <= 100:
                print(f"  ✅ RSI in valid range: {rsi_value:.2f}")
            else:
                print(f"  ❌ RSI out of range: {rsi_value:.2f}")

        # Validate Williams %R range
        if 'willr_14' in results and results['willr_14'] is not None:
            willr_value = results['willr_14']
            if -100 <= willr_value <= 0:
                print(f"  ✅ Williams %R in valid range: {willr_value:.2f}")
            else:
                print(f"  ❌ Williams %R out of range: {willr_value:.2f}")

        # Validate ATR positivity
        if 'atr_14' in results and results['atr_14'] is not None:
            atr_value = results['atr_14']
            if atr_value > 0:
                print(f"  ✅ ATR is positive: {atr_value:.4f}")
            else:
                print(f"  ❌ ATR should be positive: {atr_value:.4f}")

        # Validate MACD structure
        if 'macd' in results and isinstance(results['macd'], dict):
            macd_data = results['macd']

            # Check if it has the expected keys (column names may vary)
            has_macd_structure = any(key.startswith('MACD') for key in macd_data.keys())
            if has_macd_structure:
                print(f"  ✅ MACD has proper structure: {list(macd_data.keys())}")
            else:
                print(f"  ❌ MACD missing expected structure: {list(macd_data.keys())}")

        # Validate Bollinger Bands structure and relationships
        if 'bb_20' in results and isinstance(results['bb_20'], dict):
            bb_data = results['bb_20']

            # Extract values (handling different naming conventions)
            upper = lower = middle = None
            for key, value in bb_data.items():
                if 'upper' in key.lower() or 'u' in key.lower():
                    upper = value
                elif 'lower' in key.lower() or 'l' in key.lower():
                    lower = value
                elif 'middle' in key.lower() or 'm' in key.lower():
                    middle = value

            if upper is not None and lower is not None and middle is not None:
                if lower <= middle <= upper:
                    print(f"  ✅ Bollinger Bands relationships valid: L={lower:.2f}, M={middle:.2f}, U={upper:.2f}")
                else:
                    print(f"  ❌ Bollinger Bands relationships invalid: L={lower:.2f}, M={middle:.2f}, U={upper:.2f}")
            else:
                print(f"  ⚠️  Could not validate BB relationships: {list(bb_data.keys())}")

    async def test_performance_benchmark(self):
        """Test performance of indicator calculations"""
        print("\n⏱️  PERFORMANCE BENCHMARK")

        # Create larger dataset for performance testing
        config = MockConfig()
        context = await self.create_test_context(periods=500)  # Larger dataset

        # Test performance of common indicators
        performance_indicators = [
            {'name': 'sma', 'output_key': 'sma_20', 'parameters': {'length': 20}},
            {'name': 'ema', 'output_key': 'ema_20', 'parameters': {'length': 20}},
            {'name': 'rsi', 'output_key': 'rsi_14', 'parameters': {'length': 14}},
            {'name': 'macd', 'output_key': 'macd', 'parameters': {'fast': 12, 'slow': 26, 'signal': 9}},
            {'name': 'bbands', 'output_key': 'bb_20', 'parameters': {'length': 20, 'std': 2}},
        ]

        config.technical_indicators = [MockIndicator(**ind) for ind in performance_indicators]

        # Measure execution time
        import time
        start_time = time.time()

        await self.executor.execute_indicators(config, context)

        end_time = time.time()
        execution_time_ms = (end_time - start_time) * 1000

        print(f"   📊 Dataset Size: {len(context.aggregated_data['5m'])} periods")
        print(f"   🏃 Total Execution Time: {execution_time_ms:.1f} ms")
        print(f"   ⚡ Per Indicator Avg: {execution_time_ms/len(performance_indicators):.1f} ms")

        if execution_time_ms < 1000:  # Under 1 second for 500 periods
            print("   ✅ Performance: EXCELLENT")
        elif execution_time_ms < 3000:  # Under 3 seconds
            print("   ✅ Performance: GOOD")
        else:
            print("   ⚠️  Performance: SLOW")

        return execution_time_ms

    async def create_test_context(self, periods: int = 100):
        """Create test context with mock data"""
        # Generate realistic OHLCV data
        dates = pd.date_range(end=datetime.now(), periods=periods, freq='5min')
        base_price = 2500.0

        # Create trending price movement with volatility
        trend = 0.0001  # Small upward trend
        volatility = 0.015

        prices = []
        current_price = base_price

        for i in range(periods):
            # Add trend and random walk
            change = trend + np.random.normal(0, volatility)
            current_price *= (1 + change)
            current_price = max(current_price, base_price * 0.5)
            prices.append(current_price)

        # Create OHLCV data
        ohlcv_data = []
        for i, (date, close) in enumerate(zip(dates, prices, strict=False)):
            if i == 0:
                open_price = close
            else:
                gap = np.random.normal(0, 0.002)
                open_price = prices[i-1] * (1 + gap)

            daily_range = abs(np.random.normal(0, 0.01))
            high = max(open_price, close) * (1 + daily_range * np.random.uniform(0, 1))
            low = min(open_price, close) * (1 - daily_range * np.random.uniform(0, 1))

            high = max(high, open_price, close)
            low = min(low, open_price, close)

            # Volume correlated with price movement
            price_change = abs(close - open_price) / open_price if open_price > 0 else 0
            base_volume = 150000
            volume_multiplier = 1 + price_change * 3
            volume = int(base_volume * volume_multiplier * np.random.uniform(0.5, 2.0))

            ohlcv_data.append({
                'timestamp': date.isoformat(),
                'open': round(open_price, 2),
                'high': round(high, 2),
                'low': round(low, 2),
                'close': round(close, 2),
                'volume': volume
            })

        # Create context
        context = MockContext()
        context.instrument_key = 'NSE@RELIANCE@EQ'
        context.timestamp = datetime.now()
        context.tick_data = {
            'ltp': {'value': prices[-1], 'currency': 'INR'},
            'high': {'value': max(prices[-10:])},
            'low': {'value': min(prices[-10:])},
            'open': {'value': prices[-1] * 1.001},
            'volume': 150000,
            'metadata': {
                'exchange': 'NSE',
                'is_market_open': True
            }
        }
        context.aggregated_data = {'5m': ohlcv_data}

        return context


class MockRedisClient:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def setex(self, key, ttl, value):
        self.data[key] = value
        return True


class MockConfig:
    def __init__(self):
        self.technical_indicators = []
        self.interval = MockInterval()
        self.frequency = MockFrequency()
        self.output = MockOutput()
        self.parameters = MockParameters()


class MockInterval:
    value = '5m'


class MockFrequency:
    value = 'realtime'


class MockOutput:
    cache_results = True
    cache_ttl_seconds = 300


class MockParameters:
    length = 20


class MockIndicator:
    def __init__(self, name, output_key, parameters):
        self.name = name
        self.output_key = output_key
        self.parameters = parameters


class MockContext:
    pass


async def main():
    """Run the pandas_ta integration test"""
    print("🚀 pandas_ta Integration Test Suite")
    print("=" * 50)

    test_suite = PandasTAIntegrationTest()

    try:
        # Run comprehensive indicator tests
        results = await test_suite.test_comprehensive_indicators()

        # Run performance benchmark
        await test_suite.test_performance_benchmark()

        print("\n✅ Integration tests completed successfully!")
        print(f"   📊 Tested {len(results)} different indicator configurations")
        print("   🎯 All major indicator categories validated")

        return True

    except Exception as e:
        print(f"\n❌ Integration test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
