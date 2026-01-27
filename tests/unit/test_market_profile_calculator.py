"""
Unit tests for MarketProfileCalculator
"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.services.market_profile_calculator import MarketProfileCalculator, ProfileType


@pytest.mark.unit
class TestMarketProfileCalculator:
    """Test suite for MarketProfileCalculator"""

    @pytest.fixture
    def mock_repository(self):
        """Mock repository for testing"""
        return AsyncMock()

    @pytest.fixture
    def calculator(self, mock_repository):
        """Create calculator instance"""
        return MarketProfileCalculator(mock_repository)

    @pytest.fixture
    def sample_ohlcv_data(self):
        """Sample OHLCV data for testing"""
        base_time = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        return [
            {
                'timestamp': base_time + timedelta(minutes=i*30),
                'open': 21500 + i,
                'high': 21510 + i,
                'low': 21490 + i,
                'close': 21505 + i,
                'volume': 1000 + i * 100
            }
            for i in range(10)
        ]

    @pytest.mark.asyncio
    async def test_calculate_volume_profile(self, calculator, sample_ohlcv_data):
        """Test volume profile calculation"""
        result = calculator._calculate_volume_profile(sample_ohlcv_data, tick_size=1.0)

        assert 'price_levels' in result
        assert 'volumes' in result
        assert 'poc' in result  # Point of Control
        assert 'total_volume' in result

        # Verify data structure
        assert len(result['price_levels']) == len(result['volumes'])
        assert result['total_volume'] > 0
        assert result['poc'] is not None

        # Verify volume aggregation
        expected_total = sum(item['volume'] for item in sample_ohlcv_data)
        assert abs(result['total_volume'] - expected_total) < 1  # Allow for rounding

    @pytest.mark.asyncio
    async def test_calculate_tpo_profile(self, calculator, sample_ohlcv_data):
        """Test TPO (Time Price Opportunity) profile calculation"""
        result = calculator._calculate_tpo_profile(sample_ohlcv_data, tick_size=1.0, interval='30m')

        assert 'tpo_counts' in result
        assert 'letter_mapping' in result
        assert 'poc' in result

        # Verify TPO structure
        assert isinstance(result['tpo_counts'], dict)
        assert isinstance(result['letter_mapping'], dict)

        # Verify letter assignment
        letters = list(result['letter_mapping'].values())
        assert len(set(letters)) <= 26  # Maximum 26 letters (A-Z)

        # POC should be the price level with highest TPO count
        if result['tpo_counts']:
            max_count = max(result['tpo_counts'].values())
            poc_count = result['tpo_counts'].get(result['poc'], 0)
            assert poc_count == max_count

    @pytest.mark.asyncio
    async def test_calculate_value_areas(self, calculator):
        """Test value area calculation (70% volume rule)"""
        # Sample volume profile data
        profile = {
            'price_levels': [99.0, 100.0, 101.0, 102.0, 103.0],
            'volumes': [100, 500, 800, 300, 200],  # Total: 1900
            'poc': 101.0,
            'total_volume': 1900
        }

        result = calculator._calculate_value_areas(profile)

        assert 'value_area' in result
        assert 'vah' in result['value_area']  # Value Area High
        assert 'val' in result['value_area']  # Value Area Low
        assert 'poc' in result['value_area']  # Point of Control
        assert 'volume_percentage' in result['value_area']

        # Verify value area contains ~70% of volume
        va_percentage = result['value_area']['volume_percentage']
        assert 65 <= va_percentage <= 75  # Should be around 70%

        # Verify VAH >= POC >= VAL
        vah = result['value_area']['vah']
        val = result['value_area']['val']
        poc = result['value_area']['poc']

        assert vah >= poc >= val
        assert poc == 101.0  # Should match input POC

    @pytest.mark.asyncio
    async def test_calculate_composite_profile(self, calculator, sample_ohlcv_data):
        """Test composite profile calculation across multiple sessions"""
        # Create multi-session data
        session1_data = sample_ohlcv_data[:5]
        session2_data = sample_ohlcv_data[5:]

        # Modify timestamps to represent different sessions
        for _i, item in enumerate(session2_data):
            item['timestamp'] = item['timestamp'] + timedelta(days=1)

        all_data = session1_data + session2_data

        result = calculator._calculate_composite_profile(all_data, tick_size=1.0)

        assert 'profile' in result
        assert 'sessions' in result
        assert 'composite_poc' in result
        assert 'composite_value_area' in result

        # Verify composite structure
        assert len(result['sessions']) == 2
        assert result['composite_poc'] is not None

        # Each session should have its own profile
        for session in result['sessions']:
            assert 'session_date' in session
            assert 'profile' in session
            assert 'poc' in session['profile']

    @pytest.mark.asyncio
    async def test_detect_market_structure(self, calculator):
        """Test market structure detection"""
        # Create different profile patterns

        # Normal Distribution (Normal Day)
        normal_volumes = [50, 100, 200, 300, 400, 300, 200, 100, 50]
        normal_profile = {
            'price_levels': list(range(21500, 21509)),
            'volumes': normal_volumes,
            'poc': 21504,
            'total_volume': sum(normal_volumes)
        }

        result = calculator._detect_market_structure(normal_profile)
        assert result['pattern'] == 'Normal Day'
        assert 'distribution_shape' in result
        assert 'balance_area' in result

        # Trending Market (skewed distribution)
        trend_volumes = [500, 400, 300, 200, 100, 50, 25, 10, 5]
        trend_profile = {
            'price_levels': list(range(21500, 21509)),
            'volumes': trend_volumes,
            'poc': 21500,
            'total_volume': sum(trend_volumes)
        }

        result = calculator._detect_market_structure(trend_profile)
        assert result['pattern'] in ['Trend Day', 'Imbalanced Market']

        # Double Distribution (Two-timeframe buyer/seller)
        double_volumes = [200, 100, 50, 100, 200, 100, 50, 100, 200]
        double_profile = {
            'price_levels': list(range(21500, 21509)),
            'volumes': double_volumes,
            'poc': 21504,
            'total_volume': sum(double_volumes)
        }

        result = calculator._detect_market_structure(double_profile)
        # Should detect multiple peaks
        assert 'peaks' in result
        assert len(result['peaks']) >= 2

    @pytest.mark.asyncio
    async def test_performance_requirements(self, calculator, sample_ohlcv_data):
        """Test that calculations meet performance requirements"""
        import time

        # Test volume profile performance
        start = time.time()
        for _ in range(10):
            calculator._calculate_volume_profile(sample_ohlcv_data, tick_size=1.0)
        end = time.time()

        avg_time = (end - start) / 10 * 1000  # Convert to ms
        assert avg_time < 100, f"Volume profile calculation took {avg_time:.2f}ms, expected <100ms"

        # Test TPO profile performance
        start = time.time()
        for _ in range(10):
            calculator._calculate_tpo_profile(sample_ohlcv_data, tick_size=1.0, interval='30m')
        end = time.time()

        avg_time = (end - start) / 10 * 1000
        assert avg_time < 150, f"TPO profile calculation took {avg_time:.2f}ms, expected <150ms"

    @pytest.mark.asyncio
    async def test_api_calculate_market_profile(self, calculator, mock_repository, sample_ohlcv_data):
        """Test main API method for market profile calculation"""
        # Mock repository response
        mock_repository.get_ohlcv_data.return_value = sample_ohlcv_data

        result = await calculator.calculate_market_profile(
            instrument_key='NSE@NIFTY@equity_spot',
            interval='30m',
            lookback_period='1d',
            profile_type=ProfileType.VOLUME
        )

        assert 'profile' in result
        assert 'metadata' in result
        assert 'market_structure' in result

        # Verify metadata
        metadata = result['metadata']
        assert metadata['instrument_key'] == 'NSE@NIFTY@equity_spot'
        assert metadata['interval'] == '30m'
        assert metadata['profile_type'] == ProfileType.VOLUME.value
        assert 'calculation_time' in metadata

        # Verify profile structure
        profile = result['profile']
        assert 'price_levels' in profile
        assert 'volumes' in profile
        assert 'value_area' in profile
        assert 'poc' in profile

    @pytest.mark.asyncio
    async def test_developing_profile(self, calculator, mock_repository, sample_ohlcv_data):
        """Test developing profile calculation (intraday)"""
        # Mock current session data
        current_session = sample_ohlcv_data[:3]  # Partial session
        mock_repository.get_current_session_data.return_value = current_session

        result = await calculator.calculate_developing_profile(
            instrument_key='NSE@NIFTY@equity_spot',
            interval='30m'
        )

        assert 'developing_profile' in result
        assert 'completion_percentage' in result
        assert 'estimated_final_structure' in result

        # Developing profile should have current data
        developing = result['developing_profile']
        assert 'current_poc' in developing
        assert 'current_value_area' in developing
        assert 'time_progression' in developing

        # Completion should be partial
        completion = result['completion_percentage']
        assert 0 < completion < 100

    @pytest.mark.asyncio
    async def test_error_handling(self, calculator, mock_repository):
        """Test error handling in market profile calculations"""
        # Empty data
        mock_repository.get_ohlcv_data.return_value = []

        with pytest.raises(ValueError, match="No OHLCV data available"):
            await calculator.calculate_market_profile(
                instrument_key='INVALID@SYMBOL',
                interval='30m',
                lookback_period='1d'
            )

        # Invalid interval
        with pytest.raises(ValueError, match="Invalid interval"):
            await calculator.calculate_market_profile(
                instrument_key='NSE@NIFTY@equity_spot',
                interval='invalid',
                lookback_period='1d'
            )

        # Repository error handling
        mock_repository.get_ohlcv_data.side_effect = Exception("Database error")

        with pytest.raises(Exception):
            await calculator.calculate_market_profile(
                instrument_key='NSE@NIFTY@equity_spot',
                interval='30m',
                lookback_period='1d'
            )

    @pytest.mark.asyncio
    async def test_tick_size_handling(self, calculator, sample_ohlcv_data):
        """Test different tick size handling"""
        # Test with different tick sizes
        tick_sizes = [0.05, 0.25, 1.0, 5.0]

        for tick_size in tick_sizes:
            result = calculator._calculate_volume_profile(sample_ohlcv_data, tick_size=tick_size)

            # Verify price levels align with tick size
            price_levels = result['price_levels']
            if len(price_levels) > 1:
                price_diff = price_levels[1] - price_levels[0]
                assert abs(price_diff - tick_size) < 0.001, f"Price levels don't align with tick size {tick_size}"

    @pytest.mark.asyncio
    async def test_large_dataset_handling(self, calculator):
        """Test handling of large datasets"""
        # Create large dataset (1000 periods)
        large_dataset = []
        base_time = datetime.utcnow().replace(minute=0, second=0, microsecond=0)

        for i in range(1000):
            large_dataset.append({
                'timestamp': base_time + timedelta(minutes=i),
                'open': 21500 + (i % 100),
                'high': 21510 + (i % 100),
                'low': 21490 + (i % 100),
                'close': 21505 + (i % 100),
                'volume': 1000 + (i % 500)
            })

        # Should handle large dataset without errors
        result = calculator._calculate_volume_profile(large_dataset, tick_size=1.0)

        assert result['total_volume'] == sum(item['volume'] for item in large_dataset)
        assert len(result['price_levels']) > 0
        assert result['poc'] is not None
