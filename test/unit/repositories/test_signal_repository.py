"""Unit tests for Signal Repository."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.repositories.signal_repository import DatabaseError, SignalRepository


class TestSignalRepository:
    """Unit tests for Signal Repository."""

    @pytest.fixture
    def repository(self):
        """Create repository instance for testing."""
        return SignalRepository()

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session."""
        session = AsyncMock()
        connection = AsyncMock()

        # Setup context manager behavior
        session.acquire.return_value.__aenter__.return_value = connection
        session.acquire.return_value.__aexit__.return_value = None

        return session, connection

    @pytest.mark.asyncio
    async def test_repository_initialization(self, repository):
        """Test repository initializes correctly."""
        assert repository is not None
        assert not repository._initialized

        # Test ensure_initialized
        with patch('app.repositories.signal_repository.get_timescaledb_session') as mock_get_session:
            mock_get_session.return_value = AsyncMock()
            await repository.ensure_initialized()
            assert repository._initialized

    @pytest.mark.asyncio
    async def test_save_greeks_success(self, repository, sample_greeks_data):
        """Test successful Greeks saving."""
        session, connection = AsyncMock(), AsyncMock()
        connection.fetchrow.return_value = {'id': 123}
        session.acquire.return_value.__aenter__.return_value = connection

        with patch.object(repository, 'db_connection', session):
            repository._initialized = True

            greeks_record = {
                "signal_id": "test_signal",
                "instrument_key": "NSE@TEST@CE@20000",
                "timestamp": datetime.utcnow(),
                **sample_greeks_data
            }

            record_id = await repository.save_greeks(greeks_record)

            assert record_id == 123
            connection.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_greeks_database_error(self, repository):
        """Test Greeks saving with database error - should raise exception."""
        session, connection = AsyncMock(), AsyncMock()
        connection.fetchrow.side_effect = Exception("Database connection failed")
        session.acquire.return_value.__aenter__.return_value = connection

        with patch.object(repository, 'db_connection', session):
            repository._initialized = True

            greeks_record = {
                "signal_id": "test_signal",
                "instrument_key": "NSE@TEST@CE@20000",
                "timestamp": datetime.utcnow(),
                "delta": 0.5,
                "gamma": 0.02
            }

            # Should raise exception, not return None
            with pytest.raises(Exception):  # Original exception should propagate
                await repository.save_greeks(greeks_record)

    @pytest.mark.asyncio
    async def test_get_latest_greeks_success(self, repository):
        """Test successful latest Greeks retrieval."""
        session, connection = AsyncMock(), AsyncMock()

        # Mock successful database response
        mock_result = {
            'id': 123,
            'instrument_key': 'NSE@TEST@CE@20000',
            'delta': 0.5234,
            'gamma': 0.0156,
            'theta': -12.45,
            'timestamp': datetime.utcnow()
        }
        connection.fetchrow.return_value = mock_result
        session.acquire.return_value.__aenter__.return_value = connection

        with patch.object(repository, 'db_connection', session):
            repository._initialized = True

            result = await repository.get_latest_greeks("NSE@TEST@CE@20000")

            assert result is not None
            assert result['delta'] == 0.5234
            assert result['gamma'] == 0.0156
            assert result['instrument_key'] == 'NSE@TEST@CE@20000'

    @pytest.mark.asyncio
    async def test_get_latest_greeks_not_found(self, repository):
        """Test latest Greeks retrieval when no data found."""
        session, connection = AsyncMock(), AsyncMock()
        connection.fetchrow.return_value = None  # No data found
        session.acquire.return_value.__aenter__.return_value = connection

        with patch.object(repository, 'db_connection', session):
            repository._initialized = True

            result = await repository.get_latest_greeks("NSE@NONEXISTENT@CE@20000")

            # Should return None for not found (this is legitimate)
            assert result is None

    @pytest.mark.asyncio
    async def test_get_latest_greeks_database_error(self, repository):
        """Test latest Greeks retrieval with database error - should raise exception."""
        session, connection = AsyncMock(), AsyncMock()
        connection.fetchrow.side_effect = Exception("Database connection failed")
        session.acquire.return_value.__aenter__.return_value = connection

        with patch.object(repository, 'db_connection', session):
            repository._initialized = True

            # Should raise DatabaseError, not return None silently
            with pytest.raises(DatabaseError) as exc_info:
                await repository.get_latest_greeks("NSE@TEST@CE@20000")

            assert "Failed to fetch latest Greeks" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_historical_greeks_success(self, repository):
        """Test successful historical Greeks retrieval."""
        session, connection = AsyncMock(), AsyncMock()

        # Mock historical data
        start_time = datetime.utcnow() - timedelta(hours=1)
        end_time = datetime.utcnow()

        mock_results = [
            {
                'id': 1,
                'instrument_key': 'NSE@TEST@CE@20000',
                'timestamp': start_time + timedelta(minutes=5),
                'delta': 0.52,
                'gamma': 0.015
            },
            {
                'id': 2,
                'instrument_key': 'NSE@TEST@CE@20000',
                'timestamp': start_time + timedelta(minutes=10),
                'delta': 0.53,
                'gamma': 0.016
            }
        ]
        connection.fetch.return_value = mock_results
        session.acquire.return_value.__aenter__.return_value = connection

        with patch.object(repository, 'db_connection', session):
            repository._initialized = True

            results = await repository.get_historical_greeks(
                "NSE@TEST@CE@20000",
                start_time,
                end_time
            )

            assert len(results) == 2
            assert results[0]['delta'] == 0.52
            assert results[1]['delta'] == 0.53

    @pytest.mark.asyncio
    async def test_get_historical_greeks_database_error(self, repository):
        """Test historical Greeks retrieval with database error - should raise exception."""
        session, connection = AsyncMock(), AsyncMock()
        connection.fetch.side_effect = Exception("Database query failed")
        session.acquire.return_value.__aenter__.return_value = connection

        with patch.object(repository, 'db_connection', session):
            repository._initialized = True

            start_time = datetime.utcnow() - timedelta(hours=1)
            end_time = datetime.utcnow()

            # Should raise DatabaseError, not return empty list silently
            with pytest.raises(DatabaseError) as exc_info:
                await repository.get_historical_greeks(
                    "NSE@TEST@CE@20000",
                    start_time,
                    end_time
                )

            assert "Failed to fetch historical Greeks" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_save_indicator_success(self, repository):
        """Test successful indicator saving."""
        session, connection = AsyncMock(), AsyncMock()
        connection.fetchrow.return_value = {'id': 456}
        session.acquire.return_value.__aenter__.return_value = connection

        with patch.object(repository, 'db_connection', session):
            repository._initialized = True

            indicator_record = {
                "signal_id": "test_indicator",
                "instrument_key": "NSE@TEST",
                "timestamp": datetime.utcnow(),
                "indicator_name": "RSI",
                "parameters": {"period": 14},
                "values": {"rsi": 65.5}
            }

            record_id = await repository.save_indicator(indicator_record)

            assert record_id == 456
            connection.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_latest_indicator_success(self, repository):
        """Test successful latest indicator retrieval."""
        session, connection = AsyncMock(), AsyncMock()

        mock_result = {
            'id': 456,
            'instrument_key': 'NSE@TEST',
            'indicator_name': 'RSI',
            'parameters': '{"period": 14}',
            'values': '{"rsi": 65.5}',
            'timestamp': datetime.utcnow()
        }
        connection.fetchrow.return_value = mock_result
        session.acquire.return_value.__aenter__.return_value = connection

        with patch.object(repository, 'db_connection', session):
            repository._initialized = True

            result = await repository.get_latest_indicator("NSE@TEST", "RSI")

            assert result is not None
            assert result['indicator_name'] == 'RSI'
            assert result['parameters']['period'] == 14
            assert result['values']['rsi'] == 65.5

    @pytest.mark.asyncio
    async def test_get_latest_indicator_database_error(self, repository):
        """Test latest indicator retrieval with database error - should raise exception."""
        session, connection = AsyncMock(), AsyncMock()
        connection.fetchrow.side_effect = Exception("Database connection lost")
        session.acquire.return_value.__aenter__.return_value = connection

        with patch.object(repository, 'db_connection', session):
            repository._initialized = True

            # Should raise DatabaseError, not return None silently
            with pytest.raises(DatabaseError) as exc_info:
                await repository.get_latest_indicator("NSE@TEST", "RSI")

            assert "Failed to fetch latest indicator RSI for NSE@TEST" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_computation_metrics_database_error(self, repository):
        """Test computation metrics retrieval with database error - should raise exception."""
        session, connection = AsyncMock(), AsyncMock()
        connection.fetchrow.side_effect = Exception("Metrics query failed")
        session.acquire.return_value.__aenter__.return_value = connection

        with patch.object(repository, 'db_connection', session):
            repository._initialized = True

            start_time = datetime.utcnow() - timedelta(hours=1)
            end_time = datetime.utcnow()

            # Should raise DatabaseError, not return empty dict silently
            with pytest.raises(DatabaseError) as exc_info:
                await repository.get_computation_metrics(start_time, end_time)

            assert "Failed to fetch computation metrics" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_cleanup_old_data_success(self, repository):
        """Test successful old data cleanup."""
        session, connection = AsyncMock(), AsyncMock()
        connection.execute.return_value = "DELETE 10"  # Mock delete count
        session.acquire.return_value.__aenter__.return_value = connection

        with patch.object(repository, 'db_connection', session):
            repository._initialized = True

            # Should complete without raising exception
            await repository.cleanup_old_data(retention_days=30)

            # Verify execute was called for both Greeks and indicators
            assert connection.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_connection_initialization_failure(self, repository):
        """Test repository initialization failure."""
        with patch('app.repositories.signal_repository.get_timescaledb_session') as mock_get_session:
            mock_get_session.side_effect = Exception("Cannot connect to database")

            with pytest.raises(Exception):
                await repository.initialize()

    @pytest.mark.asyncio
    async def test_save_custom_timeframe_data(self, repository):
        """Test custom timeframe data saving."""
        session, connection = AsyncMock(), AsyncMock()
        session.acquire.return_value.__aenter__.return_value = connection

        with patch.object(repository, 'db_connection', session):
            repository._initialized = True

            test_data = [
                {"timestamp": datetime.utcnow(), "value": 100},
                {"timestamp": datetime.utcnow(), "value": 101}
            ]

            await repository.save_custom_timeframe_data(
                "NSE@TEST",
                "greeks",
                5,  # 5-minute timeframe
                test_data
            )

            connection.executemany.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_custom_timeframe_data_database_error(self, repository):
        """Test custom timeframe data retrieval with database error."""
        session, connection = AsyncMock(), AsyncMock()
        connection.fetch.side_effect = Exception("Custom timeframe query failed")
        session.acquire.return_value.__aenter__.return_value = connection

        with patch.object(repository, 'db_connection', session):
            repository._initialized = True

            start_time = datetime.utcnow() - timedelta(hours=1)
            end_time = datetime.utcnow()

            # Should raise DatabaseError, not return empty list silently
            with pytest.raises(DatabaseError):
                await repository.get_custom_timeframe_data(
                    "NSE@TEST",
                    "greeks",
                    5,
                    start_time,
                    end_time
                )
